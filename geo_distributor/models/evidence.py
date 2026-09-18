"""Evidence 层模型（ADR-007 Evidence First Architecture）。

> **P1-1 已统一**：本模块原先独立定义了一份 `Evidence` dataclass，与
> `models/geo_core.py` 中的定义字段不一致（缺 EvidenceLevel 分级，多 url/metadata），
> 造成调用方二选一的割裂。
>
> 现以 `geo_core.Evidence` 为**唯一权威定义**，本模块退化为 re-export 兼容层——
> 保留 `from geo_distributor.models.evidence import Evidence` 这条历史导入路径
> 不再报错，但不再维护第二份结构。

Evidence 是对 Observation 的可验证支撑：
- 引用原文摘录
- URL 来源
- 可信度评分
- 证据强度分级（E0–E4）
- 可追溯性（从 Provider -> Prompt -> Observation -> Evidence）

位置：Observation → Evidence → Measurement → Diagnosis
"""

from .geo_core import Evidence, EvidenceLevel

__all__ = ["Evidence", "EvidenceLevel"]
