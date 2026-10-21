"""Leads router — Website Lead Intake Queue（HQ 待分配队列）。

依据 **ADR-009-Lead-Intake-Boundary**（U2 Lead Integration Closure §2/§3）。

## 定位（关键：这不是第二套领域模型）

本路由是**来客线索的暂存队列**，是既有 `ServiceRequest` 的*上游*：

```
Website Lead ──POST /leads──> [HQ-INTAKE 待分配队列]  ──assign──> 渠道商租户
                                                            │
                                            convert ────────┴──> 既有 Client / ServiceRequest / Project
```

- 队列条目以**纯 dict** 存于既有 `SQLiteJSONRepository` 投影存储（无新 dataclass）。
- 商业语义全部由**既有实体**承载：`Client` / `ServiceRequest` / `Project`。
- **不新增**佣金 / 自动路由 / 批量分配 / 复杂 RBAC。

## 身份边界

- 未分配线索 `tenant_id = "HQ-INTAKE"`，**该租户不对应任何渠道商密钥**。
- 渠道商 `GET /leads` 只按 `auth.tenant_id` 过滤 → 结构上无法看到未分配线索。
- `assign` 为 **HQ only**；分配后条目 `tenant_id` 迁移到渠道商租户。
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime
from typing import Annotated, List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Response
from pydantic import BaseModel, Field

from .. import state
from ..deps import authenticate, require_write

router = APIRouter(prefix="/leads", tags=["leads"])

# 未分配线索的归属租户。**必须**是渠道商密钥映射不到的租户，
# 否则未分配线索会被该渠道商通过 list_by_tenant 批量看到（§3 禁止）。
LEAD_INTAKE_TENANT = "HQ-INTAKE"

SOURCE_DEFAULT = "website"

# 网站需求类型 → 既有 ServiceRequest.service 取值。
# 不发明新服务类型：全部落在既有枚举（visibility_audit / diagnosis /
# full_geo_project 等）上。
SERVICE_MAP = {
    "diagnostic": "visibility_audit",
    "competitor": "diagnosis",
    "plan": "full_geo_project",
    "retainer": "full_geo_project",
}

# 队列状态（ADR-009 §4.2，与 §3 七态一一对应）
STATUS_NEW = "new"
STATUS_PENDING = "pending_assignment"
STATUS_ASSIGNED = "assigned"
STATUS_HQ_MANAGED = "hq_managed"
STATUS_CONVERTED_CLIENT = "converted_client"
STATUS_CONVERTED_PROJECT = "converted_project"


# ------------------------------------------------------------------
# Schemas
# ------------------------------------------------------------------

class LeadIn(BaseModel):
    """官网来客线索（服务端到服务端）。"""

    source: str = Field(default=SOURCE_DEFAULT, min_length=2, max_length=32, pattern=r"^[a-z0-9_-]+$")
    source_lead_id: str = Field(default="", max_length=128, description="来源系统内 ID（wp_ggs_leads.id）")
    idempotency_key: str = Field(default="", max_length=128)
    name: str = Field(default="", max_length=100)
    company: str = Field(default="", max_length=120)
    email: str = Field(default="", max_length=190)
    domain: str = Field(default="", max_length=190)
    type: str = Field(default="", max_length=32)
    message: str = Field(default="", max_length=3000)
    created_at: str = Field(default="", max_length=64)


class LeadOut(BaseModel):
    lead_id: str
    intake_status: str
    source: str
    source_lead_id: str
    service: str
    tenant_id: str
    assigned_tenant_id: str
    client_id: str
    request_id: str
    project_id: str
    created_at: str
    updated_at: str
    deduplicated: bool = False
    contact: dict = Field(default_factory=dict)
    message: str = ""


class AssignIn(BaseModel):
    tenant_id: str = Field(..., description="目标渠道商租户；传 HQ-INTAKE 表示 HQ 直管")
    create_client: bool = False
    client_name: str = ""


class ConvertIn(BaseModel):
    service: str = ""
    target_market: List[str] = Field(default_factory=list)
    target_products: List[str] = Field(default_factory=list)
    business_question: str = ""


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _now() -> str:
    return datetime.now().isoformat()


def _queue():
    if state.lead_repo is None:
        raise HTTPException(status_code=503, detail="API not initialized")
    return state.lead_repo


def derive_lead_id(source: str, source_lead_id: str, idempotency_key: str) -> str:
    """稳定 Lead ID。

    §2 要求「稳定 Lead ID / idempotency key（重复提交或重试不得重复创建）」。
    这里把 ID **确定性地**由 (source, source_lead_id) 派生——同一来源同一 ID
    必然映射到同一个 lead_id，因此重复提交天然命中同一条记录，
    且该判定**跨进程重启仍然成立**（落在持久化表里，不依赖内存 guard）。
    """
    if source_lead_id:
        seed = f"{source}|{source_lead_id}"
    elif idempotency_key:
        seed = f"ik|{idempotency_key}"
    else:
        seed = ""
    if not seed:
        return "LEAD-" + uuid.uuid4().hex[:10].upper()
    return "LEAD-" + hashlib.sha256(seed.encode("utf-8")).hexdigest()[:10].upper()


def _to_out(row: dict, deduplicated: bool = False) -> dict:
    return {
        "lead_id": row.get("lead_id", ""),
        "intake_status": row.get("intake_status", ""),
        "source": row.get("source", ""),
        "source_lead_id": row.get("source_lead_id", ""),
        "service": row.get("service", ""),
        "tenant_id": row.get("tenant_id", ""),
        "assigned_tenant_id": row.get("assigned_tenant_id", ""),
        "client_id": row.get("client_id", ""),
        "request_id": row.get("request_id", ""),
        "project_id": row.get("project_id", ""),
        "created_at": row.get("created_at", ""),
        "updated_at": row.get("updated_at", ""),
        "deduplicated": deduplicated,
        "contact": row.get("contact", {}) or {},
        "message": row.get("message", "") or "",
    }


def _audit(row: dict, actor: str, action: str, frm: str, to: str, note: str = "") -> None:
    row.setdefault("audit", []).append(
        {"at": _now(), "actor": actor, "action": action, "from": frm, "to": to, "note": note}
    )


async def _lead_out(row: dict, deduplicated: bool = False) -> LeadOut:
    """Show the approved project via its canonical request, without rewriting lead history."""
    payload = _to_out(row, deduplicated)
    if row.get("request_id") and not row.get("project_id") and state.request_repo:
        from geo_distributor.repositories.base import PermissionError as RepoPermissionError
        try:
            request = await state.request_repo.find_by_id(row["request_id"], tenant_id=row["tenant_id"])
        except (RepoPermissionError, PermissionError):
            request = None
        if request and request.tenant_id == row["tenant_id"]:
            payload["project_id"] = request.project_id or ""
    return LeadOut(**payload)


# ------------------------------------------------------------------
# Endpoints
# ------------------------------------------------------------------

@router.post("", response_model=LeadOut)
async def intake_lead(
    body: LeadIn,
    response: Response,
    auth=Depends(require_write),
):
    """接入一条官网来客线索 → 进入 HQ 待分配队列。

    幂等：同一 (source, source_lead_id) 重复提交返回既有记录，
    `deduplicated=true`，**不新建**、**不回改**（首次创建时间与状态保持）。
    """
    # Website ingestion is a privileged server-to-server operation; distributor
    # credentials may read/assign within their scope but cannot inject anonymous leads.
    if not auth.is_hq:
        raise HTTPException(status_code=403, detail="HQ integration role required")

    source = (body.source or SOURCE_DEFAULT).strip().lower()
    source_lead_id = body.source_lead_id.strip()
    idempotency_key = body.idempotency_key.strip()
    if not source_lead_id and not idempotency_key:
        raise HTTPException(status_code=422, detail="source_lead_id or idempotency_key is required")
    if not body.name.strip() or not body.email.strip() or not body.message.strip():
        raise HTTPException(status_code=422, detail="name, email, and message are required")
    import re
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", body.email.strip()):
        raise HTTPException(status_code=422, detail="Invalid email")

    q = _queue()
    lead_id = derive_lead_id(source, source_lead_id, idempotency_key)
    service = SERVICE_MAP.get(body.type, "visibility_audit")
    now = _now()
    payload = {
        "lead_id": lead_id,
        "source": source,
        "source_lead_id": source_lead_id,
        "idempotency_key": idempotency_key,
        "created_at": body.created_at or now,
        "updated_at": now,
        "intake_status": STATUS_PENDING,
        "service_type": body.type,
        "service": service,
        "contact": {
            "name": body.name,
            "company": body.company,
            "email": body.email,
            "domain": body.domain,
        },
        "message": body.message,
        # 未分配 → 固定 HQ-INTAKE（渠道商密钥看不到）
        "tenant_id": LEAD_INTAKE_TENANT,
        # SQLiteJSONRepository 需要该列；转项目前为空
        "project_id": "",
        "assigned_tenant_id": "",
        "client_id": "",
        "request_id": "",
        "audit": [],
    }
    _audit(payload, auth.user_id, "intake", "", STATUS_PENDING, f"source={payload['source']}")
    if hasattr(q, "create_if_absent"):
        stored, created = await q.create_if_absent(payload)
    else:  # compatibility for external/custom repository adapters
        existing = await q.get(lead_id)
        if existing is not None:
            stored, created = existing, False
        else:
            await q.upsert(payload)
            stored, created = payload, True
    response.status_code = 201 if created else 200
    return await _lead_out(stored, deduplicated=not created)


@router.get("", response_model=List[LeadOut])
async def list_leads(
    status: Optional[str] = None,
    tenant_id: Optional[str] = None,
    auth=Depends(authenticate),
):
    """列出线索。

    - **HQ**：默认列出 `HQ-INTAKE` 待分配队列；可用 `tenant_id` / `status` 过滤。
    - **渠道商**：**只**列出 `auth.tenant_id` 下（即明确分配给自己）的线索。
      `tenant_id` 查询参数对渠道商**无效**——防止越权枚举（§3）。
    """
    q = _queue()

    if auth.can_cross_tenant():
        target = (tenant_id or "").strip() or LEAD_INTAKE_TENANT
        rows = await q.list_by_tenant(target)
    else:
        # 忽略查询参数中的 tenant_id：渠道商只能看自己的租户
        rows = await q.list_by_tenant(auth.tenant_id)

    if status:
        rows = [r for r in rows if r.get("intake_status") == status]
    return [await _lead_out(r) for r in rows]


@router.get("/assignable-tenants")
async def assignable_tenants(auth=Depends(authenticate)):
    """HQ-only selector data; returns tenant IDs, never API keys or user records."""
    if not auth.can_cross_tenant():
        raise HTTPException(status_code=403, detail="HQ role required")
    from ..auth import registered_tenants_by_role
    tenants = registered_tenants_by_role({"DISTRIBUTOR_ADMIN", "DISTRIBUTOR_USER"})
    return {"tenants": sorted(tenants)}


@router.get("/{lead_id}", response_model=LeadOut)
async def get_lead(lead_id: str, auth=Depends(authenticate)):
    """读取单条线索，租户作用域。越权统一 404（不泄漏存在性）。"""
    q = _queue()
    row = await q.get(lead_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Lead not found")
    if not auth.can_cross_tenant() and row.get("tenant_id") != auth.tenant_id:
        raise HTTPException(status_code=404, detail="Lead not found")
    return await _lead_out(row)


@router.post("/{lead_id}/assign", response_model=LeadOut)
async def assign_lead(
    lead_id: str,
    body: AssignIn,
    auth=Depends(require_write),
):
    """HQ 人工分配线索到渠道商租户（可选同时创建 Client）。

    §3 明确：**不虚构自动分配算法**——分配是人工决策，本端点只执行。
    """
    from ..hq_service import assign
    row = assign(lead_id, body.model_dump(), auth)
    return await _lead_out(row, bool(row.get("deduplicated")))


@router.post("/{lead_id}/convert", response_model=LeadOut)
async def convert_lead(
    lead_id: str,
    body: ConvertIn,
    auth=Depends(require_write),
):
    """HQ 把已分配的线索转换为 ServiceRequest → Project。

    复用**既有** `ProjectService.submit_request()` + `approve_scope()`，
    不新建第二套 Request/Project 逻辑（§3「禁止重复建模」）。
    转换后保留 Lead 来源关联：`source_lead_id` / `client_id` / `request_id` / `project_id`（§4-9）。
    """
    if not auth.is_hq:
        raise HTTPException(status_code=403, detail="Only HQ roles may convert leads")

    q = _queue()
    row = await q.get(lead_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Lead not found")
    if row.get("intake_status") == STATUS_CONVERTED_PROJECT and row.get("project_id"):
        return await _lead_out(row, deduplicated=True)

    if row.get("request_id"):
        return await _lead_out(row, deduplicated=True)
    target = row.get("tenant_id", "")
    if target == LEAD_INTAKE_TENANT and row.get("intake_status") != STATUS_HQ_MANAGED:
        raise HTTPException(status_code=409, detail="请先分配或确认为总部直管")
    client_id = row.get("client_id", "")
    if not client_id:
        raise HTTPException(status_code=409, detail="Lead has no Client; assign with create_client=true first")

    # A lead becomes a canonical request; approval is an explicit management action.
    from .requests import RequestIn
    from .. import request_workflow as flow
    from pydantic import ValidationError
    if row.get("request_id"):
        return await _lead_out(row, deduplicated=True)
    try:
        request_body = RequestIn(
            tenant_id=target, client_id=client_id,
            service=body.service or row.get("service", "visibility_audit"),
            market_scope="global", target_market=body.target_market,
            target_products=body.target_products,
            business_question=body.business_question or row.get("message", ""),
        )
    except ValidationError:
        raise HTTPException(422, detail="请补充有效的服务类型与业务问题")
    result = flow.create(request_body.model_dump(), auth, "lead:" + lead_id)
    row["request_id"] = result["request_id"]
    row["project_id"] = ""
    row["intake_status"] = "converted_request"
    row["updated_at"] = _now()
    _audit(row, auth.user_id, "convert_request", STATUS_CONVERTED_CLIENT, "converted_request",
           "request=" + result["request_id"])
    await q.upsert(row)
    return await _lead_out(row)
