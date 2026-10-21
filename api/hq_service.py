"""HQ orchestration and read projections; no measurement or delivery algorithms."""
from contextlib import contextmanager
from copy import deepcopy
import hashlib
import json
import threading
from fastapi import HTTPException
from . import state
from .request_workflow import now

_lock = threading.RLock()
TABLES = {
    "clients": ("client_repo", "client_id"), "projects": ("project_repo", "project_id"),
    "requests": ("request_repo", "request_id"), "leads_intake": ("lead_repo", "lead_id"),
    "hq_operations": ("hq_operation_repo", "operation_id"),
}


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


class Unit:
    def __init__(self, conn=None):
        self.conn, self.pending = conn, {}

    def get(self, table, ident):
        if self.conn:
            row = self.conn.execute(f"SELECT payload FROM {table} WHERE id=?", (ident,)).fetchone()
            return json.loads(row[0]) if row else None
        repo = getattr(state, TABLES[table][0])
        item = (repo._store if hasattr(repo, "_store") else repo._rows).get(ident)
        return deepcopy(item.to_dict() if hasattr(item, "to_dict") else item)

    def put(self, table, item):
        ident = item[TABLES[table][1]]
        if self.conn:
            if table in ("clients", "projects", "requests"):
                self.conn.execute(f"INSERT INTO {table}(id,tenant_id,payload,updated_at) VALUES(?,?,?,?) "
                    "ON CONFLICT(id) DO UPDATE SET tenant_id=excluded.tenant_id,payload=excluded.payload,updated_at=excluded.updated_at",
                    (ident, item["tenant_id"], json.dumps(item, ensure_ascii=False), item.get("updated_at", now())))
            else:
                self.conn.execute(f"INSERT INTO {table}(id,tenant_id,project_id,payload,updated_at) VALUES(?,?,?,?,?) "
                    "ON CONFLICT(id) DO UPDATE SET tenant_id=excluded.tenant_id,project_id=excluded.project_id,payload=excluded.payload,updated_at=excluded.updated_at",
                    (ident, item["tenant_id"], item.get("project_id", ""), json.dumps(item, ensure_ascii=False), item.get("updated_at", now())))
        else:
            self.pending[(table, ident)] = deepcopy(item)

    def commit(self):
        from geo_distributor.models.project import Project
        from geo_distributor.models.client import Client
        converted = [(table, ident, (Project if table == "projects" else Client).from_dict(item)
                      if table in ("projects", "clients") else item)
                     for (table, ident), item in self.pending.items()]
        for table, ident, item in converted:
            repo = getattr(state, TABLES[table][0])
            if hasattr(repo, "_store"):
                repo._store[ident] = item
                repo._by_tenant.setdefault(item.tenant_id, set()).add(ident)
            else:
                repo._rows[ident] = item


@contextmanager
def transaction():
    if state.hq_operation_repo is None or state.project_repo is None:
        raise HTTPException(503, "总部服务暂不可用")
    with _lock:
        conn = state.project_repo._connect() if state.persistence_backend == "sqlite" else None
        tx = Unit(conn)
        try:
            if conn:
                conn.execute("BEGIN IMMEDIATE")
            yield tx
            if conn:
                conn.commit()
            else:
                tx.commit()
        except Exception:
            if conn:
                conn.rollback()
            raise
        finally:
            if conn:
                conn.close()


def require_hq(auth):
    if not auth.is_hq or auth.role not in ("HQ_TECHNICAL", "HQ_MANAGEMENT"):
        raise HTTPException(403, "仅总部可处理此操作")


