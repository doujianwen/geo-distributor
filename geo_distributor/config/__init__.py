"""配置管理模块。

设计原则：
- 默认路径指向 geo-collector 的配置（共享数据源）
- 可通过环境变量或命令行参数覆盖
- 不修改 geo-collector 的任何文件
"""

import os
import sys
from functools import lru_cache
from typing import Optional

import yaml

# geo-collector 的安装路径（绝对路径，硬编码以避免依赖污染）
# __file__ = .../geo-distributor/geo_distributor/config/__init__.py
# 往上两层 → geo-distributor/，再进 geo-collector/
_GEO_COLLECTOR_ROOT = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "geo-collector")
)

# 本项目的配置根目录（geo-distributor/ 自身）
_PROJECT_ROOT = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..")
)


def get_project_root() -> str:
    """返回 geo-distributor 项目根目录。"""
    return _PROJECT_ROOT


def get_geo_collector_root() -> str:
    """返回 geo-collector 项目根目录。"""
    return _GEO_COLLECTOR_ROOT


@lru_cache
def load_settings(path: Optional[str] = None) -> dict:
    """加载配置。

    优先级：
    1. 显式传入 path
    2. 环境变量 GEO_DISTRIBUTOR_CONFIG
    3. 本项目 config/settings.yaml
    4. geo-collector config/settings.yaml（回退共享）
    """
    if path is None:
        path = os.environ.get(
            "GEO_DISTRIBUTOR_CONFIG",
            os.path.join(_PROJECT_ROOT, "config", "settings.yaml"),
        )
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


@lru_cache
def load_engines(path: Optional[str] = None) -> dict:
    """加载引擎配置，优先级同上。"""
    if path is None:
        path = os.environ.get(
            "GEO_DISTRIBUTOR_ENGINES",
            os.path.join(_PROJECT_ROOT, "config", "engines.yaml"),
        )
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def ensure_sys_path() -> None:
    """将 geo-collector 加入 sys.path，使 storage/parser/collectors 可直接 import。

    仅在需要直接调用 geo-collector 采集能力时调用此函数。
    """
    collector_path = os.path.join(_GEO_COLLECTOR_ROOT)
    if collector_path not in sys.path:
        sys.path.insert(0, collector_path)


def get_elmo_config(settings: Optional[dict] = None) -> dict:
    """Extract Elmo-specific configuration from loaded settings.

    Args:
        settings: 已加载的设置 dict；为 None 时自动加载

    Returns:
        elmo 配置 dict，缺少时返回空 dict
    """
    if settings is None:
        settings = load_settings()
    return settings.get("elmo", {})
