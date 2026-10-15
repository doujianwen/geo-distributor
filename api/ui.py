"""Distributor Portal MVP — 渠道商控制台（Commercial V1 · P0-2，Decision B 有限解冻）。

## 定位

本模块是 `docs/01-总体架构与角色边界 §5.B` 定义的 **Distributor Portal（L3）** 的
最小 UI 载体。它**不是**第二套系统：

- 身份：唯一真源仍是 `api/auth.py` 的 `verify_api_key()`（API Key → tenant 绑定）。
  本模块不引入用户表、不引入注册/改密/角色管理。
- 数据：全部读写经**既有** `/clients` `/projects` `/reports` `/measurements` 契约，
  本模块**不持有任何业务主数据**（无第二套 Client/Project/Report 存储）。
- 隔离：租户隔离仍由既有 API 层在服务端强制；本模块只做透传。

## 为什么必须有服务端会话代理（BFF），而不是让浏览器直接拿 API Key

Stage-1 冻结基线 §2 把「WordPress 服务端调用，**不向浏览器暴露 Key**」列为
**已被真实证明的不变量**，§5 又把「密钥进入代码 / HTTP 响应 / 审计库 / Git = 0」
列为受保护不变量。

若让浏览器直接持有 API Key 并调用后端，等于把该不变量降级为「密钥在浏览器」——
这是**不可接受**的。故本模块实现最小 BFF：

    Browser ──cookie(sid)──> /ui/proxy/* ──X-API-Key(服务端注入)──> 既有 API

密钥只存在于服务端内存会话表中，**任何响应体/HTML/JS 都不含密钥**。

## 边界（MVP 明确不做）

依据 `docs/06-Distributor_Portal_MVP §1.2`：
不做 Query Builder / Sampling UI / Measurement Console / Diagnosis Console /
RawResponse 查看 / Evidence 评分 / CRM 全功能 / Billing / Commission Engine。

@package geo-distributor
"""

from __future__ import annotations

import os
import secrets
import time
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from pydantic import BaseModel, Field

from .auth import verify_api_key
from .ratelimit import RateLimiter

router = APIRouter(prefix="/ui", tags=["ui"])

# ------------------------------------------------------------------
# 配置
# ------------------------------------------------------------------

UI_DIR = Path(__file__).resolve().parent.parent / "ui"

SESSION_COOKIE = "ggs_cp_sid"
SESSION_TTL_SECONDS = 8 * 3600      # 绝对上限
SESSION_IDLE_SECONDS = 60 * 60      # 空闲上限

# 代理白名单：只允许既有业务前缀，杜绝 SSRF / 任意端点穿透。
ALLOWED_PREFIXES = ("clients", "projects", "reports", "measurements", "leads")
ALLOWED_METHODS = ("GET", "POST")

# 允许透传到上游的浏览器请求头白名单。
#
# 为什么不直接透传全部请求头：那会把浏览器的 Cookie / Origin / Referer 等
# 一并带到上游，扩大指纹面。这里只放**非凭证的资源范围选择器**。
#
# `X-Client-ID` 为何可放：它标识「要看哪个客户」，不是身份凭证 ——
# 身份仍由服务端注入的 X-API-Key 决定，且上游 `/clients/{id}/portal`
# 会按密钥绑定的租户再校验一次归属（跨租户 → 404）。
# 若不转发它，该端点经 BFF 恒返回 403，等于门户能力不可用。
FORWARD_HEADERS = ("X-Client-ID",)

# UI 页面的 CSP（与 API 的 default-src 'none' 不同，但仍是白名单而非放开）。
UI_CSP = (
    "default-src 'none'; "
    "script-src 'self'; "
    "style-src 'self'; "
    "connect-src 'self'; "
    "img-src 'self' data:; "
    "base-uri 'none'; "
    "form-action 'self'; "
    "frame-ancestors 'none'"
)

# ------------------------------------------------------------------
# 会话表（进程内，不落盘）
# ------------------------------------------------------------------
# 为什么是进程内：Stage-1 §5 明确「不新增 Redis」。单实例部署下进程内即足够；
# 多实例时需外部会话存储，这一点在部署契约中标注，不在此伪造。
# 会话表**只存密钥与身份快照**，不存任何业务数据。

_SESSIONS: dict[str, dict[str, Any]] = {}

# 登录端点专用限流：以**客户端 IP** 为键，且是**预认证**（在校验密钥之前消费令牌）。
#
# 为什么必须另建一个：`api/deps.py::authenticate` 里的全局 limiter 以 **API Key**
# 为键，而登录恰恰是「还不知道正确 Key」的场景 —— 按 Key 限流对暴力枚举完全无效。
# 实测：连续 40 次错误密钥登录，全部 401，无一次 429。
#
# 参数取「够用不扰民」：桶容量 10，长期 20 次/分。真人登录远低于此；
# 脚本化枚举会在 10 次后被挡住并收到 Retry-After（已实测）。
#
# 可用环境变量覆盖（与 `api/ratelimit.py` 的既有做法一致）：验收批跑需要连续
# 登录多次，把阈值调高以免自扰；**默认值保持安全**，不因测试便利而放宽。
def _int_env(name: str, default: int) -> int:
    try:
        v = int((os.environ.get(name, "") or "").strip())
        return v if v > 0 else default
    except ValueError:
        return default


