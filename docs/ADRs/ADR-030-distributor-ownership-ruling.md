# ADR-030｜geo-distributor 资产归属裁定与 Delivery Layer 基座决定

**日期**：2026-10-06
**状态**：✅ **ACCEPTED**（用户 2026-10-06 10:28 口头裁定，已记录）
**取代**：Phase 0-B 修正版 Red Team 中「geo-distributor = OWNERSHIP UNKNOWN」的临时判定
**关联**：ADR-001 own-the-core、ADR-005 observation-first、ADR-007 evidence-first

---

## 一、Context

Phase 0-B 架构 Red Team（2026-10-06）对本地5 个 GEO 相关系统做资产归属实测时，
对 `E:/GEO项目/技术层/geo-distributor` 得出三项相互矛盾的证据：

| # | 证据 | 指向 |
|---|---|---|
| 1 | `.git/config` 的 `remote.origin.url` = `https://github.com/doujianwen/geoseo-site.git` | 非独立仓库（remote 错配） |
| 2 | 全部 4 个 commit 的作者为 `WorkBuddy <workbuddy@local>`，最早 commit 为 2026-09-17「重建主仓库」 | 历史丢失，非原创起点 |
| 3 | `README.md` 声明「项目负责人（技术）：Gino」，`A1.6_V0.2_ARCHITECTURE.md` 记「经产品负责人（Gino）审核通过」 | 存在非 doujianwen 身份的负责人 |

**用户 2026-10-06 10:28 裁定**：

> geo-distributor 可以判为OWNED，里面提到的 gino，doujianwen，都是我自己，只是不同账户而已。

---

## 二、Decision

**`geo-distributor` 判定为 `OWNERSHIP = OWNED`，`ARCHITECTURAL_STATUS = ACTIVE`。**

同时确认：
- `Gino` 与 `doujianwen` 为**同一自然人的不同账户标识**，非第三方人员
- 因此证据 1/2/3 **不构成权属瑕疵**，仅是以下**运维事实**：
  - remote 错配（运维缺陷，非权属问题）
  - 2026-09-17 前的 git 历史因 aggressive GC 损坏永久丢失（不可恢复的事实）

### 连带裁定

| 资产 | 归属 | 状态 |
|---|---|---|
| `geo-intent-system` | `OWNED` | `FROZEN`（Round 3，129 测试） |
| `ai-visibility-system` | `OWNED` | 角色待ADR-031 重定义 |
| `geoseo-site` | `OWNED` | `PRODUCTION-READY`（未部署） |
| `geo-distributor` | `OWNED` | `ACTIVE` — **本ADR 新增** |
| `geoflow` | `THIRD_PARTY` | `REFERENCE_ONLY`（Phase 0-B 修正版已裁定，本 ADR 沿用） |
| WordPress（`E:/xampp/htdocs`） | `OWNED`（归属 geocitationblueprint.com） | `REFERENCE_ONLY`（非 GEO Growth System 资产） |

---

## 三、实测证据：为什么 geo-distributor 具备作 Delivery Layer 基座的资格

裁定后补做能力实测（只读），结果**推翻**了 Phase 0-B 修正版中
「多租户全缺」「Delivery Layer 自有资产 = 0」两项判断。

### 3.1 测试套件真实状态（2026-10-06 实跑）

```
1 failed, 308 passed, 1 skipped, 2 warnings in 6.42s
```

失败项：`tests/test_prompt_integrity.py::test_shipped_prompts_file_matches_live_datasource`
（`config/prompts_hydroviv.json` 中的 prompt 与实时数据源不一致 — 数据一致性问题，非架构缺陷）

### 3.2 多租户隔离**已实现且有测试保障**（修正「多租户全缺」）

`models/tenant.py`：`TenantStatus(ACTIVE/TRIAL/SUSPENDED/INACTIVE)`，`tenant_id` 为数据隔离最小单位
`SQLiteRepository._raw_find_by_tenant()`：所有 repo 的 `find_by_tenant` 强制带 `tenant_id`

`tests/test_redteam_tenant_isolation.py` 7 项测试：
```
test_tenant_a_cannot_read_tenant_b_client
test_tenant_b_cannot_update_tenant_a_client
test_tenant_b_cannot_delete_tenant_a_client
test_request_repo_tenant_isolation
test_correlated_id_attack          ← 关联 ID 越权攻击
test_project_repo_tenant_isolation
test_work_item_repo_tenant_isolation
```

### 3.3 Client-safe 输出边界**有测试保障**（支撑 ADR-027）

`tests/test_redteam_client_safe.py` 5 项：
```
test_client_report_cannot_expose_raw_response   ← ADR-027 强制
test_technical_report_can_have_internal_data
test_distributor_cannot_access_hq_internal_data
test_report_versions_are_immuttable
test_scope_cannot_be_mutated_after_approval      ← ADR-023 Technical Scope Freeze
```

### 3.4 幂等性已实现（ADR-025 Scope Change 的技术基础）

`guards/idempotency.py` + `tests/test_redteam_idempotency.py` 7 项，含并发测试：
```
test_same_key_same_payload_returns_original
test_same_key_different_payload_returns_conflict
test_expired_key_allows_new_request
test_no_partial_duplicate_on_failure
test_concurrent_requests
```

### 3.5 技术栈与引擎同族

