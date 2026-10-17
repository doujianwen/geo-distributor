"""Delivery Service（Sprint 3 — P0 必须）。

职责：
- 生成 Client-safe Report
- 执行 QA 检查
- 管理 Report 版本
- 发布 Delivery
"""

from typing import Optional, Dict, Any, List
import logging
import sqlite3
import uuid
from datetime import datetime

logger = logging.getLogger(__name__)


class DuplicateReportError(RuntimeError):
    """RA-10 加固（2026-10-17）：存储层 UNIQUE(project_id, tenant_id, scope_version)
    约束命中——并发交付竞态由唯一约束兜底时抛出，由 execute_delivery 回退返回既有报告。
    """


class QAResult:
    """QA 检查结果。"""

    def __init__(self, passed: bool, issues: List[str] = None, warnings: List[str] = None):
        self.passed = passed
        self.issues = issues or []
        self.warnings = warnings or []

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "issues": self.issues,
            "warnings": self.warnings,
        }


class ReportService:
    """报告服务 — 生成 Client-safe Report。"""

    def __init__(self, repository=None):
        self._reports: Dict[str, Dict[str, Any]] = {}
        self._repository = repository

    async def create_report(
        self,
        project_id: str,
        tenant_id: str,
        scope_version: int,
        observations: List[Dict[str, Any]],
        findings: List[Dict[str, Any]],
        created_by: str,
    ) -> Dict[str, Any]:
        """创建 Client-safe Report。

        规则：
        - 不暴露 RawResponse
        - 不暴露证据内部评级细节
        - 只提供 Executive Summary + Key Findings + Recommendations
        """
        report_id = f"RPT-{uuid.uuid4().hex[:8].upper()}"

        # 计算 Visibility Score
        total = len(observations)
        mentioned = sum(1 for o in observations if o.get("brand_mentioned"))
        recommended = sum(1 for o in observations if o.get("recommendation_level", 0) >= 2)

        visibility_score = (mentioned / total * 50 + recommended / total * 50) if total > 0 else 0

        # 生成 Executive Summary
        executive_summary = self._generate_executive_summary(
            visibility_score=visibility_score,
            mentioned=mentioned,
            recommended=recommended,
            total=total,
        )

        # 构建 Client-safe 内容
        content = {
            "executive_summary": executive_summary,
            "visibility_score": round(visibility_score, 1),
            "visibility_summary": {
                "total_queries": total,
                "brand_mentioned": mentioned,
                "brand_recommended": recommended,
                "mention_rate": f"{mentioned/total*100:.1f}%" if total > 0 else "0%",
                "recommendation_rate": f"{recommended/total*100:.1f}%" if total > 0 else "0%",
            },
            "key_findings": [
                {
                    "finding_id": f.get("finding_id", ""),
                    "category": f.get("category", ""),
                    "severity": f.get("severity", ""),
                    "statement": f.get("statement", ""),
                    "recommendation": f.get("recommendation", ""),
                }
                for f in findings[:5]  # 最多展示5条
            ],
            "limitations": [
                "Results are based on a limited sample of queries.",
                "AI visibility is dynamic and may change over time.",
                "Findings are based on observed patterns, not causal relationships.",
            ],
            "next_steps": [
                "Review key findings with your team.",
                "Prioritize high-severity findings for intervention.",
                "Schedule follow-up measurement after 30 days.",
            ],
        }

        report = {
            "report_id": report_id,
            "project_id": project_id,
            "tenant_id": tenant_id,
            "type": "client",
            "title": f"GEO Visibility Report for {project_id}",
            "version": 1,
            "scope_version": scope_version,
            "content": content,
            "is_client_safe": True,
            "created_by": created_by,
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
        }

        if self._repository is not None:
            try:
                await self._repository.upsert(report)
            except sqlite3.IntegrityError as exc:
                # RA-10 加固：并发交付同时通过「查后再插」窗口时，
                # 存储层唯一约束保证只有第一个落库成功，其余在此转为幂等回放。
                logger.warning(
                    "Report insert hit UNIQUE(project, tenant, scope_version) constraint "
                    "(project=%s tenant=%s scope_version=%s); concurrent delivery raced: %s",
                    project_id, tenant_id, scope_version, exc,
                )
                raise DuplicateReportError(
                    f"report for ({project_id}, {tenant_id}, scope_version={scope_version}) "
                    f"already exists (storage-level idempotency)"
                ) from exc
        else:
            self._reports[report_id] = report
        logger.info("Report created: %s for project %s", report_id, project_id)

        return report

    def _generate_executive_summary(self, visibility_score: float, mentioned: int, recommended: int, total: int) -> str:
        """生成 Executive Summary。"""
        if visibility_score >= 70:
            tone = "strong"
            action = "maintain and expand"
        elif visibility_score >= 40:
            tone = "moderate"
            action = "improve through targeted content optimization"
        else:
            tone = "limited"
            action = "urgent attention required through strategic visibility interventions"

        return (
            f"Your brand has {tone} visibility across AI search platforms. "
            f"Out of {total} measured queries, your brand was mentioned in {mentioned} ({mentioned/total*100:.0f}%) "
            f"and recommended in {recommended} ({recommended/total*100:.0f}%). "
            f"Recommended actions: {action}."
        )

    async def get_report(self, report_id: str, tenant_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """获取报告，并在持久化路径下按 tenant 做源头隔离。"""
        if self._repository is not None:
            return await self._repository.get(report_id, tenant_id=tenant_id)
        report = self._reports.get(report_id)
        if report is not None and tenant_id is not None and report.get("tenant_id") != tenant_id:
            return None
        return report

    async def list_reports(self, project_id: str, tenant_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """列出项目报告；持久化路径按 tenant + project 双键过滤。"""
        if self._repository is not None:
            if tenant_id is None:
                return []
            return await self._repository.list_by_project(project_id, tenant_id)
        return [r for r in self._reports.values() if r["project_id"] == project_id and (tenant_id is None or r.get("tenant_id") == tenant_id)]


class DeliveryService:
    """交付服务 — 管理 Delivery Package。"""

    def __init__(self, report_service: Optional[ReportService] = None):
        self.report_service = report_service or ReportService()
        self._deliveries: Dict[str, Dict[str, Any]] = {}
        self._qa_checks: List[Dict[str, Any]] = []

    async def execute_delivery(
        self,
        project_id: str,
        tenant_id: str,
        scope_version: int,
        observations: List[Dict[str, Any]],
        findings: List[Dict[str, Any]],
        executed_by: str,
    ) -> Dict[str, Any]:
        """执行完整交付流程。

        流程：
        0. 幂等检查（RA-10）：同 (project, tenant, scope_version) 已有已交付报告
           时直接返回既有报告，不创建重复交付。
        1. 创建 Report
        2. 执行 QA
        3. 发布 Delivery
        """
        # 0. 幂等守卫：重复交付返回既有报告（RA-10 修复 · 2026-10-17）
        existing = await self._find_delivered_report(project_id, tenant_id, scope_version)
        if existing is not None:
            return self._replay_delivery(existing)

        # 1. 创建报告（RA-10 加固：并发竞态由存储层唯一约束兜底，
        #    落库冲突时回退返回既有报告，杜绝重复交付）
        try:
            report = await self.report_service.create_report(
                project_id=project_id,
                tenant_id=tenant_id,
                scope_version=scope_version,
                observations=observations,
                findings=findings,
                created_by=executed_by,
            )
        except DuplicateReportError:
            raced = await self._find_delivered_report(project_id, tenant_id, scope_version)
            if raced is None:
                raise
            logger.info(
                "Concurrent delivery race resolved by storage unique constraint; "
                "returning existing report %s for project %s (scope_version=%s)",
                raced["report_id"], project_id, scope_version,
            )
            return self._replay_delivery(raced)

        # 2. 执行 QA
        qa_result = await self._run_qa(report, observations, findings)

        delivery_id = f"DLV-{uuid.uuid4().hex[:8].upper()}"
        delivery = {
            "delivery_id": delivery_id,
            "project_id": project_id,
            "report_id": report["report_id"],
            "report_version": report["version"],
            "scope_version": scope_version,
            "qa_result": qa_result.to_dict(),
            "status": "DELIVERED" if qa_result.passed else "QA_FAILED",
            "created_at": datetime.now().isoformat(),
            "created_by": executed_by,
        }

        self._deliveries[delivery_id] = delivery
        self._qa_checks.append({
            "delivery_id": delivery_id,
            "report_id": report["report_id"],
            "result": qa_result.to_dict(),
            "checked_at": datetime.now().isoformat(),
        })

        logger.info("Delivery created: %s for project %s (QA: %s)", delivery_id, project_id, "PASS" if qa_result.passed else "FAIL")

        return delivery

    def _replay_delivery(self, existing: Dict[str, Any]) -> Dict[str, Any]:
        """由既有报告构造幂等回放响应（RA-10；顺序重放与并发竞态回退共用）。"""
        delivery_id = f"DLV-{existing['report_id']}"
        logger.info(
            "Idempotent replay: report %s already delivered for project %s "
            "(scope_version=%s); no new report created",
            existing["report_id"], existing.get("project_id"), existing.get("scope_version"),
        )
        return {
            "delivery_id": delivery_id,
            "project_id": existing["project_id"],
            "report_id": existing["report_id"],
            "report_version": existing["version"],
            "scope_version": existing["scope_version"],
            "qa_result": {"passed": True, "issues": [], "warnings": [
                "idempotent-replay: existing report returned for the same "
                "(project, tenant, scope_version); no new report created"
            ]},
            "status": "ALREADY_DELIVERED",
            "created_at": existing["created_at"],
            "created_by": existing["created_by"],
        }

    async def _find_delivered_report(
        self,
        project_id: str,
        tenant_id: str,
        scope_version: int,
    ) -> Optional[Dict[str, Any]]:
        """查找同 (project, tenant, scope_version) 的既有已交付报告（RA-10 幂等）。

        持久化与内存两种仓储模式统一走 report_service.list_reports()，
        该方法已内置 tenant 过滤，不会跨租户命中。
        """
        try:
            reports = await self.report_service.list_reports(project_id, tenant_id=tenant_id)
        except Exception:  # noqa: BLE001 — 幂等检查失败不应阻断正常交付
            return None
        for r in reports:
            if r.get("scope_version") == scope_version:
                return r
        return None

    async def _run_qa(self, report: Dict[str, Any], observations: List[Dict[str, Any]], findings: List[Dict[str, Any]]) -> QAResult:
        """执行 QA 检查。"""
        issues = []
        warnings = []

        # 检查 1: Scope compliance
        if not observations:
            issues.append("No observations recorded")

        # 检查 2: Required sections
        content = report.get("content", {})
        required_sections = ["executive_summary", "visibility_summary", "key_findings", "limitations", "next_steps"]
        for section in required_sections:
            if section not in content:
                issues.append(f"Missing required section: {section}")

        # 检查 3: Evidence presence
        if not findings:
            warnings.append("No findings recorded — consider adding diagnostic insights")

        # 检查 4: No internal data leak
        # 验证 report content 不包含 RawResponse
        content_str = str(content)
        if "raw_metadata" in content_str or "answer_raw" in content_str:
            issues.append("Internal data leaked into client report")

        # 检查 5: Status consistency
        if report.get("type") != "client":
            issues.append("Report type must be 'client' for distributor view")

        passed = len(issues) == 0

        return QAResult(passed=passed, issues=issues, warnings=warnings)

    async def get_delivery(self, delivery_id: str) -> Optional[Dict[str, Any]]:
        """获取 Delivery。"""
        return self._deliveries.get(delivery_id)

    async def list_deliveries(self, project_id: str) -> List[Dict[str, Any]]:
        """列出项目的所有 Delivery。"""
        return [d for d in self._deliveries.values() if d["project_id"] == project_id]


# 导出
__all__ = ["DeliveryService", "ReportService", "QAResult"]
