"""Client Repository（Sprint 0）。"""

from typing import List, Optional
import logging
from .base import InMemoryRepository

logger = logging.getLogger(__name__)


class ClientRepository(InMemoryRepository):
    """Client 仓库，tenant 隔离。"""

    def __init__(self):
        super().__init__("Client")
        self._by_tenant: dict[str, set] = {}

    async def find_by_tenant(self, tenant_id: str) -> List:
        """按租户查找所有 Client。"""
        ids = self._by_tenant.get(tenant_id, set())
        results = []
        for cid in ids:
            entity = await super().find_by_id(cid)
            if entity:
                results.append(entity)
        return results

    async def create(self, entity):
        result = await super().create(entity)
        if hasattr(entity, "tenant_id"):
            if entity.tenant_id not in self._by_tenant:
                self._by_tenant[entity.tenant_id] = set()
            self._by_tenant[entity.tenant_id].add(entity.client_id)
        return result

    async def update(self, entity):
        # 验证更新权限：租户必须匹配
        existing = await super().find_by_id(entity.client_id)
        if existing and existing.tenant_id != entity.tenant_id:
            raise PermissionError(
                f"Tenant mismatch: update request from {entity.tenant_id} "
                f"for client owned by {existing.tenant_id}"
            )
        return await super().update(entity)
