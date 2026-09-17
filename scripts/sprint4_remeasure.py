# -*- coding: utf-8 -*-
"""Sprint 4 — Day 7/14 Re-measurement Harness (Replay mode, zero-credential).

关闭 Milestone 1 的 Outcome 缺口。给定一份「与基线同源数据的手动重新导出」
（Bing AI Performance / GSC），保存为 canonical observations schema，计算
Baseline → Re-measurement Delta，并产出 client-safe 的 delta 报告。

Replay 模式：无 Live API。用户手动重新导出，脚本只做测量。
使用与基线**完全相同的 query set + total_queries 分母** → coverage 可比。

子命令：
    run             用已填好的 observations 文件计算 delta
    emit-template   写出一个空白 observations 模板，供填入真实 Day 7/14 数据

用法：
    python scripts/sprint4_remeasure.py run --case bookconv \\
        --input sprint4-lab/cases/bookconv/remeasurement/observations.DAY7.json
    python scripts/sprint4_remeasure.py emit-template --case bookconv \\
        --output sprint4-lab/cases/bookconv/remeasurement/observations.DAY7.json

护栏（防伪造，对应二轮 CEO 审计红线）：
- 模板未填（全部为 placeholder / not_collected）时，拒绝计算 delta，
  明确报错，绝不产出"看起来真实"的假数字。
- 报告顶部强制标注 DATA MODE = Replay（手动重导出），NOT live API。
- 明确区分 Product Validation（系统是否有效）≠ Commercial Validation（客户付钱）。
"""

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from geo_distributor.adapters.opengeo import OpenGeoAdapter
from geo_distributor.compatibility.opengeo import map_bing_ai_performance_row
from geo_distributor.services.measurement_analysis import aggregate_metrics
from geo_distributor.services.intervention_loop import (
    BaselineMetrics,
    DeltaCalculator,
)

LAB_ROOT = os.path.join(ROOT, "sprint4-lab", "cases")

# 案例注册表（brand/domain 仅用于 raw-bing 自动映射的便利项）
CASE_REGISTRY = {
    "bookconv": {"brand": "BookConv", "domain": "bookconv.com", "auto_map": "bing"},
    "tjostrichink": {"brand": "TJOstrichInk", "domain": "tjostrichink.com", "auto_map": None},
}


# ----------------------------------------------------------------------
# 路径与加载
# ----------------------------------------------------------------------

def resolve_case(case: str, lab_root: str = None) -> dict:
    """解析案例路径与配置。"""
    base = lab_root or LAB_ROOT
    case_dir = os.path.join(base, case)
    if not os.path.isdir(case_dir):
        raise FileNotFoundError(f"案例目录不存在: {case_dir}")
    baseline_dir = os.path.join(case_dir, "baseline")
    if not os.path.isdir(baseline_dir):
        raise FileNotFoundError(f"基线目录不存在: {baseline_dir}")
    cfg = CASE_REGISTRY.get(case, {"brand": case, "domain": "", "auto_map": None})
    return {
        "case": case,
        "case_dir": case_dir,
        "baseline_dir": baseline_dir,
        "remeasurement_dir": os.path.join(case_dir, "remeasurement"),
        "delta_dir": os.path.join(case_dir, "delta"),
        "brand": cfg["brand"],
        "domain": cfg["domain"],
        "auto_map": cfg["auto_map"],
    }


def load_query_set(baseline_dir: str) -> list:
    """读取基线 query set（用于 total_queries 分母与重测 query 列表）。"""
    qpath = os.path.join(baseline_dir, "query_set.json")
    if not os.path.isfile(qpath):
        return []
    with open(qpath, "r", encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, list):
        return [str(q) for q in data]
    if isinstance(data, dict):
        # 兼容 {"queries": [...]} 或 {"query_set": [...]}
        for key in ("queries", "query_set", "top_queries"):
            if key in data and isinstance(data[key], list):
                return [str(q) for q in data[key]]
    return []


def load_baseline_metrics(baseline_dir: str) -> BaselineMetrics:
    """从 baseline/metrics.json 读取基线指标。"""
    mpath = os.path.join(baseline_dir, "metrics.json")
    with open(mpath, "r", encoding="utf-8") as f:
        data = json.load(f)
    return BaselineMetrics(**data)


