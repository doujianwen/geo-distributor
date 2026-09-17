# 海外 GEO 分销系统｜Report Contract & Delivery Standards V0.1

> Status: DESIGN BASELINE
> Version: V0.1
> Date: 2026-09-13
> Scope: 双报告模型规范、Client-safe 语言约束、交付物标准
> Reference: [01-总体架构](./01-海外GEO分销系统_总体架构与角色边界_V1.0.md), [03-Service Contract](./03-海外GEO分销系统_Service_Contract_V0.2.md), [05-HQ技术交付架构](./05-HQ技术交付架构_V0.1.md)

---

## 1. 文档目的

定义 HQ Technical Delivery System 输出的两份报告的格式、内容规范、语言约束，以及 "Client-safe" 判定标准。

核心原则：

> 技术真相不因客户可读性而被污染；商业语言不因技术严谨性而失去说服力。

---

## 2. 双报告模型

### 2.1 报告类型

| 报告类型 | 受众 | 目的 | 可见范围 |
|----------|------|------|----------|
| **HQ Technical Report** | HQ 内部 / QA / 审计 | 技术完整记录、可复核、可追溯 | HQ 团队 |
| **Client Report** | Distributor / Client | 商业交付、行动指导、关系维护 | Distributor + Client |

### 2.2 报告关系

```
HQ Technical Report
       │
       │ 投影 + 过滤
       ▼
 Client Report
```

Client Report 是 Technical Report 的**安全可读投影**，不是独立事实来源。

---

## 3. HQ Technical Report 规范

### 3.1 结构

```
┌─────────────────────────────────────────┐
│ HQ Technical Report                     │
├─────────────────────────────────────────┤
│ 1. Sampling Environment                 │
│    - Browser / Provider / Timestamp     │
│    - Network conditions                 │
│    - Session metadata                   │
│                                         │
│ 2. Query Set                            │
│    - Query ID / Text / Category         │
│    - Intent / Location                  │
│    - Source (HQ-defined / Client-provided)│
│                                         │
│ 3. Provider / Engine Info               │
│    - Provider ID                        │
│    - Version                            │
│    - API endpoint                       │
│                                         │
│ 4. Raw Evidence                         │
│    - Answer text                        │
│    - Screenshot reference               │
│    - Source URLs                        │
│    - Citation data                      │
│                                         │
│ 5. Observation                          │
│    - Brand mention status               │
│    - First mention position             │
│    - Recommendation level               │
│                                         │
│ 6. Measurement                          │
│    - brand_position                     │
│    - citation_count                     │
│    - authority_citation_count           │
│    - geo_score                          │
│                                         │
│ 7. Validity                             │
│    - data_quality_score                 │
│    - sampling_completeness              │
│    - environment_consistency            │
│                                         │
│ 8. Diagnosis                            │
│    - verdict (PASS / WARN / FAIL)       │
│    - summary                            │
│    - findings (structured)              │
│    - root_cause_hypotheses              │
│    - confidence_score                   │
│                                         │
│ 9. Intervention                         │
│    - action_type                        │
│    - target_page                        │
│    - effort_estimate                    │
│    - expected_impact                    │
│                                         │
│ 10. Experiment Protocol                 │
│     - hypothesis                        │
│     - baseline                          │
│     - observation_window                │
│     - confounders                       │
│                                         │
│ 11. Re-measurement (if applicable)      │
│     - before / after comparison         │
│     - observed_change                   │
│                                         │
│ 12. Interpretation                      │
│     - observed_effect                   │
│     - causal_claim_limitation           │
│     - next_steps                        │
└─────────────────────────────────────────┘
```

### 3.2 存储格式

- JSON 结构化数据（不可变，Append-only）
- Screenshot 文件引用（不内嵌 Base64）
- Raw Response 原始备份

---

## 4. Client Report 规范

### 4.1 结构

```
┌─────────────────────────────────────────┐
│ Client Report                           │
├─────────────────────────────────────────┤
│ Executive Summary                       │
│ - 3-5 句话概述当前状态                  │
│ - 不含技术术语                          │
│                                         │
│ Current Visibility                      │
│ - 可视化图表（进度条 / 评分卡片）        │
│ - 简单数字（如：在 3/5 引擎中被提及）   │
│                                         │
│ Key Findings                            │
│ - 最多 5 条                             │
│ - 每条含：现象 + 影响                   │
│ - 不含技术细节                          │
│                                         │
│ Why（原因解释）                         │
│ - 为什么 AI 没选我们 / 推荐不足         │
│ - 用业务语言而非技术语言                │
│                                         │
│ Recommended Actions                     │
│ - 优先级排序                            │
│ - 每条含：动作 + 预期效果               │
│ - 不含技术实现细节                      │
│                                         │
│ Progress                                │
│ - 如果有历史对比：Before vs After       │
│ - 如果没有：仅当前状态                  │
│                                         │
│ Observed Change                         │
│ - 如有 Re-measurement                   │
│ - 标注："观察到 X% 改善"               │
│ - 明确："不代表因果保证"                │
│                                         │
│ Next Steps                              │
│ - 短期行动建议                          │
│ - 长期策略方向                          │
└─────────────────────────────────────────┘
```

### 4.2 视觉规范

- 使用简单图表（进度条、评分卡、对比表）
- 颜色：🟢 正面 / 🟡 中性 / 🔴 需关注
- 字号不小于 12pt
- 每页不超过 3 个信息模块

---

