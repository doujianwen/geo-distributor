# ADR-009 — Website Lead Intake Boundary & Assignment Queue

| 项 | 值 |
|---|---|
| **状态** | ACCEPTED（U2 Lead Integration Closure 授权范围内） |
| **日期** | 2026-10-09 |
| **授权来源** | 用户执行令「Commercial V1 — U2 Lead Integration Closure」§2/§3 |
| **影响面** | `api/`（新增 router + state 接线）、`geo_distributor/persistence/`（新增 intake queue store） |
| **不改动** | `geo_distributor/models/*`、`geo_distributor/repositories/*`、`services/delivery.py`、`geo-intent-system` |

---

## 1. 背景（READ 实测事实）

Commercial V1 Gate 的唯一阻塞项是**环节 2「Website Lead → Distributor 自动接入」**（PARTIAL）。

READ 阶段核实到三条硬事实，决定了本 ADR 的取舍：

1. **`ServiceRequest` 是 distributor 侧唯一的规范「商业需求入口」实体**，
   但它**预设已知 `tenant_id` + `client_id`**，且 `ProjectService.submit_request()` 会立即驱动
   `Intake → SCOPING → SCOPE_PENDING_APPROVAL`，最终 `approve_scope()` 生成 Project。
   → 它描述的是**已成立的需求**，不是**尚未归属的来客线索**。
2. 官网 Lead 是**匿名来客**：**无 tenant、无 client**，只有姓名/公司/邮箱/域名/诉求。
   直接塞进 `ServiceRequest` 会：① 伪造一个不存在的 client；② 让 Intake 直接推进到 SCOPING，
   跳过「人工分配」这一商业决策。
3. `IdempotencyGuard` 存在但是**死代码**（`state.py` 实例化后从未接线），且是**进程内内存**，
   不满足 §4-12「服务重启后仍可恢复」。

---

## 2. 决策

**新增一个最小「Lead Intake Queue（HQ 待分配队列）」，作为 `ServiceRequest` 的*上游暂存*，
而不是第二套商业领域模型。**

具体：

### 2.1 不新增领域模型（dataclass）

- **不**在 `geo_distributor/models/` 新增任何 `Lead` dataclass。
- 队列条目以**纯 dict payload** 存储，复用既有 `SQLiteJSONRepository`
  —— 该类文档明示定位为 *"Persistent store for service projections; **no new domain entity**"*，
  与 `reports_projection` / `measurements_projection` 同一模式。
- 队列**没有**自己的状态机引擎、没有 Client/Project/Report 语义；它只记录
  「一条来客线索当前处于哪个接入/分配阶段」。

> 因此这不是「第二套 Lead 领域模型」：它是**暂存队列**，唯一的下游出口是既有的
> `Client` / `ServiceRequest` / `Project`。商业语义仍由既有实体承载。

### 2.2 用「租户归属」表达「是否已分配」（关键安全设计）

- 未分配线索一律写入固定租户 **`HQ-INTAKE`**。
- `HQ-INTAKE` **不对应任何渠道商密钥**（渠道商密钥绑定 `GEO-TENANT-A/B`）。
- 分配后，队列条目的 `tenant_id` 由 `HQ-INTAKE` **改为该渠道商租户**。

推论（无需额外鉴权代码即成立）：

- 渠道商 `GET /leads` 只按 `auth.tenant_id` 过滤 → **永远看不到 `HQ-INTAKE` 的未分配线索**。
- 跨租户读取由既有 `resolve_tenant` 语义拦截。
- HQ（`can_cross_tenant`）显式查询 `HQ-INTAKE` 才能看到待分配队列。

满足 §3：「未分配线索不得被普通渠道商批量查看」。

### 2.3 幂等：持久化，不用内存 guard

- 幂等判定基于**持久化查表**（`source` + `source_lead_id`，或 `idempotency_key`），
  **不**依赖 `IdempotencyGuard`（内存、重启即失）。
- 重复提交 / 重试 → 返回既有 `lead_id` + `deduplicated: true`，**不新建**。

