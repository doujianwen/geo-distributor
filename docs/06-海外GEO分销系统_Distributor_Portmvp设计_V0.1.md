# 海外 GEO 分销系统｜Distributor Portal MVP 设计规范 V0.1

> Status: DESIGN BASELINE
> Version: V0.1
> Date: 2026-09-13
> Scope: Distributor Portal MVP 功能边界、数据模型、页面规格
> Reference: [01-总体架构](./01-海外GEO分销系统_总体架构与角色边界_V1.0.md), [03-Service Contract](./03-海外GEO分销系统_Service_Contract_V0.2.md), [05-HQ技术交付架构](./05-HQ技术交付架构_V0.1.md)

---

## 1. 设计原则

> **Distributor sells; HQ delivers.**

Portal 的唯一目的：让 Distributor 完成商业工作（Lead / Client / Project / Renewal），**不暴露技术细节**。

### 1.1 核心铁律

1. Portal 不调用 HQ 内部 API，只通过 Service Contract 通信
2. 技术真相不在 Portal 存储
3. Client-safe 是唯一可见的报告形式
4. Portal 是商业 Source of Truth；HQ 是技术 Source of Truth

### 1.2 不做（MVP 明确排除）

- ❌ Query Builder
- ❌ Sampling UI
- ❌ Measurement Console
- ❌ Diagnosis Console
- ❌ Browser Automation Console
- ❌ RawResponse 查看
- ❌ Provider 管理
- ❌ Evidence 评分查看
- ❌ CRM 全功能
- ❌ Billing
- ❌ Commission Engine

---

## 2. 用户角色

### 2.1 Distributor（主要用户）

具备能力：
- 市场拓展
- 客户关系维护
- 商务沟通
- 需求收集

不具备（也不需要）：
- 技术采样能力
- 测量方法知识
- 诊断方法论

### 2.2 HQ Technical Team（只读 Portal，不参与 Portal 开发）

HQ 通过 Service Contract 接收请求、交付结果，不操作 Portal UI。

### 2.3 Client（间接用户）

Client 不直接接触 Portal。所有沟通通过 Distributor 进行。

---

## 3. 数据模型（Portal 侧）

### 3.1 Lead

```json
{
  "lead_id": "LD-001",
  "distributor_id": "DST-001",
  "company_name": "Acme Corp",
  "contact_name": "John Doe",
  "contact_email": "john@acme.com",
  "source": "inbound" | "outbound" | "referral",
  "status": "NEW" | "CONTACTED" | "QUALIFIED" | "LOST",
  "notes": "",
  "created_at": "2026-09-13T00:00:00Z",
  "updated_at": "2026-09-13T00:00:00Z"
}
```

### 3.2 Client

```json
{
  "client_id": "CLI-001",
  "distributor_id": "DST-001",
  "lead_id": "LD-001",
  "name": "Acme Corp",
  "website": "https://acme.com",
  "market": ["US"],
  "industry": "industrial sensors",
  "target_customer": "B2B procurement teams",
  "known_competitors": ["CompetitorA", "CompetitorB"],
  "status": "ACTIVE" | "INACTIVE" | "CHURNED",
  "contract_start": "2026-09-13",
  "contract_end": null,
  "commercial_plan": "standard",
  "created_at": "2026-09-13T00:00:00Z"
}
```

### 3.3 Service Request

```json
{
  "request_id": "SR-001",
  "distributor_id": "DST-001",
  "client_id": "CLI-001",
  "service": "visibility_audit",
  "requested_engines": ["ChatGPT", "Google"],
  "business_question": "Why is our brand not visible in AI answers?",
  "target_market": "US",
  "target_products": ["sensor-X1"],
  "attachments": [],
  "submitted_at": "2026-09-13T00:00:00Z",
  "status": "SUBMITTED" | "CLARIFICATION_REQUIRED" | "APPROVED" | "DELIVERED" | "CANCELLED"
}
```

