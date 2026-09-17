"""业务服务层（占位，等待 A1.7 实现）。"""

from typing import List, Optional
from ..models import Organization, Account, Brand, Project, Run, Report
from ..adapters import BaseAdapter


class DistributionService:
    """分销系统核心业务服务。

    协调 Organization / Project / Brand 的生命周期，
    管理采集调度与报告生成。
    """

    def __init__(self, adapter: BaseAdapter):
        self._adapter = adapter

    async def create_organization(self, name: str, contact_email: str = "") -> Organization:
        # TODO: A1.7 实现持久化
        from datetime import datetime
        org_id = f"org_{len([]) + 1:03d}"
        return Organization(org_id=org_id, name=name, contact_email=contact_email)

    async def create_brand(
        self, org_id: str, name: str, aliases: Optional[List[str]] = None
    ) -> Brand:
        # TODO: A1.7 实现
        brand_id = f"brand_{len([]) + 1:03d}"
        return Brand(brand_id=brand_id, org_id=org_id, name=name, aliases=aliases or [])

    async def create_project(
        self,
        org_id: str,
        brand_id: str,
        name: str,
        prompts_file: str,
        engines: Optional[List[str]] = None,
        schedule_cron: str = "",
    ) -> Project:
        # TODO: A1.7 实现
        from datetime import datetime
        project_id = f"proj_{len([]) + 1:03d}"
        return Project(
            project_id=project_id,
            org_id=org_id,
            brand_id=brand_id,
            name=name,
            prompts_file=prompts_file,
            engines=engines or [],
            schedule_cron=schedule_cron,
        )

    async def run_project(self, project: Project) -> Run:
        """触发一次采集运行。"""
        return await self._adapter.run_collection(
            project=project,
            prompts_file=project.prompts_file,
            engines=project.engines,
        )

    async def generate_report_for_run(self, run: Run) -> Report:
        """为一次运行生成报告。"""
        return await self._adapter.generate_report(run)
