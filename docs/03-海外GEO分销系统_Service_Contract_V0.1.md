# 海外 GEO 分销系统｜Service Contract V0.1

> Status: DESIGN BASELINE  
> Version: V0.1  
> Date: 2026-09-13  
> Purpose: Distributor Portal ↔ HQ Technical Delivery System

## 1. Contract 定义

Service Contract 是 Distributor Portal 与 HQ Technical Delivery System 之间的正式业务技术边界。

它解决的问题不是“如何做 GEO”，而是：

> Distributor 如何把一个客户需求可靠地提交给 HQ，HQ 如何接单、技术化、执行、交付，Distributor 如何获得可用于客户管理的结果。

核心原则：

> Distributor 提交业务需求；HQ 将其技术化。

---

# 2. Contract 总流程

```text
Distributor
    │
    │ Service Request
    ▼
HQ Intake
    │
    ▼
Technical Scoping
    │
    ▼
Approved Scope
    │
    ▼
Execution
    │
    ├── Sampling
    ├── Measurement
    ├── Diagnosis
    ├── Intervention
    └── Re-measurement
    │
    ▼
QA
    │
    ▼
Delivery Result
    │
    ▼
Distributor Portal
    │
    ▼
Client
```

# 3. Service Request

Distributor 最初提交的是业务请求，不要求 Distributor 自己定义完整技术方案。

## 3.1 V0.1 Schema

```json
{
  "request_id": "SR-2026-0001",
  "distributor_id": "dist-001",
  "client_id": "client-001",
  "client": {
    "name": "Acme",
    "market": ["US"],
    "industry": "industrial sensors",
    "website": "https://example.com"
  },
  "service": {
    "type": "visibility_audit",
    "requested_engines": ["ChatGPT", "Google"]
  },
  "business_context": {
    "target_market": "US",
    "target_products": ["industrial sensors"],
    "business_goal": "understand AI visibility"
  },
  "requested_scope": {
    "priority_questions": [],
    "competitors": [],
    "brand_terms": []
  },
  "commercial": {
    "plan": "standard",
    "requested_deadline": null
  },
  "attachments": [],
  "notes": ""
}
```

# 4. Service Type

V0.1 不允许无限制自定义服务。

建议先定义：

```text
visibility_audit
measurement
diagnosis
intervention
remeasurement
full_geo_project
```

### visibility_audit
目标：
- 当前 AI Visibility 状态
- 基础 Evidence
- Key Findings

### measurement
目标：
- 针对既定 Query Set 进行 Measurement

### diagnosis
目标：
- 对已有 Measurement 进行专家诊断

### intervention
目标：
- 执行已批准的 GEO 改进动作

### remeasurement
目标：
- 干预后的重新测量

### full_geo_project
完整：
```text
Measurement
→ Diagnosis
→ Intervention
→ Re-measurement
```

# 5. Request → Scope

Distributor 提交 Request 后：

```text
Service Request
      ↓
HQ Intake
      ↓
Technical Review
      ↓
Technical Scope
      ↓
Scope Approval
      ↓
Execution
```

HQ 必须将业务请求转换成 Technical Scope。

## Technical Scope 至少包括

- Target Market
- Target Brand
- Target Website
- Industry
- Product / Service
- User Intent
- Query Set
- Engines
- Sampling Method
- Observation Window
- Measurement Dimensions
- Evidence Requirements
- Deliverables
- SLA
- Re-measurement Plan

# 6. Technical Scope Example

```json
{
  "scope_id": "SCP-2026-0001",
  "request_id": "SR-2026-0001",
  "target": {
    "brand": "Acme",
    "website": "https://example.com",
    "market": "US",
    "industry": "industrial sensors"
  },
  "measurement": {
    "engines": ["ChatGPT", "Google"],
    "query_set_id": "QS-001",
    "rounds": 3,
    "sampling_protocol": "HQ-GEO-SP-001"
  },
  "dimensions": [
    "brand_mention",
    "source_visibility",
    "citation_visibility",
    "answer_position"
  ],
  "deliverables": [
    "technical_report",
    "client_report"
  ],
  "remeasurement": {
    "included": false
  }
}
```

# 7. Project State Machine

V0.1 状态：

```text
DRAFT
  ↓
SUBMITTED
  ↓
IN_REVIEW
  ↓
SCOPED
  ↓
APPROVED
  ↓
IN_EXECUTION
  ↓
QA
  ↓
DELIVERED
  ↓
ACCEPTED
```

