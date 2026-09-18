"""竞品分析服务（P1 — 让阶段 2「竞品分析」真正产出数据）。

数据来源纪律（重要）：
    竞品名单 **只能来自观测数据里的 competitors 字段**（采集时抽取所得）。
    本模块 **不做任何品牌名猜测、不做行业常识补全、不从回答文本里"推断"竞品**。

    当观测数据无 competitors 字段时（如 sprint4 历史快照），
    结果是 `has_data=False` 并给出明确原因，**绝不返回编造的竞品名单**。
    —— 给出"无数据"比给出"看起来像真的竞品名单"更有价值，后者会误导客户决策。

竞品字段格式（采集侧约定）：
    [{"brand": "brita", "position": 2}, {"brand": "ispring", "position": 7}]

    既有 list[dict]（含 brand/position），也兼容纯字符串列表 ["brita", "ispring"]。
"""

from dataclasses import dataclass, field
from datetime import datetime
from types import SimpleNamespace
from typing import List, Dict, Optional, Any

from ..compatibility.base import PlatformObservation
from ..models.finding import Finding, FindingCategory, FindingSeverity


# ------------------------------------------------------------------
# 结果模型
# ------------------------------------------------------------------


@dataclass
class CompetitorStat:
    """单个竞品的统计。"""

    brand: str
    mention_count: int = 0          # 提及该竞品的观测条数
    mention_rate: float = 0.0       # mention_count / 总观测数
    avg_position: Optional[float] = None   # 平均出现位次（越小越靠前）
    best_position: Optional[int] = None
    share_of_voice: float = 0.0     # 该竞品提及数 / 全部竞品提及总数
    engines: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "brand": self.brand,
            "mention_count": self.mention_count,
            "mention_rate": round(self.mention_rate, 2),
            "avg_position": round(self.avg_position, 2) if self.avg_position is not None else None,
            "best_position": self.best_position,
            "share_of_voice": round(self.share_of_voice, 2),
            "engines": self.engines,
        }


@dataclass
class CompetitiveAnalysisResult:
    """竞品分析结果。

    `has_data=False` 时，`competitors` 必为空列表且 `data_note` 说明原因。
    调用方（阶段 2）据此标注 COMPLETED_NO_DATA，而非当作"分析完成"。
    """

    brand: str
    total_observations: int = 0
    observations_with_competitors: int = 0
    brand_mention_rate: float = 0.0
    brand_recommendation_rate: float = 0.0
    competitors: List[CompetitorStat] = field(default_factory=list)
    has_data: bool = False
    data_note: str = ""
    findings: List[Finding] = field(default_factory=list)
    analyzed_at: str = field(default_factory=lambda: datetime.now().isoformat())

    @property
    def top_competitor(self) -> Optional[CompetitorStat]:
        return self.competitors[0] if self.competitors else None

    @property
    def total_competitor_mentions(self) -> int:
        return sum(c.mention_count for c in self.competitors)

    def to_dict(self) -> dict:
        return {
            "brand": self.brand,
            "total_observations": self.total_observations,
            "observations_with_competitors": self.observations_with_competitors,
            "brand_mention_rate": round(self.brand_mention_rate, 2),
            "brand_recommendation_rate": round(self.brand_recommendation_rate, 2),
            "has_data": self.has_data,
            "data_note": self.data_note,
            "total_competitor_mentions": self.total_competitor_mentions,
            "top_competitor": self.top_competitor.to_dict() if self.top_competitor else None,
            "competitors": [c.to_dict() for c in self.competitors],
            "finding_count": len(self.findings),
            "analyzed_at": self.analyzed_at,
        }


# ------------------------------------------------------------------
# 解析辅助
# ------------------------------------------------------------------


def _normalize_competitors(raw: Any) -> List[Dict[str, Any]]:
    """把 competitors 字段规范成 [{"brand": str, "position": int|None}]。

    兼容三种形态：
      1. [{"brand": "brita", "position": 2}]
      2. ["brita", "ispring"]                       （纯名称，无位次）
      3. 'brita'                                     （单个字符串，视为列表）
    无法识别的形态返回 []，不猜测。
    """
    out: List[Dict[str, Any]] = []

    if raw is None:
        return out

    # JSON 字符串先反序列化
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return out
        if text.startswith("["):
            import json
            try:
                raw = json.loads(text)
            except (ValueError, TypeError):
                return out
        else:
            raw = [text]

    if not isinstance(raw, list):
        return out

    for item in raw:
        if isinstance(item, dict):
            name = item.get("brand") or item.get("name") or item.get("competitor")
            if not name or not isinstance(name, str):
                continue
            pos = item.get("position") or item.get("rank")
            try:
                pos = int(pos) if pos is not None else None
            except (TypeError, ValueError):
                pos = None
            out.append({"brand": name.strip(), "position": pos})
        elif isinstance(item, str) and item.strip():
            out.append({"brand": item.strip(), "position": None})

    return out


