"""SQLite 仓储实现（P0-5）。

与 InMemoryRepository 接口对齐，可无缝替换。
表结构统一为 (id, tenant_id, payload, updated_at)，实体以 JSON 存储。
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
from datetime import datetime
from typing import Any, List, Optional, Type

from ..repositories.base import NotFoundError

_lock = threading.Lock()

_ENV_DB = "GEO_DISTRIBUTOR_DB"


def get_default_db_path() -> str:
    """默认 SQLite 路径：<project_root>/data/geo_distributor.db"""
    from ..config import get_project_root
    return os.path.join(get_project_root(), "data", "geo_distributor.db")


def is_persistence_enabled() -> bool:
    """是否启用持久化（由环境变量 GEO_DISTRIBUTOR_DB 决定）。"""
    return bool(os.environ.get(_ENV_DB))


def resolve_db_path(db_path: Optional[str] = None) -> Optional[str]:
    """解析实际使用的 SQLite 路径；返回 None 表示走内存仓储。

    优先级：显式参数 > 环境变量 > None（内存）
    环境变量若是 `1` / `true` 这类开关值而非路径，则落到默认路径。

    ⚠️ 修复记录：早期实现里环境变量存在时直接用 get_default_db_path()，
    导致用户指定的 GEO_DISTRIBUTOR_DB=/path/x.db 被静默忽略。
    """
    if db_path:
        return db_path
    env = os.environ.get(_ENV_DB)
    if not env:
        return None
    if env.lower() in ("1", "true", "yes", "on"):
        return get_default_db_path()
    return env


class SQLiteRepository:
    """通用 SQLite 仓储。

    子类只需声明 table / id_field / entity_cls，并实现各自的
    租户隔离语义（各 repo 对"越权"的处理不同：有的返回 None，有的抛异常）。
    """

    table: str = ""
    id_field: str = ""
    tenant_field: str = "tenant_id"
    entity_cls: Type = None  # type: ignore
    entity_name: str = ""

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or os.environ.get(_ENV_DB) or get_default_db_path()
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._init_db()

    # ------------------------------------------------------------------
    # 基础设施
    # ------------------------------------------------------------------

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with _lock:
            conn = self._connect()
            try:
                conn.execute(
                    f"""CREATE TABLE IF NOT EXISTS {self.table} (
                        id TEXT PRIMARY KEY,
                        tenant_id TEXT NOT NULL,
                        payload TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    )"""
                )
                conn.execute(
                    f"CREATE INDEX IF NOT EXISTS idx_{self.table}_tenant "
                    f"ON {self.table}(tenant_id)"
                )
                conn.commit()
            finally:
                conn.close()

    # ------------------------------------------------------------------
    # 序列化
    # ------------------------------------------------------------------

    def _to_payload(self, entity: Any) -> str:
        d = entity.to_dict() if hasattr(entity, "to_dict") else dict(entity.__dict__)
        return json.dumps(d, ensure_ascii=False)

    def _from_payload(self, payload: str) -> Any:
        d = json.loads(payload)
        if hasattr(self.entity_cls, "from_dict"):
            return self.entity_cls.from_dict(d)
        return self.entity_cls(**d)

    # ------------------------------------------------------------------
    # 基础 CRUD（子类复用）
    # ------------------------------------------------------------------

    async def _raw_get(self, entity_id: str) -> Optional[Any]:
        conn = self._connect()
        try:
            cur = conn.execute(
                f"SELECT payload FROM {self.table} WHERE id = ?", (entity_id,)
            )
            row = cur.fetchone()
            if not row:
                return None
            return self._from_payload(row["payload"])
        finally:
            conn.close()

    async def _raw_upsert(self, entity: Any, exists_ok: bool = True) -> Any:
        entity_id = getattr(entity, self.id_field)
        tenant_id = getattr(entity, self.tenant_field, "")
        payload = self._to_payload(entity)
        now = datetime.now().isoformat()

        with _lock:
            conn = self._connect()
            try:
                if not exists_ok:
                    cur = conn.execute(
                        f"SELECT 1 FROM {self.table} WHERE id = ?", (entity_id,)
                    )
                    if cur.fetchone():
                        raise ValueError(
                            f"{self.entity_name or self.table} {entity_id} already exists"
                        )
                conn.execute(
                    f"""INSERT INTO {self.table} (id, tenant_id, payload, updated_at)
                        VALUES (?, ?, ?, ?)
                        ON CONFLICT(id) DO UPDATE SET
                            tenant_id=excluded.tenant_id,
                            payload=excluded.payload,
                            updated_at=excluded.updated_at""",
                    (entity_id, tenant_id, payload, now),
                )
                conn.commit()
            finally:
                conn.close()
        return entity

    async def _raw_delete(self, entity_id: str) -> bool:
        with _lock:
            conn = self._connect()
            try:
                cur = conn.execute(
                    f"DELETE FROM {self.table} WHERE id = ?", (entity_id,)
                )
                conn.commit()
                return cur.rowcount > 0
            finally:
                conn.close()

    async def _raw_find_by_tenant(self, tenant_id: str) -> List[Any]:
        conn = self._connect()
        try:
            cur = conn.execute(
                f"SELECT payload FROM {self.table} WHERE tenant_id = ? ORDER BY updated_at DESC",
                (tenant_id,),
            )
            return [self._from_payload(r["payload"]) for r in cur.fetchall()]
        finally:
            conn.close()

    async def exists(self, entity_id: str) -> bool:
        return await self._raw_get(entity_id) is not None

    async def delete(self, entity_id: str) -> bool:
        return await self._raw_delete(entity_id)


# ======================================================================
# JSON payload repository for existing service projections
# ======================================================================

class SQLiteJSONRepository:
    """Persistent store for service projections; no new domain entity."""

    def __init__(self, table: str, db_path: Optional[str] = None, id_key: str = "report_id",
                 scope_unique: bool = False):
        """id_key：payload 中充当主键的字段名。

        默认 "report_id" 保持既有 reports_projection 行为不变；
        measurements_projection 传入 "measurement_id"。

        scope_unique（RA-10 加固 · 2026-10-17）：为 True 时给表增加 scope_version 列
        并建立 UNIQUE(project_id, tenant_id, scope_version) 唯一索引，使交付幂等
        「查后再插」的并发竞态在存储层被原子约束兜底。仅 reports_projection 启用；
        measurements_projection / leads_intake 允许同键多行，保持 False。
        """
        if not table.isidentifier():
            raise ValueError("Invalid SQLite table name")
        if not id_key.isidentifier():
            raise ValueError("Invalid id_key")
        self.id_key = id_key
        self.scope_unique = scope_unique
        self.table = table
        self.db_path = db_path or os.environ.get(_ENV_DB) or get_default_db_path()
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        with _lock:
            conn = self._connect()
            try:
                conn.execute(f"CREATE TABLE IF NOT EXISTS {self.table} (id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, project_id TEXT NOT NULL, payload TEXT NOT NULL, updated_at TEXT NOT NULL)")
                conn.execute(f"CREATE INDEX IF NOT EXISTS idx_{self.table}_tenant_project ON {self.table}(tenant_id, project_id)")
                if self.scope_unique:
                    self._ensure_scope_unique(conn)
                conn.commit()
            finally:
                conn.close()

    def _ensure_scope_unique(self, conn: sqlite3.Connection) -> None:
        """RA-10 加固：scope_version 列迁移 + 唯一索引（幂等可重复执行）。

        迁移冲突（存量重复行）时显式失败并指引用专用脚本去重，
        绝不静默吞掉——静默等于假门禁。
        """
        cols = [r["name"] for r in conn.execute(f"PRAGMA table_info({self.table})").fetchall()]
        if "scope_version" not in cols:
            conn.execute(f"ALTER TABLE {self.table} ADD COLUMN scope_version INTEGER")
            conn.execute(
                f"UPDATE {self.table} SET scope_version = json_extract(payload, '$.scope_version')"
            )
        dup = conn.execute(
            f"SELECT project_id, tenant_id, scope_version FROM {self.table} "
            f"WHERE scope_version IS NOT NULL "
            f"GROUP BY project_id, tenant_id, scope_version HAVING COUNT(*) > 1"
        ).fetchone()
        if dup:
            raise RuntimeError(
                f"{self.table} contains duplicate (project_id, tenant_id, scope_version) rows "
                f"(e.g. project={dup['project_id']}, tenant={dup['tenant_id']}, "
                f"scope={dup['scope_version']}); run scripts/ra10_dedupe_reports.py "
                f"--db {self.db_path} before starting with scope_unique enabled"
            )
        conn.execute(
            f"CREATE UNIQUE INDEX IF NOT EXISTS ux_{self.table}_ptv "
            f"ON {self.table}(project_id, tenant_id, scope_version)"
        )

    def _connect(self):
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    async def upsert(self, payload: dict):
        now = datetime.now().isoformat()
        with _lock:
            conn = self._connect()
            try:
                if self.scope_unique:
                    conn.execute(
                        f"INSERT INTO {self.table} (id, tenant_id, project_id, scope_version, payload, updated_at) "
                        f"VALUES (?, ?, ?, ?, ?, ?) "
                        f"ON CONFLICT(id) DO UPDATE SET tenant_id=excluded.tenant_id, project_id=excluded.project_id, scope_version=excluded.scope_version, payload=excluded.payload, updated_at=excluded.updated_at",
                        (payload[self.id_key], payload["tenant_id"], payload["project_id"], payload.get("scope_version"), json.dumps(payload, ensure_ascii=False), now),
                    )
                else:
                    conn.execute(f"INSERT INTO {self.table} (id, tenant_id, project_id, payload, updated_at) VALUES (?, ?, ?, ?, ?) ON CONFLICT(id) DO UPDATE SET tenant_id=excluded.tenant_id, project_id=excluded.project_id, payload=excluded.payload, updated_at=excluded.updated_at", (payload[self.id_key], payload["tenant_id"], payload["project_id"], json.dumps(payload, ensure_ascii=False), now))
                conn.commit()
            finally:
                conn.close()
        return payload

    async def create_if_absent(self, payload: dict):
        """Atomically create a projection row without overwriting an existing ID.

        Returns ``(stored_payload, created)``; concurrent retries observe the first
        accepted payload and cannot reset its assignment/conversion state.
        """
        now = datetime.now().isoformat()
        entity_id = payload[self.id_key]
        with _lock:
            conn = self._connect()
            try:
                if self.scope_unique:
                    cursor = conn.execute(
                        f"INSERT OR IGNORE INTO {self.table} (id, tenant_id, project_id, scope_version, payload, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
                        (entity_id, payload["tenant_id"], payload["project_id"], payload.get("scope_version"), json.dumps(payload, ensure_ascii=False), now),
                    )
                else:
                    cursor = conn.execute(
                        f"INSERT OR IGNORE INTO {self.table} (id, tenant_id, project_id, payload, updated_at) VALUES (?, ?, ?, ?, ?)",
                        (entity_id, payload["tenant_id"], payload["project_id"], json.dumps(payload, ensure_ascii=False), now),
                    )
                created = cursor.rowcount == 1
                conn.commit()
                row = conn.execute(f"SELECT payload FROM {self.table} WHERE id = ?", (entity_id,)).fetchone()
                stored = json.loads(row["payload"]) if row else dict(payload)
                return stored, created
            finally:
                conn.close()

    async def get(self, entity_id: str, tenant_id: Optional[str] = None):
        conn = self._connect()
        try:
            row = conn.execute(f"SELECT payload, tenant_id FROM {self.table} WHERE id = ?", (entity_id,)).fetchone()
            if not row or (tenant_id is not None and row["tenant_id"] != tenant_id):
                return None
            return json.loads(row["payload"])
        finally:
            conn.close()

    async def list_by_project(self, project_id: str, tenant_id: str):
        conn = self._connect()
        try:
            rows = conn.execute(f"SELECT payload FROM {self.table} WHERE project_id = ? AND tenant_id = ? ORDER BY updated_at DESC", (project_id, tenant_id)).fetchall()
            return [json.loads(row["payload"]) for row in rows]
        finally:
            conn.close()

    async def list_by_tenant(self, tenant_id: str):
        """按租户列出全部投影行。

        ADR-009 Lead Intake Queue 需要——该类条目在「转项目」之前没有 project 维度，
        无法用 list_by_project 检索。租户过滤在 SQL 层完成，与既有隔离语义一致。
        """
        conn = self._connect()
        try:
            rows = conn.execute(
                f"SELECT payload FROM {self.table} WHERE tenant_id = ? ORDER BY updated_at DESC",
                (tenant_id,),
            ).fetchall()
            return [json.loads(row["payload"]) for row in rows]
        finally:
            conn.close()


# ======================================================================
# Client
# ======================================================================

class SQLiteClientRepository(SQLiteRepository):
    """Client 仓储（SQLite）。语义对齐 ClientRepository。"""

    table = "clients"
    id_field = "client_id"
    entity_name = "Client"

    def __init__(self, db_path: Optional[str] = None):
        from ..models import Client
        self.entity_cls = Client
        super().__init__(db_path)

    async def find_by_id(self, client_id: str, tenant_id: Optional[str] = None):
        entity = await self._raw_get(client_id)
        if entity is None:
            return None
        if tenant_id and entity.tenant_id != tenant_id:
            return None
        return entity

    async def find_by_tenant(self, tenant_id: str) -> List:
        return await self._raw_find_by_tenant(tenant_id)

    async def create(self, entity):
        return await self._raw_upsert(entity, exists_ok=False)

    async def update(self, entity):
        existing = await self._raw_get(entity.client_id)
        if existing and existing.tenant_id != entity.tenant_id:
            raise PermissionError(
                f"Tenant mismatch: update request from {entity.tenant_id} "
                f"for client owned by {existing.tenant_id}"
            )
        if existing is None:
            raise NotFoundError(f"Client {entity.client_id} not found")
        return await self._raw_upsert(entity)


# ======================================================================
# Project
# ======================================================================

class SQLiteProjectRepository(SQLiteRepository):
    """Project 仓储（SQLite）。语义对齐 ProjectRepository。"""

    table = "projects"
    id_field = "project_id"
    entity_name = "Project"

    def __init__(self, db_path: Optional[str] = None):
        from ..models import Project
        self.entity_cls = Project
        super().__init__(db_path)

    async def find_by_id(self, project_id: str, tenant_id: Optional[str] = None):
        entity = await self._raw_get(project_id)
        if entity is None:
            return None
        if tenant_id and entity.tenant_id != tenant_id:
            return None
        return entity

    async def find_by_tenant(self, tenant_id: str) -> List:
        return await self._raw_find_by_tenant(tenant_id)

    async def create(self, entity):
        return await self._raw_upsert(entity, exists_ok=False)

    async def update(self, entity):
        existing = await self._raw_get(entity.project_id)
        if existing and existing.tenant_id != entity.tenant_id:
            raise PermissionError(
                f"Tenant mismatch: update request from {entity.tenant_id} "
                f"for project owned by {existing.tenant_id}"
            )
        if existing is None:
            raise NotFoundError(f"Project {entity.project_id} not found")
        return await self._raw_upsert(entity)


# ======================================================================
# ServiceRequest
# ======================================================================

class SQLiteRequestRepository(SQLiteRepository):
    """Service Request 仓储（SQLite）。语义对齐 RequestRepository。

    注意：RequestRepository 对越权访问是 **抛 PermissionError**（而非返回 None），
    这里必须保持一致，否则租户隔离测试的行为会变化。
    """

    table = "requests"
    id_field = "request_id"
    entity_name = "ServiceRequest"

    def __init__(self, db_path: Optional[str] = None):
        from ..models.request import ServiceRequest
        self.entity_cls = ServiceRequest
        super().__init__(db_path)

    async def find_by_id(self, request_id: str, tenant_id: Optional[str] = None):
        entity = await self._raw_get(request_id)
        if entity is None:
            return None
        if tenant_id and entity.tenant_id != tenant_id:
            raise PermissionError(
                f"Access denied: Request {request_id} belongs to tenant "
                f"{entity.tenant_id}, not {tenant_id}"
            )
        return entity

    async def find_by_id_unscoped(self, request_id: str):
        """内部流程专用：无租户作用域的读取。

        B-3/P0 补齐：`RequestRepository`（内存）已有此方法，但 SQLite 版本缺失，
        导致 persist 模式下 `approve_scope` 抛 AttributeError
        —— 表现为**项目创建 100% 失败**。

        这类「两个后端方法集不一致」的缺陷只在 persist 模式暴露，
        因此必须有真实进程集成测试才能发现（单元测试用内存仓储）。

        仅供受状态机守卫保护的内部路径使用，不得暴露为 HTTP 端点。
        """
        return await self._raw_get(request_id)

    async def find_by_id_scoped(self, request_id: str, tenant_id: str):
        """B-3/P0 补齐：强制租户作用域的查询（与内存版本语义一致）。

        - tenant_id 为空 → 返回 None（fail closed，不抛异常）
        - 租户不符 → 返回 None（异常消息会泄漏目标 tenant_id）
        """
        if not tenant_id or not str(tenant_id).strip():
            return None
        entity = await self._raw_get(request_id)
        if entity is None:
            return None
        if getattr(entity, "tenant_id", None) != tenant_id:
            return None
        return entity

    async def find_by_tenant(self, tenant_id: str) -> List:
        return await self._raw_find_by_tenant(tenant_id)

    async def find_by_client(self, client_id: str, tenant_id: str) -> List:
        all_requests = await self.find_by_tenant(tenant_id)
        return [r for r in all_requests if getattr(r, "client_id", None) == client_id]

    async def create(self, entity):
        from ..models.request import ServiceRequest
        if not isinstance(entity, ServiceRequest):
            raise ValueError("Expected ServiceRequest")
        return await self._raw_upsert(entity, exists_ok=False)

    async def update(self, entity):
        from ..models.request import ServiceRequest
        if not isinstance(entity, ServiceRequest):
            raise ValueError("Expected ServiceRequest")
        existing = await self._raw_get(entity.request_id)
        if existing and existing.tenant_id != entity.tenant_id:
            raise PermissionError(
                f"Tenant mismatch: update request from {entity.tenant_id} "
                f"for request owned by {existing.tenant_id}"
            )
        if existing is None:
            raise NotFoundError(f"ServiceRequest {entity.request_id} not found")
        return await self._raw_upsert(entity)

    async def delete(self, entity_id: str, tenant_id: Optional[str] = None) -> bool:
        entity = await self.find_by_id(entity_id, tenant_id)
        if entity is None:
            return False
        return await self._raw_delete(entity_id)
