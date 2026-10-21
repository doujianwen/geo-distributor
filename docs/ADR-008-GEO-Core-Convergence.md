# ADR-008 — GEO Core 收敛（Single GEO Core Ownership）

> 2026-10-20 用户后续授权增补：两个历史产品已按总部自营关系直接接入原核心库，保留历史行并安装旧写路径围栏；未复制并行可写历史库。见 [真实接入验收](REAL-IDENTITY-HISTORY-ACCEPTANCE-20261020.md)。以下早期“本批次未迁移”是早期裁决时点；本次接入不改变公网生产 BLOCKED，也不将未实施的自动任务收敛宣布完成。

> 2026-10-20 增补：V2.2 专业作业台复用唯一核心，并通过受保护命令允许明确授权的个人在隔离工作区执行人工操作；不再将专业作业全部限制为只读展示。见 [实施验收记录](OPERATOR-WORKSPACE-IMPLEMENTATION-ACCEPTANCE-20261020.md)。本增补不执行原真实历史迁移，不改变本 ADR 的 PROPOSED 状态，也不证明原双核心已全面收敛或旧写入口已经切换。

| 项 | 值 |
|---|---|
| **状态** | `PROPOSED`（本批次**未执行**任何数据迁移/删除；迁移须在用户批准后单独批次执行） |
| **日期** | 2026-10-09 |
| **决策依据** | Commercial V1 执行令 · Decision A；上一轮 Red Team #6/#7（FAIL） |
| **取代** | 无（首次确立唯一归属） |
| **影响范围** | `geo-distributor` · `geo-intent-system` · 相关冻结规则与测试 |

---

## 1. Context — 为什么需要这份 ADR

Commercial V1 的架构原则规定：

> **Distributor sells; HQ delivers.**
> 禁止：第二套 GEO Core / 第二套 Measurement / 第二套 Report / 第二套 Client·Project。

上一轮红队审计（2026-10-09）实测发现**该原则已被违反**：

- `geo-distributor` 持有：`models/geo_core.py`（Evidence / Report）+ `services/measurement_analysis.py` + `services/intervention_loop.py` + `services/evidence_library.py`，并在 `docs/05-HQ技术交付架构_V0.1.md` 中把 **M4 GEO Core** 定义为自有的 canonical pipeline。
- `geo-intent-system` 持有：Growth Loop 数据模型（10 Core Entities）+ `observations`/`evidence`/`diagnoses`/`actions`/`deltas` 等 41 张表。
- 两者**并存且未收敛**，构成「第二套 GEO Core」。

同时，`2026-09-29` 的本地统一决策（`GEO-Growth-Loop-V1.0-Decision-20260929.md`）已明确：

> geo-collector 的测量能力**并入 `geo-intent-system`**；实施前必须做 Schema Gap Audit，**禁止重复建设第二套** Product / Site / Question / Observation / Run。

本 ADR 将该决策正式固化为架构裁定。

---

## 2. Decision

> **`geo-intent-system` 是 GEO 业务核心语义（GEO Core）的唯一归属方。**
> `geo-distributor` 保留渠道商、客户、项目、服务请求、权限、交付协调与**适配**职责，**不再持有独立的 GEO 核心实现**。

### 2.1 职责边界（收敛后）

| 层 | 系统 | 职责 |
|---|---|---|
| GEO Core（唯一） | **geo-intent-system** | Measurement · Observation · Evidence · Diagnosis · Action · Delta · Attribution 的**唯一**领域模型与存储 |
| 商业/渠道层 | geo-distributor | Tenant · User · Client · ServiceRequest · Project · WorkItem · 状态机 · 权限 · 交付协调 · **对 Core 的适配/契约** |
| 呈现层 | geo-distributor Portal UI（新） | 只读投影 + 商业动作入口；不持有技术真相 |
| 网站 | geo-growth-site | Lead 捕获（P0-1） |

---

## 3. 重复实体清单与唯一所有者

| # | 实体 | geo-distributor 现有位置 | geo-intent-system 现有位置 | **唯一所有者（裁定）** | 处置 |
|---|---|---|---|---|---|
| 1 | Observation | `compatibility/base.py` PlatformObservation | `observations` 表（139 行） | **geo-intent-system** | distributor 保留**契约/映射**，删除独立存储 |
| 2 | Evidence | `models/geo_core.py` Evidence(E0–E4) | `evidence` 表（413 行） | **geo-intent-system** | 同上；E0–E4 分级作为**分级口径**并入 Core |
| 3 | Measurement | `services/measurement_analysis.py` | Growth Loop MeasurementRun | **geo-intent-system** | distributor 改为**读取** Core 的 Measurement |
| 4 | Diagnosis | geo_core 链路 | `diagnoses` 表（17 行） | **geo-intent-system** | 同上 |
| 5 | Action / Delta | `services/intervention_loop.py` | `actions`(2) / `deltas`(12) | **geo-intent-system** | 同上 |
| 6 | Question / Prompt | `Prompt` 模型 | `questions`(309) / `rank_observations`(495) | **geo-intent-system** | distributor 不再定义 Question |
| 7 | **Report** | `models/geo_core.py` Report + `services/delivery.py` | 无（intent-system 无 Report） | **geo-distributor**（保留） | Report 是**商业交付物**，属渠道层；但内容须源自 Core |
| 8 | Client / Project / Request | `models/client.py` `project.py` `request.py` | 无 | **geo-distributor**（保留） | 唯一所有者，不迁移 |

> **关键区分**：Report / Client / Project / Request 属**商业层**，归 distributor（无重复）；Observation / Evidence / Measurement / Diagnosis / Action / Delta / Question 属**GEO Core**，归 intent-system（有重复，需收敛）。

