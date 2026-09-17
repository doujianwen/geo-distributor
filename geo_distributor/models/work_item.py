"""Work Item 模型（Sprint 0）。

Work Item 是 HQ 内部最小技术执行单位。
Distributor 不直接管理 Work Item 技术状态。
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List
from enum import Enum, auto


class WorkItemType(Enum):
    MEASUREMENT = "measurement"
    DIAGNOSIS = "diagnosis"
    INTERVENTION = "intervention"
    REMEASUREMENT = "remeasurement"
    REPORT = "report"
    QA = "qa"


class WorkItemStatus(Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"


WORK_ITEM_TRANSITIONS = {
    WorkItemStatus.PENDING: [WorkItemStatus.IN_PROGRESS, WorkItemStatus.BLOCKED],
    WorkItemStatus.IN_PROGRESS: [WorkItemStatus.COMPLETED, WorkItemStatus.FAILED, WorkItemStatus.BLOCKED],
    WorkItemStatus.BLOCKED: [WorkItemStatus.IN_PROGRESS],
    WorkItemStatus.FAILED: [WorkItemStatus.IN_PROGRESS],  # retry
    WorkItemStatus.COMPLETED: [],
}


@dataclass
class WorkItem:
    """Work Item — HQ 内部技术执行单位。"""
    work_item_id: str
    project_id: str
    tenant_id: str
    type: WorkItemType
    status: WorkItemStatus = WorkItemStatus.PENDING
    scope_ref: str = ""
    depends_on: List[str] = field(default_factory=list)
    error_message: Optional[str] = None
    completed_at: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def can_transition_to(self, new_status: WorkItemStatus) -> bool:
        current = self.status
        if current == new_status:
            return True
        allowed = WORK_ITEM_TRANSITIONS.get(current, [])
        return new_status in allowed

    def transition_to(self, new_status: WorkItemStatus, error: str = "") -> bool:
        if not self.can_transition_to(new_status):
            return False
        self.status = new_status
        self.updated_at = datetime.now().isoformat()
        if error:
            self.error_message = error
        if new_status == WorkItemStatus.COMPLETED:
            self.completed_at = self.updated_at
        return True

    def to_dict(self) -> dict:
        return {
            "work_item_id": self.work_item_id,
            "project_id": self.project_id,
            "tenant_id": self.tenant_id,
            "type": self.type.value,
            "status": self.status.value,
            "scope_ref": self.scope_ref,
            "depends_on": self.depends_on,
            "error_message": self.error_message,
            "completed_at": self.completed_at,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
