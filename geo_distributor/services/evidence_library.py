"""Sprint 4C — Evidence Library（规格 §10 / SPRINT-4-ROADMAP 4C）。

目标：建立可复用的 GEO 效果证据库。

战略价值（CEO 裁定）：GEO 分销真正值钱的资产不是代码，是可展示的效果证据。

数据结构（对齐 SPRINT-4-ROADMAP §4C）：
    {
      "case_id": "CASE-001",
      "distributor_id": "DST-001",
      "client_id": "CLI-001",
      "industry": "ebook_tools",
      "baseline_visibility_score": 23,
      "intervention": "content_optimization",
      "post_intervention_score": 45,
      "delta": 22,
      "time_to_result_days": 14,
      "evidence_refs": ["EVD-001", "EVD-002"],
      "created_at": "2026-09-14T00:00:00Z"
    }

约束：
- 不暴露 Internal Technical Data（Client-safe 投影）
- 可按 industry / distributor / time 查询
- 统计聚合（平均 Delta、中位数、分位数）
- 支持 JSON/CSV 导出（用于演示给客户）
- 支持从 sprint4-lab 真实案例数据加载
"""

import csv
import io
import json
import os
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional


@dataclass
class EvidenceRecord:
    """单条 GEO 效果证据：Observation → Intervention → Outcome。"""

    case_id: str
    distributor_id: str
    client_id: str
    industry: str
    baseline_visibility_score: float
    post_intervention_score: float
    intervention: str
    delta: float
    time_to_result_days: int = 0
    evidence_refs: List[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    @property
    def lift_pct(self) -> float:
        if self.baseline_visibility_score <= 0:
            return 0.0
        return round(
            (self.post_intervention_score - self.baseline_visibility_score)
            / self.baseline_visibility_score * 100, 2
        )

    @property
    def is_positive(self) -> bool:
        return self.delta > 0

    @property
    def status_label(self) -> str:
        if self.delta > 0:
            return "POSITIVE"
        elif self.delta < 0:
            return "NEGATIVE"
        return "NEUTRAL"

    def to_dict(self) -> dict:
        return {
            "case_id": self.case_id,
            "distributor_id": self.distributor_id,
            "client_id": self.client_id,
            "industry": self.industry,
            "baseline_visibility_score": self.baseline_visibility_score,
            "post_intervention_score": self.post_intervention_score,
            "intervention": self.intervention,
            "delta": self.delta,
            "lift_pct": self.lift_pct,
            "status": self.status_label,
            "time_to_result_days": self.time_to_result_days,
            "evidence_refs": self.evidence_refs,
            "created_at": self.created_at,
        }


class EvidenceLibraryService:
    """证据库服务：增删查 + 聚合统计 + 导出（Client-safe）。"""

    def __init__(self):
        self._records: List[EvidenceRecord] = []

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def add(self, record: EvidenceRecord) -> EvidenceRecord:
        self._records.append(record)
        return record

    def add_from_dict(self, data: dict) -> EvidenceRecord:
        rec = EvidenceRecord(**data)
        return self.add(rec)

    def remove(self, case_id: str) -> bool:
        """按 case_id 删除记录。返回是否成功。"""
        before = len(self._records)
        self._records = [r for r in self._records if r.case_id != case_id]
        return len(self._records) < before

    def get_by_case_id(self, case_id: str) -> Optional[EvidenceRecord]:
        for r in self._records:
            if r.case_id == case_id:
                return r
        return None

    def all(self) -> List[EvidenceRecord]:
        return list(self._records)

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def query(
        self,
        industry: Optional[str] = None,
        distributor_id: Optional[str] = None,
        client_id: Optional[str] = None,
        since: Optional[str] = None,
        min_delta: Optional[float] = None,
    ) -> List[EvidenceRecord]:
        result = self._records
        if industry:
            result = [r for r in result if r.industry == industry]
        if distributor_id:
            result = [r for r in result if r.distributor_id == distributor_id]
        if client_id:
            result = [r for r in result if r.client_id == client_id]
        if since:
            result = [r for r in result if r.created_at >= since]
        if min_delta is not None:
            result = [r for r in result if r.delta >= min_delta]
        return result

    # ------------------------------------------------------------------
    # Aggregate statistics
    # ------------------------------------------------------------------

    def aggregate(self) -> Dict[str, float]:
        """统计聚合：平均 Delta、中位数、分位数（Client-safe 摘要）。"""
        if not self._records:
            return {
                "count": 0,
                "avg_delta": 0.0,
                "median_delta": 0.0,
                "avg_lift_pct": 0.0,
                "p25_delta": 0.0,
                "p75_delta": 0.0,
                "positive_rate": 0.0,
            }
        deltas = sorted(r.delta for r in self._records)
        lifts = [r.lift_pct for r in self._records]
        n = len(deltas)
        positive = sum(1 for r in self._records if r.is_positive)

        def _median(xs):
            mid = n // 2
            return xs[mid] if n % 2 else (xs[mid - 1] + xs[mid]) / 2

        def _percentile(xs, p):
            if n == 1:
                return xs[0]
            k = (n - 1) * p
            f = int(k)
            c = min(f + 1, n - 1)
            return xs[f] + (xs[c] - xs[f]) * (k - f)

        return {
            "count": n,
            "avg_delta": round(sum(deltas) / n, 3),
            "median_delta": round(_median(deltas), 3),
            "avg_lift_pct": round(sum(lifts) / n, 2),
            "p25_delta": round(_percentile(deltas, 0.25), 3),
            "p75_delta": round(_percentile(deltas, 0.75), 3),
            "positive_rate": round(positive / n * 100, 2),
        }

    def aggregate_by_industry(self) -> Dict[str, Dict[str, float]]:
        """按行业聚合统计。"""
        by_industry: Dict[str, List[EvidenceRecord]] = {}
        for r in self._records:
            by_industry.setdefault(r.industry, []).append(r)

        result = {}
        for industry, records in by_industry.items():
            deltas = sorted(r.delta for r in records)
            lifts = [r.lift_pct for r in records]
            n = len(deltas)
            positive = sum(1 for r in records if r.is_positive)
            result[industry] = {
                "count": n,
                "avg_delta": round(sum(deltas) / n, 3),
                "avg_lift_pct": round(sum(lifts) / n, 2),
                "positive_rate": round(positive / n * 100, 2),
            }
        return result

    def to_dict(self) -> dict:
        return {
            "records": [r.to_dict() for r in self._records],
            "aggregate": self.aggregate(),
            "by_industry": self.aggregate_by_industry(),
        }

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------

    def export_json(self) -> str:
        """导出为 JSON 字符串（Client-safe）。"""
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)

    def export_csv(self) -> str:
        """导出为 CSV 字符串（Client-safe）。"""
        if not self._records:
            return ""
        fieldnames = [
            "case_id", "distributor_id", "client_id", "industry",
            "baseline_visibility_score", "post_intervention_score",
            "intervention", "delta", "lift_pct", "status",
            "time_to_result_days", "evidence_refs", "created_at",
        ]
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        for r in self._records:
            d = r.to_dict()
            d["evidence_refs"] = "; ".join(d["evidence_refs"])
            writer.writerow(d)
        return output.getvalue()

    # ------------------------------------------------------------------
    # Load from sprint4-lab real case data
    # ------------------------------------------------------------------

    @classmethod
    def load_from_lab_cases(cls, lab_root: Optional[str] = None) -> "EvidenceLibraryService":
        """从 sprint4-lab 真实案例数据加载 EvidenceRecord。

        每个案例目录格式：
            sprint4-lab/cases/<case_dir>/baseline/metrics.json
            sprint4-lab/cases/<case_dir>/timeline/timeline.json
        以及 optional delta + remeasurement 目录。
        """
        if lab_root is None:
            # Default: project root / sprint4-lab
            here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            lab_root = os.path.join(here, "sprint4-lab", "cases")

        svc = cls()

        if not os.path.isdir(lab_root):
            return svc

        for case_dir in os.listdir(lab_root):
            case_path = os.path.join(lab_root, case_dir)
            if not os.path.isdir(case_path):
                continue

            baseline_metrics_path = os.path.join(case_path, "baseline", "metrics.json")
            if not os.path.isfile(baseline_metrics_path):
                continue

            try:
                with open(baseline_metrics_path, "r", encoding="utf-8") as f:
                    baseline = json.load(f)
            except (json.JSONDecodeError, IOError):
                continue

            case_id = baseline.get("case_id", case_dir.upper())

            # 尝试读取时间线，找干预和执行信息
            timeline_path = os.path.join(case_path, "timeline", "timeline.json")
            timeline_data = {}
            if os.path.isfile(timeline_path):
                try:
                    with open(timeline_path, "r", encoding="utf-8") as f:
                        timeline_data = json.load(f)
                except (json.JSONDecodeError, IOError):
                    pass

            # 尝试读取 re-measurement（delta 计算）
            delta_value = 0.0
            time_to_result = 0
            intervention_type = "content_optimization"
            remeas_path = os.path.join(case_path, "remeasurement", "metrics.json")
            if os.path.isfile(remeas_path):
                try:
                    with open(remeas_path, "r", encoding="utf-8") as f:
                        remeas = json.load(f)
                    # Delta = remeasurement avg_recommendation_level - baseline avg_recommendation_level
                    baseline_avg = baseline.get("avg_recommendation_level", 0)
                    remeas_avg = remeas.get("avg_recommendation_level", 0)
                    delta_value = round(remeas_avg - baseline_avg, 3)
                    # Get time span from timeline
                    events = timeline_data.get("events", [])
                    if events:
                        dates = [e.get("date", "") for e in events if e.get("date")]
                        if len(dates) >= 2:
                            try:
                                d0 = datetime.fromisoformat(dates[0])
                                d1 = datetime.fromisoformat(dates[-1])
                                time_to_result = (d1 - d0).days
                            except ValueError:
                                pass
                    # Get intervention type from timeline
                    for ev in events:
                        if ev.get("type") in ("intervention", "execution"):
                            intervention_type = ev.get("label", "content_optimization")
                            break
                except (json.JSONDecodeError, IOError):
                    pass

            # 构造 EvidenceRecord
            # 使用 avg_recommendation_level 作为 visibility score
            baseline_score = baseline.get("avg_recommendation_level", 0)
            post_score = baseline_score + delta_value

            rec = EvidenceRecord(
                case_id=case_id,
                distributor_id=f"DST-{case_id[-3:]}",
                client_id=f"CLI-{case_id[-3:]}",
                industry=case_dir.replace("-", "_"),
                baseline_visibility_score=round(baseline_score, 3),
                post_intervention_score=round(post_score, 3),
                intervention=intervention_type,
                delta=round(delta_value, 3),
                time_to_result_days=time_to_result,
                evidence_refs=[],
            )
            svc.add(rec)

        return svc


