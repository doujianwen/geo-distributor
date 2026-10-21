"""Customer publication/review projections over canonical clients/projects/reports."""
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import threading

from fastapi import HTTPException
from . import state
from .geo_view import load_measurements, geo_view, report_projection
from geo_distributor.repositories.base import PermissionError as RepoPermissionError

_lock = threading.RLock()


def now():
    return datetime.now(timezone.utc).isoformat()


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


async def project_for(project_id, tenant_id, client_id=None):
    if state.project_repo is None:
        raise HTTPException(503, "服务暂不可用")
    try:
        p = await state.project_repo.find_by_id(project_id, tenant_id=tenant_id)
    except RepoPermissionError:
        p = None
    if not p or (client_id and p.client_id != client_id):
        raise HTTPException(404, "项目不存在或无访问权限")
    return p


async def bound_client(auth):
    from .routers.clients import _load_client
    c = await _load_client(auth.client_id, auth.tenant_id)
    if not c or not c.is_active:
        raise HTTPException(403, "企业访问权限已停用")
    return c


@contextmanager
def transaction(table, ident):
    """Atomic row/revision/replay change, including multi-process SQLite callers."""
    repo = state.customer_review_repo if table == "client_reviews" else state.customer_publication_repo
    if repo is None:
        raise HTTPException(503, "服务暂不可用")
    with _lock:
        if state.persistence_backend == "sqlite":
            conn = repo._connect()
            try:
                conn.execute("BEGIN IMMEDIATE")
                found = conn.execute(f"SELECT payload FROM {table} WHERE id=?", (ident,)).fetchone()
                box = {"row": json.loads(found[0]) if found else None, "save": None, "conn": conn}
                yield box
                if box["save"] is not None:
                    item = box["save"]
                    conn.execute(f"INSERT INTO {table}(id,tenant_id,project_id,payload,updated_at) VALUES(?,?,?,?,?) "
                                 "ON CONFLICT(id) DO UPDATE SET payload=excluded.payload,updated_at=excluded.updated_at",
                                 (ident, item["tenant_id"], item["project_id"], json.dumps(item, ensure_ascii=False), now()))
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()
        else:
            box = {"row": deepcopy(repo._rows.get(ident)), "save": None, "conn": None}
            yield box
            if box["save"] is not None:
                repo._rows[ident] = deepcopy(box["save"])


async def report_source(report_id, tenant_id, client_id=None):
    if state.report_service is None:
        raise HTTPException(503, "报告服务暂不可用")
    r = await state.report_service.get_report(report_id, tenant_id=tenant_id)
    if not r or r.get("is_client_safe") is not True:
        raise HTTPException(404, "报告不存在或无访问权限")
    p = await project_for(r["project_id"], tenant_id, client_id)
    return r, p


async def publication_snapshot(pub):
    pub = deepcopy(pub)
    if pub.get("status") != "published":
        return None
    try:
        r, p = await report_source(pub["report_id"], pub["tenant_id"], pub["client_id"])
    except HTTPException as e:
        if e.status_code == 404:
            return None
        raise
    r = deepcopy(r)
    if p.project_id != pub["project_id"] or digest(r) != pub["report_sha256"] or r.get("version") != pub["report_version"]:
        return None
    saved = await load_measurements(pub["project_id"], pub["tenant_id"])
    m = next((m for m in saved if m.get("measurement_id") == pub.get("measurement_id")), None)
    m = deepcopy(m)
    if m is None or digest(m) != pub.get("measurement_sha256") or pub.get("qa_passed") is not True:
        return None
    return {"publication": pub, "report": r, "measurement": m}


async def publication_valid(pub):
    return await publication_snapshot(pub) is not None


async def published_snapshots(tenant_id, client_id=None, project_id=None):
    if state.customer_publication_repo is None:
        raise HTTPException(503, "发布服务暂不可用")
    rows = await state.customer_publication_repo.list_by_tenant(tenant_id)
    result = []
    for pub in rows:
        if (client_id and pub["client_id"] != client_id) or (project_id and pub["project_id"] != project_id):
            continue
        snapshot = await publication_snapshot(pub)
        if snapshot is not None:
            result.append(snapshot)
    return result


