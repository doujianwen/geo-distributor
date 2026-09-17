"""compatibility 包 — Platform Observation 统一层。

A1.6 核心战场：
- PlatformObservation：所有 Adapter 的统一输出格式
- map_geo_collector_observation：geo-collector → Platform 映射（V0.2）
- map_elmo_evaluation：Elmo → Platform 映射（V0.3，Elmo 验证通过后实现）
"""

from .base import PlatformObservation, PlatformCitation, map_geo_collector_observation, map_geo_collector_citations

__all__ = [
    "PlatformObservation",
    "PlatformCitation",
    "map_geo_collector_observation",
    "map_geo_collector_citations",
]
