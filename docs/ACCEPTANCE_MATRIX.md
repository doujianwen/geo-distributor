# MVP Acceptance Matrix

## Specification Compliance Audit

**Date**: 2026-09-13
**Auditor**: Copilot-Prime
**Status**: CONDITIONAL PASS → 修复中

---

## 1. ADR Compliance Check

| ADR ID | Title | Status | Evidence |
|--------|-------|--------|----------|
| ADR-029 | Canonical Core | ✅ PASS | `geo_distributor/models/geo_core.py` 完整实现 |
| ADR-030 | Idempotency Guard | ✅ PASS | `geo_distributor/guards/idempotency.py` |
| ADR-031 | State Transition Guard | ⚠️ CONDITIONAL | 部分场景未覆盖 RBAC |
| ADR-032 | Versioning Immutability | ✅ PASS | `Report.add_version()` 保留历史 |
| ADR-033 | Audit Trail | ⚠️ CONDITIONAL | 已实现但集成度不足 |
| ADR-034 | Client-safe Isolation | ✅ PASS | `Report.add_version()` 过滤逻辑完整 |

---

## 2. MVP Backlog Scenario Coverage

### 2.1 Distributor Scenarios (B)

| Scenario ID | Description | Test File | Status |
|-------------|-------------|-----------|--------|
| B-01 | Create Client with auto-tenant binding | `test_distributor_service.py::test_create_client` | ✅ PASS |
| B-02 | Duplicate client returns existing | `test_distributor_service.py::test_duplicate_client` | ✅ PASS |
| B-03 | Create Service Request with validation | `test_sprint1_intake_scope_project.py::test_submit_request` | ✅ PASS |
| B-04 | Required fields validation | `test_sprint1_intake_scope_project.py::test_submit_request_missing_fields` | ✅ PASS |
| B-05 | Idempotency key prevents duplicate | `test_sprint1_intake_scope_project.py::test_idempotency_submit` | ✅ PASS |

### 2.2 Intake & Clarification (C)

| Scenario ID | Description | Test File | Status |
|-------------|-------------|-----------|--------|
| C-01 | HQ intakes request and approves | `test_sprint1_intake_scope_project.py::test_intake_review_approve` | ✅ PASS |
| C-02 | HQ requests clarification | `test_sprint1_intake_scope_project.py::test_intake_clarification_required` | ✅ PASS |
| C-03 | Clarification loop - distributor resubmits | `test_sprint1_intake_scope_project.py::test_clarification_loop` | ✅ PASS |
| C-04 | Rejected request cannot proceed | `test_sprint1_intake_scope_project.py::test_reject_request` | ✅ PASS |

### 2.3 Scope Management (D)

| Scenario ID | Description | Test File | Status |
|-------------|-------------|-----------|--------|
| D-01 | Create Technical Scope (HQ only) | `test_sprint1_intake_scope_project.py::test_create_scope` | ✅ PASS |
| D-02 | Scope versioning - v1 created | `test_sprint1_intake_scope_project.py::test_scope_versioning` | ✅ PASS |
| D-03 | Approve scope creates project | `test_sprint1_intake_scope_project.py::test_approve_scope` | ✅ PASS |
| D-04 | Scope is immutable after approval | `test_sprint1_intake_scope_project.py::test_scope_immutable_after_approval` | ✅ PASS |

### 2.4 Project Workflow (E)

| Scenario ID | Description | Test File | Status |
|-------------|-------------|-----------|--------|
| E-01 | Create Project from approved scope | `test_sprint1_intake_scope_project.py::test_create_project` | ✅ PASS |
| E-02 | Project inherits tenant/client from request | `test_sprint1_intake_scope_project.py::test_project_inherits_context` | ✅ PASS |
| E-03 | Cannot execute without scope approval | `test_sprint1_intake_scope_project.py::test_cannot_execute_unapproved` | ✅ PASS |

### 2.5 Measurement Core (F)

| Scenario ID | Description | Test File | Status |
|-------------|-------------|-----------|--------|
| F-01 | MockAdapter returns PlatformObservation | `test_sprint2_mock_adapter.py::test_mock_adapter_structure` | ✅ PASS |
| F-02 | Canonical Observation model | `test_sprint2_mock_adapter.py::test_canonical_observation_model` | ✅ PASS |
| F-03 | Measurement has provenance | `test_sprint2_mock_adapter.py::test_measurement_provenance` | ✅ PASS |
| F-04 | Evidence traces to observation | `test_sprint2_mock_adapter.py::test_evidence_traces_to_observation` | ✅ PASS |

### 2.6 Delivery & QA (G)

| Scenario ID | Description | Test File | Status |
|-------------|-------------|-----------|--------|
| G-01 | Delivery package created | `test_sprint3_delivery_qa.py::test_create_delivery_package` | ✅ PASS |
| G-02 | QA checklist passes | `test_sprint3_delivery_qa.py::test_qa_checklist_pass` | ✅ PASS |
| G-03 | QA checklist fails | `test_sprint3_delivery_qa.py::test_qa_checklist_fail` | ✅ PASS |
| G-04 | Publish gate blocks unpassed QA | `test_sprint3_delivery_qa.py::test_publish_gate_blocks_unpassed_qa` | ✅ PASS |

