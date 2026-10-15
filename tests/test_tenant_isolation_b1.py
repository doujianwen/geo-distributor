"""B-1 Tenant Isolation 真实跨租户测试（RED-GATE）。

目标：证明「Tenant A 拥有的资源，Tenant B 用同一个resource ID 无法读取 / 修改 / 删除」。

设计原则（针对既有 B-3 假门禁的教训）：
- ❌ 禁止 `if result: assert False` 这类条件式断言
- ✅ 一律硬断言：状态码明确属于 {403, 404}，或实体明确为 None
- ✅ 真实走 HTTP（TestClient），不绕过 API 层直接调 repository
- ✅ 每个用例都先断言「攻击确实打到了真实存在的资源」（前置断言），
  否则「拿到 404」可能只是因为资源本来就不存在，测试会变成自欺

运行：
    pytest tests/test_tenant_isolation_b1.py -v
"""

from __future__ import annotations

import importlib

import pytest
from fastapi.testclient import TestClient

TENANT_A = "DST-ATTACK-A"
TENANT_B = "DST-ATTACK-B"

# B-2 起所有端点需认证：每个 tenant 一个密钥。
# B-1 测试的断言逻辑（跨租户拒绝）完全不变，只是补上了合法的认证凭证。
KEY_A = "sk-b1-key-tenant-a"
KEY_B = "sk-b1-key-tenant-b"
_KEYS = f"{TENANT_A}:{KEY_A}:DISTRIBUTOR_ADMIN,{TENANT_B}:{KEY_B}:DISTRIBUTOR_ADMIN"


def _h(tenant: str, key: str | None = None) -> dict:
    """构造带认证的请求头。"""
    k = key or (KEY_A if tenant == TENANT_A else KEY_B)
    return {"X-API-Key": k, "X-Tenant-ID": tenant}

# 明确判定为「安全」的状态码。
#400 = 缺少 X-Tenant-ID（fail closed，tenant context 缺失即拒绝）
#   403 = 权限拒绝
#   404 = 资源不存在或租户不符（统一为不可见，避免暴露资源存在性）
SAFE_STATUS = {400, 403, 404}


@pytest.fixture()
def client():
    """每个用例独立 app 实例 + 内存仓储，避免跨用例串数据。"""
    from api import state

    import os

    os.environ["GEO_DISTRIBUTOR_ENV"] = "test"
    os.environ["GEO_DISTRIBUTOR_API_KEYS"] = _KEYS
    # auth用配置指纹缓存，环境变量变化即自动重载；显式 reset 保证边界干净
    importlib.import_module("api.auth").reset_registry_cache()

    app_mod = importlib.import_module("api.app")
    importlib.reload(app_mod)
    state.init_repositories(None)  # 内存模式，测试后不留痕
    with TestClient(app_mod.app) as c:
        yield c


def _create_project_as(client: TestClient, tenant: str) -> str:
    """以指定 tenant 创建 project，返回 project_id。前置断言确保创建成功。"""
    r = client.post(
        "/projects",
        json={
            "tenant_id": tenant,
            "client_id": f"CLI-{tenant}",
            "service": "visibility_audit",
        },
        headers=_h(tenant),
    )
    assert r.status_code == 201, f"前置失败：{tenant} 创建 project 未成功 -> {r.status_code} {r.text}"
    pid = r.json()["project_id"]
    assert r.json()["tenant_id"] == tenant, "前置失败：创建返回的 tenant_id 不符"
    return pid


def _assert_no_leak(response, tenant_a_id: str, label: str) -> None:
    """核心断言：响应中不得含 Tenant A 的任何资源内容。"""
    # 1) 状态码必须明确拒绝
    assert response.status_code in SAFE_STATUS, (
        f"{label}: 期望 {sorted(SAFE_STATUS)}，实际 {response.status_code}；"
        f"响应体={response.text[:300]}"
    )
    # 2) 响应体不得出现 Tenant A 的资源标识
    body = response.text
    assert tenant_a_id not in body, f"{label}: 响应体泄漏了 Tenant A 的 project_id={tenant_a_id}"
    # 3) 不得出现 Tenant A 的身份标识
    assert TENANT_A not in body, f"{label}: 响应体泄漏了 Tenant A 标识"


# ------------------------------------------------------------------
# 2A — Projects
# ------------------------------------------------------------------

