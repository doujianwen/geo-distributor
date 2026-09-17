# 海外 GEO 分销系统｜总体架构与角色边界 V1.0

> Status: ARCHITECTURE BASELINE  
> Version: V1.0  
> Date: 2026-09-13  
> Scope: 海外 GEO 分销系统  
> Principle: **Sell Local, Deliver Centralized**

## 1. 文档目的

本文件是“海外 GEO 分销系统”当前有效的总体架构基线，用于约束商业模式、HQ / Distributor / Client 三方角色、技术与商业职责边界、系统分层、MVP 范围及后续技术实现。

本文件不是永久不可修改的最终方案。若真实客户、真实 Distributor 或真实交付产生新证据，应通过 ADR 修改，而不是在聊天或代码中隐式改变架构。

## 2. 核心商业模型

### 2.1 定义

本系统不是：
- GEO SaaS + Reseller
- 让 Distributor 自己操作 GEO 的系统
- 让 Distributor 成为 GEO 技术专家的平台

它是：

> **HQ-powered GEO Distribution System**  
> **Local Distribution + Centralized GEO Intelligence + Centralized Technical Delivery**

即：

> **Sell Local, Deliver Centralized.**

### 2.2 核心原则

> Distributor 卖；HQ 交付。  
> Distributor 管客户关系；HQ 管技术真相。  
> Distributor 提供业务上下文；HQ 将业务问题转换为 GEO 测量问题。  
> Sampling、Measurement、Diagnosis、Technical Execution 默认集中在 HQ。  
> 普通 Distributor 不要求具备技术能力。  
> Core GEO methodology 与 Evidence 由 HQ 控制。

## 3. 三方角色

### 3.1 HQ

HQ 是 GEO Intelligence + Technical Delivery 中心。

负责：
- Query Strategy / Query Set
- AI Sampling
- Browser / Engine 操作
- Measurement
- Observation
- Evidence
- Diagnosis
- Intervention Strategy
- Technical Execution
- Verification
- Re-measurement
- GEO Report
- QA
- Methodology
- Core System

### 3.2 Distributor

Distributor 是 Market Access / Sales / Client Relationship 角色。

负责：
- 市场拓展
- Lead Generation
- 初步商务沟通
- 需求收集
- 报价 / 合同协调
- 客户关系
- 项目协调
- 报告沟通与交付协调
- Renewal
- Upsell / Expansion

Distributor 不负责：
- Query Design
- AI Sampling
- Browser / Engine 技术操作
- Measurement
- Evidence 判定
- Diagnosis
- Technical Execution
- Re-measurement
- Provider Adapter
- Parser / Validity Engine
- Experiment 内部技术细节

除非未来明确建立“Technical Delivery Partner”角色，并通过单独授权与质量体系委托。

### 3.3 Client

Client 负责：
- 业务目标与需求
- 产品、网站、品牌资料
- 必要访问权限
- 商业背景
- 审批与验收
- 业务反馈
- 干预内容确认
- 商业结果反馈

## 4. 系统五层架构

### L0 Infrastructure
- Browser
- Provider
- Storage
- Runtime
- Authentication / Access infrastructure

### L1 GEO Core
- Observation
- Measurement
- Evidence
- Diagnosis
- Intervention Hypothesis
- Experiment Protocol
- Interpretation

### L2 Technical Delivery
- Query Design
- Sampling
- Measurement execution
- Diagnosis execution
- Intervention execution
- Verification
- Re-measurement
- Report
- QA

### L3 Distributor
- Lead
- Client
- Project
- Service Request
- Order
- Status
- Report access
- Client communication
- Renewal / Expansion

### L4 Business
未来再逐步建设：
- AI Referral → Visit
- Visit → Lead
- Lead → Opportunity
- Opportunity → Deal
- Deal → Revenue
- GEO → Business Attribution

当前阶段只定义 Event Contract，不建设完整 CRM / Revenue Attribution。

## 5. 两系统模型

### A. HQ GEO Delivery System

负责完整技术交付：
- Measurement
- Diagnosis
- Execution
- Verification
- Re-measurement
- Reports
- QA

### B. Distributor Portal

负责：
- Leads
- Clients
- Projects
- Orders / Service Requests
- Status
- Reports
- Communication
- Renewal

两者通过 Service Contract 连接：

```text
Distributor Portal
      │
      │ Service Request
      ▼
HQ Delivery System
      │
      │ Delivery Result
      ▼
Distributor Portal
```

## 6. 信息边界

### HQ Source of Truth

HQ 是以下内容的唯一技术 Source of Truth：
- Measurement
- Observation
- Evidence
- Diagnosis
- Intervention
- Experiment
- Re-measurement
- Technical Report

### Distributor 可见

Distributor 可查看：
- Client Workspace
- Project
- GEO Status
- Key Findings
- Recommended Actions
- Progress
- Client-safe Reports
- Commercial Status

### Distributor 默认不可操作

