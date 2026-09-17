"""Audit Trail 模型（Sprint 0 — P0 必须）。

记录所有关键操作：actor, role, action, object_type, object_id, before, after, timestamp。
满足 ADR-033: Audit Trail 要求。
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Dict, Any
from enum import Enum


class AuditAction(Enum):
    """审计动作类型。"""
    # Request
    REQUEST_CREATED = "request.created"
    REQUEST_SUBMITTED = "request.submitted"
    REQUEST_CLARIFIED = "request.clarified"
    REQUEST_REJECTED = "request.rejected"
    # Scope
    SCOPE_CREATED = "scope.created"
    SCOPE_APPROVED = "scope.approved"
    SCOPE_CHANGED = "scope.changed"
    # Project
    PROJECT_CREATED = "project.created"
    PROJECT_STARTED = "project.started"
    PROJECT_BLOCKED = "project.blocked"
    PROJECT_COMPLETED = "project.completed"
    # WorkItem
    WORKITEM_CREATED = "workitem.created"
    WORKITEM_STARTED = "workitem.started"
    WORKITEM_COMPLETED = "workitem.completed"
    WORKITEM_FAILED = "workitem.failed"
    # Measurement
    MEASUREMENT_STARTED = "measurement.started"
    MEASUREMENT_COMPLETED = "measurement.completed"
    MEASUREMENT_FAILED = "measurement.failed"
    # QA/Delivery
    QA_STARTED = "qa.started"
    QA_PASSED = "qa.passed"
    QA_FAILED = "qa.failed"
    REPORT_CREATED = "report.created"
    REPORT_PUBLISHED = "report.published"
    REPORT_REVISION = "report.revision"


@dataclass
class AuditEvent:
    """审计事件（P0 必须，满足 ADR-033）。"""
    event_id: str
    actor_id: str
    actor_role: str
    action: str  # AuditAction
    object_type: str  # request, project, scope, work_item, report
    object_id: str
    previous_state: Optional[Dict[str, Any]] = None
    new_state: Optional[Dict[str, Any]] = None
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    correlation_id: Optional[str] = None  # 关联到 Request ID
    metadata: Optional[Dict[str, Any]] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "event_id": self.event_id,
            "actor_id": self.actor_id,
            "actor_role": self.actor_role,
            "action": self.action,
            "object_type": self.object_type,
            "object_id": self.object_id,
            "previous_state": self.previous_state,
            "new_state": self.new_state,
            "timestamp": self.timestamp,
            "correlation_id": self.correlation_id,
            "metadata": self.metadata,
        }

    @classmethod
    def for_request(cls, actor_id: str, actor_role: str, action: AuditAction,
                   request_id: str, previous_state: Optional[dict] = None,
                   new_state: Optional[dict] = None, correlation_id: Optional[str] = None) -> 'AuditEvent':
        """创建请求相关的审计事件。"""
        return cls(
            event_id=f"AUD-{datetime.now().strftime('%Y%m%d%H%M%S%f')}",
            actor_id=actor_id,
            actor_role=actor_role,
            action=action.value,
            object_type="request",
            object_id=request_id,
            previous_state=previous_state,
            new_state=new_state,
            correlation_id=correlation_id,
        )

    @classmethod
    def for_project(cls, actor_id: str, actor_role: str, action: AuditAction,
                   project_id: str, previous_state: Optional[dict] = None,
                   new_state: Optional[dict] = None, correlation_id: Optional[str] = None) -> 'AuditEvent':
        """创建项目相关的审计事件。"""
        return cls(
            event_id=f"AUD-{datetime.now().strftime('%Y%m%d%H%M%S%f')}",
            actor_id=actor_id,
            actor_role=actor_role,
            action=action.value,
            object_type="project",
            object_id=project_id,
            previous_state=previous_state,
            new_state=new_state,
            correlation_id=correlation_id,
        )
