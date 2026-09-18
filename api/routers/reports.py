"""Reports router — retrieve generated reports for projects."""

from __future__ import annotations
from typing import Annotated, List

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from .. import state

router = APIRouter(prefix="/reports", tags=["reports"])


# ------------------------------------------------------------------
# Response schema
# ------------------------------------------------------------------

class ReportOut(BaseModel):
    report_id: str
    project_id: str
    tenant_id: str
    title: str
    version: int
    visibility_score: float
    visibility_summary: dict
    key_findings: List[dict]
    limitations: List[str]
    next_steps: List[str]
    created_at: str

    model_config = {"from_attributes": True}


# ------------------------------------------------------------------
# Endpoints
# ------------------------------------------------------------------

@router.get("", response_model=List[ReportOut])
async def list_reports(
    project_id: str,
    x_tenant_id: Annotated[str | None, Header(alias="X-Tenant-ID")] = None,
):
    """列出某项目的所有报告。"""
    svc = state.delivery_service
    if svc is None:
        raise HTTPException(status_code=503, detail="API not initialized")
    reports = await svc.list_reports(project_id)
    return [ReportOut(**r) for r in reports]


@router.get("/{report_id}", response_model=ReportOut)
async def get_report(
    report_id: str,
    x_tenant_id: Annotated[str | None, Header(alias="X-Tenant-ID")] = None,
):
    """获取单个报告详情。"""
    svc = state.delivery_service
    if svc is None:
        raise HTTPException(status_code=503, detail="API not initialized")
    report = await svc.get_report(report_id)
    if not report:
        raise HTTPException(status_code=404, detail=f"Report {report_id} not found")
    return ReportOut(**report)
