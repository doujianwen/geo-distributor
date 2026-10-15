# WordPress ↔ geo-distributor 最小真实集成验证

> 批次：Real Integration Verification（2026-10-06 15:50–16:10）
> 目的：不继续做理论性代码硬化，而是**用真实进程 + 真实 HTTP** 验证
> WordPress 能否作为商业入口安全调用 geo-distributor

---

## 0. 关键结论先行

> **验证方式升级本身抓到了两个 P0 缺陷 —— 单元测试全绿时它们完全不可见。**

| # | 缺陷 | 影响 | 为什么之前没发现 |
|:-:|---|---|---|
| **1** | `SQLiteRequestRepository` 缺 `find_by_id_unscoped` / `find_by_id_scoped` | **persist 模式下项目创建 100% 失败** | 单元测试用内存仓储，两个后端方法集不一致 |
| **2** | 安全响应头中间件 + 500 脱敏处理器**根本没写入** | 无安全头、500 会泄露内部细节 | 上一批脚本在断言处中断，误以为已写入 |

> **这两个缺陷都是「以为做了」而不是「没做」**。只有真实起进程才能证伪。

---

## 1. 验证方式：Option A（真实进程，非TestClient）

### 为什么必须真实进程

| | `TestClient`（其它测试） | 真实进程（本批次） |
|---|---|---|
| 网络栈 | 进程内直接调 ASGI | 真实 TCP 端口 |
| 端口绑定 | 无 | 内核分配真实端口 |
| 环境变量 | `monkeypatch` 注入 | 子进程独立环境 |
| 存储 | 内存仓储 | **SQLite（persist 模式）** |
| 反代配置错误 | 测不出 | 能测出 |
| 后端方法集不一致 | 测不出 | **能测出** ← 本批次抓到 P0 |

### 架构（无公网暴露）

```
WordPress 模拟客户端（httpx，真实 HTTP）
    │  TCP over 127.0.0.1
    ▼
geo-distributor 进程（真实 uvicorn，生产参数）
    │  认证 → 租户解析 → 授权 → 业务 → 审计
    ▼
SQLite（data/_integration_tmp/）
```

### 关于 TLS 的如实声明

本机**无 nginx、无证书、无 DNS**。按指令 §2 要求，**不为"完成测试"而伪造 TLS**。

| 项 | 状态 |
|---|---|
| 真实进程 | ✅ 已验证 |
| 真实 HTTP / TCP | ✅ 已验证 |
| 真实 SQLite persist | ✅ 已验证 |
| **真实 TLS** | ❌ **CONDITIONAL** —— 无证书基础设施 |
| **真实 nginx 反代** | ❌ **CONDITIONAL** —— 模板已就绪，未部署 |

用自签名证书在本机做 HTTPS 只会制造「看起来有 TLS」的假象，
实际不验证任何真实部署条件 —— 因此不这样做。

---

## 2. 被测配置（生产等价）

```
GEO_DISTRIBUTOR_ENV=production          # 禁用内置开发密钥
GEO_DISTRIBUTOR_API_KEYS=<一次性测试密钥># 不使用任何真实客户密钥
GEO_DISTRIBUTOR_DB=<临时目录>            # 不碰真实数据
GEO_DISTRIBUTOR_AUDIT_DB=<临时目录>
uvicorn --host 127.0.0.1 --no-server-header  # 与生产脚本一致
```

**身份模型**（复用既有 tenant 概念，未建第二套）：

| Tenant | API Key | Role |
|---|---|---|
| `WP-TENANT-A` | `sk-wp-integration-test-tenant-a-ONLY` | `DISTRIBUTOR_ADMIN` |
| `WP-TENANT-B` | `sk-wp-integration-test-tenant-b-ONLY` | `DISTRIBUTOR_ADMIN` |

---

## 3. 基础请求矩阵（Request A~F）

