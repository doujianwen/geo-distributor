"""Audit Trail 测试（J-01, J-02）。"""

import pytest
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from geo_distributor.models.audit import AuditEvent, AuditAction
from geo_distributor.repositories.base import InMemoryRepository


class TestAuditTrail:
    """审计日志完整性测试。"""

    @pytest.mark.asyncio
    async def test_audit_events_recorded(self):
        """J-01: 关键操作记录审计事件。"""
        repo = InMemoryRepository("TestEntity")

        # 使用有 id 字段的对象
        class TestEntity:
            def __init__(self, entity_id, name):
                self.id = entity_id
                self.name = name
                self.tenant_id = "TEST-TENANT"

        entity = TestEntity("TEST-001", "test")

        # 创建实体，检查审计日志
        await repo.create(entity)

        # 审计日志应该有记录
        assert len(repo._audit_log) > 0

        # 验证审计事件结构
        event = repo._audit_log[0]
        assert "action" in event
        assert event["action"] == "create"
        assert "entity_type" in event
        assert "id" in event

    @pytest.mark.asyncio
    async def test_correlation_id_tracks_chain(self):
        """J-02: Correlation ID 追踪操作链。"""
        # 模拟 Request → Project → Report 的关联链
        request_id = "SR-CORR-001"
        project_id = "PRJ-CORR-001"
        report_id = "RPT-CORR-001"
        
        # 创建审计事件
        event1 = AuditEvent.for_request(
            actor_id="HQ-001",
            actor_role="hq_admin",
            action=AuditAction.REQUEST_CREATED,
            request_id=request_id,
            correlation_id=request_id,
        )
        
        event2 = AuditEvent.for_project(
            actor_id="HQ-001",
            actor_role="hq_admin",
            action=AuditAction.PROJECT_CREATED,
            project_id=project_id,
            correlation_id=request_id,  # 关联到同一个 Request
        )
        
        event3 = AuditEvent.for_project(
            actor_id="HQ-001",
            actor_role="hq_admin",
            action=AuditAction.REPORT_CREATED,
            project_id=project_id,
            correlation_id=request_id,  # 关联到同一个 Request
        )
        
        # 验证所有事件共享相同的 correlation_id
        assert event1.correlation_id == request_id
        assert event2.correlation_id == request_id
        assert event3.correlation_id == request_id
        
        # 验证事件包含完整字段
        assert event1.actor_id == "HQ-001"
        assert event1.actor_role == "hq_admin"
        assert event1.object_type == "request"
        assert event1.object_id == request_id
        assert event1.timestamp is not None

    @pytest.mark.asyncio
    async def test_audit_event_fields(self):
        """验证审计事件必须包含的字段。"""
        event = AuditEvent(
            event_id="AUD-TEST-001",
            actor_id="USER-001",
            actor_role="hq_operator",
            action=AuditAction.REQUEST_SUBMITTED.value,
            object_type="request",
            object_id="SR-TEST-001",
            previous_state={"status": "draft"},
            new_state={"status": "submitted"},
            correlation_id="SR-TEST-001",
        )
        
        data = event.to_dict()
        
        # 必需字段
        assert "event_id" in data
        assert "actor_id" in data
        assert "actor_role" in data
        assert "action" in data
        assert "object_type" in data
        assert "object_id" in data
        assert "timestamp" in data
        assert "correlation_id" in data
        
        # before/after 状态
        assert data["previous_state"] == {"status": "draft"}
        assert data["new_state"] == {"status": "submitted"}
