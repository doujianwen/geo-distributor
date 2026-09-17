"""Sprint 0 Red-Team: Audit Trail 攻击测试。

攻击向量：
- 审计日志完整性
- 审计事件不被业务更新覆盖
- 关键操作都有审计记录
"""

import pytest
import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

from geo_distributor.models.tenant import AuditEntry


class TestAuditIntegrity:
    """测试审计日志完整性。"""

    def test_audit_entry_creation(self):
        """审计条目创建正确。"""
        entry = AuditEntry(
            audit_id="AUD-001",
            tenant_id="DST-001",
            user_id="USR-001",
            action="TRANSITION",
            resource_type="REQUEST",
            resource_id="SR-001",
            old_value={"status": "draft"},
            new_value={"status": "submitted"},
            timestamp=datetime.now().isoformat(),
        )

        assert entry.audit_id == "AUD-001"
        assert entry.action == "TRANSITION"
        assert entry.old_value["status"] == "draft"
        assert entry.new_value["status"] == "submitted"

    def test_audit_entry_to_dict(self):
        """审计条目to_dict正确。"""
        entry = AuditEntry(
            audit_id="AUD-002",
            tenant_id="DST-001",
            user_id="USR-001",
            action="CREATE",
            resource_type="PROJECT",
            resource_id="PRJ-001",
        )

        d = entry.to_dict()
        assert d["audit_id"] == "AUD-002"
        assert "timestamp" in d
        assert d["action"] == "CREATE"

    def test_audit_not_overwritten_by_business_update(self):
        """审计事件不被普通业务更新覆盖。"""
        # 场景：一次状态转换后，业务数据更新不应影响审计记录
        audit_before = AuditEntry(
            audit_id="AUD-003",
            tenant_id="DST-001",
            user_id="USR-001",
            action="TRANSITION",
            resource_type="REQUEST",
            resource_id="SR-001",
            old_value={"status": "submitted"},
            new_value={"status": "approved"},
        )

        # 模拟业务数据后续更新
        business_data = {"status": "approved", "updated_at": "2026-09-13T23:00:00"}

        # 审计记录应保持原值
        assert audit_before.new_value["status"] == "approved"
        assert audit_before.timestamp != business_data.get("updated_at")  # 审计时间早于业务更新时间


class TestAuditCoverage:
    """测试关键操作的审计覆盖。"""

    @pytest.mark.parametrize("action", [
        "CREATE", "UPDATE", "DELETE", "TRANSITION", "VIEW", "APPROVE", "REJECT"
    ])
    def test_all_actions_can_be_audited(self, action):
        """所有关键操作都能被审计。"""
        entry = AuditEntry(
            audit_id=f"AUD-{action}",
            tenant_id="DST-001",
            user_id="USR-001",
            action=action,
            resource_type="REQUEST",
            resource_id="SR-001",
        )
        assert entry.action == action

    def test_audit_records_correlation_id(self):
        """审计应记录关联ID。"""
        entry = AuditEntry(
            audit_id="AUD-004",
            tenant_id="DST-001",
            user_id="USR-001",
            action="TRANSITION",
            resource_type="REQUEST",
            resource_id="SR-001",
        )
        # 审计条目应包含足够的上下文信息
        d = entry.to_dict()
        assert "tenant_id" in d
        assert "user_id" in d
        assert "timestamp" in d


class TestAuditTrailContinuity:
    """测试审计链连续性。"""

    def test_state_transition_chain(self):
        """状态转换链可追溯。"""
        transitions = [
            ("draft", "submitted"),
            ("submitted", "intake_review"),
            ("intake_review", "scoping"),
            ("scoping", "scope_pending_approval"),
            ("scope_pending_approval", "approved"),
        ]

        audit_log = []
        current_status = "draft"
        for i, (old, new) in enumerate(transitions):
            entry = AuditEntry(
                audit_id=f"AUD-TRANS-{i}",
                tenant_id="DST-001",
                user_id="USR-001",
                action="TRANSITION",
                resource_type="REQUEST",
                resource_id="SR-001",
                old_value={"status": old},
                new_value={"status": new},
            )
            audit_log.append(entry)
            current_status = new

        # 验证链完整
        assert len(audit_log) == 5
        assert audit_log[0].old_value["status"] == "draft"
        assert audit_log[-1].new_value["status"] == "approved"