| # | 场景 | 期望 | 实测 |
|:-:|---|:-:|:-:|
| A | Tenant A 合法调用 | 2xx | ✅ 200 |
| B | A 访问 B 的资源 | 403/404 | ✅ |
| C | 无认证 | 401 | ✅ |
| D | 错误 secret | 401 | ✅ |
| E | 认证 A + header B | 403 | ✅ 且不回显 B |
| F | 认证 A + header A | 200 | ✅ |
| F2 | 认证 A + 无 header | 200 | ✅ 回落密钥 tenant |

---

## 4. 最小商业链路（§12）

```
WordPress → 认证 → 租户解析 → Delivery Engine → 结果 → 审计
```

**实测通过**：
1. `POST /projects` → 201，返回 `project_id` / `tenant_id` / `progress_percent` / `service_stage`
2. `GET /projects/{id}` → 200，读回一致
3. 审计库产生记录：`action=POST`、`outcome=OK`、`user_id`、`role`、`created_at` 齐全
4. **审计不含原始 API Key**

> 注意：审计的 `resource_type` 记录**请求路径**（如 `/projects`），
> `resource_id` 留空 —— 中间件不解析路径中的 ID。这是当前契约，
> 若将来需要按 ID 检索审计，需在端点层显式补 `record_auth_audit`。

---

## 5. 跨租户真实业务验收（§13 — 本批次最重要）

| 方向 | 操作 | 期望 | 实测 |
|---|---|:-:|:-:|
| A → A | 读自己的项目 | 200 | ✅ |
| **A → B** | 读 B 的项目 | 拒绝 | ✅ |
| **B → A** | 读 A 的项目 | 拒绝 | ✅ |
| A → B | 读 B 的客户 | 拒绝 | ✅ |
| A → B | 删 B 的项目 | 拒绝 | ✅ 且 B 资源完好 |
| A + 伪造 header B | 越权 | 403 | ✅ |

**结论：WordPress 修改任何 ID 或 header 都无法越权。服务端租户解析是唯一权威。**

---

## 6. 审计轨迹（§7）

| 场景 | 期望 | 实测 |
|---|---|:-:|
| 成功写操作 | actor/tenant/action/resource/result/timestamp 齐全 | ✅ |
| 审计不含原始 API Key | 必须 | ✅ |
| 跨租户攻击 | `DENIED` 留痕 | ✅ |
| 攻击者审计不含受害方 tenant | 必须 | ✅ |
| 认证失败 | 留痕 | ✅ |
| **认证失败时 tenant 不可信 → 留空** | 不信攻击者提交值 | ✅ |

> 最后一条是重点：攻击者提交 `X-Tenant-ID: SPOOFED-TENANT` 但密钥错误时，
> 审计**不会**把该声明当作可信身份记录 —— 否则审计库本身就成了攻击者的写入通道。

---

## 7. 限流（§8，真实 HTTP 连续请求）

| 验证 | 期望 | 实测 |
|---|---|:-:|
| 连续请求超阈值 | 429 | ✅ |
| 限流前请求 | 全部 200 | ✅ |
| **Tenant A 被限流，Tenant B** | **不受影响** | ✅ |
| 429 含 `Retry-After` | 必须 | ✅ |
| 429 不泄露堆栈/路径/密钥 | 必须 | ✅ |

**已知限制（如实记录）**：当前为 **process-local 令牌桶**。
多实例部署时总额度 = 配置 × 实例数。已记录在部署契约 §9，**未引入 Redis**。

---

## 8. API 暴露（§9）

| 端点 | 期望 | 实测 |
|---|---|:-:|
| `/docs` | 404 | ✅ |
| `/openapi.json` | 404 | ✅ |
| `/redoc` | 404 | ✅ |
| `/health` | 仅 `{"status":"ok"}` | ✅ 无 db_path / 路径 / 内部状态 |

**安全响应头**（应用层，不依赖反代）：

| 头 | 状态 |
|---|:-:|
| `X-Content-Type-Options: nosniff` | ✅ |
| `X-Frame-Options: DENY` | ✅ |
| `Referrer-Policy: no-referrer` | ✅ |
| `Content-Security-Policy: default-src 'none'` | ✅ |
| `Server` / `X-Powered-By` | ✅ 已移除 |

