"""Main FastAPI application — wires all routers and handles startup/shutdown."""

from __future__ import annotations
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routers import clients, projects, measurements, reports, sync, distribution, leads, requests, hq
from . import ui as ui_module
from . import customer_ui
from .routers import customer

# CORS 允许来源白名单。
#
# B-5 安全修复：原先为 allow_origins=["*"] + allow_credentials=True。
# 该组合会被浏览器直接拒绝，且一旦被接受即允许任意站点跨域读取 API 响应。
#
# 现改为显式白名单，依据项目实际运行方式：
#   - start_api.sh 将服务绑定 127.0.0.1:8765，无浏览器前端消费者
#     （同进程 / 服务端调用不受 CORS 约束）
#   - 需要开放时显式设置 GEO_DISTRIBUTOR_CORS_ORIGINS，逗号分隔多个 origin
CORS_ORIGINS_ENV = "GEO_DISTRIBUTOR_CORS_ORIGINS"


def _cors_origins() -> list[str]:
    raw = os.environ.get(CORS_ORIGINS_ENV, "")
    return [item.strip() for item in raw.split(",") if item.strip()]


def _ensure_initialized() -> None:
    """Lazy init helper — safe to call multiple times."""
    from . import state
    if state.project_service is None:
        state.init_repositories()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: initialize repositories and services."""
    _ensure_initialized()
    yield
    # Shutdown: cleanup if needed


# 生产环境默认关闭 /docs 与 /openapi.json。
# 理由：这两个端点公开了完整 API 结构（端点、参数、schema），
# 对远程商业部署是不必要的攻击面信息。
# 需要排查问题时可设 GEO_DISTRIBUTOR_EXPOSE_DOCS=1 临时开启。
_EXPOSE_DOCS = (os.environ.get("GEO_DISTRIBUTOR_EXPOSE_DOCS", "") or "").strip() in {
    "1", "true", "yes", "on",
}

app = FastAPI(
    title="GEO Distributor API",
    description="V2 Web API — B2B GEO 增长与内容运营平台接口",
    version="2.0.0",
    lifespan=lifespan,
    docs_url="/docs" if _EXPOSE_DOCS else None,
    redoc_url="/redoc" if _EXPOSE_DOCS else None,
    openapi_url="/openapi.json" if _EXPOSE_DOCS else None,
)

# ------------------------------------------------------------
# 审计中间件（写操作自动留痕）
# ------------------------------------------------------------
# 为什么用中间件而不是在每个端点里手写 record_audit：
# 手写必然漏端点，而且漏了没人知道。中间件是**默认全覆盖**。
#
# 范围：只记 4xx/5xx 之外的写操作（POST/PUT/PATCH/DELETE）。
# 读操作不记 —— 量级差两个数量级，全记会撑爆存储；
# 真正的「谁读了别人的数据」由 B-1 的租户隔离在源头挡住。
#
# 审计失败绝不阻断响应（record_audit 内部吞掉所有异常）。

_WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
_READ_METHODS = {"GET", "HEAD", "OPTIONS"}


@app.middleware("http")
async def security_headers_middleware(request, call_next):
    """为所有响应加安全头，并移除可去掉的实现指纹。

    为什么应用层也要加：nginx 配置可能遗漏、被覆盖或路径不匹配。
    应用层加一份，保证「无论经过哪条路径都带这些头」。

    注意：`Server` 头由 uvicorn 在 ASGI 层**之外**注入，中间件删不掉，
    必须由服务器层关闭（start_api_prod.sh 的 --no-server-header）。
    """
    if os.environ.get("GEO_DISTRIBUTOR_DEMO_ONLY") == "1" and request.method not in {"GET", "HEAD", "OPTIONS"} and request.url.path not in {"/ui/demo-session", "/ui/session", "/ui/customer/demo-session", "/ui/customer/session", "/ui/hq/demo-session", "/ui/hq/session"}:
        from fastapi.responses import JSONResponse
        return JSONResponse({"detail": "虚拟演示工作区为只读"}, status_code=403, headers={"Cache-Control": "no-store"})
    response = await call_next(request)

    for header in ("server", "x-powered-by"):
        if header in response.headers:
            del response.headers[header]

    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    # GEO Distribution API 不加载任何页面，CSP 可极严
    response.headers.setdefault(
        "Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'"
    )
    return response


@app.exception_handler(Exception)
async def unhandled_exception_handler(request, exc):
    """未捕获异常：生产环境不返回任何内部细节。

    stack trace / 文件路径 / SQL / 对象 repr 泄漏出去等于给攻击者地图。
    完整信息只进服务端日志。
    """
    import logging as _logging

    from fastapi.responses import JSONResponse

    _logging.getLogger("api.app").exception(
        "Unhandled exception on %s %s: %s",
        request.method, request.url.path, exc, exc_info=True,
    )

    # 即使是 dev/test 也不返回细节 —— 排障看日志，不看响应体。
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
        headers={"Cache-Control": "no-store"},
    )


@app.middleware("http")
async def audit_middleware(request, call_next):
    """写操作全记；读操作仅在被拒绝时记。

    审计范围经过刻意收窄：
    - 所有写操作（POST/PUT/PATCH/DELETE）—— 商业动作必须可追溯
    - 被拒绝的读操作 —— 认证失败 / 越权/ 跨租户尝试是攻击信号，
      不记就发现不了爆破与探测
    - 成功的读操作不记 —— 量级差两个数量级，且已被 B-1 限定在本租户内
    """
    is_write = request.method in _WRITE_METHODS
    is_read = request.method in _READ_METHODS

    # /health 是公开探活端点，高频轮询会淹没日志
    if request.url.path == "/health":
        return await call_next(request)

    # /ui 是 Distributor Portal 静态与会话端点（Commercial V1 · P0-2）。
    # 它们不携带 X-API-Key（会话 cookie 在服务端换取密钥），若照常记录会写入
    # 大量 tenant 为空的噪声条目。真正的业务动作由 /ui/proxy 转发时携带密钥，
    # 由下游 API 正常留痕 —— 审计覆盖度不受影响。
    if request.url.path == "/ui" or request.url.path.startswith("/ui/"):
        return await call_next(request)

    from .audit import record_audit
    from .auth import verify_api_key

    api_key = request.headers.get("X-API-Key")
    ctx = verify_api_key(api_key) if api_key else None
    # 认证失败时没有 ctx，但仍须留痕：tenant 用**声明值**（可能是伪造的），
    # 由 outcome=DENIED 标记。审计要能回答「谁在尝试越权」。
    declared_tenant = request.headers.get("X-Tenant-ID")
    ip = request.client.host if request.client else None

    try:
        response = await call_next(request)
    except Exception as exc:
        # 未捕获异常：记录失败操作后原样抛出
        record_audit(
            action=request.method,
            resource_type=request.url.path,
            tenant_id=getattr(ctx, "tenant_id", None) or declared_tenant,
            user_id=getattr(ctx, "user_id", None),
            role=getattr(ctx, "role", None),
            ip_address=ip,
            outcome="ERROR",
            reason=type(exc).__name__,
        )
        raise

    if response.status_code < 400:
        outcome = "OK"
    elif response.status_code in (401, 403):
        outcome = "DENIED"
    else:
        outcome = "ERROR"

    record_audit(
        action=request.method,
        resource_type=request.url.path,
        tenant_id=getattr(ctx, "tenant_id", None),
        user_id=getattr(ctx, "user_id", None),
        role=getattr(ctx, "role", None),
        ip_address=ip,
        outcome=outcome,
        reason="" if response.status_code < 400 else f"HTTP {response.status_code}",
    )
    return response


# ------------------------------------------------------------
# 审计中间件（写操作自动留痕）
# ------------------------------------------------------------
# 为什么用中间件而不是在每个端点里手写 record_audit：
# 手写必然漏端点，而且漏了没人知道。中间件是**默认全覆盖**。
#
# 范围：只记 4xx/5xx 之外的写操作（POST/PUT/PATCH/DELETE）。
# 读操作不记 —— 量级差两个数量级，全记会撑爆存储；
# 真正的「谁读了别人的数据」由 B-1 的租户隔离在源头挡住。
#
# 审计失败绝不阻断响应（record_audit 内部吞掉所有异常）。





# CORS：默认零跨域（依据见 _cors_origins 上方注释）
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(hq.router)
app.include_router(clients.router)
app.include_router(requests.router)
app.include_router(projects.router)
app.include_router(measurements.router)
app.include_router(reports.router)
app.include_router(sync.router)
app.include_router(distribution.router)

# Lead Intake Queue（ADR-009 · U2 Lead Integration Closure）——
# Website Lead → HQ 待分配队列 → 分配 → 转 Client/ServiceRequest/Project。
# 必须在业务 router 之后注册；路径前缀 /leads 与既有前缀不冲突。
app.include_router(leads.router)

# Distributor Portal MVP（Commercial V1 · P0-2）—— 渠道商控制台。
# 必须在业务 router 之后注册，但其内部路径 (/ui/*) 与业务前缀不冲突。
app.include_router(ui_module.router)
app.include_router(customer.router)
app.include_router(customer.management)
app.include_router(customer_ui.router)


@app.get("/health")
async def health():
    """最小健康检查 — 仅供反向代理 / 负载均衡探活。

    ## 为什么必须最小化

    /health 是**公开**端点（无认证），因此任何返回值都是公开信息。
    原实现暴露了 `db_path`（文件系统路径）、`persistence`（实现细节）、
    各 service 内部状态与错误消息 —— 这些对攻击者定位部署环境、
    判断技术栈、判断内部组件状态都有价值。

    公开端点的返回内容应严格遵循「只回答问题所需的最少信息」：
    负载均衡只需要知道「进程活着吗」，不需要知道「用什么数据库」。

    详细诊断请看服务端日志，或显式开启 `/openapi.json`（受反代保护）。
    """
    _ensure_initialized()
    return {"status": "ok"}

from .routers import growth
from .routers import operator, workspace_access, growth_resources
from . import personal_identity
app.include_router(operator.router)
app.include_router(workspace_access.router)
app.include_router(growth_resources.router)
app.include_router(personal_identity.router)
app.include_router(growth.router)

from . import growth_lab
app.include_router(growth_lab.router)