async def publications(tenant_id, client_id=None, project_id=None):
    if state.customer_publication_repo is None:
        raise HTTPException(503, "发布服务暂不可用")
    rows = await state.customer_publication_repo.list_by_tenant(tenant_id)
    return [r for r in rows if (not client_id or r["client_id"] == client_id)
            and (not project_id or r["project_id"] == project_id) and await publication_valid(r)]


async def publish(report_id, auth):
    if not auth.is_hq:
        raise HTTPException(403, "仅总部可发布技术结果")
    r, p = await report_source(report_id, auth.tenant_id)
    from .routers.clients import _load_client
    c = await _load_client(p.client_id, auth.tenant_id)
    if not c or not c.is_active:
        raise HTTPException(409, "客户尚未启用")
    records = await load_measurements(p.project_id, auth.tenant_id)
    m = next((m for m in records if m.get("measurement_id") == r.get("measurement_id")), None)
    if not m:
        raise HTTPException(409, "报告缺少可核对的关联测量，请总部重新形成交付报告后发布")
    qa = await state.delivery_service._run_qa(r, m.get("observations") or [], r.get("content", {}).get("key_findings") or [])
    if not qa.passed:
        raise HTTPException(409, "报告未通过现有质量检查，不能向客户发布")
    ident = "PUB-" + digest([auth.tenant_id, report_id])[:24].upper()
    with transaction("client_publications", ident) as tx:
        old = tx["row"]
        if old:
            if old["status"] == "published" and old["report_sha256"] == digest(r) and old["measurement_sha256"] == digest(m):
                return publication_dto(old)
            raise HTTPException(409, "该版本已撤回或内容变更，请形成新的交付报告再发布")
        item = {"publication_id": ident, "tenant_id": auth.tenant_id, "client_id": p.client_id,
                "project_id": p.project_id, "report_id": report_id, "report_version": r.get("version"),
                "report_sha256": digest(r), "measurement_id": m["measurement_id"], "measurement_sha256": digest(m),
                "qa_passed": True, "published_at": now(), "published_by": auth.user_id, "revision": 1, "status": "published"}
        tx["save"] = item
        return publication_dto(item)


def publication_dto(item, valid=None):
    keys = ("publication_id", "project_id", "report_id", "report_version", "published_at", "revision", "status")
    result = {k: item[k] for k in keys}
    if valid is not None:
        result["currently_visible"] = valid
    return result


async def withdraw_publication(ident, revision, auth):
    if not auth.is_hq:
        raise HTTPException(403, "仅总部可撤回技术结果")
    with transaction("client_publications", ident) as tx:
        r = tx["row"]
        if not r or r["tenant_id"] != auth.tenant_id:
            raise HTTPException(404, "发布记录不存在")
        if r["revision"] != revision or r["status"] != "published":
            raise HTTPException(409, "记录已更新，请刷新")
        r.update(status="withdrawn", revision=revision + 1, withdrawn_at=now(), withdrawn_by=auth.user_id)
        tx["save"] = r
        return publication_dto(r)


async def customer_reports(auth, project_id=None):
    if project_id:
        await project_for(project_id, auth.tenant_id, auth.client_id)
    snapshots = await published_snapshots(auth.tenant_id, auth.client_id, project_id)
    result = []
    for snapshot in snapshots:
        projected = await report_projection(snapshot["report"], source_measurement=snapshot["measurement"])
        result.append({k: projected.get(k) for k in ("report_id", "project_id", "title", "version", "created_at", "key_findings", "limitations", "next_steps", "data_quality", "geo_snapshot", "is_demo")})
    return sorted(result, key=lambda r: r["created_at"], reverse=True)


async def customer_geo(auth, project_id):
    await project_for(project_id, auth.tenant_id, auth.client_id)
    snapshots = await published_snapshots(auth.tenant_id, auth.client_id, project_id)
    unique = {s["measurement"]["measurement_id"]: s["measurement"] for s in snapshots}
    g = await geo_view(project_id, auth.tenant_id, source_records=list(unique.values()))
    return g


