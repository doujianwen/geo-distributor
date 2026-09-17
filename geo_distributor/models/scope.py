"""Technical Scope 模型（Sprint 0 — P0 核心）。

Scope 是商业请求与技术执行的转换层。
一旦批准，Scope 冻结，不得随意修改。
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List
from enum import Enum, auto


class ScopeChangeType(Enum):
    """Scope Change 类型。"""
    PRICE_CHANGE = "price_change"
    SCOPE_CHANGE = "scope_change"  # 市场/引擎/Query Volume 实质性变化
    REVISION = "revision"  # 文字修改、格式调整
    REWORK = "rework"  # 技术重做


@dataclass
class TechnicalScope:
    """Technical Scope — HQ 将商业语言转换为可执行技术范围。

    Scope 批准后冻结。任何改变商业承诺的变更必须进入 Scope Change 流程。
    """
    scope_id: str
    request_id: str
    tenant_id: str
    # --- 目标 ---
    markets: List[str] = field(default_factory=list)
    engines: List[str] = field(default_factory=list)
    # --- 技术策略 ---
    query_policy: str = "HQ_DEFINED"  # HQ_DEFINED / CLIENT_PROVIDED
    query_set_id: Optional[str] = None
    measurement_rounds: int = 1
    sampling_protocol: str = "HQ-GEO-SP-001"
    # --- 服务阶段 ---
    measurement: bool = True
    diagnosis: bool = False
    intervention: bool = False
    remeasurement: bool = False
    # --- 交付物 ---
    deliverables: List[str] = field(default_factory=lambda: ["client_report"])
    # --- 假设与排除 ---
    assumptions: List[str] = field(default_factory=list)
    exclusions: List[str] = field(default_factory=list)
    # --- 审批 ---
    approved_by: Optional[str] = None  # HQ team ID
    approved_at: Optional[str] = None
    version: int = 1
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> dict:
        return {
            "scope_id": self.scope_id,
            "request_id": self.request_id,
            "tenant_id": self.tenant_id,
            "markets": self.markets,
            "engines": self.engines,
            "query_policy": self.query_policy,
            "query_set_id": self.query_set_id,
            "measurement_rounds": self.measurement_rounds,
            "sampling_protocol": self.sampling_protocol,
            "measurement": self.measurement,
            "diagnosis": self.diagnosis,
            "intervention": self.intervention,
            "remeasurement": self.remeasurement,
            "deliverables": self.deliverables,
            "assumptions": self.assumptions,
            "exclusions": self.exclusions,
            "approved_by": self.approved_by,
            "approved_at": self.approved_at,
            "version": self.version,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    def requires_scope_change(self, other: "TechnicalScope") -> bool:
        """判断是否需要 Scope Change（商业影响）。

        规则：
        - 市场/引擎实质性变化 → Scope Change
        - Query Volume 显著增加 → Scope Change
        - 新增服务阶段 → Scope Change
        - 文字修订 → Revision（非 Scope Change）
        """
        changed = False
        if set(self.markets) != set(other.markets):
            changed = True
        if set(self.engines) != set(other.engines):
            changed = True
        if abs(self.measurement_rounds - other.measurement_rounds) > 1:
            changed = True
        if self.diagnosis != other.diagnosis or self.intervention != other.intervention or self.remeasurement != other.remeasurement:
            changed = True
        return changed
