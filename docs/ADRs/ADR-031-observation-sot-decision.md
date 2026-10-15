# ADR-031｜Observation唯一 SoT 归属裁定（Phase 0-B 唯一剩余阻断项）

**日期**：2026-10-06
**状态**：🟠 **PROPOSED — 待用户批准**（本 ADR 为红队推荐，非既成决定）
**关联**：ADR-005 observation-first、ADR-007 evidence-first、ADR-030（归属裁定）
**取代**：`docs/BC_v0.1.md` §5 的 D-1 / D-3 裁定（若本 ADR 获批）

---

## 一、Context：两份裁定互相冲突，且都未废止

Phase 0-B 实测发现自有资产内部存在**架构合同冲突**：

| 时间 | 文件 | 裁定内容 | Status |
|---|---|---|---|
| 2026-09-13 | `ai-visibility-system/docs/BC_v0.1.md` §5 D-1/D-3 | `geo-intent-system` = **Query Generator only**；Measurement/Observation 归 `ai-visibility-system` | 🟠 PROPOSED（未冻结） |
| 2026-09-29/30 | `GEO-Growth-Loop-V1.0-Decision-20260929.md` + Round 3 Freeze | Observation / Evidence / Diagnosis / Action / Publication **全部落地 `geo-intent-system`** | ✅ FROZEN，129 测试 |

`geo-intent-system/docs/BOUNDARY-AND-LEGACY-RULING-2026-09-13.md` §1 同样声明：
> ❌ 本系统不得自行声明 Measurement 结果… ❌ 本系统不得产出或输出任何 "AI 回答"

**但事实已经追上了那份文档** — `geo-intent-system` 现在持有 129 条 observations + 392 条 evidence + 17 条 diagnoses，且通过了 Round 3 全部 129 项测试。

---

## 二、实测证据矩阵

| 维度 | geo-intent-system | ai-visibility-system | FACT |
|---|---|---|---|
| **Observation** | 表 `observations`，**129 条** | Pydantic `Observation`（`core/observation/models.py:57`） | 双实现 |
| **Evidence** | 表 `evidence`，**392 条**<br>AI_RESPONSE 129 / HTML_SNAPSHOT 129 / SCREENSHOT 82 / SEARCH_RESULT 52 | `Evidence` 仅 `excerpts[]`，无DB 落表 | geo-intent 独占持久化 |
| **Citation** | 表 `citations`，**711 条** | 仅 `citations: list` 字段占位 | geo-intent 独占 |
| **Measurement** | 表 `measurement_runs`，**4 条** | `MeasurementResult` + MP_v0.1 协议 + P01-P07 原则 | **协议 ai-vis 成熟；实例 geo-intent** |
| **Diagnosis** | 表 `diagnoses`，**17 条** + Diagnosis Model V1.0 | ❌ 无 | geo-intent 独占 |
| **Attribution** | 表 `deltas`，**8 条** | `ADR-008-Attribution-Unit` 文档 | 双实现 |
| **Publication** | 表 `publications`，**1 条** + Publication Model V1.0 冻结 | ❌ 无 | geo-intent 独占 |
| **Validation语义** | `citation_count / mention_status` | **三值枚举** `Visibility / Recommendation / Integration`（含 `is_real_negative()` P02 Gate） | **语义不同构，ai-vis 更精细** |
| **数据库** | SQLite，**38 张表** | SQLAlchemy，**仅 RawResponse 1 表** | geo-intent 强|
| **API** | **89 端点** | ❌ 零 | geo-intent 独占 |
| **Web 前端** | ✅ `static/` 原生 JS SPA | ❌ 零 | geo-intent 独占 |
| **Tests** | **129 passed**（Round 3 冻结） | 10 个测试文件 |双测试 |
| **当前调用方** | GEO 系统开发进度.md 作为「内容运营层」被引用 | **零外部调用**（全盘 grep 无任何系统 import） | ⚠️ ai-vis 是孤岛 |
| **最后提交** | 2026-09-30 21:43 | 2026-09-14 07:57（**已 22 天无提交**） | geo-intent 活跃 |

