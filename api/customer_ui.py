"""Customer-only session BFF, reusing authentication and session lifetimes."""
import json
import os
import re
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from . import ui, customer_service as svc
from .auth import verify_api_key

router = APIRouter(prefix="/ui/customer", tags=["customer-ui"])
ASSETS = Path(__file__).resolve().parent.parent / "ui" / "customer"
ID = r"[A-Za-z0-9_-]{1,100}"
LEGACY_GET_PATH = re.compile(rf"customer/(workspace|reports|reports/{ID}|reviews|projects/{ID}|projects/{ID}/geo)\Z")
LEGACY_POST_PATH = re.compile(rf"customer/reviews/{ID}/respond\Z")

GROWTH_GET = re.compile(rf"customer/growth/(workspace|projects/{ID}|projects/{ID}/resources|projects/{ID}/reports/[0-9]+)\Z")
GROWTH_POST = re.compile(rf"customer/growth/projects/{ID}/[a-z_]+\Z")
OPERATOR_CONTEXT = re.compile(rf"customer/growth/projects/{ID}/operator/context\Z")
OPERATOR_API = re.compile(rf"customer/growth/projects/{ID}/operator/api/[A-Za-z0-9_-]+(?:/[A-Za-z0-9_-]+)*\Z")
OPERATOR_PAGED = re.compile(rf"customer/growth/projects/{ID}/operator/paged/(?:questions|keywords|briefs|monitors|citations|content-gaps|entities|personas|scenarios|clusters)\Z")
OPERATOR_EXPORT = re.compile(rf"customer/growth/projects/{ID}/operator/export/(?:questions|keywords)\Z")
OPERATOR_QUERY = {"type", "priority", "cluster_id", "intent_class", "source", "stage", "sentiment", "question_id", "monitor_id", "engine", "active", "limit", "offset", "months", "surface", "competitor_id", "status", "run_id", "diagnosis_id", "workspace_site_id", "page", "page_size", "q", "ids"}


def demo():
    return os.environ.get("GEO_DISTRIBUTOR_DEMO_ONLY") == "1"


def cookie():
    if os.environ.get("GEO_GROWTH_SANDBOX") == "1":
        return "ggs_growth_lab_customer_sid"
    return "ggs_customer_demo_sid" if demo() else "ggs_customer_sid"


def check_origin(request):
    origin = request.headers.get("origin")
    if origin and origin != f"{request.url.scheme}://{request.url.netloc}":
        raise HTTPException(403, "请求来源无效")


async def session_context(request):
    s = ui._get_session(request.cookies.get(cookie()))
    if not s:
        raise HTTPException(401, "客户会话已失效，请重新登录")
    ctx = verify_api_key(s["api_key"])
    if (not ctx or ctx.role not in {"END_CUSTOMER", "END_CUSTOMER_EDITOR"} or not ctx.client_id
            or (ctx.tenant_id, ctx.client_id, ctx.user_id) != (s["tenant_id"], s.get("client_id"), s.get("actor_id"))):
        ui._drop_session(request.cookies.get(cookie()))
        raise HTTPException(401, "访问权限已变更，请重新登录")
    try:
        c = await svc.bound_client(ctx)
    except HTTPException:
        ui._drop_session(request.cookies.get(cookie()))
        raise HTTPException(401, "客户访问权限已停用")
    return s, ctx, c


@router.get("/info")
async def info():
    from .local_runtime import demo_url
    from .personal_identity import configured
    return {"identity_enabled":configured(),"demo": demo(), "demo_url": demo_url(customer=True) if os.environ.get("GEO_DISTRIBUTOR_LOCAL_DEMO_LINK") == "1" else ""}


@router.post("/session")
async def login(body: ui.LoginIn, request: Request, response: Response):
    check_origin(request)
    allowed, _, retry = ui._login_limiter.check("customer-login:" + (request.client.host if request.client else "unknown"))
    if not allowed:
        raise HTTPException(429, "登录尝试过于频繁，请稍后再试", headers={"Retry-After": str(retry)})
    ctx = verify_api_key(body.api_key)
    if not ctx or ctx.role not in {"END_CUSTOMER", "END_CUSTOMER_EDITOR"} or not ctx.client_id:
        raise HTTPException(401, "访问码无效，请联系服务团队")
    if demo() and (ctx.tenant_id, ctx.client_id) != ("DEMO-GEO", "DEMO-CLI-1"):
        raise HTTPException(401, "无效的演示访问身份")
    await svc.bound_client(ctx)
    old = request.cookies.get(cookie())
    if old:
        ui._drop_session(old)
    sid = ui._create_session(body.api_key, ctx.tenant_id, ctx.role, False)
    ui._SESSIONS[sid].update(client_id=ctx.client_id, actor_id=ctx.user_id)
    response.set_cookie(cookie(), sid, httponly=True, samesite="strict", secure=ui.COOKIE_SECURE,
                        path="/ui/customer", max_age=ui.SESSION_TTL_SECONDS)
    for k, v in ui._ui_headers().items():
        response.headers[k] = v
    return {"ok": True, "is_demo": demo()}


