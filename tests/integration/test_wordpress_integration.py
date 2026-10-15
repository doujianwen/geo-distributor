"""WordPress → geo-distributor 最小真实集成验证。

## 这个文件与其它测试的区别

其它测试用 `TestClient(app)` —— 在**进程内**直接调用 ASGI 应用，绕过网络层。
本文件启动**真实的 uvicorn 子进程**，用**真实的 HTTP 客户端**（httpx）
经由**真实的 TCP 连接**发起请求。

差别是实质性的：
- TestClient 不会真正走网络栈，不存在真实连接、不存在真实端口绑定
- TestClient 绕过了反向代理，任何部署配置问题都测不出来
- 本文件能验证：进程真的能起、端口真的能连、header 真的会被拒绝

## 架构（Option A —— 本机真实进程，无公网暴露）

```
WordPress 模拟客户端（本文件）
    │ 真实 HTTP over TCP
    ▼
geo-distributor 进程（真实 uvicorn，127.0.0.1:<随机端口>）
    │ 认证 → 租户解析 → 授权 → 业务 → 审计
    ▼
data/*.db
```

**为什么不在本机伪造 TLS**：
本机无nginx、无证书。用自签名证书在本机做 HTTPS 只会制造
「看起来有 TLS」的假象 —— 实际不验证任何真实部署条件。
按指令 §2 的要求，TLS 一项如实标记 CONDITIONAL，不假装完成。

**安全边界**：
- 绑定 `127.0.0.1` —— 仅本机可达，不构成公网暴露
- 一次性测试密钥，进程结束即失效
- 不写入任何真实数据文件（用临时目录）

运行：
    pytest tests/integration/test_wordpress_integration.py -v
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parent.parent.parent

# 一次性测试密钥 —— 仅本文件使用，进程退出即失效
TENANT_A = "WP-TENANT-A"
TENANT_B = "WP-TENANT-B"
KEY_A = "sk-wp-integration-test-tenant-a-ONLY"
KEY_B = "sk-wp-integration-test-tenant-b-ONLY"
KEY_BAD = "sk-wp-integration-wrong-key-ONLY"

API_KEYS = (
    f"{TENANT_A}:{KEY_A}:DISTRIBUTOR_ADMIN,"
    f"{TENANT_B}:{KEY_B}:DISTRIBUTOR_ADMIN"
)


def _free_port() -> int:
    """向操作系统要一个真实空闲端口（绑定 0 由内核分配，避免竞态）。"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@pytest.fixture(scope="module")
