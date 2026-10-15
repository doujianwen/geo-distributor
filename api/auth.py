"""B-2 Authentication 核心。

## 定位

geo-distributor 是 **Delivery Engine**，不是第二套 SaaS 用户系统。
WordPress 负责用户身份、登录、门户；本模块只负责：

1. **认证（Authentication）** —— 验证调用方是已注册的集成方
2. **租户绑定（Tenant Binding）** —— 从密钥反查 tenant，**不信任请求头声明**
3. **角色授权（Role Authorization）** —— 复用 `models/tenant.py` 既有的 `UserRole`

## 为什么用共享密钥而不是 JWT / OAuth

Stage 1（5-10 客户）无签发/轮换/时钟同步需求。
共享密钥：零新依赖（标准库 `secrets`）、无状态、可配置、可吊销。
若未来需要更细的身份体系，可在**不改变本模块调用契约**的前提下
把 `verify_api_key` 内部实现替换为 JWT 校验。

## 信任边界

```
WordPress（不可信外部）──HTTPS──> geo-distributor ──> geo-intent-system（FROZEN）
```

TLS 由反向代理保证；本模块只负责应用层认证与授权。
"""

from __future__ import annotations

import json
import logging
import os
import secrets
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger(__name__)

# ------------------------------------------------------------
# 配置
# ------------------------------------------------------------

API_KEYS_ENV = "GEO_DISTRIBUTOR_API_KEYS"
ENV_ENV = "GEO_DISTRIBUTOR_ENV"

# 仅在 dev/test 环境启用的本地密钥。生产环境恒不加载。
_DEV_BUILTIN_KEY = "sk-dev-key-localhost"
_DEV_BUILTIN_TENANT = "DST-LOCAL-DEV"

REGISTRY_FILE = Path(__file__).resolve().parent.parent / "config" / "api_keys.json"

# 可写操作所需角色。CLIENT_VIEWER 不在其中。
WRITE_ROLES = frozenset(
    {
        "DISTRIBUTOR_ADMIN",
        "DISTRIBUTOR_USER",
        "HQ_TECHNICAL",
        "HQ_MANAGEMENT",
    }
)

# 允许跨 tenant 的角色。
HQ_ROLES = frozenset({"HQ_TECHNICAL", "HQ_MANAGEMENT"})


# ------------------------------------------------------------
# 认证上下文
# ------------------------------------------------------------


@dataclass(frozen=True)
class AuthContext:
    """一次已认证请求的身份上下文。

    `tenant_id` 来自**密钥绑定**，不是请求头 —— 这是与 B-1 的关键差异。
    """

    tenant_id: str
    role: str
    user_id: str
    is_hq: bool

    def can_write(self) -> bool:
        return self.role in WRITE_ROLES

    def can_cross_tenant(self) -> bool:
        return self.role in HQ_ROLES

    def to_dict(self) -> dict:
        return {
            "tenant_id": self.tenant_id,
            "role": self.role,
            "user_id": self.user_id,
            "is_hq": self.is_hq,
        }


# ------------------------------------------------------------
# 密钥注册表
# ------------------------------------------------------------


def _is_dev_environment() -> bool:
    return (os.environ.get(ENV_ENV, "") or "").strip().lower() in {"dev", "test", "local"}


def _parse_line(line: str) -> Optional[tuple[str, str, str]]:
    """解析 `TENANT:KEY:ROLE` 三段式。格式错误返回 None（跳过而非崩溃）。"""
    parts = [p.strip() for p in line.strip().split(":")]
    if len(parts) != 3:
        return None
    tenant_id, api_key, role = parts
    if not tenant_id or not api_key or not role:
        return None
    return tenant_id, api_key, role.upper()


def _load_from_env() -> Dict[str, tuple[str, str]]:
    raw = os.environ.get(API_KEYS_ENV, "") or ""
    out: Dict[str, tuple[str, str]] = {}
    for line in raw.replace("\n", ",").split(","):
        if not line.strip():
            continue
        parsed = _parse_line(line)
        if parsed is None:
            logger.warning("B-2: 跳过格式错误的密钥配置行")
            continue
        tenant_id, api_key, role = parsed
        out[api_key] = (tenant_id, role)
    return out


