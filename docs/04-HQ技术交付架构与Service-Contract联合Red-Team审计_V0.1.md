# 海外 GEO 分销系统
## HQ 技术交付架构 + Service Contract 联合 Red-Team 审计 V0.1

**状态：ARCHITECTURE AUDIT — PASSED WITH CHANGES**  
**审计目的：**攻击当前“Distributor Portal ↔ HQ Technical Delivery System”边界，找出会导致返工、职责漂移、技术泄漏、交付失控或多客户扩展失败的问题。  

---

## 1. Executive Verdict

### 裁定
当前总体方向成立，但原 V0.1 Service Contract **不能直接进入实现**。核心问题不是角色定义错误，而是 Contract 还没有把“商业请求”稳定地转换成“技术项目”。

必须补上四个中间机制：

1. **Intake Completeness Gate**：HQ 判断请求是否足够进入技术 Scope。
2. **Technical Scope + Approval Gate**：商业请求与技术执行范围分离，Scope 经批准后冻结。
3. **Project / Work Item 分层**：一个商业 Project 可以拆成多个技术 Work Item。
4. **Change Control**：区分普通修订、技术重做和真正 Scope Change。

### 不改变的基线
- Distributor 不承担标准技术采样、Measurement、Diagnosis、Technical Execution。
- HQ 掌握技术真相与证据。
- Distributor Portal 与 HQ Technical Delivery System 分离。
- open-geo 只能进入 Measurement Adapter 边界。
- GeoLook 只能进入 Action / Verification Adapter 边界。
- Core 不被任何外部开源项目反向定义。

---

# 2. Red-Team 攻击矩阵

| # | 攻击问题 | 发现 | 严重度 | 裁定 |
|---|---|---|---|---|
| R1 | Distributor 信息是否足够启动？ | 原 Contract 没有明确最低输入门槛 | High | 增加 Intake Gate |
| R2 | HQ 是否会反复追问？ | 是。行业、市场、产品、目标客户、域名、引擎、问题类型可能缺失 | High | 一次结构化 Clarification Request，禁止无限聊天式补充 |
| R3 | 谁批准 Technical Scope？ | 原版不够明确 | High | Distributor/Client 批准商业范围；HQ 负责技术可执行性；涉及付费范围必须 Client/合同主体确认 |
| R4 | 一个 Request 能否拆多个任务？ | 原版偏“一请求=一项目” | High | Request → Project → Work Items |
| R5 | Measurement / Diagnosis / Intervention 是否共用 Project？ | 应共用商业 Project，但技术上拆 Work Item | Medium | 同 Project，不同 Work Item |
| R6 | open-geo 放哪？ | 若直接进入 Core 会污染 Canonical Model | Critical | Measurement Adapter，仅输出标准 Observation/Measurement |
| R7 | GeoLook 放哪？ | 若作为方法论源会污染诊断真相 | High | Action/Verification Adapter，不得成为 Canonical Diagnosis Engine |
| R8 | Failure / Blocked / Rework？ | 原状态机缺少技术异常语义 | High | 增加 BLOCKED / REWORK / CANCELLED，并保留原因 |
| R9 | Query/Engine 增加是否 Scope Change？ | 不一定 | High | 用“Technical Scope Dimension”判断，而不是简单字段变化 |
| R10 | Portal 与 HQ 数据同步边界？ | 需要 Source-of-Truth 规则 | Critical | 双系统不做双向任意写入；Portal 是商业视图，HQ 是技术真相 |
| R11 | 哪些字段不应进入 Contract？ | Query Set、RawResponse、Parser、Validity internals 等不应成为 Distributor API 合同 | High | 保持内部模型 |
| R12 | 多 Distributor / Client / Project？ | 当前模型可扩展，但需要 Tenant / Ownership 边界 | High | Project 必须带 distributor_id/client_id/owner_hq_team |
| R13 | 报告是否会成为数据同步替代品？ | 有风险 | Medium | Report 是 Delivery Artifact，不是实时数据库 |
| R14 | Distributor 能否修改技术结论？ | 存在风险 | Critical | 不允许。只能提出 clarification / change request |
| R15 | 客户直接联系 HQ 怎么办？ | 当前角色边界未覆盖 | Medium | 商业关系仍由 Distributor 负责；HQ 可参与技术会议 |
| R16 | 一个客户多个 Distributor？ | 潜在渠道冲突 | High | Client ownership / account assignment 必须成为商业层规则，不进入 GEO Core |

