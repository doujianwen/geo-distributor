"""审计日志 + 限流门禁（RED-GATE）。

覆盖两项：
1. 审计：写操作留痕 + 租户隔离（查询必须按 tenant 过滤）
2. 限流：令牌桶正确性 + 429 行为

设计原则（沿用 B-1/B-3 教训）：
- 硬断言，不用条件式断言
- 限流测试用可控时钟，不靠 sleep
- 审计查询的跨租户隔离必须显式验证

运行：
    pytest tests/test_audit_ratelimit.py -v
"""

from __future__ import annotations

import importlib

import pytest
from fastapi.testclient import TestClient

KEYS = (
    "DST-AUD-A:sk-aud-a:DISTRIBUTOR_ADMIN,"
    "DST-AUD-B:sk-aud-b:DISTRIBUTOR_ADMIN"
)
TA = "DST-AUD-A"
TB = "DST-AUD-B"


def _h(tenant: str) -> dict:
    key = "sk-aud-a" if tenant == TA else "sk-aud-b"
    return {"X-API-Key": key, "X-Tenant-ID": tenant}


@pytest.fixture()
def client(monkeypatch):
    import os

    os.environ["GEO_DISTRIBUTOR_ENV"] = "test"
    os.environ["GEO_DISTRIBUTOR_API_KEYS"] = KEYS
    from api.audit import reset_audit_store

    reset_audit_store()
    try:
        from api.auth import reset_registry_cache

        reset_registry_cache()
    except Exception:
        pass

    from api import state

    app_mod = importlib.import_module("api.app")
    importlib.reload(app_mod)
    state.init_repositories(None)
    with TestClient(app_mod.app) as c:
        yield c
    reset_audit_store()


# ==================================================================
# 1. 审计：基本能力
# ==================================================================


class TestAuditBasics:
    def test_record_and_read_back(self):
        from api.audit import query_audit, record_audit
        aid = record_audit(
            action="CREATE",
            resource_type="PROJECT",
            resource_id="PRJ-AUD-1",
            tenant_id=TA,
            user_id="USR-1",
            role="DISTRIBUTOR_ADMIN",
        )
        assert aid is not None, "审计写入返回 None —— 审计库不可用"

        rows = query_audit(tenant_id=TA)
        assert len(rows) == 1, f"应记录 1 条，实际 {len(rows)}"
        assert rows[0]["resource_id"] == "PRJ-AUD-1"
        assert rows[0]["action"] == "CREATE"

    def test_audit_never_raises(self):
        """审计故障绝不能影响主流程。"""
        from api.audit import record_audit
        # 传不可序列化的对象 + 极端值
        result = record_audit(
            action="CREATE",
            resource_type="X",
            resource_id="Y",
            tenant_id=TA,
            new_value={"weird": object()},
        )
        # 要么成功，要么返回 None —— 但绝不抛异常
        assert result is None or isinstance(result, str)

    def test_large_value_is_truncated(self):
        from api.audit import query_audit, record_audit
        big = "x" * 100000
        record_audit(
            action="UPDATE",
            resource_type="PROJECT",
            resource_id="PRJ-BIG",
            tenant_id=TA,
            new_value={"blob": big},
        )
        rows = query_audit(tenant_id=TA)
        assert len(rows) == 1
        stored = rows[0]["new_value"] or ""
        assert len(stored) < 5000, f"超长值未截断：{len(stored)} 字符"

    def test_outcome_failure_is_recorded(self):
        from api.audit import query_audit, record_audit
        record_audit(
            action="DELETE",
            resource_type="PROJECT",
            resource_id="PRJ-X",
            tenant_id=TA,
            outcome="DENIED",
            reason="cross-tenant attempt",
        )
        rows = query_audit(tenant_id=TA)
        assert rows, "失败操作也必须留痕"
        assert rows[0]["outcome"] == "DENIED"


# ==================================================================
# 2. 审计：租户隔离（关键安全属性）
# ==================================================================


class TestAuditTenantIsolation:
    def test_query_without_tenant_returns_empty(self):
        """不传 tenant 必须返回空，而不是「全部」——
        否则忘记传参会变成跨租户泄漏。"""
        from api.audit import query_audit, record_audit
        record_audit(action="CREATE", resource_type="P", resource_id="1", tenant_id=TA)

        assert query_audit() == [], "未指定 tenant 时竟返回了数据"
        assert query_audit(tenant_id=None) == []
        assert query_audit(tenant_id="") == []

    def test_tenant_b_cannot_see_tenant_a_audit(self):
        from api.audit import query_audit, record_audit
        record_audit(
            action="CREATE", resource_type="PROJECT",
            resource_id="PRJ-SECRET", tenant_id=TA,
        )

        rows_b = query_audit(tenant_id=TB)
        assert rows_b == [], f"Tenant B 读到了 A 的审计：{rows_b}"

    def test_audit_stats_are_tenant_scoped(self):
        from api.audit import audit_stats, record_audit
        record_audit(action="CREATE", resource_type="P", resource_id="1", tenant_id=TA)
        record_audit(action="CREATE", resource_type="P", resource_id="2", tenant_id=TA)
        record_audit(action="DELETE", resource_type="P", resource_id="3", tenant_id=TB)

        assert audit_stats(TA) == {"CREATE": 2}
        assert audit_stats(TB) == {"DELETE": 1}
        assert audit_stats("NONEXISTENT") == {}


# ==================================================================
# 3. 限流：令牌桶正确性
# ==================================================================


