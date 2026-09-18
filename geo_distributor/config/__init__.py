"""配置管理模块。

设计原则：
- 默认路径指向 geo-collector 的配置（共享数据源）
- 可通过环境变量或命令行参数覆盖
- 不修改 geo-collector 的任何文件
"""

import os
import re
import sys
from functools import lru_cache
from typing import Any, Optional

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


# ${VAR_NAME} 占位符：配置里出现即由同名环境变量注入
_ENV_PLACEHOLDER = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


def _expand_env(node: Any) -> Any:
    """递归展开配置里的 ${ENV_VAR} 占位符。

    未设置的环境变量展开为空字符串——调用方应在读取处做存在性校验，
    而不是让 KeyError 在深层代码里冒出来。
    """
    if isinstance(node, str):
        return _ENV_PLACEHOLDER.sub(lambda m: os.environ.get(m.group(1), ""), node)
    if isinstance(node, dict):
        return {k: _expand_env(v) for k, v in node.items()}
    if isinstance(node, list):
        return [_expand_env(v) for v in node]
    return node


# 疑似硬编码密钥：足够长且字符集像 base64/hex 的无空格串
_SECRET_LIKE = re.compile(r"^[A-Za-z0-9+/=_-]{20,}$")

# 这些 key 出现长字符串是正常的（路径、UA、模型名），不告警
_SECRET_KEY_ALLOWLIST = {
    "base_url", "url", "path", "output_root", "version", "name",
    "user_agent", "model", "provider", "engine", "timeout_seconds",
}

_SECRET_KEY_HINTS = ("key", "secret", "token", "password", "credential")


def scan_hardcoded_secrets(node: Any, path: str = "") -> list:
    """扫描配置里疑似硬编码的密钥，返回 [(配置路径, 原因), ...]。

    用于在启动时告警，避免密钥随仓库提交。**只报告，不修改**。
    """
    hits: list = []
    if isinstance(node, dict):
        for k, v in node.items():
            hits.extend(scan_hardcoded_secrets(v, f"{path}.{k}" if path else str(k)))
    elif isinstance(node, list):
        for i, v in enumerate(node):
            hits.extend(scan_hardcoded_secrets(v, f"{path}[{i}]"))
    elif isinstance(node, str):
        leaf = path.split(".")[-1].split("[")[0].lower()
        if any(h in leaf for h in _SECRET_KEY_HINTS) and leaf not in _SECRET_KEY_ALLOWLIST:
            if _SECRET_LIKE.match(node.strip()):
                hits.append((path, f"疑似硬编码密钥（长度 {len(node)}），应改为 ${{ENV_VAR}} 占位符"))
    return hits


def get_secret(settings: dict, *keys: str, env_var: str = "") -> str:
    """读取密钥：环境变量优先，回退配置。

    用法：get_secret(settings, "elmo", "api_key", env_var="ELMO_API_KEY")
    """
    if env_var:
        v = os.environ.get(env_var, "").strip()
        if v:
            return v
    node: Any = settings
    for k in keys:
        if not isinstance(node, dict):
            return ""
        node = node.get(k)
    return (node or "").strip() if isinstance(node, str) else ""


@lru_cache
def load_settings(path: Optional[str] = None) -> dict:
    """加载配置（含 ${ENV_VAR} 展开）。

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
        raw = yaml.safe_load(f) or {}
    return _expand_env(raw)


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