### 2.4 分配规则：默认人工，不虚构算法

- **无自动分配算法、无佣金政策、无路由规则**（§3 明确禁止虚构）。
- 默认：所有来客线索进入 `HQ-INTAKE` 的 `pending_assignment` 队列，**由 HQ 人工分配**。
- 提供最小 `assign` 端点（HQ only），可选在同一步创建 `Client`。

---

## 3. 被否决的替代方案

| 方案 | 否决理由 |
|---|---|
| **A. 直接把 Lead 塞进 `ServiceRequest`** | 需伪造 client_id；Intake 会直接推进到 SCOPING，跳过人工分配；匿名线索的 contact 字段在 `BusinessContext` 中无处安放（会污染模型语义） |
| **B. 新建 `models/lead.py` dataclass + 独立状态机** | 违反「不新增第二套 Lead 领域模型」；引入第二套状态机，与 `ServiceRequest` 状态机并存，正是 Canonical §2 禁止的「第二套」 |
| **C. 只在 WordPress 侧排队，distributor 不落库** | 不满足 §3「HQ 能查看未分配线索」「分配审计」「渠道商只能看分配给自己的线索」；也不满足 §4-6/7/8 |

---

## 4. 契约（Contract）

### 4.1 队列条目 payload

```jsonc
{
  "lead_id": "LEAD-1A2B3C4D",          // 服务端生成，稳定
  "source": "website",                  // 来源系统
  "source_lead_id": "42",               // 来源系统内的 ID（wp_ggs_leads.id）→ 幂等键
  "idempotency_key": "sha256:...",      // 备用幂等键
  "created_at": "2026-10-09T10:00:00",
  "updated_at": "2026-10-09T10:00:00",
  "intake_status": "pending_assignment", // 见 4.2
  "service_type": "diagnostic",          // 原始 type
  "service": "visibility_audit",         // 映射到 ServiceRequest.service
  "contact": { "name": "", "company": "", "email": "", "domain": "" },
  "message": "",
  "tenant_id": "HQ-INTAKE",              // 未分配 = HQ-INTAKE；分配后 = 渠道商租户
  "project_id": "",                      // 转项目后填充（SQLiteJSONRepository 需要该列）
  "assigned_tenant_id": "",
  "client_id": "",
  "request_id": "",
  "audit": [ { "at": "...", "actor": "...", "action": "intake|assign|convert", "from": "...", "to": "...", "note": "" } ]
}
```

### 4.2 状态取值（§3 七态映射）

| §3 要求 | `intake_status` |
|---|---|
| 新线索 | `new` |
| 待人工分配 | `pending_assignment` |
| 已分配渠道商 | `assigned` |
| HQ 直管 | `hq_managed` |
| 已转客户 | `converted_client` |
| 已转项目 | `converted_project` |
| 接入失败待重试 | **WP 侧** `intake_status='pending_retry'`（distributor 侧不产生该态） |

### 4.3 端点

| 方法 | 路径 | 鉴权 | 说明 |
|---|---|---|---|
| POST | `/leads` | **HQ only（服务端到服务端）** | 接入一条来客线索 → 存 `HQ-INTAKE`/`pending_assignment`；持久化幂等 |
| GET | `/leads` | 认证 | HQ：可查 `HQ-INTAKE` 待分配队列（`?status=`）；渠道商：仅本租户已分配 |
| GET | `/leads/assignable-tenants` | **HQ only** | 返回已注册渠道商租户 ID（不返回密钥），供 HQ 分配界面选择 |
| GET | `/leads/{lead_id}` | 认证 | 详情，租户作用域（HQ 可跨） |
| POST | `/leads/{lead_id}/assign` | **HQ only** | 分配至渠道商租户（可选同时建 `Client`） |

**不新增**：佣金 / 自动路由 / 批量分配 / 复杂 RBAC。

### 4.4 身份边界

