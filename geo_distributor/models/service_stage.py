"""Service Stage 模型（P1 — 客户服务四阶段工作流）。

对应客户服务工作流四个阶段：
    1. 网站诊断 (site_diagnosis)      — 客户当前 AI 可见度基线
    2. 竞品分析 (competitor_analysis) — 竞争集合内的相对位置
    3. 优化提升 (optimization)        — 针对 Finding 的干预动作
    4. 效果监控 (effect_monitoring)   — 复测与效果归因

设计原则：
- **阶段 ≠ 项目状态**。ProjectStatus 管交付流程（approved → delivered → accepted），
  ServiceStage 管业务内容阶段。两者正交。
- 阶段默认线性推进，但允许回退（监控发现问题 → 回到诊断/优化）。
- 每个阶段有独立的进度与产出记录，供 Distributor 查看客户进展。
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List, Dict
from enum import Enum


class ServiceStage(Enum):
    """客户服务四阶段。"""

    SITE_DIAGNOSIS = "site_diagnosis"            # 网站诊断
    COMPETITOR_ANALYSIS = "competitor_analysis"  # 竞品分析
    OPTIMIZATION = "optimization"                # 优化提升
    EFFECT_MONITORING = "effect_monitoring"      # 效果监控

    @property
    def label(self) -> str:
        """中文名，用于 Distributor 界面展示。"""
        return _STAGE_LABELS[self]

    @property
    def order(self) -> int:
        """阶段序号（1-4）。"""
        return _STAGE_ORDER[self]


_STAGE_LABELS: Dict[ServiceStage, str] = {
    ServiceStage.SITE_DIAGNOSIS: "网站诊断",
    ServiceStage.COMPETITOR_ANALYSIS: "竞品分析",
    ServiceStage.OPTIMIZATION: "优化提升",
    ServiceStage.EFFECT_MONITORING: "效果监控",
}

_STAGE_ORDER: Dict[ServiceStage, int] = {
    ServiceStage.SITE_DIAGNOSIS: 1,
    ServiceStage.COMPETITOR_ANALYSIS: 2,
    ServiceStage.OPTIMIZATION: 3,
    ServiceStage.EFFECT_MONITORING: 4,
}


# 合法阶段流转表
# 默认线性推进；允许回退到任意更早阶段（监控发现问题后重新诊断/优化）
STAGE_TRANSITIONS = {
    ServiceStage.SITE_DIAGNOSIS: [
        ServiceStage.COMPETITOR_ANALYSIS,
        ServiceStage.OPTIMIZATION,      # 跳过竞品分析直接优化
    ],
    ServiceStage.COMPETITOR_ANALYSIS: [
        ServiceStage.OPTIMIZATION,
        ServiceStage.SITE_DIAGNOSIS,    # 回退
    ],
    ServiceStage.OPTIMIZATION: [
        ServiceStage.EFFECT_MONITORING,
        ServiceStage.SITE_DIAGNOSIS,     # 回退：优化前需重新诊断
        ServiceStage.COMPETITOR_ANALYSIS,  # 回退
    ],
    ServiceStage.EFFECT_MONITORING: [
        ServiceStage.SITE_DIAGNOSIS,     # 回退：效果不达标，重新诊断
        ServiceStage.OPTIMIZATION,       # 回退：继续优化
    ],
}


class StageStatus(Enum):
    """单个阶段的执行状态。"""
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    BLOCKED = "blocked"


@dataclass
class StageRecord:
    """单个阶段的执行记录。

    记录该阶段从进入到完成的完整轨迹，供 Distributor 汇报客户进展。
    """
    stage: ServiceStage
    status: StageStatus = StageStatus.NOT_STARTED
    progress_percent: int = 0
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    finding_ids: List[str] = field(default_factory=list)      # 本阶段产出的 Finding
    measurement_ids: List[str] = field(default_factory=list)  # 本阶段的测量批次
    report_ids: List[str] = field(default_factory=list)       # 本阶段产出的报告
    notes: str = ""

    def start(self) -> None:
        self.status = StageStatus.IN_PROGRESS
        self.started_at = self.started_at or datetime.now().isoformat()

    def complete(self, progress: int = 100) -> None:
        self.status = StageStatus.COMPLETED
        self.progress_percent = progress
        self.completed_at = datetime.now().isoformat()
        if not self.started_at:
            self.started_at = self.completed_at

    def block(self, note: str = "") -> None:
        self.status = StageStatus.BLOCKED
        if note:
            self.notes = note

    def to_dict(self) -> dict:
        return {
            "stage": self.stage.value,
            "stage_label": self.stage.label,
            "stage_order": self.stage.order,
            "status": self.status.value,
            "progress_percent": self.progress_percent,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "finding_ids": self.finding_ids,
            "measurement_ids": self.measurement_ids,
            "report_ids": self.report_ids,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "StageRecord":
        """从 to_dict() 输出还原（持久化层用）。"""
        return cls(
            stage=ServiceStage(data["stage"]),
            status=StageStatus(data.get("status", StageStatus.NOT_STARTED.value)),
            progress_percent=data.get("progress_percent", 0),
            started_at=data.get("started_at"),
            completed_at=data.get("completed_at"),
            finding_ids=list(data.get("finding_ids", [])),
            measurement_ids=list(data.get("measurement_ids", [])),
            report_ids=list(data.get("report_ids", [])),
            notes=data.get("notes", ""),
        )


# 四阶段默认工作流（按顺序）
DEFAULT_STAGE_SEQUENCE: List[ServiceStage] = [
    ServiceStage.SITE_DIAGNOSIS,
    ServiceStage.COMPETITOR_ANALYSIS,
    ServiceStage.OPTIMIZATION,
    ServiceStage.EFFECT_MONITORING,
]


def init_stage_records() -> Dict[str, StageRecord]:
    """初始化四个阶段的空记录（key 为 stage value）。"""
    return {s.value: StageRecord(stage=s) for s in DEFAULT_STAGE_SEQUENCE}


def can_transition_stage(current: ServiceStage, target: ServiceStage) -> bool:
    """检查阶段流转是否合法。"""
    if current == target:
        return True
    return target in STAGE_TRANSITIONS.get(current, [])


def next_stage(current: ServiceStage) -> Optional[ServiceStage]:
    """返回线性序列中的下一阶段；已是最后阶段则返回 None。"""
    idx = _STAGE_ORDER[current]
    if idx >= len(DEFAULT_STAGE_SEQUENCE):
        return None
    return DEFAULT_STAGE_SEQUENCE[idx]