异常状态：

```text
CHANGES_REQUESTED
BLOCKED
CANCELLED
```

## 状态含义

### DRAFT
Distributor 尚未提交。

### SUBMITTED
已正式提交 HQ。

### IN_REVIEW
HQ 正在判断需求完整性与可交付性。

### SCOPED
技术 Scope 已形成。

### APPROVED
Scope 已获得客户 / Distributor 批准。

### IN_EXECUTION
技术交付进行中。

### QA
HQ 正在进行内部质量检查。

### DELIVERED
报告已交付。

### ACCEPTED
客户 / Distributor 已接受。

### CHANGES_REQUESTED
客户要求修改或补充。

### BLOCKED
由于访问权限、资料、平台限制或其他原因无法继续。

### CANCELLED
项目取消。

# 8. HQ Delivery Workflow

## Step 1 — Intake

输入：
```text
Service Request
```

输出：
```text
Scope Candidate
```

## Step 2 — Technical Scoping

HQ 定义：
- Query Set
- Engines
- Sampling
- Metrics
- Evidence
- Deliverables

## Step 3 — Sampling

HQ 执行：
- Browser
- Provider
- Query
- Environment

Distributor 不执行。

## Step 4 — Measurement

产生：
```text
RawResponse
Observation
Measurement
```

## Step 5 — Evidence

保存：
- Answer
- Screenshot
- Sources
- Citations
- Environment
- Timestamp
- Validity

## Step 6 — Diagnosis

输出：
- Findings
- Root Cause Hypotheses
- Confidence
- Recommended Actions

## Step 7 — Intervention

如项目包含技术执行：
- Content
- Structure
- Technical SEO / GEO
- Site Changes
- Citation / Source improvement
- Other approved actions

## Step 8 — Re-measurement

根据 Experiment / Measurement Protocol 再测。

## Step 9 — Interpretation

必须区分：

```text
Observed Change
vs
Causal Effect
```

不能自动把前者解释为后者。

## Step 10 — QA

检查：
- Evidence completeness
- Measurement correctness
- Diagnosis consistency
- Report correctness
- Client-safe language
- Commercial claim compliance

## Step 11 — Delivery

输出：
- HQ Technical Report
- Client / Distributor Report

# 9. Delivery Result

HQ 返回 Distributor 的不是内部数据库，而是 Delivery Result。

## V0.1

```json
{
  "project_id": "PRJ-2026-0001",
  "request_id": "SR-2026-0001",
  "status": "DELIVERED",
  "summary": {
    "visibility_status": "measured",
    "key_findings": [],
    "recommended_actions": [],
    "observed_change": null
  },
  "reports": {
    "client_report": "REPORT-001"
  },
  "acceptance": {
    "status": "PENDING"
  },
  "next_step": "CLIENT_REVIEW"
}
```

# 10. Report Contract

## Client Report 必须支持

```text
Executive Summary
Current Visibility
Key Findings
Why
Recommended Actions
Progress
Observed Change
Next Steps
```

## Technical Report 必须保留

```text
Query Set
Sampling Environment
Raw Evidence
Observation
Measurement
Validity
Diagnosis
Intervention
Experiment
Confounders
Re-measurement
Observed Effect
Interpretation
```

Client Report 是 Technical Report 的安全、可读投影，而不是独立事实来源。

# 11. Acceptance Contract

项目交付后：

```text
DELIVERED
   ↓
CLIENT_REVIEW
   ↓
ACCEPTED
```

或：

```text
DELIVERED
   ↓
CHANGES_REQUESTED
   ↓
REVIEW
   ↓
DELIVERED
```

## Acceptance 不等于商业效果

客户接受报告，只代表：
- 交付物符合约定
- 数据与报告满足 Scope

不代表：
- AI 一定推荐
- 流量一定增加
- Leads 一定增加
- Revenue 一定增加

# 12. SLA

V0.1 先支持字段，不立即硬编码全部 SLA：

```json
{
  "sla": {
    "acknowledgement_hours": 24,
    "scoping_hours": 48,
    "delivery_target_days": 7
  }
}
```

具体 SLA 属于 COMMERCIAL-PILOT。真实项目验证后再冻结。

# 13. Revision

允许：

```text
Revision Request
```

必须记录：
- reason
- requester
- requested_at
- affected_section
- whether new sampling required
- whether new scope required

