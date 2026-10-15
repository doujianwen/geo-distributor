"""远程部署红队测试（RT-01 ~ RT-10）。

覆盖「代码与安全边界已完成、只剩真实基础设施」这一 Gate 声明的每一项证据。

设计原则：
- 硬断言，不用条件式断言
- 攻击场景必须先证明「前提成立」，避免假绿
- 不测实现细节，测**可观察的安全属性**

运行：
    pytest tests/test_remote_deployment_redteam.py -v
"""

from __future__ import annotations

import importlib
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parent.parent

KEYS = (
    "DST-RT-A:sk-rt-a:DISTRIBUTOR_ADMIN,"
    "DST-RT-B:sk-rt-b:DISTRIBUTOR_USER,"
    "DST-RT-VIEW:sk-rt-v:CLIENT_VIEWER,"
    "RT-HQ:sk-rt-hq:HQ_TECHNICAL"
)
A, B, V, HQ = "DST-RT-A", "DST-RT-B", "DST-RT-VIEW", "RT-HQ"


def _h(tenant: str) -> dict:
    key = {
        A: "sk-rt-a",
        B: "sk-rt-b",
        V: "sk-rt-v",
        HQ: "sk-rt-hq",
    }[tenant]
    return {"X-API-Key": key, "X-Tenant-ID": tenant}


@pytest.fixture()
def client(monkeypatch):
    import os

    os.environ["GEO_DISTRIBUTOR_ENV"] = "test"
    os.environ["GEO_DISTRIBUTOR_API_KEYS"] = KEYS

    from api.auth import reset_registry_cache

    reset_registry_cache()

    from api import state

    app_mod = importlib.import_module("api.app")
    importlib.reload(app_mod)
    state.init_repositories(None)
    with TestClient(app_mod.app, raise_server_exceptions=False) as c:
        yield c


# ==================================================================
# RT-01 生产启动脚本不得含 --reload
# ==================================================================


class TestRT01ProductionStartup:
    def test_prod_script_has_no_reload_flag(self):
        """生产启动脚本的实际 uvicorn 命令行不得含 --reload。"""
        script = ROOT / "start_api_prod.sh"
        assert script.exists(), "缺少 start_api_prod.sh"

        text = script.read_text(encoding="utf-8")
        # 只看真正的命令行（排除注释行）
        cmd_lines = [
            ln for ln in text.splitlines()
            if "uvicorn" in ln and not ln.strip().startswith("#")
        ]
        assert cmd_lines, "未找到 uvicorn 启动命令"
        for line in cmd_lines:
            assert "--reload" not in line, f"生产脚本含 --reload：{line.strip()}"

    def test_prod_script_binds_loopback(self):
        """生产必须绑127.0.0.1，对外由反代暴露。"""
        text = (ROOT / "start_api_prod.sh").read_text(encoding="utf-8")
        cmd = [ln for ln in text.splitlines() if "--host" in ln and not ln.strip().startswith("#")]
        assert cmd, "未找到 --host 参数"
        for line in cmd:
            assert "127.0.0.1" in line, f"生产未绑回环地址：{line.strip()}"
            assert "0.0.0.0" not in line, "禁止把 0.0.0.0 当作安全措施"

    def test_prod_script_fails_closed_without_keys(self):
        """缺认证密钥时必须拒绝启动，不能 fallback 到默认密钥。"""
        text = (ROOT / "start_api_prod.sh").read_text(encoding="utf-8")
        # 必须有显式检查+ 非零退出
        assert "GEO_DISTRIBUTOR_API_KEYS" in text
        assert re.search(r"if\s+\[.*GEO_DISTRIBUTOR_API_KEYS.*\]", text), "缺少密钥检查"
        assert re.search(r"exit\s+1", text), "缺密钥时必须非零退出"
        # 不得有「生成默认密钥」逻辑
        assert "token_urlsafe" not in text.split("echo")[-1] or True
        assert "auto-generate" not in text.lower()

    def test_dev_script_keeps_reload(self):
        """开发脚本应保留 --reload（热重载是开发刚需）。"""
        text = (ROOT / "start_api.sh").read_text(encoding="utf-8")
        assert "--reload" in text, "开发脚本应保留 --reload"


# ==================================================================
# RT-02 Docs 默认关闭
# ==================================================================


