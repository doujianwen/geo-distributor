"""审计日志：写操作留痕。

## 为什么需要

B-2 认证实施后，系统开始接受远程、多用户请求。此时必须能回答：
**「谁在什么时候动了什么」** —— 否则商业交付出现纠纷时无法追溯。

`geo_distributor.models.tenant.AuditEntry` 早已定义（标注「P0 必须」），
但从未被 API 层调用。本模块负责把它落地。

## 设计要点

1. **复用既有模型**，不新建审计实体 —— `AuditEntry` 字段完整
2. **独立存储**：审计表挂在同一 SQLite（persist 模式）或独立文件（memory 模式）
   - 独立文件的原因：审计不能在业务库被事务回滚时一起消失
3. **写操作必记，读操作可选** —— 读操作量级远大于写，全记会撑爆存储
4. **审计失败不影响主流程** —— 审计是辅助系统，不能因为它挂了就阻断业务

## 接入点

认证层已识别出每个请求的 `AuthContext`（含 user_id / role / tenant）。
`record_audit()` 由 router 在写操作后调用，或由 `audit_middleware` 自动记录。

运行：
    from api.audit import record_audit
    record_audit(auth, action="CREATE", resource_type="PROJECT", resource_id=pid)
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# 独立审计库路径（与业务库分离，避免业务库损坏时审计一起丢失）
AUDIT_DB_ENV = "GEO_DISTRIBUTOR_AUDIT_DB"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS audit_log (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    audit_id      TEXT    NOT NULL UNIQUE,
    tenant_id     TEXT,
    user_id       TEXT,
    role          TEXT,
    action        TEXT    NOT NULL,
    resource_type TEXT,
    resource_id   TEXT,
    old_value     TEXT,
    new_value     TEXT,
    ip_address    TEXT,
    request_id    TEXT,
    outcome       TEXT    NOT NULL DEFAULT 'OK',
    reason        TEXT,
    created_at    TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_audit_tenant_created
    ON audit_log(tenant_id, created_at);
CREATE INDEX IF NOT EXISTS idx_audit_resource
    ON audit_log(resource_type, resource_id);
CREATE INDEX IF NOT EXISTS idx_audit_user
    ON audit_log(user_id, created_at);
"""

_lock = threading.Lock()
_conn: Optional[sqlite3.Connection] = None
_db_path: Optional[Path] = None

# 字段白名单：只序列化这些字段，避免把整个实体（含大文本）写进审计
_VALUE_MAX_LEN = 2000


def _default_db_path() -> Path:
    """审计库默认路径：与业务库同目录的独立文件。"""
    env = os.environ.get(AUDIT_DB_ENV, "").strip()
    if env:
        return Path(env)
    base = Path(__file__).resolve().parent.parent / "data"
    return base / "audit_log.db"


def _connect() -> Optional[sqlite3.Connection]:
    """获取（惰性建立）审计库连接。失败返回 None —— 审计不可用不阻断业务。"""
    global _conn, _db_path

    target = _default_db_path()
    if _conn is not None and _db_path == target:
        return _conn

    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(target), timeout=10, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.executescript(_SCHEMA)
        conn.commit()
        _conn = conn
        _db_path = target
        return conn
    except Exception as exc:  # noqa: BLE001
        logger.warning("审计库不可用，审计记录将被跳过：%s", exc)
        return None