### 2.7 Report Models (H)

| Scenario ID | Description | Test File | Status |
|-------------|-------------|-----------|--------|
| H-01 | Client-safe report excludes internals | `test_sprint3_delivery_qa.py::test_client_safe_report_excludes_internal_data` | ✅ PASS |
| H-02 | Report versioning - v1/v2 both accessible | `test_sprint3_delivery_qa.py::test_report_versioning` | ✅ PASS |
| H-03 | Historical versions not overwritten | `test_sprint3_delivery_qa.py::test_historical_versions_preserved` | ✅ PASS |

### 2.8 Security & Isolation (I) - ⚠️ PATCH REQUIRED

| Scenario ID | Description | Test File | Status |
|-------------|-------------|-----------|--------|
| I-01 | Distributor A cannot access B's data | `test_security_red_team.py::test_tenant_isolation` | ⏳ PENDING |
| I-02 | Unauthorized role cannot transition state | `test_security_red_team.py::test_unauthorized_state_transition` | ⏳ PENDING |
| I-03 | Client-safe API excludes RawResponse | `test_security_red_team.py::test_client_safe_api_leakage` | ⏳ PENDING |

### 2.9 Audit Trail (J)

| Scenario ID | Description | Test File | Status |
|-------------|-------------|-----------|--------|
| J-01 | Audit events recorded for key actions | `test_audit_trail.py::test_audit_events` | ⏳ PENDING |
| J-02 | Correlation ID tracks operation chain | `test_audit_trail.py::test_correlation_id` | ⏳ PENDING |

---

## 3. Security Red-Team Attack Vectors

### 3.1 Tenant Isolation Attacks

| Attack Vector | Method | Expected | Status |
|---------------|--------|----------|--------|
| Direct ID enumeration | GET /requests/{B_request_id} as A | 403 Forbidden | ⏳ PENDING |
| Client ID collision | Use B's client_id to query A's data | 403 Forbidden | ⏳ PENDING |
| Project ID bypass | Direct project access without tenant | 403 Forbidden | ⏳ PENDING |

### 3.2 RBAC Bypass Attacks

| Attack Vector | Method | Expected | Status |
|---------------|--------|----------|--------|
| Distributor as HQ | Submit as distributor, execute HQ operations | 403 Forbidden | ⏳ PENDING |
| Role escalation | Modify user_role in request | Permission denied | ⏳ PENDING |

### 3.3 State Machine Attacks

| Attack Vector | Method | Expected | Status |
|---------------|--------|----------|--------|
| Skip states | DRAFT → DELIVERED directly | INVALID_TRANSITION | ⏳ PENDING |
| Reverse transition | APPROVED → DRAFT | INVALID_TRANSITION | ⏳ PENDING |

### 3.4 Idempotency Attacks

| Attack Vector | Method | Expected | Status |
|---------------|--------|----------|--------|
| Same key different payload | POST with same key, different client_id | IDEMPOTENCY_CONFLICT | ⏳ PENDING |
| Concurrent requests | Multiple requests with same key | Only first succeeds | ⏳ PENDING |

### 3.5 Version Immutability Attacks

| Attack Vector | Method | Expected | Status |
|---------------|--------|----------|--------|
| Modify v1 | Update ReportVersion v1 after v2 created | Immutable | ⏳ PENDING |
| Delete v1 | Remove v1 while v2 exists | Not allowed | ⏳ PENDING |

### 3.6 Client-Safe Leakage

| Attack Vector | Method | Expected | Status |
|---------------|--------|----------|--------|
| RawResponse in report | Include raw_response in observations | Filtered out | ⏳ PENDING |
| Technical metadata | Include debug_info, browser_logs | Filtered out | ⏳ PENDING |
| Evidence grading | Include evidence_grading details | Filtered out | ⏳ PENDING |

---

## 4. Gap Analysis

### Critical Gaps (Must Fix Before PASS)

1. **Tenant Isolation Enforcement** - Repository `find_by_id` does not enforce tenant check
2. **Audit Trail Integration** - Audit logging not integrated into all services
3. **RBAC Role Validation** - State transition guard lacks role validation for some transitions

### Medium Priority Gaps

4. **Concurrent Idempotency** - No race condition protection
5. **Version Immutability Tests** - Need explicit tests for version modification attempts

### Low Priority (Deferred)

6. **Production Audit Storage** - Current audit is in-memory, needs persistent storage
7. **Audit Query API** - No API to query audit events by correlation_id

---

## 5. Patch Plan

### Immediate Fixes (P0)

```python
# 1. Add tenant validation to find_by_id in all repositories
# 2. Integrate AuditService into all service methods
# 3. Add RBAC validation to StateTransitionGuard
```

### Testing (P0)

```python
# Create test_security_red_team.py
# Create test_audit_trail.py
```

### Verification (P1)

```python
# Run full test suite
# Verify all 13 Backlog scenarios covered
```

---

## 6. Final Verdict

**Current Status**: CONDITIONAL PASS

**Conditions for FULL PASS**:
1. All I-01 through I-03 security tests must pass
2. All J-01 through J-02 audit tests must pass
3. 13 Backlog scenarios must have explicit test coverage

**Estimated Time to Full PASS**: 2 hours (patches + tests)
