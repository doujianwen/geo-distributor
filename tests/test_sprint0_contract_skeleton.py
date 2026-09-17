"""Sprint 0 测试 — Contract Skeleton 验证。

验证内容：
1. Tenant/User 数据模型
2. Service Request 状态机
3. Technical Scope 生成
4. Project 状态机
5. Work Item 管理
6. State Transition Guard
7. Idempotency Guard
8. Intake Service
9. Repository 隔离
"""

import pytest
import asyncio
import sys
from pathlib import Path

# 添加项目根目录到 path
sys.path.insert(0, str(Path(__file__).parent.parent))

from geo_distributor.models.tenant import Tenant, TenantStatus, User, UserRole, AuditEntry
from geo_distributor.models.request import ServiceRequest, BusinessContext, RequestStatus
from geo_distributor.models.scope import TechnicalScope
from geo_distributor.models.project import Project, ProjectStatus
from geo_distributor.models.work_item import WorkItem, WorkItemType, WorkItemStatus
from geo_distributor.models.geo_core import Evidence, EvidenceLevel, Report, ReportType
from geo_distributor.guards.state_transition import StateTransitionGuard
from geo_distributor.guards.idempotency import IdempotencyGuard
from geo_distributor.services.intake import IntakeService
from geo_distributor.repositories.request_repo import RequestRepository
from geo_distributor.repositories.project_repo import ProjectRepository


# ====================================================================
# Test 1: Tenant & Identity
# ====================================================================

class TestTenant:
    def test_create_tenant(self):
        tenant = Tenant(
            tenant_id="DST-001",
            name="Test Distributor",
            contact_email="test@example.com",
        )
        assert tenant.tenant_id == "DST-001"
        assert tenant.is_active()

    def test_suspended_tenant_not_active(self):
        tenant = Tenant(
            tenant_id="DST-002",
            name="Suspended",
            contact_email="suspended@example.com",
            status=TenantStatus.SUSPENDED,
        )
        assert not tenant.is_active()


# ====================================================================
# Test 2: Service Request State Machine
# ====================================================================

class TestRequestStateMachine:
    def test_draft_to_submitted(self):
        req = ServiceRequest(
            request_id="SR-001",
            tenant_id="DST-001",
            client_id="CLI-001",
        )
        assert req.status == RequestStatus.DRAFT
        assert req.transition_to(RequestStatus.SUBMITTED)
        assert req.status == RequestStatus.SUBMITTED

    def test_submitted_to_intake_review(self):
        req = ServiceRequest(request_id="SR-002", tenant_id="DST-001", client_id="CLI-001")
        req.transition_to(RequestStatus.SUBMITTED)
        assert req.transition_to(RequestStatus.INTAKE_REVIEW)

    def test_invalid_transition(self):
        req = ServiceRequest(request_id="SR-003", tenant_id="DST-001", client_id="CLI-001")
        # DRAFT → DELIVERED is invalid
        assert not req.transition_to(RequestStatus.DELIVERED)
        assert req.status == RequestStatus.DRAFT

    def test_clarification_loop(self):
        req = ServiceRequest(request_id="SR-004", tenant_id="DST-001", client_id="CLI-001")
        req.transition_to(RequestStatus.SUBMITTED)
        req.transition_to(RequestStatus.INTAKE_REVIEW)
        req.transition_to(RequestStatus.CLARIFICATION_REQUIRED)
        # Can go back to INTAKE_REVIEW after clarification
        assert req.transition_to(RequestStatus.INTAKE_REVIEW)


# ====================================================================
# Test 3: Technical Scope
# ====================================================================

class TestTechnicalScope:
    def test_create_scope(self):
        scope = TechnicalScope(
            scope_id="SCOPE-001",
            request_id="SR-001",
            tenant_id="DST-001",
            markets=["US"],
            engines=["ChatGPT"],
        )
        assert scope.markets == ["US"]
        assert scope.version == 1

    def test_scope_change_detection(self):
        scope1 = TechnicalScope(
            scope_id="SCOPE-001",
            request_id="SR-001",
            tenant_id="DST-001",
            markets=["US"],
            engines=["ChatGPT"],
            diagnosis=False,
        )
        scope2 = TechnicalScope(
            scope_id="SCOPE-001",
            request_id="SR-001",
            tenant_id="DST-001",
            markets=["US", "EU"],  # Changed
            engines=["ChatGPT"],
            diagnosis=True,  # Changed
        )
        assert scope1.requires_scope_change(scope2)


# ====================================================================
# Test 4: Project State Machine
# ====================================================================