def _brand_key(brand: str) -> str:
    """品牌名归一：小写 + 去空白。用于判定"本品牌"与"竞品"是否同一实体。"""
    return (brand or "").strip().lower()


def _as_observation(obj: Any) -> Any:
    """把 dict 观测转成可 getattr 的对象，使本服务同时支持两种输入。

    API 返回的观测是 dict（来自 PlatformObservation.to_dict()），
    而采集侧返回的是 PlatformObservation 实例。统一成对象后用 getattr 访问，
    避免两套代码路径。
    """
    if isinstance(obj, dict):
        return SimpleNamespace(**obj)
    return obj


# ------------------------------------------------------------------
# 主分析入口
# ------------------------------------------------------------------


def analyze_competitors(
    observations: List[PlatformObservation],
    brand: str,
    project_id: str = "",
    case_id: str = "",
) -> CompetitiveAnalysisResult:
    """从观测数据聚合竞品格局。

    Args:
        observations: 采集所得观测（需含 competitors 字段）
        brand: 本品牌名
        project_id / case_id: 用于 Finding 归属

    Returns:
        CompetitiveAnalysisResult。无竞品数据时 has_data=False。
    """
    # 归一化：同时接受 PlatformObservation 实例与 dict
    observations = [_as_observation(o) for o in observations]

    result = CompetitiveAnalysisResult(brand=brand, total_observations=len(observations))

    if not observations:
        result.data_note = "无观测数据，无法进行竞品分析。"
        return result

    # --- 本品牌基线 ---
    mentioned = sum(1 for o in observations if getattr(o, "brand_mentioned", False))
    recommended = sum(
        1 for o in observations
        if (getattr(o, "recommendation_level", 0) or 0) >= 2
    )
    result.brand_mention_rate = round(mentioned / len(observations) * 100, 2)
    result.brand_recommendation_rate = round(recommended / len(observations) * 100, 2)

    # --- 聚合竞品 ---
    own_key = _brand_key(brand)
    stat_map: Dict[str, Dict[str, Any]] = {}
    obs_with_comp = 0
    total_mentions = 0

    for obs in observations:
        raw = getattr(obs, "competitors", None)
        comps = _normalize_competitors(raw)
        if not comps:
            continue

        obs_with_comp += 1
        engine = getattr(obs, "engine", "") or ""
        seen_in_this_obs = set()

        for c in comps:
            key = _brand_key(c["brand"])
            if not key or key == own_key:
                continue  # 跳过空名与本品牌自身（竞品不含自己）

            if key in seen_in_this_obs:
                continue  # 同一条观测内同一竞品只计一次
            seen_in_this_obs.add(key)

            s = stat_map.setdefault(
                key,
                {"brand": c["brand"], "count": 0, "positions": [], "engines": set()},
            )
            s["count"] += 1
            total_mentions += 1
            if c["position"] is not None:
                s["positions"].append(c["position"])
            if engine:
                s["engines"].add(engine)

    result.observations_with_competitors = obs_with_comp

    # --- 无数据判定 ---
    if not stat_map:
        if obs_with_comp == 0:
            result.data_note = (
                f"观测数据中未包含竞品字段（{len(observations)} 条观测均无 competitors）。"
                "该数据集采集时未开启竞品抽取，需重新采集才能进行竞品分析。"
            )
        else:
            result.data_note = (
                f"{obs_with_comp} 条观测含竞品字段，但解析后无有效竞品条目"
                "（可能全部为本品牌自身或字段格式不兼容）。"
            )
        result.has_data = False
        return result

    # --- 计算份额与排序 ---
    competitors: List[CompetitorStat] = []
    for key, s in stat_map.items():
        positions = s["positions"]
        competitors.append(
            CompetitorStat(
                brand=s["brand"],
                mention_count=s["count"],
                mention_rate=round(s["count"] / len(observations) * 100, 2),
                avg_position=(sum(positions) / len(positions)) if positions else None,
                best_position=min(positions) if positions else None,
                share_of_voice=round(s["count"] / total_mentions * 100, 2) if total_mentions else 0.0,
                engines=sorted(s["engines"]),
            )
        )

    # 排序：提及数降序 → 平均位次升序（更靠前者优先）
    competitors.sort(
        key=lambda c: (-c.mention_count, c.avg_position if c.avg_position is not None else 999)
    )
    result.competitors = competitors
    result.has_data = True
    result.data_note = (
        f"基于 {obs_with_comp}/{len(observations)} 条含竞品字段的观测，"
        f"识别到 {len(competitors)} 个竞品、共 {total_mentions} 次提及。"
    )

    result.findings = _generate_competitive_findings(result, project_id=project_id, case_id=case_id)
    return result


