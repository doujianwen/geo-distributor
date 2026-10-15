# -*- coding: utf-8 -*-
"""Control Group Day30 re-measurement — TJOstrichInk GSC 2026-10-14 真实导出。

与 sprint4_lab.load_ostrich_observations 完全同一管线：
  查询数.csv → map_gsc_row → aggregate_metrics(total_queries=30)
零编造：所有数值机械来源于真实 GSC 导出。
同时归档人工导出文件到规范位置。
"""
import csv
import json
import os
import shutil
import sys
from datetime import datetime, timezone

ROOT = r"E:\GEO项目\技术层\geo-distributor"
sys.path.insert(0, ROOT)

from geo_distributor.compatibility.opengeo import map_gsc_row
from geo_distributor.compatibility.base import PlatformObservation
from geo_distributor.services.measurement_analysis import aggregate_metrics

SRC_DIR = r"C:\Users\29537\Downloads\https___www.tjostrichink.com_-Performance-on-Search-2026-10-14"
QUERY_CSV = os.path.join(SRC_DIR, "查询数.csv")
CTRL_ARCHIVE = r"E:\GEO项目\应用层\ostrich-ink\gsc-data-2026-10-14"
BC_DL = r"C:\Users\29537\Downloads"
BC_ARCHIVE = r"E:\一人公司\电子书格式转换站\ebook-converter\bookconv_data_asset\bing"
LAB = os.path.join(ROOT, "sprint4-lab", "cases", "tjostrichink")
TIMELINE_DIR = os.path.join(LAB, "timeline")
TOTAL_PLANNED = 30  # 与 Day0 相同口径（coverage 153.33% = 46/30）

# ---- 1. 读取真实 GSC 导出并走同一映射管线 ----
obs = []
with open(QUERY_CSV, "r", encoding="utf-8-sig") as f:
    reader = csv.DictReader(f)
    for row in reader:
        mapped = map_gsc_row({
            "query": row.get("热门查询", ""),
            "clicks": row.get("点击次数", 0),
            "impressions": row.get("展示", 0),
            "ctr": row.get("点击率", 0),
            "position": row.get("排名", 0),
        }, brand="OSTRICH Ink", domain="tjostrichink.com")
        obs.append(mapped)

metrics = aggregate_metrics(obs, case_id="CASE-002", version="Day30",
                            total_queries=TOTAL_PLANNED).to_dict()
metrics["captured_at"] = datetime.now(timezone.utc).isoformat()

print(f"[Control Day30] queries={len(obs)}")
print(json.dumps(metrics, ensure_ascii=False, indent=2))

# ---- 2. 写入对照组 timeline（Day0 基线 + Day30） ----
day0 = json.load(open(os.path.join(LAB, "baseline", "metrics.json"), encoding="utf-8"))
snapshot30 = {"day": "Day30", "date": "2026-10-14", "metrics": metrics,
              "source": "GSC 人工导出 2026-10-14（用户手测）", "query_count_raw": len(obs)}
os.makedirs(TIMELINE_DIR, exist_ok=True)
timeline_path = os.path.join(TIMELINE_DIR, "timeline.json")
timeline = []
if os.path.exists(timeline_path):
    timeline = json.load(open(timeline_path, encoding="utf-8"))
timeline = [s for s in timeline if s.get("day") != "Day30"]
timeline.append(snapshot30)
timeline.sort(key=lambda s: s["day"])
with open(timeline_path, "w", encoding="utf-8") as f:
    json.dump(timeline, f, ensure_ascii=False, indent=2)

# delta Day0 → Day30（同字段对齐）
delta = {}
for k in ("mention_rate", "citation_rate", "recommendation_rate", "query_coverage",
          "avg_recommendation_level", "competitor_count"):
    if k in day0 and k in metrics:
        delta[k + "_delta"] = round(metrics[k] - day0[k], 3)
with open(os.path.join(TIMELINE_DIR, "delta_day30.json"), "w", encoding="utf-8") as f:
    json.dump({"baseline": "Day0(2026-09-13)", "remeasure": "Day30(2026-10-14)",
               "delta": delta}, f, ensure_ascii=False, indent=2)
print("delta:", json.dumps(delta, ensure_ascii=False))

# ---- 3. 归档人工导出（对照组 GSC 全套 + bookconv 传统 4 件） ----
if not os.path.isdir(CTRL_ARCHIVE):
    os.makedirs(CTRL_ARCHIVE)
for name in os.listdir(SRC_DIR):
    src = os.path.join(SRC_DIR, name)
    if os.path.isfile(src):
        shutil.copy2(src, os.path.join(CTRL_ARCHIVE, name))
        print("archived(control):", name)

bc_files = ["www.bookconv.com_SearchPerformanceOverview_All_2026_10_14.csv",
            "www.bookconv.com_KeywordReport_2026_10_14.csv",
            "www.bookconv.com_PageTrafficReport_2026_10_14.csv",
            "www.bookconv.com_CountryReport_2026_10_14.csv"]
for name in bc_files:
    src = os.path.join(BC_DL, name)
    if os.path.isfile(src):
        shutil.copy2(src, os.path.join(BC_ARCHIVE, name))
        print("archived(bookconv):", name)
    else:
        print("MISSING(bookconv):", name)

print("DONE")
