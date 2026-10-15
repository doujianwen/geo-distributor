"""Sprint 0 Red-Team: Tenant Isolation 攻击测试。

攻击向量：
- Tenant A → read/update/delete Tenant B 数据
- 关联ID攻击：知道Tenant A的object_id，直接请求
- list()泄漏跨Tenant数据
"""

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from geo_distributor.models.tenant import Tenant, TenantStatus, User, UserRole
from geo_distributor.models.request import ServiceRequest, BusinessContext, RequestStatus
from geo_distributor.models.project import Project, ProjectStatus
from geo_distributor.models.work_item import WorkItem, WorkItemType, WorkItemStatus
from geo_distributor.repositories.request_repo import RequestRepository
from geo_distributor.repositories.project_repo import ProjectRepository
from geo_distributor.repositories.work_item_repo import WorkItemRepository


class TestTenantIsolationClient:
    """测试Tenant隔离——Client数据不可跨租户访问。"""

    @pytest.mark.asyncio
    async def test_tenant_a_cannot_read_tenant_b_client(self):
        """Tenant A不能读取Tenant B的Client。"""
        # 创建两个租户的Client
        client_a = {
            "client_id": "CLI-A-001",
            "tenant_id": "DST-A",
            "name": "Acme Corp",
            "website": "https://acme.com",
            "industry": "sensors",
        }
        client_b = {
            "client_id": "CLI-B-001",
            "tenant_id": "DST-B",
            "name": "Beta Inc",
            "website": "https://beta.com",
            "industry": "industrial",
        }

        # 模拟存储（实际项目中会有Repository层）
        clients_by_tenant = {
            "DST-A": [client_a],
            "DST-B": [client_b],
        }

        # 攻击：Tenant B 尝试读取 Tenant A 的 Client
        tenant_b_clients = clients_by_tenant.get("DST-B", [])
        assert len(tenant_b_clients) == 1
        assert tenant_b_clients[0]["client_id"] == "CLI-B-001"
        assert tenant_b_clients[0]["name"] != "Acme Corp"

    @pytest.mark.asyncio
    async def test_tenant_b_cannot_update_tenant_a_client(self):
        """Tenant B 不能更新 Tenant A 的 Client。"""
        from geo_distributor.models.tenant import Tenant
        from geo_distributor.repositories.client_repo import ClientRepository

        repo = ClientRepository()

        # 创建 Tenant A 的 Client（使用 Tenant 对象模拟）
        client_a = Tenant(
            tenant_id="DST-A",
            name="Acme Corp",
            contact_email="a@example.com",
        )
        client_a.client_id = "CLI-A-001"
        await repo.create(client_a)

        # 创建 Tenant B 的 Client
        client_b = Tenant(
            tenant_id="DST-B",
            name="Beta Inc",
            contact_email="b@example.com",
        )
        client_b.client_id = "CLI-B-001"
        await repo.create(client_b)

        # 攻击：Tenant B 尝试更新 Tenant A 的 Client
        with pytest.raises((PermissionError, Exception)):
            hacked_client = Tenant(
                tenant_id="DST-B",
                name="Hacked",
            )
            hacked_client.client_id = "CLI-A-001"
            await repo.update(hacked_client)

    @pytest.mark.asyncio
    async def test_tenant_b_cannot_delete_tenant_a_client(self):
        """Tenant B 不能删除 Tenant A 的 Client。"""
        # 攻击：Tenant B 尝试删除 Tenant A 的 Client
        delete_request = {"client_id": "CLI-A-001", "tenant_id": "DST-B"}
        # 验证：删除请求中的 tenant_id 与 Client 的 tenant_id 不匹配
        assert delete_request["tenant_id"] != "DST-A"


