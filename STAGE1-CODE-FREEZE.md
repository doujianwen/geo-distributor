# Stage-1 Commercial Pilot — Code Freeze / Baseline

| 项 | 值 |
|---|---|
| **声明日期** | 2026-10-06 16:42 (GMT+8) |
| **声明依据** | 用户 David Dou 正式确认（CONFIRMED） |
| **当前状态** | `CONDITIONAL PASS` — CODE AND REAL INTEGRATION READY; INFRASTRUCTURE PENDING |
| **处置** | **STOP DEVELOPMENT**。冻结 Code / Integration baseline，等待真实公网基础设施条件。 |

> 这不是开发中系统。真实 WordPress 商业集成链路已被跑通并经红队验证。
> 继续修改业务代码 = 破坏已验证基线。

---

## 1. 冻结基点（Baseline Reference）

- **Git HEAD（最后提交）**：`d61fa08`（4 commits）
- **被验证的真实状态**：当前 **working tree** as of 2026-10-06 16:42
  - 工作树含 Sprint-4 遗留的未提交修改（`api/app.py`、`api/routers/*`、`geo_distributor/*` 等 `M`，及 `config/prompts_hydroviv.json` `D`）。这些是 Stage-1 **之前**已存在、非本批次产生。
  - **被验证的 `440 passed` 回归即在此工作树状态下跑通**。故「冻结基线」= 当前工作树整体，而非 `d61fa08` 单独快照。
- **未执行 commit / push**（遵循 STOP 指令）。
  - 后续如需正式快照：先提交 Sprint-4 遗留改动 → 再打 `git tag stage-1-pilot-baseline`。此动作由用户决定，Agent 不自动执行。

---

## 2. 已被真实证明的部分（Real Validation，非理论）

- WordPress 7.1 + PHP 8.2.12 + Apache + MariaDB **真实运行**
- `WP → Apache → geo-distributor → WP` 完整真实链路打通
- WordPress **服务端调用**，不向浏览器暴露 Key
- Tenant Isolation：**PASS**
- Auth / Authorization：**PASS**
- Audit：**PASS**（ALLOW / DENIED / 认证失败 全留痕，两密钥均未出现）
- Secret non-leakage：**PASS**（插件内 0 / HTTP 响应 0 / 审计库 0 / Git 0）
- Rate Limit：**PASS**（`[200×5, 429×4]` 精确匹配 burst，Tenant-B 不受影响）
- RT-01 ～ RT-14：**全部 PASS**
- 集成测试：**22 passed**
- 回归：**`440 passed / 1 skipped / 1 failed`**
- 唯一失败项已明确归类为 **EXTERNAL / OUT OF SCOPE**
- `geo-intent-system` 修改 = 0
- `geo-collector.db` 修改 = 0
- `geo_intent.db` 修改 = 0
- 未复用 GEOFlow（reuse = 0）
- 未删除测试 / 未增加 skip / 未增加 xfail
- 公网后端暴露 = 0
- 密钥进入代码 / HTTP 响应 / 审计库 / Git = 0

---

## 3. 唯一剩下的 3 个条件（全部外部基础设施）

| 条件 | 当前状态 | 性质 |
|---|---|---|
| TLS / HTTPS | Pending | 基础设施 |
| DNS | Pending | 基础设施 |
| 公网主机部署 | Pending | 基础设施 |

**不为这 3 项修改业务代码。**

---

## 4. 停止开发纪律（STOP DEVELOPMENT）

```
现在
  ↓
STOP DEVELOPMENT
  ↓
冻结当前 Code / Integration baseline
  ↓
等待真实公网基础设施条件（TLS + DNS + 公网部署）
  ↓
重新做一次 Deployment Gate（RT-01~14 + 限流 + 审计 + 回归 + 暴露面）
  ↓
Commercial Pilot
```

---

## 5. 受保护不变量（Protected Invariants）

- `geo-intent-system` 修改 = 0
- `geo-collector.db` 修改 = 0
- `geo_intent.db` 修改 = 0
- 未复用 GEOFlow（reuse = 0）
- 未删除测试 / 未增加 skip / 未增加 xfail
- 公网后端暴露 = 0
- 密钥进入代码 / HTTP 响应 / 审计库 / Git = 0
- **不新增**：Redis / K8s / Docker 化 / OAuth-OIDC / SSO / CRM / Billing / SaaS IAM / 复杂 RBAC / 用户中心 / 复杂 WP 插件 / 多服务拆分 / 微服务 / 消息队列

