"""Work Item Repository（Sprint 0）。"""

from typing import List, Optional
import logging
from .base import InMemoryRepository

logger = logging.getLogger(__name__)


class WorkItemRepository(InMemoryRepository):
    """Work Item 仓库。"""

    def __init__(self):
        super().__init__("WorkItem")
        self._by_project: dict = {}

    async def find_by_project(self, project_id: str, tenant_id: Optional[str] = None) -> List:
        """按 Project 查找所有 Work Item，支持租户隔离。"""
        ids = self._by_project.get(project_id, set())
        results = []
        for wid in ids:
            entity = await super().find_by_id(wid, tenant_id=tenant_id)
            if entity:
                results.append(entity)
        return results

    async def find_pending(self, project_id: str) -> List:
        """查找可执行的 PENDING Work Item（依赖已满足）。"""
        items = await self.find_by_project(project_id)
        pending = []
        for item in items:
            if item.status.value == "pending":
                # 检查依赖是否完成
                deps_met = all(
                    any(wi.status.value == "completed" for wi in items if wi.work_item_id == dep)
                    for dep in item.depends_on
                )
                if deps_met:
                    pending.append(item)
        return pending

    async def find_by_tenant(self, tenant_id: str) -> List:
        """按租户查找所有 Work Item（通过 project 关联）。"""
        results = []
        for wid, entity in self._store.items():
            if hasattr(entity, "tenant_id") and entity.tenant_id == tenant_id:
                results.append(entity)
        return results

    async def create(self, entity):
        # WorkItem 使用 work_item_id 作为主键
        if hasattr(entity, "work_item_id") and entity.work_item_id:
            entity_id = str(entity.work_item_id)
        else:
            raise ValueError("WorkItem must have a work_item_id")

        # 检查重复
        if entity_id in self._store:
            from .base import DuplicateError
            raise DuplicateError(f"WorkItem {entity_id} already exists")

        self._store[entity_id] = entity

        # 更新 project 索引
        if hasattr(entity, "project_id"):
            if entity.project_id not in self._by_project:
                self._by_project[entity.project_id] = set()
            self._by_project[entity.project_id].add(entity_id)

        # 记录审计事件
        self._audit_log.append({
            "action": "create",
            "entity_type": self._entity_name,
            "id": entity_id,
            "tenant_id": getattr(entity, "tenant_id", None),
        })
        logger.info("Created %s: %s", self._entity_name, entity_id)
        return entity

    async def update(self, entity):
        # 验证更新权限：租户必须匹配
        existing = await super().find_by_id(entity.work_item_id)
        if existing and existing.tenant_id != entity.tenant_id:
            raise PermissionError(
                f"Tenant mismatch: update request from {entity.tenant_id} "
                f"for work_item owned by {existing.tenant_id}"
            )
        return await super().update(entity)
