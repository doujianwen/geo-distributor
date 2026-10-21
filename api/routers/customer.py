"""Single-enterprise customer API; never trusts a browser customer selector."""
from typing import Annotated, Literal
from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field, field_validator, model_validator
from .. import state, customer_service as svc
from ..deps import authenticate, authenticate_customer

router = APIRouter(prefix="/customer", tags=["customer"])
management = APIRouter(tags=["customer-collaboration-management"])


class TextInput(BaseModel):
    @field_validator("*", mode="after")
    @classmethod
    def clean(cls, v):
        if isinstance(v, str):
            if not v.strip():
                raise ValueError("内容不能为空白")
            return v.strip()
        return v


class ReviewCreate(TextInput):
    project_id: str = Field(min_length=1, max_length=100)
    kind: Literal["material_request", "content_review", "report_feedback"]
    title: str = Field(min_length=1, max_length=160)
    instructions: str = Field(min_length=1, max_length=3000)
    report_id: str | None = Field(default=None, max_length=100)

    @model_validator(mode="after")
    def report_required(self):
        if self.kind == "report_feedback" and not self.report_id:
            raise ValueError("报告反馈需选择已向客户发布的报告")
        return self


class ResponseInput(TextInput):
    revision: int = Field(ge=1)
    action: Literal["submit", "confirm", "request_changes"]
    note: str = Field(min_length=1, max_length=3000)


class ProcessInput(TextInput):
    revision: int = Field(ge=1)
    action: Literal["close", "reopen", "withdraw"]
    note: str = Field(min_length=1, max_length=3000)


class PublishInput(BaseModel):
    report_id: str = Field(min_length=1, max_length=100)


class RevisionInput(BaseModel):
    revision: int = Field(ge=1)


def idempotency(key):
    if not key or not key.strip() or len(key) > 128:
        raise HTTPException(422, "请提供有效提交编号")
    return key


async def project_dto(p):
    scope = {}
    if state.request_repo is not None and p.request_id:
        from geo_distributor.repositories.base import PermissionError as RepoPermissionError
        try:
            r = await state.request_repo.find_by_id(p.request_id, tenant_id=p.tenant_id)
        except RepoPermissionError:
            r = None
        if r and r.client_id == p.client_id:
            scope = r.workflow.get("scope", {})
    stages = [{"label": s.stage.label, "status": s.status.value} for s in p.stage_records.values()]
    return {"project_id": p.project_id, "name": (scope.get("summary") or "GEO 服务项目"),
            "status": p.status.value, "stage_label": p.service_stage.label, "stages": stages,
            "updated_at": p.updated_at, "confirmed_duration": scope.get("confirmed_duration"),
            "deliverables": scope.get("deliverables") or [],
            "next_action": "请查看待办或与服务团队核对后续安排" if p.status.value == "blocked" else "查看最新发布的报告和待办；后续测量由服务团队安排"}


@router.get("/workspace")
async def workspace(auth=Depends(authenticate_customer)):
    c = await svc.bound_client(auth)
    ps = [p for p in await state.project_repo.find_by_tenant(auth.tenant_id) if p.client_id == auth.client_id]
    reviews = await svc.list_reviews(auth, customer=True)
    return {"client": {"name": c.name, "website": c.website}, "projects": [await project_dto(p) for p in ps],
            "pending_count": sum(r["status"] == "pending" for r in reviews), "is_demo": auth.tenant_id == "DEMO-GEO"}


@router.get("/projects/{project_id}")
async def project(project_id: str, auth=Depends(authenticate_customer)):
    return await project_dto(await svc.project_for(project_id, auth.tenant_id, auth.client_id))


@router.get("/projects/{project_id}/geo")
async def geo(project_id: str, auth=Depends(authenticate_customer)):
    return await svc.customer_geo(auth, project_id)


@router.get("/reports")
async def reports(project_id: str | None = None, auth=Depends(authenticate_customer)):
    return await svc.customer_reports(auth, project_id)


@router.get("/reports/{report_id}")
async def report(report_id: str, auth=Depends(authenticate_customer)):
    rows = await svc.customer_reports(auth)
    found = next((r for r in rows if r["report_id"] == report_id), None)
    if not found:
        raise HTTPException(404, "报告尚未发布或无访问权限")
    return found


@router.get("/reviews")
async def reviews(project_id: str | None = None, auth=Depends(authenticate_customer)):
    return await svc.list_reviews(auth, project_id, customer=True)


@router.post("/reviews/{review_id}/respond")
async def respond(review_id: str, body: ResponseInput, idempotency_key: Annotated[str | None, Header()] = None,
                  auth=Depends(authenticate_customer)):
    return await svc.respond_review(review_id, body.model_dump(), idempotency(idempotency_key), auth)


@management.get("/client-publications")
async def publication_list(project_id: str, auth=Depends(authenticate)):
    await svc.project_for(project_id, auth.tenant_id)
    rows = await state.customer_publication_repo.list_by_tenant(auth.tenant_id)
    return [svc.publication_dto(r, await svc.publication_valid(r)) for r in rows if r["project_id"] == project_id]


@management.post("/client-publications")
async def publication_create(body: PublishInput, auth=Depends(authenticate)):
    return await svc.publish(body.report_id, auth)


@management.post("/client-publications/{ident}/withdraw")
async def publication_withdraw(ident: str, body: RevisionInput, auth=Depends(authenticate)):
    return await svc.withdraw_publication(ident, body.revision, auth)


@management.get("/client-reviews")
async def review_list(project_id: str, auth=Depends(authenticate)):
    return await svc.list_reviews(auth, project_id)


@management.post("/client-reviews", status_code=201)
async def review_create(body: ReviewCreate, idempotency_key: Annotated[str | None, Header()] = None,
                        auth=Depends(authenticate)):
    return await svc.create_review(body.model_dump(), idempotency(idempotency_key), auth)


@management.post("/client-reviews/{ident}/process")
async def review_process(ident: str, body: ProcessInput, idempotency_key: Annotated[str | None, Header()] = None,
                         auth=Depends(authenticate)):
    return await svc.process_review(ident, body.model_dump(), idempotency(idempotency_key), auth)