def assign(ident, body, auth):
    require_hq(auth)
    from .auth import registered_tenants_by_role
    from .routers.leads import LEAD_INTAKE_TENANT, _audit
    from geo_distributor.models.client import Client
    target = (body.get("tenant_id") or "").strip()
    if not target:
        raise HTTPException(422, "请选择渠道商")
    allowed = registered_tenants_by_role({"DISTRIBUTOR_ADMIN", "DISTRIBUTOR_USER"})
    if target != LEAD_INTAKE_TENANT and target not in allowed:
        raise HTTPException(422, "目标不是已注册渠道商")
    data = {"tenant_id": target, "create_client": bool(body.get("create_client")),
            "client_name": (body.get("client_name") or "").strip()}
    fp = fingerprint(data)
    with transaction() as tx:
        row = tx.get("leads_intake", ident)
        if not row:
            raise HTTPException(404, "线索不存在")
        prior = row.get("assignment_fingerprint")
        if prior:
            if prior == fp:
                return {**row, "deduplicated": True}
            raise HTTPException(409, "线索已分配；不能用不同内容重复分配")
        if row.get("intake_status") not in ("new", "pending_assignment", "hq_managed"):
            raise HTTPException(409, "线索已分配，请刷新核对")
        if row.get("request_id") or row.get("project_id"):
            raise HTTPException(409, "线索已有后续业务，不可重新分配")
        cid = row.get("client_id", "")
        if cid:
            client = tx.get("clients", cid)
            if not client or client["tenant_id"] != target or not client.get("is_active", True):
                raise HTTPException(409, "既有关联客户与目标渠道不一致，请核对")
        elif data["create_client"]:
            contact = row.get("contact") or {}
            cid = "CLI-" + fingerprint([ident, target])[:24].upper()
            if tx.get("clients", cid):
                raise HTTPException(409, "客户编号冲突，请核对原线索")
            client = Client(cid, target, data["client_name"] or contact.get("company") or contact.get("name") or "官网客户",
                            website=contact.get("domain") or "", contact_email=contact.get("email") or "")
            tx.put("clients", client.to_dict())
        before = row.get("intake_status", "")
        row.update(tenant_id=target, assigned_tenant_id="" if target == LEAD_INTAKE_TENANT else target,
                   client_id=cid, updated_at=now(), assignment_fingerprint=fp,
                   intake_status="hq_managed" if target == LEAD_INTAKE_TENANT else "converted_client" if cid else "assigned")
        _audit(row, auth.user_id, "assign", before, row["intake_status"], "总部直管" if target == LEAD_INTAKE_TENANT else "分配渠道：" + target)
        row["audit"][-1]["role"] = auth.role
        tx.put("leads_intake", row)
        return row


def project_operation(ident, body, key, auth):
    require_hq(auth)
    from geo_distributor.models.project import Project, ProjectStatus
    from geo_distributor.models.service_stage import StageStatus
    if not key or len(key) > 128 or not body.get("expected_updated_at"):
        raise HTTPException(422, "请刷新项目后携带当前版本与幂等编号操作")
    # This workspace does not create a second output-reference system.
    if any(body.get(k) for k in ("finding_ids", "measurement_ids", "report_ids")):
        raise HTTPException(422, "请通过既有交付与报告链路登记产出，本操作不接受手工产出编号")
    fp = fingerprint(body)
    operation_id = "HOP-" + fingerprint([auth.tenant_id, ident, key])[:24].upper()
    with transaction() as tx:
        raw = tx.get("projects", ident)
        if not raw or raw["tenant_id"] != auth.tenant_id:
            raise HTTPException(404, "项目不存在或无访问权限")
        old = tx.get("hq_operations", operation_id)
        if old:
            if old["fingerprint"] != fp:
                raise HTTPException(409, "此操作编号已用于其他内容")
            return {**old["result"], "deduplicated": True}
        if raw.get("updated_at") != body["expected_updated_at"]:
            raise HTTPException(409, "项目已更新，请刷新后再操作；本次未改变阶段")
        p = Project.from_dict(raw)
        action = body["action"]
        before = {"status": p.status.value, "stage": p.service_stage.value}
        note = (body.get("note") or "").strip()
        if action == "start":
            if p.status != ProjectStatus.APPROVED:
                raise HTTPException(409, "仅已批准且未启动的项目可以启动")
            if not p.scope_id:
                raise HTTPException(409, "缺少已确认范围，不能启动")
            p.transition_to(ProjectStatus.IN_EXECUTION)
            p.start_stage()
        elif action == "block":
            if p.status != ProjectStatus.IN_EXECUTION or not note or not (body.get("required_action") or "").strip():
                raise HTTPException(409, "仅执行中项目可登记阻塞，须说明原因与所需行动")
            p.set_blocked(note, body["required_action"].strip(), body.get("owner", "HQ"))
            p.transition_to(ProjectStatus.BLOCKED)
        elif action == "resume":
            if p.status != ProjectStatus.BLOCKED or not note:
                raise HTTPException(409, "仅受阻项目可恢复，须填写解除说明")
            p.clear_blocked()
            p.transition_to(ProjectStatus.IN_EXECUTION)
        else:
            if p.status != ProjectStatus.IN_EXECUTION:
                raise HTTPException(409, "只有交付执行中的项目可处理阶段；受阻项目请先恢复")
            if p.get_stage_record().status == StageStatus.BLOCKED:
                raise HTTPException(409, "当前服务阶段受阻，请先核对阶段记录")
            if action == "advance":
                from geo_distributor.models.service_stage import ServiceStage
                target = ServiceStage(body["target_stage"]) if body.get("target_stage") else None
                if not p.advance_stage(target):
                    raise HTTPException(409, "当前阶段不能按此方向推进，末阶段请完成阶段")
            elif action == "complete":
                if p.get_stage_record().status == StageStatus.COMPLETED:
                    raise HTTPException(409, "当前阶段已经完成")
                p.complete_current_stage()
            else:
                raise HTTPException(422, "未知操作")
        p.updated_at = now()
        result = {"success": True, "project_id": ident, "status": p.status.value,
                  "service_stage": p.service_stage.value, "updated_at": p.updated_at,
                  "stage_progress": p.stage_progress, "stage_label": p.service_stage.label}
        event = {"operation_id": operation_id, "tenant_id": p.tenant_id, "project_id": ident,
                 "action": action, "role": auth.role, "actor": auth.user_id, "at": now(), "updated_at": now(),
                 "before": before, "after": {"status": p.status.value, "stage": p.service_stage.value},
                 "note": note, "fingerprint": fp, "result": result}
        tx.put("projects", p.to_dict())
        tx.put("hq_operations", event)
        return result


