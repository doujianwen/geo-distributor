"""Measurements router — trigger data collection and return aggregated metrics."""

from __future__ import annotations
from typing import Annotated, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import BaseModel, Field

from .. import state
from ..deps import authenticate, require_write, require_hq
from geo_distributor.repositories.base import PermissionError as RepoPermissionError

router = APIRouter(prefix="/measurements", tags=["measurements"])


# ------------------------------------------------------------------
# Request / Response schemas
# ------------------------------------------------------------------

class MeasurementRequest(BaseModel):
    """发起一次采集任务。"""
    project_id: str
    case_id: Optional[str] = None  # Sprint4 case dir（如 bookconv/tjostrichink）
    adapter: str = "opengeo"  # opengeo / elmo / geo-collector / mock
    tenant_id: str = Field(..., description="用于隔离验证")
    observation_limit: int = Field(
        default=500,
        ge=1,
        le=5000,
        description=(
            "响应体返回的观测条数上限。分析类调用（如竞品分析）需要完整数据，"
            "故默认给足；仅需汇总时可设小。"
        ),
    )


class ObservationOut(BaseModel):
    """观测输出模型。

    ⚠️ `competitors` 与 `citations` 是下游分析（尤其中阶段 2 竞品分析）的
    必需字段。此前该模型只定义了 8 个标量字段，导致 API 响应里竞品数据被
    pydantic 静默丢弃——底层采集有竞品，上层却永远拿到空，阶段 2 恒为
    NO_DATA。现在补齐。
    """
    observation_id: str
    prompt_text: str
    engine: str
    brand_mentioned: bool
    brand_status: str
    recommendation_level: int
    citations_status: str
    timestamp: str
    competitors: List[dict] = []
    citations: List[dict] = []
    recommendation_rank: Optional[int] = None
    first_mention_position: Optional[int] = None


class MetricsOut(BaseModel):
    case_id: str
    version: str
    query_count: int
    mention_rate: float
    citation_rate: float
    recommendation_rate: float
    query_coverage: float
    avg_recommendation_level: float
    competitor_count: int
    captured_at: str


class FindingOut(BaseModel):
    finding_id: str
    category: str
    severity: str
    statement: str
    recommendation: str
    confidence: float
    status: str


class MeasurementOut(BaseModel):
    project_id: str
    tenant_id: str
    adapter: str
    case_id: Optional[str]
    collected_at: str
    observations: List[ObservationOut]
    metrics: MetricsOut
    findings: List[FindingOut]


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _get_project_repo() -> state.ProjectRepository:
    if state.project_repo is None:
        raise HTTPException(status_code=503, detail="API not initialized")
    return state.project_repo  # type: ignore


def _require_tenant_header(x_tenant_id: str | None) -> str:
    """B-1 修复：tenant context 缺失即 fail closed（原实现直接忽略该header）。"""
    # B-2：tenant 已由认证层（密钥绑定）确定，header 仅作可选声明。
    # 缺失时不报错 —— 使用认证上下文中的 tenant。
    # 声明与密钥冲突由 api.auth.resolve_tenant 拦截（403）。
    return x_tenant_id or""


async def _verify_tenant(project_id: str, tenant_id: str | None) -> None:
    """按 (project_id, tenant_id) 校验项目归属，租户不符视为不可见。"""
    # B-2：tenant_id 由认证层校验后传入，不再要求 header 存在
    repo = _get_project_repo()
    try:
        p = await repo.find_by_id(project_id, tenant_id=tenant_id)
    except RepoPermissionError:
        p = None
    if not p:
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found or tenant mismatch")


# ------------------------------------------------------------------
# Endpoints
# ------------------------------------------------------------------

