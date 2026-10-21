"""Read-only business projection. Never replaces frozen measurement calculations."""
from collections import Counter
from datetime import datetime
import math
from urllib.parse import urlsplit

from fastapi import HTTPException
from . import state


def safe_url(value):
    try:
        p = urlsplit(str(value or ""))
        if p.scheme in ("http", "https") and p.hostname and not p.username and not p.password:
            return p.geturl()[:2000]
    except ValueError:
        pass
    return ""


def safe_observation(o):
    """Do not serialize raw answers, metadata, internal ids or arbitrary nested dicts."""
    good = o.get("status") == "success" and o.get("validation_status") == "PASS"
    known = good and o.get("brand_status") in ("MENTIONED", "NOT_MENTIONED")
    rec = o.get("recommendation_level")
    return {
        "observation_id": str(o.get("observation_id", ""))[:100],
        "prompt_text": str(o.get("prompt_text", ""))[:2000],
        "engine": str(o.get("engine", ""))[:80],
        "timestamp": str(o.get("timestamp", ""))[:80],
        "status": "success" if good else "unavailable",
        "reason": "" if good else "采集未成功或质量验证未通过，不能作为效果结论",
        "brand_status": o.get("brand_status") if known else "UNKNOWN",
        "brand_mentioned": o.get("brand_mentioned") if known else None,
        "recommendation_level": rec if good and type(rec) is int and 0 <= rec <= 4 else None,
        "citations_status": o.get("citations_status") if good else "unavailable",
        "competitors": [{"name": str(c.get("name", ""))[:160]}
                        for c in (o.get("competitors") or [])[:20] if good and isinstance(c, dict) and c.get("name")],
        "citations": [{"url": safe_url(c.get("url")), "title": str(c.get("title", ""))[:200]}
                      for c in (o.get("citations") or [])[:20]
                      if good and isinstance(c, dict) and safe_url(c.get("url"))],
        # No implicit publication of answer_clean/recommendation_evidence.
        "excerpt": str(o.get("client_safe_excerpt", ""))[:600] if good and o.get("is_client_safe") is True else "",
        "category": str(o.get("client_safe_category", ""))[:100] if o.get("is_client_safe") is True else "",
    }


async def load_measurements(project_id, tenant_id):
    if state.measurement_repo is not None:
        records = await state.measurement_repo.list_by_project(project_id, tenant_id)
    else:
        records = state._measurement_results.get(project_id, [])
    return [r for r in records if r.get("tenant_id") == tenant_id and r.get("project_id") == project_id]


def _time(value):
    try:
        result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return result if result.tzinfo else None
    except (ValueError, TypeError):
        return None


def project_batch(r):
    obs = r.get("observations") or []
    m = r.get("metrics") or {}
    ids = [o.get("observation_id") for o in obs]
    times = [_time(o.get("timestamp")) for o in obs]
    valid = [o for o in obs if o.get("status") == "success" and o.get("validation_status") == "PASS"]
    context = r.get("comparison_context")
    context = context if isinstance(context, dict) else {}
    full_context = {k: context[k].strip() if isinstance(context.get(k), str) else ""
                    for k in ("brand", "market", "language", "method_version")}
    brands = {o.get("brand") for o in obs if isinstance(o.get("brand"), str) and o["brand"].strip()}
    observed_brand = next(iter(brands)) if len(brands) == 1 else ""
    brand_confirmed = bool(observed_brand) and all(o.get("brand") == observed_brand for o in obs)
    if "brand" in context:
        brand_confirmed = brand_confirmed and bool(full_context["brand"]) and full_context["brand"] == observed_brand
    complete = (bool(obs) and len(ids) == len(set(ids)) and all(ids)
                and len(obs) == r.get("observation_count") == m.get("query_count")
                and len(valid) == len(obs) and all(times) and _time(r.get("collected_at")) is not None
                and brand_confirmed)
    values = {}
    reasons = {}
    rules = {
        "mention_rate": (all(o.get("brand_status") in ("MENTIONED", "NOT_MENTIONED")
                             and type(o.get("brand_mentioned")) is bool
                             and o["brand_mentioned"] == (o["brand_status"] == "MENTIONED") for o in obs),
                         sum(o.get("brand_mentioned") is True for o in obs)),
        "recommendation_rate": (all(type(o.get("recommendation_level")) is int and 0 <= o["recommendation_level"] <= 4 for o in obs),
                                sum(type(o.get("recommendation_level")) is int and o["recommendation_level"] >= 2 for o in obs)),
        # Existing core means extracted citations, not brand-owned citations.
        "citation_rate": (all(o.get("citations_status") == "extracted" for o in obs), len(obs)),
    }
    for key, (known, numerator) in rules.items():
        value = m.get(key)
        # This is a consistency check of the existing stored metric, never a new result.
        matches = (type(value) in (int, float) and math.isfinite(value) and 0 <= value <= 100
                   and obs and abs(value - round(numerator / len(obs) * 100, 2)) <= .011)
        okay = complete and known and matches
        values[key] = value if okay else None
        reasons[key] = "已核对本批全部样本与既有汇总" if okay else "缺少完整有效样本、明确状态或一致的汇总口径，暂不展示数值"
    period = f"{min(times).isoformat()} — {max(times).isoformat()}" if times and all(times) else None
    safe_context = {k: v[:160] for k,v in full_context.items()}
    safe_context["brand"] = (full_context["brand"] or observed_brand)[:160]
    signature = None
    if complete and all(full_context.values()) and all(o.get("prompt_text") and o.get("engine") for o in obs):
        signature = (tuple(sorted(full_context.items())), tuple(sorted(Counter((o["prompt_text"], o["engine"]) for o in obs).items())))
    return {
        "measurement_id": str(r.get("measurement_id", "")), "collected_at": r.get("collected_at"),
        "source": str(r.get("adapter", "未记录"))[:80], "period": period,
        "total_samples": len(obs), "valid_samples": len(valid), "unavailable_samples": len(obs) - len(valid),
        "metrics": values, "metric_notes": reasons,
        "quality": "verified" if all(v is not None for v in values.values()) else "partial",
        "context": safe_context, "observations": [safe_observation(o) for o in obs],
        "is_demo": r.get("tenant_id") == "DEMO-GEO", "_signature": signature,
    }


