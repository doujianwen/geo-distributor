"""B-5 CORS 配置测试（RED-GATE）。

背景：Phase 1-1 Batch 1A 修复 `allow_origins=["*"] + allow_credentials=True`
这一浏览器必拒的危险组合。本测试锁定修复后的契约。

运行方式：
    pytest tests/test_cors_config.py -v
"""

from __future__ import annotations

import importlib
import os

import pytest
from fastapi.middleware.cors import CORSMiddleware


def _cors_options() -> dict:
    """从 app 实例上取出实际生效的 CORS 配置。"""
    app_mod = importlib.import_module("api.app")

    # 每次重新构建 app，确保读取当前源码配置
    importlib.reload(app_mod)

    for mw in app_mod.app.user_middleware:
        if mw.cls is CORSMiddleware:
            return dict(mw.kwargs)
    raise AssertionError("CORSMiddleware 未注册")


class TestCORSNotWildcard:
    """核心安全门禁：不允许通配 origin。"""

    def test_allow_origins_is_not_wildcard(self):
        opts = _cors_options()
        assert opts.get("allow_origins") != ["*"], (
            "allow_origins仍为 ['*'] — 任意站点可跨域读取 API 响应"
        )

    def test_allow_origins_not_contain_star_among_others(self):
        """混合列表中的 '*' 同样危险（浏览器会拒绝该组合）。"""
        opts = _cors_options()
        origins = opts.get("allow_origins") or []
        assert "*" not in origins, f"allow_origins 含 '*': {origins}"

    def test_default_origins_is_empty(self):
        """无显式配置时必须零跨域（本地 127.0.0.1 服务无浏览器消费者）。"""
        opts = _cors_options()
        assert opts.get("allow_origins") == [], (
            f"默认应为空列表，实际 {opts.get('allow_origins')!r}；"
            "如需开放请设GEO_DISTRIBUTOR_CORS_ORIGINS"
        )


class TestCORSNoCredentialLeak:
    """allow_credentials 与通配 origin 不共存。"""

    def test_allow_credentials_false_by_default(self):
        opts = _cors_options()
        assert opts.get("allow_credentials") is False, (
            "allow_credentials 应默认关闭 — 本系统无Cookie 会话认证"
        )

    def test_wildcard_and_credentials_never_combined(self):
        """即使未来配置了 origins，也不得与 credentials 同时放开。"""
        opts = _cors_options()
        origins = opts.get("allow_origins") or []
        if opts.get("allow_credentials"):
            pytest.skip("allow_credentials 已被显式配置（需人工审查）")
        assert "*" not in origins


class TestCORSExplicitAllowlist:
    """显式白名单路径可用。"""

    def test_env_var_allowlist_is_read(self, monkeypatch):
        monkeypatch.setenv(
            "GEO_DISTRIBUTOR_CORS_ORIGINS",
            "http://localhost:3000,https://app.example.com",
        )
        opts = _cors_options()
        assert opts["allow_origins"] == [
            "http://localhost:3000",
            "https://app.example.com",
        ], f"白名单解析结果不符: {opts['allow_origins']}"

    def test_env_var_blank_falls_back_to_empty(self, monkeypatch):
        monkeypatch.setenv("GEO_DISTRIBUTOR_CORS_ORIGINS", "  ")
        opts = _cors_options()
        assert opts["allow_origins"] == []

    def test_env_var_unset_yields_empty(self, monkeypatch):
        monkeypatch.delenv("GEO_DISTRIBUTOR_CORS_ORIGINS", raising=False)
        opts = _cors_options()
        assert opts["allow_origins"] == []


class TestCORSBehavior:
    """行为级验证：真实发请求看响应头。"""

    def test_disallowed_origin_gets_no_cors_header(self, monkeypatch):
        from fastapi.testclient import TestClient

        monkeypatch.setenv("GEO_DISTRIBUTOR_CORS_ORIGINS", "http://localhost:3000")
        app_mod = importlib.import_module("api.app")
        importlib.reload(app_mod)

        with TestClient(app_mod.app) as c:
            r = c.get("/health", headers={"Origin": "https://evil.example"})
        assert "access-control-allow-origin" not in {
            k.lower() for k in r.headers
        }, f"恶意 origin 竟收到 CORS 头: {dict(r.headers)}"

    def test_allowed_origin_gets_cors_header(self, monkeypatch):
        from fastapi.testclient import TestClient

        monkeypatch.setenv("GEO_DISTRIBUTOR_CORS_ORIGINS", "http://localhost:3000")
        app_mod = importlib.import_module("api.app")
        importlib.reload(app_mod)

        with TestClient(app_mod.app) as c:
            r = c.get("/health", headers={"Origin": "http://localhost:3000"})
        assert r.headers.get("access-control-allow-origin") == "http://localhost:3000"

    def test_preflight_from_allowed_origin_passes(self, monkeypatch):
        from fastapi.testclient import TestClient

        monkeypatch.setenv("GEO_DISTRIBUTOR_CORS_ORIGINS", "http://localhost:3000")
        app_mod = importlib.import_module("api.app")
        importlib.reload(app_mod)

        with TestClient(app_mod.app) as c:
            r = c.options(
                "/health",
                headers={
                    "Origin": "http://localhost:3000",
                    "Access-Control-Request-Method": "GET",
                },
            )
        assert r.status_code == 200
        assert r.headers.get("access-control-allow-origin") == "http://localhost:3000"