### 决定性结构证据

`geo-intent-system/app/database.py` 的 `observations` 表**已内置多源接入通道**：

```sql
source_system            TEXT,
source_observation_id    TEXT,
UNIQUE(source_system, source_observation_id)
```

实测 129 条的 `source_system` 取值分布：

| source_system | 条数 |
|---|---:|
| `geo-collector` | 129 |

> **通道已建，但尚未接入第二个数据源。**
> 这说明 2026-09-29的 Growth Loop 决策在设计时**已预见多源并存**，
> 只是当时唯一可用源是已冻结封存的 geo-collector。

---

## 三、Options 分析

### Option A — `geo-intent-system` 为唯一 SoT，`ai-visibility-system` 降为 Protocol/Adapter

**支持证据**：
1. ✅ Growth Loop V1.0 已冻结落地 geo-intent，129 测试在跑，10 核心实体齐备
2. ✅ 89 端点 + 38 表 + Web 前端，是唯一具备生产承载能力的实现
3. ✅ `source_system` 通道已存在，接入无需改schema
4. ✅ 唯一持有 Diagnosis / Action / Publication / Citation
5. ✅ 已合并 geo-collector 的 587 observations / 587 citations（BookConv 126 canonical obs / 331 evidence）

**反对证据**：
1. ⚠️ ai-vis 的三值枚举语义（Visibility ≠ Recommendation ≠ Integration）比 geo-intent 的 `mention_status` 更精细
2. ⚠️ BC_v0.1 D-1 明确禁止 geo-intent 自行声明 Measurement 结果

### Option B — `ai-visibility-system` 为唯一 SoT

**反对证据（决定性）**：
- ❌ 零 API、零 Web 前端、Storage 仅 1 张表
- ❌ 已 22 天无提交
- ❌ 零外部调用方（孤岛）
- ❌ 需从零建Diagnosis / Action / Publication / Citation 全部实体

> **不可行。**

### Option C — 两者长期并存

**反对证据**：
- ❌ `citations` 表 136 条 legacy 数据已证明双写灾难：REAL=0，58 条 LLM_GUESS + 14 条 SYNTHETIC + 3 条测试污染
- ❌ BC_v0.1 Q-3「接口物封闭原则」明令禁止任一系统重新定义另一系统负责的语义
- ❌ 两个Observation 实现语义不同构（`mention_status` vs 三值枚举），并存必然口径漂移

> **不可行。**双写是已付出代价的教训，不是可接受选项。

### Option D — 其中一个废弃/吸收

与 Option A 实操等价（吸收 = 角色重定义 + 协议保留），只是措辞更重。

---

## 四、Decision（推荐，待批准）

### Option D+：SoT 唯一化 + 协议保留

```
┌─────────────────────────────────────────────────────────────┐
│geo-intent-system  = Observation / Evidence / Diagnosis│
│                Action / Publication / Citation 唯一 SoT   │
│                状态：FROZEN（Round 3）                │
└─────────────────────────────────────────────────────────────┘
                          ▲
                          │ 唯一写入通道：source_system + source_observation_id
                          │ 禁止绕过此通道直连 observations 表
┌─────────────────────────────────────────────────────────────┐
│  ai-visibility-system = Measurement Protocol + Validity    │
│                        Engine 参考实现│
│                保留：MP_v0.1 / OBS_v0.1 / P01-P07│
│                      三值枚举语义 / Golden Dataset│
│                不持有业务数据，禁止成为写入源            │
└─────────────────────────────────────────────────────────────┘
```

### 角色分工的语义依据

| 实体 | 归属 | 理由 |
|---|---|---|
| **Observation / Evidence / Citation** | geo-intent | 唯一持久化实现 + 唯一 API + 唯一前端 |
| **Measurement 协议（MP_v0.1）** | ai-vis | 协议是知识资产，与实现分离 |
| **Validity Engine（P02 Invalid≠Negative）** | ai-vis | 纯规则引擎，无业务数据，可独立演进 |
| **Visibility/Recommendation/Integration 三值语义** | ai-vis | **比 geo-intent 更精细，必须保留** |
| **Diagnosis / Action / Publication** | geo-intent | 唯一实现 + 已冻结模型 |

