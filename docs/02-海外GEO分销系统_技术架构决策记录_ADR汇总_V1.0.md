# 海外 GEO 分销系统｜技术架构决策记录 ADR 汇总 V1.0

> Status: DECISION BASELINE  
> Version: V1.0  
> Date: 2026-09-13

## ADR-001｜Own the Core

### Decision
核心 GEO 数据模型、证据模型、诊断模型与解释层由本系统自己拥有。

### Canonical Core
```text
RawResponse
→ Observation
→ Measurement
→ Evidence
→ Diagnosis
→ InterventionHypothesis
→ Experiment
→ ReMeasurement
→ ObservedEffect
→ Interpretation
```

### Rationale
核心能力决定未来的方法论、数据资产、客户交付质量、多 Provider 能力与 Distributor 规模化，因此不能把 Canonical Model 绑定到某个第三方项目。

### Consequence
外部开源项目必须通过 Adapter 接入。

---

## ADR-002｜Compose at Explicitly Defined Boundaries

### Decision
采用：
> Compose at Explicitly Defined Boundaries

而不是 Compose Everything 或 Fork Everything。

### Rules
外部系统必须回答：
1. 它解决什么问题？
2. 它的输入是什么？
3. 它的输出是什么？
4. 哪些数据属于本系统 Canonical Model？
5. 哪些能力由外部系统拥有？
6. 如何替换外部系统？

不能因为“项目功能很多”就整体引入。

---

## ADR-003｜open-geo 作为 Measurement Adapter

### Decision
open-geo 定位为：
> High-Fidelity Measurement Adapter

而不是 GEO Core。

### Reason
open-geo 的优势包括真实浏览器环境、真实 AI 平台采样、QueryCapture、sources / citations 分离、screenshot、answer text、brand mention、source / citation rank、run artifact，适合 Observation-first / Evidence-first 架构。

### Integration Boundary

输入：
```text
Query
Engine
Lens
Sampling Environment
Run Context
```

输出：
```text
QueryCapture
```

再由本系统转换为：
```text
RawResponse
Observation
Measurement
Evidence
```

### 禁止
不能直接把 open-geo 数据库结构作为本系统 Canonical Model。

---

## ADR-004｜GeoLook 作为 Action / Verification Adapter

### Decision
GeoLook 不作为本系统 Core。

定位：
> Action / Verification Adapter + External Methodology Reference

### 可复用方向
- Action Ticket
- Owner
- Effort
- Acceptance Criteria
- Before / Current / Target
- Re-open
- Verification
- Delivery Package
- Content Workbench
- Site Audit
- Citation / Source analysis

### 风险
GeoLook 的 Verification 不等同于 Causal Effect。

因此：
> Verification Complete ≠ Intervention Caused Improvement

外部评分规则、方法规则也不能自动成为本系统 Canonical Methodology。

---

## ADR-005｜Observation First

### Decision
先保存 Observation，再进行 Measurement / Diagnosis。

### Principle
```text
Raw Response
↓
Observation
↓
Measurement
↓
Evidence
↓
Diagnosis
```

### Reason
避免直接从 AI Answer 推结论、丢失原始证据、无法复核、无法重新计算，以及不同 Provider 数据不可比较。

---

## ADR-006｜Evidence First

### Decision
任何客户可见的重要判断必须能够追溯到 Evidence。

### Evidence Maturity
```text
E0 Idea / Assumption
E1 Single Observation
E2 Repeated Observation
E3 Observed Effect
E4 Controlled / Comparative Evidence
E5 Commercial Outcome
```

### Rule
证据等级决定商业语言强度。

不能用 E1 / E2 的证据包装成 E4 / E5 的商业结论。

---

## ADR-007｜Distributor 不承担标准技术采样

### Decision
普通 Distributor 不执行：
- Sampling
- Measurement
- Diagnosis
- Technical Execution

### Reason
商业分销商的核心能力是市场、客户资源、销售与关系，而不是 Browser automation、Query design、Evidence evaluation、GEO methodology 与 Technical debugging。

让 Distributor 技术化会导致培训成本、质量不一致、交付瓶颈、方法论泄漏和客户结果不稳定。

### New Role
如果未来出现有技术能力的合作方，应单独定义：
> Technical Delivery Partner

不得与普通 Distributor 混为一谈。

---

## ADR-008｜HQ Technical Delivery Centralized

### Decision
Sampling、Measurement、Diagnosis、Technical Execution 默认集中 HQ。

### Benefits
- 统一方法
- 统一质量
- 统一 Query Strategy
- 统一 Evidence Standard
- 统一报告
- 规模化服务多个 Distributor

### Exception
只有明确授权的 Technical Delivery Partner 才可执行部分技术任务。

---

## ADR-009｜Two-System Architecture

### Decision
系统拆成：

### System A
HQ GEO Delivery System

### System B
Distributor Portal

### Contract
```text
Distributor Portal
      │ Service Request
      ▼
HQ Delivery System
      │ Delivery Result
      ▼
Distributor Portal
```

