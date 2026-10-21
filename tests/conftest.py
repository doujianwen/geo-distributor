"""测试全局配置。

## 为什么需要这个文件

B-2 认证引入后，端点需要 `X-API-Key`。各测试文件若各自
`os.environ["GEO_DISTRIBUTOR_API_KEYS"] = ...`，会**互相覆盖且不还原**：

- 单跑某文件 → 通过
- 全量跑 → 后设置的文件覆盖前面的，前面的测试莫名 401

这类污染极难排查（本轮实际发生：单跑 20 passed / 全跑 3 failed）。

本文件用 `autouse` fixture + `monkeypatch` 统一管理：

1. 提供一组**通用测试密钥**，覆盖项目里出现的所有测试 tenant
2. `monkeypatch` 会在用例结束后自动还原环境变量
3. 每个测试文件可覆盖自己的密钥需求（通过 `auth_keys` fixture 参数）

## 用法

需要特定密钥的测试文件，只需覆盖 `auth_keys`：

```python
@pytest.fixture(autouse=True)
def auth_keys():
    return "DST-X:sk-x:DISTRIBUTOR_ADMIN"
```
"""

from __future__ import annotations

import os

import pytest

# 覆盖项目中所有测试用到的 tenant。
# 这些密钥只在测试环境（GEO_DISTRIBUTOR_ENV=test）生效，
# 生产环境不会加载内置开发密钥。
TEST_API_KEYS = ",".join(
    f"{tenant}:{key}:{role}"
    for tenant, key, role in [
        # --- B-1 tenant isolation ---
        ("DST-ATTACK-A", "sk-b1-key-tenant-a", "DISTRIBUTOR_ADMIN"),
        ("DST-ATTACK-B", "sk-b1-key-tenant-b", "DISTRIBUTOR_ADMIN"),
        # --- B-2 auth ---
        ("DST-ADMIN-A", "sk-test-admin-key-AAA", "DISTRIBUTOR_ADMIN"),
        ("DST-USER-B", "sk-test-user-key-BBB", "DISTRIBUTOR_USER"),
        ("DST-VIEW-C", "sk-test-viewer-key-CCC", "CLIENT_VIEWER"),
        ("HQ-OPS", "sk-test-hq-key-DDD", "HQ_TECHNICAL"),
        # --- B-3 correlated ID ---
        ("DST-B3-A", "sk-b3-key-a", "DISTRIBUTOR_ADMIN"),
        ("DST-B3-B", "sk-b3-key-b", "DISTRIBUTOR_ADMIN"),
        # --- p1_remaining ---
        ("T-CA", "sk-p1-tca", "DISTRIBUTOR_ADMIN"),
        ("T-CB", "sk-p1-tcb", "DISTRIBUTOR_ADMIN"),
        ("HQ-TEST", "sk-p1-hq", "HQ_TECHNICAL"),
        # --- 其他测试可能用到 ---
        ("DST-001", "sk-test-dst001", "DISTRIBUTOR_ADMIN"),
        ("TEST-TENANT", "sk-test-tenant", "DISTRIBUTOR_ADMIN"),
    ]
)


@pytest.fixture(autouse=True, scope="session")
def _b2_env_session():
    """会话级：确保测试环境标识已设置。

    必须在 session 级设置 GEO_DISTRIBUTOR_ENV=test，
    否则 api.auth 不会加载任何配置，非认证测试也会401。
    """
    prev = os.environ.get("GEO_DISTRIBUTOR_ENV")
    os.environ["GEO_DISTRIBUTOR_ENV"] = "test"
    yield
    if prev is None:
        os.environ.pop("GEO_DISTRIBUTOR_ENV", None)
    else:
        os.environ["GEO_DISTRIBUTOR_ENV"] = prev


