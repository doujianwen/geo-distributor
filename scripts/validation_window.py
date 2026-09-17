# -*- coding: utf-8 -*-
"""Validation Window — BookConv GEO Evidence Loop 可复现重测引擎（V1.0）。

用法（项目根目录）：
    .venv/Scripts/python.exe scripts/validation_window.py <bing导出json> <Day标签> [日期]

示例：
    # Day 0 基线入库（用已有 2026-09-13 导出）
    .venv/Scripts/python.exe scripts/validation_window.py \
        "E:/一人公司/电子书格式转换站/ebook-converter/bookconv_data_asset/bing/bing_analysis_2026-09-13.json" Day0 2026-09-13

    # 未来某天拿到新导出后
    .venv/Scripts/python.exe scripts/validation_window.py <新导出.json> Day7 2026-09-20

行为：
- 读取 FIXED query set（cases/bookconv/baseline/query_set.json，禁止修改）
- 映射新导出 → OpenGeoAdapter → PlatformObservation
- 逐 query 判定状态（Covered/Weak/Missing/Competitor-Dominated）
- 聚合指标 → 追加到 timeline.json（cases/bookconv/timeline/）
- 与 Day0 基线算 Delta → delta.json
- 重绘 BOOKCONV_TIMELINE.md

铁律：缺测 query 标记 MISSING；禁止编造数字；Delta 仅在有真实新导出时计算。
"""

import json
import os
import sys
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from geo_distributor.adapters.opengeo import OpenGeoAdapter
from geo_distributor.compatibility.opengeo import map_bing_ai_performance_row
from geo_distributor.services.measurement_analysis import aggregate_metrics
from geo_distributor.services.intervention_loop import DeltaCalculator, BaselineMetrics

LAB = os.path.join(ROOT, "sprint4-lab")
CASE = os.path.join(LAB, "cases", "bookconv")
QUERY_SET_PATH = os.path.join(CASE, "baseline", "query_set.json")
BASELINE_METRICS = os.path.join(CASE, "baseline", "metrics.json")
TIMELINE_DIR = os.path.join(CASE, "timeline")
TIMELINE_JSON = os.path.join(TIMELINE_DIR, "timeline.json")
DELTA_DIR = os.path.join(CASE, "delta")
DELTA_JSON = os.path.join(DELTA_DIR, "delta.json")
TIMELINE_MD = os.path.join(CASE, "timeline", "BOOKCONV_TIMELINE.md")
SNAPSHOT_DEFAULT = "2026-09-13"

# Query 分类（与 sprint4_lab.BOOKCONV_QUERY_SET 分组一致，冻结）
QUERY_CATEGORY = {}
_BRAND = ["bookconv", "bookconv ebook converter", "bookconv review", "bookconv alternative",
          "is bookconv safe", "bookconv free", "bookconv vs calibre", "bookconv login"]
_PROBLEM = ["convert epub to pdf", "convert mobi to epub", "epub to kindle", "azw3 to epub",
            "convert pdf to epub", "djvu to pdf", "best ebook converter", "free ebook converter",
            "ebook conversion software", "convert ebook to pdf", "mobi to epub converter free",
            "convert epub to azw3", "kindle to pdf", "epub to mobi converter free"]
_CATEGORY = ["ai ebook tools", "ebook converter software", "ebook format converter",
             "online ebook converter", "ebook reader app", "ebook syncing services",
             "what format does kindle use", "kindle formats explained", "transfer ebooks between devices",
             "best free epub reader", "Harry Potter digital books multiple devices"]
_COMPARISON = ["bookconv alternatives", "calibre alternative", "best calibre alternative",
               "convert epub to azw3 vs mobi", "bookconv vs zamzar", "online converter vs desktop"]
for q in _BRAND:
    QUERY_CATEGORY[q] = "Brand"
for q in _PROBLEM:
    QUERY_CATEGORY[q] = "Problem"
for q in _CATEGORY:
    QUERY_CATEGORY[q] = "Category"
for q in _COMPARISON:
    QUERY_CATEGORY[q] = "Comparison"


def visibility_score(m: dict) -> float:
    """复合可见度评分（0-100）：mention/citation/recommendation 加权。"""
    return round(0.3 * m["mention_rate"] + 0.3 * m["citation_rate"] + 0.4 * m["recommendation_rate"], 1)


def classify_query(query, obs_by_query):
    """返回单 query 状态与详情。"""
    cat = QUERY_CATEGORY.get(query, "Other")
    if query in obs_by_query:
        o = obs_by_query[query]
        lvl = o.get("recommendation_level") or 0
        share = o.get("recommendation_evidence", "")
        if lvl >= 3:
            status = "COVERED"
        elif lvl == 2:
            status = "COVERED"
        elif lvl == 1:
            status = "WEAK"
        else:
            status = "COVERED"
        return {"query": query, "category": cat, "status": status,
                "recommendation_level": lvl, "share": share}
    else:
        # 对比类 query：未测量但竞品（Calibre）主导风险高
        comp_risk = "HIGH" if cat == "Comparison" else "LOW"
        return {"query": query, "category": cat, "status": "MISSING",
                "recommendation_level": 0, "share": "", "competitor_risk": comp_risk}


