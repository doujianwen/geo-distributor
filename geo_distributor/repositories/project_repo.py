"""Project Repository（Sprint 0）。"""

from typing import List, Optional
import logging
from .base import InMemoryRepository

logger = logging.getLogger(__name__)


class ProjectRepository(InMemoryRepository):
    """Project 仓库。

    数据隔离：按 tenant_id 过滤。
    """

    def __init__(self):
        super().__init__("Project")
        self._by_tenant: dict = {}

    async def find_by_id(self, project_id: str, tenant_id: Optional[str] = None) -> Optional["Project"]:
        """查找 Project，支持租户隔离验证。"""
        entity = await super().find_by_id(project_id, tenant_id=tenant_id)
        return entity  # type: ignore

    async def find_by_tenant(self, tenant_id: str) -> List["Project"]:
        """按租户查找所有 Project（数据隔离）。"""
        ids = self._by_tenant.get(tenant_id, set())
        results = []
        for pid in ids:
            entity = await super().find_by_id(pid)
            if entity:
                results.append(entity)
        return results

    async def create(self, entity):
        # 直接使用 project_id 作为 key（覆盖父类逻辑）
        project_id = getattr(entity, "project_id", None)
        if not project_id:
            raise ValueError("Entity must have a project_id field")
        if project_id in self._store:
            raise Exception(f"Project {project_id} already exists")
        self._store[project_id] = entity
        if hasattr(entity, "tenant_id"):
            if entity.tenant_id not in self._by_tenant:
                self._by_tenant[entity.tenant_id] = set()
            self._by_tenant[entity.tenant_id].add(entity.project_id)
        logger.info("Created Project: %s", project_id)
        return entity

    async def update(self, entity):
        # 验证更新权限：租户必须匹配
        existing = await super().find_by_id(entity.project_id)
        if existing and existing.tenant_id != entity.tenant_id:
            raise PermissionError(
                f"Tenant mismatch: update request from {entity.tenant_id} "
                f"for project owned by {existing.tenant_id}"
            )
        return await super().update(entity)