@pytest.fixture(autouse=True)
def _b2_registry(monkeypatch, request):
    """用例级：注入测试密钥，结束后自动还原。

    优先使用测试文件自己定义的 `auth_keys` fixture；
    未定义时用通用的 TEST_API_KEYS。
    """
    keys = TEST_API_KEYS

    # 若该测试文件提供了自己的密钥集fixture，则用它
    own = getattr(request.module, "AUTH_KEYS", None)
    if own:
        keys = own

    monkeypatch.setenv("GEO_DISTRIBUTOR_ENV", "test")
    # Fixture-only integration actors; real professional sessions require WordPress people.
    monkeypatch.setenv('GEO_OPERATOR_ALLOW_SERVICE_ACTORS','1')
    monkeypatch.setenv("GEO_DISTRIBUTOR_API_KEYS", keys)

    # 清空注册表缓存，让新配置立即生效
    try:
        from api.auth import reset_registry_cache

        reset_registry_cache()
    except Exception:
        pass

    yield

    # 用例结束后再次清理，避免下一个用例读到本例的缓存
    try:
        from api.auth import reset_registry_cache

        reset_registry_cache()
    except Exception:
        pass


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    """用例级：重置限流器。

    限流是**按 API Key 累计**的，而测试会反复用同一密钥发多次请求
    —— 不重置会因配额耗尽（429）导致与安全无关的失败。

    这不是「放宽测试」，而是让每个用例从干净状态开始。
    限流本身由 tests/test_ratelimit.py 单独验证。
    """
    from api.ratelimit import limiter

    limiter.reset()
    yield
    limiter.reset()


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    """用例级：重置限流器。

    限流是**按 API Key 累计**的，而测试会反复用同一密钥发多次请求
    —— 不重置会因配额耗尽（429）导致与安全无关的失败。

    这不是「放宽测试」，而是让每个用例从干净状态开始。
    限流本身由 tests/test_ratelimit.py 单独验证。
    """
    from api.ratelimit import limiter

    limiter.reset()
    yield
    limiter.reset()


@pytest.fixture(autouse=True)
def _isolate_audit_db(tmp_path, monkeypatch):
    """用例级：把审计库指向独立临时文件。

    `reset_audit_store()` 只关闭连接、**不删数据**，
    所以逐个测试调用它并不足以隔离 —— 记录会跨用例累积，
    导致「应记录 1 条，实际 9 条」这类失败。

    正确做法：每个用例一个全新的审计库文件。
    """
    from api.audit import reset_audit_store

    db = tmp_path / "audit.db"
    monkeypatch.setenv("GEO_DISTRIBUTOR_AUDIT_DB", str(db))
    reset_audit_store()
    yield
    reset_audit_store()


@pytest.fixture(autouse=True)
def _restore_module_singletons():
    """用例级：恢复被reload 污染的模块级单例。

    `tests/test_audit_ratelimit.py` 为了测不同配额会 `importlib.reload`
    并替换 `api.ratelimit.limiter` / `api.deps.limiter`。
    reload 后的新对象会**留在模块里**，影响后续所有用例
    （表现为：单跑该文件全绿，全跑时其他文件莫名429）。

    做法：用例结束后把limiter 恢复为新建的默认实例。
    """
    yield

    try:
        import api.deps as deps_mod
        import api.ratelimit as rl_mod

        fresh = rl_mod.RateLimiter()
        rl_mod.limiter = fresh
        deps_mod.limiter = fresh
    except Exception:
        pass


@pytest.fixture(autouse=True)
def _restore_module_singletons():
    """用例级：恢复被reload 污染的模块级单例。

    `tests/test_audit_ratelimit.py` 为了测不同配额会 `importlib.reload`
    并替换 `api.ratelimit.limiter` / `api.deps.limiter`。
    reload 后的新对象会**留在模块里**，影响后续所有用例
    （表现为：单跑该文件全绿，全跑时其他文件莫名429）。

    做法：用例结束后把limiter 恢复为新建的默认实例。
    """
    yield

    try:
        import api.deps as deps_mod
        import api.ratelimit as rl_mod

        fresh = rl_mod.RateLimiter()
        rl_mod.limiter = fresh
        deps_mod.limiter = fresh
    except Exception:
        pass