---

## 4. 读写路径与 API 契约（目标态）

```
geo-growth-site (WP)
   │  Lead (P0-1)
   ▼
geo-distributor  ── ServiceRequest / Client / Project / Report（商业层，自有存储）
   │  ▲
   │  │  Adapter（只读 + 命令）
   ▼  │
geo-intent-system ── GEO Core（Measurement / Observation / Evidence / Diagnosis / Action / Delta）
```

### 4.1 契约（Adapter，目标态）

| 方向 | 调用 | 说明 |
|---|---|---|
| distributor → core | `POST /measurements`（触发一次测量运行） | 由 Core 执行；distributor 只传 Scope |
| distributor ← core | `GET /measurements/{run_id}` | 读 Observation/Evidence/Measurement 结果 |
| distributor ← core | `GET /diagnoses?run_id=` | 读诊断 |
| distributor ← core | `GET /actions?project_ref=` | 读行动项与 Delta |
| distributor（自有） | `/clients` `/projects` `/reports` | 商业层，不经 Core |

> **本批次不实现该 Adapter**（属迁移批次）。此处只固化契约方向，避免二次返工。

### 4.2 兼容策略

- 现有 `api/` 六个 router（clients/projects/measurements/reports/sync/distribution）**契约保持不变**。
- `measurements` router 现状（读 `state._measurement_results` 进程内字典）**暂保留**，但标注为 `LEGACY / TO BE REPLACED BY CORE ADAPTER`。
- 冻结的 Stage-1 集成（WordPress bridge → `/projects`）**不受影响**。

---

## 5. 迁移步骤（分阶段，**本批次均不执行**）

| 阶段 | 动作 | 破坏性 | 前置 |
|---|---|---|---|
| M0 | 本 ADR 获批 | 无 | 用户批准 |
| M1 | 在 intent-system 侧补齐 Core 的**对外只读 API**（measurements/diagnoses/actions） | 无 | M0 |
| M2 | distributor 新增 **Core Adapter 客户端**（只读），与现有 measurement 路径**并存**（feature flag） | 无 | M1 |
| M3 | 逐项切换读取源到 Adapter；旧路径保留 fallback | 低 | M2 + 契约测试通过 |
| M4 | 移除 distributor 的独立 Measurement/Evidence/Diagnosis 计算实现（保留契约定义） | **中（不可逆）** | M3 + 全量回归绿 |
| M5 | 删除重复数据表/文件 | **高（不可逆）** | M4 + 备份 + 用户显式批准 |

> **M4/M5 属高风险不可逆动作，按执行令要求「暂停该动作并报告」。**

---

## 6. 数据一致性与回滚

| 项 | 方案 |
|---|---|
| 一致性 | 迁移期间以 **intent-system 为写入权威**；distributor 侧旧存储转为只读镜像，避免双写分歧 |
| 回滚点 | M3/M4 前对 `geo_intent.db` 与 distributor `data/*.db` 做完整备份（放 datadir 外） |
| 回滚方式 | 撤销 Adapter feature flag → 回到旧读取路径；数据未删除时零损失 |
| 不可逆边界 | 仅 M5（删表）不可逆；M4 以下均可回滚 |

---

## 7. 受影响的冻结规则与测试

| 资产 | 影响 | 处置 |
|---|---|---|
| `STAGE1-CODE-FREEZE.md` §5 保护不变量 | 「`geo-intent-system` 修改 = 0」将被 M1/M2 打破 | 需在 M0 获批时**显式修订**该不变量（改为「除 ADR-008 授权的 Core API 增补外修改 = 0」） |
| `STAGE1-CODE-FREEZE.md` §5 「不新增…微服务」 | Adapter 属**新增集成**，非微服务拆分 | 判定为**不违反**（Adapter 是客户端，不是新服务） |
| distributor 测试 `test_measurement*` / `test_evidence*` / `test_intervention_loop*` | M4 后需迁移到 Core 侧 | 迁移批次处理，本批次**不动** |
| intent-system 129 tests | M1 新增 API 需补测试 | 迁移批次处理 |
| B3 表单契约（website） | 无影响 | — |

---

## 8. 本批次（2026-10-09）实际执行与未执行

**已执行（非破坏性）**：
- ✅ 本 ADR 落盘
- ✅ 在 distributor `docs/` 标注重复实体与归属（文档层）

**明确未执行（高风险/不可逆，按执行令暂停）**：
- ❌ 未删除任何表或数据
- ❌ 未迁移任何数据
- ❌ 未修改 intent-system 任何代码/DB
- ❌ 未重构 distributor 的 GEO Core 实现

**风险清单（待批准后处理）**：
1. `state._measurement_results` 为**进程内字典**（非持久化）——与 P0-4 冲突，见 Gap。
2. `geo-intent-system` 修改 = 0 的冻结不变量与 M1 冲突，需修订。
3. Adapter 契约需两侧同时实现，跨仓库协同成本高。

---

## 9. Consequences

**正面**：消除第二套 GEO Core；测量/证据/归因单一真相；Report 与商业实体归属清晰；符合 Commercial V1 架构原则。

**负面/成本**：跨仓库协同；冻结不变量需修订；迁移批次有不可逆步骤。

**替代方案（已否决）**：
- 反向（把 intent-system 并入 distributor）——intent-system 有真实数据（139 obs / 413 evidence / 495 rank_obs）与冻结基线，风险更高。
- 维持双核心——直接违反架构原则，且越建越乱（已发生 6 类重复）。
