"""Intervention Loop + Measurement Analysis 测试（Sprint 4B）。"""

import pytest

from geo_distributor.compatibility.base import PlatformObservation
from geo_distributor.services.intervention_loop import (
    InterventionRecommendation,
    InterventionExecution,
    BaselineMetrics,
    DeltaCalculator,
    ReMeasurementService,
)
from geo_distributor.services.measurement_analysis import aggregate_metrics


class _StubAdapter:
    def __init__(self, observations):
        self._obs = observations

    async def health_check(self):
        return True

    async def collect_prompt(self, prompt):
        return self._obs[0]

    async def collect_batch(self, prompts, progress_callback=None):
        out = []
        for i, p in enumerate(prompts):
            out.append(self._obs[i % len(self._obs)])
            if progress_callback:
                progress_callback(i + 1, len(prompts))
        return out


def _obs(mentioned: bool, rec: int, cites: int = 0) -> PlatformObservation:
    return PlatformObservation(
        observation_id=f"o{mentioned}{rec}",
        prompt_id=1, engine="bing_ai", timestamp="", prompt_text="q",
        answer_raw="", answer_clean="", answer_char_count=0, extraction_method="t",
        validation_status="PASS", brand="B", brand_mentioned=mentioned,
        brand_status="MENTIONED" if mentioned else "NOT_MENTIONED",
        first_mention_position=None, recommendation_level=rec, recommendation_rank=None,
        recommendation_evidence="", competitors=[], citations=[],
        citations_status="extracted" if mentioned else "none", status="success",
        raw_metadata={"cites": cites},
    )


def test_priority_score_formula():
    rec = InterventionRecommendation(
        intervention_id="I1", finding_id="F1", case_id="CASE-001",
        itype="faq", title="t", description="d", target="/faq",
        impact=5, effort=1, confidence=0.9,
    )
    assert rec.priority_score() == round(5 * 0.9 / 1, 3)


def test_delta_calculator():
    base = BaselineMetrics(case_id="C", version="baseline",
                           mention_rate=40.0, citation_rate=30.0,
                           recommendation_rate=20.0, query_coverage=100.0,
                           avg_recommendation_level=1.5, competitor_count=3)
    re = BaselineMetrics(case_id="C", version="remeasurement",
                         mention_rate=60.0, citation_rate=55.0,
                         recommendation_rate=45.0, query_coverage=100.0,
                         avg_recommendation_level=2.5, competitor_count=4)
    delta = DeltaCalculator.compute(base, re)
    assert delta["mention_delta"] == 20.0
    assert delta["citation_delta"] == 25.0
    assert delta["recommendation_delta"] == 25.0
    assert delta["competitor_delta"] == 1.0


def test_aggregate_metrics():
    obs = [_obs(True, 3, cites=10), _obs(True, 2, cites=5), _obs(False, 0)]
    m = aggregate_metrics(obs, case_id="CASE-001", version="baseline", total_queries=3)
    assert m.query_count == 3
    assert m.mention_rate == pytest.approx(66.67, abs=0.1)
    assert m.citation_rate == pytest.approx(66.67, abs=0.1)
    assert m.recommendation_rate == pytest.approx(66.67, abs=0.1)
    assert m.query_coverage == 100.0


@pytest.mark.asyncio
async def test_remeasurement_service():
    adapter = _StubAdapter([_obs(True, 3, cites=10), _obs(False, 0), _obs(True, 2, cites=3)])
    svc = ReMeasurementService(adapter)
    m = await svc.remeasure("CASE-001", ["q1", "q2", "q3"])
    assert m.version == "remeasurement"
    assert m.query_count == 3
    assert m.mention_rate == pytest.approx(66.67, abs=0.1)