def detect_input_format(data) -> str:
    """自动识别输入格式：observations 列表 / raw-bing 导出 / observations 包裹。"""
    if isinstance(data, list):
        return "observations"
    if isinstance(data, dict):
        if "top_queries" in data:
            return "raw_bing"
        if "observations" in data and isinstance(data["observations"], list):
            return "observations"
    return "unknown"


def load_observations_from_input(path: str, case_cfg: dict) -> list:
    """从输入文件加载 PlatformObservation 列表（auto-map raw-bing 走 BookConv 便利路径）。"""
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    fmt = detect_input_format(data)
    if fmt == "observations":
        obs_list = data if isinstance(data, list) else data["observations"]
        return OpenGeoAdapter.from_dicts(obs_list)._observations
    if fmt == "raw_bing":
        if case_cfg["auto_map"] != "bing":
            raise ValueError(
                f"案例 {case_cfg['case']} 未注册 raw-bing 自动映射；"
                f"请将导出手动映射为 observations schema 后传入。"
            )
        snapshot = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        rows = data.get("top_queries", [])
        obs = [
            map_bing_ai_performance_row(
                r, brand=case_cfg["brand"], domain=case_cfg["domain"], snapshot_date=snapshot
            )
            for r in rows
        ]
        return obs
    raise ValueError(f"无法识别的输入格式（既非 observations 列表也非 raw-bing 导出）: {path}")


def _is_filled(obs) -> bool:
    """判断一条 observation 是否已被填入真实数据（非模板占位）。"""
    if getattr(obs, "raw_metadata", {}).get("placeholder"):
        return False
    if getattr(obs, "status", "") == "not_collected":
        return False
    if (getattr(obs, "recommendation_level", -1) or -1) < 0:
        return False
    return True


# ----------------------------------------------------------------------
# 核心管线
# ----------------------------------------------------------------------

def run_pipeline(case: str, input_path: str, day_label: str = "day7", lab_root: str = None) -> dict:
    """执行重测管线：基线 vs 重测 → Delta → 报告。返回结果字典。"""
    case_cfg = resolve_case(case, lab_root=lab_root)
    if not os.path.isfile(input_path):
        raise FileNotFoundError(f"重测输入文件不存在: {input_path}")

    query_set = load_query_set(case_cfg["baseline_dir"])
    total_queries = len(query_set) if query_set else None

    # 基线（来自存储的 metrics.json）
    baseline = load_baseline_metrics(case_cfg["baseline_dir"])
    case_id = baseline.case_id

    # 重测观测
    remeas_obs = load_observations_from_input(input_path, case_cfg)

    # 防伪造护栏：模板未填 → 拒绝
    filled = [o for o in remeas_obs if _is_filled(o)]
    if not filled:
        raise RuntimeError(
            "⛔ 拒绝计算 Delta：输入文件全部为占位/未采集观测（模板未填）。\n"
            "   请先填入真实的 Day 7/14 重新导出数据，再运行 run。\n"
            f"   输入: {input_path}"
        )
    if len(filled) < len(remeas_obs):
        coverage_warn = (
            f"⚠️ 部分观测未填（{len(filled)}/{len(remeas_obs)} 已填），"
            f"Delta 仅基于已填部分，覆盖率偏低，解读需谨慎。"
        )
    else:
        coverage_warn = None

    remeas_metrics = aggregate_metrics(
        remeas_obs, case_id=case_id, version="remeasurement", total_queries=total_queries
    )
    delta = DeltaCalculator.compute(baseline, remeas_metrics)

    # 写入产物
    os.makedirs(case_cfg["remeasurement_dir"], exist_ok=True)
    os.makedirs(case_cfg["delta_dir"], exist_ok=True)

    remeas_metrics_path = os.path.join(case_cfg["remeasurement_dir"], "metrics.json")
    with open(remeas_metrics_path, "w", encoding="utf-8") as f:
        json.dump(remeas_metrics.to_dict(), f, ensure_ascii=False, indent=2)

    delta_path = os.path.join(case_cfg["delta_dir"], "delta.json")
    with open(delta_path, "w", encoding="utf-8") as f:
        json.dump(delta, f, ensure_ascii=False, indent=2)

    report = generate_delta_report(
        case_id=case_id, brand=case_cfg["brand"], day_label=day_label,
        baseline=baseline, remeasurement=remeas_metrics, delta=delta,
        total_queries=total_queries, input_path=input_path,
        coverage_warn=coverage_warn,
    )
    report_path = os.path.join(case_cfg["remeasurement_dir"], "DELTA_REPORT.md")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report)

    return {
        "case_id": case_id,
        "brand": case_cfg["brand"],
        "day_label": day_label,
        "baseline": baseline,
        "remeasurement": remeas_metrics,
        "delta": delta,
        "total_queries": total_queries,
        "filled_count": len(filled),
        "total_obs": len(remeas_obs),
        "remeas_metrics_path": remeas_metrics_path,
        "delta_path": delta_path,
        "report_path": report_path,
        "coverage_warn": coverage_warn,
    }


