"""Sprint 4B — Intervention Loop（规格 §6 / SPRINT-4-ROADMAP 4B）。

目标：证明「建议 → 执行 → Re-measurement → Delta」链条。

约束（CEO 冻结清单）：
- 禁止 CRM 集成、Billing、自动化干预
- 客户执行是外部输入（InterventionExecution 由人工/客户回填）

核心数据流：
    Baseline Measurement (v1)
        ↓
    Diagnosis → Findings
        ↓
    InterventionRecommendation (Finding → Intervention 一一映射)
        ↓
    [客户执行] InterventionExecution
        ↓
    Re-measurement (v2)
        ↓
    Delta = v2 - v1
        ↓
    Evidence: 「建议 X 导致 Y 改善」
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional


# 干预类型（规格 §C2）
INTERVENTION_TYPES = [
    "content",   # 新增页面
    "faq",       # 新增 FAQ
    "comparison",# 新增对比页
    "entity",    # 补充实体信息
    "trust",     # 补充案例与可信信号
    "ia",        # 优化信息架构
]


@dataclass
class InterventionRecommendation:
    """干预建议项：必须可追溯到某个 Finding（规格 §C1）。"""

    intervention_id: str
    finding_id: str
    case_id: str
    itype: str            # 见 INTERVENTION_TYPES
    title: str
    description: str
    target: str           # 目标页面 / URL / 栏目
    impact: int = 3       # 1-5，预期影响
    effort: int = 3       # 1-5，1=低
    confidence: float = 0.6  # 0-1，证据置信度
    priority: int = 0
    status: str = "proposed"  # proposed / approved / executed / skipped

    def priority_score(self) -> float:
        """Impact × Confidence / Effort（Effort 越低越优先）。"""
        effort = self.effort if self.effort > 0 else 1
        return round(self.impact * self.confidence / effort, 3)

    def to_dict(self) -> dict:
        return {
            "intervention_id": self.intervention_id,
            "finding_id": self.finding_id,
            "case_id": self.case_id,
            "type": self.itype,
            "title": self.title,
            "description": self.description,
            "target": self.target,
            "impact": self.impact,
            "effort": self.effort,
            "confidence": self.confidence,
            "priority_score": self.priority_score(),
            "priority": self.priority,
            "status": self.status,
        }


@dataclass
class InterventionExecution:
    """客户执行记录（外部输入回填，规格 §D）。"""

    execution_id: str
    intervention_id: str
    case_id: str
    status: str = "planned"  # planned / executed / skipped
    executed_at: str = ""
    changes: str = ""        # 修改内容
    page: str = ""           # 修改页面
    note: str = ""

    def to_dict(self) -> dict:
        return {
            "execution_id": self.execution_id,
            "intervention_id": self.intervention_id,
            "case_id": self.case_id,
            "status": self.status,
            "executed_at": self.executed_at,
            "changes": self.changes,
            "page": self.page,
            "note": self.note,
        }


@dataclass
class BaselineMetrics:
    """基线 / 重测的聚合指标（用于 Delta 计算）。"""

    case_id: str
    version: str                      # "baseline" / "remeasurement"
    query_count: int = 0
    mention_rate: float = 0.0         # 被提及 query 占比 %
    citation_rate: float = 0.0        # 被引用（cites>0）query 占比 %
    recommendation_rate: float = 0.0  # recommendation_level>=2 占比 %
    query_coverage: float = 0.0       # 有观测覆盖的 query 占比 %
    avg_recommendation_level: float = 0.0
    competitor_count: int = 0
    captured_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> dict:
        return {
            "case_id": self.case_id,
            "version": self.version,
            "query_count": self.query_count,
            "mention_rate": self.mention_rate,
            "citation_rate": self.citation_rate,
            "recommendation_rate": self.recommendation_rate,
            "query_coverage": self.query_coverage,
            "avg_recommendation_level": self.avg_recommendation_level,
            "competitor_count": self.competitor_count,
            "captured_at": self.captured_at,
        }


class DeltaCalculator:
    """计算基线 → 重测的 Delta（规格 §9）。"""

    @staticmethod
    def compute(baseline: BaselineMetrics, remeasurement: BaselineMetrics) -> Dict[str, float]:
        def _delta(a: float, b: float) -> float:
            return round(b - a, 3)

        return {
            "mention_delta": _delta(baseline.mention_rate, remeasurement.mention_rate),
            "citation_delta": _delta(baseline.citation_rate, remeasurement.citation_rate),
            "recommendation_delta": _delta(baseline.recommendation_rate, remeasurement.recommendation_rate),
            "query_coverage_delta": _delta(baseline.query_coverage, remeasurement.query_coverage),
            "avg_recommendation_level_delta": _delta(
                baseline.avg_recommendation_level, remeasurement.avg_recommendation_level
            ),
            "competitor_delta": _delta(baseline.competitor_count, remeasurement.competitor_count),
        }


class ReMeasurementService:
    """重测服务：对相同 Query Set 重新采集并计算聚合指标（规格 §8）。"""

    def __init__(self, adapter):
        self.adapter = adapter

    async def remeasure(
        self,
        case_id: str,
        queries: List[str],
        metrics_fn=None,
    ) -> BaselineMetrics:
        """用相同 Query Set 重测，返回聚合指标。

        metrics_fn: 可选，自定义指标聚合函数 (observations) -> BaselineMetrics
        """
        observations = await self.adapter.collect_batch(
            [{"query": q} for q in queries]
        )
        from .measurement_analysis import aggregate_metrics
        if metrics_fn:
            return metrics_fn(observations, case_id=case_id, version="remeasurement")
        return aggregate_metrics(observations, case_id=case_id, version="remeasurement")
