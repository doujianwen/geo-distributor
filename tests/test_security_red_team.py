"""Security Red-Team 攻击测试（P0 必须）。

验证：
- Tenant Isolation（Distributor A 无法访问 B 的数据）
- RBAC Role Validation（角色权限边界）
- State Machine Attacks（非法状态转换）
- Idempotency Attacks（并发/冲突）
- Client-Safe Leakage（API 数据泄漏）
"""

import pytest
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from geo_distributor.models.tenant import Tenant, User, UserRole
from geo_distributor.models.request import ServiceRequest, RequestStatus
from geo_distributor.models.project import Project, ProjectStatus
from geo_distributor.models.geo_core import Report, ReportType, Evidence, EvidenceLevel
from geo_distributor.repositories.request_repo import RequestRepository
from geo_distributor.repositories.project_repo import ProjectRepository
from geo_distributor.services.project_service import ProjectService
from geo_distributor.services.project_service import ProjectService
from geo_distributor.guards.state_transition import StateTransitionGuard
from geo_distributor.guards.idempotency import IdempotencyGuard


@pytest.fixture
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


class TestTenantIsolation:
    """租户隔离攻击测试（I-01, I-02, I-03）。"""

    @pytest.mark.asyncio
    async def test_distributor_a_cannot_access_distributor_b_request(self):
        """攻击：Distributor A 直接访问 Distributor B 的 Request ID。"""
        request_repo = RequestRepository()
        
        # 创建两个租户的 Request
        req_a = ServiceRequest(
            request_id="SR-A-001",
            tenant_id="DST-A",
            client_id="CLI-A-001",
        )
        req_b = ServiceRequest(
            request_id="SR-B-001",
            tenant_id="DST-B",
            client_id="CLI-B-001",
        )
        await request_repo.create(req_a)
        await request_repo.create(req_b)
        
        # 攻击：A 尝试直接访问 B 的 Request
        with pytest.raises(Exception):  # PermissionError or NotFoundError
            await request_repo.find_by_id("SR-B-001", tenant_id="DST-A")
        
        # 验证：A 只能看到自己的数据
        a_requests = await request_repo.find_by_tenant("DST-A")
        assert len(a_requests) == 1
        assert a_requests[0].request_id == "SR-A-001"
        assert a_requests[0].tenant_id == "DST-A"

    @pytest.mark.asyncio
    async def test_distributor_a_cannot_access_distributor_b_project(self):
        """攻击：Distributor A 直接访问 Distributor B 的 Project ID。"""
        project_repo = ProjectRepository()

        proj_a = Project(
            project_id="PRJ-A-001",
            request_id="SR-A-001",
            tenant_id="DST-A",
            client_id="CLI-A-001",
            scope_id="SCOPE-A-001",
        )
        proj_b = Project(
            project_id="PRJ-B-001",
            request_id="SR-B-001",
            tenant_id="DST-B",
            client_id="CLI-B-001",
            scope_id="SCOPE-B-001",
        )
        await project_repo.create(proj_a)
        await project_repo.create(proj_b)

        # 攻击：A 尝试直接访问 B 的 Project（带 tenant_id 验证）
        with pytest.raises(Exception):
            await project_repo.find_by_id("PRJ-B-001", tenant_id="DST-A")

        # 验证：A 只能看到自己的 Project
        a_projects = await project_repo.find_by_tenant("DST-A")
        assert len(a_projects) == 1
        assert a_projects[0].project_id == "PRJ-A-001"
        assert a_projects[0].tenant_id == "DST-A"

        # B 只能看到自己的 Project
        b_projects = await project_repo.find_by_tenant("DST-B")
        assert len(b_projects) == 1
        assert b_projects[0].project_id == "PRJ-B-001"
        assert b_projects[0].tenant_id == "DST-B"

    @pytest.mark.asyncio
    async def test_client_id_collision_attack(self):
        """攻击：使用 B 的 Client ID 查询 A 的数据。"""
        request_repo = RequestRepository()
        
        req_a = ServiceRequest(
            request_id="SR-A-001",
            tenant_id="DST-A",
            client_id="CLI-A-001",
        )
        req_b = ServiceRequest(
            request_id="SR-B-001",
            tenant_id="DST-B",
            client_id="CLI-B-001",
        )
        await request_repo.create(req_a)
        await request_repo.create(req_b)
        
        # 攻击：A 尝试用 B 的 client_id 查询
        results = await request_repo.find_by_client("CLI-B-001", tenant_id="DST-A")
        assert len(results) == 0  # 应该返回空，因为 CLI-B-001 不在 DST-A 中

    @pytest.mark.asyncio
    async def test_tenant_isolation_in_full_pipeline(self):
        """完整流程中的租户隔离验证。"""
        request_repo = RequestRepository()
        project_repo = ProjectRepository()
        
        # 创建两个 Distributor 的数据
        req_a = ServiceRequest(request_id="SR-ISOL-A", tenant_id="DST-ISOL-A", client_id="CLI-ISOL-A-001")
        req_b = ServiceRequest(request_id="SR-ISOL-B", tenant_id="DST-ISOL-B", client_id="CLI-ISOL-B-001")
        await request_repo.create(req_a)
        await request_repo.create(req_b)
        
        proj_a = Project(project_id="PRJ-ISOL-A", request_id="SR-ISOL-A", tenant_id="DST-ISOL-A", client_id="CLI-ISOL-A-001", scope_id="SCOPE-ISOL-A")
        proj_b = Project(project_id="PRJ-ISOL-B", request_id="SR-ISOL-B", tenant_id="DST-ISOL-B", client_id="CLI-ISOL-B-001", scope_id="SCOPE-ISOL-B")
        await project_repo.create(proj_a)
        await project_repo.create(proj_b)
        
        # 交叉访问测试
        a_reqs = await request_repo.find_by_tenant("DST-ISOL-A")
        b_reqs = await request_repo.find_by_tenant("DST-ISOL-B")
        a_projs = await project_repo.find_by_tenant("DST-ISOL-A")
        b_projs = await project_repo.find_by_tenant("DST-ISOL-B")
        
        assert len(a_reqs) == 1 and a_reqs[0].request_id == "SR-ISOL-A"
        assert len(b_reqs) == 1 and b_reqs[0].request_id == "SR-ISOL-B"
        assert len(a_projs) == 1 and a_projs[0].project_id == "PRJ-ISOL-A"
        assert len(b_projs) == 1 and b_projs[0].project_id == "PRJ-ISOL-B"
        
        # 验证不能跨租户访问
        assert all(r.tenant_id == "DST-ISOL-A" for r in a_reqs)
        assert all(r.tenant_id == "DST-ISOL-B" for r in b_reqs)