def generate_delta_report(
    case_id, brand, day_label, baseline, remeasurement, delta,
    total_queries, input_path, coverage_warn,
) -> str:
    """生成 client-safe 的 Markdown Delta 报告（强制标注 Replay 模式）。"""
    now = datetime.now(timezone.utc).isoformat()
    pos = delta.get("avg_recommendation_level_delta", 0) > 0
    status = "POSITIVE ✅" if pos else ("NEGATIVE ❌" if delta.get("avg_recommendation_level_delta", 0) < 0 else "NEUTRAL")

    lines = []
    day_display = day_label.replace("day", "Day ")
    lines.append(f"# {day_display} Re-measurement Delta Report — {case_id}\n")
    lines.append("> **DATA MODE**: 🟡 Replay（手动重新导出 Bing AI Performance / GSC）。**NOT a live API measurement.**")
    lines.append(f"> **Generated**: {now}")
    lines.append("> **Caution**: 本 Delta 对比真实重新导出数据与基线真实导出，属于 **Product Validation**（系统是否显示效果），**≠ Commercial Validation**（客户是否付费）。\n")

    lines.append("## 1. Inputs")
    lines.append(f"- Case: `{case_id}` ({brand})")
    lines.append(f"- Query set: {total_queries} queries（与基线完全相同，保证分母一致）")
    lines.append(f"- Re-measurement source: `{input_path}`")
    lines.append(f"- Observations collected: {remeasurement.query_count} / {total_queries} (coverage {remeasurement.query_coverage}%)\n")

    if coverage_warn:
        lines.append(f"> {coverage_warn}\n")

    lines.append("## 2. Metrics Comparison")
    lines.append("| Metric | Baseline | Re-measure | Delta |")
    lines.append("|--------|----------|------------|-------|")
    rows = [
        ("Mention Rate %", baseline.mention_rate, remeasurement.mention_rate, delta["mention_delta"]),
        ("Citation Rate %", baseline.citation_rate, remeasurement.citation_rate, delta["citation_delta"]),
        ("Recommendation Rate %", baseline.recommendation_rate, remeasurement.recommendation_rate, delta["recommendation_delta"]),
        ("Query Coverage %", baseline.query_coverage, remeasurement.query_coverage, delta["query_coverage_delta"]),
        ("Avg Recommendation Level", baseline.avg_recommendation_level, remeasurement.avg_recommendation_level, delta["avg_recommendation_level_delta"]),
        ("Competitor Count", baseline.competitor_count, remeasurement.competitor_count, delta["competitor_delta"]),
    ]
    for name, b, r, d in rows:
        lines.append(f"| {name} | {b} | {r} | {d:+} |")
    lines.append("")

    lines.append("## 3. Delta Interpretation")
    lift = delta["avg_recommendation_level_delta"]
    lines.append(f"- **Visibility lift (avg_recommendation_level)**: {lift:+} → **{status}**")
    lines.append(f"- Mention/Citation/Recommendation 变化见上表。")
    lines.append(f"- 解读：{'可见度有正向改善迹象' if pos else '暂未见正向改善，需检查干预是否被正确收录'}。\n")

    lines.append("## 4. Evidence Record (draft)")
    baseline_score = baseline.avg_recommendation_level
    post_score = remeasurement.avg_recommendation_level
    lift_pct = round((post_score - baseline_score) / baseline_score * 100, 2) if baseline_score else 0.0
    lines.append(f"- case_id: `{case_id}`")
    lines.append(f"- baseline_visibility_score: {baseline_score}")
    lines.append(f"- post_intervention_score: {post_score}")
    lines.append(f"- delta: {lift}")
    lines.append(f"- lift_pct: {lift_pct}%")
    lines.append(f"- status: {status}\n")

    lines.append("## 5. Next")
    lines.append("- 通过 `EvidenceLibraryService.load_from_lab_cases()` 自动入库（读取 remeasurement/metrics.json）。")
    lines.append("- 当 delta 实质为正，Milestone 1 Outcome 升级为 PARTIAL/YES。")
    lines.append("- 仍属 Product Validation；商业验证需真实付费客户。")

    return "\n".join(lines) + "\n"