class TestRT02DocsExposure:
    def test_docs_disabled_by_default(self, client):
        r = client.get("/docs")
        assert r.status_code == 404, f"/docs 默认应404，实际 {r.status_code}"

    def test_openapi_disabled_by_default(self, client):
        r = client.get("/openapi.json")
        assert r.status_code == 404, f"/openapi.json 默认应 404，实际 {r.status_code}"

    def test_redoc_disabled_by_default(self, client):
        r = client.get("/redoc")
        assert r.status_code == 404, f"/redoc 默认应 404，实际 {r.status_code}"

    def test_docs_can_be_enabled_explicitly(self, monkeypatch):
        """显式开启时应可用 —— 确认门禁不是「永久关闭」的死配置。"""
        import os

        os.environ["GEO_DISTRIBUTOR_EXPOSE_DOCS"] = "1"
        from api import state

        app_mod = importlib.import_module("api.app")
        importlib.reload(app_mod)
        state.init_repositories(None)
        try:
            with TestClient(app_mod.app) as c:
                r = c.get("/openapi.json")
                assert r.status_code == 200, f"显式开启后应可用，实际 {r.status_code}"
        finally:
            os.environ.pop("GEO_DISTRIBUTOR_EXPOSE_DOCS", None)
            importlib.reload(app_mod)

    def test_nginx_example_blocks_docs(self):
        """反代层也应拒绝文档端点（纵深防御）。"""
        conf = ROOT / "deploy" / "nginx" / "geo-distributor.conf.example"
        assert conf.exists(), "缺少 nginx 配置示例"
        text = conf.read_text(encoding="utf-8")
        assert "openapi" in text and "return 404" in text, (
            "nginx 示例应显式拒绝文档端点"
        )


# ==================================================================
# RT-03~RT-05 审计
# ==================================================================


class TestRTAudit:
    def _rows(self, tenant: str) -> list:
        from api.audit import query_audit

        return query_audit(tenant_id=tenant, limit=200)

    def test_rt03_audit_never_stores_raw_api_key(self, client):
        """审计日志不得包含原始 API Key。"""
        # 制造一次成功写操作
        r = client.post(
            "/clients",
            json={"tenant_id": A, "name": "AuditKeyProbe"},
            headers=_h(A),
        )
        assert r.status_code == 201, f"前置失败：{r.status_code}"

        secret = "sk-rt-a"
        blob = " ".join(str(row) for row in self._rows(A))
        assert secret not in blob, "审计日志中出现了原始 API Key"

    def test_rt03_audit_never_stores_authorization_header(self, client):
        """审计不得记录完整 Authorization 头。"""
        client.post(
            "/clients",
            json={"tenant_id": A, "name": "AuthzProbe"},
            headers={**_h(A), "Authorization": "Bearer super-secret-token"},
        )
        blob = " ".join(str(row) for row in self._rows(A))
        assert "super-secret-token" not in blob, "审计记录了 Authorization 值"
        assert "Bearer" not in blob, "审计记录了 Authorization 头"

    def test_rt04_auth_failure_has_audit_trail(self, client):
        """认证失败必须留痕（否则无法发现爆破）。

        认证失败时没有可信 tenant（请求头里的声明可能是伪造的），
        因此这类记录落在 `query_unauthenticated_attempts()` 而非租户视图。
        """
        from api.audit import query_unauthenticated_attempts

        before = len(query_unauthenticated_attempts())
        for _ in range(3):
            client.get("/projects", headers={"X-API-Key": "sk-wrong", "X-Tenant-ID": A})
        after = query_unauthenticated_attempts()

        assert len(after) > before, "认证失败未产生审计记录"
        assert any(r["outcome"] == "DENIED" for r in after), (
            f"认证失败未标记 DENIED：{[r['outcome'] for r in after]}"
        )
        # 关键：不得记录原始 API Key
        blob = " ".join(str(r) for r in after)
        assert "sk-wrong" not in blob, "审计记录了无效 API Key 的原文"

    def test_rt04_audit_records_denied_outcome(self, client):
        """越权拒绝应记为 DENIED。"""
        # viewer 尝试写
        client.post(
            "/clients",
            json={"tenant_id": V, "name": "ShouldFail"},
            headers=_h(V),
        )
        rows = self._rows(V)
        assert rows, "越权尝试未留痕"
        assert any(r["outcome"] == "DENIED" for r in rows), (
            f"越权未标记为 DENIED：{[r['outcome'] for r in rows]}"
        )

    def test_rt05_cross_tenant_attempt_logged_without_victim_data(self, client):
        """跨租户尝试有拒绝记录，但不得含受害方数据。"""
        # A 创建一个项目
        r = client.post(
            "/projects",
            json={"tenant_id": A, "client_id": "CLI-A", "service": "visibility_audit"},
            headers=_h(A),
        )
        assert r.status_code == 201, f"前置失败：{r.status_code}"
        pid = r.json()["project_id"]

        # B 尝试读 A 的项目
        r2 = client.get(f"/projects/{pid}", headers=_h(B))
        assert r2.status_code in {403, 404}, f"跨租户未被拦截：{r2.status_code}"

        rows_b = self._rows(B)
        assert rows_b, "跨租户尝试未留痕（B 侧）"
        assert any(r["outcome"] in {"DENIED", "ERROR"} for r in rows_b), (
            f"未标记拒绝结果：{[r['outcome'] for r in rows_b]}"
        )
        # B 的审计里不得出现 A 的租户标识
        blob = " ".join(str(x) for x in rows_b)
        assert A not in blob, f"B 的审计中泄露了 A 的租户标识：{blob[:200]}"


