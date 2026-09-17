# 海外 GEO 分销系统
## Technical Specification V0.1

**状态：MVP IMPLEMENTATION SPEC**
**原则：** Contract-first / Observation-first / HQ-owned technical truth / Minimal infrastructure

---

# 1. System Boundary

```text
┌─────────────────────────────┐
│      Distributor Portal     │
│ Lead / Client / Request     │
│ Project View / Reports      │
└──────────────┬──────────────┘
               │ Command / Query
               ▼
┌─────────────────────────────┐
│      HQ Delivery API        │
├─────────────────────────────┤
│ Intake / Scope / Project    │
│ Work Item / Delivery / QA   │
└──────────────┬──────────────┘
               ▼
┌─────────────────────────────┐
│          GEO Core            │
│ Observation / Measurement    │
│ Evidence / Diagnosis         │
└──────────────┬──────────────┘
               ▼
       Adapter Interfaces
        ┌──────┴──────┐
        ▼             ▼
    open-geo       GeoLook
```

Portal never imports Core implementation modules.

---

# 2. MVP Technology Shape

推荐保持简单：

```text
Portal UI
   ↓
HQ API
   ↓
Application Services
   ↓
Domain Model
   ↓
Repository
   ↓
PostgreSQL / SQLite for early local development
```

不要在 MVP 引入：

- microservices
- Kafka
- Kubernetes
- distributed workflow engine

生产部署可以后续演进。

---

# 3. Domain Objects

## 3.1 Distributor

```json
{
  "id": "DST-001",
  "name": "Example Distribution",
  "status": "ACTIVE"
}
```

## 3.2 Client

```json
{
  "id": "CLI-001",
  "distributor_id": "DST-001",
  "name": "Acme",
  "website": "https://example.com",
  "status": "ACTIVE"
}
```

## 3.3 Service Request

必需：

```text
id
distributor_id
client_id
market
industry
business_question
service
website(if applicable)
submitted_by
created_at
```

可选：

```text
target_customer
requested_engines
competitors
attachments
```

---

# 4. Technical Scope

Scope 是 HQ 产生的技术合同，而不是 Distributor 输入对象。

字段：

```text
scope_id
request_id
markets
engines
query_policy
measurement_rounds
diagnosis
intervention
remeasurement
deliverables
assumptions
exclusions
version
status
approved_by
approved_at
```

状态：

```text
DRAFT
PENDING_APPROVAL
APPROVED
SUPERSEDED
CANCELLED
```

Scope Approved 后不可原地修改。

---

# 5. Project

```text
project_id
request_id
scope_id
distributor_id
client_id
status
owner_team
created_at
updated_at
```

Project 是交付生命周期容器。

---

# 6. Work Item

```text
work_item_id
project_id
type
status
owner
scope_ref
depends_on
attempt_count
started_at
completed_at
blocked_reason
```

MVP `type`：

```text
MEASUREMENT
DIAGNOSIS
INTERVENTION
REMEASUREMENT
REPORT
QA
```

MVP 只支持简单依赖：

```text
A → B → C
```

不做任意 DAG builder UI。

---

# 7. Canonical GEO Objects

```text
RawResponse
Observation
Measurement
Evidence
Diagnosis
InterventionHypothesis
Experiment
ReMeasurement
ObservedEffect
Interpretation
```

这些对象只由 HQ Core 管理。

---

# 8. API Contract

## 8.1 POST /service-requests

用途：创建 Service Request。

Headers：

```text
Authorization
Idempotency-Key
X-Correlation-ID
```

返回：

```json
{
  "request_id": "SR-001",
  "status": "SUBMITTED"
}
```

---

## 8.2 POST /service-requests/{id}/review

HQ Intake Review。

结果：

```text
ACCEPTED
CLARIFICATION_REQUIRED
REJECTED
```

---

## 8.3 POST /service-requests/{id}/scope

HQ 创建 Scope。

只允许 HQ role。

---

## 8.4 POST /projects/{id}/approve

审批 Scope / Project。

必须满足：

- Scope exists
- Scope status = PENDING_APPROVAL
- required commercial approval exists

---

## 8.5 POST /projects/{id}/work-items

创建技术 Work Item。

只允许 HQ。

---

## 8.6 POST /work-items/{id}/transition

后端执行状态迁移。

前端不得直接 PUT status。

---

## 8.7 GET /projects/{id}

返回 Distributor-safe Project View。

不返回 RawResponse / parser / debug data。

---

## 8.8 GET /projects/{id}/delivery

返回 Delivery Result + client-safe report metadata。

---

# 9. Idempotency Contract

适用于所有 command endpoint。

```text
same key + same payload → same logical result
same key + different payload → 409 IDEMPOTENCY_CONFLICT
```

建议保存：

```text
idempotency_key
actor_id
endpoint
request_hash
response_snapshot
created_at
```

---

# 10. State Transition Rules

## Request