@router.post("", response_model=MeasurementOut, status_code=201)
async def run_measurement(body: MeasurementRequest, auth=Depends(require_hq)):
    """触发一次采集并返回聚合结果。"""
    await _verify_tenant(body.project_id, body.tenant_id)

    from geo_distributor.adapters.opengeo import OpenGeoAdapter
    from geo_distributor.compatibility.base import PlatformObservation
    from geo_distributor.services.measurement_analysis import aggregate_metrics
    from geo_distributor.models.finding import Finding, FindingSeverity, FindingCategory
    from datetime import datetime, timezone
    import os
    from geo_distributor.config import get_project_root
    import json

    observations: list[PlatformObservation] = []
    case_id = body.case_id or body.project_id
    adapter_name = body.adapter

    if adapter_name == "opengeo" and body.case_id:
        cases_dir = os.path.join(get_project_root(), "sprint4-lab", "cases", body.case_id, "baseline")
        obs_path = os.path.join(cases_dir, "observations.json")
        if os.path.exists(obs_path):
            with open(obs_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            observations = [PlatformObservation(**o) for o in data] if isinstance(data, list) else []
        else:
            raise HTTPException(status_code=404, detail=f"Case data not found: {obs_path}")
    elif adapter_name == "geo-collector-db":
        # 直接从 geo-collector SQLite 数据库读取，零依赖
        from geo_distributor.config import get_geo_collector_root
        from geo_distributor.adapters.geo_collector_db import GeoCollectorDBAdapter
        import sqlite3
        from geo_distributor.models import Prompt

        db_path = os.path.join(get_geo_collector_root(), "geo_collector.db")
        if not os.path.exists(db_path):
            raise HTTPException(status_code=404, detail=f"geo_collector.db not found at {db_path}")

        # 加载品牌配置
        from geo_distributor.config import load_settings
        settings = load_settings()
        brand = settings.get("brand", "Hydroviv")

        # 从 DB 加载 prompts
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute("SELECT prompt_id, prompt_text, category, intent, location FROM prompts ORDER BY prompt_id")
        rows = cur.fetchall()
        conn.close()

        if not rows:
            raise HTTPException(status_code=400, detail="No prompts found in geo-collector.db")

        prompts = [
            Prompt(
                prompt_id=r["prompt_id"],
                text=r["prompt_text"],
                category=r["category"] or "",
                intent=r["intent"] or "",
                location=r["location"] or "",
            )
            for r in rows
        ]

        # 使用适配器批量采集
        adapter = GeoCollectorDBAdapter(db_path=db_path, brand=brand)
        observations = await adapter.collect_batch(prompts)
    elif adapter_name == "mock":
        observations = []  # mock requires external seed data
    else:
        raise HTTPException(status_code=400, detail=f"Adapter {adapter_name} not supported in this endpoint")

    if not observations:
        raise HTTPException(status_code=400, detail="No observations returned by adapter")

    metrics = aggregate_metrics(observations, case_id=case_id, version="baseline")

    # Generate findings from observations
    findings_list = []
    for obs in observations:
        if not obs.brand_mentioned:
            findings_list.append(Finding(
                finding_id=f"FND-{body.project_id}-{len(findings_list)+1:03d}",
                observation_ids=[obs.observation_id],
                category=FindingCategory.VISIBILITY_GAP,
                severity=FindingSeverity.HIGH,
                statement=f"Brand not mentioned for query: '{obs.prompt_text}'",
                recommendation="Add entity-focused content and improve brand signals",
                confidence=0.9,
                project_id=body.project_id,
                case_id=case_id,
            ))
        elif obs.recommendation_level < 2:
            findings_list.append(Finding(
                finding_id=f"FND-{body.project_id}-{len(findings_list)+1:03d}",
                observation_ids=[obs.observation_id],
                category=FindingCategory.CITATION_QUALITY,
                severity=FindingSeverity.MEDIUM,
                statement=f"Low recommendation (level={obs.recommendation_level}) for: '{obs.prompt_text}'",
                recommendation="Improve content authority and add expert citations",
                confidence=0.7,
                project_id=body.project_id,
                case_id=case_id,
            ))

    # Store result for later retrieval
    import uuid as _uuid

    result = {
        # P0-4：稳定主键，供 measurements_projection 持久化与跨重启检索。
        "measurement_id": f"MSR-{_uuid.uuid4().hex[:8].upper()}",
        "project_id": body.project_id,
        "tenant_id": body.tenant_id,
        "adapter": adapter_name,
        "case_id": case_id,
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "observation_count": len(observations),
        # 存完整观测（含 competitors），否则历史查询拿不到数据，
        # 竞品分析等下游能力在 GET 路径上会静默退化成"无数据"。
        "observations": [o.to_dict() for o in observations],
        "metrics": metrics.to_dict(),
        "findings": [f.to_dict() for f in findings_list],
    }
    state._measurement_results.setdefault(body.project_id, []).append(result)

    # P0-4：落库（跨重启保留）。失败不阻断本次响应，但会记入日志。
    if state.measurement_repo is not None:
        try:
            await state.measurement_repo.upsert(result)
        except Exception as exc:  # noqa: BLE001 — 持久化失败不应吞掉已完成的采集
            import logging as _logging
            _logging.getLogger("api.measurements").warning(
                "measurement persistence failed for %s: %s", body.project_id, exc
            )

    return MeasurementOut(
        project_id=body.project_id,
        tenant_id=body.tenant_id,
        adapter=adapter_name,
        case_id=case_id,
        collected_at=result["collected_at"],
        observations=[
            ObservationOut(**o.to_dict()) for o in observations[: body.observation_limit]
        ],
        metrics=MetricsOut(**metrics.to_dict()),
        findings=[FindingOut(**f.to_dict()) for f in findings_list],
    )


@router.get("/{project_id}", response_model=List[MeasurementOut])
async def get_measurements(
    project_id: str,
    x_tenant_id: Annotated[str | None, Header(alias="X-Tenant-ID")] = None,
    auth=Depends(require_hq),
):
    """获取某项目的所有采集结果。"""
    # B-2：使用认证上下文的 tenant（header 已交叉校验）
    tenant_id = auth.tenant_id
    # B-1 修复：先校验项目归属，再读数据
    await _verify_tenant(project_id, tenant_id)
    from ..geo_view import load_measurements
    results = await load_measurements(project_id, tenant_id)
    if not results:
        raise HTTPException(status_code=404, detail=f"No measurements found for project {project_id}")
    # 双保险：结果内若含其他 tenant 的记录，一并拒绝
    if any(r.get("tenant_id") != tenant_id for r in results):
        raise HTTPException(status_code=404, detail="Measurement tenant mismatch")
    out = []
    for r in results:
        out.append(MeasurementOut(
            project_id=r["project_id"],
            tenant_id=r["tenant_id"],
            adapter=r["adapter"],
            case_id=r.get("case_id"),
            collected_at=r["collected_at"],
            observations=[
                ObservationOut(**o) for o in r.get("observations", [])
            ],
            metrics=MetricsOut(**r["metrics"]),
            findings=[FindingOut(**f) for f in r.get("findings", [])],
        ))
    return out