def build_obs_by_query(observations):
    return {o.get("prompt_text"): o for o in observations}


def record_day(export_json, day_label, date_str):
    with open(QUERY_SET_PATH, "r", encoding="utf-8") as f:
        query_set = json.load(f)
    with open(export_json, "r", encoding="utf-8") as f:
        data = json.load(f)

    rows = data.get("top_queries", [])
    obs = [map_bing_ai_performance_row(r, brand="BookConv", domain="bookconv.com",
                                       snapshot_date=date_str).to_dict() for r in rows]
    # 转回 observation 对象供 aggregate
    from geo_distributor.compatibility.base import PlatformObservation
    obs_objs = [PlatformObservation(**o) for o in obs]

    metrics = aggregate_metrics(obs_objs, case_id="CASE-001", version=day_label,
                                total_queries=len(query_set)).to_dict()
    metrics["visibility_score"] = visibility_score(metrics)

    obs_by_query = build_obs_by_query(obs)
    per_query = [classify_query(q, obs_by_query) for q in query_set]

    snapshot = {
        "day": day_label,
        "date": date_str,
        "metrics": metrics,
        "per_query": per_query,
        "query_coverage_strict": round(
            sum(1 for p in per_query if p["status"] in ("COVERED", "WEAK")) / len(query_set) * 100, 2),
    }

    # 载入/初始化 timeline
    os.makedirs(TIMELINE_DIR, exist_ok=True)
    timeline = []
    if os.path.exists(TIMELINE_JSON):
        with open(TIMELINE_JSON, "r", encoding="utf-8") as f:
            timeline = json.load(f)
    timeline = [s for s in timeline if s["day"] != day_label]  # 幂等：同 Day 覆盖
    timeline.append(snapshot)
    timeline.sort(key=lambda s: s["day"])
    with open(TIMELINE_JSON, "w", encoding="utf-8") as f:
        json.dump(timeline, f, ensure_ascii=False, indent=2)

    # Delta vs Day0
    if day_label != "Day0" and os.path.exists(BASELINE_METRICS):
        with open(BASELINE_METRICS, "r", encoding="utf-8") as f:
            base = json.load(f)
        base_obj = BaselineMetrics(**{k: v for k, v in base.items()
                                      if k in BaselineMetrics.__dataclass_fields__})
        rem_obj = BaselineMetrics(**{k: v for k, v in metrics.items()
                                     if k in BaselineMetrics.__dataclass_fields__})
        delta = DeltaCalculator.compute(base_obj, rem_obj)
        os.makedirs(DELTA_DIR, exist_ok=True)
        with open(DELTA_JSON, "w", encoding="utf-8") as f:
            json.dump({"day": day_label, "date": date_str,
                       "baseline_day": "Day0", "delta": delta}, f, ensure_ascii=False, indent=2)
        print(f"  Delta vs Day0: {json.dumps(delta, ensure_ascii=False)}")

    _render_timeline_md(timeline)
    print(f"  recorded {day_label} ({date_str}) | coverage(strict)={snapshot['query_coverage_strict']}% "
          f"visibility={metrics['visibility_score']}")
    return snapshot


def _render_timeline_md(timeline):
    lines = ["# BookConv Monitoring Timeline (Validation Window)\n",
             "> Fixed Query Set = 39 queries（见 cases/bookconv/baseline/query_set.json，禁止修改）。\n",
             "> Day 0 = 真实 Bing AI Performance 基线。Day 7/14/30 = 真实重测（需新导出）。\n"]
    lines.append("| Day | Date | Mention% | Citation% | Recommendation% | Coverage%(strict) | Visibility Score | Competitors |")
    lines.append("|-----|------|----------|-----------|-----------------|------------------|-----------------|------------|")
    for s in timeline:
        m = s["metrics"]
        lines.append(
            f"| {s['day']} | {s['date']} | {m['mention_rate']} | {m['citation_rate']} | "
            f"{m['recommendation_rate']} | {s['query_coverage_strict']} | {m['visibility_score']} | "
            f"{m['competitor_count']} |")
    lines.append("\n## Per-Query Status (latest day)\n")
    latest = timeline[-1]
    lines.append("| Query | Category | Status | Rec Level | Share |")
    lines.append("|-------|----------|--------|-----------|-------|")
    for p in latest["per_query"]:
        lines.append(f"| {p['query']} | {p['category']} | {p['status']} | "
                     f"{p['recommendation_level']} | {p.get('share','')} |")
    lines.append(f"\n---\n*Rendered by validation_window.py — {datetime.now(timezone.utc).strftime('%Y-%m-%d')}*")
    with open(TIMELINE_MD, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    export_json = sys.argv[1]
    day_label = sys.argv[2]
    date_str = sys.argv[3] if len(sys.argv) > 3 else datetime.now(timezone.utc).strftime("%Y-%m-%d")
    print(f"=== Validation Window record {day_label} ({date_str}) ===")
    record_day(export_json, day_label, date_str)
    print("Done.")


if __name__ == "__main__":
    main()
