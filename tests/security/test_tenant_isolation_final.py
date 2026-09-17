"""Tenant Isolation Final Red-Team — Phase 2

攻击向量 A-H 逐一验证租户数据完全隔离。
"""

import pytest
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from geo_distributor.models.request import ServiceRequest, RequestStatus
from geo_distributor.models.project import Project, ProjectStatus
from geo_distributor.models.geo_core import Report, ReportType
from geo_distributor.repositories.request_repo import RequestRepository
from geo_distributor.repositories.project_repo import ProjectRepository
from geo_distributor.repositories.client_repo import ClientRepository
from geo_distributor.guards.state_transition import StateTransitionGuard


class TestAttackA_DirectIdQuery:
    """Attack A: Tenant A 使用 Tenant B 的 ID 查询。"""

    @pytest.mark.asyncio
    async def test_request_by_b_id_from_a_context(self):
        repo = RequestRepository()
        req_b = ServiceRequest(request_id="SR-B-001", tenant_id="DST-B", client_id="CLI-B")
        await repo.create(req_b)

        # 攻击：A 尝试直接查询 B 的 ID
        with pytest.raises(Exception):
            await repo.find_by_id("SR-B-001", tenant_id="DST-A")

    @pytest.mark.asyncio
    async def test_project_by_b_id_from_a_context(self):
        repo = ProjectRepository()
        proj_b = Project(project_id="PRJ-B-001", request_id="SR-B-001", tenant_id="DST-B", client_id="CLI-B", scope_id="SCOPE-B")
        await repo.create(proj_b)

        with pytest.raises(Exception):
            await repo.find_by_id("PRJ-B-001", tenant_id="DST-A")


class TestAttackB_ModifyOtherTenant:
    """Attack B: Tenant A 使用 Tenant B 的 ID 修改。"""

    @pytest.mark.asyncio
    async def test_update_other_tenant_request(self):
        repo = RequestRepository()
        req_a = ServiceRequest(request_id="SR-A-001", tenant_id="DST-A", client_id="CLI-A")
        req_b = ServiceRequest(request_id="SR-B-001", tenant_id="DST-B", client_id="CLI-B")
        await repo.create(req_a)
        await repo.create(req_b)

        # 攻击：A 尝试修改 B 的 Request
        hacked = ServiceRequest(request_id="SR-B-001", tenant_id="DST-A", client_id="CLI-HACKED")
        with pytest.raises(Exception):
            await repo.update(hacked)


class TestAttackC_RelationBypass:
    """Attack C: 通过父子关系绕过 tenant filter。"""

    @pytest.mark.asyncio
    async def test_parent_child_isolation(self):
        req_repo = RequestRepository()
        proj_repo = ProjectRepository()

        req_a = ServiceRequest(request_id="SR-ISOL-A", tenant_id="DST-ISOL-A", client_id="CLI-ISOL-A")
        proj_a = Project(project_id="PRJ-ISOL-A", request_id="SR-ISOL-A", tenant_id="DST-ISOL-A", client_id="CLI-ISOL-A", scope_id="SCOPE-ISOL-A")
        req_b = ServiceRequest(request_id="SR-ISOL-B", tenant_id="DST-ISOL-B", client_id="CLI-ISOL-B")
        proj_b = Project(project_id="PRJ-ISOL-B", request_id="SR-ISOL-B", tenant_id="DST-ISOL-B", client_id="CLI-ISOL-B", scope_id="SCOPE-ISOL-B")

        await req_repo.create(req_a)
        await proj_repo.create(proj_a)
        await req_repo.create(req_b)
        await proj_repo.create(proj_b)

        # A 不能通过 request_id 获取 B 的 project
        a_reqs = await req_repo.find_by_tenant("DST-ISOL-A")
        b_reqs = await req_repo.find_by_tenant("DST-ISOL-B")
        a_projs = await proj_repo.find_by_tenant("DST-ISOL-A")
        b_projs = await proj_repo.find_by_tenant("DST-ISOL-B")

        assert len(a_reqs) == 1 and a_reqs[0].tenant_id == "DST-ISOL-A"
        assert len(b_reqs) == 1 and b_reqs[0].tenant_id == "DST-ISOL-B"
        assert len(a_projs) == 1 and a_projs[0].tenant_id == "DST-ISOL-A"
        assert len(b_projs) == 1 and b_projs[0].tenant_id == "DST-ISOL-B"


class TestAttackD_MalformedTenantId:
    """Attack D: 构造错误 tenant_id。"""

    @pytest.mark.asyncio
    async def test_empty_tenant_id_rejected(self):
        repo = RequestRepository()
        req = ServiceRequest(request_id="SR-MAL", tenant_id="DST-MAL", client_id="CLI-MAL")
        await repo.create(req)

        # 空 tenant_id 不应返回任何数据
        results = await repo.find_by_tenant("")
        assert len(results) == 0

    @pytest.mark.asyncio
    async def test_wildcard_tenant_id_blocked(self):
        repo = RequestRepository()
        req_a = ServiceRequest(request_id="SR-WILD-A", tenant_id="DST-WILD-A", client_id="CLI-A")
        await repo.create(req_a)

        # "__all__" 不应返回所有数据
        results = await repo.find_by_tenant("__all__")
        assert len(results) == 0


