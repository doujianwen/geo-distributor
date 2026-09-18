"""Clients router — CRUD for Client entities with tenant isolation."""

from __future__ import annotations
from typing import Annotated

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from .. import state

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
):
    tenant_id = _require_tenant(x_tenant_id)
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
):
    tenant_id = _require_tenant(x_tenant_id)
    repo = _get_repo()
    clients = await repo.find_by_tenant(tenant_id)
    return [ClientOut(**c.to_dict()) for c in clients]


@router.get("/{client_id}", response_model=ClientOut)
async def get_client(
    client_id: str,
    x_tenant_id: Annotated[str | None, Header(alias="X-Tenant-ID")] = None,
):
    tenant_id = _require_tenant(x_tenant_id)
    repo = _get_repo()
    client = await repo.find_by_id(client_id, tenant_id=tenant_id)
    if not client:
        raise HTTPException(status_code=404, detail=f"Client {client_id} not found")
    return ClientOut(**client.to_dict())


@router.delete("/{client_id}", status_code=204)
async def delete_client(
    client_id: str,
    x_tenant_id: Annotated[str | None, Header(alias="X-Tenant-ID")] = None,
):
    tenant_id = _require_tenant(x_tenant_id)
    repo = _get_repo()
    existing = await repo.find_by_id(client_id, tenant_id=tenant_id)
    if not existing:
        raise HTTPException(status_code=404, detail=f"Client {client_id} not found")
    await repo.delete(client_id)
    return None
