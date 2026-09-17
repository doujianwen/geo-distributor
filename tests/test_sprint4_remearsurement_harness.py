# -*- coding: utf-8 -*-
"""Sprint 4 Day 7/14 Re-measurement Harness 测试（隔离于临时目录）。

覆盖：
- 管线产出 delta + 报告 + metrics
- 防伪造护栏（模板未填 → 拒绝）
- emit-template 生成占位观测
- 输入格式自动识别
- 基线方法论一致性（重算 = 存储值）
"""

import json
import os
import shutil
import sys
import tempfile

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from scripts import sprint4_remeasure as harness  # noqa: E402


@pytest.fixture
def temp_lab():
    """复制真实 bookconv 基线到临时 lab，避免污染 sprint4-lab。"""
    tmp = tempfile.mkdtemp()
    src = os.path.join(ROOT, "sprint4-lab", "cases", "bookconv")
    dst = os.path.join(tmp, "bookconv")
    os.makedirs(dst)
    shutil.copytree(os.path.join(src, "baseline"), os.path.join(dst, "baseline"))
    yield tmp
    shutil.rmtree(tmp, ignore_errors=True)


def _make_filled_input(temp_lab):
    """基于真实基线观测生成"已改善"的填入数据（模拟 Day 7 重测）。"""
    base_obs = json.load(
        open(os.path.join(temp_lab, "bookconv", "baseline", "observations.json"), encoding="utf-8")
    )
    for o in base_obs:
        lvl = o.get("recommendation_level", -1)
        if lvl >= 0:
            o["recommendation_level"] = min(lvl + 1, 3)  # 模拟可见度提升
            o["brand_mentioned"] = True
            o["brand_status"] = "MENTIONED"
            o["status"] = "success"
    path = os.path.join(temp_lab, "bookconv", "remeasurement_input.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(base_obs, f, ensure_ascii=False, indent=2)
    return path


def test_run_pipeline_produces_delta(temp_lab):
    inp = _make_filled_input(temp_lab)
    result = harness.run_pipeline("bookconv", inp, day_label="day7", lab_root=temp_lab)
    assert result["delta"]["avg_recommendation_level_delta"] > 0
    assert os.path.isfile(result["report_path"])
    assert os.path.isfile(result["remeas_metrics_path"])
    assert os.path.isfile(result["delta_path"])
    # 报告顶部强制标注 Replay 模式
    report = open(result["report_path"], encoding="utf-8").read()
    assert "DATA MODE" in report and "Replay" in report
    assert "NOT a live API" in report


def test_guard_rejects_placeholder(temp_lab):
    tpl_path = os.path.join(temp_lab, "bookconv", "tpl.json")
    harness.emit_template("bookconv", tpl_path, lab_root=temp_lab)
    with pytest.raises(RuntimeError):
        harness.run_pipeline("bookconv", tpl_path, lab_root=temp_lab)


def test_emit_template(temp_lab):
    tpl_path = os.path.join(temp_lab, "bookconv", "tpl.json")
    harness.emit_template("bookconv", tpl_path, lab_root=temp_lab)
    data = json.load(open(tpl_path, encoding="utf-8"))
    qs = harness.load_query_set(os.path.join(temp_lab, "bookconv", "baseline"))
    assert len(data) == len(qs)
    assert all(d["raw_metadata"].get("placeholder") for d in data)
    assert all(d["status"] == "not_collected" for d in data)


def test_detect_input_format():
    assert harness.detect_input_format([{"a": 1}]) == "observations"
    assert harness.detect_input_format({"top_queries": []}) == "raw_bing"
    assert harness.detect_input_format({"observations": []}) == "observations"
    assert harness.detect_input_format({"foo": 1}) == "unknown"


def test_baseline_methodology_consistency(temp_lab):
    """重算基线指标应与存储的 metrics.json 一致（同 query set / 同分母）。"""
    from geo_distributor.adapters.opengeo import OpenGeoAdapter
    from geo_distributor.services.measurement_analysis import aggregate_metrics

    baseline = harness.load_baseline_metrics(os.path.join(temp_lab, "bookconv", "baseline"))
    obs = OpenGeoAdapter.from_json_file(
        os.path.join(temp_lab, "bookconv", "baseline", "observations.json")
    )._observations
    qs = harness.load_query_set(os.path.join(temp_lab, "bookconv", "baseline"))
    fresh = aggregate_metrics(obs, case_id=baseline.case_id, version="baseline", total_queries=len(qs))
    assert abs(fresh.avg_recommendation_level - baseline.avg_recommendation_level) < 0.001
    assert abs(fresh.query_coverage - baseline.query_coverage) < 0.01
    assert abs(fresh.mention_rate - baseline.mention_rate) < 0.01


def test_run_with_partial_fill_warns(temp_lab):
    """部分填入应产生 coverage_warn 但仍计算 delta。"""
    base_obs = json.load(
        open(os.path.join(temp_lab, "bookconv", "baseline", "observations.json"), encoding="utf-8")
    )
    # 只填前 3 条，其余保持占位
    for i, o in enumerate(base_obs):
        if i < 3:
            o["recommendation_level"] = 3
            o["brand_mentioned"] = True
            o["brand_status"] = "MENTIONED"
            o["status"] = "success"
            o["raw_metadata"] = {}
        else:
            o["raw_metadata"] = {"placeholder": True}
            o["status"] = "not_collected"
            o["recommendation_level"] = -1
    path = os.path.join(temp_lab, "bookconv", "partial.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(base_obs, f, ensure_ascii=False, indent=2)
    result = harness.run_pipeline("bookconv", path, lab_root=temp_lab)
    assert result["coverage_warn"] is not None
    assert result["filled_count"] == 3