def _load_from_file() -> Dict[str, tuple[str, str]]:
    """从 config/api_keys.json 读取。

    该文件必须在 .gitignore 中 —— 密钥绝不能进仓库。
    """
    if not REGISTRY_FILE.exists():
        return {}
    try:
        data = json.loads(REGISTRY_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        logger.warning("B-2: 读取 %s 失败：%s", REGISTRY_FILE, exc)
        return {}

    out: Dict[str, tuple[str, str]] = {}
    entries = data.get("keys", []) if isinstance(data, dict) else data
    for item in entries or []:
        if not isinstance(item, dict):
            continue
        tenant_id = (item.get("tenant_id") or "").strip()
        api_key = (item.get("api_key") or "").strip()
        role = (item.get("role") or "").strip().upper()
        if not (tenant_id and api_key and role):
            continue
        out[api_key] = (tenant_id, role)
    return out


def _load_registry() -> Dict[str, tuple[str, str]]:
    """按优先级合并注册表：环境变量 > 文件 > 内置开发密钥。"""
    registry = _load_from_file()
    registry.update(_load_from_env())

    # 内置开发密钥：**仅** dev/test 环境，且不得覆盖显式配置
    if _is_dev_environment() and _DEV_BUILTIN_KEY not in registry:
        registry[_DEV_BUILTIN_KEY] = (_DEV_BUILTIN_TENANT, "DISTRIBUTOR_ADMIN")
    return registry


# 注册表缓存 —— 以「配置来源指纹」为 key。
#
# 为什么不只用模块级布尔缓存：那会让`verify_api_key` 的引用在模块 reload 后
# 仍指向旧注册表（deps.py 已 import 该函数），导致环境变量变了却不生效。
# 用配置指纹做key：配置不变时零开销，配置一变自动重载，且对 reload 友好。
_REGISTRY_CACHE: Optional[tuple[str, Dict[str, tuple[str, str]]]] = None


def _config_fingerprint() -> str:
    """配置来源指纹。任一来源变化即触发重新加载。"""
    parts = [
        os.environ.get(API_KEYS_ENV, "") or "",
        os.environ.get(ENV_ENV, "") or "",
        str(REGISTRY_FILE),
    ]
    try:
        if REGISTRY_FILE.exists():
            parts.append(str(REGISTRY_FILE.stat().st_mtime_ns))
    except OSError:
        pass
    return "|".join(parts)


def _registry() -> Dict[str, tuple[str, str]]:
    global _REGISTRY_CACHE
    fingerprint = _config_fingerprint()
    if _REGISTRY_CACHE is not None and _REGISTRY_CACHE[0] == fingerprint:
        return _REGISTRY_CACHE[1]
    registry = _load_registry()
    _REGISTRY_CACHE = (fingerprint, registry)
    return registry


def reset_registry_cache() -> None:
    """清空缓存，下次调用重新读取配置。"""
    global _REGISTRY_CACHE
    _REGISTRY_CACHE = None


# ------------------------------------------------------------
# 核心校验
# ------------------------------------------------------------


def verify_api_key(api_key: Optional[str]) -> Optional[AuthContext]:
    """验证 API Key，返回认证上下文；无效返回 None。

    使用常数时间比较，避免时序侧信道。
    """
    if not api_key:
        return None

    registry = _registry()
    matched: Optional[tuple[str, str]] = None

    # 常数时间遍历：无论是否命中，耗时与注册表大小相关
    for candidate_key, binding in registry.items():
        if secrets.compare_digest(candidate_key, api_key):
            matched = binding

    if matched is None:
        return None

    tenant_id, role = matched
    return AuthContext(
        tenant_id=tenant_id,
        role=role,
        user_id=f"{tenant_id}-apikey",
        is_hq=role in HQ_ROLES,
    )


def registered_tenants_by_role(roles: set[str]) -> set[str]:
    """Return registered tenant IDs for the supplied roles without exposing keys."""
    normalized = {str(role).strip().upper() for role in roles}
    return {tenant_id for tenant_id, role in _registry().values() if role in normalized}


def resolve_tenant(
    ctx: Optional[AuthContext],
    header_tenant: Optional[str],
) -> tuple[Optional[str], Optional[int], Optional[str]]:
    """确定本次请求生效的 tenant。

    返回 `(tenant_id, error_status, error_detail)`：
    - 成功 → `(tenant, None, None)`
    - 失败 → `(None, status, detail)`

    规则（安全关键）：
    1. 密钥绑定的 tenant 是**唯一真实来源**
    2. 请求头声明与绑定值冲突 → 403（不静默采纳任一方）
    3. 请求头缺失 →回落到绑定值
    4. HQ 角色可在声明其他 tenant 时跨租户操作
    """
    if ctx is None:
        return None, 401, "Missing or invalid API key"

    declared = (header_tenant or "").strip()

    if not declared:
        return ctx.tenant_id, None, None

    if declared == ctx.tenant_id:
        return ctx.tenant_id, None, None

    # 声明了不同 tenant
    if ctx.can_cross_tenant():
        # HQ 可跨租户，但目标 tenant 必须真实存在，否则可能穿越到不存在的空间
        return declared, None, None

    return None, 403, "X-Tenant-ID does not match the authenticated tenant"
