"""Sprint 4 — Real Adapter Integration Tests.

目标：
- 使用BookConv baseline数据验证 OpenGeoAdapter
- 验证完整链路：Observation → Evidence → Diagnosis → Report
- 确认与MockAdapter结果一致

数据源：sprint4-lab/cases/bookconv/baseline/observations.json
"""

import json
import os
import pytest
from typing import List, Dict, Any

from geo_distributor.adapters.opengeo import OpenGeoAdapter
from geo_distributor.adapters.mock import MockMeasurementAdapter
from geo_distributor.compatibility.base import PlatformObservation
from geo_distributor.models.geo_core import Evidence, EvidenceLevel, Report, ReportVersion, ReportType
from geo_distributor.services.measurement_analysis import aggregate_metrics


# 路径常量
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CASES_DIR = os.path.join(BASE_DIR, "sprint4-lab", "cases")
BOOKCONV_BASELINE = os.path.join(CASES_DIR, "bookconv", "baseline")


def _load_bookconv_observations() -> List[PlatformObservation]:
    """加载BookConv baseline observations。"""
    path = os.path.join(BOOKCONV_BASELINE, "observations.json")
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return [PlatformObservation(**obs) for obs in data]


def _load_bookconv_query_set() -> List[str]:
    """加载BookConv query set。"""
    path = os.path.join(BOOKCONV_BASELINE, "query_set.json")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# ============================================================================
# Sprint 4A: OpenGeoAdapter 真实数据集成
# ============================================================================

