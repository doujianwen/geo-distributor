"""分销 / 采集调度路由（平台层）。

把 DistributionService 暴露为 HTTP 能力。此前该服务只有类定义、
无入口，属于"代码存在但能力不可达"。

注意：本路由管理的是**平台层采集侧**对象（Organization / Brand /
CollectionProject / Run / CollectionReport），与商业交付侧的
/clients / /projects 是两套东西，不要混用 ID。
"""

from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .. import state

router = APIRouter(prefix="/distribution", tags=["distribution"])


# ------------------------------------------------------------------
# Schemas
# ------------------------------------------------------------------


class OrgCreate(BaseModel):
    name: str
    contact_email: str = ""


class OrgOut(BaseModel):
    org_id: str
    name: str
    status: str
    contact_email: str
    created_at: str


class BrandCreate(BaseModel):
    org_id: str
    name: str
    aliases: List[str] = Field(default_factory=list)
    competitors: List[str] = Field(default_factory=list)
    target: str = "primary"


class BrandOut(BaseModel):
    brand_id: str
    org_id: str
    name: str
    target: str
    aliases: List[str]
    competitors: List[str]


class CollectionProjectCreate(BaseModel):
    org_id: str
    brand_id: str
    name: str
    prompts_file: str
    engines: List[str] = Field(default_factory=list)
    schedule_cron: str = ""


class CollectionProjectOut(BaseModel):
    project_id: str
    org_id: str
    brand_id: str
    name: str
    status: str
    prompts_file: str
    engines: List[str]
    schedule_cron: str


class RunOut(BaseModel):
    run_id: str
    project_id: str
    status: str
    started_at: str
    ended_at: Optional[str] = None
    total_prompts: int = 0
    successful: int = 0
    failed: int = 0
    skipped: int = 0
    error_summary: str = ""
    prompt_mismatch: int = 0


class ReportOut(BaseModel):
    report_id: str
    project_id: str
    run_ids: List[str]
    title: str
    total_observations: int
    brand_mentioned_count: int
    brand_recommended_count: int
    summary: dict


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _svc():
    if state.distribution_service is None:
        raise HTTPException(status_code=503, detail="DistributionService not initialized")
    return state.distribution_service


# ------------------------------------------------------------------
# Organization
# ------------------------------------------------------------------


@router.post("/orgs", response_model=OrgOut, status_code=201)
async def create_org(body: OrgCreate):
    from geo_distributor.services.distribution import DistributionError
    try:
        org = await _svc().create_organization(body.name, body.contact_email)
    except DistributionError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return OrgOut(
        org_id=org.org_id, name=org.name, status=org.status.value,
        contact_email=org.contact_email, created_at=org.created_at,
    )


@router.get("/orgs", response_model=List[OrgOut])
async def list_orgs():
    return [
        OrgOut(
            org_id=o.org_id, name=o.name, status=o.status.value,
            contact_email=o.contact_email, created_at=o.created_at,
        )
        for o in _svc().list_organizations()
    ]


# ------------------------------------------------------------------
# Brand
# ------------------------------------------------------------------


@router.post("/brands", response_model=BrandOut, status_code=201)
async def create_brand(body: BrandCreate):
    from geo_distributor.services.distribution import DistributionError
    from geo_distributor.models import BrandTarget
    try:
        target = BrandTarget(body.target) if body.target in (
            t.value for t in BrandTarget
        ) else BrandTarget.PRIMARY
        brand = await _svc().create_brand(
            body.org_id, body.name,
            aliases=body.aliases, target=target, competitors=body.competitors,
        )
    except DistributionError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return BrandOut(
        brand_id=brand.brand_id, org_id=brand.org_id, name=brand.name,
        target=brand.target.value, aliases=brand.aliases, competitors=brand.competitors,
    )


@router.get("/brands", response_model=List[BrandOut])
async def list_brands(org_id: str):
    return [
        BrandOut(
            brand_id=b.brand_id, org_id=b.org_id, name=b.name,
            target=b.target.value, aliases=b.aliases, competitors=b.competitors,
        )
        for b in _svc().list_brands(org_id)
    ]


# ------------------------------------------------------------------
# CollectionProject
# ------------------------------------------------------------------


@router.post("/projects", response_model=CollectionProjectOut, status_code=201)
async def create_collection_project(body: CollectionProjectCreate):
    from geo_distributor.services.distribution import DistributionError
    try:
        p = await _svc().create_project(
            body.org_id, body.brand_id, body.name,
            prompts_file=body.prompts_file,
            engines=body.engines, schedule_cron=body.schedule_cron,
        )
    except DistributionError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return CollectionProjectOut(
        project_id=p.project_id, org_id=p.org_id, brand_id=p.brand_id,
        name=p.name, status=p.status.value, prompts_file=p.prompts_file,
        engines=p.engines, schedule_cron=p.schedule_cron,
    )


@router.get("/projects", response_model=List[CollectionProjectOut])
async def list_collection_projects(org_id: Optional[str] = None):
    return [
        CollectionProjectOut(
            project_id=p.project_id, org_id=p.org_id, brand_id=p.brand_id,
            name=p.name, status=p.status.value, prompts_file=p.prompts_file,
            engines=p.engines, schedule_cron=p.schedule_cron,
        )
        for p in _svc().list_projects(org_id=org_id)
    ]


@router.post("/projects/{project_id}/run", response_model=RunOut, status_code=201)
async def run_collection_project(project_id: str):
    """触发一次采集运行。"""
    from geo_distributor.services.distribution import DistributionError
    svc = _svc()
    project = svc.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail=f"collection project not found: {project_id}")
    try:
        run = await svc.run_project(project)
    except DistributionError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return RunOut(**run.__dict__)


@router.get("/runs", response_model=List[RunOut])
async def list_runs(project_id: Optional[str] = None):
    return [RunOut(**r.__dict__) for r in _svc().list_runs(project_id=project_id)]


# ------------------------------------------------------------------
# Report
# ------------------------------------------------------------------


@router.post("/runs/{run_id}/report", response_model=ReportOut, status_code=201)
async def generate_run_report(run_id: str):
    svc = _svc()
    run = svc.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"run not found: {run_id}")
    rep = await svc.generate_report_for_run(run)
    return ReportOut(**rep.__dict__)


@router.get("/reports", response_model=List[ReportOut])
async def list_reports(project_id: Optional[str] = None):
    return [ReportOut(**r.__dict__) for r in _svc().list_reports(project_id=project_id)]
