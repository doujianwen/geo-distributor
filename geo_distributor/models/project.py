"""Project 模型（Sprint 0 — 统一状态机）。

基于 08-统一状态机与实施序列 V0.1 定义的状态机。
一个 Service Request 对应一个 Project，Project 包含多个 Work Item。
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List, Dict
from enum import Enum, auto

from .service_stage import (
    ServiceStage,
    StageRecord,
    StageStatus,
    DEFAULT_STAGE_SEQUENCE,
    init_stage_records,
    can_transition_stage,
    next_stage,
)


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

    def to_dict(self) -> dict:
        """序列化。

        ⚠️ 修复记录：Project.to_dict() 一直调用本方法，但本方法此前不存在——
        任何被 set_blocked() 过的 Project 序列化都会抛 AttributeError
        （API 层表现为 GET /projects/{id} 返回 500）。
        """
        return {
            "reason": self.reason,
            "blocked_since": self.blocked_since,
            "required_action": self.required_action,
            "owner": self.owner,
        }


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
    # --- 客户服务四阶段（P1 新增，与 ProjectStatus 正交）---
    service_stage: ServiceStage = ServiceStage.SITE_DIAGNOSIS
    stage_records: Dict[str, StageRecord] = field(default_factory=init_stage_records)
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

    # ------------------------------------------------------------------
    # 四阶段工作流（Service Stage）
    # ------------------------------------------------------------------

    def get_stage_record(self, stage: Optional[ServiceStage] = None) -> StageRecord:
        """获取指定阶段的记录（默认当前阶段）。缺失时自动补建。"""
        stage = stage or self.service_stage
        key = stage.value
        if key not in self.stage_records:
            self.stage_records[key] = StageRecord(stage=stage)
        return self.stage_records[key]

    def start_stage(self, stage: Optional[ServiceStage] = None) -> bool:
        """开始指定阶段（默认当前阶段）。不校验流转，用于首次进入。"""
        rec = self.get_stage_record(stage)
        rec.start()
        self.updated_at = datetime.now().isoformat()
        return True

    def can_advance_to(self, target: ServiceStage) -> bool:
        """检查能否流转到目标阶段。"""
        return can_transition_stage(self.service_stage, target)

    def advance_stage(self, target: Optional[ServiceStage] = None) -> bool:
        """推进到下一阶段（默认线性下一阶段）。

        会先把当前阶段标记完成（若仍在进行中），再切换到目标阶段并置为进行中。
        返回 False 表示流转非法。
        """
        if target is None:
            target = next_stage(self.service_stage)
            if target is None:
                return False  # 已是最后阶段
        if not can_transition_stage(self.service_stage, target):
            return False

        # 完成当前阶段
        # NOT_STARTED 也要收口：项目创建后未必显式调用 start_stage()，
        # 若只处理 IN_PROGRESS 会导致首阶段永久未完成、整体进度卡在 75%。
        # BLOCKED 不自动完成——阻塞中的阶段需要先解除阻塞。
        current_rec = self.get_stage_record()
        if current_rec.status in (StageStatus.NOT_STARTED, StageStatus.IN_PROGRESS):
            current_rec.complete()

        # 切换并启动目标阶段
        self.service_stage = target
        self.updated_at = datetime.now().isoformat()
        self.get_stage_record(target).start()
        return True

    def complete_current_stage(self) -> None:
        """标记当前阶段完成。"""
        self.get_stage_record().complete()
        self.updated_at = datetime.now().isoformat()

    def record_stage_output(
        self,
        stage: Optional[ServiceStage] = None,
        finding_ids: Optional[List[str]] = None,
        measurement_ids: Optional[List[str]] = None,
        report_ids: Optional[List[str]] = None,
    ) -> None:
        """登记某阶段的产出（Finding / Measurement / Report）。"""
        rec = self.get_stage_record(stage)
        if finding_ids:
            rec.finding_ids.extend(i for i in finding_ids if i not in rec.finding_ids)
        if measurement_ids:
            rec.measurement_ids.extend(i for i in measurement_ids if i not in rec.measurement_ids)
        if report_ids:
            rec.report_ids.extend(i for i in report_ids if i not in rec.report_ids)

    @classmethod
    def from_dict(cls, data: dict) -> "Project":
        """从 to_dict() 输出还原（持久化层用）。

        注意：stage_progress / service_stage_label 是 to_dict 派生的只读字段，
        还原时忽略——它们由 service_stage + stage_records 重新计算。
        """
        blocked = data.get("blocked_reason")
        stage_records = {
            k: StageRecord.from_dict(v) for k, v in (data.get("stage_records") or {}).items()
        }
        return cls(
            project_id=data["project_id"],
            request_id=data.get("request_id", ""),
            tenant_id=data.get("tenant_id", ""),
            client_id=data.get("client_id", ""),
            scope_id=data.get("scope_id", ""),
            status=ProjectStatus(data.get("status", ProjectStatus.APPROVED.value)),
            service_stage=ServiceStage(data.get("service_stage", ServiceStage.SITE_DIAGNOSIS.value)),
            stage_records=stage_records or init_stage_records(),
            work_items=list(data.get("work_items", [])),
            blocked_reason=BlockedReason(**blocked) if blocked else None,
            key_findings=list(data.get("key_findings", [])),
            progress_percent=data.get("progress_percent", 0),
            report_ids=list(data.get("report_ids", [])),
            approved_at=data.get("approved_at"),
            delivered_at=data.get("delivered_at"),
            accepted_at=data.get("accepted_at"),
            cancelled_at=data.get("cancelled_at"),
            created_at=data.get("created_at") or datetime.now().isoformat(),
            updated_at=data.get("updated_at") or datetime.now().isoformat(),
        )

    @property
    def stage_label(self) -> str:
        return self.service_stage.label

    @property
    def stage_progress(self) -> int:
        """四阶段整体进度（0-100）：已完成阶段数 / 4 * 100，含当前阶段内进度。"""
        total = len(DEFAULT_STAGE_SEQUENCE)
        done = 0.0
        for s in DEFAULT_STAGE_SEQUENCE:
            rec = self.stage_records.get(s.value)
            if rec is None:
                continue
            if rec.status == StageStatus.COMPLETED:
                done += 1.0
            elif rec.status == StageStatus.IN_PROGRESS:
                done += rec.progress_percent / 100.0
        return int(done / total * 100) if total else 0

    def to_dict(self) -> dict:
        return {
            "project_id": self.project_id,
            "request_id": self.request_id,
            "tenant_id": self.tenant_id,
            "client_id": self.client_id,
            "scope_id": self.scope_id,
            "status": self.status.value,
            # --- 四阶段工作流 ---
            "service_stage": self.service_stage.value,
            "service_stage_label": self.service_stage.label,
            "stage_progress": self.stage_progress,
            "stage_records": {
                k: v.to_dict() for k, v in self.stage_records.items()
            },
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