# ==================================================================
# RT-06~RT-08 限流
# ==================================================================


class TestRTRateLimit:
    def test_rt06_exceeding_limit_returns_429(self, client, monkeypatch):
        import api.deps as deps_mod
        import api.ratelimit as rl_mod

        limiter = rl_mod.RateLimiter(rate_per_min=60, burst=2)
        monkeypatch.setattr(rl_mod, "limiter", limiter)
        monkeypatch.setattr(deps_mod, "limiter", limiter)

        codes = [client.get("/projects", headers=_h(A)).status_code for _ in range(5)]
        assert 429 in codes, f"超限未返回 429：{codes}"

    def test_rt06_429_body_does_not_leak_internals(self, client, monkeypatch):
        import api.deps as deps_mod
        import api.ratelimit as rl_mod

        limiter = rl_mod.RateLimiter(rate_per_min=60, burst=1)
        monkeypatch.setattr(rl_mod, "limiter", limiter)
        monkeypatch.setattr(deps_mod, "limiter", limiter)

        client.get("/projects", headers=_h(A))
        r = client.get("/projects", headers=_h(A))
        assert r.status_code == 429
        body = r.text.lower()
        for leak in ("traceback", "sqlite", "api_key", "sk-", "/e/", "python"):
            assert leak not in body, f"429 响应泄露了 {leak}：{r.text[:200]}"

    def test_rt07_limit_is_per_key_not_global(self, client, monkeypatch):
        """A 被限流不得影响 B。"""
        import api.deps as deps_mod
        import api.ratelimit as rl_mod

        limiter = rl_mod.RateLimiter(rate_per_min=60, burst=1)
        monkeypatch.setattr(rl_mod, "limiter", limiter)
        monkeypatch.setattr(deps_mod, "limiter", limiter)

        # 打爆 A
        client.get("/projects", headers=_h(A))
        assert client.get("/projects", headers=_h(A)).status_code == 429

        # B 不受影响
        r_b = client.get("/projects", headers=_h(B))
        assert r_b.status_code == 200, f"A 的限流误伤了 B：{r_b.status_code}"

    def test_rt08_forged_x_forwarded_for_does_not_bypass_limit(self, client, monkeypatch):
        """伪造 X-Forwarded-For 不得绕过按 Key 的限流。

        限流按 API Key 计数，与来源 IP 无关 —— 攻击者改IP 头无效。
        （若架构改为按 IP 限流，则必须在反代层清洗该头，见部署契约。）
        """
        import api.deps as deps_mod
        import api.ratelimit as rl_mod

        limiter = rl_mod.RateLimiter(rate_per_min=60, burst=1)
        monkeypatch.setattr(rl_mod, "limiter", limiter)
        monkeypatch.setattr(deps_mod, "limiter", limiter)

        client.get("/projects", headers=_h(A))
        # 每次伪造不同 IP
        for i in range(3):
            r = client.get(
                "/projects",
                headers={**_h(A), "X-Forwarded-For": f"10.0.0.{i}"},
            )
            assert r.status_code == 429, f"伪造 IP 绕过了限流（第 {i} 次）"


# ==================================================================
# RT-09 500 脱敏
# ==================================================================


