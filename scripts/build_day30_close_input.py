# -*- coding: utf-8 -*-
"""Day30 窗口闭合版重测输入构造（2026-10-14 闭合日真实导出）。

仅做机械字段映射：保留与冻结 query set 精确匹配的行，零编造。
运行：在项目根执行  .venv/Scripts/python.exe scripts/build_day30_close_input.py
"""
import csv
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BING = "E:/一人公司/电子书格式转换站/ebook-converter/bookconv_data_asset/bing/"
SRC = BING + "www.bookconv.com_AISearchQueriesReport_2026_10_14.csv"
OUT = BING + "bing_analysis_2026-10-14_day30close.json"
QS = json.load(open(os.path.join(ROOT, "sprint4-lab/cases/bookconv/baseline/query_set.json"),
                    encoding="utf-8"))
qsset = set(QS)

with open(SRC, encoding="utf-8-sig") as f:
    rows = list(csv.DictReader(f))

matched = []
for r in rows:
    q = (r.get("Grounding Query") or "").strip()
    if q in qsset:
        matched.append({
            "query": q,
            "cites": int(r["Citations"].replace(",", "") or 0),
            "share": (r["Citation Share"] or "").strip(),
        })
matched.sort(key=lambda x: -x["cites"])

payload = {
    "measurement_note": (
        "窗口闭合版（2026-10-14 用户人工导出）由真实 Bing Webmaster Tools AI 性能分区导出 CSV 机械转换生成，"
        "仅保留冻结 query set（39 条）精确匹配行，零编造。"
        "注意：导出内含日序列数据截至 2026-10-11（Bing 报表固有 3 天滞后），10-12/13/14 无数据。"
        "本文件取代 10-08 中间版作为 Day30 终值（10-08 版保留于 bing_analysis_2026-10-08_day30.json）。"),
    "source_export": os.path.basename(SRC),
    "snapshot_date": "2026-10-14",
    "checkpoint": "Day30 (window-close)",
    "window_close_date": "2026-10-14",
    "csv_total_rows": len(rows),
    "query_set_exact_matches": len(matched),
    "brand_query_occurrences": sum(1 for r in rows if "bookconv" in (r.get("Grounding Query") or "").lower()),
    "top_queries": matched,
}
with open(OUT, "w", encoding="utf-8") as f:
    json.dump(payload, f, ensure_ascii=False, indent=2)

print(f"total_rows={len(rows)} matched={len(matched)} "
      f"brand_occurrences={payload['brand_query_occurrences']}")
for m in matched:
    print(f"   {m['query']} | {m['cites']} | {m['share']}")
