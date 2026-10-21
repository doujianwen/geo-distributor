"""Fictional HQ queues, seeded only in isolated demo/acceptance databases."""
from pathlib import Path
from api import state


async def seed_hq_demo():
    if not state.active_db_path or Path(state.active_db_path).parent.name != "portal-demo":
        raise RuntimeError("HQ fictional seed requires the isolated portal-demo directory")
    from geo_distributor.models.client import Client
    from geo_distributor.models.project import Project, ProjectStatus
    from geo_distributor.models.request import ServiceRequest
    for tenant, cid, name in [("DEMO-PARTNER", "DEMO-CLI-PARTNER", "远山设备｜第二渠道虚拟客户")]:
        if not await state.client_repo.find_by_id(cid, tenant_id=tenant):
            await state.client_repo.create(Client(cid, tenant, name, industry="设备制造", website="https://yuanshan.example.test"))
    for suffix, tenant, cid, status in [("INTAKE", "DEMO-GEO", "DEMO-CLI-1", "submitted"),
                                       ("APPROVAL", "DEMO-PARTNER", "DEMO-CLI-PARTNER", "scope_pending_approval"),
                                       ("APPROVED-PARTNER", "DEMO-PARTNER", "DEMO-CLI-PARTNER", "approved")]:
        rid = "DEMO-REQ-" + suffix
        if not await state.request_repo.find_by_id(rid, tenant_id=tenant):
            scope = {"summary": "虚拟客户网站与竞品诊断", "confirmed_duration": "资料齐备后5个工作日（虚拟）", "deliverables": ["客户诊断报告"], "exclusions": ["不承诺询盘或排名"], "version": 1, "approved_at": None} if status in ("scope_pending_approval", "approved") else None
            item = ServiceRequest(rid, tenant, cid).to_dict()
            item.update(status=status, service="diagnosis", business_context={"market_scope": "global", "target_market": [], "target_languages": ["English"], "target_products": ["虚拟产品"], "business_question": "希望了解品牌AI可见性与改进方向（虚拟）", "service_duration": "one_time"}, workflow={"revision": 1, "scope": scope, "history": [{"action": "scope" if scope else "submitted", "role": "HQ_TECHNICAL" if scope else "DISTRIBUTOR_ADMIN", "at": "2026-10-18T08:00:00+00:00", "note": "虚拟审批队列"}]})
            if status == "approved":
                item.update(project_id="DEMO-PRJ-PARTNER", scope_id="DEMO-SCOPE-PARTNER")
                item["workflow"]["scope"].update(scope_id="DEMO-SCOPE-PARTNER", approved_at="2026-10-18T08:00:00+00:00", approved_by="virtual-demo-hq")
                item["workflow"]["history"][0]["action"]="approve"
                item["workflow"]["history"][0]["role"]="HQ_MANAGEMENT"
            await state.request_repo.create(ServiceRequest.from_dict(item))
    pid = "DEMO-PRJ-PARTNER"
    if not await state.project_repo.find_by_id(pid, tenant_id="DEMO-PARTNER"):
        await state.project_repo.create(Project(pid, "DEMO-REQ-APPROVED-PARTNER", "DEMO-PARTNER", "DEMO-CLI-PARTNER", "DEMO-SCOPE-PARTNER", status=ProjectStatus.APPROVED))
    await state.lead_repo.create_if_absent({"lead_id": "DEMO-HQ-LEAD-1", "tenant_id": "HQ-INTAKE", "project_id": "", "client_id": "", "request_id": "", "intake_status": "pending_assignment", "source": "fictional-demo", "source_lead_id": "DEMO-WEB-1", "service": "diagnosis", "assigned_tenant_id": "", "contact": {"name": "虚拟联系人", "company": "云岚机械｜虚拟线索", "email": "demo@example.test", "domain": "https://yunlan.example.test"}, "message": "希望了解海外市场AI回答表现（虚拟线索）", "created_at": "2026-10-18T09:00:00+00:00", "updated_at": "2026-10-18T09:00:00+00:00", "audit": [{"action": "intake", "at": "2026-10-18T09:00:00+00:00", "note": "虚拟官网接收"}]})
    repo = state.report_service._repository
    await repo.create_if_absent({"report_id": "DEMO-RPT-HQ-UNPUBLISHED", "tenant_id": "DEMO-GEO", "project_id": "DEMO-PRJ-2", "scope_version": 99, "version": 1, "measurement_id": "DEMO-MSR-ZERO", "is_client_safe": True, "title": "星帆家居诊断草案｜虚拟待发布", "created_at": "2026-10-18T10:00:00+00:00", "content": {"executive_summary": "尚待总部核对的虚拟报告", "key_findings": [], "limitations": ["虚拟案例，尚未向客户发布"]}})
    from api import customer_service as svc
    from api.auth import AuthContext
    key = "demo-hq-awaiting-team"
    ident = "CRV-" + svc.digest(["DEMO-GEO", key])[:24].upper()
    if not await state.customer_review_repo.get(ident):
        hq = AuthContext("DEMO-GEO", "HQ_TECHNICAL", "virtual-demo-ops", True)
        r = await svc.create_review({"project_id": "DEMO-PRJ-1", "kind": "material_request", "title": "应用场景资料（虚拟已答待处理）", "instructions": "请补充应用场景。", "report_id": None}, key, hq)
        await svc.respond_review(r["review_id"], {"revision": r["revision"], "action": "submit", "note": "虚拟客户答复：主要用于食品加工设备选型。"}, "demo-hq-response", AuthContext("DEMO-GEO", "END_CUSTOMER", "virtual-demo-customer", False, "DEMO-CLI-1"))
