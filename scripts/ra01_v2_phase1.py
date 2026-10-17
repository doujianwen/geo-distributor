#!/usr/bin/env python3
"""RA-01 V2 restart durability test - phase 1 (pre-restart write).

Creates uniquely identifiable test records via the real API, saves evidence.
Never prints API keys. Run from repo root:
    .venv/Scripts/python.exe scripts/ra01_v2_phase1.py
"""
import json
import sqlite3
import urllib.request
import urllib.error
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
EVID = Path(r"E:\一人公司\FDE\渠道商演示环境就绪度核验\2026-10-17\REMAINING_BLOCKERS_CLOSURE_20261017_V2\evidence")
DB = REPO / "data" / "geo_distributor.db"
BASE = "http://127.0.0.1:8765"
MARK = "RA01-V2-DURABILITY-20261017"


def load_hq_key() -> str:
    reg = json.loads((REPO / "config" / "api_keys.json").read_text(encoding="utf-8"))
    items = reg if isinstance(reg, list) else reg.get("keys", reg)
    for k, v in (items.items() if isinstance(items, dict) else
                 [(e.get("api_key") or e.get("key"), e) for e in items]):
        if v.get("role") == "HQ_TECHNICAL":
            return k
    raise SystemExit("HQ_TECHNICAL key not found")


def api(method: str, path: str, key: str, body: dict | None = None):
    req = urllib.request.Request(BASE + path, method=method)
    req.add_header("X-API-Key", key)
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, data=data, timeout=30) as r:
        return r.status, json.loads(r.read().decode())


def db_counts() -> dict:
    c = sqlite3.connect(DB)
    out = {}
    for t in ["clients", "projects", "requests", "reports_projection",
              "measurements_projection"]:
        out[t] = c.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
    out["_report_ids"] = [r[0] for r in c.execute(
        "SELECT id FROM reports_projection ORDER BY updated_at").fetchall()]
    c.close()
    return out


def main():
    key = load_hq_key()
    pre = db_counts()
    (EVID / "ra01_v2_pre_state.json").write_text(
        json.dumps(pre, indent=2, ensure_ascii=False), encoding="utf-8")
    print("PRE counts:", {k: v for k, v in pre.items() if not k.startswith("_")})
    print("PRE report_ids:", pre["_report_ids"])

    s, client = api("POST", "/clients", key, {
        "name": MARK, "industry": "demo",
        "website": "http://ra01-v2.test", "contact_email": "ra01v2@test.local"})
    print("client:", s, client["client_id"])
    s, project = api("POST", "/projects", key, {
        "tenant_id": "T-E2E-SMOKE",
        "client_id": client["client_id"],
        "service": "visibility_audit",
        "business_question": "V2 independent restart durability test"})
    print("project:", s, project["project_id"])
    s, meas = api("POST", "/measurements", key, {
        "project_id": project["project_id"], "tenant_id": "T-E2E-SMOKE",
        "adapter": "geo-collector-db", "observation_limit": 10})
    print("measurement:", s, json.dumps(meas, ensure_ascii=False)[:200])
    measurement_id = meas.get("measurement_id") or meas.get("metrics", {}).get("measurement_id")

    s, dlv = api("POST", f"/projects/{project['project_id']}/deliver", key,
                 {"scope_version": 1})
    print("deliver:", s, json.dumps(dlv, ensure_ascii=False)[:200])
    report_id = dlv["report_id"]

    s, report = api("GET", f"/reports/{report_id}", key)
    (EVID / "ra01_v2_report_before_restart.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print("report readback:", s, report_id, "| title:", report.get("title"))

    ids = {"client_id": client["client_id"], "project_id": project["project_id"],
           "measurement_id": measurement_id, "report_id": report_id,
           "delivery_id": dlv.get("delivery_id")}
    (EVID / "ra01_v2_ids.json").write_text(
        json.dumps(ids, indent=2), encoding="utf-8")
    print("IDS:", json.dumps(ids))


if __name__ == "__main__":
    main()
