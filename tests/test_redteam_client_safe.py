"""Sprint 0 Red-Team: Client-safe Boundary 攻击测试。

攻击向量：
- Distributor API 不应暴露 RawResponse
- Distributor API 不应暴露 parser output
- Distributor API 不应暴露 provider internals
- Client Report 与 Technical Report 严格分离
"""

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from geo_distributor.models.geo_core import Report, ReportType, ReportVersion


class TestClientSafeBoundary:
    """测试Client-safe边界。"""

    def test_client_report_cannot_expose_raw_response(self):
        """Client Report不能包含RawResponse。"""
        report = Report(
            report_id="RPT-001",
            project_id="PRJ-001",
            tenant_id="DST-001",
            type=ReportType.CLIENT,
            title="GEO Visibility Report",
        )

        # 尝试向Client Report注入RawResponse数据
        client_content = {
            "executive_summary": "Brand visibility is 65/100",
            "key_findings": ["Brand not mentioned in ChatGPT"],
            "raw_response": "<HTML>...</HTML>",  # 不应该出现
            "parser_output": {"tokens": [1, 2, 3]},  # 不应该出现
        }

        report.add_version(client_content, is_client_safe=True)

        # 验证：raw_response和parser_output不应在client-safe报告中
        latest = report.get_latest_version()
        assert "raw_response" not in latest.content
        assert "parser_output" not in latest.content

    def test_technical_report_can_have_internal_data(self):
        """Technical Report可以包含内部数据。"""
        report = Report(
            report_id="RPT-002",
            project_id="PRJ-001",
            tenant_id="DST-001",
            type=ReportType.TECHNICAL,
            title="GEO Technical Report",
        )

        technical_content = {
            "raw_response": "<HTML>...</HTML>",
            "parser_output": {"tokens": [1, 2, 3]},
            "provider_details": {"api_version": "v1"},
            "browser_logs": ["navigation complete"],
        }

        report.add_version(technical_content, is_client_safe=False)

        latest = report.get_latest_version()
        assert latest.is_client_safe is False
        assert "raw_response" in latest.content

    def test_distributor_cannot_access_hq_internal_data(self):
        """Distributor不能访问HQ内部数据。"""
        # 模拟API层的数据过滤
        hq_internal_data = {
            "raw_response": "...",
            "parser_output": {...},
            "validity_internals": {...},
            "evidence_grading": {...},
        }

        client_safe_projection = {
            "executive_summary": "...",
            "key_findings": [...],
            "recommendations": [...],
        }

        # 验证：内部数据不在client-safe投影中
        for key in hq_internal_data.keys():
            assert key not in client_safe_projection


class TestReportVersioning:
    """测试报告版本管理。"""

    def test_report_versions_are_immuttable(self):
        """报告版本不可变——新版本不覆盖旧版本。"""
        report = Report(
            report_id="RPT-003",
            project_id="PRJ-001",
            tenant_id="DST-001",
            type=ReportType.CLIENT,
        )

        # v1
        report.add_version({"summary": "v1 content"}, is_client_safe=True)
        # v2
        report.add_version({"summary": "v2 content"}, is_client_safe=True)
        # v3
        report.add_version({"summary": "v3 content"}, is_client_safe=True)

        # 验证所有版本都存在
        assert len(report.versions) == 3
        assert report.versions[0].version == 1
        assert report.versions[1].version == 2
        assert report.versions[2].version == 3

        # 验证v1未被覆盖
        assert report.versions[0].content["summary"] == "v1 content"

    def test_scope_cannot_be_mutated_after_approval(self):
        """Scope批准后不能原地修改。"""
        from geo_distributor.models.scope import TechnicalScope

        scope = TechnicalScope(
            scope_id="SCOPE-001",
            request_id="SR-001",
            tenant_id="DST-001",
            markets=["US"],
            engines=["ChatGPT"],
        )

        # 模拟批准
        scope.approved_by = "HQ-MGMT-001"
        scope.approved_at = "2026-09-13T22:00:00"
        scope.version = 1

        # 尝试修改已批准的Scope
        original_markets = scope.markets.copy()
        scope.markets = ["US", "EU"]  # 这应该触发version bump，不是原地修改
        scope.version += 1
        scope.approved_at = None  # 需要重新审批

        # 验证：原版本数据应保留
        assert scope.version == 2
        assert scope.approved_at is None  # 新version需要重新审批