---

## 6. 重新 Gate 触发条件（Re-Gate Trigger）

仅当以下**全部就绪**时，重启 Deployment Gate：

1. 真实 TLS 证书已签发并挂载（HSTS 在真实 HTTPS 正常后启用）
2. 真实 DNS 已解析至部署主机
3. 真实公网主机已部署（非同机 loopback，后端仍只绑内部地址）

重启后须重跑：RT-01~14 + 限流 + 审计 + 回归 + 暴露面检查。
Gate 通过后才进入 Commercial Pilot。

---

## 7. R-3 外部失败的处理（保持不变）

`test_prompt_integrity` 维持 **EXTERNAL / OUT OF SCOPE**：

- 根因：`geo-collector.db` mtime `15:07:07` 早于本批次 `16:20`（外部遗留状态）
- 保持：不修改数据、不 skip、不 xfail、不删除测试
- 最终报告区分：`Code / Deployment failures` vs `External historical data failure`

---

## 8. 关联文档

- `docs/STAGE1-PILOT-FINAL-GATE.md` — 完整 Gate 证据（含实测输出）
- `docs/DEPLOYMENT-CONTRACT.md` — 部署契约（FACT / ASSUMPTION / UNKNOWN 标注）
- `deploy/apache/geo-distributor-pilot.conf` — Apache 反代模板
- `E:/xampp/htdocs/wp-content/mu-plugins/geo-distributor-bridge.php` — WP 服务端桥接（零密钥）
- `E:/xampp/apache/conf/extra/httpd-vhosts.conf` — 已挂载的 vhost（运行时配置）
- `E:/xampp/apache/conf/httpd.conf` — 已启用 proxy 模块 + `ServerTokens Prod`

---

## 9. Commercial V1 有限解冻记录（2026-10-09 追加）

> **本节为追加记录，不修改上文任何既有结论。** 上文的 `CONDITIONAL PASS` 与「STOP DEVELOPMENT」在
> **无新授权时仍然有效**；本节记录的是用户在执行令中**显式授权**的例外范围。

### 9.1 授权来源

用户下达「WorkBuddy｜Commercial V1 落地执行令」，其中：

- **Decision B** = 渠道商 UI 有限解冻（允许新建 Distributor Portal UI）
- **Decision D** = Partner 页纳入 Website P0
- **P0-3 / P0-4** = 要求补齐 HQ 交付链路与持久化可追踪性

授权性质：**范围受限的解冻**，不是解除冻结。

### 9.2 本批次实际修改（Before → After）

| 文件 | 类型 | 说明 |
|---|---|---|
| `api/ui.py` | **新增** | BFF：会话 + `/ui/proxy/*` + 静态资源。浏览器**零持有** API Key |
| `ui/index.html` / `ui/app.css` / `ui/app.js` | **新增** | 渠道商控制台前端（零依赖，CSP 合规） |
| `api/app.py` | 修改 | 挂载 ui router；审计中间件跳过 `/ui/*` |
| `api/routers/reports.py` | 修改 | 修 `ReportOut` 投影（原正常路径必 500）+ `state.report_service` |
| `api/routers/clients.py` | 修改 | portal 端点改用 `state.report_service` + `report_to_out` |
| `api/routers/projects.py` | 修改 | 新增 `POST /projects/{id}/deliver`（强制 HQ） |
| `api/routers/measurements.py` | 修改 | 新增 `measurement_id` + 落库 + GET 回落持久化 |
| `api/state.py` | 修改 | 新增 `measurement_repo` |
| `geo_distributor/persistence/sqlite_repository.py` | 修改 | `id_key` 参数化 |

### 9.3 本批次**明确未触碰**（保持冻结）

- ❌ `geo_distributor/services/delivery.py`（`version` 硬编码所在）
- ❌ `geo_distributor/models/*`、`geo_distributor/repositories/*`
- ❌ `sprint4-lab/cases/**`（采集样本，mtime 仍为 2026-09-18）
- ❌ 主题文件、`wp-config.php`、物理 `robots.txt`
- ❌ `geo-intent-system`（修改 = 0）
- ❌ 任何测试的删除 / skip / xfail（测试总数 **442 = 基线 442**）

### 9.4 §5 受保护不变量的复核结果

