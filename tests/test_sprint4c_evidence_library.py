"""Sprint 4C — Evidence Library 综合测试（完整版）。

覆盖：
- EvidenceRecord 属性与序列化
- EvidenceLibraryService CRUD、查询、聚合
- EvidenceDashboard 仪表盘视图
- JSON/CSV 导出
- 从 sprint4-lab 真实案例数据加载
- Client-safe 约束
"""

import csv
import io
import json
import os
import pytest

from geo_distributor.services.evidence_library import (
    EvidenceRecord,
    EvidenceLibraryService,
    EvidenceDashboard,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _rec(case_id="CASE-001", base=23.0, post=45.0, delta=22.0, industry="ebook_tools"):
    return EvidenceRecord(
        case_id=case_id,
        distributor_id="DST-001",
        client_id="CLI-001",
        industry=industry,
        baseline_visibility_score=base,
        post_intervention_score=post,
        intervention="content_optimization",
        delta=delta,
        time_to_result_days=14,
        evidence_refs=["EVD-001"],
    )


@pytest.fixture
def sample_service():
    """含 3 条记录的服务实例（至少 3 条，满足验收标准）。"""
    svc = EvidenceLibraryService()
    svc.add(_rec(case_id="CASE-001", base=23.0, post=45.0, delta=22.0, industry="ebook_tools"))
    svc.add(_rec(case_id="CASE-002", base=10.0, post=30.0, delta=20.0, industry="fountain_pen_ink"))
    svc.add(_rec(case_id="CASE-003", base=5.0, post=8.0, delta=3.0, industry="industrial_sensors"))
    return svc


@pytest.fixture
def lab_cases_dir():
    """指向 sprint4-lab/cases 目录的绝对路径。"""
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(here, "sprint4-lab", "cases")


# ---------------------------------------------------------------------------
# EvidenceRecord 基础
# ---------------------------------------------------------------------------

class TestEvidenceRecord:
    def test_lift_pct(self):
        rec = _rec(base=23.0, post=45.0, delta=22.0)
        assert rec.lift_pct == pytest.approx(95.65, abs=0.1)

    def test_lift_pct_zero_baseline(self):
        rec = _rec(base=0.0, post=10.0, delta=10.0)
        assert rec.lift_pct == 0.0

    def test_is_positive(self):
        assert _rec(delta=22.0).is_positive is True
        assert _rec(delta=-5.0).is_positive is False
        assert _rec(delta=0.0).is_positive is False

    def test_status_label(self):
        assert _rec(delta=22.0).status_label == "POSITIVE"
        assert _rec(delta=-5.0).status_label == "NEGATIVE"
        assert _rec(delta=0.0).status_label == "NEUTRAL"

    def test_to_dict_keys(self):
        d = _rec().to_dict()
        required = {"case_id", "baseline_visibility_score", "post_intervention_score",
                     "intervention", "delta", "lift_pct", "status", "evidence_refs"}
        assert required <= set(d.keys())

    def test_no_internal_data_leak(self):
        d = _rec().to_dict()
        leak_keys = {"raw_response", "internal", "technical_notes", "browser_logs"}
        assert not (leak_keys & set(d.keys()))


# ---------------------------------------------------------------------------
# EvidenceLibraryService CRUD
# ---------------------------------------------------------------------------

class TestEvidenceLibraryServiceCRUD:
    def test_add_and_all(self, sample_service):
        assert len(sample_service.all()) == 3

    def test_add_from_dict(self):
        svc = EvidenceLibraryService()
        rec = svc.add_from_dict({
            "case_id": "CASE-010",
            "distributor_id": "DST-010",
            "client_id": "CLI-010",
            "industry": "test",
            "baseline_visibility_score": 10.0,
            "post_intervention_score": 20.0,
            "intervention": "content",
            "delta": 10.0,
        })
        assert rec.case_id == "CASE-010"
        assert len(svc.all()) == 1

    def test_remove(self, sample_service):
        assert sample_service.remove("CASE-001") is True
        assert len(sample_service.all()) == 2
        assert sample_service.remove("CASE-999") is False  # 不存在

    def test_get_by_case_id(self, sample_service):
        rec = sample_service.get_by_case_id("CASE-002")
        assert rec is not None
        assert rec.case_id == "CASE-002"
        assert sample_service.get_by_case_id("CASE-999") is None


# ---------------------------------------------------------------------------
# 查询
# ---------------------------------------------------------------------------

class TestEvidenceLibraryQuery:
    def test_query_industry(self, sample_service):
        r = sample_service.query(industry="ebook_tools")
        assert len(r) == 1
        assert r[0].case_id == "CASE-001"

    def test_query_distributor(self, sample_service):
        r = sample_service.query(distributor_id="DST-001")
        assert len(r) == 3

    def test_query_client(self, sample_service):
        r = sample_service.query(client_id="CLI-001")
        assert len(r) == 3

    def test_query_since(self, sample_service):
        # 所有记录创建时间相同，不会过滤
        r = sample_service.query(since="2000-01-01")
        assert len(r) == 3
        r_late = sample_service.query(since="2099-01-01")
        assert len(r_late) == 0

    def test_query_min_delta(self, sample_service):
        r = sample_service.query(min_delta=10.0)
        assert len(r) == 2  # CASE-001 (22) + CASE-002 (20)
        assert all(rec.delta >= 10.0 for rec in r)

    def test_query_combined(self, sample_service):
        r = sample_service.query(industry="ebook_tools", min_delta=10.0)
        assert len(r) == 1
        assert r[0].case_id == "CASE-001"


# ---------------------------------------------------------------------------
# 聚合统计
# ---------------------------------------------------------------------------

class TestEvidenceLibraryAggregate:
    def test_aggregate_basic(self, sample_service):
        agg = sample_service.aggregate()
        assert agg["count"] == 3
        assert agg["avg_delta"] == pytest.approx((22 + 20 + 3) / 3, abs=0.01)
        assert agg["median_delta"] == 20.0
        assert "p25_delta" in agg
        assert "p75_delta" in agg
        assert "positive_rate" in agg
        assert agg["positive_rate"] == 100.0

    def test_aggregate_empty(self):
        svc = EvidenceLibraryService()
        agg = svc.aggregate()
        assert agg["count"] == 0
        assert agg["avg_delta"] == 0.0

    def test_aggregate_by_industry(self, sample_service):
        by_ind = sample_service.aggregate_by_industry()
        assert "ebook_tools" in by_ind
        assert by_ind["ebook_tools"]["count"] == 1
        assert by_ind["fountain_pen_ink"]["count"] == 1
        assert by_ind["industrial_sensors"]["count"] == 1

    def test_aggregate_by_industry_single(self):
        svc = EvidenceLibraryService()
        svc.add(_rec(industry="single"))
        svc.add(_rec(case_id="C2", industry="single"))
        by_ind = svc.aggregate_by_industry()
        assert by_ind["single"]["count"] == 2


# ---------------------------------------------------------------------------
# 导出
# ---------------------------------------------------------------------------

class TestEvidenceExport:
    def test_export_json(self, sample_service):
        j = sample_service.export_json()
        data = json.loads(j)
        assert "records" in data
        assert "aggregate" in data
        assert "by_industry" in data
        assert len(data["records"]) == 3

    def test_export_csv(self, sample_service):
        csv_str = sample_service.export_csv()
        reader = csv.DictReader(io.StringIO(csv_str))
        rows = list(reader)
        assert len(rows) == 3
        assert "case_id" in rows[0]
        assert "delta" in rows[0]
        assert "lift_pct" in rows[0]

    def test_export_csv_empty(self):
        svc = EvidenceLibraryService()
        csv_str = svc.export_csv()
        assert csv_str == ""

    def test_to_dict_comprehensive(self, sample_service):
        d = sample_service.to_dict()
        assert len(d["records"]) == 3
        assert "aggregate" in d
        assert "by_industry" in d


# ---------------------------------------------------------------------------
# EvidenceDashboard
# ---------------------------------------------------------------------------

class TestEvidenceDashboard:
    def test_summary(self, sample_service):
        dashboard = EvidenceDashboard(sample_service)
        s = dashboard.summary()
        assert s["total_cases"] == 3
        assert s["avg_delta"] == pytest.approx((22 + 20 + 3) / 3, abs=0.01)
        assert s["positive_rate_pct"] == 100.0
        assert len(s["top_3_deltas"]) == 3

    def test_top_n_ordering(self, sample_service):
        dashboard = EvidenceDashboard(sample_service)
        top = dashboard._top_n_by_delta(2)
        assert top[0]["delta"] >= top[1]["delta"]  # 降序

    def test_industry_report(self, sample_service):
        dashboard = EvidenceDashboard(sample_service)
        r = dashboard.industry_report("ebook_tools")
        assert r is not None
        assert r["industry"] == "ebook_tools"
        assert r["case_count"] == 1
        assert r["avg_delta"] == 22.0

    def test_industry_report_not_found(self):
        dashboard = EvidenceDashboard(EvidenceLibraryService())
        assert dashboard.industry_report("nonexistent") is None


# ---------------------------------------------------------------------------
# 从 sprint4-lab 真实案例数据加载
# ---------------------------------------------------------------------------

class TestLoadFromLabCases:
    def test_load_from_real_cases(self, lab_cases_dir):
        if not os.path.isdir(lab_cases_dir):
            pytest.skip("sprint4-lab/cases not found")
        svc = EvidenceLibraryService.load_from_lab_cases(lab_cases_dir)
        all_records = svc.all()
        # 至少有 BookConv 和 TJOstrichInk 两条
        assert len(all_records) >= 2
        case_ids = {r.case_id for r in all_records}
        assert "CASE-001" in case_ids
        assert "CASE-002" in case_ids

    def test_load_creates_valid_records(self, lab_cases_dir):
        if not os.path.isdir(lab_cases_dir):
            pytest.skip("sprint4-lab/cases not found")
        svc = EvidenceLibraryService.load_from_lab_cases(lab_cases_dir)
        for rec in svc.all():
            assert rec.case_id.startswith("CASE-")
            assert rec.baseline_visibility_score >= 0
            assert rec.delta >= 0  # 没有 re-measurement，delta=0
            assert rec.industry  # 行业不为空

    def test_load_empty_when_no_cases(self):
        svc = EvidenceLibraryService.load_from_lab_cases("/nonexistent/path")
        assert len(svc.all()) == 0

    def test_load_record_structure(self, lab_cases_dir):
        if not os.path.isdir(lab_cases_dir):
            pytest.skip("sprint4-lab/cases not found")
        svc = EvidenceLibraryService.load_from_lab_cases(lab_cases_dir)
        for rec in svc.all():
            d = rec.to_dict()
            required_keys = {
                "case_id", "distributor_id", "client_id", "industry",
                "baseline_visibility_score", "post_intervention_score",
                "intervention", "delta", "lift_pct", "status",
            }
            assert required_keys <= set(d.keys())


# ---------------------------------------------------------------------------
# Client-safe 约束
# ---------------------------------------------------------------------------

class TestClientSafe:
    def test_export_no_tech_leaks(self, sample_service):
        json_str = sample_service.export_json()
        data = json.loads(json_str)
        tech_keywords = ["raw_response", "browser_logs", "query_internals",
                         "provider_internals", "evidence_grading", "technical_notes"]
        for kw in tech_keywords:
            assert kw not in json_str

    def test_csv_no_tech_leaks(self, sample_service):
        csv_str = sample_service.export_csv()
        assert "raw_response" not in csv_str
        assert "browser_logs" not in csv_str

    def test_dashboard_no_tech_leaks(self, sample_service):
        dashboard = EvidenceDashboard(sample_service)
        summary = dashboard.summary()
        assert "raw_response" not in str(summary)


# ---------------------------------------------------------------------------
# 边界情况
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_single_record_aggregate(self):
        svc = EvidenceLibraryService()
        svc.add(_rec(delta=5.0))
        agg = svc.aggregate()
        assert agg["count"] == 1
        assert agg["avg_delta"] == 5.0
        assert agg["median_delta"] == 5.0
        assert agg["p25_delta"] == 5.0
        assert agg["p75_delta"] == 5.0

    def test_negative_delta(self):
        svc = EvidenceLibraryService()
        svc.add(_rec(delta=-10.0, base=50.0, post=40.0))
        agg = svc.aggregate()
        assert agg["avg_delta"] == -10.0
        assert agg["positive_rate"] == 0.0

    def test_mixed_delta_signs(self):
        svc = EvidenceLibraryService()
        svc.add(_rec(case_id="A", delta=20.0))
        svc.add(_rec(case_id="B", delta=-5.0))
        svc.add(_rec(case_id="C", delta=0.0))
        agg = svc.aggregate()
        assert agg["avg_delta"] == pytest.approx(5.0, abs=0.01)
        assert agg["positive_rate"] == pytest.approx(33.33, abs=0.1)

    def test_duplicate_case_id(self):
        """允许多条记录有相同 case_id（不同干预版本）。"""
        svc = EvidenceLibraryService()
        svc.add(_rec(case_id="CASE-X", delta=10.0))
        svc.add(_rec(case_id="CASE-X", delta=20.0))
        assert len(svc.all()) == 2
        assert len(svc.query(client_id="CLI-001")) == 2