def server():
    """启动**真实 uvicorn 进程**。

    这是本文件与 TestClient 的核心区别：真实进程、真实端口、真实网络栈。
    """
    port = _free_port()
    tmp = ROOT / "data" / "_integration_tmp"
    tmp.mkdir(parents=True, exist_ok=True)

    env = dict(os.environ)
    env.update(
        {
            "GEO_DISTRIBUTOR_ENV": "production",
            "GEO_DISTRIBUTOR_API_KEYS": API_KEYS,
            "GEO_DISTRIBUTOR_DB": str(tmp / "integration.db"),
            "GEO_DISTRIBUTOR_AUDIT_DB": str(tmp / "audit.db"),
            "GEO_DISTRIBUTOR_RATE_LIMIT": "600",
            "GEO_DISTRIBUTOR_RATE_BURST": "200",
            # 不设置 EXPOSE_DOCS → 验证生产默认关闭
        }
    )
    env.pop("GEO_DISTRIBUTOR_EXPOSE_DOCS", None)

    proc = subprocess.Popen(
        [
            str(ROOT / ".venv/Scripts/python.exe"),
            "-m",
            "uvicorn",
            "api.app:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--log-level",
            "warning",
            # 与 start_api_prod.sh 保持一致：不暴露 Server 头
            "--no-server-header",
        ],
        cwd=str(ROOT),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    # 等待端口真正可连（不是 sleep 猜测，是轮询连接）
    base = f"http://127.0.0.1:{port}"
    ready = False
    # Python 解释器冷启动 + 路由导入可能需要数秒；用退避轮询而非固定 sleep。
    for attempt in range(120):
        if proc.poll() is not None:
            pytest.fail(
                f"服务进程启动即退出（code={proc.returncode}）。"
                "常见原因：环境变量缺失、端口被占、依赖导入失败。"
            )
        try:
            r = httpx.get(f"{base}/health", timeout=2.0)
            if r.status_code == 200:
                ready = True
                break
        except (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout, OSError):
            pass
        # 前 40 次固定 100ms，之后退避到 500ms（总预算约 45s）
        time.sleep(0.1 if attempt < 40 else 0.5)

    if not ready:
        proc.kill()
        proc.wait(timeout=10)
        pytest.fail(
            "服务进程在超时内未就绪（45s）。"
            "在受限沙箱中子进程可能无法监听端口 —— "
            "此时应改用 in-process uvicorn 模式（见 test_wordpress_inprocess.py）。"
        )

    try:
        yield {"base": base, "port": port, "tmp": tmp}
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()


@pytest.fixture()
def wp(server):
    """模拟 WordPress 侧的 HTTP 客户端。

    刻意用裸 httpx 而非 TestClient —— 必须走真实网络。
    """

    class WordPressClient:
        """最小 WordPress 调用方。

        对应真实 WordPress 侧会用 wp_remote_get() / wp_remote_post() 发出的请求。
        它只知道两件事：API 地址、自己的 API Key。
        **不知道**内部 tenant 授权规则 —— 这正是要验证的架构点。
        """

        def __init__(self, base: str, api_key: str):
            self._client = httpx.Client(base_url=base, timeout=10.0)
            self._api_key = api_key

        def get(self, path: str, tenant: str | None = None, key: str | None = None):
            headers = {"X-API-Key": key or self._api_key}
            if tenant is not None:
                headers["X-Tenant-ID"] = tenant
            return self._client.get(path, headers=headers)

        def post(self, path: str, body: dict, tenant: str | None = None,
                 key: str | None = None):
            headers = {"X-API-Key": key or self._api_key}
            if tenant is not None:
                headers["X-Tenant-ID"] = tenant
            return self._client.post(path, json=body, headers=headers)

        def delete(self, path: str, tenant: str | None = None, key: str | None = None):
            headers = {"X-API-Key": key or self._api_key}
            if tenant is not None:
                headers["X-Tenant-ID"] = tenant
            return self._client.delete(path, headers=headers)

        def raw(self, method: str, path: str, headers: dict):
            return self._client.request(method, path, headers=headers)

    return WordPressClient


# ==================================================================
# §5 基础请求场景（Request A ~ F）
# ==================================================================


class TestBasicRequestMatrix:
    """六种基础请求的真实 HTTP 行为。"""

    def test_A_tenant_a_legal_call_2xx(self, wp, server):
        """A：Tenant A 合法调用 → 2xx。"""
        c = wp(server["base"], KEY_A)
        r = c.get("/projects", tenant=TENANT_A)
        assert r.status_code == 200, f"A 合法调用应 200，实际 {r.status_code} {r.text[:150]}"
        assert isinstance(r.json(), list)

    def test_B_tenant_a_reads_tenant_b_denied(self, wp, server):
        """B：Tenant A 访问 Tenant B → 403/去标识 404。"""
        c = wp(server["base"], KEY_A)
        r = c.get("/projects", tenant=TENANT_B)
        assert r.status_code in {403, 404}, (
            f"B 越权应被拒，实际 {r.status_code} {r.text[:150]}"
        )

    def test_C_no_auth_401(self, wp, server):
        """C：无认证 → 401。"""
        r = httpx.get(f"{server['base']}/projects", timeout=10)
        assert r.status_code == 401, f"无认证应 401，实际 {r.status_code}"

    def test_D_wrong_secret_401(self, wp, server):
        """D：错误 secret → 401。"""
        c = wp(server["base"], KEY_BAD)
        r = c.get("/projects", tenant=TENANT_A)
        assert r.status_code == 401, f"错误密钥应 401，实际 {r.status_code} {r.text[:150]}"

    def test_E_authenticated_A_with_header_B_403(self, wp, server):
        """E：认证 tenant=A，header 声明 B → 403。"""
        c = wp(server["base"], KEY_A)
        r = c.get("/projects", tenant=TENANT_B)
        assert r.status_code == 403, (
            f"租户声明冲突应 403，实际 {r.status_code} {r.text[:150]}"
        )
        # 403 不应回显受害方租户
        assert TENANT_B not in r.text, f"403 回显了声明的租户：{r.text[:200]}"

    def test_F_matched_tenant_ok(self, wp, server):
        """F：认证 A + header A → 正常。"""
        c = wp(server["base"], KEY_A)
        r = c.get("/projects", tenant=TENANT_A)
        assert r.status_code == 200, f"匹配租户应 200，实际 {r.status_code} {r.text[:150]}"

    def test_F2_no_header_falls_back_to_key_tenant(self, wp, server):
        """X-Tenant-ID 可选：缺失时回落到密钥绑定 tenant。"""
        c = wp(server["base"], KEY_A)
        r = c.get("/projects")  # 不发 X-Tenant-ID
        assert r.status_code == 200, f"缺 header 应回落密钥 tenant，实际 {r.status_code}"
        assert isinstance(r.json(), list), f"应返回列表，实际 {r.text[:150]}"


# ==================================================================
# §12 最小商业链路
# ==================================================================


class TestBusinessFlow:
    """WordPress → 认证 → 租户解析 → Delivery Engine → 结果 → 审计。"""

    def test_full_create_project_flow(self, wp, server):
        """完整商业链路：创建项目 → 读取 → 审计留痕。"""
        c = wp(server["base"], KEY_A)

        # 1) WordPress 发起创建
        r = c.post(
            "/projects",
            {
                "tenant_id": TENANT_A,
                "client_id": "CLI-WP-A",
                "service": "visibility_audit",
            },
            tenant=TENANT_A,
        )
        assert r.status_code == 201, f"创建项目失败：{r.status_code} {r.text[:200]}"
        data = r.json()
        pid = data["project_id"]
        assert data["tenant_id"] == TENANT_A, "返回的租户不符"
        assert pid

        # 2) Delivery Engine 返回结果
        assert "progress_percent" in data, "缺少交付结果字段"
        assert "service_stage" in data, "缺少服务阶段字段"

        # 3) WordPress 读回（确认可访问自己的资源）
        r2 = c.get(f"/projects/{pid}", tenant=TENANT_A)
        assert r2.status_code == 200, f"读回失败：{r2.status_code}"
        assert r2.json()["project_id"] == pid

        # 4) 审计留痕
        #
        # 必须**直连子进程的审计库**，不能用主进程的 api.audit.query_audit：
        # 审计由子进程写入，主进程模块持有的是另一个连接/另一个库路径。
        # 这正是「真实进程集成」与「TestClient」的本质差别之一。
        import sqlite3

        audit_db = server["tmp"] / "audit.db"
        assert audit_db.exists(), f"审计库未创建：{audit_db}"
        conn = sqlite3.connect(str(audit_db))
        conn.row_factory = sqlite3.Row
        # 中间件按**请求路径**记录（resource_type），resource_id 留给
        # 端点层按需补充 —— 当前中间件不解析路径中的 ID。
        # 因此这里按 tenant + 路径匹配，project_id 应出现在路径里。
        rows = [
            dict(r)
            for r in conn.execute(
                "SELECT * FROM audit_log "
                "WHERE tenant_id = ? AND action = 'POST' AND resource_type = ?",
                (TENANT_A, "/projects"),
            ).fetchall()
        ]
        conn.close()
        assert rows, f"创建项目未产生审计记录（审计库={audit_db}）"
        entry = rows[0]
        assert entry["action"] == "POST", f"审计 action 异常：{entry['action']}"
        assert entry["outcome"] == "OK", f"审计 outcome 异常：{entry['outcome']}"
        assert entry["user_id"], "审计缺actor"
        assert entry["role"], "审计缺 role"
        assert entry["created_at"], "审计缺时间戳"
        # 不得含原始 API Key
        assert KEY_A not in str(entry), "审计记录了原始 API Key"

    def test_client_flow(self, wp, server):
        """客户维度的商业链路。"""
        c = wp(server["base"], KEY_B)
        r = c.post(
            "/clients",
            {"tenant_id": TENANT_B, "name": "WP Integration Client"},
            tenant=TENANT_B,
        )
        assert r.status_code == 201, f"创建客户失败：{r.status_code} {r.text[:200]}"
        cid = r.json()["client_id"]

        r2 = c.get(f"/clients/{cid}", tenant=TENANT_B)
        assert r2.status_code == 200
        assert r2.json()["name"] == "WP Integration Client"


# ==================================================================
# §6 + §13 架构验证：WordPress 无需知道内部 tenant 授权
# ==================================================================


class TestTenantIsolationReal:
    """WordPress 改 ID 也无法越权 —— 服务端租户解析是唯一权威。"""

    def test_project_id_spoof_denied(self, wp, server):
        """A 拿 B 的 project_id 无法读取。"""
        a = wp(server["base"], KEY_A)
        b = wp(server["base"], KEY_B)

        # B 创建一个项目
        r_b = b.post(
            "/projects",
            {"tenant_id": TENANT_B, "client_id": "CLI-B", "service": "visibility_audit"},
            tenant=TENANT_B,
        )
        assert r_b.status_code == 201, f"前置失败：{r_b.status_code} {r_b.text[:150]}"
        pid_b = r_b.json()["project_id"]

        # A 尝试读 B 的项目 —— 换 header 也没用
        r = a.get(f"/projects/{pid_b}", tenant=TENANT_A)
        assert r.status_code in {403, 404}, (
            f"project_id 伪造未被拦截：{r.status_code} {r.text[:150]}"
        )
        assert pid_b not in r.text, "响应体泄漏了 B 的 project_id"

    def test_bidirectional_isolation(self, wp, server):
        """A→B 与 B→A 双向都必须被拒。"""
        a = wp(server["base"], KEY_A)
        b = wp(server["base"], KEY_B)

        pid_a = a.post(
            "/projects",
            {"tenant_id": TENANT_A, "client_id": "CLI-A2", "service": "visibility_audit"},
            tenant=TENANT_A,
        ).json()["project_id"]
        pid_b = b.post(
            "/projects",
            {"tenant_id": TENANT_B, "client_id": "CLI-B2", "service": "visibility_audit"},
            tenant=TENANT_B,
        ).json()["project_id"]

        # A → B
        r = a.get(f"/projects/{pid_b}", tenant=TENANT_A)
        assert r.status_code in {403, 404}, f"A 读 B 未被拒：{r.status_code}"

        # B → A
        r2 = b.get(f"/projects/{pid_a}", tenant=TENANT_B)
        assert r2.status_code in {403, 404}, f"B 读 A 未被拒：{r2.status_code}"

    def test_client_id_spoof_denied(self, wp, server):
        """client_id 伪造同样无效。"""
        a = wp(server["base"], KEY_A)
        b = wp(server["base"], KEY_B)

        cid_b = b.post(
            "/clients", {"tenant_id": TENANT_B, "name": "Victim Client"}, tenant=TENANT_B
        ).json()["client_id"]

        # A 改 tenant header 试图读 B 的客户
        r = a.get(f"/clients/{cid_b}", tenant=TENANT_A)
        assert r.status_code in {403, 404}, f"client_id 伪造未被拦截：{r.status_code}"
        assert cid_b not in r.text, "响应体泄漏了 B 的 client_id"

    def test_delete_spoof_denied(self, wp, server):
        """越权删除必须被拒，且资源完好。"""
        a = wp(server["base"], KEY_A)
        b = wp(server["base"], KEY_B)

        pid_b = b.post(
            "/projects",
            {"tenant_id": TENANT_B, "client_id": "CLI-B3", "service": "visibility_audit"},
            tenant=TENANT_B,
        ).json()["project_id"]

        r = a.delete(f"/projects/{pid_b}", tenant=TENANT_A)
        assert r.status_code in {403, 404}, f"越权删除未被拦截：{r.status_code}"

        # B 的资源必须仍在
        r2 = b.get(f"/projects/{pid_b}", tenant=TENANT_B)
        assert r2.status_code == 200, "越权删除破坏了受害方资源"


# ==================================================================
# §7 审计轨迹（跨租户攻击 + 认证失败）
# ==================================================================


class TestAuditTrailReal:
    def test_cross_tenant_attempt_is_denied_and_logged(self, wp, server):
        """跨租户攻击：必须 DENIED 留痕，且不泄露受害方 tenant。"""
        import sqlite3

        a = wp(server["base"], KEY_A)
        b = wp(server["base"], KEY_B)

        pid_b = b.post(
            "/projects",
            {"tenant_id": TENANT_B, "client_id": "CLI-AUD", "service": "visibility_audit"},
            tenant=TENANT_B,
        ).json()["project_id"]

        # A 攻击 B
        r = a.get(f"/projects/{pid_b}", tenant=TENANT_A)
        assert r.status_code in {403, 404}, f"攻击未被拦截：{r.status_code}"
        assert pid_b not in r.text, "响应体泄漏了受害方 project_id"

        # A 侧审计必须有 DENIED
        conn = sqlite3.connect(str(server["tmp"] / "audit.db"))
        conn.row_factory = sqlite3.Row
        rows = [
            dict(r)
            for r in conn.execute(
                "SELECT * FROM audit_log WHERE tenant_id = ? ORDER BY id DESC LIMIT 10",
                (TENANT_A,),
            ).fetchall()
        ]
        conn.close()
        assert rows, "攻击未产生审计记录"
        assert any(x["outcome"] in {"DENIED", "ERROR"} for x in rows), (
            f"攻击未标记为拒绝：{[x['outcome'] for x in rows]}"
        )
        # A 的审计里不得出现 B 的租户标识
        blob = " ".join(str(x) for x in rows)
        assert TENANT_B not in blob, f"A 的审计泄露了 B 的租户：{blob[:200]}"

    def test_auth_failure_logged_without_tenant(self, wp, server):
        """认证失败留痕，且 tenant_id 不可信时为空（不信攻击者提交的值）。"""
        import sqlite3

        # 攻击者声称自己是某个租户，但密钥错误
        httpx.get(
            f"{server['base']}/projects",
            headers={"X-API-Key": KEY_BAD, "X-Tenant-ID": "SPOOFED-TENANT"},
            timeout=10,
        )

        conn = sqlite3.connect(str(server["tmp"] / "audit.db"))
        conn.row_factory = sqlite3.Row
        rows = [
            dict(r)
            for r in conn.execute(
                "SELECT * FROM audit_log WHERE user_id IS NULL ORDER BY id DESC LIMIT 5"
            ).fetchall()
        ]
        conn.close()
        assert rows, "认证失败未留痕"
        #关键：不得把攻击者声明的租户当成可信身份存下来
        assert all(r["tenant_id"] != "SPOOFED-TENANT" for r in rows), (
            "审计把攻击者声明的租户当成了可信身份"
        )


# ==================================================================
# §8 限流（真实 HTTP 连续请求）
# ==================================================================


class TestRateLimitReal:
    """用真实 HTTP 连续请求验证限流。

    限制：当前实现是**process-local令牌桶**（Stage 1 设计）。
    因此本测试对单个进程有效；多实例部署时总额度 = 配置 × 实例数。
    这一点记录在部署契约中，不在此处伪造 Redis 测试。
    """

    def test_rate_limit_triggers_and_is_per_key(self, server):
        """独立启动一个低配额进程，验证 429 与租户隔离。"""
        import socket as _sock
        import subprocess as _sp
        import time as _t

        with _sock.socket() as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]

        tmp = server["tmp"] / "ratelimit"
        tmp.mkdir(exist_ok=True)
        env = dict(os.environ)
        env.update(
            {
                "GEO_DISTRIBUTOR_ENV": "production",
                "GEO_DISTRIBUTOR_API_KEYS": API_KEYS,
                "GEO_DISTRIBUTOR_RATE_LIMIT": "60",
                "GEO_DISTRIBUTOR_RATE_BURST": "3",
                "GEO_DISTRIBUTOR_DB": str(tmp / "rl.db"),
                "GEO_DISTRIBUTOR_AUDIT_DB": str(tmp / "rl_audit.db"),
            }
        )
        proc = _sp.Popen(
            [
                str(ROOT / ".venv/Scripts/python.exe"), "-m", "uvicorn",
                "api.app:app", "--host", "127.0.0.1", "--port", str(port),
                "--log-level", "warning",
            ],
            cwd=str(ROOT), env=env,
            stdout=_sp.DEVNULL, stderr=_sp.DEVNULL,
        )
        base = f"http://127.0.0.1:{port}"
        try:
            for _ in range(120):
                try:
                    if httpx.get(f"{base}/health", timeout=2).status_code == 200:
                        break
                except Exception:
                    _t.sleep(0.1)

            # 打爆 Tenant A
            codes_a = []
            for _ in range(8):
                r = httpx.get(
                    f"{base}/projects",
                    headers={"X-API-Key": KEY_A, "X-Tenant-ID": TENANT_A},
                    timeout=10,
                )
                codes_a.append(r.status_code)
            assert 429 in codes_a, f"Tenant A 超限未返回 429：{codes_a}"
            first_429 = codes_a.index(429)
            assert all(x == 200 for x in codes_a[:first_429]), (
                f"限流前的请求应全部成功：{codes_a[:first_429]}"
            )

            # Tenant B 不受影响
            r_b = httpx.get(
                f"{base}/projects",
                headers={"X-API-Key": KEY_B, "X-Tenant-ID": TENANT_B},
                timeout=10,
            )
            assert r_b.status_code == 200, (
                f"Tenant A 的限流误伤了 Tenant B：{r_b.status_code}"
            )

            # 429 响应不得泄露内部信息
            r_429 = httpx.get(
                f"{base}/projects",
                headers={"X-API-Key": KEY_A, "X-Tenant-ID": TENANT_A},
                timeout=10,
            )
            assert r_429.status_code == 429
            assert "Retry-After" in r_429.headers, "429 缺少 Retry-After"
            for leak in ("traceback", "sqlite", "sk-", "/e/", "python"):
                assert leak not in r_429.text.lower(), f"429 泄露了 {leak}"
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except Exception:
                proc.kill()


