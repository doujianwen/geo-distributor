"""Explicit client publication and collaboration fixtures in the existing demo DB."""
from pathlib import Path
import json
from api import state
from api.auth import AuthContext
from api import customer_service as svc


async def seed_customer_demo():
    path = Path(state.active_db_path or "").resolve()
    if path.parent.name != "portal-demo" or path.name != "portal.db":
        raise RuntimeError("Customer demo must use the dedicated portal-demo database")
    for repo in (state.customer_publication_repo, state.customer_review_repo):
        conn = repo._connect()
        try:
            rows = [json.loads(row[0]) for row in conn.execute(f"SELECT payload FROM {repo.table}")]
        finally:
            conn.close()
        for r in rows:
            if r.get("tenant_id") != "DEMO-GEO" or not r.get("client_id", "").startswith("DEMO-") or not r.get("project_id", "").startswith("DEMO-"):
                raise RuntimeError("Refusing non-demo collaboration data")
    hq = AuthContext("DEMO-GEO", "HQ_MANAGEMENT", "virtual-demo-hq", True)
    customer = AuthContext("DEMO-GEO", "END_CUSTOMER", "virtual-demo-customer", False, "DEMO-CLI-1")
    # Keep the fictional monitoring example's stage records consistent with its stage.
    from geo_distributor.models.service_stage import ServiceStage, StageStatus
    p = await state.project_repo.find_by_id("DEMO-PRJ-1", tenant_id="DEMO-GEO")
    if p and p.service_stage == ServiceStage.EFFECT_MONITORING and all(s.status == StageStatus.NOT_STARTED for s in p.stage_records.values()):
        for s in p.stage_records.values():
            s.status = StageStatus.IN_PROGRESS if s.stage == ServiceStage.EFFECT_MONITORING else StageStatus.COMPLETED
            s.started_at = "2026-10-01T08:00:00+00:00"
            if s.status == StageStatus.COMPLETED:
                s.completed_at = "2026-10-15T08:00:00+00:00"
        p.updated_at = "2026-10-15T09:00:00+00:00"
        await state.project_repo.update(p)
    # Enrich only our two fictional legacy fixtures for the unchanged QA contract.
    repo = state.report_service._repository
    for ident in ("DEMO-RPT-1", "DEMO-RPT-2"):
        r = await repo.get(ident, tenant_id="DEMO-GEO")
        if r.get("project_id") != "DEMO-PRJ-1" or "虚拟" not in r.get("title", ""):
            raise RuntimeError("Unexpected non-fictional report at demo ID")
        if not r.get("type") or "executive_summary" not in r.get("content", {}):
            r["type"] = "client"
            r["content"]["executive_summary"] = "虚拟演示：用于理解结果、依据与改善建议，不代表真实平台实测。"
            await repo.upsert(r)
        pub_id = "PUB-" + svc.digest(["DEMO-GEO", ident])[:24].upper()
        if not await state.customer_publication_repo.get(pub_id, tenant_id="DEMO-GEO"):
            await svc.publish(ident, hq)
    async def seed_review(body, key):
        ident = "CRV-" + svc.digest(["DEMO-GEO", key])[:24].upper()
        existing = await state.customer_review_repo.get(ident, tenant_id="DEMO-GEO")
        return svc.review_dto(existing) if existing else await svc.create_review(body, key, hq)
    base = {"project_id": "DEMO-PRJ-1", "report_id": None}
    await seed_review({**base, "kind": "material_request", "title": "补充产品应用场景（虚拟）", "instructions": "请说明主要客户、适用工况与产品差异；仅文字说明，不提供密码或密钥。"}, "demo-customer-material")
    await seed_review({**base, "kind": "content_review", "title": "确认下一步优化方向（虚拟）", "instructions": "建议补充选型说明及可核验技术资料。请确认此方向，或说明需要调整的内容。"}, "demo-customer-content")
    r = await seed_review({**base, "report_id": "DEMO-RPT-1", "kind": "report_feedback", "title": "基线报告意见（虚拟已处理）", "instructions": "请确认基线报告是否清楚，并提供意见。"}, "demo-customer-finished")
    if r["status"] == "pending":
        r = await svc.respond_review(r["review_id"], {"revision": r["revision"], "action": "confirm", "note": "虚拟客户：已阅读，后续希望补充产品选型依据。"}, "demo-response", customer)
    if r["status"] == "confirmed":
        await svc.process_review(r["review_id"], {"revision": r["revision"], "action": "close", "note": "虚拟服务团队：已将意见纳入后续资料计划，本项反馈已处理，不代表项目已验收。"}, "demo-close", hq)