> `Server` 头由 uvicorn 在 **ASGI 层之外**注入，应用层中间件**删不掉**。
> 必须在服务器层关闭 → `start_api_prod.sh` 加了 `--no-server-header`。
> 反代侧 `server_tokens off` 作为第二层。

---

## 9. 后端隔离（§10 / RT-WP-08）

| 验证 | 结果 |
|---|:-:|
| 回环地址可访问 | ✅ |
| 非回环地址 | ✅ 不可达（或本机仅有回环时skip） |
| 生产脚本 `--host` | `127.0.0.1`（非 `0.0.0.0`） |

---

## 10. Forwarded Headers（§11）

| 测试 | 期望 | 实测 |
|---|---|:-:|
| 伪造 `X-Forwarded-For` + 声明他人 tenant | 仍 403 | ✅ |
| 伪造 `X-Forwarded-Proto` / `X-Real-IP` | 不影响授权 | ✅ |
| 自己 tenant + 伪造头 | 200（不额外获权） | ✅ |

**责任划分**（锁定在部署契约 §5）：
- 应用层**按 API Key** 限流，不按 IP → 伪造 XFF 无法绕过
- 反代层**覆盖**（非追加）forwarded headers → 可信链由反代保证

---

## 11. Red Team（RT-WP-01 ~ RT-WP-10，全部真实 HTTP）

| ID | 场景 | 结果 |
|:-:|---|:-:|
| RT-WP-01 | 无认证 → 401 | ✅ |
| RT-WP-02 | 错误密钥 → 401 | ✅ |
| RT-WP-03 | tenant header 欺骗 → 403 | ✅ |
| RT-WP-04 | project_id 伪造 → 拒绝 | ✅ |
| RT-WP-05 | client_id 伪造 → 拒绝 | ✅ |
| RT-WP-06 | 跨租户项目 → 拒绝 | ✅ |
| RT-WP-07 | 限流 + 租户隔离 | ✅ |
| RT-WP-08 | 后端仅内部可达 | ✅ |
| RT-WP-09 | 文档端点 → 404 | ✅ |
| RT-WP-10 | health 无信息泄漏 | ✅ |

---

## 12. 修掉的两个 P0 缺陷

### P0-1：SQLite 仓储方法集不一致

```
AttributeError: 'SQLiteRequestRepository' object has no attribute 'find_by_id_unscoped'
→ projects.py:122 create_project → approve_scope → 500
```

**影响**：persist 模式下**所有项目创建 100% 失败**（即生产模式完全不可用）。
**根因**：B-3 批次我只在内存仓储加了 `find_by_id_unscoped` / `find_by_id_scoped`，
SQLite 版本没同步。单元测试用内存仓储 → 完全测不到。

**修复**：补齐两个方法，并用 `inspect` 做了**三对仓储的方法集一致性检查**
（Request/Project/Client）—— 现仅差测试辅助方法 `clear`。

**教训**：`TestClient` + 内存仓储的组合会系统性屏蔽「后端不一致」这类缺陷。
凡是有多个实现（内存/SQLite、mock/real），必须有真实实现的集成测试。

### P0-2：安全中间件与 500 脱敏从未写入

上一批的编辑脚本在 `assert s.count(a)==1` 处中断，
我误以为「改动已生效」（因为后续 `grep` 显示 `_EXPOSE_DOCS` 存在）。

**实际**：`security_headers_middleware` 与 `unhandled_exception_handler` **不存在**。
响应体实测暴露 `Server: uvicorn`，且无任何安全头。

**修复**：立即补齐，并让集成 fixture 用**生产启动参数**（`--no-server-header`），
确保测的是真实生产配置而非测试配置。

**教训**：「脚本抛了异常」不等于「代码没改」也不等于「代码改了」——
必须用 `grep`/`py_compile`/真实请求**逐一确认落地**。我当时只验证了部分。

---

## 13. Full Regression

```
440 passed / 1 skipped / 1 failed / 2 warnings in 41.65s
```