### 3.4 Project（Portal 视图）

```json
{
  "project_id": "PRJ-001",
  "request_id": "SR-001",
  "client_id": "CLI-001",
  "distributor_id": "DST-001",
  "status": "APPROVED" | "IN_EXECUTION" | "QA" | "DELIVERED" | "ACCEPTED" | "BLOCKED",
  "scope_summary": {
    "markets": ["US"],
    "engines": ["ChatGPT", "Google"],
    "service_stages": ["measurement", "diagnosis"],
    "deliverables": ["client_report"]
  },
  "key_findings": [],
  "recommended_actions": [],
  "progress_percent": 45,
  "report_available": false,
  "accepted_at": null,
  "created_at": "2026-09-13T00:00:00Z"
}
```

### 3.5 Report（Portal 视图）

```json
{
  "report_id": "RPT-001",
  "project_id": "PRJ-001",
  "type": "client_report" | "technical_report",
  "title": "GEO Visibility Audit - Acme Corp",
  "generated_at": "2026-09-20T00:00:00Z",
  "content": {},  // 实际内容由 HQ 生成，Portal 只做展示
  "is_client_safe": true
}
```

### 3.6 Commercial（商业状态）

```json
{
  "commercial_id": "COM-001",
  "client_id": "CLI-001",
  "plan": "standard",
  "unit_price": null,  // 由 Distributor 定价，Portal 不限制
  "status": "ACTIVE" | "RENEWAL_PENDING" | "EXPIRED",
  "renewal_date": "2027-09-13",
  "upsell_opportunities": []
}
```

---

## 4. 页面规格（MVP）

### 4.1 首页 / Dashboard

**目的**：让 Distributor 一眼看到当前业务状态

**内容**：
```
┌─────────────────────────────────────────────┐
│  📊 Dashboard                                │
├─────────────────────────────────────────────┤
│  Active Clients: 12                          │
│  Projects in Progress: 5                     │
│  Deliveries This Month: 3                    │
│  Renewals Due (30d): 2                       │
├─────────────────────────────────────────────┤
│  Recent Activity                             │
│  ─────────────────────────────────────────  │
│  PRJ-001 • Acme Corp • DELIVERED • Sep 20   │
│  PRJ-002 • Beta Inc • IN_EXECUTION • Sep 18  │
│  SR-003 • Gamma LLC • CLARIFICATION_REQ • Sep 17│
└─────────────────────────────────────────────┘
```

### 4.2 Client 列表 & 详情页

**Client 列表**：
- Name, Website, Market, Industry
- Status (Active/Inactive)
- Last Project Date
- Renewal Status

**Client 详情**：
- Basic Info（名称、网站、市场、行业）
- Associated Leads
- Active Projects
- Commercial Plan
- Communication Log

### 4.3 Project 列表 & 详情页

**Project 列表**：
- Project ID, Client, Service Type
- Status（带颜色标识）
- Progress Bar
- Expected Delivery Date

**Project 详情**：
- Scope Summary（市场、引擎、服务阶段）
- Key Findings（来自 HQ 交付）
- Recommended Actions
- Report Download（Client-safe only）
- Acceptance Status
- Change Request Button

### 4.4 Service Request 提交页

**输入字段**：
- Client 选择（下拉，从已有 Client 或新建）
- Service Type（下拉：visibility_audit / measurement / diagnosis / intervention / remeasurement / full_geo_project）
- Requested Engines（多选：ChatGPT / Google / Perplexity / Gemini）
- Business Question（文本框）
- Target Market（多选）
- Target Products（文本，逗号分隔）
- Known Competitors（文本，逗号分隔）
- Attachments（可选）
- Notes（可选）

**提交后**：显示 Request ID + 预期响应时间

### 4.5 Renewal / Expansion 管理

**Renewal**：
- 到期前 30 天提醒
- 一键发起续约流程
- 历史项目参考

