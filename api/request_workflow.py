"""Portal orchestration over canonical Requests/Projects, with atomic persistence.

No measurement/delivery calculations live here. SQLite BEGIN IMMEDIATE covers
the read/version check/request/project write as one transaction across workers.
Deterministic IDs enforce submission and approval uniqueness through primary keys.
"""
from __future__ import annotations
import copy
import hashlib
import json
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from fastapi import HTTPException
from . import state
from geo_distributor.models.request import ServiceRequest
from geo_distributor.models.project import Project

_lock = threading.RLock()

def now():
    return datetime.now(timezone.utc).isoformat()

def stable_id(prefix, value):
    return prefix + hashlib.sha256(value.encode()).hexdigest()[:24].upper()

class Unit:
    def __init__(self, conn=None):
        self.conn = conn
        self.pending = {}

    def get(self, table, ident):
        if self.conn:
            row = self.conn.execute(f"SELECT payload FROM {table} WHERE id=?", (ident,)).fetchone()
            return json.loads(row[0]) if row else None
        repo = getattr(state, {"requests":"request_repo", "projects":"project_repo", "clients":"client_repo"}[table])
        entity = repo._store.get(ident)
        return copy.deepcopy(entity.to_dict()) if entity else None

    def put(self, table, item):
        ident = item["request_id" if table == "requests" else "project_id"]
        if self.conn:
            self.conn.execute(f"INSERT INTO {table}(id,tenant_id,payload,updated_at) VALUES(?,?,?,?) "
                              "ON CONFLICT(id) DO UPDATE SET payload=excluded.payload,updated_at=excluded.updated_at",
                              (ident, item["tenant_id"], json.dumps(item, ensure_ascii=False), item["updated_at"]))
        else:
            self.pending[(table, ident)] = copy.deepcopy(item)

    def commit_memory(self):
        # Construct everything first; a conversion error cannot partially commit.
        entities = [(t, i, (ServiceRequest if t == "requests" else Project).from_dict(p))
                    for (t, i), p in self.pending.items()]
        for table, ident, entity in entities:
            repo = getattr(state, "request_repo" if table == "requests" else "project_repo")
            repo._store[ident] = entity
            repo._by_tenant.setdefault(entity.tenant_id, set()).add(ident)

@contextmanager
def transaction():
    if state.request_repo is None:
        raise HTTPException(503, "服务暂不可用，请稍后重试")
    with _lock:
        if state.persistence_backend == "sqlite":
            conn = state.request_repo._connect()
            try:
                conn.execute("BEGIN IMMEDIATE")
                yield Unit(conn)
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()
        else:
            unit = Unit()
            yield unit
            unit.commit_memory()

def visible(item, auth):
    if not item or (not auth.is_hq and item["tenant_id"] != auth.tenant_id):
        raise HTTPException(404, "记录不存在或无访问权限")
    return item

def event(item, auth, action, note=""):
    item["updated_at"] = now()
    wf = item.setdefault("workflow", {})
    wf["revision"] = wf.get("revision", 0) + 1
    wf.setdefault("history", []).append({"at":item["updated_at"], "actor":auth.user_id,
                                         "role":auth.role,"action":action,"note":note})

def revision(item, expected):
    if item.get("workflow", {}).get("revision", 0) != expected:
        raise HTTPException(409, "记录已更新，请刷新后再操作")

def create(body, auth, key):
    tenant = body.get("tenant_id") if auth.is_hq else auth.tenant_id
    tenant = tenant or auth.tenant_id
    if not auth.is_hq and body.get("tenant_id") not in (None, "", auth.tenant_id):
        raise HTTPException(403, "不能为其他渠道商提交需求")
    if not key or len(key) > 128:
        raise HTTPException(422, "请提供有效的 Idempotency-Key")
    fingerprint = hashlib.sha256(json.dumps(body, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    ident = stable_id("SR-", tenant + ":" + key)
    with transaction() as tx:
        old = tx.get("requests", ident)
        if old:
            if old.get("workflow", {}).get("fingerprint") != fingerprint:
                raise HTTPException(409, "此提交编号已用于其他内容，请核对原需求")
            return old
        client = tx.get("clients", body["client_id"])
        if not client or client["tenant_id"] != tenant:
            raise HTTPException(404, "客户不存在或无访问权限")
        if not client.get("is_active", True):
            raise HTTPException(409, "该客户已停用")
        context = {k:body[k] for k in ("market_scope", "target_market", "target_languages", "service_duration",
                                       "target_products", "business_question")}
        item = ServiceRequest(ident, tenant, body["client_id"]).to_dict()
        item.update(service=body["service"], status="submitted", business_context=context,
                    submitted_at=now(), idempotency_key=key,
                    workflow={"fingerprint":fingerprint,"revision":0,"history":[],"scope":None})
        event(item, auth, "submitted", "需求已提交，等待总部确认")
        tx.put("requests", item)
        return item

def change(ident, auth, action, body):
    with transaction() as tx:
        item = visible(tx.get("requests", ident), auth)
        wf = item.setdefault("workflow", {})
        if action == "approve" and item["status"] == "approved":
            # Retry of the exact approved revision is harmless; altered approval is not.
            if body["revision"] not in (wf.get("approved_revision"), wf.get("revision")):
                raise HTTPException(409, "记录已更新，请刷新后再操作")
            return item
        revision(item, body["revision"])
        if item["status"] in ("approved", "rejected", "cancelled", "delivered", "accepted"):
            raise HTTPException(409, "该需求已结束受理；范围变更请新建需求")
        note = body.get("note", "").strip()
        if action == "clarification":
            item["status"] = "clarification_required"
            wf["scope"] = None
            item["scope_id"] = None
            item["clarification_request"] = {"request_id":ident,"missing_fields":[],"questions":[note],"created_at":now()}
        elif action == "supplement":
            if item["status"] != "clarification_required":
                raise HTTPException(409, "当前无需补充资料")
            wf["supplement"] = note
            wf["scope"] = None  # Any new information requires renewed scope review.
            item["scope_id"] = None
            item["status"] = "intake_review"
            item["clarification_request"] = None
        elif action == "scope":
            if item["status"] == "clarification_required":
                raise HTTPException(409, "请先等待渠道商补充资料")
            scope = body["scope"]
            scope["scope_id"] = stable_id("SCOPE-", ident + ":" + str(wf.get("revision", 0)))
            scope.update(request_id=ident, tenant_id=item["tenant_id"], approved_by=None, approved_at=None,
                         version=wf.get("scope_version", 0) + 1)
            wf["scope_version"] = scope["version"]
            wf["scope"] = scope
            item["scope_id"] = scope["scope_id"]
            item["status"] = "scope_pending_approval"
        elif action == "approve":
            if item["status"] != "scope_pending_approval" or not wf.get("scope"):
                raise HTTPException(409, "请先拟定并保存服务范围")
            wf["approved_revision"] = body["revision"]
            wf["scope"].update(approved_by=auth.user_id, approved_at=now())
            project = Project(stable_id("PRJ-", ident), ident, item["tenant_id"], item["client_id"], item["scope_id"])
            # PK(project_id) + this transaction enforce one project per portal request.
            if tx.get("projects", project.project_id):
                raise HTTPException(409, "项目已存在，请刷新核对")
            tx.put("projects", project.to_dict())
            item.update(project_id=project.project_id, status="approved", approved_at=now())
        elif action == "reject":
            item["status"] = "rejected"
            wf["rejection_reason"] = note
        event(item, auth, action, note)
        tx.put("requests", item)
        return item