## 5. Client-safe 判定标准

### 5.1 允许内容（Client-safe）

| 内容 | 条件 |
|------|------|
| 品牌提及状态 | ✅ 可直接显示 |
| 提及位置 | ✅ 可简化为"前 3 位"等 |
| 综合评分 | ✅ 可显示，但需有说明文字 |
| 关键发现 | ✅ 不超过 5 条，无技术细节 |
| 推荐行动 | ✅ 不含技术实现 |
| 前后对比 | ✅ 需标注"观察到的变化" |

### 5.2 禁止内容（Non-Client-safe）

| 内容 | 原因 |
|------|------|
| RawResponse 原文 | 技术调试数据 |
| 证据评分细节 | 方法论内部逻辑 |
| Parser 输出 | 技术实现细节 |
| 有效性引擎内部状态 | 技术实现细节 |
| 浏览器自动化日志 | 技术实现细节 |
| Evidence 等级判定过程 | 方法论内部逻辑 |
| Query 生成算法 | 方法论知识产权 |
| 调试数据 | 技术实现细节 |

### 5.3 灰区内容（需判断）

| 内容 | 判定规则 |
|------|----------|
| 引用来源 URL | ✅ 可显示（外部可访问） |
| 置信度分数 | ⚠️ 需简化，加说明文字 |
| Root Cause Hypothesis | ⚠️ 可显示，但不标"E2 证据" |
| Sampling 环境说明 | ⚠️ 简化为"测试时间/浏览器" |

---

## 6. 商业承诺纪律

### 6.1 允许的表达

> - "增加品牌在 AI 驱动的发现、考虑与选择过程中的可见性"
> - "当前在 3/5 目标引擎中有品牌提及"
> - "观察到 X% 的改善（基于重测对比）"
> - "建议优先优化以下页面"

### 6.2 禁止的表达

> - ❌ "保证被 AI 推荐"
> - ❌ "保证获得流量"
> - ❌ "保证增加客户"
> - ❌ "保证收入增长"
> - ❌ "控制 AI 推荐结果"
> - ❌ "排名第一"
> - ❌ "进入 AI 答案首位"
> - ❌ "确保品牌可见性 100%"

### 6.3 因果声明约束

| 声明类型 | 允许条件 |
|----------|----------|
| "观察到变化" | 有 Re-measurement 数据 |
| "改善 X%" | 有 Before/After 对比 |
| "由干预导致" | 有 Controlled Experiment 设计 |
| "因果效应" | E4 以上证据，且经 CEO 批准 |

**默认规则**：无 Re-measurement = 只能报告当前状态，不得做前后对比。

---

## 7. 报告版本与变更

### 7.1 版本规则

- 每次 Delivery 生成新版本报告
- 旧版本归档，不覆盖
- Report ID 带版本号：`RPT-001-V001`

### 7.2 Revision vs Scope Change

| 类型 | 定义 | 流程 |
|------|------|------|
| **Revision** | 文字修改、格式调整、解释补充 | Distributor 发起 → HQ 执行 |
| **Scope Change** | 改变价格/范围/周期/市场/Engine | Distributor 发起 → Client 确认 → 新 Scope |

### 7.3 触发条件

**Revision 触发**：
- Client 要求解释某条发现
- 报告文字有歧义
- 格式调整请求

**Scope Change 触发**：
- 新增 Engine
- 扩展 Market
- 增加 Service Stage
- 改变 Deliverable Set

---

## 8. QA Checkpoint

### 8.1 报告输出前 QA 检查

| 检查项 | 通过标准 |
|--------|----------|
| Evidence Completeness | 所有 Key Finding 有对应 Evidence |
| Measurement Correctness | 数值与 Observation 一致 |
| Diagnosis Consistency | 结论与证据匹配 |
| Report Correctness | 无技术术语泄露 |
| Client-safe Language | 无禁止表达 |
| Commercial Claim Compliance | 无过度承诺 |
| Scope Compliance | 内容与 Technical Scope 一致 |

### 8.2 QA 失败处理

- QA FAIL → 返回 Diagnosis Engine 修复
- 修复后重新 QA
- 记录 QA Issue Log

---

## 9. 报告模板（Client Report 示例）

```markdown
# GEO Visibility Report — [Client Name]

## Executive Summary
[3-5 句话概述]

## Current Visibility
| Engine | Mentioned? | Position |
|--------|-----------|----------|
| ChatGPT | ✅ Yes | 2nd |
| Google AI | ❌ No | N/A |
| Perplexity | ✅ Yes | 5th |

**Overall Score: 65/100** 🟡

## Key Findings
1. 品牌在 ChatGPT 中有提及，但位置靠后
2. Google AI 完全未提及品牌
3. 引用来源以自有页面为主，第三方权威性不足

## Why
[用业务语言解释原因]

## Recommended Actions
1. **高优先级**：优化首页 About 页面，增加权威引用
2. **中优先级**：建立行业媒体合作关系
3. **低优先级**：完善 FAQ 页面，覆盖目标关键词

## Progress
[如有历史对比]

## Next Steps
[短期行动建议]
```

---

## 10. 实施优先级

| 优先级 | 功能 |
|--------|------|
| P0 | Client Report 模板生成 |
| P0 | QA 检查清单 |
| P1 | Report Versioning |
| P1 | Revision Workflow |
| P2 | Visual Charts（进度条/评分卡）|
| P2 | Export to PDF |
| P3 | Multi-language Support |
