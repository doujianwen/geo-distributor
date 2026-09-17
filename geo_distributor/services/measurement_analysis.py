"""Measurement 聚合分析 — 将 PlatformObservation 列表转为基线/重测指标。

被 Sprint 4 Lab 管线与 ReMeasurementService 共用。纯函数，平台无关。
"""

from typing import List, Optional

from ..compatibility.base import PlatformObservation
from ..services.intervention_loop import BaselineMetrics


def _obs_list(observations) -> List[PlatformObservation]:
    result = []
    for o in observations:
        if isinstance(o, PlatformObservation):
            result.append(o)
        elif isinstance(o, dict):
            result.append(PlatformObservation(**o))
        else:
            # 尝试 to_dict 后再构造
            result.append(PlatformObservation(**o.to_dict()))
    return result


def aggregate_metrics(
    observations,
    case_id: str,
    version: str = "baseline",
    total_queries: Optional[int] = None,
) -> BaselineMetrics:
    """聚合观测为 BaselineMetrics。

    Args:
        observations: PlatformObservation 列表（或 dict / 可 to_dict 对象）
        case_id: 案例 ID
        version: "baseline" / "remeasurement"
        total_queries: Query Set 总数（用于计算 query_coverage）；
                      缺省时以观测数代替（coverage=100%）
    """
    obs = _obs_list(observations)
    n = len(obs)
    if n == 0:
        return BaselineMetrics(case_id=case_id, version=version, query_count=0)

    mentioned = [o for o in obs if o.brand_mentioned]
    cited = [o for o in obs if o.raw_metadata.get("cites", 0) or o.citations_status == "extracted"]
    recommended = [o for o in obs if (o.recommendation_level or 0) >= 2]
    competitors = set()
    for o in obs:
        for c in o.competitors:
            name = c.get("name") if isinstance(c, dict) else str(c)
            if name:
                competitors.add(name)

    valid = n  # 有效观测（status != failed / not_collected）
    mention_rate = round(len(mentioned) / valid * 100, 2) if valid else 0.0
    citation_rate = round(len(cited) / valid * 100, 2) if valid else 0.0
    recommendation_rate = round(len(recommended) / valid * 100, 2) if valid else 0.0
    avg_rec = round(sum(o.recommendation_level or 0 for o in obs) / n, 3)

    q_total = total_queries if total_queries else n
    query_coverage = round(n / q_total * 100, 2) if q_total else 100.0

    return BaselineMetrics(
        case_id=case_id,
        version=version,
        query_count=n,
        mention_rate=mention_rate,
        citation_rate=citation_rate,
        recommendation_rate=recommendation_rate,
        query_coverage=query_coverage,
        avg_recommendation_level=avg_rec,
        competitor_count=len(competitors),
    )