@router.post("/demo-session")
async def demo_login(request: Request, response: Response):
    if not demo():
        raise HTTPException(404, "Not found")
    key = os.environ.get("GEO_DISTRIBUTOR_CUSTOMER_DEMO_KEY", "")
    if not key:
        raise HTTPException(503, "演示暂不可用")
    return await login(ui.LoginIn(api_key=key), request, response)


@router.get("/session")
async def whoami(request: Request):
    try:
        await session_context(request)
    except HTTPException:
        return JSONResponse({"ok": False}, headers=ui._ui_headers())
    return JSONResponse({"ok": True, "is_demo": demo()}, headers=ui._ui_headers())


@router.delete("/session")
async def logout(request: Request):
    check_origin(request)
    current=ui._get_session(request.cookies.get(cookie()))
    if current:
        from .personal_identity import revoke_token
        revoke_token(current['api_key'])
    ui._drop_session(request.cookies.get(cookie()))
    response = JSONResponse({"ok": True}, headers=ui._ui_headers())
    response.delete_cookie(cookie(), path="/ui/customer")
    response.delete_cookie('ggs_person_identity',path='/ui')
    return response


@router.get("/proxy/{path:path}")
@router.post("/proxy/{path:path}")
@router.put("/proxy/{path:path}")
@router.delete("/proxy/{path:path}")
async def proxy(path: str, request: Request):
    s, _, _ = await session_context(request)
    native = bool(OPERATOR_API.fullmatch(path))
    paged = bool(OPERATOR_PAGED.fullmatch(path))
    export = bool(OPERATOR_EXPORT.fullmatch(path))
    allowed = ((LEGACY_GET_PATH.fullmatch(path) or GROWTH_GET.fullmatch(path) or OPERATOR_CONTEXT.fullmatch(path) or native or paged or export) if request.method == "GET" else
               (LEGACY_POST_PATH.fullmatch(path) or GROWTH_POST.fullmatch(path) or native) if request.method == "POST" else native)
    if not allowed:
        raise HTTPException(403, "客户工作区不允许访问此路径")
    pairs = list(request.query_params.multi_items())
    if len(pairs) != len(set(k for k, _ in pairs)):
        raise HTTPException(403, "客户工作区不接受重复范围参数")
    if any((k not in OPERATOR_QUERY or len(v) > 200 or any(c in v for c in "\r\n\x00")) if native or paged or export else
           (k not in {"project_id", "workspace_site_id"} or not re.fullmatch(ID, v)) for k, v in pairs):
        raise HTTPException(403, "客户工作区不接受此范围参数")
    if request.headers.get("x-tenant-id") or request.headers.get("x-client-id"):
        raise HTTPException(403, "客户范围由登录身份确定")
    body = None
    if any(request.headers.get(h) for h in ("If-Match", "If-Match-Object")) and not native:
        raise HTTPException(403, "版本头仅用于专业作业接口")
    if request.method != "GET":
        check_origin(request)
        if demo():
            raise HTTPException(403, "虚拟客户演示为只读")
        try:
            raw = await request.body()
            if len(raw) > 200000:
                raise HTTPException(413, "单次提交内容过大")
            body = json.loads(raw) if raw else {}
        except (ValueError, UnicodeDecodeError):
            raise HTTPException(400, "无效的提交内容")
    import httpx
    from .app import app
    headers = {"X-API-Key": s["api_key"]}
    if request.headers.get("Idempotency-Key"):
        headers["Idempotency-Key"] = request.headers["Idempotency-Key"]
    if native:
        for name in ("If-Match", "If-Match-Object"):
            if request.headers.get(name): headers[name] = request.headers[name]
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://internal") as c:
        r = await c.request(request.method, "/" + path, params=list(request.query_params.multi_items()), json=body, headers=headers)
    return JSONResponse(r.json(), status_code=r.status_code, headers=ui._ui_headers())


@router.get("/", response_class=HTMLResponse)
async def index():
    return HTMLResponse((ASSETS / "index.html").read_text(encoding="utf-8"), headers=ui._ui_headers())


@router.get('/operator-export/{project_id}/{collection}')
async def operator_download(project_id: str, collection: str, request: Request):
    from .operator_service import download_response
    return await download_response(request,project_id,collection,customer=True)


@router.get("/app.js")
async def js():
    return PlainTextResponse((ASSETS / "app.js").read_text(encoding="utf-8"), media_type="application/javascript", headers=ui._ui_headers())


@router.get("/app.css")
async def css():
    return PlainTextResponse((ASSETS / "app.css").read_text(encoding="utf-8"), media_type="text/css", headers=ui._ui_headers())
