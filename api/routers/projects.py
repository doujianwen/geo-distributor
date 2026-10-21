"""Projects router — CRUD + lifecycle for Project entities with tenant isolation."""

from __future__ import annotations
from typing import Annotated, List

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from .. import state
from geo_distributor.repositories.base import PermissionError as RepoPermissionError
from ..deps import authenticate, require_write, require_hq
from geo_distributor.models import ServiceStage, DEFAULT_STAGE_SEQUENCE

router = APIRouter(prefix="/projects", tags=["projects"])


@router.get("/{project_id}/geo")
async def get_geo_view(project_id: str, auth=Depends(authenticate)):
    from ..geo_view import geo_view
    return await geo_view(project_id, auth.tenant_id)


# ------------------------------------------------------------------
# Request / Response schemas
# ------------------------------------------------------------------

class ProjectCreate(BaseModel):
    """通过 Service Request 创建 Project（简化入口，跳过完整 SCOPING 流程）。"""
    tenant_id: str = Field(..., description="Tenant ID 同时用于隔离验证")
    client_id: str
    service: str = "visibility_audit"  # legacy values remain accepted
    market_scope: str = "multi"  # single / multi / global
    target_market: List[str] = Field(default_factory=list)  # country/region codes
    target_languages: List[str] = Field(default_factory=list)
    service_duration: str = "to_be_determined"  # one_time / 1_month / 3_months / 6_months / 12_months / to_be_determined
    target_products: List[str] = Field(default_factory=list)
    business_question: str = ""


class ProjectOut(BaseModel):
    project_id: str
    tenant_id: str
    client_id: str
    request_id: str
    scope_id: str
    status: str
    service: str = ""
    market_scope: str = "unspecified"
    target_market: List[str] = Field(default_factory=list)
    target_languages: List[str] = Field(default_factory=list)
    service_duration: str = "to_be_determined"
    # --- 四阶段工作流 ---
    service_stage: str = "site_diagnosis"
    service_stage_label: str = "网站诊断"
    stage_progress: int = 0
    progress_percent: int
    key_findings: List[str]
    report_ids: List[str]
    created_at: str
    updated_at: str
    blocked_reason: dict | None = None
    request_summary: dict = Field(default_factory=dict)

    model_config = {"from_attributes": True}


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _get_project_repo() -> state.ProjectRepository:
    if state.project_repo is None:
        raise HTTPException(status_code=503, detail="API not initialized")
    return state.project_repo  # type: ignore


async def _project_response(project) -> ProjectOut:
    """Return project fields plus HQ-approved request-intake details when available.

    Legacy projects without a readable request remain valid and use response defaults.
    """
    payload = project.to_dict()
    request_repo = state.request_repo
    request = None
    if request_repo is not None and project.request_id:
        try:
            request = await request_repo.find_by_id(project.request_id, tenant_id=project.tenant_id)
        except (RepoPermissionError, ValueError):
            request = None
    context = getattr(request, "business_context", None) if request else None
    payload.update({
        "service": getattr(request, "service", "") if request else "",
        "market_scope": getattr(context, "market_scope", "unspecified") if context else "unspecified",
        "target_market": list(getattr(context, "target_market", []) or []) if context else [],
        "target_languages": list(getattr(context, "target_languages", []) or []) if context else [],
        "service_duration": getattr(context, "service_duration", "to_be_determined") if context else "to_be_determined",
        "request_summary": {"request_id": project.request_id,
                            "status": getattr(getattr(request, "status", None), "value", ""),
                            "business_question": getattr(context, "business_question", "") if context else "",
                            "scope": (getattr(request, "workflow", {}) or {}).get("scope")},
    })
    return ProjectOut(**payload)


def _require_tenant(x_tenant_id: str | None) -> str:
    """B-1修复：tenant context 必须存在，缺失即fail closed。

    原实现用 `x_tenant_id or None` / `or ""`，会把查询退化为「无租户约束」，
    等于取消隔离。这里改为缺失即 400拒绝。
    """
    # B-2：tenant 已由认证层（密钥绑定）确定，header 仅作可选声明。
    # 缺失时不报错 —— 使用认证上下文中的 tenant。
    # 声明与密钥冲突由 api.auth.resolve_tenant 拦截（403）。
    return x_tenant_id or""


