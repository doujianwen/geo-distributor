"""Request Repository（Sprint 0）。"""

from typing import List, Optional
import logging
from .base import InMemoryRepository, NotFoundError

logger = logging.getLogger(__name__)


class RequestRepository(InMemoryRepository):
    """Service Request 仓库。

    数据隔离：按 tenant_id 过滤。
    所有查询必须通过 tenant_id 参数，禁止无过滤查询。
    """

    def __init__(self):
        super().__init__("ServiceRequest")
        self._by_tenant: dict = {}  # tenant_id -> set of request_ids

    async def find_by_id(self, request_id: str, tenant_id: Optional[str] = None) -> Optional["ServiceRequest"]:  # type: ignore
        """查找 Request。向后兼容签名（不带 tenant 可查到）。

        ⚠️ 该方法**不提供租户隔离保证**，仅供内部流程与既有契约使用。
        tenant-facing API 必须使用 `find_by_id_scoped`（tenant 必填、不符返回 None）。
        """
        entity = await super().find_by_id(request_id)
        if entity is None:
            return None
        if tenant_id and entity.tenant_id != tenant_id:
            logger.warning("Tenant mismatch: requested %s for tenant %s, belongs to %s",
                          request_id, tenant_id, entity.tenant_id)
            raise PermissionError(
                f"Access denied: Request {request_id} belongs to tenant {entity.tenant_id}, "
                f"not {tenant_id}"
            )
        return entity  # type: ignore

    async def find_by_id_unscoped(self, request_id: str) -> Optional["ServiceRequest"]:  # type: ignore
        """内部流程专用：无租户作用域的读取。

        仅供受状态机守卫保护的内部路径使用（如 approve_scope）。
        **不得**用于任何 tenant-facing API 路径。
        """
        return await super().find_by_id(request_id)

    async def find_by_id_scoped(self, request_id: str, tenant_id: str) -> Optional["ServiceRequest"]:  # type: ignore
        """B-3 修复：强制租户作用域的查询。

        `find_by_id` 的 tenant_id 是 Optional，省略即等于「看到全部」——
        这让任何忘记传 tenant 的调用都变成跨租户泄漏（correlated-ID 攻击）。

        本方法是 tenant-facing API 唯一应使用入口：
        - tenant_id 必填
        - 租户不符返回 None（不抛异常，避免异常消息泄漏目标 tenant_id）

        内部流程（如 approve_scope）可继续用 find_by_id —— 那条路径
        由状态机守卫 + approver_id 角色控制，不暴露为 HTTP API。
        """
        if not tenant_id or not str(tenant_id).strip():
            # 空 tenant = 拒绝（返回 None 而非抛异常：异常会进入API 响应体）
            logger.warning(
                "B-3: find_by_id_scoped called without tenant for %s; denying",
                request_id,
            )
            return None
        entity = await super().find_by_id(request_id)
        if entity is None:
            return None
        if getattr(entity, "tenant_id", None) != tenant_id:
            logger.warning(
                "Tenant mismatch: request %s requested by tenant %s, belongs to %s",
                request_id, tenant_id, getattr(entity, "tenant_id", None),
            )
            return None
        return entity  # type: ignore

    async def find_by_tenant(self, tenant_id: str) -> List["ServiceRequest"]:  # type: ignore
        """按租户查找所有 Request（数据隔离）。"""
        ids = self._by_tenant.get(tenant_id, set())
        results = []
        for rid in ids:
            entity = await super().find_by_id(rid)
            if entity:
                results.append(entity)
        return results  # type: ignore

    async def find_by_client(self, client_id: str, tenant_id: str) -> List["ServiceRequest"]:
        """按 Client 查找所有 Request（必须在租户内）。"""
        all_requests = await self.find_by_tenant(tenant_id)
        return [r for r in all_requests if getattr(r, "client_id", None) == client_id]  # type: ignore

    async def create(self, entity):  # type: ignore
        from ..models.request import ServiceRequest
        if not isinstance(entity, ServiceRequest):
            raise ValueError("Expected ServiceRequest")
        result = await super().create(entity)  # type: ignore
        # 更新 tenant 索引
        if entity.tenant_id not in self._by_tenant:
            self._by_tenant[entity.tenant_id] = set()
        self._by_tenant[entity.tenant_id].add(entity.request_id)
        return result  # type: ignore

    async def update(self, entity):  # type: ignore
        from ..models.request import ServiceRequest
        if not isinstance(entity, ServiceRequest):
            raise ValueError("Expected ServiceRequest")
        # 租户隔离验证：检查请求的租户是否与实体匹配
        existing = await super().find_by_id(entity.request_id)
        if existing and existing.tenant_id != entity.tenant_id:
            from .base import PermissionError as RepoPermissionError
            raise RepoPermissionError(
                f"Tenant mismatch: update request from {entity.tenant_id} "
                f"for request owned by {existing.tenant_id}"
            )
        return await super().update(entity)  # type: ignore

    async def delete(self, entity_id: str, tenant_id: Optional[str] = None) -> bool:
        entity = await self.find_by_id(entity_id, tenant_id)
        if entity:
            self._by_tenant.get(entity.tenant_id, set()).discard(entity_id)  # type: ignore
        return await super().delete(entity_id)