class TestProjectStateMachine:
    def test_approved_to_in_execution(self):
        proj = Project(
            project_id="PRJ-001",
            request_id="SR-001",
            tenant_id="DST-001",
            client_id="CLI-001",
            scope_id="SCOPE-001",
        )
        assert proj.status == ProjectStatus.APPROVED
        assert proj.transition_to(ProjectStatus.IN_EXECUTION)
        assert proj.status == ProjectStatus.IN_EXECUTION

    def test_blocked_to_in_execution(self):
        proj = Project(
            project_id="PRJ-002",
            request_id="SR-002",
            tenant_id="DST-001",
            client_id="CLI-001",
            scope_id="SCOPE-002",
        )
        proj.transition_to(ProjectStatus.IN_EXECUTION)
        proj.set_blocked("Missing access", "Provide API key", "CLIENT")
        # set_blocked only sets the reason, status stays IN_EXECUTION
        assert proj.blocked_reason is not None
        assert proj.blocked_reason.reason == "Missing access"
        # Transition to BLOCKED explicitly
        assert proj.transition_to(ProjectStatus.BLOCKED)
        assert proj.status == ProjectStatus.BLOCKED
        # Can unblock
        proj.clear_blocked()
        assert proj.transition_to(ProjectStatus.IN_EXECUTION)

    def test_qa_to_rework(self):
        proj = Project(
            project_id="PRJ-003",
            request_id="SR-003",
            tenant_id="DST-001",
            client_id="CLI-001",
            scope_id="SCOPE-003",
        )
        proj.transition_to(ProjectStatus.IN_EXECUTION)
        proj.transition_to(ProjectStatus.QA)
        assert proj.transition_to(ProjectStatus.REWORK)
        assert proj.status == ProjectStatus.REWORK

    def test_delivered_to_accepted(self):
        proj = Project(
            project_id="PRJ-004",
            request_id="SR-004",
            tenant_id="DST-001",
            client_id="CLI-001",
            scope_id="SCOPE-004",
        )
        proj.transition_to(ProjectStatus.IN_EXECUTION)
        proj.transition_to(ProjectStatus.QA)
        proj.transition_to(ProjectStatus.DELIVERED)
        assert proj.transition_to(ProjectStatus.ACCEPTED)

    def test_invalid_project_transition(self):
        proj = Project(
            project_id="PRJ-005",
            request_id="SR-005",
            tenant_id="DST-001",
            client_id="CLI-001",
            scope_id="SCOPE-005",
        )
        # APPROVED → CANCELLED is valid, but APPROVED → DELIVERED is not
        assert not proj.transition_to(ProjectStatus.DELIVERED)


# ====================================================================
# Test 5: Work Item
# ====================================================================

class TestWorkItem:
    def test_create_and_complete(self):
        wi = WorkItem(
            work_item_id="WI-001",
            project_id="PRJ-001",
            tenant_id="DST-001",
            type=WorkItemType.MEASUREMENT,
        )
        assert wi.status == WorkItemStatus.PENDING
        assert wi.transition_to(WorkItemStatus.IN_PROGRESS)
        assert wi.transition_to(WorkItemStatus.COMPLETED)
        assert wi.completed_at is not None

    def test_failed_and_retry(self):
        wi = WorkItem(
            work_item_id="WI-002",
            project_id="PRJ-001",
            tenant_id="DST-001",
            type=WorkItemType.MEASUREMENT,
        )
        wi.transition_to(WorkItemStatus.IN_PROGRESS)
        wi.transition_to(WorkItemStatus.FAILED, error="API timeout")
        # Can retry
        assert wi.transition_to(WorkItemStatus.IN_PROGRESS)


# ====================================================================
# Test 6: State Transition Guard
# ====================================================================

class TestStateTransitionGuard:
    def test_valid_request_transition(self):
        result = StateTransitionGuard.validate_request_transition(
            current_status="draft",
            target_status="submitted",
            user_role="distributor_admin",
        )
        assert result.success

    def test_invalid_request_transition(self):
        result = StateTransitionGuard.validate_request_transition(
            current_status="draft",
            target_status="delivered",
            user_role="distributor_admin",
        )
        assert not result.success
        assert result.error_code == "INVALID_TRANSITION"

    def test_permission_denied(self):
        # distributor_user cannot move from INTAKE_REVIEW to SCOPING
        # (only hq roles can do this)
        result = StateTransitionGuard.validate_request_transition(
            current_status="intake_review",
            target_status="scoping",
            user_role="distributor_user",
        )
        assert not result.success
        assert result.error_code == "PERMISSION_DENIED"


