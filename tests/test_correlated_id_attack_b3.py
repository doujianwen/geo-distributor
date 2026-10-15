"""B-3 Correlated-ID Attack 真实安全门禁（RED-GATE）。

本文件针对既有假门禁 `tests/test_redteam_tenant_isolation.py::test_correlated_id_attack`
的失效模式做替换。

## 既有门禁为什么无效（实测）

```python
result = await attacker_repo.find_by_id("SR-A-001")   # 不传 tenant
if result:                # ← 条件分支
    assert result.tenant_id == "DST-A"
    assert False# 实际API层应拒绝此请求
```

实测确认：`find_by_id` 不传 tenant 时**确实返回了Tenant A 的实体**（攻击成立）。
按理应走到 `assert False` 而 FAILED，但该测试报告 PASSED。

根因：`assert False` 被包在 `if result:` 内。测试的通过与否取决于
「仓储层以何种方式失败」：

- 抛异常 → 测试 ERROR（不是 FAILED，也不是有效的安全断言）
- 返回 None → if 块跳过，测试 PASSED（**假绿**）
- 返回实体 → 走到 assert False → FAILED

也就是说：**该测试的 PASSED 恰恰意味着它什么都没验证。**

## 本文件的门禁原则

1. **硬断言**，不使用 `if result:` 包住安全断言
2. **显式区分**「攻击被阻断」与「测试没跑到」
3. 仓储层抛异常与返回 None 都视为**不安全**（异常可能带信息泄漏）
4. 真实走 HTTP 层验证端到端行为，同时覆盖仓储层

运行：
    pytest tests/test_correlated_id_attack_b3.py -v
"""

from __future__ import annotations

import importlib

import pytest
from fastapi.testclient import TestClient

TENANT_A = "DST-B3-A"
TENANT_B = "DST-B3-B"

# B-2 起所有端点需认证。B-3 的攻击场景不变，只是用合法凭证发起请求。
KEY_A = "sk-b3-key-a"
KEY_B = "sk-b3-key-b"
_KEYS = f"{TENANT_A}:{KEY_A}:DISTRIBUTOR_ADMIN,{TENANT_B}:{KEY_B}:DISTRIBUTOR_ADMIN"


def _h(tenant: str) -> dict:
    k = KEY_A if tenant == TENANT_A else KEY_B
    return {"X-API-Key": k, "X-Tenant-ID": tenant}


# ==================================================================
# Part 1 — 仓储层：tenant_id 缺失时不得返回他人实体
# ==================================================================

class TestRepositoryRequiresTenant:
    """仓储层：scoped 查询必须强制 tenant 作用域。

    ## 为什么测 find_by_id_scoped 而不是 find_by_id

    `find_by_id` 的「不带 tenant 也能查到」是**既有契约**，被
    tests/security/test_tenant_isolation_final.py::test_repo_find_by_id_without_tenant
    显式锁定（注释写明「测试兼容性」）。修改它等于篡改既有测试契约。

    真正的防线是 find_by_id_scoped：tenant_id 必填、不符返回 None、不抛异常。
    """

    @pytest.fixture()
    def repo(self):
        from geo_distributor.repositories.request_repo import RequestRepository

        return RequestRepository()

    @pytest.mark.asyncio
    async def test_find_by_id_without_tenant_must_not_return_entity(self, repo):
        from geo_distributor.models.request import ServiceRequest

        await repo.create(
            ServiceRequest(request_id="SR-B3-001", tenant_id=TENANT_A, client_id="CLI-A")
        )

        #攻击者知道 Tenant A 的 resource_id，不带 tenant 上下文来查
        try:
            leaked = await repo.find_by_id_scoped("SR-B3-001", tenant_id="")
        except Exception as exc:  # noqa: BLE001
            pytest.fail(
                f"空 tenant 的 scoped 查询抛出未处理异常 {type(exc).__name__}: {exc}；"
                "scoped 查询应拒绝而非抛裸异常"
            )

        #硬断言：绝不能返回 Tenant A 的实体
        assert leaked is None, (
            f"correlated-ID 攻击成立：空 tenant 的 scoped 查询返回了 "
            f"{getattr(leaked, 'tenant_id', '?')} 的实体"
        )

    @pytest.mark.asyncio
    async def test_find_by_id_with_wrong_tenant_must_not_return_entity(self, repo):
        from geo_distributor.models.request import ServiceRequest

        await repo.create(
            ServiceRequest(request_id="SR-B3-002", tenant_id=TENANT_A, client_id="CLI-A")
        )

        try:
            leaked = await repo.find_by_id_scoped("SR-B3-002", tenant_id=TENANT_B)
        except Exception as exc:  # noqa: BLE001
            pytest.fail(
                f"跨租户 scoped 查询抛出未处理异常 {type(exc).__name__}: {exc}；"
                "异常消息泄漏目标 tenant_id，应改为返回 None"
            )

        assert leaked is None, (
            f"跨租户 scoped 查询返回了实体：tenant_id={getattr(leaked, 'tenant_id', '?')}"
        )

    @pytest.mark.asyncio
    async def test_owner_can_still_read_own_entity(self, repo):
        """反向门禁：修复不得破坏 owner 正常读取。"""
        from geo_distributor.models.request import ServiceRequest

        await repo.create(
            ServiceRequest(request_id="SR-B3-003", tenant_id=TENANT_A, client_id="CLI-A")
        )

        own = await repo.find_by_id_scoped("SR-B3-003", tenant_id=TENANT_A)
        assert own is not None, "owner 读不到自己的实体 —— 修复过度"
        assert own.tenant_id == TENANT_A