**Expansion**：
- 同一 Client 的新增 Service Request
- 跨市场扩展
- 新增 Engine 覆盖

---

## 5. 状态流转（Portal 视角）

### 5.1 Service Request 状态

```
DRAFT → SUBMITTED → CLARIFICATION_REQUIRED → SCOPING → APPROVED → DELIVERED
                                                              ↓
                                                    CANCELLED
```

### 5.2 Project 状态（Portal 可见）

```
APPROVED → IN_EXECUTION → QA → DELIVERED → ACCEPTED
                  ↓          ↓
               BLOCKED    CHANGES_REQUESTED
                  ↓          ↓
              (等 Client)  → REVIEW → DELIVERED
```

### 5.3 颜色标识约定

| 状态 | 颜色 |
|------|------|
| DRAFT / APPROVED | 🟡 黄色 |
| IN_EXECUTION / CLARIFICATION_REQUIRED | 🔵 蓝色 |
| DELIVERED | 🟢 绿色 |
| ACCEPTED | 🟢 深绿 |
| BLOCKED | 🔴 红色 |
| CANCELLED | ⚫ 灰色 |

---

## 6. 通知机制（MVP）

| 事件 | 通知方式 | 接收方 |
|------|----------|--------|
| Service Request Submitted | 系统内通知 | Distributor |
| Clarification Required | 系统内通知 + 邮件 | Distributor |
| Scope Approved | 系统内通知 | Distributor |
| Project BLOCKED | 系统内通知 + 邮件 | Distributor |
| Project DELIVERED | 系统内通知 + 邮件 | Distributor |
| Report Available | 系统内通知 | Distributor |
| Renewal Due（30d）| 系统内提醒 | Distributor |

---

## 7. 安全边界

### 7.1 数据隔离

- Distributor A 不可见 Distributor B 的数据
- 同一 Distributor 下的多个 Client 相互可见
- HQ 团队可见所有技术数据，不通过 Portal 操作

### 7.2 报告可见性

| 报告类型 | Distributor 可见 | Client 可见 |
|----------|-----------------|-------------|
| Client Report | ✅ | ✅（通过 Distributor）|
| Technical Report | ❌ | ❌ |
| RawResponse | ❌ | ❌ |
| Evidence Internals | ❌ | ❌ |

### 7.3 变更控制

Distributor 不能修改：
- Technical Scope
- Measurement Methodology
- Evidence Grading
- Diagnosis Conclusions

Distributor 可以：
- 提交 Clarification Request
- 发起 Change Request（影响价格/范围）
- 请求 Report Revision（文字修改，非数据修改）

---

## 8. 与技术 Side 的接口

### 8.1 Service Contract（单向）

```
Portal ──POST──→ HQ /service-request
HQ ──POLL/SSE──→ Portal /delivery-result
```

### 8.2 同步策略

MVP 阶段采用**轮询**（每 5 分钟），不使用实时 WebSocket。

### 8.3 字段映射规则

Portal 显示的字段来自 HQ Delivery Result，**不做本地存储**。HQ 返回什么，Portal 显示什么。

---

## 9. MVP 范围总结

### 必须有

1. Client 管理（CRUD）
2. Service Request 提交
3. Project 状态查看
4. Client Report 下载
5. Dashboard 概览
6. 基本通知

### 明确不做

1. 任何技术操作界面
2. 报告生成/编辑
3. 多客户共享视图
4. 自动报价引擎
5. 合同模板生成
6. 财务结算

---

## 10. 实施优先级

| 优先级 | 功能 | 说明 |
|--------|------|------|
| P0 | Client CRUD | 基础数据 |
| P0 | Service Request 提交 | 入口 |
| P1 | Project 状态查看 | 核心使用场景 |
| P1 | Client Report 下载 | 交付物消费 |
| P2 | Dashboard | 业务全景 |
| P2 | Renewal 管理 | 商业闭环 |
| P3 | Notification System | 体验优化 |