# ------------------------------------------------------------------
# Finding 生成
# ------------------------------------------------------------------


def _generate_competitive_findings(
    result: CompetitiveAnalysisResult,
    project_id: str = "",
    case_id: str = "",
) -> List[Finding]:
    """依据竞品格局生成 Finding。

    纪律：只陈述数据支持的对比结论，不推断"为什么"，不给未验证的改进承诺。
    """
    findings: List[Finding] = []
    if not result.has_data or not result.competitors:
        return findings

    top = result.top_competitor
    if top is None:
        return findings

    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    seq = 0

    def _mk(severity: FindingSeverity, statement: str, recommendation: str) -> Finding:
        nonlocal seq
        seq += 1
        return Finding(
            finding_id=f"FND-{ts}-CA{seq:03d}",
            observation_ids=[],
            category=FindingCategory.COMPETITIVE_DISADVANTAGE,
            severity=severity,
            statement=statement,
            recommendation=recommendation,
            evidence_refs=[],
            confidence=0.6,      # 竞品对比基于单次快照，置信度中等
            priority_score=0.0,
            project_id=project_id,
            case_id=case_id,
        )

    # 1) 头部竞品提及率显著高于本品牌
    if top.mention_rate > result.brand_mention_rate:
        gap = round(top.mention_rate - result.brand_mention_rate, 2)
        sev = FindingSeverity.HIGH if gap >= 20 else FindingSeverity.MEDIUM
        findings.append(
            _mk(
                sev,
                f"竞品「{top.brand}」在 {top.mention_count} 条查询中被 AI 提及"
                f"（提及率 {top.mention_rate}%），高于本品牌「{result.brand}」的"
                f"{result.brand_mention_rate}%，差距 {gap} 个百分点。",
                f"优先分析「{top.brand}」在哪些查询场景被提及，"
                "对照其内容与信源布局，识别本品牌缺失的场景覆盖。",
            )
        )

    # 2) 竞品整体占位压力（SOV 集中度高）
    if len(result.competitors) >= 2:
        total_sov = sum(c.share_of_voice for c in result.competitors[:3])
        if total_sov >= 60:
            top3 = "、".join(c.brand for c in result.competitors[:3])
            findings.append(
                _mk(
                    FindingSeverity.MEDIUM,
                    f"竞品声量高度集中：{top3} 合计占据 {round(total_sov, 2)}% 的竞品提及份额，"
                    "说明该场景已被少数品牌主导。",
                    "进入该场景需先明确差异化定位，"
                    "避免在头部品牌已占位的通用查询上正面竞争。",
                )
            )

    # 3) 本品牌零提及但竞品有提及（最严重：完全缺席）
    if result.brand_mention_rate == 0 and top.mention_count > 0:
        findings.append(
            _mk(
                FindingSeverity.CRITICAL,
                f"本品牌「{result.brand}」在 {result.total_observations} 条查询中"
                f"零提及，而竞品「{top.brand}」被提及 {top.mention_count} 次"
                f"（{top.mention_rate}%）。",
                "该场景本品牌尚未进入 AI 答案的候选集合，"
                "需先补齐可被核验的基础事实页与第三方提及。",
            )
        )

    # 4) 本品牌有提及但推荐率明显低于头部竞品
    if result.brand_mention_rate > 0 and result.brand_recommendation_rate < result.brand_mention_rate * 0.5:
        findings.append(
            _mk(
                FindingSeverity.HIGH,
                f"本品牌「{result.brand}」提及率 {result.brand_mention_rate}%，"
                f"但推荐率仅 {result.brand_recommendation_rate}%"
                "—— 被提到但未被推荐。",
                "重点补齐支撑推荐的第三方信源（评测、认证、行业媒体），"
                "而非继续增加自述型内容。",
            )
        )

    return findings
