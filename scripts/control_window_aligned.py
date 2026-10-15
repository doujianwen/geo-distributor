# -*- coding: utf-8 -*-
"""对照组窗口对齐对比 — 用 图表.csv 日序列消除「过去3个月」滚动窗口口径漂移。

Day0 快照 = 2026-09-13，Day30 快照 = 2026-10-14（数据至 10-11）。
窗口 A（Day0 前 28 天）= 2026-08-17 → 2026-09-13
窗口 B（Day30 前 28 天）= 2026-09-14 → 2026-10-11
两窗口等长 → clicks/impressions/CTR/加权平均排名 直接可比。
"""
import csv
import json
from datetime import date

SRC = r"C:\Users\29537\Downloads\https___www.tjostrichink.com_-Performance-on-Search-2026-10-14\图表.csv"

rows = []
with open(SRC, "r", encoding="utf-8-sig") as f:
    for r in csv.DictReader(f):
        rows.append({
            "date": date.fromisoformat(r["日期"].strip()),
            "clicks": int(r["点击次数"]),
            "impressions": int(r["展示"]),
            "position": float(r["排名"]),
        })

rows.sort(key=lambda x: x["date"])
print(f"total days: {len(rows)}, range: {rows[0]['date']} → {rows[-1]['date']}")


def window(start: date, end: date):
    sel = [r for r in rows if start <= r["date"] <= end]
    clicks = sum(r["clicks"] for r in sel)
    impressions = sum(r["impressions"] for r in sel)
    ctr = round(clicks / impressions * 100, 2) if impressions else 0.0
    wpos = (round(sum(r["position"] * r["impressions"] for r in sel) / impressions, 2)
            if impressions else 0.0)
    return {"window": f"{start}→{end}", "days": len(sel), "clicks": clicks,
            "impressions": impressions, "ctr_pct": ctr, "weighted_avg_position": wpos}


A = window(date(2026, 8, 17), date(2026, 9, 13))   # Day0 前 28 天
B = window(date(2026, 9, 14), date(2026, 10, 11))  # Day30 前 28 天
delta = {
    "clicks_delta": B["clicks"] - A["clicks"],
    "impressions_delta": B["impressions"] - A["impressions"],
    "ctr_delta_pp": round(B["ctr_pct"] - A["ctr_pct"], 2),
    "position_delta": round(B["weighted_avg_position"] - A["weighted_avg_position"], 2),
}
out = {"window_A_before_Day0": A, "window_B_before_Day30": B, "delta": delta}
print(json.dumps(out, ensure_ascii=False, indent=2))

dst = r"E:\GEO项目\技术层\geo-distributor\sprint4-lab\cases\tjostrichink\timeline\control_window_aligned.json"
with open(dst, "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=2)
print("written:", dst)