```text
DRAFT → SUBMITTED
SUBMITTED → INTAKE_REVIEW
INTAKE_REVIEW → CLARIFICATION_REQUIRED
INTAKE_REVIEW → SCOPING
INTAKE_REVIEW → REJECTED
CLARIFICATION_REQUIRED → INTAKE_REVIEW
SCOPING → SCOPE_PENDING_APPROVAL
SCOPE_PENDING_APPROVAL → APPROVED
```

## Project

```text
APPROVED → IN_EXECUTION
IN_EXECUTION → QA
QA → DELIVERED
DELIVERED → ACCEPTED
```

异常：

```text
IN_EXECUTION → BLOCKED
BLOCKED → IN_EXECUTION
QA → REWORK
REWORK → IN_EXECUTION
DELIVERED → CHANGES_REQUESTED
CHANGES_REQUESTED → REWORK / SCOPE_CHANGE
```

每次迁移记录 Audit Event。

---

# 11. Scope Change

系统必须把 change request 分成：

### REWORK
技术执行纠错，不改变商业承诺。

### SCOPE_CHANGE
改变：

- market
- material engine coverage
- material query volume
- service stage
- deliverables
- price
- delivery commitment

Scope Change 产生新 Scope version。

```text
SCOPE-001 v1 APPROVED
        ↓
Change Request
        ↓
SCOPE-001 v2 PENDING_APPROVAL
```

---

# 12. Delivery Artifact

每个 Delivery 至少包含：

```text
delivery_id
project_id
report_id
report_version
scope_version
completed_work_items
findings_summary
client_safe_report
created_at
created_by
```

Delivery 不可静默覆盖。

---

# 13. Authorization Matrix

| Action | Distributor | HQ Operator | HQ Reviewer | HQ Admin |
|---|---:|---:|---:|---:|
| Create Request | ✓ | - | - | - |
| View Own Client | ✓ | ✓ | ✓ | ✓ |
| Review Intake | - | ✓ | ✓ | ✓ |
| Create Scope | - | ✓ | ✓ | ✓ |
| Approve Technical Scope | - | - | ✓ | ✓ |
| Create Work Item | - | ✓ | ✓ | ✓ |
| Execute Technical Work | - | ✓ | - | ✓ |
| QA | - | - | ✓ | ✓ |
| Publish Client Report | - | - | ✓ | ✓ |
| View RawResponse | - | ✓ | ✓ | ✓ |
| Change Commercial Scope | Request only | - | - | - |

---

# 14. Data Exposure Rules

### Portal-safe

- status
- scope summary
- key findings
- diagnosis summary
- recommendations
- delivery report
- next step

### HQ-only

- RawResponse
- provider internals
- parser output
- browser logs
- validity internals
- evidence grading internals
- query generation internals
- technical notes

---

# 15. Error Codes

```text
INVALID_REQUEST
UNAUTHORIZED
FORBIDDEN
NOT_FOUND
CLARIFICATION_REQUIRED
SCOPE_NOT_APPROVED
SCOPE_CHANGE_REQUIRED
ACCESS_BLOCKED
PROVIDER_UNAVAILABLE
MEASUREMENT_FAILED
QA_FAILED
IDEMPOTENCY_CONFLICT
INVALID_STATE_TRANSITION
```

所有错误至少包含：

```text
error_code
message
correlation_id
retryable
```

---

# 16. Audit Event

```json
{
  "event_id": "EVT-001",
  "actor_id": "USR-001",
  "actor_role": "HQ_OPERATOR",
  "action": "PROJECT_STATE_CHANGED",
  "object_type": "PROJECT",
  "object_id": "PRJ-001",
  "previous_state": "IN_EXECUTION",
  "new_state": "QA",
  "correlation_id": "COR-001",
  "created_at": "2026-09-13T00:00:00Z"
}
```

---

# 17. Adapter Interfaces

## MeasurementAdapter

```python
class MeasurementAdapter:
    def measure(self, scope, query_set, context) -> MeasurementResult:
        ...
```

Adapter 不直接写 Portal。

## ActionVerificationAdapter

```python
class ActionVerificationAdapter:
    def evaluate(self, evidence, diagnosis_context) -> ActionResult:
        ...
```

---

# 18. MVP Definition of Done

系统只有同时满足以下条件，才算 MVP Ready：

1. Distributor 可以创建 Request。
2. HQ 可以 Intake Review。
3. HQ 可以创建 Scope。
4. Scope 可以审批并冻结。
5. Project 可以创建。
6. Work Item 可以执行/阻塞/重做。
7. 至少一个 Measurement Adapter 可以返回标准结果。
8. Measurement 可以进入 Canonical Observation/Measurement。
9. HQ 可以创建 client-safe findings。
10. QA 后可以发布 Delivery。
11. Distributor 只能看到授权 Project。
12. 重复 command 不产生重复对象。
13. 所有状态变化可审计。
14. Report 有版本，不静默覆盖。

---

# 19. Explicit Non-goals

- CRM
- Billing
- Commission
- Revenue attribution
- Distributor technical sampling
- Distributor query builder
- arbitrary workflow engine
- full client IAM
- microservice decomposition
- event bus