| 项 | geo-distributor | geo-intent-system | 判定 |
|---|---|---|---|
| 语言/框架 | Python 3.12+ / FastAPI ≥0.141 | Python 3.12 / FastAPI ≥0.110 | ✅ **同栈** |
| 数据库 | SQLite（`geo_distributor.db`，含 `-wal`） | SQLite（`geo_intent.db`，含 `-wal`） | ✅ 同族 |
| 持久化 | `SQLiteRepository` + 4 个专用 repo | 原生 `sqlite3` | 可桥接 |
| Web 前端 | ❌ 无 | ✅ `static/` 原生 JS SPA | 可复用引擎前端 |
| 认证 | ❌ API 层无（见 Known Issues） | ❌ 无 | **双方共同缺口** |
| 依赖 | playwright/pyyaml/httpx/fastapi/uvicorn | fastapi/uvicorn/pydantic（仅 3 包） | dist 较重 |

> **结论**：geo-distributor 与 geo-intent-system **同为 FastAPI + SQLite**，
> 意味着 Delivery Layer 与 Intelligence Layer 之间**无需跨语言/跨栈集成**。

---

## 四、Consequence

### 4.1 正向

1. **Delivery Layer不再是「零自有资产」** — `clients / projects / measurements / reports / sync / distribution` 6 个 router 已通
2. **ADR-021~027 从「候选参考」升格为「自有架构合同」** — 本 ADR 确认其有效性
3. **多租户不需要自建** — tenant 隔离 + 7 项越权测试已覆盖
4. **Client-safe 报告边界不需要自建** — 对应「客户只能看Client-safe 结果」的商业红线

### 4.2 负向 / 新增义务

| # | 义务 | 说明 |
|---|---|---|
| 1 | **修remote 错配** | `.git/config` origin 指向 `geoseo-site.git`，存在误推风险 |
| 2 | **修 API 层认证缺口** | `api/app.py` 无任何认证中间件；`clients.py` 无 `Depends` |
| 3 | **修 CORS 自相矛盾** | `allow_origins=["*"]` + `allow_credentials=True` 在浏览器端必被拒 |
| 4 | **修 prompt 数据不一致** | 唯一失败测试项 |
| 5 | **裁定 Observation SoT** | 转ADR-031（Phase 0-B 唯一剩余阻断项） |

### 4.3 架构影响：Phase 0-B 推荐架构**改写**

Phase 0-B 修正版曾因geo-distributor 归属不明而推荐「D: 纯 Python 单体」（总分 32）。
归属确认后，**新增架构 F** 成为最优解：

```
Architecture F（推荐）
──────────────────────
  geoseo-site (Next.js 14)Marketing Layer — 保留 100%
            ↓
  geo-distributor (FastAPI + SQLite)  Delivery Layer — OWNED，308 测试
       clients / projects / reports / distribution / sync
            ↓ Command In → HQ → Result Out（ADR-024）
  geo-intent-system (FastAPI + SQLite)  Intelligence Layer — OWNED，FROZEN
       observations / evidence / diagnoses / actions / publications
            ↓
  ai-visibility-system (Protocol 参考)  Measurement Protocol / Validity 引擎
            ↓
  WordPress / geoflow  = REFERENCE_ONLY（下游分发渠道 / 参考实现）
```

**F 相对 D 的优势**：Delivery 层不是从零自建，而是复用 308 测试覆盖的既有骨架。

---

## 五、Rollback

本 ADR 为**裁定类**，无代码变更。若日后出现权属争议证据，回滚方式：
将 `ARCHITECTURAL_STATUS` 从 `ACTIVE` 改回 `UNKNOWN`，
并将 Architecture F 降级为 Architecture D（纯 Python 单体自建 Delivery）。

---

## 六、Known Issues（本 ADR 不解决，转入后续）

| # | 问题 | 严重度 | 建议 |
|---|---|:-:|---|
| 1 | `remote.origin.url` 指向 `geoseo-site.git` | 🔴 高 | 修正为独立仓库地址 |
| 2 | API 层零认证 | 🔴 高 | 加 API Key / Bearer 中间件 |
| 3 | CORS `*` + `allow_credentials=True` 矛盾 | 🟠 中 | 收敛为白名单 origin |
| 4 | `test_shipped_prompts_file_matches_live_datasource` 失败 | 🟠 中 | 同步 `config/prompts_hydroviv.json` |
| 5 | `settings.yaml` 中 `brand: "Hydroviv"` 为特定客户定制 | 🟡 低 | 多租户场景需参数化 |

---

## 七、Evidence 索引

| 证据 | 路径 / 命令 |
|---|---|
| 用户裁定 | 2026-10-06 10:28对话记录 |
| remote 错配 | `E:/GEO项目/技术层/geo-distributor/.git/config` |
| 测试实跑 | `pytest` → `1 failed, 308 passed, 1 skipped in 6.42s` |
| 租户隔离测试 | `tests/test_redteam_tenant_isolation.py` |
| Client-safe 测试 | `tests/test_redteam_client_safe.py` |
| 幂等测试 | `tests/test_redteam_idempotency.py` |
| 租户模型 | `geo_distributor/models/tenant.py` |
| 既有 ADR | `docs/ADRs/ADR-001` ~ `ADR-007`、`docs/09-ADR增量_V1.2.md` |