class EvidenceDashboard:
    """内部 HQ 使用的证据库仪表盘（纯数据视图，无 UI 依赖）。"""

    def __init__(self, service: EvidenceLibraryService):
        self._svc = service

    def summary(self) -> dict:
        """仪表盘摘要视图。"""
        agg = self._svc.aggregate()
        by_industry = self._svc.aggregate_by_industry()

        return {
            "total_cases": agg["count"],
            "avg_delta": agg["avg_delta"],
            "median_delta": agg["median_delta"],
            "avg_lift_pct": agg["avg_lift_pct"],
            "positive_rate_pct": agg["positive_rate"],
            "by_industry": by_industry,
            "top_3_deltas": self._top_n_by_delta(3),
        }

    def _top_n_by_delta(self, n: int) -> List[dict]:
        records = sorted(self._svc.all(), key=lambda r: r.delta, reverse=True)[:n]
        return [r.to_dict() for r in records]

    def industry_report(self, industry: str) -> Optional[dict]:
        """单个行业的详细报告。"""
        records = self._svc.query(industry=industry)
        if not records:
            return None

        deltas = sorted(r.delta for r in records)
        lifts = [r.lift_pct for r in records]
        n = len(deltas)
        positive = sum(1 for r in records if r.is_positive)

        return {
            "industry": industry,
            "case_count": n,
            "avg_delta": round(sum(deltas) / n, 3),
            "avg_lift_pct": round(sum(lifts) / n, 2),
            "positive_rate_pct": round(positive / n * 100, 2),
            "best_case": max(records, key=lambda r: r.delta).case_id if records else None,
            "worst_case": min(records, key=lambda r: r.delta).case_id if records else None,
            "records": [r.to_dict() for r in records],
        }