---

# 3. 新的四层对象模型

原模型：

```text
Service Request → Project → Delivery Result
```

升级为：

```text
Service Request
      ↓
Intake
      ↓
Technical Scope
      ↓
Project
      ↓
Work Items
      ↓
Evidence / Measurement / Diagnosis / Intervention / ReMeasurement
      ↓
Delivery Package
      ↓
Client Acceptance
```

## 3.1 Service Request
商业入口。描述“客户想解决什么问题”。

不要求 Distributor 理解 GEO 技术细节。

## 3.2 Technical Scope
HQ 将商业语言转换成可执行技术范围。

例如：

```json
{
  "market": ["US"],
  "engines": ["ChatGPT", "Google"],
  "query_scope": "HQ_DEFINED",
  "measurement_rounds": 1,
  "diagnosis": true,
  "intervention": false,
  "remeasurement": false,
  "deliverables": ["client_report"],
  "assumptions": [],
  "exclusions": []
}
```

## 3.3 Project
商业交付容器。

一个 Project 可以覆盖：

```text
Initial Audit
Measurement
Diagnosis
Intervention
ReMeasurement
```

但不强迫所有项目都执行全部阶段。

## 3.4 Work Item
HQ 内部技术执行单位。

例如：

```text
PRJ-001
 ├── WI-001 Measurement
 ├── WI-002 Diagnosis
 ├── WI-003 Intervention
 └── WI-004 ReMeasurement
```

Distributor 不直接管理 Work Item 的技术细节，只看到可公开状态。

---

# 4. Intake Completeness Gate

## 4.1 Minimum Required Input

标准 Distributor Request 至少需要：

- Client name
- Website/domain（如适用）
- Market / country
- Industry / product category
- Target customer description
- Business question / desired outcome
- Requested service
- Known competitors（如有）
- Known AI engines（可为空）
- Contact / approval information

## 4.2 不完整时的处理

禁止 HQ 进入技术执行后才发现资料缺失。

状态：

```text
SUBMITTED
   ↓
INTAKE_REVIEW
   ├── COMPLETE → SCOPING
   └── INCOMPLETE → CLARIFICATION_REQUIRED
```

Clarification 必须结构化记录：

```json
{
  "request_id": "SR-001",
  "missing_fields": ["target_customer", "market"],
  "questions": [
    "Who is the primary buyer?",
    "Which market should be measured?"
  ]
}
```

原则：**一次集中补齐，不进行无限来回追问。**

---

# 5. Scope Approval Gate

## 5.1 三方责任

| 角色 | 责任 |
|---|---|
| Distributor | 确认客户商业需求与商业范围 |
| HQ | 定义技术 Scope、可执行性、方法、交付物 |
| Client | 对影响价格/范围/周期的 Scope 作最终确认 |

HQ 不应要求 Distributor 审批技术算法。

Distributor/Client 也不应直接修改技术测量定义。

---

# 6. Request → Project → Work Item

## 6.1 为什么不能 Request = Project

一个客户可能提交：

> “帮我看看 ChatGPT 为什么不推荐我们，并帮我们改善。”

这可能展开为：

```text
Project
 ├── Visibility Audit
 ├── Measurement
 ├── Diagnosis
 ├── Intervention
 └── ReMeasurement
```

因此：

> Request 是需求入口；Project 是商业交付容器；Work Item 是技术执行单位。

---

# 7. Measurement / Diagnosis / Intervention 边界

三者可以属于同一 Project，但不能混成一个不可分割的 Service。

推荐：

```text
Measurement
   ↓
Diagnosis
   ↓
Intervention
   ↓
ReMeasurement
```

前一阶段的结果可以成为后一阶段的输入，但每阶段拥有自己的状态与证据。

这样可以支持：

- 只卖 Audit
- Audit + Diagnosis
- Diagnosis + Intervention
- Full Project

无需修改 Core。

---

# 8. open-geo 插入点

最终边界：

```text
Browser / Provider
        ↓
open-geo Adapter
        ↓
RawResponse / QueryCapture
        ↓
Observation Normalization
        ↓
Canonical Measurement
```

open-geo：

