# 海外 GEO 分销系统
## Implementation Readiness Audit V0.1

**审计对象：** HQ Technical Delivery + Distributor Portal + Service Contract V0.2
**审计类型：** Implementation Readiness / Red-Team
**结论：** **CONDITIONAL PASS — 可进入规格与 MVP 实现，但必须先关闭 P0 Blocker；不得直接写业务代码。**

---

## 1. Executive Verdict

当前架构已经从“概念架构”进入“可实施架构”的门槛，但还缺少 7 类实现级定义：

1. Identity / Tenant / Authorization
2. Canonical IDs 与唯一性规则
3. API contract 与幂等规则
4. 状态迁移规则与权限
5. Project / Work Item 的依赖与失败语义
6. Delivery Artifact 的版本与不可变性
7. Audit Trail / 最小操作日志

这些不是新增产品能力，而是让已经批准的架构可以安全落地的最小基础设施。

**不得在本阶段引入：** CRM、Billing、Commission、Revenue Attribution、复杂 Event Bus、Workflow Builder、Distributor Technical Console。

---

# 2. Readiness Scorecard

| Area | Status | Verdict |
|---|---|---|
| 商业角色边界 | 🟢 | Frozen |
| HQ / Distributor 边界 | 🟢 | Frozen |
| Two-System Architecture | 🟢 | Ready |
| Service Request / Scope / Project / Work Item | 🟢 | Ready |
| GEO Core Boundary | 🟢 | Ready |
| Adapter Boundary | 🟢 | Ready |
| State Machine | 🟡 | 需定义 transition guard |
| Multi-tenant isolation | 🟡 | P0 必须补齐 |
| Identity / RBAC | 🟡 | P0 最小实现即可 |
| API contract | 🟡 | P0 必须冻结 |
| Idempotency | 🔴 | P0 Blocker |
| Artifact versioning | 🔴 | P0 Blocker |
| Audit trail | 🟡 | P0 最小实现 |
| Failure / retry | 🟡 | 需定义 |
| open-geo adapter contract | 🟡 | Interface 可先冻结，具体 adapter 后实现 |
| GeoLook adapter contract | 🟡 | Interface 可先冻结，非 MVP blocker |
| Observability | 🟡 | 最小 request/project/work-item logging |
| Billing / CRM | 🟢 | 明确不做 |
| Revenue attribution | 🟢 | 明确不做 |

---

# 3. P0 Blockers

## P0-01 Tenant / Ownership Model

最小隔离模型：

```text
Distributor
  └── Client
       └── Project
            └── Work Item
                 └── Technical Data
```

必须所有商业对象至少带：

- `distributor_id`
- `client_id`
- `project_id`
- `owner_team`（HQ 内部）

技术对象从 Project 继承访问上下文，不允许客户端自行传入任意 tenant ID 绕过校验。

---

## P0-02 Identity / Authorization

MVP 不需要完整 IAM 平台，但必须有最小 RBAC：

### Distributor roles
- `DISTRIBUTOR_ADMIN`
- `DISTRIBUTOR_MEMBER`

### HQ roles
- `HQ_ADMIN`
- `HQ_OPERATOR`
- `HQ_REVIEWER`

### Client-safe access
MVP 可先通过 Distributor 代管客户视图，不直接建立独立 Client 用户体系；Client 用户体系留后续。

核心规则：

> 身份决定“是谁”；Project ownership 决定“能看什么”；Role 决定“能做什么”。

---

## P0-03 Canonical IDs

统一 ID：

```text
DST-xxxx
CLI-xxxx
SR-xxxx
SCP-xxxx
PRJ-xxxx
WI-xxxx
OBS-xxxx
MEAS-xxxx
EVD-xxxx
RPT-xxxx
DLV-xxxx
```

ID 不表达业务含义以外的可变信息，不使用数据库自增 ID 暴露给外部 Contract。

---

## P0-04 Idempotency

所有会创建/提交/状态迁移的 Portal → HQ command 必须支持：

```text
Idempotency-Key
```

重复请求不得创建重复：

- Service Request
- Project
- Work Item
- Delivery

同一 key + 同一 command payload → 返回原结果。
同一 key + 不同 payload → `IDEMPOTENCY_CONFLICT`。

---

## P0-05 State Transition Guards

状态不能由前端任意设置。

例如：

```text
SUBMITTED → INTAKE_REVIEW
IN_REVIEW → SCOPING
SCOPING → SCOPE_PENDING_APPROVAL
SCOPE_PENDING_APPROVAL → APPROVED
```

禁止：

```text
SUBMITTED → DELIVERED
IN_EXECUTION → APPROVED
```

每个 transition 必须由后端根据 role + precondition 判定。

---

## P0-06 Delivery Artifact Versioning

Report / Delivery Result 必须可追踪。

```text
RPT-001 v1
RPT-001 v2
```

历史版本不可被静默覆盖。

Client-safe report 与 HQ technical report 分开生成。

---

## P0-07 Audit Trail

MVP 至少记录：

- actor
- role
- action
- object_type
- object_id
- previous_state
- new_state
- timestamp
- correlation_id

不要求第一版做完整 SIEM；但必须能回答：

> 谁在什么时候把哪个 Project 从什么状态改成了什么状态？

---

# 4. P1 Risks

### P1-01 Query Set ownership

Query Set 属于 HQ Technical Execution，不进入 Distributor Contract。

### P1-02 Measurement provenance

必须保留 engine、market、timestamp、sampling context 等 provenance，但先由 GEO Core / Adapter 管理。

### P1-03 Rework semantics

技术失败可 Rework；商业变化必须 Scope Change。

### P1-04 Concurrent changes

Scope 已批准后，禁止两个角色同时修改。

### P1-05 Report regeneration

同一 evidence 可以重新排版，但不能悄悄改变 technical conclusion。

---

# 5. Implementation Guardrails

1. 不先建完整 CRM。
2. 不先建 Distributor 技术操作台。
3. 不把 open-geo schema 直接写进 Portal。
4. 不把 GeoLook schema 直接写进 Core。
5. 不把 RawResponse 放进 Portal API。
6. 不让前端直接控制状态。
7. 不允许双系统自由双写。
8. 不用 event bus 解决尚未存在的规模问题。
9. 不为未来 billing / commission 提前设计几十个表。
10. 不在 MVP 追求“通用工作流平台”。

---

# 6. Go / No-Go

### GO
进入：

- Technical Specification
- API contract
- Data model
- State transition implementation
- MVP backlog

### NO-GO
尚不能：

- 直接开始 Portal 全量开发
- 接入 CRM / Billing
- 公开 Query Builder
- 把 open-geo 当成 Core
- 宣称 GEO → Revenue attribution

**最终裁定：CONDITIONAL PASS。**

关闭 P0-01～P0-07 后，进入 MVP Coding。
