"""Repository 抽象层（Sprint 0 — 基础设施）。

所有数据访问必须通过 Repository，禁止直接操作数据库。
MVP 使用 InMemoryRepository，生产环境可替换为 SQL/NoSQL。
"""

from abc import ABC, abstractmethod
from typing import TypeVar, Generic, List, Optional, Dict, Any
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)

T = TypeVar("T")


class RepositoryError(Exception):
    """Repository 异常基类。"""
    pass


class NotFoundError(RepositoryError):
    pass


class DuplicateError(RepositoryError):
    pass


class PermissionError(Exception):
    """权限拒绝（租户不匹配）。"""
    pass


class BaseRepository(ABC, Generic[T]):
    """Repository 基类。

    所有 Repository 必须实现以下方法。
    """

    @abstractmethod
    async def find_by_id(self, entity_id: str) -> Optional[T]:
        """按 ID 查找。"""
        raise NotImplementedError

    @abstractmethod
    async def find_by_tenant(self, tenant_id: str) -> List[T]:
        """按 Tenant 查找（数据隔离）。"""
        raise NotImplementedError

    @abstractmethod
    async def create(self, entity: T) -> T:
        """创建实体。"""
        raise NotImplementedError

    @abstractmethod
    async def update(self, entity: T) -> T:
        """更新实体。"""
        raise NotImplementedError

    @abstractmethod
    async def delete(self, entity_id: str) -> bool:
        """删除实体。"""
        raise NotImplementedError

    @abstractmethod
    async def exists(self, entity_id: str) -> bool:
        """检查实体是否存在。"""
        raise NotImplementedError


class InMemoryRepository(BaseRepository[T]):
    """内存实现（MVP 使用）。

    注意：
    - 不支持并发
    - 重启后数据丢失
    - 仅用于开发/测试

    子类可通过类属性 `_id_attr` 声明主键字段名（见 update 实现）。
    """

    # 主键字段名；None 时 update() 回退到按固定顺序探测（见 update）。
    _id_attr: str | None = None

    def __init__(self, entity_name: str):
        self._entity_name = entity_name
        self._store: Dict[str, T] = {}
        self._audit_log: List[Dict[str, Any]] = []

    async def find_by_id(self, entity_id: str, tenant_id: Optional[str] = None) -> Optional[T]:
        entity = self._store.get(entity_id)
        if entity is None:
            return None
        # 租户隔离验证：如果提供了 tenant_id，必须匹配
        if tenant_id and hasattr(entity, "tenant_id") and entity.tenant_id != tenant_id:
            raise PermissionError(
                f"Access denied: entity {entity_id} belongs to tenant {entity.tenant_id}, "
                f"not {tenant_id}"
            )
        return entity

    async def find_by_tenant(self, tenant_id: str) -> List[T]:
        """按 Tenant 查找（数据隔离）。子类必须覆盖此方法。"""
        results = []
        for entity in self._store.values():
            if hasattr(entity, "tenant_id") and entity.tenant_id == tenant_id:
                results.append(entity)
        return results

    async def create(self, entity: T) -> T:
        # 尝试多个可能的 ID 字段名（按优先级顺序）
        entity_id = None
        for attr in ("entity_id", "id", "request_id", "project_id", "work_item_id", "scope_id", "client_id"):
            if hasattr(entity, attr):
                val = getattr(entity, attr)
                if val:
                    entity_id = str(val)
                    break
        if not entity_id:
            raise ValueError(f"Entity must have an id field: {self._entity_name}")
        if entity_id in self._store:
            raise DuplicateError(f"Entity {self._entity_name} {entity_id} already exists")
        self._store[entity_id] = entity
        # 记录审计事件
        self._audit_log.append({
            "action": "create",
            "entity_type": self._entity_name,
            "id": entity_id,
            "tenant_id": getattr(entity, "tenant_id", None),
        })
        logger.info("Created %s: %s", self._entity_name, entity_id)
        return entity

    async def update(self, entity: T) -> T:
        # 优先使用子类显式声明的 ID 字段（_id_attr）。
        # 否则回退到"按固定顺序探测"的旧逻辑——注意该顺序对同时拥有多个
        # ID 字段的实体（如 Project 同时有 request_id / project_id）会取错 key，
        # 因此这类实体必须声明 _id_attr。
        entity_id = None
        if getattr(self, "_id_attr", None):
            entity_id = getattr(entity, self._id_attr, None)
        else:
            for attr in ("entity_id", "id", "request_id", "project_id", "work_item_id", "scope_id"):
                if hasattr(entity, attr):
                    entity_id = getattr(entity, attr)
                    break
        if not entity_id:
            raise ValueError(f"Entity must have an id field: {self._entity_name}")
        if entity_id not in self._store:
            raise NotFoundError(f"Entity {self._entity_name} {entity_id} not found")
        self._store[entity_id] = entity
        logger.info("Updated %s: %s", self._entity_name, entity_id)
        return entity

    async def delete(self, entity_id: str) -> bool:
        if entity_id in self._store:
            del self._store[entity_id]
            return True
        return False

    async def exists(self, entity_id: str) -> bool:
        return entity_id in self._store

    def clear(self):
        self._store.clear()