class TestRateLimiterUnit:
    def test_allows_up_to_burst(self):
        from api.ratelimit import RateLimiter

        rl = RateLimiter(rate_per_min=60, burst=5)
        results = [rl.check("k1")[0] for _ in range(5)]
        assert all(results), f"前5 次应全放行：{results}"

    def test_blocks_after_burst(self):
        from api.ratelimit import RateLimiter

        rl = RateLimiter(rate_per_min=60, burst=3)
        for _ in range(3):
            rl.check("k1")
        allowed, remaining, retry = rl.check("k1")
        assert allowed is False, "超出 burst 竟仍放行"
        assert remaining == 0
        assert retry >= 1, "必须给出建议等待秒数"

    def test_keys_are_independent(self):
        from api.ratelimit import RateLimiter

        rl = RateLimiter(rate_per_min=60, burst=2)
        rl.check("k1")
        rl.check("k1")
        assert rl.check("k1")[0] is False, "k1 应已耗尽"
        assert rl.check("k2")[0] is True, "k2 是独立桶，不应受影响"

    def test_empty_key_is_never_limited(self):
        """无 key 的请求已在认证层被拒，此处不应再限流。"""
        from api.ratelimit import RateLimiter

        rl = RateLimiter(rate_per_min=1, burst=1)
        for _ in range(100):
            assert rl.check("")[0] is True

    def test_reset_clears_buckets(self):
        from api.ratelimit import RateLimiter

        rl = RateLimiter(rate_per_min=60, burst=1)
        rl.check("k1")
        assert rl.check("k1")[0] is False
        rl.reset()
        assert rl.check("k1")[0] is True, "reset 后应恢复"

    def test_reset_single_key_only(self):
        from api.ratelimit import RateLimiter

        rl = RateLimiter(rate_per_min=60, burst=1)
        rl.check("k1")
        rl.check("k2")
        rl.reset("k1")
        assert rl.check("k1")[0] is True
        assert rl.check("k2")[0] is False, "reset(k1) 不应影响 k2"

    def test_token_refills_over_time(self):
        """令牌随时间补充 —— 用可控时钟，不靠 sleep。"""
        import api.ratelimit as rl_mod

        rl_mod.os.environ["GEO_DISTRIBUTOR_CLOCK_SCALE"] = "1000"  # 加速1000倍
        try:
            importlib.reload(rl_mod)
            rl = rl_mod.RateLimiter(rate_per_min=60, burst=2)  # 1 token/秒
            rl.check("k1")
            rl.check("k1")
            assert rl.check("k1")[0] is False, "应已耗尽"
            # 真实等待 0.05s × 1000 = 虚拟 50 秒 → 令牌早已补满
            import time

            time.sleep(0.05)
            assert rl.check("k1")[0] is True, "令牌未随时间补充"
        finally:
            rl_mod.os.environ.pop("GEO_DISTRIBUTOR_CLOCK_SCALE", None)
            importlib.reload(rl_mod)


# ==================================================================
# 4. 限流：HTTP 行为
# ==================================================================


class TestRateLimitHTTP:
    def test_burst_then_429(self, client, monkeypatch):
        """连续请求超过 burst 后应返回 429 + Retry-After。"""
        import api.ratelimit as rl_mod

        monkeypatch.setenv("GEO_DISTRIBUTOR_RATE_LIMIT", "60")
        monkeypatch.setenv("GEO_DISTRIBUTOR_RATE_BURST", "3")
        importlib.reload(rl_mod)
        monkeypatch.setattr(rl_mod, "limiter", rl_mod.RateLimiter(60, 3))
        # 让 deps 用新的 limiter
        import api.deps as deps_mod

        deps_mod.limiter = rl_mod.limiter

        # 5 次读操作，前 3 次应成功
        codes = []
        for _ in range(5):
            r = client.get("/projects", headers=_h(TA))
            codes.append(r.status_code)

        assert 429 in codes, f"未触发限流：{codes}"
        idx = codes.index(429)
        assert all(c == 200 for c in codes[:idx]), f"限流前应全部成功：{codes[:idx]}"

    def test_429_includes_retry_after_header(self, client, monkeypatch):
        import api.ratelimit as rl_mod

        monkeypatch.setenv("GEO_DISTRIBUTOR_RATE_LIMIT", "60")
        monkeypatch.setenv("GEO_DISTRIBUTOR_RATE_BURST", "1")
        importlib.reload(rl_mod)
        limiter = rl_mod.RateLimiter(60, 1)
        monkeypatch.setattr(rl_mod, "limiter", limiter)
        import api.deps as deps_mod

        deps_mod.limiter = limiter

        client.get("/projects", headers=_h(TA))
        r = client.get("/projects", headers=_h(TA))
        assert r.status_code == 429
        assert "Retry-After" in r.headers, "429 响应必须带 Retry-After"

    def test_limit_is_per_key(self, client, monkeypatch):
        """A 的限流不影响 B。"""
        import api.ratelimit as rl_mod

        monkeypatch.setenv("GEO_DISTRIBUTOR_RATE_LIMIT", "60")
        monkeypatch.setenv("GEO_DISTRIBUTOR_RATE_BURST", "1")
        importlib.reload(rl_mod)
        limiter = rl_mod.RateLimiter(60, 1)
        monkeypatch.setattr(rl_mod, "limiter", limiter)
        import api.deps as deps_mod

        deps_mod.limiter = limiter

        client.get("/projects", headers=_h(TA))
        assert client.get("/projects", headers=_h(TA)).status_code == 429
        # B 是独立 key
        assert client.get("/projects", headers=_h(TB)).status_code == 200, "限流影响了其他租户"
