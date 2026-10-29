"""官网投递角色的最小权限边界（2026-10-28 新增）。

背景：`POST /leads` 原本只接受 `is_hq` 的密钥。官网表单的密钥必须存放在
wp-config.php（www-data 可读），若沿用 HQ_MANAGEMENT，一次 WordPress 插件
漏洞即可换到全租户读写。因此引入 `HQ_INTAKE`：能投递线索，但**不跨租户、
不能调用 require_hq 端点**。

本文件把这三条边界钉成断言，防止日后有人为了「图方便」把 HQ_INTAKE 加进
HQ_ROLES。
"""
from __future__ import annotations

import importlib

import pytest
from fastapi.testclient import TestClient

# 注意：HQ-INTAKE 租户只承载未分配线索，不含任何客户/项目数据。
AUTH_KEYS = (
    "HQ-INTAKE:sk-test-intake:HQ_INTAKE,"
    "DST-LEAD-A:sk-test-lead-a:DISTRIBUTOR_ADMIN,"
    "HQ-OPS:sk-test-lead-hq:HQ_MANAGEMENT"
)


@pytest.fixture()
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("GEO_DISTRIBUTOR_ENV", "test")
    monkeypatch.setenv("GEO_DISTRIBUTOR_DB", str(tmp_path / "intake-scope.db"))
    monkeypatch.setenv("GEO_DISTRIBUTOR_AUDIT_DB", str(tmp_path / "intake-scope-audit.db"))
    from api.auth import reset_registry_cache
    reset_registry_cache()
    from api import state
    state.init_repositories(str(tmp_path / "intake-scope.db"))
    # 隔离文件注册表，避免本机 config/api_keys.json 污染断言
    monkeypatch.setattr("api.auth.REGISTRY_FILE", tmp_path / "api_keys.json")
    app_mod = importlib.import_module("api.app")
    importlib.reload(app_mod)
    with TestClient(app_mod.app) as test_client:
        yield test_client
    reset_registry_cache()


def _payload(source_lead_id="scope-1"):
    return {
        "source": "website",
        "source_lead_id": source_lead_id,
        "idempotency_key": "website:" + source_lead_id,
        "name": "Scoped Contact",
        "company": "Scoped Co",
        "email": "scoped@example.com",
        "domain": "example.com",
        "type": "diagnostic",
        "message": "官网表单投递的最小权限验证。",
    }


def test_intake_role_can_post_lead(client):
    """HQ_INTAKE 必须能投递线索，否则官网表单形同虚设。"""
    response = client.post("/leads", json=_payload(), headers={"X-API-Key": "sk-test-intake"})
    assert response.status_code == 201, response.text
    assert response.json()["intake_status"] == "pending_assignment"
    assert response.json()["tenant_id"] == "HQ-INTAKE"


def test_intake_role_cannot_cross_tenant(client):
    """HQ_INTAKE 不得声明其他租户——这是它与 HQ_TECHNICAL 的关键差异。"""
    response = client.get(
        "/leads",
        params={"tenant_id": "DST-LEAD-A"},
        headers={"X-API-Key": "sk-test-intake"},
    )
    assert response.status_code == 403, response.text


def test_intake_role_cannot_use_hq_only_endpoints(client):
    """HQ_INTAKE 不能调用 require_hq 端点（如创建项目）。"""
    body = {
        "request_id": "REQ-X",
        "tenant_id": "DST-LEAD-A",
        "client_id": "CLI-X",
        "scope_id": "SCOPE-X",
    }
    response = client.post("/projects", json=body, headers={"X-API-Key": "sk-test-intake"})
    assert response.status_code == 403, response.text


def test_intake_role_is_not_hq_but_is_writable():
    """直接钉住角色集合：可写、不跨租户。"""
    from api.auth import HQ_ROLES, WRITE_ROLES

    assert "HQ_INTAKE" in WRITE_ROLES
    assert "HQ_INTAKE" not in HQ_ROLES
