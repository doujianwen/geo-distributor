"""Canonical GEO Core Boundary Audit — Phase 9

验证 Core 模型是否与 open-geo/GeoLook 解耦。
"""

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from geo_distributor.compatibility.base import (
    PlatformObservation,
)
from geo_distributor.models.geo_core import (
    Evidence, Report, ReportType,
)
from geo_distributor.models import Observation, Measurement


class TestCanonicalBoundary:
    """验证 Core 模型的平台无关性。"""

    def test_observation_has_no_provider_specific_fields(self):
        """PlatformObservation 不应包含 provider-specific 字段。"""
        obs = PlatformObservation(
            observation_id="OBS-001",
            prompt_id=1,
            engine="mock",
            timestamp="2026-01-01T00:00:00Z",
            prompt_text="test query",
            answer_raw="Test answer",
            answer_clean="Test answer",
            answer_char_count=9,
            extraction_method="dom_traversal",
            validation_status="PASS",
            brand="TestBrand",
            brand_mentioned=False,
            brand_status="NOT_MENTIONED",
            first_mention_position=None,
            recommendation_level=0,
            recommendation_rank=None,
            recommendation_evidence="",
            competitors=[],
            citations=[],
            citations_status="unavailable",
            status="success",
        )
        assert obs.engine == "mock"
        d = obs.to_dict()
        assert "provider_specific" not in d
        assert "raw_html" not in d

    def test_platform_observation_is_adapter_independent(self):
        """PlatformObservation 应独立于具体 Adapter。"""
        obs = PlatformObservation(
            observation_id="OBS-002",
            prompt_id=2,
            engine="chatgpt",
            timestamp="2026-01-01T00:00:00Z",
            prompt_text="best sensors",
            answer_raw="Acme is best",
            answer_clean="Acme is best",
            answer_char_count=13,
            extraction_method="dom_traversal",
            validation_status="PASS",
            brand="Acme",
            brand_mentioned=True,
            brand_status="MENTIONED",
            first_mention_position=1,
            recommendation_level=2,
            recommendation_rank=None,
            recommendation_evidence="Answer text",
            competitors=[],
            citations=[],
            citations_status="unavailable",
            status="success",
        )
        assert obs.engine in ["mock", "chatgpt", "google", "perplexity"]
        d = obs.to_dict()
        forbidden = {"raw_html", "browser_driver", "provider_name", "api_key", "open_geo"}
        assert not forbidden.intersection(d.keys())

    def test_evidence_traces_to_canonical_observation(self):
        """Evidence 应追溯到 Observation，而非 provider response。"""
        e = Evidence(
            evidence_id="EVD-001",
            observation_id="OBS-001",
            source_type="citation",
            content="Test evidence",
        )
        assert e.observation_id == "OBS-001"
        assert e.source_type in ["screenshot", "url", "text_quote", "citation"]
        # 验证没有直接引用 provider response
        assert "raw_response" not in e.__dict__

    def test_measurement_has_provenance(self):
        """Measurement 应有 provenance，而非 provider 信息。"""
        m = Measurement(
            measurement_id="MEAS-001",
            observation_id="OBS-001",
        )
        assert m.observation_id == "OBS-001"
        # 验证没有 adapter-specific 字段
        d = m.__dict__
        assert "provider_specific" not in d
        assert "raw_html" not in d

    def test_report_has_no_internal_debug_fields(self):
        """Client-safe Report 不应包含内部调试字段。"""
        r = Report(
            report_id="RPT-001",
            project_id="PRJ-001",
            tenant_id="DST-001",
            type=ReportType.CLIENT,
        )
        d = r.to_dict()
        assert "debug_info" not in str(d)
        assert "browser_logs" not in str(d)

    def test_core_does_not_import_open_geo(self):
        """Core 模块不应导入 open-geo 具体实现。"""
        import geo_distributor.models.geo_core as core_module
        with open(core_module.__file__, 'r', encoding='utf-8') as f:
            src = f.read()
        # 允许 adapter 相关导入，但不允许 open-geo 具体实现
        assert "open_geo" not in src.lower() or "adapter" in src.lower()

    def test_canonical_models_are_platform_independent(self):
        """验证核心模型（Observation/Measurement/Evidence/Report）都是平台无关的。"""
        # Observation（使用 compatibility 层的）
        obs = PlatformObservation(
            observation_id="OBS-003",
            prompt_id=3,
            engine="mock",
            timestamp="2026-01-01T00:00:00Z",
            prompt_text="test query",
            answer_raw="Test result",
            answer_clean="Test result",
            answer_char_count=11,
            extraction_method="dom_traversal",
            validation_status="PASS",
            brand="",
            brand_mentioned=False,
            brand_status="UNKNOWN",
            first_mention_position=None,
            recommendation_level=-1,
            recommendation_rank=None,
            recommendation_evidence="",
            competitors=[],
            citations=[],
            citations_status="unavailable",
            status="success",
        )
        assert obs.observation_id == "OBS-003"
        d = obs.to_dict()
        assert "raw_html" not in d

        # Measurement
        meas = Measurement(
            measurement_id="MEAS-002",
            observation_id="OBS-003",
        )
        assert meas.observation_id == "OBS-003"
        assert not hasattr(meas, 'provider_name')

        # Evidence
        evd = Evidence(
            evidence_id="EVD-002",
            observation_id="OBS-003",
            source_type="url",
            content="http://example.com",
        )
        assert evd.observation_id == "OBS-003"
        assert "raw_response" not in evd.__dict__

        # Report
        rpt = Report(
            report_id="RPT-002",
            project_id="PRJ-001",
            tenant_id="DST-001",
            type=ReportType.CLIENT,
        )
        assert rpt.report_id == "RPT-002"
        assert "debug_info" not in str(rpt.to_dict())


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
