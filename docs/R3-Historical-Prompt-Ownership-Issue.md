# R-3｜Historical Prompt Ownership / Semantic Mismatch

**登记日期**：2026-10-06
**登记阶段**：Phase 1-1（TD-11 审计链关闭时一并登记）
**状态**：**REGISTERED — 本轮不处理，禁止数据修改**
**严重度**：P1（不影响 Batch 1-3，但影响任何按 `prompt_id` 聚合的分析）

---

## 一、事实陈述（实测，非推断）

### F1 `prompt_id=1–50` 不能安全视为 BookConv-only namespace

```
SELECT brand, COUNT(*) FROM observations WHERE prompt_id<=50 GROUP BY brand;
→ Hydroviv: 287
  bookconv: 204
```

全表分布：`Hydroviv 545` / `bookconv 204`

### F2 历史 Hydroviv observation 直接占用 1–50 槽位

`prompt_id 1–50` 区间内Hydroviv 观测的 `observation_id` 日期前缀分布：

| 日期前缀 | 条数 |
|---|---:|
| `20260907` | 260 |
| `20260906` | 15 |
| `20260905` | 12 |
| **合计** | **287** |

按 prompt_id 展开（前20个槽位）：

| prompt_id | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | 11 | 12 | 13 | 14 | 15 | 16 | 17 | 18 | 19 | 20 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Hydroviv 观测 | 15 | 15 | 15 | 15 | 15 | 15 | 15 | 15 | 15 | 15 | 15 | 15 | 14 | 14 | 14 | 14 | 13 | 13 | 13 | 13 |

### F3 这些 observation 没有 `HYDRO_` 前缀

```
prompt_id=1 的 observation_id 样例：
  20260905_chatgpt_p001
  20260906_chatgpt_p001
  20260907_chatgpt_original_A1_R1_S008
  20260907_chatgpt_original_A1_R2_S032
  20260907_chatgpt_original_A1_R3_S053
```

对比本次迁移写入的 72 条：`HYDRO_20260905_chatgpt_p001` 等（**有前缀**）

### F4 prompt text 与 observation brand/content 存在语义错位

| prompt_id | prompt text | observation brand | observation content |
|---:|---|---|---|
| 1 | `epub to pdf`（BookConv） | **Hydroviv** | `If you're in the **San Jose, California area**, I…`（water filter） |
| 17 | `reader app`（BookConv） | **Hydroviv** | water filter 相关回答 |

### F5 交叉污染量化

```
prompt_id <= 50 且 brand LIKE '%Hydroviv%'  →  287条
prompt_id >= 51 且 prompt_text 含 epub/ebook/mobi  →  0 条（干净）
```

---

## 二、根因（本次 TD-11 迁移**未造成**此问题）

时间线证据表明这是**历史遗留**：

```
2026-09-05~07  Hydroviv 采集写入 1-50 槽位（无前缀，共 287 条）
                ↓
              BookConv 后写入 1-50 槽位（prompt 覆盖/共存）
                ↓
2026-10-06     TD-11 迁移：新建 51-67 槽位 + HYDRO_ 前缀
               → 解决了「新增Hydroviv 数据」与「新增 BookConv 数据」的冲突
               → 但**未处理已在 1-50 槽位的 287 条旧 Hydroviv 观测**
```

> **TD-11 的修复范围是正确的**：它保证了新写入不再冲突。
> R-3 是 TD-11 范围**之外**的历史数据语义归属问题。

---

## 三、明确禁止的处理方式

以下做法**一律禁止**：

| # | 禁止动作 | 原因 |
|---|---|---|
| 1 | 删除这 287 条 observation | 销毁真实采集数据，不可逆 |
| 2 | 修改历史 observation 的 `brand` 字段 | 篡改历史事实 |
| 3 | 伪造 / 重写 `prompt_id` | 制造新的语义错位，且破坏 `observation_id` 与 prompt 的对应关系 |
| 4 | 用新 prompt 文本覆盖 1–50 段 | 会破坏 BookConv 侧的真实 prompt 定义 |
| 5 | 清洗历史数据前未建模型 | 见第四节 |

---

## 四、未来处理 R-3 的前置条件

**必须先建立以下链路模型**，否则禁止任何数据操作：

```
observation
    → source batch（采集批次）
    → brand ownership（品牌归属）
    → prompt ownership（prompt 归属）
    → migration policy（迁移策略）
```

### 建模前需回答的问题

| # | 问题 |
|---|---|
| Q1 | 2026-09-05/06/07 三批采集的原始 prompt 定义保存在哪里？（`geo-collector` 已冻结，是否有更早备份？） |
| Q2 | BookConv 的 1–50 prompt 是什么时候写入的？是覆盖还是与Hydroviv 共存？ |
| Q3 | 这 287 条观测在业务上应归属 Hydroviv 还是 BookConv？（其 `brand` 字段与 `prompt_text` 矛盾） |
| Q4 | 是否需要在不修改历史数据的前提下，引入「有效 prompt 归属」派生视图？ |
| Q5 | 该问题的处理是否影响 `geo-intent-system` 的 Observation 导入？（**若影响 → 触发 Run#5 Freeze 变更流程**） |

---

## 五、对当前工作的影响边界

| 事项 | 是否受 R-3 影响 |
|---|---|
| Phase 1-1 Batch 1（B-5 CORS / B-7 remote） | ❌ 不受影响 |
| Batch 2（B-1 tenant isolation） | ❌ 不受影响 |
| Batch 3（B-2 认证 / B-3 假门禁） | ❌ 不受影响 |
| `test_prompt_integrity` 测试 | ❌ 已通过（fixture 与 51-67 段对齐） |
| 按 `prompt_id` 聚合的 GEO 分析 | 🔴 **受影响** — 1-50 段结果会混入跨品牌数据 |
| Hydroviv 历史趋势分析 | 🔴 **受影响** — 需同时查 1-20 段与 51-67 段 |

---

## 六、状态

```
R-3 Status = REGISTERED
Data modified = NO（本轮零数据操作）
Blocked on = 链路模型建立（第四节）
Owner = 待用户裁定
```

**本轮不推进。** 待用户决定是否立项。