| 不变量 | 复核 |
|---|---|
| `geo-intent-system` 修改 = 0 | ✅ 近 24h 修改文件为空 |
| `geo-collector.db` 修改 = 0 | ✅ mtime 仍 `2026-10-06 15:07:07` |
| `geo_intent.db` 修改 = 0 | ✅ mtime 仍 `2026-09-14 22:28:14` |
| 密钥进入代码 / HTTP / 审计库 / Git = 0 | ✅ 本批次测试密钥全仓扫描零命中 |
| 未删除测试 / 未增加 skip / xfail | ✅ 442 = 442 |
| 公网后端暴露 = 0 | ✅ 绑定 `127.0.0.1:8791` |
| **不新增** Redis / K8s / OAuth-OIDC / SSO / CRM / Billing / SaaS IAM / 微服务 | ✅ 零新增依赖 |

### 9.5 §7 R-3 外部失败项的复核

`test_prompt_integrity` 维持 **EXTERNAL / OUT OF SCOPE**：根因 `geo-collector.db` mtime `2026-10-06 15:07:07` **实测未变**，与本批次无关。

### 9.6 解冻的收敛条件

本解冻**不改变** §6 的 Re-Gate 触发条件。Commercial V1 的 Gate 判定见
`E:/xampp/COMMERCIAL-V1-ACCEPTANCE-REPORT-V1.0.md`：
**P0 范围内 4/4 达成**，但 **Commercial Ready Gate 7 PASS + 1 PARTIAL → 未通过**（阻塞项：Website Lead → Distributor 自动接入）。

### 10. U2 Lead Integration Closure（2026-10-09）

本节记录在明确授权的 U2 范围内完成的有限解冻；不改变 §6 的生产 Re-Gate 条件。

#### 10.1 本批次允许变更

- `api/auth.py`：查询已注册渠道商 tenant ID（不暴露密钥）。
- `api/routers/leads.py`：HQ-only intake、待分配查询、人工分配、Client/ServiceRequest/Project 转换关联。
- `geo_distributor/persistence/sqlite_repository.py`、`json_store.py`：稳定 ID 的 `create_if_absent`，避免重复提交覆盖状态。
- `api/ui.py`、`ui/app.js`：BFF 允许 `/leads`，新增 HQ 线索分配 / 渠道商我的线索视图。
- WordPress `geo-growth-leads.php`：schema v2、服务端推送、失败保留、限量 WP-Cron 重试、管理员手动重试。
- 新增测试与追加文档；不改 `services/delivery.py`，不改 `geo-intent-system`。

#### 10.2 冻结不变量复核

| 不变量 | U2 结果 |
|---|---|
| `geo-intent-system` 修改 = 0 | PASS |
| `geo-collector.db` / `geo_intent.db` 未触碰 | PASS（U2 未修改） |
| 交付服务 `services/delivery.py` 未修改 | PASS |
| 浏览器/URL/日志不含 API Key | PASS（U2 T-10） |
| 未分配 Lead 对渠道商不可见；跨租户读取失败 | PASS（T-07/T-08 + API tests） |
| WordPress 验收测试行清理 | PASS：`wp_ggs_leads` 当前 0 行 |
| 公网暴露 | 0：U2 API 绑定 `127.0.0.1:8765` |

#### 10.3 Gate 更新

- U2 Phase A：`T-01..T-10` + `E2E-A` PASS。
- U2 Phase B：`T-12` + `E2E-B` PASS（跨重启读取）。
- 唯一 ID 归一后 U2 为 13 个 PASS 场景；原始结果因重复执行 Phase B，`T-12`/`E2E-B` 各重复一次。`T-11` 未在原始 U2 脚本定义，回归结果单独报告。
- Website P0 verifier 11/11 PASS；U2 API-focused tests 6/6 PASS；PHP lint 4/4 PASS。
- 回归：排除已知外部 `test_prompt_integrity.py::test_shipped_prompts_file_matches_live_datasource` 后通过；未过滤套件仍保留该 1 个 EXTERNAL / OUT OF SCOPE 失败，不声称全套无例外全绿。
- **Local Commercial E2E Gate 更新为 8/8 PASS。** 该结果 supersede §9.6 中旧的 `7 PASS + 1 PARTIAL` 快照。
- **Production Launch Gate 仍 BLOCKED**：未做 DNS/TLS/公网部署，站点仍为本机预发布状态。