async def _load_project(project_id: str, tenant_id: str):
    """按 (project_id, tenant_id) 取项目，租户不符统一视为不可见。

    内存仓储 tenant 不匹配时抛 PermissionError（含对方 tenant_id，属信息泄漏），
    SQLite 仓储则返回 None。这里两者都归一为 404。
    """
    repo = _get_project_repo()
    try:
        return await repo.find_by_id(project_id, tenant_id=tenant_id)
    except RepoPermissionError:
        return None


# ------------------------------------------------------------------
# Endpoints
# ------------------------------------------------------------------

@router.post("", response_model=ProjectOut, status_code=201)
async def create_project(body: ProjectCreate, auth=Depends(require_hq)):
    """快速创建 Project — 走 Intake → Scoping → Approve 全链路。"""
    if auth.role != "HQ_MANAGEMENT":
        raise HTTPException(403, detail="仅总部管理角色可直接确认创建项目；渠道商请使用需求入口")
    svc = state.project_service
    if svc is None:
        raise HTTPException(status_code=503, detail="API not initialized")

    # B-2 安全：项目归属取认证 tenant，不信任请求体声明
    effective_tenant = auth.tenant_id
    if body.tenant_id and body.tenant_id != effective_tenant and not auth.is_hq:
        raise HTTPException(
            status_code=403,
            detail="X-Tenant-ID does not match the authenticated tenant",
        )
    if auth.is_hq and body.tenant_id:
        effective_tenant = body.tenant_id

    result = await svc.submit_request(
        tenant_id=effective_tenant,
        client_id=body.client_id,
        service=body.service,
        business_context={
            "market_scope": body.market_scope,
            "target_market": body.target_market,
            "target_languages": body.target_languages,
            "service_duration": body.service_duration,
            "target_products": body.target_products,
            "business_question": body.business_question,
            "known_competitors": [],
            "target_customer": "",
        },
    )

    # submit_request 只到 SCOPE_PENDING_APPROVAL，需要再 approve
    if result.get("status") == "SCOPE_PENDING_APPROVAL":
        approve_result = await svc.approve_scope(request_id=result["request_id"], approver_id="api-admin")
        if not approve_result.get("success", True):
            raise HTTPException(status_code=400, detail=approve_result.get("message", "Scope approval failed"))
        project_id = approve_result["project_id"]
    else:
        project_id = result.get("project_id")
        if not project_id:
            raise HTTPException(status_code=500, detail="Unexpected request result")

    project = await _load_project(project_id, effective_tenant)
    if not project:
        raise HTTPException(status_code=500, detail="Project created but not found")
    return await _project_response(project)


@router.get("", response_model=list[ProjectOut])
async def list_projects(
    x_tenant_id: Annotated[str | None, Header(alias="X-Tenant-ID")] = None,
    auth=Depends(authenticate),
):
    tenant_id = auth.tenant_id  # B-2: 取认证 tenant，header 已交叉校验
    repo = _get_project_repo()
    projects = await repo.find_by_tenant(tenant_id)
    return [await _project_response(p) for p in projects]