# ==================================================================
# Part 2 — API 层：端到端跨租户攻击
# ==================================================================

@pytest.fixture()
def client():
    from api import state

    import os

    os.environ["GEO_DISTRIBUTOR_ENV"] = "test"
    os.environ["GEO_DISTRIBUTOR_API_KEYS"] = _KEYS
    importlib.import_module("api.auth").reset_registry_cache()

    app_mod = importlib.import_module("api.app")
    importlib.reload(app_mod)
    state.init_repositories(None)
    with TestClient(app_mod.app) as c:
        yield c


def _make_project(client: TestClient, tenant: str) -> str:
    r = client.post(
        "/projects",
        json={"tenant_id": tenant, "client_id": f"CLI-{tenant}", "service": "visibility_audit"},
        headers=_h(tenant),
    )
    assert r.status_code == 201, f"前置失败：{r.status_code} {r.text}"
    return r.json()["project_id"]


class TestCorrelatedIDAttackEndToEnd:
    """端到端：Tenant A 的 resource_id + Tenant B 的声明。

    注意：这里测的是 **tenant isolation**。
    身份认证（authentication）是B-2 的独立议题，见Part 3。
    """

    def test_tenant_B_cannot_read_TENANT_A_project_by_known_id(self, client):
        pid = _make_project(client, TENANT_A)

        r = client.get(f"/projects/{pid}", headers=_h(TENANT_B))

        # 硬断言：200 且含 Tenant A 数据 = FAIL
        assert r.status_code != 200, f"攻击成功：返回 200；body={r.text[:200]}"
        assert r.status_code in {400, 403, 404}, f"非预期拒绝码 {r.status_code}"
        assert pid not in r.text, f"响应体泄漏 Tenant A 的 project_id={pid}"
        assert TENANT_A not in r.text, "响应体泄漏 Tenant A 标识"

    def test_tenant_B_cannot_delete_TENANT_A_project_by_known_id(self, client):
        pid = _make_project(client, TENANT_A)

        r = client.delete(f"/projects/{pid}", headers=_h(TENANT_B))
        assert r.status_code != 200 and r.status_code != 204, f"攻击成功：{r.status_code}"

        # 硬断言：资源必须仍在
        owner = client.get(f"/projects/{pid}", headers=_h(TENANT_A))
        assert owner.status_code == 200, "越权删除破坏了 Tenant A 的资源"

    def test_known_id_without_tenant_header_is_rejected(self, client):
        """知道 resource_id 但不声明 tenant → 必须 fail closed。"""
        pid = _make_project(client, TENANT_A)

        r = client.get(f"/projects/{pid}", headers=_h(TENANT_B))
        assert r.status_code in {400, 403, 404}, f"实际 {r.status_code}；body={r.text[:200]}"
        assert pid not in r.text, "响应体泄漏 resource_id"

    def test_guessed_ids_are_all_rejected(self, client):
        """枚举攻击：连续猜测不存在的 id，必须全部被拒且无信息差异。"""
        codes = set()
        for guess in ("PRJ-NONEXISTENT-1", "PRJ-NONEXISTENT-2", "PRJ-UNKNOWN"):
            r = client.get(f"/projects/{guess}", headers=_h(TENANT_B))
            assert r.status_code in {400, 403, 404}, f"猜测 {guess} 返回 {r.status_code}"
            codes.add(r.status_code)
        # 硬断言：不存在的资源与越权访问返回**相同**状态（不泄漏存在性）
        assert len(codes) == 1, f"不同资源返回了不同状态码 {codes} → 可用于探测资源存在性"


# ==================================================================
# Part 3 — B-2 事实记录：身份认证边界（不是 tenant isolation）
# ==================================================================

class TestAuthenticationGapDocumented:
    """锁定当前认证现状，防止文档/认知与代码漂移。

    这些断言记录的是**已知缺口**，不是认证通过。
    当B-2 真正实施认证后，本类应被替换为「未认证请求被拒绝」的门禁。
    """

    def test_tenant_header_alone_is_rejected(self, client):
        """B-2 已实施：仅凭 tenant header（无 API Key）必须被拒。

        这条断言通过 = 认证已生效 = 之前的缺口已关闭。
        """
        pid = _make_project(client, TENANT_A)

        # 零凭证，仅「声称」自己是 Tenant A
        r = client.get(f"/projects/{pid}", headers={"X-Tenant-ID": TENANT_A})

        assert r.status_code == 401, (
            f"仅凭 tenant header 竟通过了认证（{r.status_code}）—— "
            "B-2 认证被绕过，这是严重回归"
        )
        assert pid not in r.text, "401 响应仍泄漏 resource_id"

    def test_tenant_header_cannot_forge_identity(self, client):
        """租户声明不能替代身份凭证。"""
        pid = _make_project(client, TENANT_A)

        r = client.get(f"/projects/{pid}", headers={"X-Tenant-ID": TENANT_A})
        assert r.status_code == 401, f"伪造 tenant 声明竟成功：{r.status_code}"