# ====================================================================
# Test 7: Idempotency Guard
# ====================================================================

class TestIdempotencyGuard:
    def test_first_request_stored(self):
        guard = IdempotencyGuard()
        result = guard.check_and_store(
            key="test-key-1",
            payload={"client_id": "CLI-001"},
            result={"request_id": "SR-001"},
        )
        assert result["idempotent"] == False
        assert result["stored"] == True

    def test_duplicate_request_returns_original(self):
        guard = IdempotencyGuard()
        guard.check_and_store(
            key="test-key-2",
            payload={"client_id": "CLI-001"},
            result={"request_id": "SR-002"},
        )
        # Same key, same payload
        result = guard.check_and_store(
            key="test-key-2",
            payload={"client_id": "CLI-001"},
            result={"request_id": "SR-002-NEW"},  # Different result should be ignored
        )
        assert result["idempotent"] == True
        assert result["result"]["request_id"] == "SR-002"

    def test_different_payload_conflict(self):
        guard = IdempotencyGuard()
        guard.check_and_store(
            key="test-key-3",
            payload={"client_id": "CLI-001"},
            result={"request_id": "SR-003"},
        )
        # Same key, different payload
        result = guard.check_and_store(
            key="test-key-3",
            payload={"client_id": "CLI-002"},  # Different
            result={"request_id": "SR-003-NEW"},
        )
        assert result["idempotent"] == False
        assert result["error"] == "IDEMPOTENCY_CONFLICT"


# ====================================================================
# Test 8: Intake Service
# ====================================================================

class TestIntakeService:
    def test_complete_request(self):
        service = IntakeService()
        req = ServiceRequest(
            request_id="SR-001",
            tenant_id="DST-001",
            client_id="CLI-001",
            service="visibility_audit",
            business_context=BusinessContext(
                target_market=["US"],
                target_products=["product-1"],
                business_question="Why no mention?",
            ),
        )
        result = asyncio.run(service.review(req))
        assert result["status"] == "COMPLETE"
        assert result["recommendation"] == "SCOPING"

    def test_incomplete_request(self):
        service = IntakeService()
        req = ServiceRequest(
            request_id="SR-002",
            tenant_id="DST-001",
            client_id="CLI-001",
            service="visibility_audit",
            # Missing business_context
        )
        result = asyncio.run(service.review(req))
        assert result["status"] == "INCOMPLETE"
        assert result["recommendation"] == "CLARIFICATION_REQUIRED"
        assert "business_context" in result["missing_fields"]


# ====================================================================
# Test 9: Repository Isolation
# ====================================================================

class TestRepositoryIsolation:
    @pytest.mark.asyncio
    async def test_tenant_isolation(self):
        repo = RequestRepository()

        # Create requests for different tenants
        req1 = ServiceRequest(
            request_id="SR-DST1-001",
            tenant_id="DST-001",
            client_id="CLI-001",
        )
        req2 = ServiceRequest(
            request_id="SR-DST2-001",
            tenant_id="DST-002",
            client_id="CLI-002",
        )

        await repo.create(req1)
        await repo.create(req2)

        # DST-001 should only see its own requests
        dst1_requests = await repo.find_by_tenant("DST-001")
        assert len(dst1_requests) == 1
        assert dst1_requests[0].request_id == "SR-DST1-001"

        dst2_requests = await repo.find_by_tenant("DST-002")
        assert len(dst2_requests) == 1
        assert dst2_requests[0].request_id == "SR-DST2-001"


# ====================================================================
# Test 10: Evidence & Report Versioning
# ====================================================================

class TestEvidenceAndReport:
    def test_evidence_levels(self):
        evidence = Evidence(
            evidence_id="EVD-001",
            observation_id="OBS-001",
            source_type="url",
            content="https://example.com",
            level=EvidenceLevel.E2,
        )
        assert evidence.level == EvidenceLevel.E2

    def test_report_versioning(self):
        report = Report(
            report_id="RPT-001",
            project_id="PRJ-001",
            tenant_id="DST-001",
            type=ReportType.CLIENT,
            title="GEO Visibility Report",
        )
        # Add versions
        report.add_version({"summary": "v1 content"}, is_client_safe=True)
        report.add_version({"summary": "v2 content"}, is_client_safe=True, notes="Updated")

        assert len(report.versions) == 2
        assert report.versions[0].version == 1
        assert report.versions[1].version == 2

        latest = report.get_latest_version()
        assert latest.version == 2
        assert latest.notes == "Updated"