class TestRBACBypass:
    """RBAC 绕过攻击测试。"""

    @pytest.mark.asyncio
    async def test_distributor_cannot_execute_hq_operations(self):
        """攻击：Distributor 尝试执行 HQ 操作。"""
        guard = StateTransitionGuard()
        
        # Distributor 不能执行 INTAKE_REVIEW → SCOPING
        result = guard.validate_request_transition(
            current_status="intake_review",
            target_status="scoping",
            user_role="distributor_user",
        )
        assert result.success is False
        assert result.error_code == "PERMISSION_DENIED"
        
        # Distributor 不能执行 APPROVAL
        result = guard.validate_request_transition(
            current_status="scope_pending_approval",
            target_status="approved",
            user_role="distributor_admin",
        )
        assert result.success is False
        assert result.error_code == "PERMISSION_DENIED"

    @pytest.mark.asyncio
    async def test_unauthorized_role_cannot_transition(self):
        """攻击：未授权角色尝试状态转换。"""
        guard = StateTransitionGuard()
        
        test_cases = [
            ("draft", "submitted", "hq_technical", False),  # HQ 不能提交
            ("approved", "in_execution", "distributor_admin", False),  # Distributor 不能启动
            ("delivered", "accepted", "hq_operator", False),  # Operator 不能接受
        ]
        
        for current, target, role, expected_success in test_cases:
            result = guard.validate_request_transition(current, target, role)
            assert result.success == expected_success, f"Expected {expected_success} for {current}→{target} as {role}"


class TestStateMachineAttacks:
    """状态机攻击测试。"""

    @pytest.mark.asyncio
    async def test_skip_states_attack(self):
        """攻击：跳过中间状态直接到最终状态。"""
        guard = StateTransitionGuard()
        
        # DRAFT → DELIVERED（跳过所有中间状态）
        result = guard.validate_request_transition(
            current_status="draft",
            target_status="delivered",
            user_role="hq_admin",
        )
        assert result.success is False
        assert result.error_code == "INVALID_TRANSITION"

    @pytest.mark.asyncio
    async def test_reverse_transition_attack(self):
        """攻击：逆向状态转换。"""
        guard = StateTransitionGuard()
        
        # APPROVED → DRAFT（逆向）
        result = guard.validate_request_transition(
            current_status="approved",
            target_status="draft",
            user_role="hq_admin",
        )
        assert result.success is False
        assert result.error_code == "INVALID_TRANSITION"

    @pytest.mark.asyncio
    async def test_circular_transition_attack(self):
        """攻击：循环状态转换。"""
        guard = StateTransitionGuard()
        
        # ACCEPTED → SUBMITTED（不可能）
        result = guard.validate_request_transition(
            current_status="accepted",
            target_status="submitted",
            user_role="hq_admin",
        )
        assert result.success is False
        assert result.error_code == "INVALID_TRANSITION"