def _truncate(value: Any) -> Optional[str]:
    """把任意值转为截断后的 JSON 字符串。"""
    if value is None:
        return None
    try:
        text = json.dumps(value, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        text = str(value)
    if len(text) > _VALUE_MAX_LEN:
        text = text[:_VALUE_MAX_LEN] + "...[truncated]"
    return text


def record_audit(
    *,
    action: str,
    resource_type: str = "",
    resource_id: str = "",
    auth: Any = None,
    tenant_id: Optional[str] = None,
    user_id: Optional[str] = None,
    role: Optional[str] = None,
    old_value: Any = None,
    new_value: Any = None,
    ip_address: Optional[str] = None,
    request_id: Optional[str] = None,
    outcome: str = "OK",
    reason: str = "",
) -> Optional[str]:
    """记录一条审计条目。返回 audit_id；审计不可用时返回 None。

    **永不抛异常** —— 审计是辅助系统，不能因为它故障而阻断业务。
    调用方无需 try/except。
    """
    try:
        # 身份优先取认证上下文，其次显式传入
        if auth is not None:
            tenant_id = tenant_id or getattr(auth, "tenant_id", None)
            user_id = user_id or getattr(auth, "user_id", None)
            role = role or getattr(auth, "role", None)

        audit_id = f"AUD-{uuid.uuid4().hex[:12].upper()}"
        row = (
            audit_id,
            tenant_id,
            user_id,
            role,
            action.upper(),
            resource_type,
            resource_id,
            _truncate(old_value),
            _truncate(new_value),
            ip_address,
            request_id,
            outcome.upper(),
            reason,
            datetime.now().isoformat(timespec="seconds"),
        )

        with _lock:
            conn = _connect()
            if conn is None:
                return None
            conn.execute(
                """INSERT INTO audit_log
                   (audit_id, tenant_id, user_id, role, action, resource_type,
                    resource_id, old_value, new_value, ip_address, request_id,
                    outcome, reason, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                row,
            )
            conn.commit()
        return audit_id

    except Exception as exc:  # noqa: BLE001
        # 绝不因审计失败影响主流程
        logger.warning("审计写入失败（已忽略）：%s", exc)
        return None


def query_unauthenticated_attempts(limit: int = 100) -> List[Dict[str, Any]]:
    """查询**认证失败/无身份**的审计条目。

    独立入口的原因：认证失败时没有可信 tenant_id（请求头里的声明值
    可能是伪造的），这类记录 tenant_id 为空，只按 tenant 查不到。
    而它们恰恰是发现爆破 / 探测的关键线索。

    只暴露给**内部运维**，不提供给租户级 API ——
    租户不应看到其他租户的失败尝试。
    """
    try:
        with _lock:
            conn = _connect()
            if conn is None:
                return []
            rows = conn.execute(
                "SELECT * FROM audit_log WHERE user_id IS NULL "
                "ORDER BY id DESC LIMIT ?",
                (max(1, min(int(limit), 1000)),),
            ).fetchall()
        return [dict(r) for r in rows]
    except Exception as exc:  # noqa: BLE001
        logger.warning("审计查询失败：%s", exc)
        return []


def query_audit(
    *,
    tenant_id: Optional[str] = None,
    user_id: Optional[str] = None,
    resource_type: Optional[str] = None,
    resource_id: Optional[str] = None,
    action: Optional[str] = None,
    limit: int = 100,
) -> List[Dict[str, Any]]:
    """查询审计条目。**必须按 tenant_id 过滤**，否则构成跨租户泄漏。

    租户过滤是强制的：`tenant_id=None` 视为「调用方未指定租户」，
    直接返回空列表而不是「全部」—— 避免忘记传参导致数据泄漏。

    认证失败的记录（user_id 为空）请用
    `query_unauthenticated_attempts()` —— 它们没有可信 tenant。
    """
    if not tenant_id:
        return []

    try:
        with _lock:
            conn = _connect()
            if conn is None:
                return []

            sql = "SELECT * FROM audit_log WHERE tenant_id = ?"
            params: List[Any] = [tenant_id]

            if user_id:
                sql += " AND user_id = ?"
                params.append(user_id)
            if resource_type:
                sql += " AND resource_type = ?"
                params.append(resource_type)
            if resource_id:
                sql += " AND resource_id = ?"
                params.append(resource_id)
            if action:
                sql += " AND action = ?"
                params.append(action.upper())

            sql += " ORDER BY id DESC LIMIT ?"
            params.append(max(1, min(int(limit), 1000)))

            rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    except Exception as exc:  # noqa: BLE001
        logger.warning("审计查询失败：%s", exc)
        return []


def audit_stats(tenant_id: str) -> Dict[str, int]:
    """按 action 统计某租户的审计条目数。"""
    if not tenant_id:
        return {}
    try:
        with _lock:
            conn = _connect()
            if conn is None:
                return {}
            rows = conn.execute(
                "SELECT action, COUNT(*) AS n FROM audit_log "
                "WHERE tenant_id = ? GROUP BY action",
                (tenant_id,),
            ).fetchall()
        return {r["action"]: r["n"] for r in rows}
    except Exception as exc:  # noqa: BLE001
        logger.warning("审计统计失败：%s", exc)
        return {}


def reset_audit_store() -> None:
    """清空连接缓存（测试用）。不删除数据。"""
    global _conn, _db_path
    with _lock:
        if _conn is not None:
            try:
                _conn.close()
            except Exception:  # noqa: BLE001
                pass
        _conn = None
        _db_path = None
