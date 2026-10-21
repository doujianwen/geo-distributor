"""Role guarded HQ workspace boundary."""
from typing import Annotated, Literal
from fastapi import APIRouter, Depends, Header
from pydantic import BaseModel, Field
from ..deps import require_hq
from .. import hq_service as svc

router = APIRouter(prefix="/hq", tags=["hq"])


class ProjectOperation(BaseModel):
    model_config = {"extra": "forbid"}
    action: Literal["start", "advance", "complete", "block", "resume"]
    expected_updated_at: str = Field(min_length=1, max_length=100)
    note: str = Field(default="", max_length=3000)
    required_action: str = Field(default="", max_length=1000)
    owner: Literal["HQ", "CLIENT", "DISTRIBUTOR"] = "HQ"


@router.get("/workspace")
async def workspace(tenant_id: str | None = None, auth=Depends(require_hq)):
    return await svc.workspace(auth, tenant_id)


@router.post("/projects/{project_id}/operation")
async def operation(project_id: str, body: ProjectOperation,
                    idempotency_key: Annotated[str | None, Header()] = None, auth=Depends(require_hq)):
    return svc.project_operation(project_id, body.model_dump(), idempotency_key, auth)
