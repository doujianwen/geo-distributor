"""Deterministic fictional examples; restricted to a dedicated demo directory."""
from copy import deepcopy
from pathlib import Path
import json
import sqlite3

TENANT = "DEMO-GEO"


def batch(project="DEMO-PRJ-1", ident="DEMO-MSR-1", day=1, mentions=1):
    obs = []
    for i in range(4):
        yes = i < mentions
        obs.append({
            "observation_id": f"{ident}-O{i}", "prompt_text": ["哪些工业水处理品牌适合中小型工厂？", "如何选择工业过滤设备供应商？"][i // 2],
            "engine": ["ChatGPT", "Perplexity"][i % 2], "timestamp": f"2026-10-{day:02d}T08:0{i}:00+00:00",
            "brand_mentioned": yes, "brand_status": "MENTIONED" if yes else "NOT_MENTIONED",
            "recommendation_level": 3 if yes else 0, "citations_status": "extracted",
            "status": "success", "validation_status": "PASS", "brand": "澄源工业（虚拟）",
            "citations": [{"url": "https://chengyuan.example.test/guide", "title": "虚拟工业过滤选型指南"}],
            "competitors": [{"name": "蓝峰设备（虚拟）"}],
            "is_client_safe": True, "client_safe_excerpt": "【虚拟回答摘要】本条用于演示品牌在选型回答中的出现情况，不是实际平台回答。",
        })
    return {"measurement_id": ident, "project_id": project, "tenant_id": TENANT, "adapter": "fictional-demo", "case_id": "fictional-only",
            "collected_at": f"2026-10-{day:02d}T09:00:00+00:00", "observation_count": 4,
            "comparison_context": {"brand": "澄源工业（虚拟）", "market": "US", "language": "Chinese", "method_version": "demo-fixed-v1"},
            "observations": obs, "metrics": {"case_id": "fictional-only", "version": "baseline", "query_count": 4,
                "mention_rate": mentions * 25, "recommendation_rate": mentions * 25, "citation_rate": 100,
                "query_coverage": 100, "avg_recommendation_level": mentions * .75, "competitor_count": 1,
                "captured_at": f"2026-10-{day:02d}T09:00:00+00:00"}, "findings": []}


async def seed_demo(directory: Path):
    directory = directory.absolute()
    if directory.name != "portal-demo" or directory.is_symlink() or directory.resolve() != directory:
        raise RuntimeError("Demo seed requires its own non-symlink portal-demo directory")
    directory.mkdir(parents=True, exist_ok=True)
    db = directory / "portal.db"
    if db.is_symlink():
        raise RuntimeError("Demo database may not be a symlink")
    # Refuse accidental reuse of any existing non-demo business database BEFORE init.
    if db.exists():
        with sqlite3.connect(db) as conn:
            tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            for table in ("clients", "projects", "requests", "measurements_projection", "reports_projection", "leads_intake"):
                if table in tables:
                    for tenant, payload in conn.execute(f"SELECT tenant_id,payload FROM {table}"):
                        item = json.loads(payload)
                        field = {"clients":"client_id", "projects":"project_id", "requests":"request_id", "measurements_projection":"measurement_id", "reports_projection":"report_id", "leads_intake":"lead_id"}[table]
                        ident = item.get(field, "")
                        allowed = tenant in {TENANT, "DEMO-PARTNER"} or (tenant == "HQ-INTAKE" and table == "leads_intake")
                        if not allowed or item.get("tenant_id") != tenant or not str(ident).startswith("DEMO-"):
                            raise RuntimeError("Refusing a non-demo database")
    from api import state
    from geo_distributor.models.client import Client
    from geo_distributor.models.project import Project, ProjectStatus, BlockedReason
    from geo_distributor.models.request import ServiceRequest, RequestStatus, BusinessContext
    from geo_distributor.models.service_stage import ServiceStage
    state.init_repositories(str(db))
    names = ["澄源工业｜虚拟演示", "星帆家居｜虚拟演示", "青禾新材｜虚拟演示"]
    for i, name in enumerate(names, 1):
        cid, pid, rid = f"DEMO-CLI-{i}", f"DEMO-PRJ-{i}", f"DEMO-REQ-{i}"
        if not await state.client_repo.find_by_id(cid, tenant_id=TENANT):
            await state.client_repo.create(Client(cid, TENANT, name, industry=["工业设备", "家居", "新材料"][i-1], website=f"https://demo{i}.example.test", metadata={"is_demo": True}))
        if not await state.request_repo.find_by_id(rid, tenant_id=TENANT):
            await state.request_repo.create(ServiceRequest(rid, TENANT, cid, status=RequestStatus.APPROVED,
                service="full_geo_project", project_id=pid, scope_id=f"DEMO-SCOPE-{i}",
                business_context=BusinessContext(target_market=["US"], market_scope="single", target_languages=["Chinese"], business_question="查看品牌在AI回答中的表现及下一步建议（虚拟演示）"),
                workflow={"revision": 1, "scope": {"summary": "虚拟诊断与复测案例", "confirmed_duration": "演示周期", "deliverables": ["虚拟效果查看", "虚拟报告"], "version": 1, "approved_by": "虚拟总部"}, "history": [{"action": "approve", "actor": "虚拟总部", "at": "2026-10-01T08:00:00+00:00", "note": "仅演示，不是真实审批"}]}))
        if not await state.project_repo.find_by_id(pid, tenant_id=TENANT):
            p = Project(pid, rid, TENANT, cid, f"DEMO-SCOPE-{i}", status=ProjectStatus.IN_EXECUTION)
            if i == 1:
                p.service_stage = ServiceStage.EFFECT_MONITORING
            if i == 2:
                p.status = ProjectStatus.BLOCKED
                p.blocked_reason = BlockedReason("虚拟部分平台采集失败", required_action="由总部复核采集后重新测量", owner="HQ")
            await state.project_repo.create(p)
    rows = [batch(), batch(ident="DEMO-MSR-2", day=15, mentions=3),
            batch("DEMO-PRJ-2", "DEMO-MSR-ZERO", day=1, mentions=0),
            batch("DEMO-PRJ-2", "DEMO-MSR-PARTIAL", day=15, mentions=0)]
    rows[2]["comparison_context"]["brand"] = "星帆家居（虚拟）"
    rows[3]["comparison_context"]["brand"] = "星帆家居（虚拟）"
    rows[3]["observations"][0].update(status="failed", validation_status="FAIL", brand_status="UNKNOWN", recommendation_level=-1, citations_status="unavailable")
    rows[3]["observations"][1].update(brand_status="UNKNOWN", recommendation_level=-1, citations_status="unavailable")
    for r in rows:
        if r["project_id"] == "DEMO-PRJ-2":
            for o in r["observations"]:
                o.update(brand="星帆家居（虚拟）", prompt_text=o["prompt_text"].replace("工业", "家居"), competitors=[{"name": "云栖家居（虚拟）"}], citations=[{"url": "https://xingfan.example.test/guide", "title": "虚拟家居选型指南"}])
        await state.measurement_repo.create_if_absent(r)
    from geo_distributor.persistence import SQLiteJSONRepository
    reports = SQLiteJSONRepository("reports_projection", str(db), scope_unique=True)
    for idx, (mid, count) in enumerate((("DEMO-MSR-1", 1), ("DEMO-MSR-2", 3)), 1):
        await reports.create_if_absent({"report_id": f"DEMO-RPT-{idx}", "project_id": "DEMO-PRJ-1", "tenant_id": TENANT,
            "scope_version": idx, "measurement_id": mid, "version": idx, "title": f"澄源工业 GEO 效果报告｜虚拟演示 {idx}",
            "created_at": f"2026-10-{1 if idx==1 else 15:02d}T10:00:00+00:00", "is_client_safe": True,
            "content": {"visibility_score": count * 25, "visibility_summary": {"total_queries": 4, "brand_mentioned": count, "brand_recommended": count},
                "key_findings": [{"statement": "虚拟样本中，品牌在部分选型问题中尚未出现。", "recommendation": "演示建议：补充产品适用场景及可核验的技术资料。"}],
                "limitations": ["全部为人为构造的虚拟案例，不是平台实测，也不证明增长效果。", "观察样本有限，不承诺排名、询盘或收入增长。"],
                "next_steps": ["演示下一步：核对问题范围，再安排同口径复测。"]}})
    return db
