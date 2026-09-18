"""分销/采集调度服务（平台层）。

职责：管理 Organization / Brand / CollectionProject 的生命周期，
调度采集运行（Run）并汇总为 CollectionReport。

⚠️ 实现纪律：
    本服务**只依赖 BaseAdapter 的真实契约**（health_check / collect_prompt /
    collect_batch）。旧版本调用过 `adapter.run_collection()` 与
    `adapter.generate_report()` —— 这两个方法在 BaseAdapter 上**并不存在**，
    属于占位代码调用虚构接口，运行必然 AttributeError。现改为：
      - Run     由本服务基于 collect_batch 的结果自行组装
      - Report  由本服务基于该 Run 的观测统计自行生成

命名说明：本模块用的是**平台层采集侧**模型（Organization / Brand /
CollectionProject / Run / CollectionReport），与商业交付侧的
models.project.Project 是两套东西，勿混用。
"""

from datetime import datetime
from typing import List, Optional, Dict, Any

from ..models import (
    Organization, OrganizationStatus,
    Account,
    Brand, BrandTarget,
    CollectionProject, CollectionProjectStatus,
    Run,
    CollectionReport,
    Prompt,
)
from ..adapters import BaseAdapter
from ..compatibility.base import PlatformObservation


# ------------------------------------------------------------------
# 异常
# ------------------------------------------------------------------


class DistributionError(Exception):
    """分销服务业务异常（参数校验失败、引用不存在等）。"""


# --- observation status semantics ---
# valid        : answer actually collected
# uncollected  : no observation for this prompt in the data source (placeholder)
# failed       : collection error
#
# Treating "not_collected" as failure makes every Run red; treating it as valid
# makes the report claim "mention rate 0%" from data that was never collected.
_VALID_STATUS = {"success", "ok", "completed", ""}
_UNCOLLECTED_STATUS = {"not_collected", "skipped", "no_data", "pending"}
#
# prompt_mismatch：prompt_id 在库里命中、但 prompt_text 对不上。
# 适配器拒绝返回错配数据，这里单列记账——它既不是"采到了"，
# 也不是"数据源没数据"，而是"问的问题和库里存的不是同一个"。
# 混进 successful 会让 Run 显示全绿、报告给出一个衡量了别的问题的提及率。
_MISMATCH_STATUS = {"prompt_mismatch"}


def _obs_status(obs: Any) -> str:
    return (getattr(obs, "status", "") or "").strip().lower()


# ------------------------------------------------------------------
# 服务
# ------------------------------------------------------------------