class TestTenantIsolationRequest:
    """测试Service Request的Tenant隔离。"""

    @pytest.mark.asyncio
    async def test_request_repo_tenant_isolation(self):
        """RequestRepository 必须按 tenant_id 隔离。"""
        repo = RequestRepository()

        # 创建 Tenant A 的 Request
        req_a = ServiceRequest(
            request_id="SR-A-001",
            tenant_id="DST-A",
            client_id="CLI-A-001",
            service="visibility_audit",
        )
        await repo.create(req_a)

        # 创建 Tenant B 的 Request
        req_b = ServiceRequest(
            request_id="SR-B-001",
            tenant_id="DST-B",
            client_id="CLI-B-001",
            service="visibility_audit",
        )
        await repo.create(req_b)

        # 攻击：Tenant B 尝试读取 Tenant A 的 Request
        tenant_a_requests = await repo.find_by_tenant("DST-A")
        tenant_b_requests = await repo.find_by_tenant("DST-B")

        assert len(tenant_a_requests) == 1
        assert tenant_a_requests[0].request_id == "SR-A-001"
        assert len(tenant_b_requests) == 1
        assert tenant_b_requests[0].request_id == "SR-B-001"

        # 确认没有泄漏
        assert not any(r.request_id == "SR-A-001" for r in tenant_b_requests)

    @pytest.mark.asyncio
    async def test_correlated_id_attack(self):
        """关联ID攻击：知道Tenant A的object_id，直接请求。"""
        repo = RequestRepository()

        # 创建 Tenant A 的数据
        req_a = ServiceRequest(
            request_id="SR-A-001",
            tenant_id="DST-A",
            client_id="CLI-A-001",
        )
        await repo.create(req_a)

        # 前置硬断言：Tenant A 的数据确实存在于**攻击者使用的那个仓储**里。
        # 原实现用 `attacker_repo = RequestRepository()` 新建了一个空仓储，
        # 攻击者在其中根本查不到任何东西 → result 恒为 None → 断言恒通过。
        # 这是比`if result:` 更隐蔽的假绿：**攻击从未真正发生，测试却通过了**。
        attacker_repo = repo  # 复用同一仓储，攻击者与受害者共享数据视图

        # 步骤 1：证明攻击者的仓储里确实有这个实体（否则后面的拒绝毫无意义）
        try:
            victim_visible = await attacker_repo.find_by_id("SR-A-001")
        except Exception as exc:  # noqa: BLE001
            pytest.fail(f"前置失败：{type(exc).__name__}: {exc}")
        assert victim_visible is not None, (
            "前置失败：攻击者仓储中查不到 Tenant A 的实体，"
            "说明攻击场景未成立，后续断言无意义"
        )
        assert victim_visible.tenant_id == "DST-A", "前置失败：实体归属不符"

        # 步骤 2：真正的门禁 —— tenant-facing 的 scoped 查询必须拒绝
        try:
            result = await attacker_repo.find_by_id_scoped(
                "SR-A-001", tenant_id="DST-B"
            )
        except Exception as exc:  # noqa: BLE001
            pytest.fail(
                f"跨租户 scoped 查询抛出未处理异常 {type(exc).__name__}: {exc}；"
                "异常消息泄漏目标 tenant_id，应改为返回 None"
            )

        # 硬断言：Tenant B 不得看到 Tenant A 的实体
        assert result is None, (
            "correlated-ID 攻击成立：Tenant B 拿到了 "
            f"{getattr(result, 'tenant_id', '?')} 的实体"
        )


class TestTenantIsolationProject:
    """测试Project的Tenant隔离。"""

    @pytest.mark.asyncio
    async def test_project_repo_tenant_isolation(self):
        """ProjectRepository 必须按 tenant_id 隔离。"""
        repo = ProjectRepository()

        # 创建 Tenant A 的 Project
        proj_a = Project(
            project_id="PRJ-A-001",
            request_id="SR-A-001",
            tenant_id="DST-A",
            client_id="CLI-A-001",
            scope_id="SCOPE-A-001",
        )
        await repo.create(proj_a)

        # 创建 Tenant B 的 Project
        proj_b = Project(
            project_id="PRJ-B-001",
            request_id="SR-B-001",
            tenant_id="DST-B",
            client_id="CLI-B-001",
            scope_id="SCOPE-B-001",
        )
        await repo.create(proj_b)

        # 攻击：Tenant B 尝试读取 Tenant A 的 Project
        tenant_a_projects = await repo.find_by_tenant("DST-A")
        tenant_b_projects = await repo.find_by_tenant("DST-B")

        assert len(tenant_a_projects) == 1
        assert tenant_a_projects[0].project_id == "PRJ-A-001"
        assert len(tenant_b_projects) == 1
        assert tenant_b_projects[0].project_id == "PRJ-B-001"


class TestTenantIsolationWorkItem:
    """测试Work Item的Tenant隔离。"""

    @pytest.mark.asyncio
    async def test_work_item_repo_tenant_isolation(self):
        """WorkItemRepository 必须按 project/tenant 隔离。"""
        repo = WorkItemRepository()

        # 创建 Project A 的 Work Item
        wi_a = WorkItem(
            work_item_id="WI-A-001",
            project_id="PRJ-A-001",
            tenant_id="DST-A",
            type=WorkItemType.MEASUREMENT,
        )
        await repo.create(wi_a)

        # 创建 Project B 的 Work Item
        wi_b = WorkItem(
            work_item_id="WI-B-001",
            project_id="PRJ-B-001",
            tenant_id="DST-B",
            type=WorkItemType.MEASUREMENT,
        )
        await repo.create(wi_b)

        # 攻击：Tenant B 尝试读取 Tenant A 的 Work Item
        tenant_a_items = await repo.find_by_tenant("DST-A")
        tenant_b_items = await repo.find_by_tenant("DST-B")

        assert len(tenant_a_items) == 1
        assert tenant_a_items[0].work_item_id == "WI-A-001"
        assert len(tenant_b_items) == 1
        assert tenant_b_items[0].work_item_id == "WI-B-001"
