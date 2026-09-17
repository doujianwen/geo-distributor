"""OpenGeo 真实采集导出 → PlatformObservation 映射层。

将真实测量导出（Bing AI Performance / Google Search Console）转换为统一的
PlatformObservation，保证 Canonical Core 不被 OpenGeo / Bing / GSC 的私有
schema 污染（ADR-007 Evidence First + Sprint 4 §11）。

设计约束：
- 本文件只做「外部导出 → PlatformObservation」的映射，不引入业务判断
- 所有计算透明、可追溯（原始值保留在 raw_metadata）
- 代理信号（如 recommendation_level）必须显式标注来源，禁止伪装成真实 LLM 判定
"""

from typing import Any, Dict, List

from ..compatibility.base import PlatformObservation


def _safe_float(value: Any, default: float = 0.0) -> float:
    """将 '12.5%' / '12.5' / '' 等安全转为 float。"""
    if value is None:
        return default
    s = str(value).replace("%", "").replace(",", "").strip()
    if not s:
        return default
    try:
        return float(s)
    except ValueError:
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(_safe_float(value, default))
    except (ValueError, TypeError):
        return default


# ------------------------------------------------------------------
# Bing AI Performance → PlatformObservation
# ------------------------------------------------------------------

def map_bing_ai_performance_row(
    row: Dict[str, Any],
    brand: str = "BookConv",
    domain: str = "bookconv.com",
    snapshot_date: str = "",
) -> PlatformObservation:
    """将 Bing AI Performance 的单个 query 行映射为 PlatformObservation。

    Bing AI Performance 为每个 query 提供：
    - cites: 该 query 下品牌被 AI 引用的次数
    - share: 该 query 下品牌被引用的占比（citation share %）

    映射语义（透明声明）：
    - brand_mentioned: cites > 0 且 share > 0 → 该 query 下品牌被 AI 引用
    - recommendation_level: 由 citation share 推导的**代理信号**，非真实 LLM 推荐判定
        share >= 40% → 3（被重点引用，considered/recommended 代理）
        share >= 10% → 2
        share > 0   → 1
        否则        → 0
    """
    query = row.get("query", "") or ""
    cites = _safe_int(row.get("cites", 0))
    share = _safe_float(row.get("share", 0))
    mentioned = cites > 0 and share > 0

    if not mentioned:
        rec_level = 0
    elif share >= 40.0:
        rec_level = 3
    elif share >= 10.0:
        rec_level = 2
    else:
        rec_level = 1

    return PlatformObservation(
        observation_id=f"obs_bing_{abs(hash(query)) % 10**8:08d}",
        prompt_id=abs(hash(query)) % 10**8,
        engine="bing_ai",
        timestamp=snapshot_date or row.get("snapshot_date", ""),
        prompt_text=query,
        answer_raw="",
        answer_clean="",
        answer_char_count=0,
        extraction_method="bing_ai_performance_export",
        validation_status="PASS",
        brand=brand,
        brand_mentioned=mentioned,
        brand_status="MENTIONED" if mentioned else "NOT_MENTIONED",
        first_mention_position=None,
        recommendation_level=rec_level,
        recommendation_rank=None,
        recommendation_evidence=(
            f"Bing AI cited {brand} {cites} times ({share:.2f}% share)" if mentioned
            else ""
        ),
        competitors=[],
        citations=(
            [{"text": f"{brand} cited ({share:.2f}%)", "url": "", "type": "brand"}]
            if mentioned else []
        ),
        citations_status="extracted" if mentioned else "none",
        status="success",
        raw_metadata={
            "source": "bing_ai_performance",
            "cites": cites,
            "share_pct": share,
            "brand": brand,
            "domain": domain,
            "note": "recommendation_level is a citation-share proxy, not a real LLM judgment",
        },
    )


# ------------------------------------------------------------------
# Google Search Console → PlatformObservation（传统搜索可见性代理）
# ------------------------------------------------------------------

def map_gsc_row(
    row: Dict[str, Any],
    brand: str = "OSTRICH Ink",
    domain: str = "tjostrichink.com",
) -> PlatformObservation:
    """将 GSC 的单个 query 行映射为 PlatformObservation。

    GSC 提供传统搜索可见性（clicks / impressions / ctr / position），
    **不直接提供 AI 引用**。此处作为「传统搜索可见性代理」用于基线对照。

    映射语义（透明声明）：
    - brand_mentioned: impressions > 0 → 该 query 下官网有曝光（传统搜索）
    - recommendation_level: 由平均排名推导的代理信号（排名越靠前代理推荐越强）
    """
    query = row.get("query", "") or row.get("Top queries", "") or ""
    clicks = _safe_int(row.get("clicks", 0))
    impressions = _safe_int(row.get("impressions", 0))
    ctr = _safe_float(row.get("ctr", 0))
    position = _safe_float(row.get("position", row.get("avg_position", 0)) or 0)
    mentioned = impressions > 0

    if not mentioned:
        rec_level = 0
    elif position > 0 and position <= 3:
        rec_level = 3
    elif position > 0 and position <= 10:
        rec_level = 2
    else:
        rec_level = 1

    return PlatformObservation(
        observation_id=f"obs_gsc_{abs(hash(query)) % 10**8:08d}",
        prompt_id=abs(hash(query)) % 10**8,
        engine="google_search",
        timestamp=row.get("date", ""),
        prompt_text=query,
        answer_raw="",
        answer_clean="",
        answer_char_count=0,
        extraction_method="gsc_export",
        validation_status="PASS",
        brand=brand,
        brand_mentioned=mentioned,
        brand_status="MENTIONED" if mentioned else "NOT_MENTIONED",
        first_mention_position=int(position) if position > 0 else None,
        recommendation_level=rec_level,
        recommendation_rank=None,
        recommendation_evidence=(
            f"GSC: {impressions} impressions, {clicks} clicks, pos {position:.1f}"
            if mentioned else ""
        ),
        competitors=[],
        citations=[],
        citations_status="unavailable",
        status="success",
        raw_metadata={
            "source": "gsc",
            "clicks": clicks,
            "impressions": impressions,
            "ctr_pct": ctr,
            "avg_position": position,
            "brand": brand,
            "domain": domain,
            "note": "traditional-search visibility proxy; AI citation not measured by GSC",
        },
    )
