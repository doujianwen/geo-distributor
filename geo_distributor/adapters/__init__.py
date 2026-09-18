"""适配器包。

提供与外部系统的集成接口：
- ElmoAdapter: Elmo 平台适配器（REST API，等待 A1.7）
- GeoCollectorAdapter: 直接调用 geo-collector Python 模块（fallback，有 import 风险）
- GeoCollectorDBAdapter: 直接读取 geo-collector SQLite 数据库（推荐，零依赖）
- OpenGeoAdapter: 从已落盘的 JSON 文件读取（Sprint4 测试用）
"""

from .base import BaseAdapter, ElmoAdapter, GeoCollectorAdapter
from .opengeo import OpenGeoAdapter
from .geo_collector_db import GeoCollectorDBAdapter

__all__ = ["BaseAdapter", "ElmoAdapter", "GeoCollectorAdapter", "OpenGeoAdapter", "GeoCollectorDBAdapter"]
