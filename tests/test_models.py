"""测试：数据模型。"""

import sys
import os
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from geo_distributor.models import (
    Organization, Account, Brand, CollectionProject, Run, CollectionReport,
    OrganizationStatus, CollectionProjectStatus, BrandTarget,
)


def test_organization_defaults():
    org = Organization(org_id="org_001", name="TestOrg")
    assert org.status == OrganizationStatus.ACTIVE
    assert org.created_at != ""


def test_brand_with_aliases():
    brand = Brand(
        brand_id="b1",
        org_id="org_001",
        name="Hydroviv",
        aliases=["Hydroviv Water", "Hydroviv filter"],
        competitors=["Brita", "Aquasana"],
    )
    assert brand.target == BrandTarget.PRIMARY
    assert len(brand.aliases) == 2
    assert len(brand.competitors) == 2


def test_project_default_status():
    project = CollectionProject(
        project_id="p1",
        org_id="org_001",
        brand_id="b1",
        name="Water Filter Test",
        prompts_file="prompts/hydroviv_20.csv",
        engines=["chatgpt", "perplexity"],
    )
    assert project.status == CollectionProjectStatus.DRAFT
    assert project.schedule_cron == ""


def test_run_status_flow():
    run = Run(run_id="r1", project_id="p1", started_at="2026-09-10T00:00:00")
    assert run.status == "running"
    assert run.total_prompts == 0
    run.status = "completed"
    run.ended_at = "2026-09-10T00:05:00"
    assert run.status == "completed"


def test_report_with_stats():
    report = CollectionReport(
        report_id="rep1",
        project_id="p1",
        total_observations=33,
        brand_mentioned_count=5,
        brand_recommended_count=0,
    )
    assert report.total_observations == 33
    assert report.brand_mentioned_count == 5
