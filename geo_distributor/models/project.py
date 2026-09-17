"""Project 模型（Sprint 0 — 统一状态机）。

基于 08-统一状态机与实施序列 V0.1 定义的状态机。
一个 Service Request 对应一个 Project，Project 包含多个 Work Item。
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List
from enum import Enum, auto


class ProjectStatus(Enum):
    APPROVED = "approved"
    IN_EXECUTION = "in_execution"
    BLOCKED = "blocked"
    REWORK = "rework"
    QA = "qa"
    DELIVERED = "delivered"
    ACCEPTED = "accepted"
    CHANGES_REQUESTED = "changes_requested"
    CANCELLED = "cancelled"


# 合法状态转换表
PROJECT_TRANSITIONS = {
    ProjectStatus.APPROVED: [ProjectStatus.IN_EXECUTION, ProjectStatus.CANCELLED],
    ProjectStatus.IN_EXECUTION: [ProjectStatus.BLOCKED, ProjectStatus.QA, ProjectStatus.REWORK, ProjectStatus.CANCELLED],
    ProjectStatus.BLOCKED: [ProjectStatus.IN_EXECUTION],
    ProjectStatus.REWORK: [ProjectStatus.IN_EXECUTION],
    ProjectStatus.QA: [ProjectStatus.DELIVERED, ProjectStatus.REWORK],
    ProjectStatus.DELIVERED: [ProjectStatus.ACCEPTED, ProjectStatus.CHANGES_REQUESTED],
    ProjectStatus.CHANGES_REQUESTED: [ProjectStatus.DELIVERED, ProjectStatus.REWORK],
    ProjectStatus.ACCEPTED: [],
    ProjectStatus.CANCELLED: [],
}


@dataclass
class BlockedReason:
    """BLOCKED 状态记录（P0 必须）。"""
    reason: str
    blocked_since: str = field(default_factory=lambda: datetime.now().isoformat())
    required_action: str = ""
    owner: str = "CLIENT"  # CLIENT / DISTRIBUTOR / HQ


@dataclass
class Project:
    """Project — 商业交付容器。

    一个 Project 可包含多个 Work Item（Measurement/Diagnosis/Intervention/ReMeasurement）。
    Distributor 不直接管理 Work Item，只看到 Project 级状态和 Client-safe 结果。
    """
    project_id: str
    request_id: str
    tenant_id: str
    client_id: str
    scope_id: str
    status: ProjectStatus = ProjectStatus.APPROVED
    work_items: List[str] = field(default_factory=list)  # WI-001, WI-002...
    blocked_reason: Optional[BlockedReason] = None
    key_findings: List[str] = field(default_factory=list)
    progress_percent: int = 0
    report_ids: List[str] = field(default_factory=list)
    approved_at: Optional[str] = None
    delivered_at: Optional[str] = None
    accepted_at: Optional[str] = None
    cancelled_at: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def can_transition_to(self, new_status: ProjectStatus) -> bool:
        current = self.status
        if current == new_status:
            return True
        allowed = PROJECT_TRANSITIONS.get(current, [])
        return new_status in allowed

    def transition_to(self, new_status: ProjectStatus, reason: str = "") -> bool:
        if not self.can_transition_to(new_status):
            return False
        old = self.status
        self.status = new_status
        self.updated_at = datetime.now().isoformat()
        if new_status == ProjectStatus.IN_EXECUTION and not self.approved_at:
            self.approved_at = self.updated_at
        elif new_status == ProjectStatus.DELIVERED and not self.delivered_at:
            self.delivered_at = self.updated_at
        elif new_status == ProjectStatus.ACCEPTED and not self.accepted_at:
            self.accepted_at = self.updated_at
        elif new_status == ProjectStatus.CANCELLED and not self.cancelled_at:
            self.cancelled_at = self.updated_at
        return True

    def set_blocked(self, reason: str, action: str, owner: str = "CLIENT"):
        self.blocked_reason = BlockedReason(reason=reason, required_action=action, owner=owner)

    def clear_blocked(self):
        self.blocked_reason = None

    def to_dict(self) -> dict:
        return {
            "project_id": self.project_id,
            "request_id": self.request_id,
            "tenant_id": self.tenant_id,
            "client_id": self.client_id,
            "scope_id": self.scope_id,
            "status": self.status.value,
            "work_items": self.work_items,
            "blocked_reason": self.blocked_reason.to_dict() if self.blocked_reason else None,
            "key_findings": self.key_findings,
            "progress_percent": self.progress_percent,
            "report_ids": self.report_ids,
            "approved_at": self.approved_at,
            "delivered_at": self.delivered_at,
            "accepted_at": self.accepted_at,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
