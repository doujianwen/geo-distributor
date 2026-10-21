"""Reports router — retrieve generated reports for projects."""

from __future__ import annotations
from typing import Annotated, List

from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import BaseModel, Field

from .. import state
from ..deps import authenticate, require_write
from geo_distributor.repositories.base import PermissionError as RepoPermissionError

router = APIRouter(prefix="/reports", tags=["reports"])


# ------------------------------------------------------------------
# Response schema
# ------------------------------------------------------------------

class ReportOut(BaseModel):
    report_id: str
    project_id: str
    tenant_id: str
    title: str
    version: int
    visibility_score: float
    visibility_summary: dict
    key_findings: List[dict]
    limitations: List[str]
    next_steps: List[str]
    created_at: str
    data_quality: dict = Field(default_factory=dict)
    geo_snapshot: dict | None = None
    is_demo: bool = False

    model_config = {"from_attributes": True}


def report_to_out(r: dict) -> dict:
    """把 ReportService 的**存储形态**展平为 ReportOut 契约。

    Commercial V1 · P0-2 缺陷修复：ReportService.create_report 把 client-safe 内容
    放在 `content` 之下（executive_summary / visibility_score / visibility_summary /
    key_findings / limitations / next_steps），而 ReportOut 期望这些字段在顶层。
    原实现 `ReportOut(**r)` 在同租户正常路径必然 5 个 missing → ValidationError(500)。

    这里做一次**显式投影**：不改存储结构、不删字段、不放宽契约，只是把已知的
    client-safe 字段提到顶层。未识别字段保持原样（多余键由 pydantic 忽略）。
    """
    out = dict(r)
    content = r.get("content")
    if not isinstance(content, dict):
        content = {}

    def pick(key: str, default):
        if key in content:
            return content[key]
        return r.get(key, default)

    out["visibility_score"] = pick("visibility_score", 0.0)
    out["visibility_summary"] = pick("visibility_summary", {})
    out["key_findings"] = pick("key_findings", [])
    out["limitations"] = pick("limitations", [])
    out["next_steps"] = pick("next_steps", [])
    # Historical reports have no auditable valid denominator. Do not infer one
    # or rewrite stored numbers; hide unsupported headline metrics in the UI.
    out["data_quality"] = {
        "status": "legacy_unverified",
        "valid_queries": None,
        "period": None,
        "source": None,
        "note": "历史汇总未提供可核验的有效分母与测量窗口；指标不作为当前效果结论。",
    }
    return out


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _require_tenant(x_tenant_id: str | None) -> str:
    """B-1 修复：tenant context 缺失即 fail closed。"""
    # B-2：tenant 已由认证层（密钥绑定）确定，header 仅作可选声明。
    # 缺失时不报错 —— 使用认证上下文中的 tenant。
    # 声明与密钥冲突由 api.auth.resolve_tenant 拦截（403）。
    return x_tenant_id or""


async def _verify_project_tenant(project_id: str, tenant_id: str) -> None:
    """B-1 修复：按 (project_id, tenant_id) 校验项目归属。"""
    if state.project_repo is None:
        raise HTTPException(status_code=503, detail="API not initialized")
    try:
        p = await state.project_repo.find_by_id(project_id, tenant_id=tenant_id)
    except RepoPermissionError:
        p = None
    if not p:
        raise HTTPException(status_code=404, detail="Project not found or tenant mismatch")


# ------------------------------------------------------------------
# Endpoints
# ------------------------------------------------------------------

@router.get("", response_model=List[ReportOut])
async def list_reports(
    project_id: str,
    x_tenant_id: Annotated[str | None, Header(alias="X-Tenant-ID")] = None, auth=Depends(authenticate)):
    """列出某项目的所有报告。"""
    tenant_id = auth.tenant_id  # B-2: 取认证 tenant，header 已交叉校验
    await _verify_project_tenant(project_id, tenant_id)  # B-1
    # Commercial V1 · P0-2 缺陷修复：`list_reports` 定义在 ReportService 上，
    # 而非 DeliveryService。原实现 `state.delivery_service.list_reports(...)` 在
    # **同租户正常路径**必然 AttributeError → 500（跨租户路径因上游 404 而掩盖，
    # 故既有用例未暴露）。此处改用 state.report_service（= delivery_service.report_service）。
    svc = state.report_service
    if svc is None:
        raise HTTPException(status_code=503, detail="API not initialized")
    reports = await svc.list_reports(project_id, tenant_id=tenant_id)
    if any(r.get("tenant_id") != tenant_id for r in reports):  # B-1 双保险
        raise HTTPException(status_code=404, detail="Report not found")
    from ..geo_view import report_projection
    return [ReportOut(**await report_projection(r)) for r in reports if r.get("is_client_safe") is True]


@router.get("/{report_id}", response_model=ReportOut)
async def get_report(
    report_id: str,
    x_tenant_id: Annotated[str | None, Header(alias="X-Tenant-ID")] = None, auth=Depends(authenticate)):
    """获取单个报告详情。"""
    tenant_id = auth.tenant_id  # B-2: 取认证 tenant，header 已交叉校验  # B-1
    # 同 list_reports：报告读写统一走 ReportService。
    svc = state.report_service
    if svc is None:
        raise HTTPException(status_code=503, detail="API not initialized")
    report = await svc.get_report(report_id, tenant_id=tenant_id)
    if not report or report.get("is_client_safe") is not True:
        raise HTTPException(status_code=404, detail="Report not found")
    if report.get("tenant_id") != tenant_id:  # B-1
        raise HTTPException(status_code=404, detail="Report not found")
    from ..geo_view import report_projection
    return ReportOut(**await report_projection(report))