### Reason
商业系统和技术交付系统生命周期不同。

Distributor Portal 优先解决 Sales、Client、Project、Status、Report、Renewal；HQ System 优先解决 Measurement、Evidence、Diagnosis、Execution、Verification、Re-measurement。

---

## ADR-010｜Technical Truth Owned by HQ

### Decision
HQ 是技术 Source of Truth。

Distributor 可以消费：
- 状态
- Findings
- Recommendations
- Reports

Distributor 不拥有：
- RawResponse internals
- Parser
- Validity Engine
- Provider Adapter
- Experiment internals
- Debug data
- Full evidence grading

### Reason
避免技术版本分叉、方法论不一致、证据链破坏、白标后无法追责、Distributor 私自修改技术结论。

---

## ADR-011｜双报告

### Decision
系统输出两个层级：
1. HQ Technical Report
2. Client / Distributor Report

### Reason
内部技术审计需要完整证据；客户与 Distributor 需要可理解、可行动的信息。

不能为了客户可读性而破坏内部 Evidence Chain。

---

## ADR-012｜GrowthBook 暂不集成

### Decision
当前不接 GrowthBook。

先定义：
> GEO Experiment Protocol

模型：
```text
Experiment
├── hypothesis
├── target_query_set
├── baseline
├── intervention
├── intervention_date
├── observation_window
├── sampling_protocol
├── confounders
├── remeasurement
├── observed_effect
└── interpretation
```

### Reason
当前最大问题不是实验平台，而是 GEO Experiment Semantics 尚未完全冻结。

---

## ADR-013｜PostHog 定位

### Decision
PostHog 属于未来：
> Business Behavior Layer

不是 GEO Core。

可用于未来：
- AI referral
- website behavior
- lead
- conversion
- revenue events

当前只定义 Business Event Contract。

---

## ADR-014｜CRM 暂不建设

### Decision
当前不建设完整 CRM。

### Reason
尚未有足够真实客户量证明 CRM 是当前瓶颈。

先定义：
- Lead Event
- Opportunity Event
- Deal Event
- Revenue Event

未来根据真实销售流程选择 Twenty / SuiteCRM 或其他系统。

---

## ADR-015｜L4 暂不承诺商业归因

### Decision
不承诺：
- AI → Revenue
- GEO → Revenue
- GEO → Deal
- Causal Revenue Attribution

### 当前可以做
逐步收集：
```text
AI Referral
→ Visit
→ Lead
```

但必须标注：
> Observed / Client-site dependent / Attribution incomplete

---

## ADR-016｜商业能力等级

当前能力：

| Level | Capability | Status |
|---|---|---|
| L1 | Visibility | 🟢 |
| L2 | Measurement | 🟢 |
| L3 | Diagnosis | 🟡 |
| L3.5 | Intervention & Verification | 🟡 |
| L3.75 | Observed Effect | 🟡 |
| L4 | Business Outcome | 🔴 |
| L4.5 | Attribution | 🔴 |

### Commercial Rule
> 能卖到 L3 的语言，不代表能承诺 L3 的结果。

尤其禁止把 Visibility、Mention、Citation、Recommendation 直接等同于 Traffic、Lead、Customer、Revenue。

---

## ADR-017｜商业价值表达

### Decision
核心价值表达：

> 帮助品牌进入 AI 驱动的客户发现、考虑与选择过程。

用户痛点解释可以使用：

> 为什么 AI 没选我，以及我该做什么。

但这属于问题解释框架，不是结果保证。

禁止：
- 抢推荐机会
- 获得流量机会
- 获得客户机会
- 保证 AI 推荐
- 保证收入增长

---

## ADR-018｜当前禁止过度治理

### Decision
治理机制必须对应真实失败模式。

### Principle
> 产品没卖出去而治理体系 200 页 = 失败。

因此：
- 新规则先标 COMMERCIAL-PILOT
- 有真实失败证据后再升级
- 不为了“看起来完整”而增加控制项

---

## ADR-019｜当前阶段优先级

### P0
- Core Domain Contract
- Service Contract
- HQ Technical Delivery Workflow

### P1
- open-geo Adapter
- GeoLook Action / Verification Adapter
- Report Contract

### P2
- Distributor Portal MVP
- Business Event Contract

### P3
- Business Behavior
- CRM
- Attribution
- Advanced Experimentation

---

## ADR-020｜下一阶段决策

### Decision
下一阶段直接进入：

> **HQ Technical Delivery Architecture + Distributor Service Contract**

不再重新讨论 Distributor 是否应该承担技术采样，除非出现新的真实证据。

---

# Decision Change Protocol

任何新提案必须回答：
1. 它解决哪个已知问题？
2. 证据是什么？
3. 是否影响 Canonical Model？
4. 是否影响 Distributor / HQ 边界？
5. 是否需要新增控制？
6. 是否可以通过 Adapter 解决？
7. 是否需要新的 ADR？
8. 是否属于 COMMERCIAL-PILOT？

没有这些答案，不进入核心架构。