### Rule

如果客户只是要求解释文字：
> Report Revision

如果要求增加 Query / Engine / Sampling：
> Scope Change

不能把 Scope Change 隐藏成普通报告修改。

# 14. Distributor 能看到什么

Distributor Portal V0.1：

```text
Client
 ├── Projects
 │    ├── Status
 │    ├── Scope Summary
 │    ├── Key Findings
 │    ├── Recommendations
 │    ├── Reports
 │    └── Acceptance
 │
 └── Commercial
      ├── Plan
      ├── Renewal
      └── Expansion
```

# 15. Distributor 不能看到什么

默认不暴露：

```text
RawResponse internals
Provider implementation
Parser
Validity Engine internals
Debug logs
Experiment internals
Internal evidence grading details
Prompt / system implementation
Browser automation internals
Technical credentials
Internal methodology implementation
```

这不是为了“隐藏技术”，而是为了：
- 保持技术 Source of Truth
- 避免版本分叉
- 防止错误解释
- 保护方法论
- 降低 Distributor 培训成本

# 16. Open-source Adapter Boundary

## open-geo

```text
HQ Technical Delivery
        │
        ▼
open-geo Adapter
        │
        ▼
QueryCapture
        │
        ▼
Core RawResponse / Observation
```

Distributor 永远不直接调用 open-geo。

## GeoLook

```text
HQ Core
   │
   ▼
Action / Verification Adapter
   │
   ▼
GeoLook capabilities
```

Distributor 只看到最终：
- Recommended Actions
- Progress
- Verification Result

# 17. Error Contract

V0.1 至少定义：

```text
INVALID_REQUEST
MISSING_CLIENT_DATA
SCOPE_REQUIRED
CLIENT_ACCESS_REQUIRED
ENGINE_UNAVAILABLE
SAMPLING_FAILED
MEASUREMENT_INVALID
EVIDENCE_INSUFFICIENT
DIAGNOSIS_BLOCKED
DELIVERY_BLOCKED
CLIENT_CHANGE_REQUEST
```

错误必须区分：
- 商务问题
- 数据问题
- 技术问题
- 客户依赖问题

# 18. Ownership Matrix

| Artifact | Distributor | HQ |
|---|---:|---:|
| Lead | Own | View |
| Client Relationship | Own | View |
| Service Request | Submit | Own technical processing |
| Technical Scope | Request context | Own |
| Query Set | View summary | Own |
| Sampling | No | Own |
| Measurement | No | Own |
| Evidence | Client-safe view | Own |
| Diagnosis | Receive | Own |
| Intervention | Coordinate | Own |
| Re-measurement | Receive | Own |
| Technical Report | View | Own |
| Client Report | Deliver | Produce |
| Acceptance | Coordinate | Record |
| Renewal | Own | Support |

# 19. Contract Evolution

V0.1 不是最终 API。

任何字段进入 Canonical Contract 前必须回答：
1. 是否真实使用？
2. 是否影响交付？
3. 是否需要跨系统同步？
4. 是否需要持久化？
5. 是否可能成为未来核心模型？

如果只是内部实现细节，不进入 Service Contract。

# 20. 当前不做

Service Contract V0.1 不负责：
- Distributor 技术采样
- Distributor 自建 Query Engine
- Distributor 自建 Measurement
- Distributor 自建 Diagnosis
- CRM 全功能
- Revenue Attribution
- 自动因果推断
- 多层白标技术系统
- 自动化报价引擎
- 自动化合同生成
- 财务结算系统

# 21. 下一步

基于本 Contract，下一阶段进入：

> **HQ Technical Delivery Architecture Design**

重点定义：
1. Intake
2. Scope
3. Query Set
4. Sampling
5. Measurement
6. Evidence
7. Diagnosis
8. Intervention
9. Re-measurement
10. QA
11. Report
12. Delivery

然后再设计 Distributor Portal。

# 22. Contract 设计原则

> Distributor 不需要知道“怎么测 GEO”。

Distributor 只需要知道：

```text
客户是谁
客户要解决什么问题
要什么服务
什么时候需要
```

HQ 负责把：

```text
Business Requirement
```

转换成：

```text
Technical Scope
→ Measurement
→ Diagnosis
→ Intervention
→ Verification
→ Re-measurement
→ Delivery
```

这是本系统规模化分销的核心。
