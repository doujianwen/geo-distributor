"""State Transition Guard（Sprint 0 — P0 必须）。

基于 08-统一状态机 实现状态转换守卫。
所有状态变更必须通过此守卫，禁止直接修改状态字段。

规则：
1. 检查目标状态是否在当前状态的有效转换图中
2. 检查用户角色是否有权限执行该转换
3. 返回 TransitionResult 包含 success/error_code/message
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
import logging

from ..models.request import RequestStatus, REQUEST_TRANSITIONS

logger = logging.getLogger(__name__)


@dataclass
class TransitionResult:
    """状态转换结果。"""
    success: bool
    error_code: Optional[str] = None
    message: Optional[str] = None
    required_permissions: List[str] = field(default_factory=list)


class StateTransitionGuard:
    """状态转换守卫。

    验证:
    - 目标状态是否在合法转换图中
    - 用户角色是否有权限执行转换
    """

    # 角色权限映射（谁可以触发什么类型的转换）
    ROLE_PERMISSIONS: Dict[str, List[str]] = {
        "distributor_admin": ["submit_request", "accept_delivery", "request_changes"],
        "distributor_user": ["submit_request", "accept_delivery"],
        "hq_technical": [
            "intake_review",
            "request_clarification",
            "start_scoping",
            "submit_scope",
            "approve_scope",
            "reject_scope",
            "reject_request",
            "start_execution",
            "block_project",
            "unblock_project",
            "run_qa",
            "reject_qa",
            "deliver",
            "cancel_project",
        ],
        "hq_management": [
            "intake_review",
            "request_clarification",
            "start_scoping",
            "submit_scope",
            "approve_scope",
            "reject_scope",
            "reject_request",
            "start_execution",
            "block_project",
            "unblock_project",
            "run_qa",
            "reject_qa",
            "deliver",
            "accept_delivery",
            "cancel_project",
        ],
    }

    # 每个状态转换需要的权限
    TRANSITION_PERMISSIONS: Dict[tuple, List[str]] = {
        ("draft", "submitted"): ["submit_request"],
        ("submitted", "intake_review"): ["intake_review"],
        ("intake_review", "clarification_required"): ["request_clarification"],
        ("intake_review", "scoping"): ["start_scoping"],
        ("intake_review", "rejected"): ["reject_request"],
        ("clarification_required", "intake_review"): ["clarification_response"],
        ("scoping", "scope_pending_approval"): ["submit_scope"],
        ("scope_pending_approval", "approved"): ["approve_scope"],
        ("scope_pending_approval", "rejected"): ["reject_scope"],
        ("approved", "in_execution"): ["start_execution"],
        ("in_execution", "blocked"): ["block_project"],
        ("blocked", "in_execution"): ["unblock_project"],
        ("in_execution", "qa"): ["run_qa"],
        ("qa", "delivered"): ["deliver"],
        ("qa", "rework"): ["reject_qa"],
        ("delivered", "accepted"): ["accept_delivery"],
        ("delivered", "changes_requested"): ["request_changes"],
        ("changes_requested", "delivered"): ["re_deliver"],
        ("in_execution", "cancelled"): ["cancel_project"],
    }

    @staticmethod
    def validate_request_transition(current_status: str, target_status: str, user_role: str) -> TransitionResult:
        """验证请求状态转换。

        Args:
            current_status: 当前状态
            target_status: 目标状态
            user_role: 用户角色 (distributor_admin / distributor_user / hq_technical / hq_management)

        Returns:
            TransitionResult with success flag and error details
        """
        # 1. 检查是否是合法的状态转换（禁止自环）
        if current_status == target_status:
            return TransitionResult(
                success=False,
                error_code="INVALID_TRANSITION",
                message=f"Cannot transition from {current_status} to {target_status} (same state)",
            )

        try:
            current = RequestStatus(current_status)
            target = RequestStatus(target_status)
        except ValueError:
            return TransitionResult(
                success=False,
                error_code="INVALID_STATUS",
                message=f"Invalid status: {current_status} or {target_status}",
            )

        # 检查是否在有向无环图中有边
        if target not in REQUEST_TRANSITIONS.get(current, []):
            return TransitionResult(
                success=False,
                error_code="INVALID_TRANSITION",
                message=f"Cannot transition from {current_status} to {target_status}",
            )

        # 2. 检查角色权限（P0 必须）
        role_permissions = StateTransitionGuard.ROLE_PERMISSIONS.get(user_role, [])

        # 定义每个转换需要的权限
        required_permissions = StateTransitionGuard.TRANSITION_PERMISSIONS.get(
            (current_status, target_status), []
        )

        if required_permissions:
            if not any(perm in role_permissions for perm in required_permissions):
                return TransitionResult(
                    success=False,
                    error_code="PERMISSION_DENIED",
                    message=f"Role '{user_role}' does not have permission for transition {current_status}→{target_status}",
                    required_permissions=required_permissions,
                )

        # 特殊权限检查：Scope Approval 只能由 hq_management 执行
        if (current_status, target_status) == ("scope_pending_approval", "approved"):
            if user_role not in ["hq_management"]:
                return TransitionResult(
                    success=False,
                    error_code="PERMISSION_DENIED",
                    message="Only hq_management can approve scope",
                    required_permissions=["approve_scope"],
                )

        return TransitionResult(success=True)

    @staticmethod
    def validate_project_transition(
        current_status: str,
        target_status: str,
        user_role: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> TransitionResult:
        """验证项目状态转换。"""
        from ..models.project import ProjectStatus, PROJECT_TRANSITIONS

        if current_status == target_status:
            return TransitionResult(success=True)

        try:
            current = ProjectStatus(current_status)
            target = ProjectStatus(target_status)
        except ValueError:
            return TransitionResult(
                success=False,
                error_code="INVALID_STATUS",
                message=f"Invalid project status: {current_status} or {target_status}",
            )

        # Project 状态转换表
        if target not in PROJECT_TRANSITIONS.get(current, []):
            return TransitionResult(
                success=False,
                error_code="INVALID_TRANSITION",
                message=f"Cannot transition project from {current_status} to {target_status}",
            )

        # 前置条件检查
        if target_status == "in_execution" and context:
            if context.get("scope_approved") is False:
                return TransitionResult(
                    success=False,
                    error_code="PREREQUISITE_FAILED",
                    message="Scope must be approved before execution",
                )

        # 权限检查：只有 HQ 角色可以执行项目操作
        allowed_roles = {"hq_technical", "hq_management"}
        if user_role not in allowed_roles:
            return TransitionResult(
                success=False,
                error_code="PERMISSION_DENIED",
                message=f"Role {user_role} cannot transition project state",
            )

        return TransitionResult(success=True)


if __name__ == "__main__":
    # 快速测试
    guard = StateTransitionGuard()

    # 合法转换
    result = guard.validate_request_transition("draft", "submitted", "distributor_admin")
    print(f"draft→submitted (distributor_admin): {result.success}")

    # 非法转换
    result = guard.validate_request_transition("draft", "delivered", "hq_admin")
    print(f"draft→delivered (hq_admin): {result.success} - {result.error_code}")

    # 权限不足
    result = guard.validate_request_transition("intake_review", "scoping", "distributor_user")
    print(f"intake_review→scoping (distributor_user): {result.success} - {result.error_code}")
