"""B-2 Authentication 门禁（RED-GATE）。

针对「远程 / 多用户 / 跨 Tenant 商业部署」场景，验证：

1. 认证边界：无有效凭证 → 401
2. 租户绑定：请求头 tenant 与密钥绑定值不一致 → 403
3. 角色授权：CLIENT_VIEWER 不得写入
4. 跨 tenant：非 HQ 角色不得访问他人资源
5. 角色不可伪造：header 声明 HQ 角色无效
6. 生产环境不得启用内置开发密钥

设计原则（沿用 B-3 教训）：
- 硬断言，不用 `if result:` 包住安全断言
- 每个攻击场景先断言「攻击前提成立」，避免假绿
- 不修改既有测试契约

运行：
    pytest tests/test_auth_b2.py -v
"""

from __future__ import annotations

import importlib

import pytest
from fastapi.testclient import TestClient

# ==============================================================
# 测试用密钥注册表
# ==============================================================

KEYS_ADMIN = "sk-test-admin-key-AAA"      # DST-ADMIN-A / distributor_admin
KEYS_USER = "sk-test-user-key-BBB"# DST-USER-B / distributor_user
KEYS_VIEWER = "sk-test-viewer-key-CCC"    # DST-VIEW-C / client_viewer
KEYS_HQ = "sk-test-hq-key-DDD"            # 跨 tenant / hq_technical

REGISTRY = (
    f"DST-ADMIN-A:{KEYS_ADMIN}:DISTRIBUTOR_ADMIN,"
    f"DST-USER-B:{KEYS_USER}:DISTRIBUTOR_USER,"
    f"DST-VIEW-C:{KEYS_VIEWER}:CLIENT_VIEWER,"
    f"HQ-OPS:{KEYS_HQ}:HQ_TECHNICAL"
)

TENANT_A = "DST-ADMIN-A"
TENANT_B = "DST-USER-B"


def _env(monkeypatch, extra: str = "") -> None:
    monkeypatch.setenv("GEO_DISTRIBUTOR_ENV", "test")
    monkeypatch.setenv("GEO_DISTRIBUTOR_API_KEYS", REGISTRY)
    if extra:
        monkeypatch.setenv("GEO_DISTRIBUTOR_API_KEYS", extra)


@pytest.fixture()
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("GEO_DISTRIBUTOR_AUDIT_DB",str(tmp_path/"audit.db"))
    _env(monkeypatch)
    from api import state

    app_mod = importlib.import_module("api.app")
    importlib.reload(app_mod)
    state.init_repositories(None)
    # reload 后需要重新加载 auth 模块以读取新环境变量
    importlib.reload(importlib.import_module("api.auth"))
    with TestClient(app_mod.app) as c:
        yield c


def _create_project(client: TestClient, tenant: str, key: str) -> str:
    """Seed a canonical legacy project for read/authorization tests.

    Distributor direct creation was intentionally closed by the HQ approval
    workflow. This fixture must not depend on that obsolete write permission.
    """
    import asyncio
    import uuid
    from api import state, auth
    from geo_distributor.models.client import Client
    from geo_distributor.models.project import Project
    ctx=auth.verify_api_key(key)
    assert ctx and (ctx.tenant_id==tenant or ctx.is_hq)
    ident=uuid.uuid4().hex[:10]
    cid="CLI-AUTH-"+ident
    pid="PRJ-AUTH-"+ident
    asyncio.run(state.client_repo.create(Client(cid,tenant,"Auth fixture")))
    asyncio.run(state.project_repo.create(Project(pid,"REQ-FIXTURE",tenant,cid,"SCOPE-FIXTURE")))
    return pid


def _create_project_as(client: TestClient, tenant: str, key: str) -> str:
    return _create_project(client,tenant,key)


# 每个密钥与其绑定 tenant 的对照（避免测试里写错配对）
KEY_TENANT = {
    KEYS_ADMIN: TENANT_A,
    KEYS_USER: TENANT_B,
    KEYS_VIEWER: "DST-VIEW-C",
    KEYS_HQ: "HQ-OPS",
}


# ==============================================================
# 1. 认证边界 —— 401
# ==============================================================

class TestAuthenticationRequired:
    """无有效凭证一律 401。这是商业部署的最低门槛。"""

    def test_no_api_key_is_rejected(self, client):
        r = client.get("/projects", headers={"X-Tenant-ID": TENANT_A})
        assert r.status_code == 401, f"无凭证竟通过：{r.status_code} {r.text[:200]}"

    def test_wrong_api_key_is_rejected(self, client):
        r = client.get("/projects", headers={"X-API-Key": "sk-invalid", "X-Tenant-ID": TENANT_A})
        assert r.status_code == 401, f"错误密钥竟通过：{r.status_code}"

    def test_empty_api_key_is_rejected(self, client):
        r = client.get("/projects", headers={"X-API-Key": "", "X-Tenant-ID": TENANT_A})
        assert r.status_code == 401, f"空密钥竟通过：{r.status_code}"

    def test_health_endpoint_remains_public(self, client):
        """健康检查必须保持公开 —— 负载均衡/反代探活需要。"""
        r = client.get("/health")
        assert r.status_code == 200, f"健康检查应公开，实际 {r.status_code}"

    def test_openapi_docs_disabled_by_default(self, client):
        """API 文档默认关闭（404）——避免向公网暴露完整接口结构。

        需要排查时可设 GEO_DISTRIBUTOR_EXPOSE_DOCS=1 开启。
        """
        r = client.get("/openapi.json")
        assert r.status_code == 404, (
            f"API 文档未关闭（{r.status_code}）—— "
            "远程部署下会暴露端点/参数/schema"
        )

    def test_health_is_public_for_probes(self, client):
        """健康检查必须公开 —— 反向代理/负载均衡探活依赖它。"""
        r = client.get("/health")
        assert r.status_code == 200, f"健康检查应公开，实际 {r.status_code}"


