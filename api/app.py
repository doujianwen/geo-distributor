"""Main FastAPI application — wires all routers and handles startup/shutdown."""

from __future__ import annotations
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routers import clients, projects, measurements, reports, sync, distribution


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


app = FastAPI(
    title="GEO Distributor API",
    description="V2 Web API — B2B GEO 增长与内容运营平台接口",
    version="2.0.0",
    lifespan=lifespan,
)

# CORS: allow frontend dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(clients.router)
app.include_router(projects.router)
app.include_router(measurements.router)
app.include_router(reports.router)
app.include_router(sync.router)
app.include_router(distribution.router)


@app.get("/health")
async def health():
    """Simple health check — ensures repos are initialized then reports status."""
    _ensure_initialized()
    from . import state
    return {
        "status": "ok",
        "clients_repo": state.client_repo is not None,
        "projects_repo": state.project_repo is not None,
        "project_service": state.project_service is not None,
        "delivery_service": state.delivery_service is not None,
        # P0-5: 持久化后端（memory = 重启即失；sqlite = 跨重启保留）
        "persistence": state.persistence_backend,
        "db_path": state.active_db_path,
        # 平台层采集调度服务；未初始化时给出原因，避免 /distribution 全部 503 无从排查
        "distribution_service": state.distribution_service is not None,
        "distribution_service_error": state.distribution_service_error or None,
    }
