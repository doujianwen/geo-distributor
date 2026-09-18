"""业务验证脚本 — 用真实案例跑完整四阶段客户服务流程。

目的
----
验证"代码存在"之外，业务能力是否真的跑得通：
    网站诊断 → 竞品分析 → 优化提升 → 效果监控

使用真实案例（非 mock）：
    - bookconv      : 15 queries, mention 100%, rec 86.67%
    - tjostrichink  : 46 queries, mention 100%, rec 23.91%, citation 0%

**红线（不可违反）**：
    - 效果监控阶段若无复测数据，输出 status=NOT_AVAILABLE，delta=None
    - 绝不编造改善幅度、绝不输出未经采集的数字

运行：
    .venv/Scripts/python.exe scripts/business_validation.py

输出：
    exports/validation/<case>_<timestamp>.json
    exports/validation/<case>_<timestamp>.md
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from typing import Any, Dict, List, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient  # noqa: E402

from api.app import app  # noqa: E402
from geo_distributor.config import get_project_root  # noqa: E402
from geo_distributor.services.competitive_analysis import (  # noqa: E402
    analyze_competitors as analyze_competitors_service,
)

CASES = {
    "bookconv": {
        "client_name": "BookConv",
        "industry": "EdTech / eBook Converter",
        "brand": "BookConv",
        "business_question": "Why is BookConv absent from AI answers about ebook conversion?",
    },
    "tjostrichink": {
        "client_name": "TJ Ostrich Ink",
        "industry": "Creative / Art Supplies",
        "brand": "TJ Ostrich Ink",
        "business_question": "How visible is TJ Ostrich Ink in AI recommendations?",
        "adapter": "opengeo",
    },
    # 该案例来自 geo-collector SQLite（473 条观测，含竞品抽取），
    # 用于验证「有竞品数据时阶段 2 能否真正产出」——
    # 与上面两个 sprint4 快照案例（无竞品字段）形成对照。
    "hydroviv": {
        "client_name": "Hydroviv",
        "industry": "Water Filtration",
        "brand": "Hydroviv",
        "business_question": "How does Hydroviv compare to competitors in AI answers?",
        "adapter": "geo-collector-db",
    },
}

TENANT = "DST-VALIDATION"


# ----------------------------------------------------------------------
# 阶段 2：竞品分析（从观测中提取竞品提及）
# ----------------------------------------------------------------------

def analyze_competitors(
    observations: List[Dict[str, Any]],
    brand: str = "",
    project_id: str = "",
    case_id: str = "",
) -> Dict[str, Any]:
    """竞品分析 —— 委托给 geo_distributor.services.competitive_analysis。

    ⚠️ 旧版本在此处用 `c.get("name")` 读竞品名，但采集侧字段实际是 `brand`，
    导致竞品**永远解析为空**、阶段 2 恒为 NO_DATA。现统一走服务，
    服务内按 `brand` 解析并兼容多种形态。

    无竞品数据时服务返回 has_data=False，本函数对应 empty=True，
    报告层据此标注 COMPLETED_NO_DATA——不伪造竞品名单。
    """
    r = analyze_competitors_service(
        observations, brand=brand, project_id=project_id, case_id=case_id
    )
    return {
        "empty": not r.has_data,
        "unique_competitors": len(r.competitors),
        "total_competitor_mentions": r.total_competitor_mentions,
        "observations_with_competitors": r.observations_with_competitors,
        "ranked": [
            {
                "name": c.brand,
                "mentions": c.mention_count,
                "share_of_voice": f"{c.share_of_voice:.1f}%",
                "mention_rate": f"{c.mention_rate:.1f}%",
                "avg_position": c.avg_position,
            }
            for c in r.competitors[:10]
        ],
        "note": r.data_note,
        "brand_mention_rate": r.brand_mention_rate,
        "brand_recommendation_rate": r.brand_recommendation_rate,
        "competitive_findings": [
            {"severity": f.severity.value, "statement": f.statement}
            for f in r.findings
        ],
    }


# ----------------------------------------------------------------------
# 阶段 3：优化提升（由 Finding 推导干预清单）
# ----------------------------------------------------------------------

_SEVERITY_ORDER = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3, "INFO": 4}

_ACTION_BY_CATEGORY = {
    "visibility_gap": "建设实体页（Organization/Product Schema + sameAs），补齐 AI 可核验的身份基线",
    "citation_quality": "提升内容权威性：补充一手数据、专家署名、可引用结论块",
    "competitive_disadvantage": "针对竞品占据的查询做对比型内容与差异化事实点",
    "content_gap": "补齐该查询意图下的专题内容，覆盖 AI 倾向引用的结构化答案",
    "entity_weakness": "统一品牌名/产品名写法，跨语言实体归一（中英文共用同一 @id）",
    "technical_issue": "修复抓取与结构化标记问题（llms.txt / Schema @graph）",
}


def build_intervention_plan(findings: List[Dict[str, Any]]) -> Dict[str, Any]:
    """按严重度排序，产出可执行的干预清单（不宣称效果）。"""
    ordered = sorted(
        findings,
        key=lambda f: _SEVERITY_ORDER.get(str(f.get("severity", "")).upper(), 9),
    )

    by_category: Dict[str, int] = {}
    for f in findings:
        by_category[f.get("category", "unknown")] = (
            by_category.get(f.get("category", "unknown"), 0) + 1
        )

    plan = []
    for i, f in enumerate(ordered[:10], 1):
        cat = f.get("category", "unknown")
        plan.append({
            "priority": i,
            "finding_id": f.get("finding_id", ""),
            "severity": f.get("severity", ""),
            "category": cat,
            "statement": f.get("statement", ""),
            "action": _ACTION_BY_CATEGORY.get(cat, "待人工评估"),
        })

    return {
        "total_findings": len(findings),
        "by_category": by_category,
        "top_actions": plan,
        "disclaimer": (
            "Actions are derived from observed patterns. No ranking, traffic, "
            "lead or revenue improvement is guaranteed or implied."
        ),
    }


# ----------------------------------------------------------------------
# 阶段 4：效果监控
# ----------------------------------------------------------------------

def check_remeasurement(case_id: str, project_root: str) -> Dict[str, Any]:
    """检查复测数据是否存在。

    **红线**：不存在时返回 NOT_AVAILABLE，delta=None。绝不编造改善数字。
    """
    remeasure_path = os.path.join(
        project_root, "sprint4-lab", "cases", case_id, "remeasurement", "observations.json"
    )
    if not os.path.exists(remeasure_path):
        return {
            "status": "NOT_AVAILABLE",
            "reason": f"No remeasurement data found at {remeasure_path}",
            "baseline_captured": True,
            "remeasurement_captured": False,
            "delta": None,
            "next_action": "Schedule re-collection (recommended: 30 days after baseline)",
        }
    # 存在复测数据时才计算 delta（此处保留实现位，避免未来伪造）
    with open(remeasure_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return {
        "status": "AVAILABLE",
        "remeasurement_captured": True,
        "observation_count": len(data) if isinstance(data, list) else 0,
        "delta": None,  # 需与 baseline 对齐后计算，见 TODO
    }


# ----------------------------------------------------------------------
# 主流程
# ----------------------------------------------------------------------

def run_case(case_id: str, client: TestClient) -> Dict[str, Any]:
    cfg = CASES[case_id]
    project_root = get_project_root()
    result: Dict[str, Any] = {
        "case_id": case_id,
        "client_name": cfg["client_name"],
        "tenant_id": TENANT,
        "started_at": datetime.now().isoformat(),
        "stages": {},
    }

    # --- Setup: Client + Project ---
    r = client.post(
        "/clients",
        json={"name": cfg["client_name"], "industry": cfg["industry"]},
        headers={"X-Tenant-ID": TENANT},
    )
    assert r.status_code == 201, f"client create failed: {r.text}"
    client_id = r.json()["client_id"]

    r = client.post(
        "/projects",
        json={
            "tenant_id": TENANT,
            "client_id": client_id,
            "service": "visibility_audit",
            "target_market": ["US"],
            "business_question": cfg["business_question"],
        },
        headers={"X-Tenant-ID": TENANT},
    )
    assert r.status_code == 201, f"project create failed: {r.text}"
    project_id = r.json()["project_id"]
    result["client_id"] = client_id
    result["project_id"] = project_id

    # ==================================================================
    # 阶段 1 · 网站诊断
    # ==================================================================
    r = client.post(
        "/measurements",
        json={
            "project_id": project_id,
            "case_id": case_id,
            "adapter": cfg.get("adapter", "opengeo"),
            "tenant_id": TENANT,
        },
        headers={"X-Tenant-ID": TENANT},
    )
    assert r.status_code == 201, f"measurement failed: {r.text}"
    measurement = r.json()
    metrics = measurement.get("metrics", {})
    findings = measurement.get("findings", [])
    observations = measurement.get("observations", [])

    result["stages"]["1_site_diagnosis"] = {
        "stage": "site_diagnosis",
        "status": "COMPLETED",
        "query_count": metrics.get("query_count"),
        "mention_rate": metrics.get("mention_rate"),
        "recommendation_rate": metrics.get("recommendation_rate"),
        "avg_recommendation_level": metrics.get("avg_recommendation_level"),
        "citation_rate": metrics.get("citation_rate"),
        "finding_count": len(findings),
        "measurement_id": measurement.get("measurement_id"),
    }

    # ==================================================================
    # 阶段 2 · 竞品分析
    # ==================================================================
    competitor = analyze_competitors(
        observations,
        brand=cfg["brand"],
        project_id=project_id,
        case_id=case_id,
    )
    result["stages"]["2_competitor_analysis"] = {
        "stage": "competitor_analysis",
        "status": "COMPLETED_NO_DATA" if competitor["empty"] else "COMPLETED",
        **competitor,
    }

    # 推进阶段（登记阶段 1/2 产出）
    finding_ids = [f.get("finding_id", "") for f in findings]
    client.post(
        f"/projects/{project_id}/stage",
        json={"finding_ids": finding_ids[:50]},
        headers={"X-Tenant-ID": TENANT},
    )

    # ==================================================================
    # 阶段 3 · 优化提升
    # ==================================================================
    plan = build_intervention_plan(findings)
    result["stages"]["3_optimization"] = {
        "stage": "optimization",
        "status": "COMPLETED",
        **plan,
    }
    client.post(
        f"/projects/{project_id}/stage",
        json={},
        headers={"X-Tenant-ID": TENANT},
    )

    # ==================================================================
    # 阶段 4 · 效果监控
    # ==================================================================
    remeasure = check_remeasurement(case_id, project_root)
    result["stages"]["4_effect_monitoring"] = {
        "stage": "effect_monitoring",
        "status": remeasure["status"],
        **remeasure,
    }
    client.post(
        f"/projects/{project_id}/stage",
        json={},
        headers={"X-Tenant-ID": TENANT},
    )
    # 最终阶段无法再"推进"，需显式收口，否则进度停在 75% 以下
    client.post(
        f"/projects/{project_id}/stage/complete",
        headers={"X-Tenant-ID": TENANT},
    )

    # --- 项目最终状态 ---
    st = client.get(f"/projects/{project_id}/stage", headers={"X-Tenant-ID": TENANT}).json()
    result["final_stage"] = st["current_stage"]
    result["stage_progress"] = st["stage_progress"]
    result["completed_at"] = datetime.now().isoformat()

    return result


def render_markdown(result: Dict[str, Any]) -> str:
    """渲染人类可读的验证报告（Client-safe 口径）。"""
    s = result["stages"]
    d = s["1_site_diagnosis"]
    c = s["2_competitor_analysis"]
    o = s["3_optimization"]
    m = s["4_effect_monitoring"]

    lines = [
        f"# 业务验证报告 · {result['client_name']}",
        "",
        f"- 案例：`{result['case_id']}`",
        f"- Tenant：`{result['tenant_id']}`",
        f"- Project：`{result['project_id']}`",
        f"- 开始：{result['started_at']}",
        f"- 完成：{result['completed_at']}",
        f"- 最终阶段：**{result['final_stage']}**（进度 {result['stage_progress']}%）",
        "",
        "## 阶段 1 · 网站诊断",
        "",
        "| 指标 | 值 |",
        "|------|-----|",
        f"| 查询数 | {d['query_count']} |",
        f"| 品牌提及率 | {d['mention_rate']}% |",
        f"| 推荐率 | {d['recommendation_rate']}% |",
        f"| 平均推荐等级 | {d['avg_recommendation_level']} |",
        f"| 引用率 | {d.get('citation_rate')}% |",
        f"| Findings | {d['finding_count']} |",
        "",
        "## 阶段 2 · 竞品分析",
        "",
    ]

    if c["empty"]:
        lines += [f"> ⚠️ {c['note']}", ""]
    else:
        lines += [
            f"本品牌提及率 **{c['brand_mention_rate']}%**，"
            f"推荐率 **{c['brand_recommendation_rate']}%**。",
            "",
            "| 竞品 | 提及次数 | 提及率 | SOV | 平均位次 |",
            "|------|---------|--------|-----|---------|",
        ]
        for item in c["ranked"]:
            avg = item["avg_position"]
            avg_txt = f"{avg:.2f}" if isinstance(avg, (int, float)) else "—"
            lines.append(
                f"| {item['name']} | {item['mentions']} | {item['mention_rate']} "
                f"| {item['share_of_voice']} | {avg_txt} |"
            )
        lines.append("")
        if c["competitive_findings"]:
            lines += ["**竞品格局结论：**", ""]
            for f in c["competitive_findings"]:
                lines.append(f"- `{f['severity']}` {f['statement']}")
            lines.append("")

    lines += [
        "## 阶段 3 · 优化提升",
        "",
        f"共 {o['total_findings']} 条 Finding，按类别分布：",
        "",
        "| 类别 | 数量 |",
        "|------|------|",
    ]
    for cat, cnt in o["by_category"].items():
        lines.append(f"| {cat} | {cnt} |")
    lines += ["", "**优先行动（Top 5）**", ""]
    for a in o["top_actions"][:5]:
        lines.append(f"{a['priority']}. 【{a['severity']}】{a['statement'][:80]}")
        lines.append(f"   - 动作：{a['action']}")
    lines.append("")
    lines.append(f"> {o['disclaimer']}")
    lines.append("")

    lines += [
        "## 阶段 4 · 效果监控",
        "",
        f"- 状态：**{m['status']}**",
    ]
    if m["status"] == "NOT_AVAILABLE":
        lines += [
            f"- 原因：{m['reason']}",
            f"- 下一步：{m['next_action']}",
            "",
            "> 本报告**不提供**效果改善数字——尚无复测数据，任何改善幅度均为推测。",
        ]
    else:
        lines += [f"- 复测观测数：{m.get('observation_count')}"]

    return "\n".join(lines)


def main() -> int:
    project_root = get_project_root()
    out_dir = os.path.join(project_root, "exports", "validation")
    os.makedirs(out_dir, exist_ok=True)

    print("=" * 64)
    print("业务验证 · 真实案例四阶段全流程")
    print("=" * 64)

    with TestClient(app) as client:
        for case_id in CASES:
            print(f"\n--- {case_id} ---")
            result = run_case(case_id, client)
            ts = datetime.now().strftime("%Y%m%d-%H%M%S")

            json_path = os.path.join(out_dir, f"{case_id}_{ts}.json")
            md_path = os.path.join(out_dir, f"{case_id}_{ts}.md")
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
            with open(md_path, "w", encoding="utf-8") as f:
                f.write(render_markdown(result))

            d = result["stages"]["1_site_diagnosis"]
            m = result["stages"]["4_effect_monitoring"]
            print(f"  阶段1 诊断: {d['query_count']} queries, mention {d['mention_rate']}%, "
                  f"rec {d['recommendation_rate']}%, {d['finding_count']} findings")
            print(f"  阶段2 竞品: {result['stages']['2_competitor_analysis']['status']}")
            print(f"  阶段3 优化: {result['stages']['3_optimization']['total_findings']} findings → "
                  f"{len(result['stages']['3_optimization']['by_category'])} 类行动")
            print(f"  阶段4 监控: {m['status']}")
            print(f"  最终阶段: {result['final_stage']} ({result['stage_progress']}%)")
            print(f"  输出: {md_path}")

    print("\n" + "=" * 64)
    print("验证完成")
    print("=" * 64)
    return 0


if __name__ == "__main__":
    sys.exit(main())