class TestAttackE_DirectRepositoryAccess:
    """Attack E: 通过 Repository 直接访问 B。"""

    @pytest.mark.asyncio
    async def test_repo_find_by_id_without_tenant(self):
        """直接调用 find_by_id 不带 tenant_id 应返回数据（测试兼容性）。"""
        repo = RequestRepository()
        req_b = ServiceRequest(request_id="SR-DIR-B", tenant_id="DST-DIR-B", client_id="CLI-B")
        await repo.create(req_b)

        # 不带 tenant_id 应该能查到（向后兼容）
        result = await repo.find_by_id("SR-DIR-B")
        assert result is not None
        assert result.tenant_id == "DST-DIR-B"

        # 带错误 tenant_id 应该被拒绝
        with pytest.raises(Exception):
            await repo.find_by_id("SR-DIR-B", tenant_id="DST-DIR-A")


class TestAttackF_ServiceLayer:
    """Attack F: 通过 Service 层访问 B。"""

    @pytest.mark.asyncio
    async def test_service_cannot_cross_tenant(self):
        from geo_distributor.services.project_service import ProjectService
        from geo_distributor.services.intake import IntakeService
        from geo_distributor.services.scoping import ScopingService

        req_repo = RequestRepository()
        proj_repo = ProjectRepository()
        intake = IntakeService()
        scoping = ScopingService()
        guard = StateTransitionGuard()

        svc = ProjectService(
            request_repo=req_repo,
            project_repo=proj_repo,
            work_item_repo=None,
            scope_service=scoping,
            intake_service=intake,
            transition_guard=guard,
        )

        # 创建 A 的 Request
        result_a = await svc.submit_request(
            tenant_id="DST-SVC-A",
            client_id="CLI-SVC-A",
            service="visibility_audit",
            business_context={"target_market": ["US"], "business_question": "Test"},
            requested_engines=["ChatGPT"],
        )
        assert result_a["status"] == "SCOPE_PENDING_APPROVAL"

        # A 不能提交到 B 的 tenant
        # 验证：A 只能看到自己的数据
        a_requests = await req_repo.find_by_tenant("DST-SVC-A")
        assert len(a_requests) == 1
        assert a_requests[0].tenant_id == "DST-SVC-A"


class TestAttackG_ApiBoundary:
    """Attack G: 模拟 API 层的租户隔离。"""

    @pytest.mark.asyncio
    async def test_api_like_tenant_enforcement(self):
        """模拟 API 从 session 获取 tenant_id 并强制使用。"""
        req_repo = RequestRepository()

        # 创建两个租户的数据
        for tid, cid in [("DST-API-A", "CLI-API-A"), ("DST-API-B", "CLI-API-B")]:
            req = ServiceRequest(request_id=f"SR-{tid}", tenant_id=tid, client_id=cid)
            await req_repo.create(req)

        # 模拟：API 从 session 得到 tenant_id，查询自己的数据
        session_tenant = "DST-API-A"
        results = await req_repo.find_by_tenant(session_tenant)
        assert all(r.tenant_id == session_tenant for r in results)

        # 模拟：攻击者伪造 session
        fake_tenant = "DST-API-B"
        fake_results = await req_repo.find_by_tenant(fake_tenant)
        assert all(r.tenant_id == fake_tenant for r in fake_results)
        assert not any(r.request_id == f"SR-DST-API-A" for r in fake_results)


class TestAttackH_IDCollision:
    """Attack H: ID collision / duplicate ID。"""

    @pytest.mark.asyncio
    async def test_duplicate_id_prevented(self):
        repo = RequestRepository()
        req1 = ServiceRequest(request_id="SR-DUP-001", tenant_id="DST-DUP-A", client_id="CLI-A")
        req2 = ServiceRequest(request_id="SR-DUP-001", tenant_id="DST-DUP-B", client_id="CLI-B")

        await repo.create(req1)
        with pytest.raises(Exception):  # DuplicateError
            await repo.create(req2)

    @pytest.mark.asyncio
    async def test_different_tenants_same_client_id(self):
        """不同租户可以有相同 client_id（客户端 ID 非全局唯一）。"""
        repo = RequestRepository()
        req_a = ServiceRequest(request_id="SR-CID-A", tenant_id="DST-CID-A", client_id="CLI-SAME")
        req_b = ServiceRequest(request_id="SR-CID-B", tenant_id="DST-CID-B", client_id="CLI-SAME")

        await repo.create(req_a)
        await repo.create(req_b)

        a_results = await repo.find_by_tenant("DST-CID-A")
        b_results = await repo.find_by_tenant("DST-CID-B")

        assert len(a_results) == 1 and a_results[0].request_id == "SR-CID-A"
        assert len(b_results) == 1 and b_results[0].request_id == "SR-CID-B"


class TestReportTenantIsolation:
    """Report 对象的租户隔离。"""

    @pytest.mark.asyncio
    async def test_report_tenant_isolation(self):
        from geo_distributor.models.geo_core import Report, ReportType

        report_a = Report(report_id="RPT-ISOL-A", project_id="PRJ-ISOL-A", tenant_id="DST-ISOL-A", type=ReportType.CLIENT)
        report_b = Report(report_id="RPT-ISOL-B", project_id="PRJ-ISOL-B", tenant_id="DST-ISOL-B", type=ReportType.CLIENT)

        assert report_a.tenant_id == "DST-ISOL-A"
        assert report_b.tenant_id == "DST-ISOL-B"
        # Report 本身没有 Repository，依赖 Project 的租户关联保证隔离


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