def review_dto(item):
    keys = ("review_id", "project_id", "kind", "title", "instructions", "report_id", "status", "revision", "created_at", "updated_at", "response", "resolution")
    out = {k: deepcopy(item.get(k)) for k in keys}
    out["history"] = [{k: e.get(k) for k in ("at", "action", "note", "by")} for e in item.get("history", [])]
    return out


def append_event(item, action, note, auth):
    item["revision"] += 1
    item["updated_at"] = now()
    item.setdefault("history", []).append({"at": item["updated_at"], "action": action, "note": note,
                                            "by": "客户" if auth.role == "END_CUSTOMER" else "服务团队", "actor": auth.user_id, "role": auth.role})


async def report_is_visible(report_id, auth, project_id, client_id):
    pubs = await publications(auth.tenant_id, client_id, project_id)
    return any(p["report_id"] == report_id for p in pubs)


async def visible_review(item, auth):
    if not item or item["tenant_id"] != auth.tenant_id or item["client_id"] != auth.client_id:
        raise HTTPException(404, "待办不存在或无访问权限")
    await project_for(item["project_id"], auth.tenant_id, auth.client_id)
    if item.get("report_id") and not await report_is_visible(item["report_id"], auth, item["project_id"], auth.client_id):
        raise HTTPException(404, "关联结果已撤回或不可用")
    return item


async def list_reviews(auth, project_id=None, customer=False):
    if project_id:
        await project_for(project_id, auth.tenant_id, auth.client_id if customer else None)
    rows = await state.customer_review_repo.list_by_tenant(auth.tenant_id)
    result = []
    for r in rows:
        if project_id and r["project_id"] != project_id:
            continue
        if customer:
            if r["client_id"] != auth.client_id:
                continue
            try:
                await visible_review(r, auth)
            except HTTPException as e:
                if e.status_code == 404:
                    continue
                raise
        result.append(review_dto(r))
    return sorted(result, key=lambda r: r["updated_at"], reverse=True)


def replay(item, key, fingerprint):
    old = item.get("replays", {}).get(key) if item else None
    if old:
        if old["fingerprint"] != fingerprint:
            raise HTTPException(409, "此提交编号已用于其他内容")
        return deepcopy(old["result"])


def save_replay(item, key, fingerprint):
    result = review_dto(item)
    item.setdefault("replays", {})[key] = {"fingerprint": fingerprint, "result": deepcopy(result)}
    return result


async def create_review(body, key, auth):
    if auth.role not in ("DISTRIBUTOR_ADMIN", "HQ_TECHNICAL", "HQ_MANAGEMENT"):
        raise HTTPException(403, "当前角色不能发布客户待办")
    p = await project_for(body["project_id"], auth.tenant_id)
    if body.get("report_id") and not await report_is_visible(body["report_id"], auth, p.project_id, p.client_id):
        raise HTTPException(409, "关联报告尚未向该客户发布")
    ident = "CRV-" + digest([auth.tenant_id, key])[:24].upper()
    fingerprint = digest(body)
    with transaction("client_reviews", ident) as tx:
        old = tx["row"]
        if old:
            if old["create_fingerprint"] != fingerprint:
                raise HTTPException(409, "此发布编号已用于其他内容")
            return review_dto(old)
        item = {**body, "review_id": ident, "tenant_id": auth.tenant_id, "client_id": p.client_id,
                "status": "pending", "revision": 0, "created_at": now(), "response": None, "resolution": "",
                "create_fingerprint": fingerprint, "history": [], "replays": {}}
        append_event(item, "published", body["instructions"], auth)
        tx["save"] = item
        return review_dto(item)


