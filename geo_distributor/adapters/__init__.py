"""适配器包。

提供与外部系统的集成接口：
- ElmoAdapter: Elmo 平台适配器（预留，等待 A1.6）
- GeoCollectorAdapter: 直接调用 geo-collector（fallback 方案）
"""

from .base import BaseAdapter, ElmoAdapter, GeoCollectorAdapter
from .opengeo import OpenGeoAdapter

__all__ = ["BaseAdapter", "ElmoAdapter", "GeoCollectorAdapter", "OpenGeoAdapter"]