# ==============================================================
# 2. 租户绑定 —— 403
# ==============================================================

class TestTenantBinding:
    """tenant 必须从密钥反查，而非信任请求头声明。"""

    def test_header_tenant_conflicting_with_key_is_rejected(self, client):
        """用 A 的密钥 + 声明 B 的 tenant → 403。"""
        pid = _create_project(client, TENANT_A, KEYS_ADMIN)

        r = client.get(
            f"/projects/{pid}",
            headers={"X-API-Key": KEYS_ADMIN, "X-Tenant-ID": TENANT_B},
        )
        assert r.status_code == 403, f"声明冲突未拦截：{r.status_code} {r.text[:200]}"

    def test_missing_header_tenant_uses_key_tenant(self, client):
        """不声明 tenant 时应使用密钥绑定值，而非拒绝或泄漏。"""
        pid = _create_project(client, TENANT_A, KEYS_ADMIN)

        r = client.get(f"/projects/{pid}", headers={"X-API-Key": KEYS_ADMIN})
        assert r.status_code == 200, f"应回落到密钥 tenant，实际 {r.status_code} {r.text[:200]}"
        assert r.json()["tenant_id"] == TENANT_A, "回落到了错误的 tenant"

    def test_key_cannot_read_other_tenant_resource(self, client):
        """B 的密钥 + A 的 resource_id → 拒绝。"""
        pid = _create_project(client, TENANT_A, KEYS_ADMIN)

        r = client.get(f"/projects/{pid}", headers={"X-API-Key": KEYS_USER})
        assert r.status_code in {403, 404}, f"跨租户读取未被拦截：{r.status_code}"
        assert pid not in r.text, "响应体泄漏 resource_id"

    def test_key_cannot_delete_other_tenant_resource(self, client):
        pid = _create_project(client, TENANT_A, KEYS_ADMIN)

        r = client.delete(f"/projects/{pid}", headers={"X-API-Key": KEYS_USER})
        assert r.status_code in {403, 404}, f"跨租户删除未被拦截：{r.status_code}"

        owner = client.get(f"/projects/{pid}", headers={"X-API-Key": KEYS_ADMIN})
        assert owner.status_code == 200, "越权删除破坏了资源"

    def test_distributor_cannot_cross_tenant(self, client):
        """DISTRIBUTOR 角色不得跨 tenant 读取（角色越权）。"""
        pid = _create_project(client, TENANT_A, KEYS_ADMIN)

        r = client.get(f"/projects/{pid}", headers={"X-API-Key": KEYS_USER, "X-Tenant-ID": TENANT_B})
        assert r.status_code in {403, 404}, f"跨tenant 未拦截：{r.status_code}"


# ==============================================================
# 3. 角色授权 —— 403
# ==============================================================

class TestRoleAuthorization:
    def test_client_viewer_cannot_create_project(self, client):
        r = client.post(
            "/projects",
            json={"tenant_id": TENANT_B, "client_id": "C", "service": "visibility_audit"},
            headers={"X-API-Key": KEYS_VIEWER, "X-Tenant-ID": "DST-VIEW-C"},
        )
        assert r.status_code == 403, f"CLIENT_VIEWER 竟可创建项目：{r.status_code} {r.text[:200]}"

    def test_client_viewer_cannot_delete_project(self, client):
        # 资源由有写权限的密钥创建，viewer 尝试删除
        pid = _create_project_as(client, TENANT_B, KEYS_USER)

        r = client.delete(
            f"/projects/{pid}",
            headers={"X-API-Key": KEYS_VIEWER, "X-Tenant-ID": "DST-VIEW-C"},
        )
        assert r.status_code == 403, f"CLIENT_VIEWER 竟可删除：{r.status_code} {r.text[:150]}"

    def test_client_viewer_can_read(self, client):
        """Tenant-wide read-only role retains its own legacy resource access."""
        pid = _create_project_as(client, "DST-VIEW-C", KEYS_VIEWER)
        r = client.get(f"/projects/{pid}", headers={"X-API-Key": KEYS_VIEWER})
        assert r.status_code == 200

    def test_role_cannot_be_spoofed_via_header(self, client):
        """header 声明 HQ 角色无效 —— 角色必须来自密钥绑定。"""
        pid = _create_project(client, TENANT_A, KEYS_ADMIN)

        r = client.get(
            f"/projects/{pid}",
            headers={
                "X-API-Key": KEYS_ADMIN,
                "X-Tenant-ID": TENANT_A,
                "X-WP-Role": "hq_management",
            },
        )
        # DISTRIBUTOR_ADMIN 读自己 tenant 的项目本就允许；
        # 关键是不能因为伪造 header 而获得跨 tenant 能力（下一个用例验证）
        assert r.status_code in {200, 403}, f"未定义行为：{r.status_code}"

    def test_spoofed_hq_role_cannot_cross_tenant(self, client):
        """伪造 HQ 角色 + 声明他人 tenant → 必须仍被拒。"""
        pid = _create_project(client, TENANT_A, KEYS_ADMIN)

        r = client.get(
            f"/projects/{pid}",
            headers={
                "X-API-Key": KEYS_USER,
                "X-Tenant-ID": TENANT_A,
                "X-WP-Role": "hq_management",
            },
        )
        assert r.status_code in {403, 404}, f"伪造 HQ 角色成功跨租户：{r.status_code}"


