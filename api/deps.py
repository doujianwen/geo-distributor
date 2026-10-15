"""FastAPI 依赖：B-2 认证中间层。

用法（router 层）：

```python
from ..deps import require_auth, AuthContextDep

@router.get("")
async def list_projects(
    auth: AuthContextDep,                      # ← 认证 + tenant 解析
    x_tenant_id: ... = Header(None),           # ← 声明（会被交叉校验）
):
    tenant_id = auth.tenant_id                 # ← 用认证结果，不用 header
```

设计要点：
- 认证失败 → 401（无凭证 / 密钥无效）
- tenant 声明冲突 → 403（认证通过但越权）
- 写操作需 `require_write` 额外校验
-认证层**不改变** B-1 的 tenant 隔离语义，只在其之前建立身份
"""

from __future__ import annotations

from typing import Annotated, Optional

from fastapi import Depends, Header, HTTPException

from .auth import AuthContext, resolve_tenant, verify_api_key

API_KEY_HEADER = "X-API-Key"
TENANT_HEADER = "X-Tenant-ID"


def authenticate(
    x_api_key: Annotated[Optional[str], Header(alias=API_KEY_HEADER)] = None,
    x_tenant_id: Annotated[Optional[str], Header(alias=TENANT_HEADER)] = None,
) -> AuthContext:
    """FastAPI 依赖：认证 + tenant 解析。失败即抛 HTTPException。"""
    ctx = verify_api_key(x_api_key)
    if ctx is None:
        # 401：无法证明身份。刻意不区分「缺失」与「无效」，
        # 避免给攻击者提供「密钥是否存在」的信息。
        raise HTTPException(status_code=401, detail="Invalid or missing API key")

    # 限流：按 API Key 计数（认证已通过，key 有效）
    from .ratelimit import limiter

    allowed, remaining, retry_after = limiter.check(x_api_key or "")
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded",
            headers={
                "Retry-After": str(retry_after),
                "X-RateLimit-Limit": str(limiter.rate_per_min),
                "X-RateLimit-Remaining": "0",
            },
        )

    tenant_id, err_status, err_detail = resolve_tenant(ctx, x_tenant_id)
    if err_status is not None:
        raise HTTPException(status_code=err_status, detail=err_detail)

    # 用校验后的 tenant 覆盖，确保下游只看到可信值
    return AuthContext(
        tenant_id=tenant_id or ctx.tenant_id,
        role=ctx.role,
        user_id=ctx.user_id,
        is_hq=ctx.is_hq,
    )


def require_write(auth: AuthContext = Depends(authenticate)) -> AuthContext:
    """FastAPI 依赖：写权限校验（CLIENT_VIEWER 禁止写）。"""
    if not auth.can_write():
        raise HTTPException(status_code=403, detail="Role is not permitted to write")
    return auth


# 便于 router 直接标注


# ------------------------------------------------------------
# Annotated 形式（推荐）
# ------------------------------------------------------------
# 为什么需要这个别名：
# 本项目所有 router 都有 `from __future__ import annotations`，
# 它会把注解变成字符串，导致 FastAPI 在部分版本下无法正确识别
# `auth=Depends(x)` 默认值形式，把 auth 当作请求体字段。
# 用 `Annotated[AuthContext, Depends(...)]` 可稳定工作。

AuthDep = Annotated[AuthContext, Depends(authenticate)]
WriteDep = Annotated[AuthContext, Depends(authenticate), Depends(require_write)]


# ------------------------------------------------------------
# 审计辅助
# ------------------------------------------------------------
# 写操作后调用示例：
#   record_auth_audit(auth, "CREATE", "PROJECT", pid, new_value=...)
#
# 刻意做得很薄：审计不阻断主流程，失败只记warning。
def record_auth_audit(
    auth: AuthContext,
    action: str,
    resource_type: str = "",
    resource_id: str = "",
    **kwargs,
) -> None:
    """按认证身份记录一条审计。永不抛异常。"""
    from .audit import record_audit

    record_audit(
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        auth=auth,
        **kwargs,
    )
