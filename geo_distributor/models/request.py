"""Service Request 模型（Sprint 0 — 统一状态机）。

基于 08-统一状态机与实施序列 V0.1 定义的状态机。
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List
from enum import Enum, auto


class RequestStatus(Enum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    INTAKE_REVIEW = "intake_review"
    CLARIFICATION_REQUIRED = "clarification_required"
    SCOPING = "scoping"
    SCOPE_PENDING_APPROVAL = "scope_pending_approval"
    APPROVED = "approved"
    DELIVERED = "delivered"
    ACCEPTED = "accepted"
    CANCELLED = "cancelled"
    REJECTED = "rejected"
    CHANGES_REQUESTED = "changes_requested"


# 合法状态转换表（State Transition Guard 使用）
REQUEST_TRANSITIONS = {
    RequestStatus.DRAFT: [RequestStatus.SUBMITTED],
    RequestStatus.SUBMITTED: [RequestStatus.INTAKE_REVIEW, RequestStatus.REJECTED],
    RequestStatus.INTAKE_REVIEW: [
        RequestStatus.CLARIFICATION_REQUIRED,
        RequestStatus.SCOPING,
        RequestStatus.REJECTED,
    ],
    RequestStatus.CLARIFICATION_REQUIRED: [RequestStatus.INTAKE_REVIEW],
    RequestStatus.SCOPING: [RequestStatus.SCOPE_PENDING_APPROVAL],
    RequestStatus.SCOPE_PENDING_APPROVAL: [RequestStatus.APPROVED, RequestStatus.REJECTED],
    RequestStatus.APPROVED: [],  # 触发 Project 创建后进入 IN_EXECUTION
    RequestStatus.DELIVERED: [RequestStatus.ACCEPTED, RequestStatus.CHANGES_REQUESTED],
    RequestStatus.CHANGES_REQUESTED: [RequestStatus.DELIVERED],
    RequestStatus.ACCEPTED: [],
    RequestStatus.CANCELLED: [],
    RequestStatus.REJECTED: [],
}


@dataclass
class BusinessContext:
    """商业背景信息（Distributor 提供）。"""
    target_market: List[str] = field(default_factory=list)
    target_products: List[str] = field(default_factory=list)
    target_customer: str = ""
    known_competitors: List[str] = field(default_factory=list)
    business_question: str = ""
    attachments: List[str] = field(default_factory=list)  # 文件引用


@dataclass
class ClarificationRequest:
    """结构化澄清请求（禁止无限聊天式补充）。"""
    request_id: str
    missing_fields: List[str] = field(default_factory=list)
    questions: List[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    resolved_at: Optional[str] = None


@dataclass
class ServiceRequest:
    """Service Request — 商业需求入口。

    一个 Service Request 对应一个 Project。
    Distributor 提交业务需求，不需要理解 GEO 技术细节。
    """
    request_id: str
    tenant_id: str
    client_id: str
    status: RequestStatus = RequestStatus.DRAFT
    service: str = "visibility_audit"  # visibility_audit / measurement / diagnosis / intervention / remeasurement / full_geo_project
    requested_engines: List[str] = field(default_factory=list)  # ChatGPT / Google / Perplexity / Gemini
    business_context: Optional[BusinessContext] = field(default=None)
    clarification_request: Optional[ClarificationRequest] = None
    scope_id: Optional[str] = None
    project_id: Optional[str] = None
    submitted_at: Optional[str] = None
    approved_at: Optional[str] = None
    delivered_at: Optional[str] = None
    accepted_at: Optional[str] = None
    cancelled_at: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    idempotency_key: Optional[str] = None  # 防止重复提交

    def can_transition_to(self, new_status: RequestStatus) -> bool:
        """检查状态转换是否合法（State Transition Guard）。"""
        current = self.status
        if current == new_status:
            return True
        allowed = REQUEST_TRANSITIONS.get(current, [])
        return new_status in allowed

    def transition_to(self, new_status: RequestStatus) -> bool:
        """执行状态转换，返回是否成功。"""
        if not self.can_transition_to(new_status):
            return False
        old_status = self.status
        self.status = new_status
        self.updated_at = datetime.now().isoformat()
        # 自动更新时间戳
        if new_status == RequestStatus.SUBMITTED and not self.submitted_at:
            self.submitted_at = self.updated_at
        elif new_status == RequestStatus.APPROVED and not self.approved_at:
            self.approved_at = self.updated_at
        elif new_status == RequestStatus.DELIVERED and not self.delivered_at:
            self.delivered_at = self.updated_at
        elif new_status == RequestStatus.ACCEPTED and not self.accepted_at:
            self.accepted_at = self.updated_at
        elif new_status == RequestStatus.CANCELLED and not self.cancelled_at:
            self.cancelled_at = self.updated_at
        return True

    def to_dict(self) -> dict:
        return {
            "request_id": self.request_id,
            "tenant_id": self.tenant_id,
            "client_id": self.client_id,
            "status": self.status.value,
            "service": self.service,
            "requested_engines": self.requested_engines,
            "business_context": self.business_context.to_dict() if self.business_context else None,
            "clarification_request": self.clarification_request.to_dict() if self.clarification_request else None,
            "scope_id": self.scope_id,
            "project_id": self.project_id,
            "submitted_at": self.submitted_at,
            "approved_at": self.approved_at,
            "delivered_at": self.delivered_at,
            "accepted_at": self.accepted_at,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