class TestProjectsCrossTenant:
    def test_TENANT_B_cannot_read_TENANT_A_project(self, client):
        pid = _create_project_as(client, TENANT_A)

        r = client.get(f"/projects/{pid}", headers=_h(TENANT_B))
        _assert_no_leak(r, pid, "GET /projects/{id}")

    def test_TENANT_B_cannot_read_TENANT_A_project_without_header(self, client):
        """完全不带 X-Tenant-ID → 必须 fail closed，不能退化成无租户查询。"""
        pid = _create_project_as(client, TENANT_A)

        r = client.get(f"/projects/{pid}", headers={"X-API-Key": KEY_B})
        _assert_no_leak(r, pid, "GET /projects/{id} (no header)")

    def test_TENANT_B_cannot_delete_TENANT_A_project(self, client):
        pid = _create_project_as(client, TENANT_A)

        r = client.delete(f"/projects/{pid}", headers=_h(TENANT_B))
        _assert_no_leak(r, pid, "DELETE /projects/{id}")

        # 硬断言：Tenant A 的资源必须仍然存在（未被越权删除）
        owner_view = client.get(f"/projects/{pid}", headers=_h(TENANT_A))
        assert owner_view.status_code == 200, (
            f"越权删除破坏了 Tenant A 的资源：{owner_view.status_code}"
        )

    def test_TENANT_B_cannot_advance_TENANT_A_stage(self, client):
        pid = _create_project_as(client, TENANT_A)

        r = client.post(f"/projects/{pid}/stage", json={}, headers=_h(TENANT_B))
        _assert_no_leak(r, pid, "POST /projects/{id}/stage")

    def test_TENANT_B_cannot_complete_TENANT_A_stage(self, client):
        pid = _create_project_as(client, TENANT_A)

        r = client.post(f"/projects/{pid}/stage/complete", headers=_h(TENANT_B))
        _assert_no_leak(r, pid, "POST /projects/{id}/stage/complete")

    def test_TENANT_B_cannot_read_TENANT_A_stage(self, client):
        pid = _create_project_as(client, TENANT_A)

        r = client.get(f"/projects/{pid}/stage", headers=_h(TENANT_B))
        _assert_no_leak(r, pid, "GET /projects/{id}/stage")

    def test_TENANT_B_cannot_start_TENANT_A_project(self, client):
        """start 端点此前完全不校验 tenant。"""
        pid = _create_project_as(client, TENANT_A)

        r = client.post(f"/projects/{pid}/start", headers=_h(TENANT_B))
        _assert_no_leak(r, pid, "POST /projects/{id}/start")

    def test_TENANT_B_list_excludes_TENANT_A_projects(self, client):
        pid = _create_project_as(client, TENANT_A)

        r = client.get("/projects", headers=_h(TENANT_B))
        assert r.status_code == 200
        ids = [p["project_id"] for p in r.json()]
        assert pid not in ids, f"Tenant B 的列表泄漏了 Tenant A 的 project: {ids}"
        assert all(p["tenant_id"] == TENANT_B for p in r.json()), "列表含非 Tenant B 的记录"

    def test_TENANT_B_list_without_tenant_header_excludes_A(self, client):
        """B-2 契约：不声明 tenant 时回落到密钥 tenant（B），
        列表中不得出现 A 的任何项目。"""
        pid_a = _create_project_as(client, TENANT_A)

        r = client.get("/projects", headers={"X-API-Key": KEY_B})
        assert r.status_code == 200, f"应回落到密钥 tenant，实际 {r.status_code} {r.text[:150]}"
        ids = [p["project_id"] for p in r.json()]
        assert pid_a not in ids, f"回落后仍泄漏 Tenant A 的项目：{ids}"
        assert all(p["tenant_id"] == TENANT_B for p in r.json()), "列表含非 Tenant B 的记录"
        # 400/403/404 均视为 fail closed

    def test_TENANT_A_can_still_operate_own_project(self, client):
        """反向门禁：修复后 Tenant A 必须仍能正常操作自己的资源。"""
        pid = _create_project_as(client, TENANT_A)

        assert client.get(f"/projects/{pid}", headers=_h(TENANT_A)).status_code == 200
        assert client.get(f"/projects/{pid}/stage", headers=_h(TENANT_A)).status_code == 200
        assert client.post(
            f"/projects/{pid}/stage", json={}, headers=_h(TENANT_A)
        ).status_code == 200
        assert client.delete(f"/projects/{pid}", headers=_h(TENANT_A)).status_code == 204


# ------------------------------------------------------------------
# 2B — Clients
# ------------------------------------------------------------------

class TestClientsCrossTenant:
    def _create_client_as(self, client: TestClient, tenant: str) -> str:
        r = client.post(
            "/clients",
            json={"tenant_id": tenant, "name": f"Client of {tenant}"},
            headers=_h(tenant),
        )
        assert r.status_code == 201, f"前置失败：{r.status_code} {r.text}"
        return r.json()["client_id"]

    def test_TENANT_B_cannot_read_TENANT_A_client(self, client):
        cid = self._create_client_as(client, TENANT_A)

        r = client.get(f"/clients/{cid}", headers=_h(TENANT_B))
        assert r.status_code in SAFE_STATUS, f"实际 {r.status_code}；body={r.text[:200]}"
        assert cid not in r.text and TENANT_A not in r.text

    def test_TENANT_B_cannot_delete_TENANT_A_client(self, client):
        cid = self._create_client_as(client, TENANT_A)

        r = client.delete(f"/clients/{cid}", headers=_h(TENANT_B))
        assert r.status_code in SAFE_STATUS, f"实际 {r.status_code}"

        owner = client.get(f"/clients/{cid}", headers=_h(TENANT_A))
        assert owner.status_code == 200, "越权删除破坏了 Tenant A 的 client"

    def test_TENANT_B_client_list_excludes_TENANT_A(self, client):
        cid = self._create_client_as(client, TENANT_A)

        r = client.get("/clients", headers=_h(TENANT_B))
        assert r.status_code == 200
        assert cid not in [c["client_id"] for c in r.json()]

    def test_clients_list_without_tenant_header_falls_back_to_key(self, client):
        """B-2 契约：不声明 tenant 时使用密钥绑定值，而非拒绝。"""
        self._create_client_as(client, TENANT_A)

        r = client.get("/clients", headers={"X-API-Key": KEY_B})
        assert r.status_code == 200, f"应回落到密钥 tenant，实际 {r.status_code} {r.text[:150]}"
        assert r.json() == [], f"回落后只应看到自己 tenant 的数据，实际 {r.json()}"