def _bool_env(name: str, default: bool = False) -> bool:
    """读取布尔型环境变量。接受 1/true/yes/on（不区分大小写）。"""
    raw = (os.environ.get(name, "") or "").strip().lower()
    if raw == "":
        return default
    return raw in ("1", "true", "yes", "on")


# U2H 本地加固（2026-10-09）：会话 Cookie 的 Secure 标志改为环境可配置。
#   - 默认 False = **本地 HTTP 测试形态**（本机回环，无 TLS）。
#   - 生产 HTTPS 部署**必须**设置 GEO_DISTRIBUTOR_COOKIE_SECURE=1，
#     否则浏览器可能经明文信道回传会话 Cookie。
#   - 重要边界：把它置 1 **不等于**「生产 TLS 已完成」。域名 / 证书 / HSTS /
#     反代 TLS 终止仍需独立完成并通过 §6 安全 Gate；本开关只是让生产就绪
#     不再需要改代码。
COOKIE_SECURE = _bool_env("GEO_DISTRIBUTOR_COOKIE_SECURE", False)


_LOGIN_RATE_PER_MIN = _int_env("GEO_DISTRIBUTOR_LOGIN_RATE_PER_MIN", 20)
_LOGIN_BURST = _int_env("GEO_DISTRIBUTOR_LOGIN_BURST", 10)
_login_limiter = RateLimiter(rate_per_min=_LOGIN_RATE_PER_MIN, burst=_LOGIN_BURST)


def _purge_expired(now: float) -> None:
    for sid in list(_SESSIONS.keys()):
        s = _SESSIONS[sid]
        if now - s["created"] > SESSION_TTL_SECONDS or now - s["seen"] > SESSION_IDLE_SECONDS:
            _SESSIONS.pop(sid, None)


def _create_session(api_key: str, tenant_id: str, role: str, is_hq: bool) -> str:
    now = time.time()
    _purge_expired(now)
    sid = secrets.token_urlsafe(32)
    _SESSIONS[sid] = {
        "api_key": api_key,
        "tenant_id": tenant_id,
        "role": role,
        "is_hq": is_hq,
        "created": now,
        "seen": now,
    }
    return sid


def _get_session(sid: Optional[str]) -> Optional[dict[str, Any]]:
    if not sid:
        return None
    now = time.time()
    _purge_expired(now)
    # 常数时间查找：逐项 compare_digest，避免时序侧信道暴露会话 id 前缀。
    matched: Optional[str] = None
    for candidate in _SESSIONS:
        if secrets.compare_digest(candidate, sid):
            matched = candidate
    if matched is None:
        return None
    sess = _SESSIONS[matched]
    sess["seen"] = now
    return sess


def _drop_session(sid: Optional[str]) -> None:
    if sid:
        _SESSIONS.pop(sid, None)


def active_session_count() -> int:
    """仅供测试/运维探活，不暴露任何会话内容。"""
    _purge_expired(time.time())
    return len(_SESSIONS)


# ------------------------------------------------------------------
# Schemas
# ------------------------------------------------------------------

class LoginIn(BaseModel):
    api_key: str = Field(..., min_length=1, max_length=512)


class SessionOut(BaseModel):
    # 未登录时返回 ok=False 且其余字段留空——不含任何身份信息。
    ok: bool
    tenant_id: str = ""
    role: str = ""
    can_write: bool = False
    is_hq: bool = False


# ------------------------------------------------------------------
# 会话端点
# ------------------------------------------------------------------

def _ui_headers() -> dict[str, str]:
    return {
        "Content-Security-Policy": UI_CSP,
        "Cache-Control": "no-store",
        "X-Content-Type-Options": "nosniff",
    }


@router.post("/session", response_model=SessionOut)
async def ui_login(payload: LoginIn, request: Request, response: Response) -> SessionOut:
    """以 API Key 换取服务端会话。**响应体永不回显密钥。**"""
    # 预认证 IP 限流：必须在 verify_api_key 之前，否则无效密钥会绕过限流。
    client_ip = request.client.host if request.client else "unknown"
    allowed, _remaining, retry_after = _login_limiter.check(f"login:{client_ip}")
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail="Too many login attempts",
            headers={"Retry-After": str(retry_after)},
        )

    ctx = verify_api_key(payload.api_key)
    if ctx is None:
        # 不区分「缺失」与「无效」，避免探测。
        raise HTTPException(status_code=401, detail="Invalid API key")

    sid = _create_session(payload.api_key, ctx.tenant_id, ctx.role, ctx.is_hq)
    response.set_cookie(
        SESSION_COOKIE,
        sid,
        httponly=True,
        samesite="strict",
        secure=COOKIE_SECURE,  # 本地默认 False；生产 HTTPS 置 GEO_DISTRIBUTOR_COOKIE_SECURE=1
        path="/ui",
        max_age=SESSION_TTL_SECONDS,
    )
    for k, v in _ui_headers().items():
        response.headers[k] = v
    return SessionOut(
        ok=True,
        tenant_id=ctx.tenant_id,
        role=ctx.role,
        can_write=ctx.can_write(),
        is_hq=ctx.is_hq,
    )


