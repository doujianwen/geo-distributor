"""Evidence Library 测试（Sprint 4C）。"""

import pytest

from geo_distributor.services.evidence_library import EvidenceRecord, EvidenceLibraryService


def _rec(case_id="CASE-001", base=23.0, post=45.0, delta=22.0, industry="ebook_tools"):
    return EvidenceRecord(
        case_id=case_id, distributor_id="DST-001", client_id="CLI-001",
        industry=industry, baseline_visibility_score=base,
        post_intervention_score=post, intervention="content_optimization",
        delta=delta, time_to_result_days=14, evidence_refs=["EVD-001"],
    )


def test_lift_pct():
    rec = _rec(base=23.0, post=45.0, delta=22.0)
    assert rec.lift_pct == pytest.approx(95.65, abs=0.1)


def test_add_and_query_filters():
    svc = EvidenceLibraryService()
    svc.add(_rec(case_id="CASE-001", industry="ebook_tools"))
    svc.add(_rec(case_id="CASE-002", industry="fountain_pen_ink"))
    assert len(svc.all()) == 2
    assert len(svc.query(industry="ebook_tools")) == 1
    assert len(svc.query(distributor_id="DST-001")) == 2


def test_aggregate_stats():
    svc = EvidenceLibraryService()
    svc.add(_rec(delta=22.0))
    svc.add(_rec(case_id="CASE-002", base=10.0, post=30.0, delta=20.0, industry="x"))
    svc.add(_rec(case_id="CASE-003", base=5.0, post=8.0, delta=3.0, industry="y"))
    agg = svc.aggregate()
    assert agg["count"] == 3
    assert agg["avg_delta"] == pytest.approx((22 + 20 + 3) / 3, abs=0.01)
    assert agg["median_delta"] == 20.0
    assert "p25_delta" in agg and "p75_delta" in agg


def test_client_safe_no_internal_leak():
    d = _rec().to_dict()
    assert "internal" not in d and "raw_response" not in d
    # 仅暴露汇总指标，不含技术内部字段
    assert set(d.keys()) >= {
        "case_id", "baseline_visibility_score", "post_intervention_score",
        "delta", "lift_pct", "evidence_refs",
    }