async def geo_view(project_id, tenant_id, allowed_measurement_ids=None, source_records=None):
    if state.project_repo is None:
        raise HTTPException(503, "服务暂不可用")
    from geo_distributor.repositories.base import PermissionError as RepoPermissionError
    try:
        p = await state.project_repo.find_by_id(project_id, tenant_id=tenant_id)
    except RepoPermissionError:
        p = None
    if not p:
        raise HTTPException(404, "项目不存在或无访问权限")
    records = source_records if source_records is not None else await load_measurements(project_id, tenant_id)
    if allowed_measurement_ids is not None:
        records = [r for r in records if r.get("measurement_id") in allowed_measurement_ids]
    batches = [project_batch(r) for r in records]
    batches.sort(key=lambda b: (_time(b["collected_at"]).timestamp() if _time(b["collected_at"]) else float("-inf"), b["measurement_id"]))
    for i, batch in enumerate(batches):
        previous = batches[i - 1] if i else None
        comparable = (previous is not None and batch["_signature"] is not None
                      and batch["_signature"] == previous["_signature"]
                      and _time(batch["collected_at"]) > _time(previous["collected_at"]))
        batch["comparison"] = {
            "previous_id": previous["measurement_id"] if previous else None,
            "comparable": bool(comparable),
            "note": "与上批同范围比较；变化不证明因果" if comparable else "无同口径前批或范围信息不足，不能判断增长",
            "delta_pp": {k: round(v - previous["metrics"][k], 2) if comparable and v is not None and previous["metrics"][k] is not None else None
                         for k, v in batch["metrics"].items()},
        }
    for batch in batches:
        batch.pop("_signature", None)
    return {"project_id": project_id, "client_id": p.client_id, "is_demo": tenant_id == "DEMO-GEO", "batches": batches,
            "limitations": ["仅为已保存批次，不表示覆盖完整问题库。", "回答引用可用率不等于品牌被引用率。", "无已发布的SEO、行动归因或商业转化数据；阶段状态见项目。"]}


async def report_projection(r, source_measurement=None):
    from .routers.reports import report_to_out
    out = report_to_out(r)
    out = {k: out[k] for k in ("report_id", "project_id", "tenant_id", "title", "version", "visibility_score", "visibility_summary", "key_findings", "limitations", "next_steps", "created_at", "data_quality")}
    out["visibility_summary"] = {k: v for k, v in out["visibility_summary"].items()
                                 if k in ("total_queries", "brand_mentioned", "brand_recommended", "mention_rate", "recommendation_rate")}
    out["key_findings"] = [{k: f[k] for k in ("finding_id", "category", "severity", "statement", "recommendation") if k in f}
                           for f in out["key_findings"] if isinstance(f, dict)]
    mid = r.get("measurement_id")
    records = [source_measurement] if source_measurement is not None else (await load_measurements(r["project_id"], r["tenant_id"]) if mid else [])
    record = next((x for x in records if x.get("measurement_id") == mid), None)
    if record:
        batch = project_batch(record)
        summary = out["visibility_summary"]
        metrics = batch["metrics"]
        n = batch["total_samples"]
        # Legacy report scores are separate formulas; verify their counts and score too.
        mention = metrics["mention_rate"]
        rec = metrics["recommendation_rate"]
        def rate_matches(key, expected):
            if key not in summary:
                return True
            value = summary[key]
            if type(value) is str and value.endswith("%"):
                try:
                    value = float(value[:-1])
                except ValueError:
                    return False
            return type(value) in (int, float) and math.isfinite(value) and expected is not None and abs(value - expected) <= .11
        valid = (mention is not None and rec is not None and isinstance(summary, dict)
                 and summary.get("total_queries") == n
                 and summary.get("brand_mentioned") == sum(o.get("brand_mentioned") is True for o in record["observations"])
                 and summary.get("brand_recommended") == sum(o.get("recommendation_level", -1) >= 2 for o in record["observations"])
                 and type(out["visibility_score"]) in (int, float)
                 and rate_matches("mention_rate", mention) and rate_matches("recommendation_rate", rec)
                 and abs(out["visibility_score"] - round((mention + rec) / 2, 1)) <= .11)
        if valid:
            batch.pop("_signature", None)
            out["data_quality"] = {"status": "verified", "valid_queries": n, "period": batch["period"],
                                   "source": batch["source"], "note": "报告与明确关联批次的样本、时间和汇总已核对；不代表因果验证。"}
            out["geo_snapshot"] = batch
    out["is_demo"] = r.get("tenant_id") == "DEMO-GEO"
    return out