# ==============================================================
# 4. HQ 跨 tenant —— 允许
# ==============================================================

class TestHQCrossTenant:
    def test_hq_can_read_any_tenant_project(self, client):
        """HQ 角色必须能跨 tenant —— 否则无法履行「HQ 交付」职责。"""
        pid = _create_project(client, TENANT_A, KEYS_ADMIN)

        # HQ 密钥绑定 HQ-OPS；要读 A 的项目，需在header 显式声明目标 tenant
        r = client.get(f"/projects/{pid}", headers={"X-API-Key": KEYS_HQ, "X-Tenant-ID": TENANT_A})
        assert r.status_code == 200, f"HQ 应可跨 tenant 读取，实际 {r.status_code} {r.text[:200]}"

    def test_hq_defaults_to_own_tenant_without_header(self, client):
        """HQ 不声明 tenant 时使用密钥绑定值，不应报错。"""
        r = client.get("/projects", headers={"X-API-Key": KEYS_HQ})
        assert r.status_code == 200, f"HQ 免声明应回落自身 tenant，实际 {r.status_code}"


# ==============================================================
# 5. 配置安全
# ==============================================================

class TestConfigurationSafety:
    def test_production_env_does_not_load_builtin_dev_keys(self, monkeypatch):
        """非 test/dev 环境下，内置开发密钥恒不加载。"""
        monkeypatch.setenv("GEO_DISTRIBUTOR_ENV", "production")
        monkeypatch.delenv("GEO_DISTRIBUTOR_API_KEYS", raising=False)

        auth = importlib.reload(importlib.import_module("api.auth"))

        # 尝试用内置开发密钥认证
        ctx = auth.verify_api_key("sk-dev-key-localhost")
        assert ctx is None, "生产环境竟加载了内置开发密钥"

    def test_api_keys_file_is_gitignored(self):
        """密钥文件绝不能进 git。"""
        import pathlib

        root = pathlib.Path(__file__).resolve().parent.parent
        gi = (root / ".gitignore").read_text(encoding="utf-8")
        assert "api_keys" in gi, "config/api_keys.json 未被 .gitignore 保护"

    def test_registry_parses_multiple_keys(self, monkeypatch):
        _env(monkeypatch)
        auth = importlib.reload(importlib.import_module("api.auth"))

        ctx = auth.verify_api_key(KEYS_ADMIN)
        assert ctx is not None, "合法密钥解析失败"
        assert ctx.tenant_id == TENANT_A, f"tenant 绑定错误：{ctx.tenant_id}"
        assert ctx.role == "DISTRIBUTOR_ADMIN", f"角色错误：{ctx.role}"

    def test_revoked_key_is_rejected(self, monkeypatch):
        """从注册表移除后立即失效（吊销能力）。"""
        _env(monkeypatch)
        auth = importlib.reload(importlib.import_module("api.auth"))
        assert auth.verify_api_key(KEYS_ADMIN) is not None, "前置失败：密钥初始应有效"

        # 重新加载一个不含该密钥的注册表
        monkeypatch.setenv(
            "GEO_DISTRIBUTOR_API_KEYS",
            f"DST-USER-B:{KEYS_USER}:DISTRIBUTOR_USER",
        )
        auth2 = importlib.reload(importlib.import_module("api.auth"))
        assert auth2.verify_api_key(KEYS_ADMIN) is None, "已吊销的密钥仍有效"

    def test_malformed_registry_line_is_skipped(self, monkeypatch):
        """格式错误的配置行应跳过而非崩溃。"""
        monkeypatch.setenv("GEO_DISTRIBUTOR_ENV", "test")
        monkeypatch.setenv(
            "GEO_DISTRIBUTOR_API_KEYS",
            f"BROKEN-LINE-NO-COLONS,,{TENANT_A}:{KEYS_ADMIN}:DISTRIBUTOR_ADMIN",
        )
        auth = importlib.reload(importlib.import_module("api.auth"))
        assert auth.verify_api_key(KEYS_ADMIN) is not None, "合法行应仍可用"
        assert auth.verify_api_key("anything") is None