- RawResponse internals
- Parser
- Validity Engine
- Provider Adapter
- Experiment internals
- Debug data
- Full Evidence grading
- Methodology implementation

## 7. 双报告模型

### 7.1 HQ Technical Report

用于内部技术审计与质量控制。

应包含：
- Sampling environment
- Query set
- Engine / Provider
- Raw evidence
- Observation
- Measurement
- Validity
- Diagnosis
- Intervention
- Experiment
- Confounders
- Re-measurement
- Observed Effect
- Interpretation

### 7.2 Client / Distributor Report

用于商业交付。

包含：
- Executive Summary
- Current Visibility
- Key Findings
- Why
- Recommended Actions
- Progress
- Observed Change
- Next Steps

不直接暴露不必要的内部实现细节。

## 8. Distributor 工作流

```text
Market
 ↓
Distributor
 ↓
Lead
 ↓
Client
 ↓
Business Requirement
 ↓
HQ Technical Scoping
 ↓
GEO Measurement
 ↓
Diagnosis
 ↓
Intervention
 ↓
Technical Execution
 ↓
Re-measurement
 ↓
Observed Effect
 ↓
Client Report
 ↓
Distributor Client Management
 ↓
Renewal
 ↓
Expansion
```

从 HQ Technical Scoping 开始，技术工作由 HQ 主导。

## 9. KPI 边界

### Distributor KPI
- Qualified Leads
- Opportunities
- Closed Deals
- Revenue
- Renewal
- Expansion

### HQ KPI
- Delivery SLA
- Measurement Quality
- Diagnosis Quality
- Report Quality
- Re-measurement Completion
- Client Acceptance
- Delivery Quality

## 10. Distributor MVP

必须支持：
1. Add Lead
2. Add Client
3. Submit GEO Service Request
4. View Project Status
5. Receive HQ Report
6. View Client-safe Findings
7. Manage Follow-up
8. Renewal / Expansion

明确不做：
- Query Builder
- Sampling UI
- Measurement UI
- Diagnosis UI
- Browser Automation Console
- Technical Debug Console

## 11. HQ MVP

必须支持：
1. Receive Request
2. Review Scope
3. Build Query Set
4. Execute Sampling
5. Measurement
6. Evidence
7. Diagnosis
8. Intervention
9. Re-measurement
10. Report
11. QA
12. Delivery

## 12. Open-source 组合原则

采用：

> **Compose at Explicitly Defined Boundaries**

而不是：
- Fork 一个项目作为整个系统
- 将外部项目的数据模型直接变成 Canonical Model
- 因为某项目已有功能就改变核心架构

当前边界：
- open-geo → High-Fidelity Measurement Adapter
- GeoLook → Action / Verification Adapter / Reference
- 其他项目 → 必须通过明确 Adapter / Contract 接入

## 13. 当前能力成熟度

| 能力 | 状态 |
|---|---|
| L1 Visibility | 🟢 Sellable |
| L2 Measurement | 🟢 Sellable |
| L3 Diagnosis | 🟡 Expert Service |
| Intervention | 🟡 Pilot |
| Re-measurement | 🟡→🟢 Implementable |
| Observed Effect | 🟡 Reportable, no overclaim |
| Causal Effect | 🔴 No promise |
| AI → Visit | 🟡 Can start collecting |
| Visit → Lead | 🟡 Client-site dependent |
| Lead → Opportunity | 🔴 |
| Opportunity → Deal | 🔴 |
| Deal → Revenue | 🔴 |
| GEO → Revenue Attribution | 🔴 |

## 14. 商业承诺纪律

客户买的是：
> 进入 AI 驱动客户决策过程的机会。

不要承诺：
- 必然被推荐
- 必然获得流量
- 必然获得客户
- 必然增加收入
- 控制 AI 推荐结果

正确表达：
> 增加品牌在 AI 驱动的发现、考虑与选择过程中的可见性、可理解性与被纳入考虑的概率。

## 15. 架构冻结规则

以下内容在新证据出现前视为当前基线：
1. Distributor 不承担标准技术采样。
2. HQ 掌握技术 Source of Truth。
3. 技术交付集中在 HQ。
4. Distributor Portal 与 HQ Delivery System 分离。
5. 两者通过 Service Contract 连接。
6. Core GEO methodology 不由 Distributor 控制。
7. Open-source 项目只能通过明确边界接入。
8. L4 商业归因暂不作为当前核心系统建设目标。

后续变更必须通过 ADR。

## 16. 下一阶段

下一阶段不是继续讨论宏观商业模式，而是：

> **HQ Technical Delivery Architecture + Distributor Service Contract 联合设计**

目标：
- 定义 Service Request
- 定义 Delivery Contract
- 定义 HQ Technical Delivery 状态机
- 定义 Report / Acceptance
- 定义 open-geo Adapter 边界
- 定义 GeoLook Action / Verification 边界
- 定义 Distributor Portal MVP 数据边界