async def respond_review(ident, body, key, auth):
    initial = await state.customer_review_repo.get(ident, tenant_id=auth.tenant_id)
    await visible_review(initial, auth)
    fingerprint = digest(body)
    with transaction("client_reviews", ident) as tx:
        r = tx["row"]
        if not r or r["tenant_id"] != auth.tenant_id or r["client_id"] != auth.client_id:
            raise HTTPException(404, "待办不存在")
        check_response_references(tx, r)
        replay_key = auth.user_id + ":" + key
        old = replay(r, replay_key, fingerprint)
        if old is not None:
            return old
        if r["revision"] != body["revision"] or r["status"] != "pending":
            raise HTTPException(409, "待办已更新或已处理，请刷新")
        action = body["action"]
        if (r["kind"] == "material_request" and action != "submit") or (r["kind"] != "material_request" and action not in ("confirm", "request_changes")):
            raise HTTPException(422, "该待办不支持此答复")
        r["response"] = {"action": action, "note": body["note"], "at": now()}
        r["status"] = {"submit": "submitted", "confirm": "confirmed", "request_changes": "changes_requested"}[action]
        append_event(r, action, body["note"], auth)
        result = save_replay(r, replay_key, fingerprint)
        tx["save"] = r
        return result


def check_response_references(tx, review):
    """Recheck publication/client/project inside the same writer transaction.

    A revoke that wins the lock must prevent a later customer response, even
    when it occurred after the request's initial asynchronous authorization.
    """
    conn = tx["conn"]
    def get(table, ident):
        if conn is not None:
            row = conn.execute(f"SELECT payload FROM {table} WHERE id=?", (ident,)).fetchone()
            return json.loads(row[0]) if row else None
        if table in ("clients", "projects"):
            repo = state.client_repo if table == "clients" else state.project_repo
            obj = repo._store.get(ident)
            return obj.to_dict() if obj else None
        if table == "reports_projection":
            return state.report_service._reports.get(ident)
        if table == "measurements_projection":
            return next((m for m in state._measurement_results.get(review["project_id"], []) if m.get("measurement_id") == ident), None)
        return state.customer_publication_repo._rows.get(ident)
    c = get("clients", review["client_id"])
    p = get("projects", review["project_id"])
    if not c or not c.get("is_active") or c["tenant_id"] != review["tenant_id"] or not p or (p["tenant_id"], p["client_id"]) != (review["tenant_id"], review["client_id"]):
        raise HTTPException(409, "客户或项目范围已变更，请刷新")
    if review.get("report_id"):
        pub = get("client_publications", "PUB-" + digest([review["tenant_id"], review["report_id"]])[:24].upper())
        report = get("reports_projection", review["report_id"])
        measurement = get("measurements_projection", pub.get("measurement_id")) if pub else None
        if (not pub or pub.get("status") != "published" or not report or not measurement
            or (pub["tenant_id"], pub["client_id"], pub["project_id"]) != (review["tenant_id"], review["client_id"], review["project_id"])
            or pub.get("report_sha256") != digest(report) or pub.get("measurement_sha256") != digest(measurement)):
            raise HTTPException(409, "关联结果已撤回或变更，请刷新")


async def process_review(ident, body, key, auth):
    if auth.role not in ("DISTRIBUTOR_ADMIN", "HQ_TECHNICAL", "HQ_MANAGEMENT"):
        raise HTTPException(403, "当前角色不能处理客户待办")
    initial = await state.customer_review_repo.get(ident, tenant_id=auth.tenant_id)
    if not initial:
        raise HTTPException(404, "待办不存在")
    await project_for(initial["project_id"], auth.tenant_id)
    with transaction("client_reviews", ident) as tx:
        r = tx["row"]
        if not r or r["tenant_id"] != auth.tenant_id:
            raise HTTPException(404, "待办不存在")
        fingerprint = digest(body)
        old = replay(r, auth.user_id + ":" + key, fingerprint)
        if old is not None:
            return old
        if r["revision"] != body["revision"] or r["status"] in ("closed", "withdrawn"):
            raise HTTPException(409, "待办已更新或结束")
        action = body["action"]
        if action != "withdraw" and r["status"] == "pending":
            raise HTTPException(409, "请等待客户答复，或撤回本项待办")
        r["status"] = {"close": "closed", "reopen": "pending", "withdraw": "withdrawn"}[action]
        r["resolution"] = body["note"]
        if action == "reopen":
            r["instructions"] = body["note"]
            r["response"] = None
        append_event(r, action, body["note"], auth)
        result = save_replay(r, auth.user_id + ":" + key, fingerprint)
        tx["save"] = r
        return result