class DistributionService:
    """分销系统核心业务服务。

    存储：进程内字典（与项目其余 InMemory 仓储一致）。
    若需跨重启保留，可注入实现了同名方法的持久化仓储——本类的
    所有读写都集中在 _orgs / _brands / _projects / _runs / _reports 上，
    替换点唯一。
    """

    def __init__(self, adapter: BaseAdapter):
        self._adapter = adapter
        self._orgs: Dict[str, Organization] = {}
        self._accounts: Dict[str, Account] = {}
        self._brands: Dict[str, Brand] = {}
        self._projects: Dict[str, CollectionProject] = {}
        self._runs: Dict[str, Run] = {}
        self._reports: Dict[str, CollectionReport] = {}
        self._run_observations: Dict[str, List[PlatformObservation]] = {}
        self._seq: Dict[str, int] = {}

    # ------------------------------------------------------------------
    # 内部工具
    # ------------------------------------------------------------------

    def _next_id(self, prefix: str) -> str:
        """生成单调递增 ID，如 ORG-001。"""
        n = self._seq.get(prefix, 0) + 1
        self._seq[prefix] = n
        return f"{prefix}-{n:03d}"

    @staticmethod
    def _ts() -> str:
        return datetime.now().isoformat()

    # ------------------------------------------------------------------
    # Organization
    # ------------------------------------------------------------------

    async def create_organization(
        self,
        name: str,
        contact_email: str = "",
        status: OrganizationStatus = OrganizationStatus.ACTIVE,
    ) -> Organization:
        if not name or not name.strip():
            raise DistributionError("organization name is required")
        # 同名去重：避免重复创建造成数据噪音
        for org in self._orgs.values():
            if org.name.strip().lower() == name.strip().lower():
                return org
        org = Organization(
            org_id=self._next_id("ORG"),
            name=name.strip(),
            contact_email=contact_email,
            status=status,
        )
        self._orgs[org.org_id] = org
        return org

    def get_organization(self, org_id: str) -> Optional[Organization]:
        return self._orgs.get(org_id)

    def list_organizations(self) -> List[Organization]:
        return list(self._orgs.values())

    # ------------------------------------------------------------------
    # Account
    # ------------------------------------------------------------------

    async def create_account(
        self, org_id: str, email: str, role: str = "viewer"
    ) -> Account:
        if org_id not in self._orgs:
            raise DistributionError(f"organization not found: {org_id}")
        if not email or "@" not in email:
            raise DistributionError(f"invalid email: {email}")
        acct = Account(
            account_id=self._next_id("ACC"),
            org_id=org_id,
            email=email.strip().lower(),
            role=role,
        )
        self._accounts[acct.account_id] = acct
        return acct

    def list_accounts(self, org_id: str) -> List[Account]:
        return [a for a in self._accounts.values() if a.org_id == org_id]

    # ------------------------------------------------------------------
    # Brand
    # ------------------------------------------------------------------

    async def create_brand(
        self,
        org_id: str,
        name: str,
        aliases: Optional[List[str]] = None,
        target: BrandTarget = BrandTarget.PRIMARY,
        competitors: Optional[List[str]] = None,
    ) -> Brand:
        if org_id not in self._orgs:
            raise DistributionError(f"organization not found: {org_id}")
        if not name or not name.strip():
            raise DistributionError("brand name is required")
        for b in self._brands.values():
            if b.org_id == org_id and b.name.strip().lower() == name.strip().lower():
                return b
        brand = Brand(
            brand_id=self._next_id("BRAND"),
            org_id=org_id,
            name=name.strip(),
            target=target,
            aliases=aliases or [],
            competitors=competitors or [],
        )
        self._brands[brand.brand_id] = brand
        return brand

    def get_brand(self, brand_id: str) -> Optional[Brand]:
        return self._brands.get(brand_id)

    def list_brands(self, org_id: str) -> List[Brand]:
        return [b for b in self._brands.values() if b.org_id == org_id]

    # ------------------------------------------------------------------
    # CollectionProject
    # ------------------------------------------------------------------

    async def create_project(
        self,
        org_id: str,
        brand_id: str,
        name: str,
        prompts_file: str,
        engines: Optional[List[str]] = None,
        schedule_cron: str = "",
    ) -> CollectionProject:
        if org_id not in self._orgs:
            raise DistributionError(f"organization not found: {org_id}")
        if brand_id not in self._brands:
            raise DistributionError(f"brand not found: {brand_id}")
        brand = self._brands[brand_id]
        if brand.org_id != org_id:
            raise DistributionError(
                f"brand {brand_id} does not belong to org {org_id}"
            )
        if not name or not name.strip():
            raise DistributionError("project name is required")

        project = CollectionProject(
            project_id=self._next_id("CPROJ"),
            org_id=org_id,
            brand_id=brand_id,
            name=name.strip(),
            prompts_file=prompts_file,
            engines=engines or [],
            schedule_cron=schedule_cron,
        )
        self._projects[project.project_id] = project
        return project

    def get_project(self, project_id: str) -> Optional[CollectionProject]:
        return self._projects.get(project_id)

    def list_projects(
        self,
        org_id: Optional[str] = None,
        status: Optional[CollectionProjectStatus] = None,
    ) -> List[CollectionProject]:
        out = list(self._projects.values())
        if org_id:
            out = [p for p in out if p.org_id == org_id]
        if status:
            out = [p for p in out if p.status == status]
        return out

    def set_project_status(
        self, project_id: str, status: CollectionProjectStatus
    ) -> CollectionProject:
        project = self._projects.get(project_id)
        if not project:
            raise DistributionError(f"project not found: {project_id}")
        project.status = status
        return project

    # ------------------------------------------------------------------
    # Run（采集执行）
    # ------------------------------------------------------------------

    async def run_project(self, project: CollectionProject) -> Run:
        """触发一次采集运行。

        基于 adapter.collect_batch 的真实契约；prompts 来自 project.prompts_file。
        """
        if not project.prompts_file:
            raise DistributionError(
                f"project {project.project_id} has no prompts_file configured"
            )

        prompts = self.load_prompts(project.prompts_file)
        if not prompts:
            raise DistributionError(
                f"no prompts loaded from {project.prompts_file}"
            )

        # 采集前把目标品牌同步给适配器。
        # GeoCollectorDBAdapter 的 SQL 按 brand 过滤，若沿用构造时的默认 brand
        # （或空值）会一条都查不到，返回 not_collected 占位——表面像"采集失败"，
        # 实则是"查错了品牌"。
        brand = self._brands.get(project.brand_id)
        if brand is not None and hasattr(self._adapter, "brand"):
            try:
                self._adapter.brand = brand.name
            except Exception:  # noqa: BLE001 — 适配器不支持切换时按原配置继续
                pass

        run = Run(
            run_id=self._next_id("RUN"),
            project_id=project.project_id,
            started_at=self._ts(),
            status="running",
            total_prompts=len(prompts),
        )
        self._runs[run.run_id] = run

        observations: List[PlatformObservation] = []
        failed = 0
        skipped = 0
        mismatched = 0
        errors: List[str] = []

        try:
            # 单个 prompt 失败不应中断整批——collect_batch 契约已保证，
            # 这里再兜一层，避免 adapter 实现不一致时整个 Run 丢失。
            results = await self._adapter.collect_batch(prompts)
            observations = list(results or [])
        except Exception as exc:  # noqa: BLE001 — 记录到 Run 而非抛出
            failed = len(prompts)
            errors.append(f"batch failed: {type(exc).__name__}: {exc}")
            run.status = "failed"
        else:
            for obs in observations:
                st = _obs_status(obs)
                if st in _MISMATCH_STATUS:
                    mismatched += 1
                    skipped += 1
                elif st in _UNCOLLECTED_STATUS:
                    skipped += 1
                elif st not in _VALID_STATUS:
                    failed += 1
                    errors.append(f"{getattr(obs, 'observation_id', '?')}: status={st or 'empty'}")

            if mismatched:
                errors.append(
                    f"{mismatched}/{len(prompts)} prompts: prompt_id matched a different "
                    f"prompt_text in the data source — excluded from metrics "
                    f"(check {project.prompts_file} prompt_id mapping)"
                )
            run.status = "completed" if failed == 0 else (
                "failed" if len(observations) == 0 else "completed_with_errors"
            )

        run.ended_at = self._ts()
        run.successful = max(0, len(observations) - failed - skipped)
        run.failed = failed
        run.skipped = skipped + max(0, len(prompts) - len(observations))
        try:
            run.prompt_mismatch = mismatched
        except Exception:  # noqa: BLE001 — Run 实现不支持新字段时降级，不影响主流程
            pass
        run.error_summary = "; ".join(errors)[:500]

        self._run_observations[run.run_id] = observations
        return run

    def get_run(self, run_id: str) -> Optional[Run]:
        return self._runs.get(run_id)

    def list_runs(self, project_id: Optional[str] = None) -> List[Run]:
        out = list(self._runs.values())
        if project_id:
            out = [r for r in out if r.project_id == project_id]
        return out

    def get_run_observations(self, run_id: str) -> List[PlatformObservation]:
        """取回该 Run 采集到的观测（供报告/分析复用）。"""
        return self._run_observations.get(run_id, [])

    # ------------------------------------------------------------------
    # Report
    # ------------------------------------------------------------------

    async def generate_report_for_run(self, run: Run) -> CollectionReport:
        """为一次运行生成汇总报告。

        统计口径基于该 Run 实际采集到的观测；无观测时各项为 0 并在
        summary 中标注原因，不回填任何推测值。
        """
        observations = self.get_run_observations(run.run_id)
        project = self._projects.get(run.project_id)
        brand_name = ""
        if project:
            brand = self._brands.get(project.brand_id)
            brand_name = brand.name if brand else ""

        # ⚠️ 只按"有效观测"统计比率。未采集的占位观测（status=not_collected）
        # 若计入分母，会得出"提及率 0%"——那是用没采到的数据冒充结论。
        valid = [o for o in observations if _obs_status(o) in _VALID_STATUS]
        uncollected = len(observations) - len(valid)
        mismatched = sum(
            1 for o in observations if _obs_status(o) in _MISMATCH_STATUS
        )

        mentioned = sum(1 for o in valid if getattr(o, "brand_mentioned", False))
        recommended = sum(
            1 for o in valid if (getattr(o, "recommendation_level", 0) or 0) >= 2
        )
        total = len(valid)

        if total == 0 and mismatched:
            note = (
                f"{mismatched}/{len(observations)} 条 prompt 的 prompt_id 在数据源中"
                "命中了**不同的** prompt 文本，已按错配剔除，不出具数值结论。"
                f"请核对 {project.prompts_file if project else 'prompts 文件'} 的 "
                "prompt_id 与数据源是否同一套编号。"
            )
        elif total == 0:
            note = (
                f"本次运行未采集到任何有效观测"
                f"（共 {len(observations)} 条记录，其中未采集 {uncollected} 条），"
                "提及率/推荐率无意义，不出具数值结论。"
            )
        elif mismatched or uncollected:
            parts = [f"有效观测 {total} 条"]
            if mismatched:
                parts.append(f"错配剔除 {mismatched} 条（prompt_id 与文本不一致）")
            if uncollected - mismatched > 0:
                parts.append(f"未采集 {uncollected - mismatched} 条")
            note = "；".join(parts) + "，均未计入比率分母。"
        else:
            note = ""

        report = CollectionReport(
            report_id=self._next_id("CREP"),
            project_id=run.project_id,
            run_ids=[run.run_id],
            title=f"{brand_name or run.project_id} — Run {run.run_id}",
            total_observations=total,
            brand_mentioned_count=mentioned,
            brand_recommended_count=recommended,
            summary={
                "brand": brand_name,
                "run_status": run.status,
                "total_prompts": run.total_prompts,
                "successful": run.successful,
                "failed": run.failed,
                "skipped": run.skipped,
                "records_returned": len(observations),
                "uncollected": uncollected,
                "prompt_mismatch": getattr(run, "prompt_mismatch", 0),
                "mention_rate": round(mentioned / total * 100, 2) if total else 0.0,
                "recommendation_rate": round(recommended / total * 100, 2) if total else 0.0,
                "note": note,
            },
        )
        self._reports[report.report_id] = report
        return report

    def get_report(self, report_id: str) -> Optional[CollectionReport]:
        return self._reports.get(report_id)

    def list_reports(self, project_id: Optional[str] = None) -> List[CollectionReport]:
        out = list(self._reports.values())
        if project_id:
            out = [r for r in out if r.project_id == project_id]
        return out

    # ------------------------------------------------------------------
    # prompts 加载
    # ------------------------------------------------------------------

    @staticmethod
    def load_prompts(path: str) -> List[Prompt]:
        """从文件加载 prompts。

        支持三种格式：
          1. JSON 数组：[{"prompt_id":1,"text":"...","category":"","intent":"","location":""}]
          2. JSONL：每行一个 JSON 对象
          3. 纯文本：每行一条 prompt（prompt_id 按行号生成）

        无法识别时返回 []，由调用方给出明确错误——不静默造数据。
        """
        import json
        import os

        if not path or not os.path.exists(path):
            return []

        with open(path, encoding="utf-8") as f:
            raw = f.read()

        stripped = raw.strip()
        if not stripped:
            return []

        prompts: List[Prompt] = []

        if stripped.startswith("["):
            try:
                data = json.loads(stripped)
            except ValueError:
                return []
            for i, item in enumerate(data, start=1):
                if isinstance(item, dict):
                    prompts.append(
                        Prompt(
                            prompt_id=item.get("prompt_id", i),
                            text=item.get("text") or item.get("prompt_text") or "",
                            category=item.get("category", "") or "",
                            intent=item.get("intent", "") or "",
                            location=item.get("location", "") or "",
                        )
                    )
                elif isinstance(item, str):
                    prompts.append(
                        Prompt(prompt_id=i, text=item, category="", intent="", location="")
                    )
            return [p for p in prompts if p.text]

        # JSONL 或纯文本
        for i, line in enumerate(raw.splitlines(), start=1):
            line = line.strip()
            if not line:
                continue
            if line.startswith("{"):
                try:
                    item = json.loads(line)
                except ValueError:
                    continue
                prompts.append(
                    Prompt(
                        prompt_id=item.get("prompt_id", i),
                        text=item.get("text") or item.get("prompt_text") or "",
                        category=item.get("category", "") or "",
                        intent=item.get("intent", "") or "",
                        location=item.get("location", "") or "",
                    )
                )
            else:
                prompts.append(
                    Prompt(prompt_id=i, text=line, category="", intent="", location="")
                )

        return [p for p in prompts if p.text]