# ------------------------------------------------------------------
# 2C — Measurements
# ------------------------------------------------------------------

class TestMeasurementsCrossTenant:
    def test_TENANT_B_cannot_read_TENANT_A_measurements(self, client):
        pid = _create_project_as(client, TENANT_A)

        r = client.get(f"/measurements/{pid}", headers=_h(TENANT_B))
        assert r.status_code in SAFE_STATUS, f"实际 {r.status_code}；body={r.text[:200]}"
        assert TENANT_A not in r.text

    def test_TENANT_B_cannot_read_measurements_without_header(self, client):
        pid = _create_project_as(client, TENANT_A)

        r = client.get(f"/measurements/{pid}", headers={"X-API-Key": KEY_B})
        assert r.status_code in SAFE_STATUS, f"实际 {r.status_code}"

    def test_TENANT_B_cannot_create_measurement_under_TENANT_A_project(self, client):
        """body.tenant_id 声明 B，但 project_id属于 A → 必须拒绝。"""
        pid = _create_project_as(client, TENANT_A)

        r = client.post(
            "/measurements",
            json={
                "project_id": pid,
                "tenant_id": TENANT_B,   # 伪造：自称 B
                "engine": "chatgpt",
                "prompt": "test",
            },
            headers=_h(TENANT_B),
        )
        assert r.status_code in SAFE_STATUS, (
            f"Tenant B 竟能在 Tenant A 的 project 下建measurement：{r.status_code} {r.text[:200]}"
        )

    def test_measurements_missing_header_rejected(self, client):
        pid = _create_project_as(client, TENANT_A)

        r = client.get(f"/measurements/{pid}", headers={"X-API-Key": KEY_B})
        assert r.status_code in SAFE_STATUS, f"实际 {r.status_code}"


# ------------------------------------------------------------------
# 2D — Reports
# ------------------------------------------------------------------

class TestReportsCrossTenant:
    def test_TENANT_B_cannot_list_TENANT_A_reports(self, client):
        pid = _create_project_as(client, TENANT_A)

        r = client.get("/reports", params={"project_id": pid}, headers=_h(TENANT_B))
        assert r.status_code in SAFE_STATUS, (
            f"Tenant B 竟能列出 Tenant A 的报告：{r.status_code} {r.text[:200]}"
        )
        if r.status_code == 200:
            assert r.json() == [], f"返回了非空报告列表：{r.json()}"

    def test_reports_without_tenant_header_rejected(self, client):
        """B-2：密钥 B 不声明 tenant 时回落到自身 tenant，
        而该 project 属 A → 租户校验必须拒绝。"""
        pid = _create_project_as(client, TENANT_A)

        r = client.get("/reports", params={"project_id": pid}, headers={"X-API-Key": KEY_B})
        assert r.status_code in SAFE_STATUS, (
            f"跨 tenant 读报告未被拦截：{r.status_code} {r.text[:200]}"
        )


# ------------------------------------------------------------------
# 2E — Sync / Distribution（确认其资源是否tenant-owned）
# ------------------------------------------------------------------

class TestSyncDistributionScope:
    def test_sync_status_requires_auth(self, client):
        """sync 需认证：未认证 401；已认证按平台级端点放行。"""
        r = client.get("/sync/status")
        assert r.status_code == 401, f"未认证竟通过：{r.status_code}"

        r2 = client.get("/sync/status", headers=_h(TENANT_B))
        assert r2.status_code in {200, 404, 501}, f"已认证后意外状态 {r2.status_code}"

    def test_distribution_brand_list_requires_auth(self, client):
        """distribution 端点需认证。"""
        r = client.get("/distribution/brands")
        assert r.status_code == 401, f"未认证竟通过：{r.status_code}"

        r2 = client.get("/distribution/brands", headers=_h(TENANT_B))
        assert r2.status_code in {200, 422}, f"已认证后实际 {r2.status_code}"

    def test_no_router_exposes_bare_project_list_without_tenant(self, client):
        """兜底：/projects 无 header 时不得返回任何数据。"""
        r = client.get("/projects", headers={"X-API-Key": KEY_B})
        if r.status_code == 200:
            assert r.json() == [], f"无 tenant header 返回了数据：{r.json()}"
        else:
            assert r.status_code in SAFE_STATUS