| 项 | 值 |
|---|---|
| 本批次开始 | 418 passed / 1 skipped / 1 failed |
| 本批次结束 | **440 passed** / 1 skipped / 1 failed |
| 新增（集成测试） | **+22** |
| 删除 | **0** |
| 新增 skip / xfail | **0** |
| 安全测试弱化 | **0** |

**唯一 failed**：`test_prompt_integrity` — R-3 外部域，
`geo-collector.db` 于 15:07:07 被外部任务写入。**与本批次无关。**

---

## 14. Scope Integrity

| 对象 | 改动 | 证据 |
|---|:-:|---|
| `geo-intent-system` 代码 | **NO** | `app/database.py` sha256 `41bfd5dd` 一致 |
| `geo-intent.db` | **NO**（本批次） | mtime 15:14:23，早于本批次开始 15:50 |
| `geo-collector` | **NO** | mtime 15:07:07，早于本批次 |
| R-3 数据 | **NO** | 未触碰 |
| `geoflow` | **NO** | mtime 仍 2026-06-02 |
| commit / push | **0 / 0** | 未执行 |

### 变更归属

| 类别 | 内容 |
|---|---|
| **Pre-existing** | 51 项脏工作区（TD-11 / B-1 / B-2 / 审计 / 限流 / Hardening 批次） |
| **This batch** | `tests/integration/`（新）、`sqlite_repository.py`（补齐）、`api/app.py`（补中间件）、`start_api_prod.sh`（`--no-server-header`） |

---

## 15. Final Deployment Gate

### A. Code Security

| 项 | 状态 |
|---|:-:|
| Authentication | **PASS** |
| Tenant Isolation | **PASS** |
| Authorization | **PASS** |
| Audit | **PASS** |
| Rate Limit | **PASS** |
| CORS | **PASS** |
| Error Handling | **PASS**（本批次补齐 500 脱敏） |
| API Exposure | **PASS**（本批次补齐安全头） |

### B. Infrastructure

| 项 | 状态 |
|---|:-:|
| Production Startup | **PASS**（无 reload /绑回环 / 缺密钥拒启） |
| Backend Isolation | **PASS**（127.0.0.1，非回环不可达） |
| **HTTPS** | **CONDITIONAL** — 无证书基础设施 |
| **Reverse Proxy** | **CONDITIONAL** — 模板就绪，未部署 |
| **DNS** | **CONDITIONAL** — 外部条件 |
| **Certificate** | **CONDITIONAL** — 外部条件 |

### C. Real Integration

| 项 | 状态 |
|---|:-:|
| WordPress → HTTP → geo-distributor | **PASS** |
| 真实进程 / 真实 TCP | **PASS** |
| 生产环境配置 | **PASS** |
| 持久化后端（SQLite） | **PASS**（并因此抓到 P0 缺陷） |

### D. Business Flow

| 项 | 状态 |
|---|:-:|
| Authenticated request | **PASS** |
| Tenant resolution | **PASS** |
| Delivery Engine 执行 | **PASS** |
| Result 返回 | **PASS** |
| Audit 留痕 | **PASS** |
| **Cross-tenant双向拒绝** | **PASS** |

---

## 16. 最终结论

> # CONDITIONAL PASS — Ready for controlled deployment
>
> 代码安全 ✅ · WordPress HTTP 集成 ✅ ·跨租户 ✅ · 审计 ✅ · 限流 ✅
>
> 剩余全部是**真实基础设施**：DNS、正式证书、nginx 部署、真实主机、生产 hostname。
>
> **TLS 未在本机伪造** —— 用自签名证书做「假 HTTPS」不验证任何真实部署条件。

### 进入 Stage-1 Commercial Pilot 还需要

1. 部署到真实主机（Windows/Linux 均可，脚本已就绪）
2. 签发 TLS 证书 + 配置 nginx（模板：`deploy/nginx/geo-distributor.conf.example`）
3. 为 WordPress 生成生产密钥（**不要**用本批次的测试密钥）
4. WordPress 侧配置 CORS 白名单
5. 重跑本集成测试指向真实地址

**不需要**继续做代码层安全优化。