# ----------------------------------------------------------------------
# 模板生成
# ----------------------------------------------------------------------

def emit_template(case: str, output_path: str, lab_root: str = None) -> None:
    """生成空白 observations 模板（占位，标注 placeholder，需用户填入真实数据）。"""
    case_cfg = resolve_case(case, lab_root=lab_root)
    query_set = load_query_set(case_cfg["baseline_dir"])
    if not query_set:
        raise RuntimeError(f"案例 {case} 无 baseline/query_set.json，无法生成模板。")

    stubs = []
    for i, q in enumerate(query_set):
        stubs.append({
            "observation_id": f"obs_placeholder_{i:04d}",
            "prompt_id": i,
            "engine": "bing_ai",
            "timestamp": "",
            "prompt_text": q,
            "answer_raw": "",
            "answer_clean": "",
            "answer_char_count": 0,
            "extraction_method": "placeholder",
            "validation_status": "PENDING",
            "brand": case_cfg["brand"],
            "brand_mentioned": False,
            "brand_status": "NOT_COLLECTED",
            "first_mention_position": None,
            "recommendation_level": -1,
            "recommendation_rank": None,
            "recommendation_evidence": "",
            "competitors": [],
            "citations": [],
            "citations_status": "unavailable",
            "status": "not_collected",
            "raw_metadata": {"placeholder": True, "note": "FILL WITH REAL DAY 7/14 RE-EXPORT"},
        })

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(stubs, f, ensure_ascii=False, indent=2)
    print(f"✅ 模板已写出: {output_path}")
    print(f"   共 {len(stubs)} 条占位观测（= query set 大小）。")
    print(f"   请逐条替换为 Day 7/14 真实重新导出数据，然后运行 run。")


# ----------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Sprint 4 Day 7/14 Re-measurement Harness (Replay)")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_run = sub.add_parser("run", help="计算 delta（需已填好的 observations 输入）")
    p_run.add_argument("--case", required=True, help="案例目录名，如 bookconv / tjostrichink")
    p_run.add_argument("--input", required=True, help="已填好的 observations JSON 路径")
    p_run.add_argument("--day", default="day7", help="标签 day7 / day14")

    p_tpl = sub.add_parser("emit-template", help="生成空白 observations 模板")
    p_tpl.add_argument("--case", required=True)
    p_tpl.add_argument("--output", required=True, help="模板输出路径")

    args = parser.parse_args()

    if args.cmd == "emit-template":
        emit_template(args.case, args.output)
        return

    if args.cmd == "run":
        try:
            result = run_pipeline(args.case, args.input, day_label=args.day)
        except (RuntimeError, FileNotFoundError, ValueError) as e:
            print(str(e), file=sys.stderr)
            sys.exit(2)

        print(f"=== Re-measurement Delta ({result['case_id']}, {result['day_label']}) ===")
        for k, v in result["delta"].items():
            print(f"  {k}: {v}")
        print(f"Baseline:     mention={result['baseline'].mention_rate}% rec={result['baseline'].recommendation_rate}%")
        print(f"Re-measure:   mention={result['remeasurement'].mention_rate}% rec={result['remeasurement'].recommendation_rate}%")
        print(f"Filled:       {result['filled_count']}/{result['total_obs']}")
        print(f"Report:       {result['report_path']}")
        print(f"Metrics:      {result['remeas_metrics_path']}")
        print(f"Delta json:   {result['delta_path']}")


if __name__ == "__main__":
    main()
