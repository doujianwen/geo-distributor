"""E2E 完整业务闭环测试。"""

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from geo_distributor.models.tenant import Tenant, User, UserRole
from geo_distributor.models.request import ServiceRequest, BusinessContext, RequestStatus
from geo_distributor.models.scope import TechnicalScope
from geo_distributor.models.project import Project, ProjectStatus
from geo_distributor.models.work_item import WorkItem, WorkItemType, WorkItemStatus
from geo_distributor.models.geo_core import Report, ReportType, Evidence, EvidenceLevel
from geo_distributor.repositories.request_repo import RequestRepository
from geo_distributor.repositories.project_repo import ProjectRepository
from geo_distributor.services.intake import IntakeService
from geo_distributor.services.scoping import ScopingService
from geo_distributor.services.project_service import ProjectService
from geo_distributor.services.delivery import DeliveryService, ReportService
from geo_distributor.adapters.mock import MockMeasurementAdapter, MockMeasurementService
from geo_distributor.guards.state_transition import StateTransitionGuard
from geo_distributor.guards.idempotency import IdempotencyGuard


class TestE2EFullPipeline:
    @pytest.mark.asyncio
    async def test_full_distributor_to_hq_delivery(self):
        request_repo = RequestRepository()
        project_repo = ProjectRepository()
        intake_service = IntakeService()
        scoping_service = ScopingService()
        transition_guard = StateTransitionGuard()
        idempotency_guard = IdempotencyGuard()
        
        project_service = ProjectService(
            request_repo=request_repo,
            project_repo=project_repo,
            work_item_repo=None,
            scope_service=scoping_service,
            intake_service=intake_service,
            transition_guard=transition_guard,
        )
        
        distributor_tenant = "DST-TEST-001"
        client_id = "CLI-E2E-001"
        
        request_result = await project_service.submit_request(
            tenant_id=distributor_tenant,
            client_id=client_id,
            service="visibility_audit",
            business_context={
                "target_market": ["US"],
                "target_products": ["sensors"],
                "business_question": "Test question",
            },
            requested_engines=["ChatGPT"],
            idempotency_key="e2e-test-key-001",
        )
        
        assert request_result["status"] == "SCOPE_PENDING_APPROVAL"
        request_id = request_result["request_id"]
        scope_id = request_result["scope_id"]
        
        request = await request_repo.find_by_id(request_id)
        assert request is not None
        assert request.status == RequestStatus.SCOPE_PENDING_APPROVAL
        
        approval_result = await project_service.approve_scope(
            request_id=request_id,
            approver_id="HQ-ADMIN-001",
        )
        assert approval_result["status"] == "APPROVED"
        project_id = approval_result["project_id"]
        
        mock_adapter = MockMeasurementAdapter()
        mock_service = MockMeasurementService(adapter=mock_adapter)
        
        measurement_result = await mock_service.execute_measurement(
            project_id=project_id,
            queries=["best industrial sensors manufacturer", "industrial sensor solutions"],
            scope={"markets": ["US"], "engines": ["ChatGPT"]},
        )
        
        assert measurement_result["observation_count"] > 0
        observations = measurement_result["observations"]
        findings = measurement_result["findings"]
        
        delivery_service = DeliveryService()
        delivery_result = await delivery_service.execute_delivery(
            project_id=project_id,
            tenant_id=distributor_tenant,
            scope_version=1,
            observations=observations,
            findings=findings,
            executed_by="HQ-OPERATOR-001",
        )
        
        assert delivery_result["status"] == "DELIVERED"
        assert delivery_result["qa_result"]["passed"] is True
        
        report_id = delivery_result["report_id"]
        report = await delivery_service.report_service.get_report(report_id)
        assert report is not None
        assert report["is_client_safe"] is True
        
        content = report["content"]
        assert "executive_summary" in content
        assert "visibility_summary" in content
        assert "key_findings" in content
        assert "limitations" in content
        assert "next_steps" in content
        
        print(f"E2E TEST PASSED - Request: {request_id}, Project: {project_id}, Report: {report_id}")