@router.get("/{project_id}", response_model=ProjectOut)
async def get_project(
    project_id: str,
    x_tenant_id: Annotated[str | None, Header(alias="X-Tenant-ID")] = None,
    auth=Depends(authenticate),
):
    tenant_id = auth.tenant_id  # B-2: 取认证 tenant，header 已交叉校验
    project = await _load_project(project_id, tenant_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return await _project_response(project)


class LifecycleInput(BaseModel):
    expected_updated_at: str = Field(default="", max_length=100)
    target_stage: str | None = None
    finding_ids: list[str] = Field(default_factory=list)
    measurement_ids: list[str] = Field(default_factory=list)
    report_ids: list[str] = Field(default_factory=list)


async def _lifecycle(project_id, body, key, auth, action):
    from ..hq_service import project_operation
    payload = (body or LifecycleInput()).model_dump()
    if payload.get("target_stage"):
        try:
            ServiceStage(payload["target_stage"])
        except ValueError:
            raise HTTPException(422, "请选择有效服务阶段")
    payload["action"] = action
    return project_operation(project_id, payload, key, auth)


@router.post("/{project_id}/start")
async def start_project(project_id: str, body: LifecycleInput | None = None,
                        idempotency_key: Annotated[str | None, Header()] = None, auth=Depends(require_hq)):
    return await _lifecycle(project_id, body, idempotency_key, auth, "start")


@router.post("/{project_id}/stage")
async def advance_stage(project_id: str, body: LifecycleInput | None = None,
                        idempotency_key: Annotated[str | None, Header()] = None, auth=Depends(require_hq)):
    return await _lifecycle(project_id, body, idempotency_key, auth, "advance")


@router.post("/{project_id}/stage/complete")
async def complete_stage(project_id: str, body: LifecycleInput | None = None,
                         idempotency_key: Annotated[str | None, Header()] = None, auth=Depends(require_hq)):
    return await _lifecycle(project_id, body, idempotency_key, auth, "complete")


@router.get("/{project_id}/stage", response_model=dict)
async def get_stage(
    project_id: str,
    x_tenant_id: Annotated[str | None, Header(alias="X-Tenant-ID")] = None,
    auth=Depends(authenticate),
):
    """查看项目当前服务阶段与四阶段进度明细。"""
    tenant_id = auth.tenant_id  # B-2: 取认证 tenant，header 已交叉校验
    repo = _get_project_repo()
    project = await _load_project(project_id, tenant_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return {
        "project_id": project_id,
        "current_stage": project.service_stage.value,
        "current_stage_label": project.service_stage.label,
        "stage_progress": project.stage_progress,
        "stages": {k: v.to_dict() for k, v in project.stage_records.items()},
    }


class DeliverRequest(BaseModel):
    """HQ 交付请求体。

    observations/findings 留空时，自动取该项目**最近一次采集结果**。
    """
    observations: List[dict] = Field(default_factory=list)
    findings: List[dict] = Field(default_factory=list)
    scope_version: int = 1


@router.post("/{project_id}/deliver", response_model=dict)
async def deliver_project(
    project_id: str,
    body: DeliverRequest | None = None,
    x_tenant_id: Annotated[str | None, Header(alias="X-Tenant-ID")] = None,
    auth=Depends(require_write),
):
    """HQ 交付：把项目的最新测量结果转为 client-safe 报告并发布。

    架构约束（docs/01-总体架构与角色边界 §2.2「Distributor 卖；HQ 交付」、
    §7.2 双报告模型）：**仅 HQ 角色可调用**。Distributor 不得自行生成或修改
    技术报告，只能查看已交付的 client-safe 报告。

    Commercial V1 · P0-3：此前该链路只存在于服务层（execute_delivery），
    没有任何 HTTP 入口 → 「总部可以交付」在接口层面不成立。本端点补齐该入口。
    """
    if not auth.is_hq:
        raise HTTPException(status_code=403, detail="Only HQ roles may deliver")
    tenant_id = auth.tenant_id  # B-2: 取认证 tenant，header 已交叉校验
    project = await _load_project(project_id, tenant_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    svc = state.delivery_service
    if svc is None:
        raise HTTPException(status_code=503, detail="API not initialized")

    body = body or DeliverRequest()
    observations = body.observations
    findings = body.findings
    latest = None

    if not observations:
        from ..geo_view import load_measurements, _time
        saved = await load_measurements(project_id, tenant_id)
        latest = max(saved, key=lambda r: _time(r.get("collected_at")).timestamp() if _time(r.get("collected_at")) else float("-inf")) if saved else None
        if latest is None:
            raise HTTPException(
                status_code=409,
                detail="No measurement available to deliver for this project",
            )
        observations = latest.get("observations", [])
        findings = latest.get("findings", [])

    delivery = await svc.execute_delivery(
        project_id=project_id,
        tenant_id=tenant_id,
        scope_version=body.scope_version,
        observations=observations,
        findings=findings,
        executed_by=auth.user_id,
    )
    # Link only a newly created report. Replays must never relabel historical scope.
    if latest and delivery.get("status") != "ALREADY_DELIVERED":
        report = await state.report_service.get_report(delivery["report_id"], tenant_id=tenant_id)
        if report:
            report["measurement_id"] = latest.get("measurement_id")
            repo = getattr(state.report_service, "_repository", None)
            if repo is not None:
                await repo.upsert(report)
            else:
                state.report_service._reports[report["report_id"]] = report
    return delivery


@router.delete("/{project_id}", status_code=204)
async def delete_project(
    project_id: str,
    x_tenant_id: Annotated[str | None, Header(alias="X-Tenant-ID")] = None,
    auth=Depends(require_hq),
):
    tenant_id = auth.tenant_id  # B-2: 取认证 tenant，header 已交叉校验
    repo = _get_project_repo()
    existing = await _load_project(project_id, tenant_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Project not found")
    try:
        await repo.delete(project_id)
    except RepoPermissionError:
        # 与读取路径一致：租户不符统一表现为「不可见」
        raise HTTPException(status_code=404, detail="Project not found")
    return None
