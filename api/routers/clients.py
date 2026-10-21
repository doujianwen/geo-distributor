"""Clients router — CRUD for Client entities with tenant isolation."""

from __future__ import annotations
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from .. import state
from geo_distributor.repositories.base import PermissionError as RepoPermissionError
from ..deps import authenticate, require_write
from .reports import report_to_out
from ..geo_view import geo_view, report_projection

router = APIRouter(prefix="/clients", tags=["clients"])


# ------------------------------------------------------------------
# Request / Response schemas
# ------------------------------------------------------------------

class ClientCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    industry: str = Field(default="", max_length=100)
    website: str = Field(default="", max_length=500)
    contact_email: str = Field(default="", max_length=200)


class ClientOut(BaseModel):
    client_id: str
    tenant_id: str
    name: str
    industry: str
    website: str
    contact_email: str
    is_active: bool
    created_at: str

    model_config = {"from_attributes": True}


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

async def _load_client(client_id: str, tenant_id: str):
    """按 (client_id, tenant_id) 取客户，租户不符统一视为不可见。

    B-1 修复：内存仓储 tenant 不匹配抛 PermissionError（消息含对方 tenant_id），
    SQLite 仓储返回 None；两者都归一为 None，由调用方转 404。
    """
    repo = _get_repo()
    try:
        return await repo.find_by_id(client_id, tenant_id=tenant_id)
    except RepoPermissionError:
        return None


def _require_tenant(tenant_id: str | None) -> str:
    if not tenant_id:
        raise HTTPException(status_code=400, detail="X-Tenant-ID header is required")
    return tenant_id


def _get_repo() -> state.ClientRepository:
    if state.client_repo is None:
        raise HTTPException(status_code=503, detail="API not initialized")
    return state.client_repo  # type: ignore


# ------------------------------------------------------------------
# Endpoints
# ------------------------------------------------------------------

@router.post("", response_model=ClientOut, status_code=201)
async def create_client(
    body: ClientCreate,
    x_tenant_id: Annotated[str | None, Header(alias="X-Tenant-ID")] = None,
    auth=Depends(require_write),
):
    tenant_id = auth.tenant_id  # B-2: 取认证 tenant，header 已交叉校验
    repo = _get_repo()

    import uuid
    client_id = f"CLI-{uuid.uuid4().hex[:8].upper()}"
    from geo_distributor.models.client import Client
    client = Client(
        client_id=client_id,
        tenant_id=tenant_id,
        name=body.name,
        industry=body.industry,
        website=body.website,
        contact_email=body.contact_email,
    )
    created = await repo.create(client)
    return ClientOut(**created.to_dict())


@router.get("", response_model=list[ClientOut])
async def list_clients(
    x_tenant_id: Annotated[str | None, Header(alias="X-Tenant-ID")] = None,
    auth=Depends(authenticate),
):
    tenant_id = auth.tenant_id  # B-2: 取认证 tenant，header 已交叉校验
    repo = _get_repo()
    clients = await repo.find_by_tenant(tenant_id)
    return [ClientOut(**c.to_dict()) for c in clients]


@router.get("/{client_id}", response_model=ClientOut)
async def get_client(
    client_id: str,
    x_tenant_id: Annotated[str | None, Header(alias="X-Tenant-ID")] = None,
    auth=Depends(authenticate),
):
    tenant_id = auth.tenant_id  # B-2: 取认证 tenant，header 已交叉校验
    repo = _get_repo()
    client = await _load_client(client_id, tenant_id)
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    return ClientOut(**client.to_dict())


class ClientPortalProjectOut(BaseModel):
    project_id: str
    status: str
    service_stage: str
    service_stage_label: str
    stage_progress: int
    progress_percent: int
    reports: list[dict]
    measurements: list[dict]
    next_actions: list[str]


class ClientPortalOut(BaseModel):
    client_id: str
    tenant_id: str
    projects: list[ClientPortalProjectOut]


@router.get("/{client_id}/portal", response_model=ClientPortalOut)
async def get_client_portal(
    client_id: str,
    x_client_id: Annotated[str | None, Header(alias="X-Client-ID")] = None,
    x_tenant_id: Annotated[str | None, Header(alias="X-Tenant-ID")] = None,
    auth=Depends(authenticate),
):
    """Client Portal MVP: client-scoped, read-only project/report/measurement view.

    X-Client-ID is required because the current AuthContext carries tenant/role,
    not a client identity. HQ may explicitly select a client; non-HQ callers must
    match the requested client. All project/report reads remain tenant-scoped.
    """
    tenant_id = auth.tenant_id
    if not x_client_id or x_client_id != client_id:
        raise HTTPException(status_code=403, detail="Client context mismatch")
    client = await _load_client(client_id, tenant_id)
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    if not auth.is_hq and x_client_id != client_id:
        raise HTTPException(status_code=403, detail="Client access denied")

    if state.project_repo is None:
        raise HTTPException(status_code=503, detail="API not initialized")
    projects = [p for p in await state.project_repo.find_by_tenant(tenant_id)
                if getattr(p, "client_id", None) == client_id]

    result = []
    for project in projects:
        reports = []
        # Commercial V1 · P0-2 缺陷修复：`list_reports` 属于 ReportService，
        # 不属于 DeliveryService（原写法在正常路径必然 500）。
        if state.report_service is not None:
            raw_reports = await state.report_service.list_reports(project.project_id, tenant_id=tenant_id)
            # 存储形态把 client-safe 字段嵌在 content 下，此处投影为顶层形态
            # （与 /reports 契约一致，供 portal 消费 next_steps 等）。
            reports = [
                await report_projection(r)
                for r in raw_reports
                if r.get("tenant_id") == tenant_id and r.get("is_client_safe") is True
            ]
        measurements = (await geo_view(project.project_id, tenant_id))["batches"]
        next_actions = []
        for report in reports:
            for step in report.get("next_steps", []) or []:
                if step not in next_actions:
                    next_actions.append(step)
        result.append(ClientPortalProjectOut(
            project_id=project.project_id,
            status=project.status.value if hasattr(project.status, "value") else str(project.status),
            service_stage=project.service_stage.value,
            service_stage_label=project.service_stage.label,
            stage_progress=project.stage_progress,
            progress_percent=project.progress_percent,
            reports=reports,
            measurements=measurements,
            next_actions=next_actions,
        ))
    return ClientPortalOut(client_id=client_id, tenant_id=tenant_id, projects=result)


@router.delete("/{client_id}", status_code=204)
async def delete_client(
    client_id: str,
    x_tenant_id: Annotated[str | None, Header(alias="X-Tenant-ID")] = None,
    auth=Depends(require_write),
):
    tenant_id = auth.tenant_id  # B-2: 取认证 tenant，header 已交叉校验
    repo = _get_repo()
    existing = await _load_client(client_id, tenant_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Client not found")
    await repo.delete(client_id)
    return None