```
Browser ──?──  永不接触 API Key
WordPress（服务端）──HTTPS(本机 loopback)──> POST /leads ── X-API-Key ──> distributor
                                                              │
                              tenant 绑定为唯一真源；lead 固定落 HQ-INTAKE
                                                              ▼
                                    渠道商租户只能看 tenant_id == 自己的行
```

- API Key 仅存 `wp-config.php`（唯一 secret 落点），**不进浏览器/HTML/JS/URL/日志**。
- 日志/审计**不记录**完整敏感联系信息（email 在审计中不落明文；见实现）。
- 失败重试为 **WP → distributor 单向**，失败时 Lead 已在 WP 库，不丢。

---

## 5. 影响与回滚

- 新增文件：`geo_distributor/persistence/lead_store.py`、`api/routers/leads.py`
- 修改文件：`api/state.py`（接线 `lead_repo`）、`api/app.py`（注册 router）、
  `geo_distributor/persistence/sqlite_repository.py`（`SQLiteJSONRepository` 追加 `list_by_tenant` / `find_by_field`）
- WP 侧：`geo-growth-leads.php`（dbDelta 加列 + 推送钩子 + 后台重试）、`wp-config.php`（常量）
- **回滚**：删除新增文件 + 还原 `app.py`/`state.py` 接线即回到基线；WP 侧删列不影响原功能（新列可空）。

## 6. U2 实施与验收记录（2026-10-09）

### 6.1 实施范围

- `api/routers/leads.py`：官网 Lead 接入、HQ 待分配查询、HQ 人工分配、关联 Client/ServiceRequest/Project 转换；接入只允许 HQ 角色。
- `geo_distributor/persistence/sqlite_repository.py` 与 `json_store.py`：新增 `create_if_absent`，重复请求不会覆盖已分配/已转换状态。
- `api/auth.py`：只暴露已注册渠道商 tenant ID 集合，不暴露密钥。
- `api/ui.py`、`ui/app.js`：BFF 白名单加入 `/leads`；新增 HQ 线索分配页和渠道商“我的线索”页，浏览器不接触 API Key。
- WordPress `geo-growth-leads.php`：schema v2、先本地落库后服务端推送、失败保留并标记 `pending_retry`、每 5 分钟最多重试 10 条、管理员 nonce 保护的手动重试；错误只保存 `transport_error` / `http_NNN` 等安全分类。

### 6.2 实测验收

- U2 Phase A：`T-01..T-10` 与 `E2E-A` 全部 PASS；覆盖本地落库、真实 HTTP 自动接入、重复提交幂等、远端不可用时保留、重试、HQ 待分配队列、租户隔离、Client/Project 来源关联、密钥不进入浏览器/日志，以及完整交付闭环。
- U2 Phase B：服务重启后 `T-12` 与 `E2E-B` PASS；Lead/Client/Project/Measurement/Report 可读回，接口状态码均为 200。
- 当前 `u2_results.json` 中 `T-12` 与 `E2E-B` 各重复记录一次；按唯一用例 ID 归一后，**13 个唯一场景全部 PASS**。回归套件（排除已知外部 prompt-integrity mismatch）通过；未过滤的完整套件仍有 1 个既有外部失败，不将其伪装成全绿。
- WordPress U2 本地 stub 验证：成功回写远端 ID、远端失败时线索仍在本地且进入 `pending_retry`；临时测试行已清理。
- 实际 WP → API 只读探针：`/health` = 200，`GET /leads` = 200；API 仅绑定 `127.0.0.1`。

### 6.3 当前判定与边界

- **Local Commercial E2E Gate：8/8 PASS**（Website → Lead → HQ/Distributor Assignment → Client → Project → HQ Delivery → Measurement → Report → Authorized Distributor View）。
- **Production Launch Gate：仍 BLOCKED**。本次没有配置公网 DNS/TLS、没有发布站点；`blog_public=0` 继续保留。不得声称网站 LIVE 或公开环境已验收。
- **Notion：未同步**；Canonical 与 Notion Sync Payload 仍需在连接恢复后同步。

