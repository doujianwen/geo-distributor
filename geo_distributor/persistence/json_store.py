"""内存版 JSON 投影存储（与 SQLiteJSONRepository 接口对齐）。

## 为什么需要

`SQLiteJSONRepository` 只在 `GEO_DISTRIBUTOR_DB` 存在时可用；未启用持久化时
（默认内存模式）调用方会拿到 `None`。Lead Intake Queue（ADR-009）需要在两种
后端下都可用，且**接口一致**，因此提供这个最小内存实现。

## 定位（与 ADR-009 一致）

与 `SQLiteJSONRepository` 一样，它是**投影存储**，不是领域模型：
只存/取 dict payload，不承载任何商业语义，不引入新 dataclass。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


class InMemoryJSONRepository:
    """纯内存的 dict 投影存储。进程重启即失（与内存后端语义一致）。"""

    def __init__(self, id_key: str = "lead_id"):
        if not id_key.isidentifier():
            raise ValueError("Invalid id_key")
        self.id_key = id_key
        self._rows: Dict[str, Dict[str, Any]] = {}

    async def upsert(self, payload: dict) -> dict:
        self._rows[payload[self.id_key]] = dict(payload)
        return payload

    async def create_if_absent(self, payload: dict):
        """Create once per stable ID; never overwrite a prior assignment on retry."""
        entity_id = payload[self.id_key]
        existing = self._rows.get(entity_id)
        if existing is not None:
            return dict(existing), False
        self._rows[entity_id] = dict(payload)
        return dict(payload), True

    async def get(self, entity_id: str, tenant_id: Optional[str] = None):
        row = self._rows.get(entity_id)
        if row is None:
            return None
        if tenant_id is not None and row.get("tenant_id") != tenant_id:
            return None
        return dict(row)

    async def list_by_tenant(self, tenant_id: str) -> List[dict]:
        return [dict(v) for v in self._rows.values() if v.get("tenant_id") == tenant_id]

    async def list_all(self) -> List[dict]:
        return [dict(v) for v in self._rows.values()]