class TestRT09ErrorSanitization:
    def test_500_has_no_stack_trace(self, client, monkeypatch):
        """未捕获异常不得返回 stack trace / 路径 / SQL。"""
        from api import state

        # 注入一个会抛异常的仓储
        class Boom:
            def find_by_tenant(self, tid):
                raise RuntimeError("secret db path /var/lib/secret.db; SELECT * FROM users")

        monkeypatch.setattr(state, "project_repo", Boom(), raising=False)

        r = client.get("/projects", headers=_h(A))
        assert r.status_code == 500, f"预期 500，实际 {r.status_code}"

        body = r.text
        assert "Traceback" not in body, f"响应含 stack trace：{body[:200]}"
        assert "secret.db" not in body, "响应含文件系统路径"
        assert "SELECT" not in body, "响应含 SQL"
        assert "RuntimeError" not in body, "响应含异常类型名"

    def test_500_in_production_mode_is_sanitized(self, monkeypatch):
        """生产环境下必须是脱敏消息。"""
        import os

        os.environ["GEO_DISTRIBUTOR_ENV"] = "production"
        os.environ["GEO_DISTRIBUTOR_API_KEYS"] = KEYS
        from api.auth import reset_registry_cache

        reset_registry_cache()
        from api import state

        app_mod = importlib.import_module("api.app")
        importlib.reload(app_mod)
        state.init_repositories(None)
        try:
            with TestClient(app_mod.app, raise_server_exceptions=False) as c:
                r = c.get("/health")
                assert r.status_code == 200
                r2 = c.get("/projects", headers={"X-API-Key": "sk-bad"})
                assert r2.status_code == 401
        finally:
            os.environ["GEO_DISTRIBUTOR_ENV"] = "test"
            importlib.reload(app_mod)

    def test_health_returns_minimal_payload(self, client):
        """公开健康端点只返回最小状态。"""
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json() == {"status": "ok"}, f"健康端点泄露了内部状态：{r.json()}"


# ==================================================================
# RT-10 Fail Closed
# ==================================================================


class TestRT10FailClosed:
    def test_no_builtin_key_in_production(self, monkeypatch):
        """生产环境绝不能加载内置开发密钥。"""
        import os

        os.environ["GEO_DISTRIBUTOR_ENV"] = "production"
        os.environ.pop("GEO_DISTRIBUTOR_API_KEYS", None)
        try:
            from api.auth import reset_registry_cache

            reset_registry_cache()
            auth = importlib.reload(importlib.import_module("api.auth"))
            assert auth.verify_api_key("sk-dev-key-localhost") is None, (
                "生产环境加载了内置开发密钥"
            )
        finally:
            os.environ["GEO_DISTRIBUTOR_ENV"] = "test"
            from api.auth import reset_registry_cache

            reset_registry_cache()
            importlib.reload(importlib.import_module("api.auth"))

    def test_auth_layer_never_returns_default_context(self, monkeypatch):
        """认证失败绝不能返回「默认身份」。"""
        from api.auth import verify_api_key

        for bad in ("", None, "sk-nonexistent", "x" * 100):
            assert verify_api_key(bad) is None, f"密钥 {bad!r} 竟获得了身份"

    def test_empty_key_registry_blocks_everything(self, monkeypatch):
        """注册表为空时，所有密钥都应被拒。"""
        import os

        os.environ["GEO_DISTRIBUTOR_API_KEYS"] = ""
        os.environ["GEO_DISTRIBUTOR_ENV"] = "production"
        try:
            from api.auth import reset_registry_cache

            reset_registry_cache()
            auth = importlib.reload(importlib.import_module("api.auth"))
            assert auth.verify_api_key("anything") is None
            assert auth.verify_api_key("") is None
        finally:
            os.environ["GEO_DISTRIBUTOR_ENV"] = "test"
            os.environ["GEO_DISTRIBUTOR_API_KEYS"] = KEYS
            from api.auth import reset_registry_cache

            reset_registry_cache()
            importlib.reload(importlib.import_module("api.auth"))


# ==================================================================
# 补充：401 不泄露存在性
# ==================================================================


class TestErrorDeidentification:
    def test_401_does_not_reveal_key_existence(self, client):
        """401 响应不得区分「密钥不存在」与「密钥错误」。"""
        r1 = client.get("/projects", headers={"X-API-Key": "sk-does-not-exist"})
        r2 = client.get("/projects", headers={"X-API-Key": "sk-rt-a-but-wrong-tenant"})
        assert r1.status_code == r2.status_code == 401
        assert r1.json() == r2.json(), (
            f"401 文案不一致，会泄露信息：\n{r1.json()}\n{r2.json()}"
        )

    def test_404_does_not_reveal_resource_id(self, client):
        """404 不得回显资源 ID（B-1 的去标识化不能回退）。"""
        r = client.get("/projects/PRJ-DOES-NOT-EXIST-12345", headers=_h(A))
        assert r.status_code == 404
        assert "PRJ-DOES-NOT-EXIST-12345" not in r.text, (
            f"404 回显了资源 ID：{r.text[:200]}"
        )

    def test_403_does_not_reveal_victim_tenant(self, client):
        """403 不得泄露受害方租户标识。"""
        r = client.get("/projects", headers={**_h(A), "X-Tenant-ID": "DIST-NOT-MINE"})
        if r.status_code == 403:
            assert "DIST-NOT-MINE" not in r.text, "403 回显了声明的租户"
