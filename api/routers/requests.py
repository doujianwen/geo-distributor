"""Tenant-safe service intake and explicit HQ approval API."""
from __future__ import annotations
from typing import Annotated, Literal
from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field, field_validator, model_validator
from ..deps import authenticate, require_write
from .. import state, request_workflow as flow

router = APIRouter(prefix="/requests", tags=["requests"])
SERVICES = ("diagnosis", "competitor_analysis", "intervention", "measurement", "full_geo_project", "visibility_audit", "remeasurement")

class RequestIn(BaseModel):
    tenant_id: str = ""
    client_id: str = Field(min_length=1, max_length=100)
    service: str
    business_question: str = Field(min_length=1, max_length=3000)
    market_scope: Literal["single", "multi", "global"] = "global"
    target_market: list[str] = Field(default_factory=list, max_length=250)
    target_languages: list[str] = Field(default_factory=list, max_length=40)
    service_duration: Literal["one_time", "1_month", "3_months", "6_months", "12_months", "to_be_determined"] = "to_be_determined"
    target_products: list[str] = Field(default_factory=list, max_length=100)

    @field_validator("client_id", "business_question")
    @classmethod
    def nonblank(cls, v):
        if not v.strip():
            raise ValueError("必填项不能为空")
        return v.strip()

    @field_validator("service")
    @classmethod
    def service_known(cls, v):
        if v not in SERVICES:
            raise ValueError("请选择有效服务类型")
        return v

    @field_validator("target_market")
    @classmethod
    def countries(cls, v):
        result = list(dict.fromkeys(s.strip().upper() for s in v if s.strip()))
        if any(len(s) != 2 or not s.isascii() or not s.isalpha() for s in result):
            raise ValueError("国家/地区请使用两位字母代码")
        return result

    @field_validator("target_languages", "target_products")
    @classmethod
    def strings(cls, v):
        if any(len(s) > 200 for s in v):
            raise ValueError("选项内容过长")
        return list(dict.fromkeys(s.strip() for s in v if s.strip()))

    @model_validator(mode="after")
    def market_count(self):
        if self.market_scope == "single" and len(self.target_market) != 1:
            raise ValueError("单一市场请准确选择一个国家/地区")
        if self.market_scope == "multi" and len(self.target_market) < 2:
            raise ValueError("多个市场请至少选择两个国家/地区")
        return self

class ScopeIn(BaseModel):
    summary: str = Field(min_length=1, max_length=3000)
    confirmed_duration: str = Field(min_length=1, max_length=200)
    deliverables: list[str] = Field(min_length=1, max_length=30)
    exclusions: list[str] = Field(default_factory=list, max_length=30)

    @field_validator("summary", "confirmed_duration")
    @classmethod
    def text(cls, v):
        if not v.strip(): raise ValueError("不能为空")
        return v.strip()

    @field_validator("deliverables", "exclusions")
    @classmethod
    def lines(cls, v):
        if any(not s.strip() or len(s) > 500 for s in v): raise ValueError("请填写有效交付物/排除项")
        return [s.strip() for s in v]

class ActionIn(BaseModel):
    revision: int = Field(ge=0)
    note: str = Field(default="", max_length=3000)
    scope: ScopeIn | None = None

@router.post("", status_code=201)
async def create_request(body: RequestIn, idempotency_key: Annotated[str | None, Header()] = None,
                         auth=Depends(require_write)):
    if auth.role not in ("DISTRIBUTOR_ADMIN", "HQ_TECHNICAL", "HQ_MANAGEMENT"):
        raise HTTPException(403, "当前角色不能提交需求")
    return flow.create(body.model_dump(), auth, idempotency_key)

@router.get("")
async def list_requests(tenant_id: str | None = None, auth=Depends(authenticate)):
    if state.request_repo is None: raise HTTPException(503, "服务暂不可用")
    if tenant_id and tenant_id != auth.tenant_id and not auth.is_hq:
        raise HTTPException(403, "无权查看此队列")
    if auth.is_hq and not tenant_id:
        if state.persistence_backend == "sqlite":
            conn = state.request_repo._connect()
            try:
                import json
                return [json.loads(r[0]) for r in conn.execute("SELECT payload FROM requests ORDER BY updated_at DESC")]
            finally: conn.close()
        return [r.to_dict() for r in state.request_repo._store.values()]
    rows = await state.request_repo.find_by_tenant(tenant_id or auth.tenant_id)
    return [r.to_dict() for r in rows]

@router.get("/{request_id}")
async def get_request(request_id: str, tenant_id: str | None = None, auth=Depends(authenticate)):
    with flow.transaction() as tx:
        item = flow.visible(tx.get("requests", request_id), auth)
        if tenant_id and item["tenant_id"] != tenant_id:
            raise HTTPException(404, "需求不存在或不属于当前范围")
        return item

@router.post("/{request_id}/{action}")
async def update_request(request_id: str, action: Literal["clarification", "supplement", "scope", "approve", "reject"],
                         body: ActionIn, tenant_id: str | None = None, auth=Depends(require_write)):
    if action in ("approve", "reject"):
        if not auth.is_hq or auth.role != "HQ_MANAGEMENT":
            raise HTTPException(403, "仅总部管理角色可批准或拒绝需求")
    elif action in ("clarification", "scope"):
        if not auth.is_hq: raise HTTPException(403, "仅总部可受理需求")
    elif auth.role != "DISTRIBUTOR_ADMIN":
        item = await get_request(request_id, tenant_id, auth)
        if not auth.is_hq or item["tenant_id"] != "HQ-INTAKE":
            raise HTTPException(403, "仅所属渠道商管理员可补充需求；总部只能补充直管需求")
    if action in ("clarification", "supplement", "reject") and not body.note.strip():
        raise HTTPException(422, "请填写说明")
    if action == "scope" and body.scope is None:
        raise HTTPException(422, "请填写确认范围")
    if tenant_id:
        await get_request(request_id, tenant_id, auth)
    return flow.change(request_id, auth, action, body.model_dump())