### 对 BC_v0.1 D-1 / D-3 的处置

若本 ADR 获批：
- `BC_v0.1.md` §5的 D-1（geo-intent = Query Generator only）标记 **SUPERSEDED by ADR-031**
- `BOUNDARY-AND-LEGACY-RULING-2026-09-13.md` §1 的❌ 条款**保留但收窄**：
  - ✅ 保留：「不得引入 LLM Guess / Simulation 作为 Measurement Evidence 来源」
  - ✅ 保留：「不得引入 `query_id` 或同义别名（BC Q-1）」
  - ❌ 废止：「不得自行声明 Measurement 结果」— 因为 Growth Loop 已冻结落地，事实已变
  - 🔄 改写为：「Measurement **协议**（判定规则）归 ai-vis；Measurement **实例**（数据）归 geo-intent」

### 三值枚举的落地要求（本 ADR 的唯一新增技术债）

geo-intent 的 `observations` 表当前只有 `mention_status / recommendation_status`，
**缺 `integration_status`**。若采纳本裁定，需在**后续阶段**（非本阶段）评估是否补该字段。

> ⚠️ **本阶段不执行任何迁移。** 此项仅登记为 Known Issue，由用户在 Phase 1 决定是否立项。

---

## 五、Consequence

### 正向
1. 消除 BC_v0.1 与 Growth Loop 的合同冲突，架构文档恢复单一事实源
2. `geo-intent-system` 继续作为唯一 Intelligence SoT，**Run#5 Freeze 不受影响**
3. `ai-visibility-system` 的协议资产（MP_v0.1 / P01-P07 / Golden Dataset）**不被浪费**
4. `source_system` 通道成为唯一受控入口，天然防止双写

### 负向
1. ai-vis 系统**长期无业务数据**，需接受「协议参考实现」的定位（可能感觉像废弃）
2. 三值枚举与 geo-intent 的字段差异需在Phase 1 评估对齐
3. 两套文档需要同步维护（协议文档在 ai-vis，数据模型文档在 geo-intent）

---

## 六、Rollback

若用户不认可Option D+：
- 退而选Option C（并存）→ **不可接受**，已被 136 条 legacy citations 证据否决
- 或彻底冻结 Growth Loop、回到 Query Generator only → 需废止 Round 3 全部冻结资产，代价极高
- **建议：批准 Option D+**，这是唯一与既有事实（129 绿测在跑）一致的选项

---

## 七、待用户确认的问题

| # | 问题 |
|---|---|
| Q1 | 是否批准 Option D+（geo-intent为 Observation SoT，ai-vis 为 Protocol 参考）？ |
| Q2 | `BC_v0.1.md` D-1/D-3 是否可标记为 `SUPERSEDED by ADR-031`？ |
| Q3 | 三值枚举的 `integration_status` 缺失，是否登记为 Phase 1 候选技术债？ |

---

## 八、Evidence 索引

| 证据 | 路径 |
|---|---|
| 冲突裁定 1 | `ai-visibility-system/docs/BC_v0.1.md` §5 D-1/D-3 |
| 冲突裁定 2 | `E:/GEO项目/技术层/GEO-Growth-Loop-V1.0-Decision-20260929.md` |
| Boundary声明 | `geo-intent-system/docs/BOUNDARY-AND-LEGACY-RULING-2026-09-13.md` |
| observations DDL | `geo-intent-system/app/database.py`（含 `source_system` + UNIQUE） |
| 数据量实测 | `sqlite3 geo_intent.db` 只读 SELECT |
| Freeze 状态 | `geo-intent-system/ROUND3_FREEZE_STATUS.md` |
| ai-vis 模型 | `ai-visibility-system/core/observation/models.py:57`、`core/evidence/models.py:19` |
| 归属裁定 | `docs/ADRs/ADR-030-distributor-ownership-ruling.md` |