@router.get("/session", response_model=SessionOut)
async def ui_whoami(request: Request, response: Response) -> SessionOut:
    sess = _get_session(request.cookies.get(SESSION_COOKIE))
    for k, v in _ui_headers().items():
        response.headers[k] = v
    if sess is None:
        # 未登录返回 200 + ok=false，而非 401。
        # 理由：页面加载时的会话探活是**预期路径**（首次访问必然未登录），
        # 用 401 会被浏览器记为 Failed resource 并污染控制台，掩盖真实错误。
        # 安全性不变——此处不回传任何身份字段；**业务端点仍然强制 401**。
        return SessionOut(ok=False)
    return SessionOut(
        ok=True,
        tenant_id=sess["tenant_id"],
        role=sess["role"],
        can_write=sess["role"] in {
            "DISTRIBUTOR_ADMIN", "DISTRIBUTOR_USER", "HQ_TECHNICAL", "HQ_MANAGEMENT",
        },
        is_hq=sess["is_hq"],
    )


@router.delete("/session")
async def ui_logout(request: Request, response: Response) -> JSONResponse:
    _drop_session(request.cookies.get(SESSION_COOKIE))
    response.delete_cookie(SESSION_COOKIE, path="/ui")
    return JSONResponse({"ok": True}, headers=_ui_headers())


# ------------------------------------------------------------------
# 代理端点
# ------------------------------------------------------------------

def _path_allowed(path: str) -> bool:
    if not path or path.startswith("/") or ".." in path or "//" in path:
        return False
    head = path.split("/", 1)[0]
    return head in ALLOWED_PREFIXES


@router.get("/proxy/{path:path}", name="ui_proxy_get")
@router.post("/proxy/{path:path}", name="ui_proxy_post")
async def ui_proxy(path: str, request: Request) -> Response:
    """服务端注入 API Key 后转发到既有 API。密钥不出服务端。"""
    sess = _get_session(request.cookies.get(SESSION_COOKIE))
    if sess is None:
        raise HTTPException(status_code=401, detail="Not authenticated")

    if request.method not in ALLOWED_METHODS:
        raise HTTPException(status_code=405, detail="Method not allowed")
    if not _path_allowed(path):
        raise HTTPException(status_code=403, detail="Path not allowed")

    body: Any = None
    if request.method == "POST":
        raw = await request.body()
        if raw:
            import json as _json

            try:
                body = _json.loads(raw.decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                raise HTTPException(status_code=400, detail="Invalid JSON body")

    # 惰性导入，避免与 api.app 的循环导入。
    import httpx

    from .app import app as _asgi_app

    headers = {"X-API-Key": sess["api_key"], "Accept": "application/json"}
    # 仅转发白名单内的业务头（见 FORWARD_HEADERS）；浏览器 Cookie / Origin /
    # Referer / Authorization 一律不转发，避免扩大上游指纹面与越权面。
    for name in FORWARD_HEADERS:
        val = request.headers.get(name)
        if val:
            headers[name] = val
    transport = httpx.ASGITransport(app=_asgi_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://internal") as client:
        upstream = await client.request(
            request.method,
            "/" + path,
            params=dict(request.query_params),
            json=body,
            headers=headers,
        )

    # 只回传状态码 + JSON 体，不回传任何上游响应头（避免泄漏 Server/CSP 等指纹）。
    try:
        payload = upstream.json()
    except ValueError:
        payload = {"detail": "Upstream returned non-JSON"}

    return JSONResponse(
        status_code=upstream.status_code,
        content=payload,
        headers=_ui_headers(),
    )


# ------------------------------------------------------------------
# 静态资源（显式路由，不用 Mount，避免与 /ui/session 的匹配顺序问题）
# ------------------------------------------------------------------

def _read_asset(name: str) -> Optional[str]:
    p = (UI_DIR / name).resolve()
    try:
        p.relative_to(UI_DIR.resolve())
    except ValueError:
        return None
    if not p.is_file():
        return None
    return p.read_text(encoding="utf-8")


@router.get("/", response_class=HTMLResponse)
async def ui_index() -> HTMLResponse:
    html = _read_asset("index.html")
    if html is None:
        raise HTTPException(status_code=404, detail="UI not built")
    return HTMLResponse(html, headers=_ui_headers())


@router.get("/app.js")
async def ui_js() -> PlainTextResponse:
    js = _read_asset("app.js")
    if js is None:
        raise HTTPException(status_code=404, detail="UI asset missing")
    return PlainTextResponse(
        js, media_type="application/javascript; charset=utf-8", headers=_ui_headers()
    )


@router.get("/app.css")
async def ui_css() -> PlainTextResponse:
    css = _read_asset("app.css")
    if css is None:
        raise HTTPException(status_code=404, detail="UI asset missing")
    return PlainTextResponse(css, media_type="text/css; charset=utf-8", headers=_ui_headers())
