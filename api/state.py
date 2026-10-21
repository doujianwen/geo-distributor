"""Shared state container for the API layer.

All repositories and services are instantiated once at startup and stored here,
so router modules can access them without circular imports.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from geo_distributor.repositories.client_repo import ClientRepository
    from geo_distributor.repositories.project_repo import ProjectRepository
    from geo_distributor.repositories.request_repo import RequestRepository
    from geo_distributor.services.project_service import ProjectService
    from geo_distributor.services.delivery import DeliveryService, ReportService


# --- repositories (initialized at startup) ---
client_repo: "ClientRepository | None" = None
project_repo: "ProjectRepository | None" = None
request_repo: "RequestRepository | None" = None

# --- services (initialized at startup) ---
project_service: "ProjectService | None" = None
delivery_service: "DeliveryService | None" = None
report_service: "ReportService | None" = None

# --- 平台层采集调度服务（Organization / Brand / CollectionProject / Run）---
distribution_service: "DistributionService | None" = None
distribution_service_error: str = ""

# --- sync service (lazy-initialized by /sync router) ---
sync_service = None

# --- persistence backend: "memory" | "sqlite" ---
persistence_backend: str = "memory"
active_db_path: str | None = None

# --- in-memory measurement results store ---
# key: project_id -> list of dicts (collect_result payloads)
#
# Commercial V1 · P0-4：本字典**不再是唯一真源**。SQLite 模式下每次采集都会同时
# 写入 measurements_projection 表；本字典保留为同进程内的热缓存与内存模式回退。
_measurement_results: dict[str, list[dict]] = {}

# --- measurement persistence (SQLite 模式下非 None) ---
measurement_repo = None

# --- Lead Intake Queue（ADR-009 · U2）---
# 投影存储（dict payload，非领域模型）；SQLite 模式下落 leads_intake 表，
# 内存模式下走 InMemoryJSONRepository。用于 Website Lead → HQ 待分配队列。
lead_repo = None
customer_review_repo = None
customer_publication_repo = None
hq_operation_repo = None


def init_repositories(db_path: str | None = None) -> None:
    """Initialize all repositories and services. Call once at app startup.

    Args:
        db_path: 显式指定 SQLite 路径以启用持久化；None 时看环境变量
                 GEO_DISTRIBUTOR_DB，仍未设置则退回内存仓储。
    """
    global client_repo, project_repo, request_repo
    global project_service, delivery_service, report_service
    global distribution_service, distribution_service_error
    global persistence_backend, active_db_path
    global measurement_repo
    global lead_repo
    global customer_review_repo, customer_publication_repo
    global hq_operation_repo

    from geo_distributor.repositories.client_repo import ClientRepository
    from geo_distributor.repositories.project_repo import ProjectRepository
    from geo_distributor.repositories.request_repo import RequestRepository
    from geo_distributor.services.project_service import ProjectService
    from geo_distributor.services.delivery import DeliveryService
    from geo_distributor.guards.idempotency import IdempotencyGuard
    from geo_distributor.guards.state_transition import StateTransitionGuard
    from geo_distributor.services.intake import IntakeService
    from geo_distributor.services.scoping import ScopingService

    from geo_distributor.persistence import (
        resolve_db_path,
        SQLiteClientRepository,
        SQLiteProjectRepository,
        SQLiteRequestRepository,
        SQLiteJSONRepository,
    )
    from geo_distributor.persistence.json_store import InMemoryJSONRepository

    # 显式参数 > 环境变量 GEO_DISTRIBUTOR_DB > None（内存）
    resolved_db = resolve_db_path(db_path)

    if resolved_db:
        # --- SQLite 持久化（跨重启保留）---
        client_repo = SQLiteClientRepository(resolved_db)
        project_repo = SQLiteProjectRepository(resolved_db)
        request_repo = SQLiteRequestRepository(resolved_db)
        # RA-10 加固（2026-10-17）：scope_unique=True → UNIQUE(project, tenant, scope_version)
        # 存储层唯一约束，并发交付竞态原子兜底（见 persistence/sqlite_repository.py）。
        report_repo = SQLiteJSONRepository("reports_projection", resolved_db, scope_unique=True)
        # P0-4：采集结果持久化（跨重启保留），与 reports_projection 同构。
        measurement_repo = SQLiteJSONRepository(
            "measurements_projection", resolved_db, id_key="measurement_id"
        )
        # ADR-009：Lead Intake Queue（跨重启保留 → 满足 §4-12）
        lead_repo = SQLiteJSONRepository("leads_intake", resolved_db, id_key="lead_id")
        customer_review_repo = SQLiteJSONRepository("client_reviews", resolved_db, id_key="review_id")
        customer_publication_repo = SQLiteJSONRepository("client_publications", resolved_db, id_key="publication_id")
        hq_operation_repo = SQLiteJSONRepository("hq_operations", resolved_db, id_key="operation_id")
        persistence_backend = "sqlite"
        active_db_path = resolved_db
    else:
        # --- 内存（默认，行为与 Sprint 0 一致）---
        client_repo = ClientRepository()
        project_repo = ProjectRepository()
        request_repo = RequestRepository()
        report_repo = None
        measurement_repo = None
        lead_repo = InMemoryJSONRepository("lead_id")
        customer_review_repo = InMemoryJSONRepository("review_id")
        customer_publication_repo = InMemoryJSONRepository("publication_id")
        hq_operation_repo = InMemoryJSONRepository("operation_id")
        persistence_backend = "memory"
        active_db_path = None

    idempotency_guard = IdempotencyGuard()
    transition_guard = StateTransitionGuard()
    intake_service = IntakeService()
    scoping_service = ScopingService()

    project_service = ProjectService(
        request_repo=request_repo,
        project_repo=project_repo,
        work_item_repo=None,  # not wired for V2 MVP API
        scope_service=scoping_service,
        intake_service=intake_service,
        transition_guard=transition_guard,
    )
    delivery_service = DeliveryService(report_service=None)
    if report_repo is not None:
        delivery_service.report_service._repository = report_repo
    report_service = delivery_service.report_service

    # 平台层采集调度服务：默认接 geo-collector SQLite。
    # DB 不可用时适配器仍能构造（health_check 返回 False），
    # 采集运行会失败并把原因写进 Run.error_summary——不静默成功。
    try:
        from geo_distributor.adapters.geo_collector_db import GeoCollectorDBAdapter
        from geo_distributor.services.distribution import DistributionService
        from geo_distributor.config import get_geo_collector_root

        _gc_db = os.path.join(get_geo_collector_root(), "geo_collector.db")
        distribution_service = DistributionService(
            adapter=GeoCollectorDBAdapter(db_path=_gc_db, brand="")
        )
    except Exception as exc:  # noqa: BLE001 — 调度服务不可用时不应阻断整个 API
        # 静默失败会让 /distribution 全部 503 且无从排查，故留存原因
        distribution_service = None
        distribution_service_error = f"{type(exc).__name__}: {exc}"
