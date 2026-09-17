"""Project Service（Sprint 0）。

职责：管理 Project 生命周期，协调 Intake → Scope → Execution → Delivery。
"""

from typing import Optional, Dict, Any, List
import logging
import uuid

logger = logging.getLogger(__name__)


class ProjectService:
    """Project 服务 — 管理 Project 全生命周期。"""

    def __init__(self, request_repo, project_repo, work_item_repo, scope_service, intake_service, transition_guard):
        self._request_repo = request_repo
        self._project_repo = project_repo
        self._work_item_repo = work_item_repo
        self._scope_service = scope_service
        self._intake_service = intake_service
        self._transition_guard = transition_guard

    async def submit_request(
        self,
        tenant_id: str,
        client_id: str,
        service: str,
        business_context: Dict[str, Any],
        requested_engines: Optional[List[str]] = None,
        idempotency_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        """提交 Service Request。

        流程：创建 Request → Intake Review → 决定 SCOPING 或 CLARIFICATION_REQUIRED
        """
        from ..models.request import ServiceRequest, BusinessContext, RequestStatus
        from ..guards.state_transition import StateTransitionGuard

        request_id = f"SR-{uuid.uuid4().hex[:8].upper()}"

        # 创建 Request
        biz_context = BusinessContext(
            target_market=business_context.get("target_market", []),
            target_products=business_context.get("target_products", []),
            target_customer=business_context.get("target_customer", ""),
            known_competitors=business_context.get("known_competitors", []),
            business_question=business_context.get("business_question", ""),
        )

        request = ServiceRequest(
            request_id=request_id,
            tenant_id=tenant_id,
            client_id=client_id,
            service=service,
            requested_engines=requested_engines or [],
            business_context=biz_context,
            idempotency_key=idempotency_key,
        )

        await self._request_repo.create(request)

        # Intake Review
        intake_result = await self._intake_service.review(request)

        if intake_result["recommendation"] == "CLARIFICATION_REQUIRED":
            # 状态转换守卫：SUBMITTED → CLARIFICATION_REQUIRED
            guard_result = self._transition_guard.validate_request_transition(
                current_status="submitted",
                target_status="clarification_required",
                user_role="hq_technical",
            )
            if not guard_result.success:
                raise PermissionError(f"State transition blocked: {guard_result.error_code}")

            # 进入澄清状态
            request.transition_to(RequestStatus.CLARIFICATION_REQUIRED)
            request.clarification_request = intake_result["clarification_request"]
            await self._request_repo.update(request)
            return {
                "status": "CLARIFICATION_REQUIRED",
                "request_id": request_id,
                "missing_fields": intake_result["missing_fields"],
                "questions": intake_result["clarification_request"]["questions"],
            }

        # 进入 Scoping（通过Guard验证每个转换）
        transitions = [
            ("draft", "submitted", "distributor_admin"),
            ("submitted", "intake_review", "hq_technical"),
            ("intake_review", "scoping", "hq_technical"),
        ]
        for current, target, role in transitions:
            guard_result = self._transition_guard.validate_request_transition(
                current_status=current,
                target_status=target,
                user_role=role,
            )
            if not guard_result.success:
                raise PermissionError(f"State transition blocked: {guard_result.error_code}")
            # 执行转换
            if current == "draft" and target == "submitted":
                request.transition_to(RequestStatus.SUBMITTED)
            elif current == "submitted" and target == "intake_review":
                request.transition_to(RequestStatus.INTAKE_REVIEW)
            elif current == "intake_review" and target == "scoping":
                request.transition_to(RequestStatus.SCOPING)
        await self._request_repo.update(request)

        # 生成 Technical Scope
        scope = await self._scope_service.create_scope(
            request_id=request_id,
            tenant_id=tenant_id,
            business_context=business_context,
            service=service,
            requested_engines=requested_engines,
        )

        # 更新 Request
        request.scope_id = scope["scope_id"]
        request.transition_to(RequestStatus.SCOPE_PENDING_APPROVAL)
        await self._request_repo.update(request)

        return {
            "status": "SCOPE_PENDING_APPROVAL",
            "request_id": request_id,
            "scope_id": scope["scope_id"],
        }

    async def approve_scope(
        self,
        request_id: str,
        approver_id: str,
    ) -> Dict[str, Any]:
        """批准 Scope，创建 Project。"""
        from ..models.request import RequestStatus
        from ..models.project import Project, ProjectStatus

        request = await self._request_repo.find_by_id(request_id)
        if not request:
            raise ValueError(f"Request {request_id} not found")

        # 状态转换守卫：SCOPE_PENDING_APPROVAL → APPROVED
        guard_result = self._transition_guard.validate_request_transition(
            current_status="scope_pending_approval",
            target_status="approved",
            user_role="hq_management",
        )
        if not guard_result.success:
            return {
                "success": False,
                "error": guard_result.error_code,
                "message": guard_result.error_message,
            }

        # 创建 Project
        project_id = f"PRJ-{uuid.uuid4().hex[:8].upper()}"
        project = Project(
            project_id=project_id,
            request_id=request_id,
            tenant_id=request.tenant_id,
            client_id=request.client_id,
            scope_id=request.scope_id,
            status=ProjectStatus.APPROVED,
        )
        await self._project_repo.create(project)

        # 更新 Request（已通过Guard验证）
        request.project_id = project_id
        request.transition_to(RequestStatus.APPROVED)
        await self._request_repo.update(request)

        logger.info("Project approved: %s for request %s", project_id, request_id)
        return {
            "project_id": project_id,
            "request_id": request_id,
            "scope_id": request.scope_id,
            "status": "APPROVED",
        }

    async def start_execution(
        self,
        project_id: str,
        user_role: str,
    ) -> Dict[str, Any]:
        """启动 Project 执行。"""
        from ..models.project import ProjectStatus

        project = await self._project_repo.find_by_id(project_id)
        if not project:
            raise ValueError(f"Project {project_id} not found")

        # 状态转换守卫
        guard_result = self._transition_guard.validate_project_transition(
            current_status=project.status.value,
            target_status="in_execution",
            user_role=user_role,
            context={"scope_approved": True},
        )

        if not guard_result.success:
            return {
                "success": False,
                "error": guard_result.error_code,
                "message": guard_result.error_message,
            }

        # 执行转换
        project.transition_to(ProjectStatus.IN_EXECUTION)
        await self._project_repo.update(project)

        logger.info("Project execution started: %s", project_id)
        return {
            "success": True,
            "project_id": project_id,
            "status": "IN_EXECUTION",
        }