- 负责高保真采样能力
- 提供 QueryCapture
- 不拥有 HQ 的 Canonical Evidence
- 不决定商业结论
- 不直接写 Distributor Portal

如果未来替换 open-geo，只替换 Adapter。

---

# 9. GeoLook 插入点

最终边界：

```text
Canonical Evidence / Diagnosis
            ↓
      GeoLook Adapter
            ↓
Action / Verification Suggestions
            ↓
HQ Intervention Workflow
```

GeoLook 的：

- Audit dimensions
- Action tickets
- Verification concepts
- Content / technical checks

可以被复用，但必须经过 HQ Canonical Model 转译。

原则：

> 外部项目提供 capability；HQ Core 决定 meaning。

---

# 10. Failure / Blocked / Rework

新增技术状态：

```text
IN_EXECUTION
   ├── QA
   ├── BLOCKED
   └── REWORK
```

### BLOCKED
外部依赖导致不能继续，例如：

- Client 未提供必要访问权限
- Provider 不可用
- 浏览器环境不可用
- 数据不足

必须记录：

```text
blocked_reason
blocked_since
required_action
owner
```

### REWORK
技术交付已执行，但 QA 发现必须重做。

不能简单回到 IN_EXECUTION 而丢失历史。

---

# 11. Query / Engine 变化：Revision 还是 Scope Change？

不能规定“增加一个 Engine 就一定是 Scope Change”。

判断标准：

### Revision
不改变商业承诺，仅修正技术执行细节。

例如：
- Query wording 微调
- Query 顺序调整
- 浏览器重跑
- 修复采样失败

### Scope Change
改变商业承诺、成本、周期或交付范围。

例如：
- 从 ChatGPT 扩展到 Gemini + Perplexity
- 从 US 扩展到 EU
- 从 20 queries 扩展到 100 queries
- 从 Audit 增加 Intervention

原则：

> **Scope Change 看商业影响，不看字段变化。**

---

# 12. Source of Truth

必须明确：

| 数据 | Source of Truth |
|---|---|
| Lead | Distributor Portal |
| Client | Distributor Portal |
| Commercial Contract | Distributor Portal / Commercial System |
| Service Request | Distributor Portal |
| Technical Scope | HQ System |
| RawResponse | HQ System |
| Observation | HQ System |
| Measurement | HQ System |
| Evidence | HQ System |
| Diagnosis | HQ System |
| Intervention | HQ System |
| ReMeasurement | HQ System |
| Technical Report | HQ System |
| Client-safe Report | HQ-generated artifact，Portal 展示 |
| Project commercial status | Portal |
| Technical delivery status | HQ |

禁止双向自由写入同一技术对象。

---

# 13. Portal / HQ 同步原则

不是：

```text
Portal DB ↔ HQ DB
```

而是：

```text
Portal
  │ Service Request
  ▼
HQ
  │ Delivery Status / Result
  ▼
Portal
```

即：**Command in / Result out**。

实时同步不是当前 MVP 必需能力。

---

# 14. 多 Distributor / 多 Client 扩展

Project 最低身份边界：

```json
{
  "project_id": "PRJ-001",
  "distributor_id": "DST-001",
  "client_id": "CLI-001",
  "hq_owner": "TEAM-001"
}
```

技术 Core 不需要理解 Distributor 的佣金、销售等级、返点等商业规则。

这些属于 L3/L4。

---

# 15. 不进入当前 Contract 的字段

暂不公开或固定：

- RawResponse schema internals
- Parser internals
- Validity Engine internals
- Provider implementation details
- Browser automation details
- Evidence scoring implementation
- Query generation algorithm
- Prompt engineering internals
- Model-specific hidden parameters
- Internal debugging logs

原因：这些是 HQ 实现细节，不是服务边界。

---

# 16. 最终裁定

### PASS
总体架构：PASS

### CHANGES REQUIRED
Service Contract：需要升级 V0.2。

### NOT APPROVED
以下仍不得进入 MVP：

- Distributor Query Builder
- Distributor Sampling UI
- Distributor Measurement Console
- Distributor Diagnosis Console
- Browser Automation Console
- CRM
- Revenue Attribution
- GrowthBook
- PostHog 核心集成

### 下一阶段
不是继续讨论角色，而是进入：

> **HQ Technical Delivery Architecture V0.1 + Service Contract V0.2 implementation-ready specification**

并以本审计作为约束基线。
