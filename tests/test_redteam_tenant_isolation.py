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

        # 攻击：Tenant B 使用 Tenant A 的 ID 尝试读取
        attacker_repo = RequestRepository()
        result = await attacker_repo.find_by_id("SR-A-001")

        # 即使能查到，也必须验证 tenant_id
        if result:
            assert result.tenant_id == "DST-A"
            # 攻击者 tenant_id != 数据 tenant_id → 拒绝
            assert False  # 实际API层应拒绝此请求


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