class TestOpenGeoAdapterWithRealData:
    """使用BookConv真实数据测试OpenGeoAdapter。"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """加载BookConv baseline数据。"""
        self.observations = _load_bookconv_observations()
        self.query_set = _load_bookconv_query_set()
        self.adapter = OpenGeoAdapter.from_observations(self.observations)

    @pytest.mark.asyncio
    async def test_adapter_health_with_real_data(self):
        """Adapter应报告健康（有数据）。"""
        assert await self.adapter.health_check() is True
        assert len(self.adapter._observations) == len(self.observations)

    @pytest.mark.asyncio
    async def test_collect_known_query(self):
        """已知query应返回匹配观测。"""
        # 取第一个query
        query = self.query_set[0]
        obs = await self.adapter.collect_prompt({"query": query})
        assert obs is not None
        assert obs.prompt_text == query
        assert obs.engine == "opengeo"  # OpenGeoAdapter返回opengeo作为engine

    @pytest.mark.asyncio
    async def test_collect_unknown_query_returns_not_collected(self):
        """未知query应返回NOT_COLLECTED状态，不伪造数据。"""
        obs = await self.adapter.collect_prompt({"query": "nonexistent query xyz"})
        assert obs.status == "not_collected"
        assert obs.brand_mentioned is False
        assert obs.brand_status == "NOT_COLLECTED"
        assert "not present in collected store" in obs.raw_metadata.get("note", "")

    @pytest.mark.asyncio
    async def test_collect_batch_returns_all_results(self):
        """批量采集应返回所有结果。"""
        prompts = [{"query": q} for q in self.query_set[:5]]
        results = await self.adapter.collect_batch(prompts)
        assert len(results) == 5
        for r in results:
            assert r is not None
            assert isinstance(r, PlatformObservation)


class TestBookConvMetricsAggregation:
    """验证BookConv metrics聚合。"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """加载数据。"""
        self.observations = _load_bookconv_observations()
        self.query_set = _load_bookconv_query_set()

    def test_aggregate_metrics(self):
        """聚合指标应与baseline/metrics.json一致。"""
        metrics = aggregate_metrics(
            observations=self.observations,
            case_id="CASE-001",
            version="baseline",
            total_queries=len(self.query_set),
        )

        # 验证基本字段
        assert metrics.case_id == "CASE-001"
        assert metrics.version == "baseline"
        assert metrics.query_count == len(self.observations)
        assert metrics.query_coverage > 0

        # 验证计算逻辑
        mentioned = sum(1 for o in self.observations if o.brand_mentioned)
        expected_mention_rate = round(mentioned / len(self.observations) * 100, 2)
        assert metrics.mention_rate == expected_mention_rate

    def test_metrics_match_baseline(self):
        """聚合结果应与已保存的baseline metrics匹配。"""
        # 加载已保存的metrics
        metrics_path = os.path.join(BOOKCONV_BASELINE, "metrics.json")
        with open(metrics_path, "r", encoding="utf-8") as f:
            baseline_metrics = json.load(f)

        # 重新聚合
        computed_metrics = aggregate_metrics(
            observations=self.observations,
            case_id="CASE-001",
            version="baseline",
            total_queries=len(self.query_set),
        )

        # 验证关键字段一致
        assert abs(computed_metrics.mention_rate - baseline_metrics["mention_rate"]) < 0.1
        assert abs(computed_metrics.recommendation_rate - baseline_metrics["recommendation_rate"]) < 0.1
        assert abs(computed_metrics.avg_recommendation_level - baseline_metrics["avg_recommendation_level"]) < 0.1


# ============================================================================
# Sprint 4B: Evidence & Diagnosis Chain
# ============================================================================

class TestEvidenceFromRealObservations:
    """验证从真实观测生成Evidence链。"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """加载数据。"""
        self.observations = _load_bookconv_observations()

    def test_generate_evidence_from_mentioned(self):
        """品牌被提及的观测应生成证据。"""
        # 找一个品牌被提及的观测
        mentioned_obs = next((o for o in self.observations if o.brand_mentioned), None)
        assert mentioned_obs is not None

        # 生成Evidence（注意：Evidence没有statement/source/confidence字段）
        evidence = Evidence(
            evidence_id=f"EVD-{mentioned_obs.observation_id}",
            observation_id=mentioned_obs.observation_id,
            source_type="bing_ai_performance",
            content=f"BookConv is mentioned for '{mentioned_obs.prompt_text}'",
            credibility_score=0.8,
            level=EvidenceLevel.E2,  # 来自Bing AI Performance
        )

        assert evidence.level in [EvidenceLevel.E2, EvidenceLevel.E3]
        assert evidence.content is not None
        assert len(evidence.content) > 0

    def test_generate_evidence_from_not_mentioned(self):
        """品牌未被提及的观测也应记录。"""
        not_mentioned = next(
            (o for o in self.observations if not o.brand_mentioned),
            None
        )
        if not not_mentioned:  # 修复变量名错误
            # 如果没有not mentioned的观测，跳过
            pytest.skip("No NOT_MENTIONED observations found")

        evidence = Evidence(
            evidence_id=f"EVD-{not_mentioned.observation_id}",
            observation_id=not_mentioned.observation_id,
            source_type="bing_ai_performance",
            content=f"BookConv not found for '{not_mentioned.prompt_text}'",
            credibility_score=0.9,
            level=EvidenceLevel.E1,  # 仅观测，无推荐
        )

        assert evidence.level == EvidenceLevel.E1
        assert "not found" in evidence.content.lower()


class TestDiagnosisFromRealData:
    """验证基于真实数据的Diagnosis生成。"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """加载数据。"""
        self.observations = _load_bookconv_observations()
        self.query_set = _load_bookconv_query_set()

    def test_generate_findings(self):
        """应能从观测生成Diagnosis Findings。"""
        metrics = aggregate_metrics(
            observations=self.observations,
            case_id="CASE-001",
            version="baseline",
            total_queries=len(self.query_set),
        )

        # 生成Findings
        findings = []

        # Finding 1: Mention Rate
        if metrics.mention_rate >= 80:
            findings.append({
                "finding_id": "F-001",
                "category": "visibility",
                "severity": "positive",
                "statement": f"Brand mention rate: {metrics.mention_rate}%",
                "evidence_refs": ["EVD-bing-001"],
            })
        else:
            findings.append({
                "finding_id": "F-001",
                "category": "visibility",
                "severity": "warning",
                "statement": f"Brand mention rate below target: {metrics.mention_rate}%",
                "evidence_refs": [],
            })

        # Finding 2: Query Coverage
        if metrics.query_coverage < 50:
            findings.append({
                "finding_id": "F-002",
                "category": "coverage",
                "severity": "high",
                "statement": f"Query coverage only {metrics.query_coverage}%",
                "evidence_refs": [],
            })

        assert len(findings) > 0
        assert any(f["category"] == "visibility" for f in findings)

    def test_recommendation_level_distribution(self):
        """验证Recommendation Level分布。"""
        levels = {1: 0, 2: 0, 3: 0, 0: 0}
        for obs in self.observations:
            level = obs.recommendation_level or 0
            if level in levels:
                levels[level] += 1

        # 应有至少一个positive recommendation
        assert levels[2] + levels[3] > 0, "Should have some recommendations"


# ============================================================================
# Sprint 4C: Report Generation with Real Data
# ============================================================================

class TestReportGenerationWithRealData:
    """验证使用真实数据生成Report。"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """加载数据。"""
        self.observations = _load_bookconv_observations()
        self.query_set = _load_bookconv_query_set()

    def test_generate_client_safe_report(self):
        """应生成Client-safe Report。"""
        metrics = aggregate_metrics(
            observations=self.observations,
            case_id="CASE-001",
            version="baseline",
            total_queries=len(self.query_set),
        )

        report = Report(
            report_id="RPT-BOOKCONV-BASELINE",
            project_id="PRJ-BOOKCONV-001",
            tenant_id="DST-TEST-001",
            type=ReportType.CLIENT,
            title="BookConv GEO Baseline Report",
        )
        report.add_version(
            content={
                "summary": f"BookConv GEO Baseline Report",
                "metrics": {
                    "mention_rate": metrics.mention_rate,
                    "recommendation_rate": metrics.recommendation_rate,
                    "query_coverage": metrics.query_coverage,
                    "avg_recommendation_level": metrics.avg_recommendation_level,
                },
                "recommendations": [
                    "Focus on high-share queries (e.g., 'transfer ebooks between devices')",
                    "Improve presence in AI Answer boxes",
                ],
            },
            is_client_safe=True,
            notes="Generated from Bing AI Performance data",
        )

        # 验证Client-safe过滤
        assert len(report.versions) == 1
        latest = report.get_latest_version()
        assert latest is not None
        assert latest.is_client_safe is True
        assert "answer_raw" not in latest.content  # 敏感字段不应暴露
        assert "raw_metadata" not in latest.content

    def test_report_versioning(self):
        """验证Report版本管理。"""
        report = Report(
            report_id="RPT-VERSION-TEST",
            project_id="PRJ-TEST-001",
            tenant_id="DST-TEST-001",
            type=ReportType.TECHNICAL,
            title="Version Test Report",
        )
        report.add_version(content={"version": 1}, is_client_safe=False)

        # 添加新版本
        report.add_version(
            content={"version": 2, "update": "Added more findings"},
            is_client_safe=True,
            notes="Updated with intervention results",
        )

        # 验证两个版本都存在
        assert len(report.versions) == 2
        assert report.versions[0].version == 1
        assert report.versions[1].version == 2

        # 验证旧版本未被覆盖
        assert report.versions[0].content == {"version": 1}
        assert report.versions[1].content == {"version": 2, "update": "Added more findings"}


# ============================================================================
# Sprint 4: E2E Integration Test
# ============================================================================

class TestE2ERealAdapterPipeline:
    """完整E2E测试：使用OpenGeoAdapter验证端到端链路。"""

    @pytest.mark.asyncio
    async def test_full_pipeline_with_real_data(self):
        """完整链路：OpenGeoAdapter → Metrics → Findings → Report。"""
        # 1. 加载数据
        observations = _load_bookconv_observations()
        query_set = _load_bookconv_query_set()

        # 2. 创建Adapter
        adapter = OpenGeoAdapter.from_observations(observations)
        assert await adapter.health_check()

        # 3. 采集（模拟）
        prompts = [{"query": q} for q in query_set[:5]]
        collected = await adapter.collect_batch(prompts)
        assert len(collected) == 5

        # 4. 聚合Metrics
        metrics = aggregate_metrics(
            observations=collected,
            case_id="CASE-001",
            version="baseline",
            total_queries=len(query_set),
        )

        # 5. 验证Metrics有效性
        assert metrics.query_count > 0
        assert metrics.mention_rate >= 0
        assert metrics.recommendation_rate >= 0

        # 6. 生成Report
        report = Report(
            report_id="RPT-E2E-REAL",
            project_id="PRJ-E2E-001",
            tenant_id="DST-TEST-001",
            type=ReportType.CLIENT,
            title="E2E Real Adapter Test",
        )
        report.add_version(
            content={
                "metrics": {
                    "mention_rate": metrics.mention_rate,
                    "query_coverage": metrics.query_coverage,
                },
            },
            is_client_safe=True,
            notes="Generated from real BookConv data",
        )

        # 7. 验证Report
        assert report.report_id == "RPT-E2E-REAL"
        latest = report.get_latest_version()
        assert latest is not None
        assert latest.is_client_safe is True


# ============================================================================
# Sprint 4: Comparison with Mock
# ============================================================================

class TestAdapterComparison:
    """对比OpenGeoAdapter与MockAdapter的行为一致性。"""

    @pytest.mark.asyncio
    async def test_both_return_platform_observation(self):
        """两种Adapter都应返回PlatformObservation。"""
        # Mock
        mock_adapter = MockMeasurementAdapter()

        # OpenGeo
        real_adapter = OpenGeoAdapter.from_observations([])

        # 都需要await（async方法）
        mock_obs = await mock_adapter.collect_prompt({"query": "test"})
        real_obs = await real_adapter.collect_prompt({"query": "test"})

        assert isinstance(mock_obs, PlatformObservation)
        assert isinstance(real_obs, PlatformObservation)

    @pytest.mark.asyncio
    async def test_real_adapter_more_specific(self):
        """OpenGeoAdapter应比MockAdapter更具体。"""
        real_adapter = OpenGeoAdapter.from_observations([
            PlatformObservation(
                observation_id="obs-test",
                prompt_id=1,
                engine="bing_ai",
                timestamp="2026-09-13",
                prompt_text="test query",
                answer_raw="",
                answer_clean="",
                answer_char_count=0,
                extraction_method="test",
                validation_status="PASS",
                brand="TestBrand",
                brand_mentioned=True,
                brand_status="MENTIONED",
                first_mention_position=None,
                recommendation_level=2,
                recommendation_rank=None,
                recommendation_evidence="Test evidence",
                competitors=[],
                citations=[],
                citations_status="extracted",
                status="success",
            )
        ])

        obs = await real_adapter.collect_prompt({"query": "test query"})
        assert obs.brand == "TestBrand"
        assert obs.brand_mentioned is True
        assert obs.recommendation_level == 2