class TestIdempotencyAttacks:
    """幂等性攻击测试。"""

    @pytest.mark.asyncio
    async def test_same_key_different_payload(self):
        """攻击：相同 Key 不同 Payload。"""
        guard = IdempotencyGuard()
        
        # 第一次提交
        result1 = guard.check_and_store(
            key="attack-key-001",
            payload={"client_id": "CLI-001"},
            result={"request_id": "SR-001"},
        )
        assert result1["stored"] is True
        
        # 第二次提交相同 Key 不同 Payload
        result2 = guard.check_and_store(
            key="attack-key-001",
            payload={"client_id": "CLI-002"},  # 不同
            result={"request_id": "SR-002"},
        )
        assert result2["error"] == "IDEMPOTENCY_CONFLICT"

    @pytest.mark.asyncio
    async def test_concurrent_requests_same_key(self):
        """攻击：并发请求使用相同 Key。"""
        guard = IdempotencyGuard()
        
        results = []
        for i in range(5):
            result = guard.check_and_store(
                key="concurrent-key",
                payload={"index": i},
                result={"request_id": f"SR-CONC-{i}"},
            )
            results.append(result)
        
        # 只有第一个应该成功存储
        stored_count = sum(1 for r in results if r.get("stored"))
        conflict_count = sum(1 for r in results if r.get("error") == "IDEMPOTENCY_CONFLICT")
        
        assert stored_count == 1
        assert conflict_count == 4


class TestClientSafeLeakage:
    """Client-safe 数据泄漏攻击测试（I-03）。"""

    @pytest.mark.asyncio
    async def test_raw_response_excluded_from_client_report(self):
        """攻击：RawResponse 不应出现在 Client-safe 报告中。"""
        from geo_distributor.models.geo_core import Report, ReportType
        
        report = Report(
            report_id="RPT-LEAK-TEST",
            project_id="PRJ-TEST",
            tenant_id="DST-TEST",
            type=ReportType.CLIENT,
        )
        
        # 包含敏感字段的内容
        content = {
            "executive_summary": "Summary text",
            "visibility_summary": {"score": 72},
            "raw_response": {"debug": "internal data"},  # 应被过滤
            "parser_output": {"parsed": "data"},  # 应被过滤
            "provider_internals": {"api_key": "secret"},  # 应被过滤
            "browser_logs": ["log1", "log2"],  # 应被过滤
            "key_findings": [{"finding": "test"}],
        }
        
        report.add_version(content, is_client_safe=True)
        
        latest = report.get_latest_version()
        content_str = str(latest.content)
        
        # 验证敏感字段被过滤
        assert "raw_response" not in content_str
        assert "parser_output" not in content_str
        assert "provider_internals" not in content_str
        assert "browser_logs" not in content_str
        assert "debug" not in content_str
        assert "internal data" not in content_str
        assert "api_key" not in content_str
        
        # 验证安全字段保留
        assert "executive_summary" in content_str
        assert "visibility_summary" in content_str
        assert "key_findings" in content_str

    @pytest.mark.asyncio
    async def test_evidence_grading_excluded_from_client_report(self):
        """攻击：Evidence grading 细节不应出现在 Client-safe 报告中。"""
        from geo_distributor.models.geo_core import Report, ReportType
        
        report = Report(
            report_id="RPT-EVIDENCE-TEST",
            project_id="PRJ-TEST",
            tenant_id="DST-TEST",
            type=ReportType.CLIENT,
        )
        
        content = {
            "findings": [{"statement": "Brand not mentioned"}],
            "evidence_grading": {
                "method": "manual_review",
                "scores": {"obs_1": 0.8, "obs_2": 0.6},
                "notes": "Grading details"
            },
            "technical_notes": "Internal technical assessment",
        }
        
        report.add_version(content, is_client_safe=True)
        
        latest = report.get_latest_version()
        content_str = str(latest.content)
        
        assert "evidence_grading" not in content_str
        assert "technical_notes" not in content_str
        assert "findings" in content_str

    @pytest.mark.asyncio
    async def test_technical_report_contains_full_data(self):
        """验证 Technical Report 可以包含完整数据。"""
        from geo_distributor.models.geo_core import Report, ReportType
        
        report = Report(
            report_id="RPT-TECH-TEST",
            project_id="PRJ-TEST",
            tenant_id="DST-TEST",
            type=ReportType.TECHNICAL,
        )
        
        content = {
            "executive_summary": "Executive summary",
            "raw_response": {"debug": "internal"},
            "parser_output": {"parsed": "data"},
            "evidence_grading": {"scores": {}},
        }
        
        report.add_version(content, is_client_safe=False)  # Technical report
        
        latest = report.get_latest_version()
        content_str = str(latest.content)
        
        # Technical report 应包含所有数据
        assert "raw_response" in content_str
        assert "parser_output" in content_str
        assert "evidence_grading" in content_str


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
