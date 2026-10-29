"""待开通页（/ui/account/）的渲染回归。

2026-10-28 修了两个只在生产才暴露的缺陷，这里各钉一条断言：

1. **按钮不可见**：页面只引了 `app.css`，而 `app.css` 的 `--brand` 引用了
   `brand-tokens.css` 里的 `--brand-primary`。缺了它 `.btn` 的 `background`
   计算值失效 → 透明底 + `color:white` → 白字落在白卡片上，肉眼几乎看不见。
2. **返回链接跳错域**：原来硬编码 `http://geo-growth.local/portal/`，
   在生产点「返回」会跳到不存在的本地域名。改为按请求推导（或 GEO_PUBLIC_SITE_URL 覆盖）。

这两条都属于「本地看着正常、上线才坏」，所以必须由测试守住，而不是靠肉眼验收。
"""
from __future__ import annotations

import asyncio
import hashlib
import os
import time

import pytest
from starlette.requests import Request

from api import personal_identity as identity


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


@pytest.fixture()
def identity_env(tmp_path, monkeypatch):
    monkeypatch.setenv("GEO_IDENTITY_DB", str(tmp_path / "identity.db"))
    monkeypatch.setenv("GEO_IDENTITY_SECRET", "account-page-test-secret-000000000000")
    monkeypatch.setenv("GEO_IDENTITY_ISSUER", "https://www.example.com")
    monkeypatch.delenv("GEO_PUBLIC_SITE_URL", raising=False)
    return tmp_path


def _seed(token: str, status: str) -> None:
    subject = "wp:" + _digest(os.environ["GEO_IDENTITY_ISSUER"])[:20] + ":42"
    conn = identity.connect()
    try:
        conn.execute("INSERT OR IGNORE INTO identity_people VALUES(?,?,?,?)",
                     (subject, os.environ["GEO_IDENTITY_ISSUER"], "42", int(time.time())))
        conn.execute("INSERT OR REPLACE INTO identity_requests VALUES(?,?,?)",
                     (subject, status, int(time.time())))
        conn.execute("INSERT OR REPLACE INTO identity_sessions VALUES(?,?,?)",
                     (_digest(token), subject, int(time.time()) + 600))
        conn.commit()
    finally:
        conn.close()


def _request(token: str, host: str = "www.example.com", proto: str = "https") -> Request:
    scope = {
        "type": "http",
        "method": "GET",
        "scheme": "http",
        "path": "/ui/account/",
        "query_string": b"",
        "headers": [
            (b"host", host.encode()),
            (b"x-forwarded-proto", proto.encode()),
            (b"x-forwarded-host", host.encode()),
            (b"cookie", f"ggs_person_identity={token}".encode()),
        ],
    }
    return Request(scope)


def _render(token: str, **kwargs) -> str:
    response = asyncio.run(identity.account_status(_request(token, **kwargs)))
    return response.body.decode()


def test_brand_tokens_loaded_before_app_css(identity_env):
    """缺 brand-tokens.css 会让主按钮白字白底。"""
    token = "person_" + "a" * 40
    _seed(token, "pending")
    html = _render(token)
    assert "/ui/brand-tokens.css" in html, "待开通页必须引入 brand-tokens.css"
    assert html.index("/ui/brand-tokens.css") < html.index("/ui/app.css"), \
        "brand-tokens.css 必须排在 app.css 之前，否则 CSS 变量未定义"


def test_no_hardcoded_local_domain(identity_env):
    token = "person_" + "b" * 40
    _seed(token, "pending")
    html = _render(token)
    assert "geo-growth.local" not in html, "不得硬编码本地域名"
    assert "https://www.example.com/" in html, "返回链接应指向当前站点"


def test_public_site_url_override(identity_env, monkeypatch):
    monkeypatch.setenv("GEO_PUBLIC_SITE_URL", "https://portal.example.org/")
    token = "person_" + "c" * 40
    _seed(token, "pending")
    html = _render(token)
    assert "https://portal.example.org/" in html
    assert "portal.example.org//" not in html, "覆盖值结尾斜杠应被规范化"


def test_approved_offers_reentry_action(identity_env):
    """已开通时应直接给出重新进入的动作，而不是让用户自己猜。"""
    token = "person_" + "d" * 40
    _seed(token, "approved")
    html = _render(token)
    assert "geo_workspace_login=1" in html
    assert "重新进入工作区" in html


def test_pending_has_no_reentry_loop(identity_env):
    """待开通时不应给「重新进入」——那只会绕回同一页。"""
    token = "person_" + "e" * 40
    _seed(token, "pending")
    html = _render(token)
    assert "geo_workspace_login=1" not in html
    assert "返回官网首页" in html


def test_missing_session_is_rejected(identity_env):
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as denied:
        asyncio.run(identity.account_status(_request("person_" + "f" * 40)))
    assert denied.value.status_code == 401
