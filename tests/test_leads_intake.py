"""Commercial V1 U2 — website lead intake, idempotency and tenant boundary tests."""
from __future__ import annotations

import importlib

import pytest
from fastapi.testclient import TestClient

AUTH_KEYS = (
    "DST-LEAD-A:sk-test-lead-a:DISTRIBUTOR_ADMIN,"
    "DST-LEAD-B:sk-test-lead-b:DISTRIBUTOR_USER,"
    "HQ-OPS:sk-test-lead-hq:HQ_MANAGEMENT"
)


@pytest.fixture()
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("GEO_DISTRIBUTOR_ENV", "test")
    monkeypatch.setenv("GEO_DISTRIBUTOR_DB", str(tmp_path / "lead-intake.db"))
    from api.auth import reset_registry_cache
    reset_registry_cache()
    from api import state
    state.init_repositories(str(tmp_path / "lead-intake.db"))
    # 测试隔离：本文件断言可分配租户的**精确集合**（env 密钥 + dev 内置）。
    # 必须把文件注册表（config/api_keys.json，本机可能存在 T-E2E-SMOKE 等
    # 本地开发租户）指到 tmp_path，否则共享配置会污染断言。
    monkeypatch.setattr("api.auth.REGISTRY_FILE", tmp_path / "api_keys.json")
    app_mod = importlib.import_module("api.app")
    importlib.reload(app_mod)
    with TestClient(app_mod.app) as test_client:
        yield test_client
    reset_registry_cache()


def _payload(source_lead_id="101"):
    return {
        "source": "website",
        "source_lead_id": source_lead_id,
        "idempotency_key": "website:" + source_lead_id,
        "name": "Example Contact",
        "company": "Example Co",
        "email": "lead@example.com",
        "domain": "example.com",
        "type": "diagnostic",
        "message": "Please diagnose AI visibility.",
        "created_at": "2026-10-09T08:00:00+08:00",
    }


def _headers(key="sk-test-lead-hq"):
    return {"X-API-Key": key}


def test_website_intake_is_hq_only_and_requires_stable_id(client):
    denied = client.post("/leads", json=_payload(), headers=_headers("sk-test-lead-a"))
    assert denied.status_code == 403
    missing_id = _payload("")
    missing_id["idempotency_key"] = ""
    invalid = client.post("/leads", json=missing_id, headers=_headers())
    assert invalid.status_code == 422
    accepted = client.post("/leads", json=_payload(), headers=_headers())
    assert accepted.status_code == 201, accepted.text
    assert accepted.json()["intake_status"] == "pending_assignment"


def test_retries_are_idempotent_and_do_not_reset_assignment(client):
    first = client.post("/leads", json=_payload(), headers=_headers())
    assert first.status_code == 201
    lead_id = first.json()["lead_id"]
    assigned = client.post(
        f"/leads/{lead_id}/assign",
        json={"tenant_id": "DST-LEAD-A", "create_client": False},
        headers=_headers(),
    )
    assert assigned.status_code == 200
    retry = client.post("/leads", json=_payload(), headers=_headers())
    assert retry.status_code == 200
    assert retry.json()["deduplicated"] is True
    assert retry.json()["intake_status"] == "assigned"
    assert retry.json()["tenant_id"] == "DST-LEAD-A"


def test_distributor_cannot_see_unassigned_or_other_tenant_leads(client):
    response = client.post("/leads", json=_payload(), headers=_headers())
    lead_id = response.json()["lead_id"]
    assert client.get("/leads", headers=_headers("sk-test-lead-a")).json() == []
    client.post(f"/leads/{lead_id}/assign", json={"tenant_id": "DST-LEAD-A"}, headers=_headers())
    assert len(client.get("/leads", headers=_headers("sk-test-lead-a")).json()) == 1
    assert client.get(f"/leads/{lead_id}", headers=_headers("sk-test-lead-b")).status_code == 404
    assert client.get("/leads?tenant_id=DST-LEAD-A", headers=_headers("sk-test-lead-b")).json() == []


def test_assignment_rejects_unregistered_distributor_tenant(client):
    response = client.post("/leads", json=_payload(), headers=_headers())
    lead_id = response.json()["lead_id"]
    bad = client.post(f"/leads/{lead_id}/assign", json={"tenant_id": "NOT-REGISTERED"}, headers=_headers())
    assert bad.status_code == 422


def test_hq_can_convert_assigned_lead_to_client_request_project(client):
    created = client.post("/leads", json=_payload("conversion-1"), headers=_headers())
    assert created.status_code == 201
    lead_id = created.json()["lead_id"]
    assigned = client.post(
        f"/leads/{lead_id}/assign",
        json={"tenant_id": "DST-LEAD-A", "create_client": True, "client_name": "Example Co"},
        headers=_headers(),
    )
    assert assigned.status_code == 200
    assert assigned.json()["client_id"]
    converted = client.post(
        f"/leads/{lead_id}/convert",
        json={"target_market": ["US"], "target_products": ["Example"], "business_question": "Visibility diagnostic"},
        headers=_headers(),
    )
    assert converted.status_code == 200, converted.text
    assert converted.json()["intake_status"] == "converted_project"
    assert converted.json()["request_id"]
    assert converted.json()["project_id"]
    repeated = client.post(
        f"/leads/{lead_id}/convert",
        json={"target_market": ["US"], "target_products": ["Example"], "business_question": "Visibility diagnostic"},
        headers=_headers(),
    )
    assert repeated.status_code == 200
    assert repeated.json()["project_id"] == converted.json()["project_id"]
    assert repeated.json()["deduplicated"] is True

def test_assignable_tenants_and_ui_proxy_are_scoped(client):
    hq_tenants = client.get("/leads/assignable-tenants", headers=_headers())
    assert hq_tenants.status_code == 200
    assert set(hq_tenants.json()["tenants"]) == {"DST-LEAD-A", "DST-LEAD-B", "DST-LOCAL-DEV"}
    denied = client.get("/leads/assignable-tenants", headers=_headers("sk-test-lead-a"))
    assert denied.status_code == 403

    login = client.post("/ui/session", json={"api_key": "sk-test-lead-hq"})
    assert login.status_code == 200 and login.json()["ok"] is True
    proxied = client.get("/ui/proxy/leads")
    assert proxied.status_code == 200, proxied.text
    assert isinstance(proxied.json(), list)
    assert "sk-test-lead-hq" not in proxied.text

def test_lead_and_assignment_survive_repository_reinitialization(client, monkeypatch, tmp_path):
    created = client.post("/leads", json=_payload(), headers=_headers())
    lead_id = created.json()["lead_id"]
    client.post(f"/leads/{lead_id}/assign", json={"tenant_id": "DST-LEAD-A"}, headers=_headers())
    from api import state
    state.init_repositories(str(tmp_path / "lead-intake.db"))
    reloaded = client.get(f"/leads/{lead_id}", headers=_headers())
    assert reloaded.status_code == 200
    assert reloaded.json()["intake_status"] == "assigned"
    assert reloaded.json()["assigned_tenant_id"] == "DST-LEAD-A"