# ==================================================================
# §9 + §14 API 暴露与红队（全部走真实 HTTP）
# ==================================================================


class TestAPIExposureReal:
    def test_RT_WP_09_docs_closed(self, server):
        """生产环境文档端点必须 404。"""
        for path in ("/docs", "/openapi.json", "/redoc"):
            r = httpx.get(f"{server['base']}{path}", timeout=10)
            assert r.status_code == 404, f"{path} 应 404，实际 {r.status_code}"

    def test_RT_WP_10_health_no_leak(self, server):
        """健康端点只返回最小状态。"""
        r = httpx.get(f"{server['base']}/health", timeout=10)
        assert r.status_code == 200
        payload = r.json()
        assert payload == {"status": "ok"}, f"健康端点泄露内部状态：{payload}"
        body = r.text
        for leak in ("db_path", ".db", "sqlite", "backend", "service", "\\", "/"):
            assert leak not in body, f"健康响应含 {leak}：{body[:150]}"

    def test_RT_WP_08_backend_binds_loopback_only(self, server):
        """后端只绑回环 —— 不可从外部网卡访问。

        本机验证方式：确认监听地址是 127.0.0.1而非 0.0.0.0。
        """
        # 服务由 fixture 以 --host 127.0.0.1 启动；这里验证它确实只在回环可达
        host_ip = httpx.get(f"{server['base']}/health", timeout=5).status_code
        assert host_ip == 200, "回环地址应可访问"

        # 尝试通过本机的非回环地址访问同一端口 —— 应失败
        import socket

        # 取本机一个非回环 IP
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("8.8.8.8", 80))
            local_ip = s.getsockname()[0]
        except Exception:
            pytest.skip("无法确定本机非回环 IP")
        finally:
            s.close()

        if local_ip.startswith("127."):
            pytest.skip("本机只有回环地址，无法验证非回环不可达")

        try:
            httpx.get(f"http://{local_ip}:{server['port']}/health", timeout=3)
            pytest.fail(
                f"后端在非回环地址 {local_ip}:{server['port']} 上可访问 —— "
                "违反「仅内部可达」约束"
            )
        except (httpx.ConnectError, httpx.ConnectTimeout, OSError):
            pass  # 预期：非回环不可达

    def test_security_headers_present(self, server):
        """安全响应头由应用层保证（不依赖反代）。"""
        r = httpx.get(f"{server['base']}/health", timeout=10)
        assert "nosniff" in r.headers.get("X-Content-Type-Options", "").lower()
        assert r.headers.get("X-Frame-Options") == "DENY"
        # 不得暴露服务端实现（--no-server-header 已抑制）
        assert "uvicorn" not in r.headers.get("Server", "").lower(), (
            f"暴露了 Server 头：{r.headers.get('Server')}"
        )
        assert "X-Powered-By" not in r.headers

    def test_RT_WP_01_to_07_summary(self, wp, server):
        """RT-WP-01~07 汇总（各条已在独立测试中验证）。"""
        a = wp(server["base"], KEY_A)

        # RT-WP-01 无认证
        assert httpx.get(f"{server['base']}/projects", timeout=10).status_code == 401
        # RT-WP-02 错误密钥
        assert wp(server["base"], KEY_BAD).get("/projects", tenant=TENANT_A).status_code == 401
        # RT-WP-03 tenant header 欺骗
        assert a.get("/projects", tenant=TENANT_B).status_code == 403
        # RT-WP-04 project_id 伪造
        pid_b = wp(server["base"], KEY_B).post(
            "/projects",
            {"tenant_id": TENANT_B, "client_id": "C", "service": "visibility_audit"},
            tenant=TENANT_B,
        ).json()["project_id"]
        assert a.get(f"/projects/{pid_b}", tenant=TENANT_A).status_code in {403, 404}
        # RT-WP-06 跨租户
        assert a.get("/projects", tenant=TENANT_B).status_code in {403, 404}
        # RT-WP-07 限流已在 TestRateLimitReal 验证


# ==================================================================
# §11 Forwarded Headers —— 最低安全假设
# ==================================================================


class TestForwardedHeadersReal:
    def test_app_does_not_trust_forwarded_for(self, wp, server):
        """应用层按 API Key 限流，伪造 XFF 无法影响判定。

        真正的可信链由反代保证（覆盖而非追加），见部署契约。
        本测试锁定应用层的**最低安全假设**：不因XFF 而改变权限。
        """
        a = wp(server["base"], KEY_A)
        # 伪造 XFF + 声称别的租户 —— 仍必须 403
        r = httpx.get(
            f"{server['base']}/projects",
            headers={
                "X-API-Key": KEY_A,
                "X-Tenant-ID": TENANT_B,
                "X-Forwarded-For": "127.0.0.1",
                "X-Forwarded-Proto": "https",
                "X-Real-IP": "127.0.0.1",
            },
            timeout=10,
        )
        assert r.status_code == 403, (
            f"伪造 forwarded headers 影响了授权判定：{r.status_code}"
        )
        # 自己的租户则正常（说明伪造头不会额外获得权限）
        assert a.get("/projects", tenant=TENANT_A).status_code == 200
