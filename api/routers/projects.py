"""Projects router — CRUD + lifecycle for Project entities with tenant isolation."""

from __future__ import annotations
from typing import Annotated, List

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from .. import state
from geo_distributor.models import ServiceStage, DEFAULT_STAGE_SEQUENCE

router = APIRouter(prefix="/projects", tags=["projects"])


# ------------------------------------------------------------------
# Request / Response schemas
# ------------------------------------------------------------------

class ProjectCreate(BaseModel):
    """通过 Service Request 创建 Project（简化入口，跳过完整 SCOPING 流程）。"""
    tenant_id: str = Field(..., description="Tenant ID 同时用于隔离验证")
    client_id: str
    service: str = "visibility_audit"  # visibility_audit / measurement / full_geo_project
    target_market: List[str] = Field(default_factory=list)
    target_products: List[str] = Field(default_factory=list)
    business_question: str = ""


class ProjectOut(BaseModel):
    project_id: str
    tenant_id: str
    client_id: str
    request_id: str
    scope_id: str
    status: str
    # --- 四阶段工作流 ---
    service_stage: str = "site_diagnosis"
    service_stage_label: str = "网站诊断"
    stage_progress: int = 0
    progress_percent: int
    key_findings: List[str]
    report_ids: List[str]
    created_at: str
    updated_at: str

    model_config = {"from_attributes": True}


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _get_project_repo() -> state.ProjectRepository:
    if state.project_repo is None:
        raise HTTPException(status_code=503, detail="API not initialized")
    return state.project_repo  # type: ignore


# ------------------------------------------------------------------
# Endpoints
# ------------------------------------------------------------------

@router.post("", response_model=ProjectOut, status_code=201)
async def create_project(body: ProjectCreate):
    """快速创建 Project — 走 Intake → Scoping → Approve 全链路。"""
    svc = state.project_service
    if svc is None:
        raise HTTPException(status_code=503, detail="API not initialized")

    result = await svc.submit_request(
        tenant_id=body.tenant_id,
        client_id=body.client_id,
        service=body.service,
        business_context={
            "target_market": body.target_market,
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

    project = await _get_project_repo().find_by_id(project_id)
    if not project:
        raise HTTPException(status_code=500, detail="Project created but not found")
    return ProjectOut(**project.to_dict())


@router.get("", response_model=list[ProjectOut])
async def list_projects(
    x_tenant_id: Annotated[str | None, Header(alias="X-Tenant-ID")] = None,
):
    tenant_id = x_tenant_id or ""
    repo = _get_project_repo()
    projects = await repo.find_by_tenant(tenant_id)
    return [ProjectOut(**p.to_dict()) for p in projects]


@router.get("/{project_id}", response_model=ProjectOut)
async def get_project(
    project_id: str,
    x_tenant_id: Annotated[str | None, Header(alias="X-Tenant-ID")] = None,
):
    repo = _get_project_repo()
    project = await repo.find_by_id(project_id, tenant_id=x_tenant_id or None)
    if not project:
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found")
    return ProjectOut(**project.to_dict())


@router.post("/{project_id}/start", response_model=dict)
async def start_project(
    project_id: str,
    x_tenant_id: Annotated[str | None, Header(alias="X-Tenant-ID")] = None,
):
    svc = state.project_service
    if svc is None:
        raise HTTPException(status_code=503, detail="API not initialized")
    result = await svc.start_execution(project_id=project_id, user_role="hq_technical")
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("message", "Start failed"))
    return result


class StageAdvanceRequest(BaseModel):
    """推进服务阶段的请求体。"""
    target_stage: str | None = Field(
        None,
        description="目标阶段 site_diagnosis / competitor_analysis / optimization / effect_monitoring；缺省则推进到线性下一阶段",
    )
    finding_ids: list[str] = Field(default_factory=list)
    measurement_ids: list[str] = Field(default_factory=list)
    report_ids: list[str] = Field(default_factory=list)


@router.post("/{project_id}/stage", response_model=dict)
async def advance_stage(
    project_id: str,
    body: StageAdvanceRequest | None = None,
    x_tenant_id: Annotated[str | None, Header(alias="X-Tenant-ID")] = None,
):
    """推进客户服务四阶段。

    默认按 网站诊断 → 竞品分析 → 优化提升 → 效果监控 线性推进；
    也可指定 target_stage 回退（如监控发现问题后回到优化）。
    """
    repo = _get_project_repo()
    project = await repo.find_by_id(project_id, tenant_id=x_tenant_id or None)
    if not project:
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found")

    body = body or StageAdvanceRequest()
    before = project.service_stage.value

    # 先登记当前阶段产出（若有）
    if body.finding_ids or body.measurement_ids or body.report_ids:
        project.record_stage_output(
            finding_ids=body.finding_ids or None,
            measurement_ids=body.measurement_ids or None,
            report_ids=body.report_ids or None,
        )

    if body.target_stage:
        try:
            target = ServiceStage(body.target_stage)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown stage '{body.target_stage}'; "
                       f"valid: {[s.value for s in DEFAULT_STAGE_SEQUENCE]}",
            )
        if not project.can_advance_to(target):
            raise HTTPException(
                status_code=409,
                detail=f"Illegal transition {before} -> {target}",
            )
        ok = project.advance_stage(target)
    else:
        ok = project.advance_stage()
        if not ok:
            raise HTTPException(
                status_code=409,
                detail=f"Cannot advance from {before} (already final stage)",
            )

    await repo.update(project)

    return {
        "success": True,
        "project_id": project_id,
        "from_stage": before,
        "to_stage": project.service_stage.value,
        "stage_label": project.service_stage.label,
        "stage_progress": project.stage_progress,
    }


@router.post("/{project_id}/stage/complete", response_model=dict)
async def complete_stage(
    project_id: str,
    x_tenant_id: Annotated[str | None, Header(alias="X-Tenant-ID")] = None,
):
    """标记当前阶段完成。

    最终阶段（效果监控）无法再"推进"，需显式调用本端点收口，
    否则 stage_progress 会永久停在 75% 以下。
    """
    repo = _get_project_repo()
    project = await repo.find_by_id(project_id, tenant_id=x_tenant_id or None)
    if not project:
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found")

    project.complete_current_stage()
    await repo.update(project)

    return {
        "success": True,
        "project_id": project_id,
        "completed_stage": project.service_stage.value,
        "stage_label": project.service_stage.label,
        "stage_progress": project.stage_progress,
    }


@router.get("/{project_id}/stage", response_model=dict)
async def get_stage(
    project_id: str,
    x_tenant_id: Annotated[str | None, Header(alias="X-Tenant-ID")] = None,
):
    """查看项目当前服务阶段与四阶段进度明细。"""
    repo = _get_project_repo()
    project = await repo.find_by_id(project_id, tenant_id=x_tenant_id or None)
    if not project:
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found")
    return {
        "project_id": project_id,
        "current_stage": project.service_stage.value,
        "current_stage_label": project.service_stage.label,
        "stage_progress": project.stage_progress,
        "stages": {k: v.to_dict() for k, v in project.stage_records.items()},
    }


@router.delete("/{project_id}", status_code=204)
async def delete_project(
    project_id: str,
    x_tenant_id: Annotated[str | None, Header(alias="X-Tenant-ID")] = None,
):
    repo = _get_project_repo()
    existing = await repo.find_by_id(project_id, tenant_id=x_tenant_id or None)
    if not existing:
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found")
    await repo.delete(project_id)
    return None