async def all_rows(table, repo=None):
    repo = repo or (getattr(state, TABLES[table][0]) if table in TABLES else None)
    if repo is None:
        raise HTTPException(503, "总部依赖暂不可用，请重试")
    if state.persistence_backend == "sqlite":
        conn = repo._connect()
        try:
            return [json.loads(r[0]) for r in conn.execute(f"SELECT payload FROM {table}")]
        finally:
            conn.close()
    if hasattr(repo, "list_all"):
        return deepcopy(await repo.list_all())
    return [deepcopy(r.to_dict()) for r in repo._store.values()]


async def workspace(auth, selected=None):
    require_hq(auth)
    from .auth import registered_tenants_by_role
    from . import customer_service as customer
    from .routers.leads import _lead_out
    cs, ps, rs, ls, ops = [await all_rows(t) for t in TABLES]
    pubs = await all_rows("client_publications", state.customer_publication_repo)
    reviews = await all_rows("client_reviews", state.customer_review_repo)
    report_repo = getattr(state.report_service, "_repository", None)
    if state.report_service is None:
        raise HTTPException(503, "报告服务暂不可用")
    reports = await all_rows("reports_projection", report_repo) if report_repo else deepcopy(list(state.report_service._reports.values()))
    registered = registered_tenants_by_role({"DISTRIBUTOR_ADMIN", "DISTRIBUTOR_USER"})
    known = registered | {r["tenant_id"] for rows in (cs, ps, rs, ls, pubs, reviews) for r in rows}
    known.add("HQ-INTAKE")
    if selected and selected not in known:
        raise HTTPException(404, "该渠道范围不存在")
    filt = lambda rows: [r for r in rows if not selected or r["tenant_id"] == selected]
    names = {(c["tenant_id"], c["client_id"]): c["name"] for c in cs}
    active_clients = {(c["tenant_id"], c["client_id"]): c.get("is_active", True) for c in cs}
    projects = {(p["tenant_id"], p["project_id"]): p for p in ps}
    requests = {(r["tenant_id"], r["request_id"]): r for r in rs}
    def context(r):
        p = projects.get((r["tenant_id"], r.get("project_id")), {})
        cid = r.get("client_id") or p.get("client_id", "")
        return {"tenant_id": r["tenant_id"], "client_id": cid,
                "client_name": names.get((r["tenant_id"], cid), "客户未记录"), "project_id": r.get("project_id", "")}
    client_out = [{k: c.get(k) for k in ("client_id", "tenant_id", "name", "industry", "website", "is_active", "created_at")} for c in filt(cs)]
    project_out = []
    for p in filt(ps):
        req = requests.get((p["tenant_id"], p.get("request_id")), {})
        project_out.append({**context(p), **{k: p.get(k) for k in ("request_id", "status", "service_stage", "service_stage_label", "stage_progress", "updated_at", "blocked_reason")}, "service": req.get("service", "")})
    request_out = [{**context(r), **{k: r.get(k) for k in ("request_id", "service", "status", "updated_at")}} for r in filt(rs)]
    lead_out = [(await _lead_out(r)).model_dump() for r in filt(ls)]
    review_out = [{**context(r), **{k: r.get(k) for k in ("review_id", "title", "kind", "status", "updated_at")}} for r in filt(reviews)]
    report_out = []
    visible = {}
    for pub in filt(pubs):
        visible[pub["publication_id"]] = await customer.publication_valid(pub)
    for r in filt(reports):
        matched = [p for p in pubs if p["tenant_id"] == r["tenant_id"] and p["report_id"] == r["report_id"]]
        pub = max(matched, key=lambda x: x.get("updated_at") or x.get("created_at") or "") if matched else None
        status = ("internal" if not r.get("is_client_safe") else "unpublished" if not pub else
                  "withdrawn" if pub["status"] == "withdrawn" else ("visible" if active_clients.get((r["tenant_id"], context(r)["client_id"]), False) else "access_inactive") if visible.get(pub["publication_id"]) else "invalid")
        report_out.append({**context(r), **{k: r.get(k) for k in ("report_id", "title", "version", "created_at", "measurement_id")},
                           "status": status, "updated_at": r.get("created_at", "")})
    # Missing report publications must still remain visible as anomalies.
    report_keys = {(r["tenant_id"], r["report_id"]) for r in reports}
    for pub in filt(pubs):
        if (pub["tenant_id"], pub["report_id"]) not in report_keys and pub["status"] == "published":
            report_out.append({**context(pub), "report_id": pub["report_id"], "title": "原报告缺失", "status": "invalid", "version": pub.get("report_version"), "created_at": pub.get("created_at"), "updated_at": pub.get("updated_at", "")})
    events = []
    def history(rows, field, source, id_field):
        for r in filt(rows):
            data = r.get("workflow", {}).get(field, []) if source == "request" else r.get(field, [])
            for e in data:
                events.append({**context(r), "source": source, "object_id": r[id_field], "at": e.get("at"),
                    "action": e.get("action", "未记录"), "role": e.get("role") or (e.get("by") if e.get("by") in ("HQ_TECHNICAL", "HQ_MANAGEMENT", "END_CUSTOMER", "DISTRIBUTOR_ADMIN") else "未记录"),
                    "note": e.get("note", "")})
    history(rs, "history", "request", "request_id")
    history(ls, "audit", "lead", "lead_id")
    history(reviews, "history", "review", "review_id")
    history(pubs, "history", "publication", "publication_id")
    for pub in filt(pubs):
        for field, action in (("published_at", "publish"), ("withdrawn_at", "withdraw")):
            if pub.get(field):
                events.append({**context(pub), "source": "publication", "object_id": pub["publication_id"],
                    "at": pub[field], "action": action, "role": "未记录", "note": "报告：" + pub["report_id"]})
    for e in filt(ops):
        events.append({**context(e), **{k: e.get(k) for k in ("at", "action", "role", "note")}, "source": "project", "object_id": e["project_id"]})
    counts = {"unassigned": sum(l["intake_status"] in ("new", "pending_assignment") for l in lead_out),
        "scoping": sum(r["status"] in ("submitted", "intake_review", "scoping") for r in request_out),
        "approval": sum(r["status"] == "scope_pending_approval" for r in request_out),
        "blocked": sum(p["status"] == "blocked" for p in project_out),
        "awaiting_customer": sum(r["status"] == "pending" for r in review_out),
        "awaiting_team": sum(r["status"] in ("submitted", "confirmed", "changes_requested") for r in review_out),
        "unpublished": sum(r["status"] == "unpublished" for r in report_out),
        "invalid": sum(r["status"] == "invalid" for r in report_out)}
    return {"scope": selected or "", "generated_at": now(), "counts": counts,
        "tenants": [{"tenant_id": t, "assignable": t in registered,
                     "clients": sum(c["tenant_id"] == t for c in cs), "projects": sum(p["tenant_id"] == t for p in ps)} for t in sorted(known)],
        "clients": client_out, "projects": project_out, "requests": request_out, "leads": lead_out,
        "reports": report_out, "reviews": review_out, "events": sorted(events, key=lambda e: e.get("at") or "", reverse=True),
        "limitations": ["总部角色是现有集成身份，不能据此认定逐员工操作人。", "业务处理记录仅覆盖已存储事件，不包含全部安全访问日志。", "报告生成、客户可见与项目验收是独立状态。"]}
