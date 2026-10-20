# 海外 GEO 分销系统
## Service Contract V0.2

**状态：IMPLEMENTATION BASELINE**

## 1. Boundary

```text
Distributor Portal
      │
      │ Service Request
      ▼
HQ Technical Delivery
      │
      │ Delivery Result
      ▼
Distributor Portal
```

Portal 不调用 GEO Core 内部 API。

## 2. Service Request

```json
{
  "request_id": "SR-001",
  "distributor_id": "DST-001",
  "client_id": "CLI-001",
  "market": ["US"],
  "industry": "industrial sensors",
  "website": "example.com",
  "target_customer": "B2B procurement teams",
  "business_question": "Why is our brand not visible in AI answers?",
  "service": "visibility_audit",
  "requested_engines": ["ChatGPT", "Google"],
  "competitors": [],
  "attachments": [],
  "submitted_by": "DST_USER"
}
```

## 3. Request Validation

Required minimum：

- client
- market
- industry/product
- business question
- service
- website/domain when applicable

Missing → `CLARIFICATION_REQUIRED`。

## 4. Technical Scope

HQ generates：

```json
{
  "scope_id": "SCOPE-001",
  "request_id": "SR-001",
  "markets": ["US"],
  "engines": ["ChatGPT", "Google"],
  "query_policy": "HQ_DEFINED",
  "measurement_rounds": 1,
  "diagnosis": false,
  "intervention": false,
  "remeasurement": false,
  "deliverables": ["client_report"],
  "assumptions": [],
  "exclusions": []
}
```

## 5. Approval

- HQ approves technical feasibility.
- Distributor confirms commercial alignment.
- Client confirms any change that affects price, scope, or delivery commitment.

After approval：Scope is frozen.

> **适用说明（2026-10-20 增补，正文未改动）**
> 本契约下实际交付期（delivery commitment）随第 5–6 节的具体服务与批准范围逐项目确定；
> 不存在适用于所有服务的统一默认交付天数。旧 V0.1 §12 的 `delivery_target_days: 7`
> 仅为字段格式示例，不构成本契约下的默认 SLA。
> 现行对外产品时效以官网现行产品规格为准：
> `geo-growth-site/docs/PRODUCT-SPEC-AI-VISIBILITY-DIAGNOSTIC-V1.0.md`
> （¥999／次 AI 可见性诊断：资料齐备并确认服务范围后 3 个工作日交付）。

## 6. Scope Change

A change is Scope Change if it changes any of：

- commercial price
- delivery commitment
- market coverage
- engine coverage materially
- query volume materially
- service stage
- deliverable set
- intervention / remeasurement commitment

Otherwise it is a Revision / Rework.

## 7. Project

```json
{
  "project_id": "PRJ-001",
  "request_id": "SR-001",
  "scope_id": "SCOPE-001",
  "distributor_id": "DST-001",
  "client_id": "CLI-001",
  "status": "IN_EXECUTION"
}
```

## 8. Work Items

A Project may contain multiple Work Items：

```text
Measurement
Diagnosis
Intervention
ReMeasurement
```

Each has independent technical status.

## 9. State Machine

### Request

```text
DRAFT
→ SUBMITTED
→ INTAKE_REVIEW
→ CLARIFICATION_REQUIRED
→ SCOPING
→ SCOPE_PENDING_APPROVAL
→ APPROVED
```

### Project

```text
APPROVED
→ IN_EXECUTION
→ QA
→ DELIVERED
→ ACCEPTED
```

Exception：

```text
BLOCKED
REWORK
CHANGES_REQUESTED
CANCELLED
```

## 10. Blocked

Required fields：

```json
{
  "blocked_reason": "client_access_missing",
  "blocked_since": "2026-09-13T00:00:00Z",
  "required_action": "Provide GA4 read access",
  "owner": "CLIENT"
}
```

## 11. Delivery Result

```json
{
  "project_id": "PRJ-001",
  "status": "DELIVERED",
  "completed_work_items": ["WI-001"],
  "findings_summary": [],
  "report_id": "RPT-001",
  "client_report_available": true,
  "next_recommended_step": "diagnosis"
}
```

## 12. Visibility Boundary

### Distributor / Client can see

- project status
- service scope
- key findings
- diagnosis summary
- recommendations
- progress
- client-safe report

### HQ only

- RawResponse
- parser output
- validity internals
- provider details
- evidence grading internals
- query generation internals
- browser/debug logs
- technical notes

## 13. Source of Truth

Portal：
- Lead
- Client
- Commercial request
- Commercial status

HQ：
- Technical Scope
- Project technical state
- Work Items
- Observation
- Measurement
- Evidence
- Diagnosis
- Intervention
- ReMeasurement
- Technical Report

## 14. Adapter Boundary

open-geo：Measurement Adapter。

GeoLook：Action / Verification Adapter。

Neither becomes the Service Contract.

## 15. Error Contract

```json
{
  "error_code": "SCOPE_NOT_APPROVED",
  "message": "Technical scope requires approval before execution.",
  "request_id": "SR-001",
  "retryable": false
}
```

Minimum error classes：

- INVALID_REQUEST
- CLARIFICATION_REQUIRED
- SCOPE_NOT_APPROVED
- ACCESS_BLOCKED
- PROVIDER_UNAVAILABLE
- MEASUREMENT_FAILED
- QA_FAILED
- SCOPE_CHANGE_REQUIRED

## 16. Contract Evolution

### Safe change
- add optional response field
- add internal metadata
- improve report wording

### Breaking change
- change required field
- change state semantics
- expose internal technical schema
- change ownership boundary

Breaking changes require new Contract version.

## 17. Current Non-goals

- Distributor Query Builder
- Distributor Sampling
- Distributor Measurement UI
- Distributor Diagnosis UI
- CRM
- Billing
- Commission
- Revenue Attribution
