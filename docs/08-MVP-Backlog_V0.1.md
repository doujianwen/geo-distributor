# 海外 GEO 分销系统
## MVP Backlog V0.1

**目标：**用最小可运行闭环验证“Distributor 卖 → HQ 接单 → HQ 技术交付 → Distributor 获取结果”。

**MVP 不追求：**完整 SaaS、完整 CRM、完整自动化 GEO 平台。

---

# 1. MVP North Star

完成第一条真实闭环：

```text
Distributor
  ↓
Create Client
  ↓
Submit GEO Request
  ↓
HQ Intake
  ↓
Technical Scope
  ↓
Approval
  ↓
Project
  ↓
Measurement
  ↓
Evidence / Findings
  ↓
QA
  ↓
Client-safe Report
  ↓
Distributor sees result
```

---

# 2. Priority Definition

- **P0**：没有它，MVP 无法安全运行
- **P1**：没有它，MVP 可以运行但交付能力明显不足
- **P2**：验证后再做

---

# 3. EPIC A — Identity / Tenant / Access

## A-01 Distributor identity — P0

**Goal:** Distributor 用户可以登录并只访问自己的数据。

Acceptance:
- 用户有 distributor_id
- API 从 session/token 得到身份
- 不接受客户端提交的任意 distributor_id 作为授权依据

Dependency: none

## A-02 HQ roles — P0

Roles:
- HQ_OPERATOR
- HQ_REVIEWER
- HQ_ADMIN

Acceptance:
- Operator 可执行技术任务
- Reviewer 可 QA / publish
- Admin 可管理系统

## A-03 Object ownership guard — P0

Acceptance:
- Distributor A 无法读取 Distributor B 的 Client/Project
- Client/Project ownership 在后端强制验证

---

# 4. EPIC B — Client / Request Intake

## B-01 Create Client — P0

Fields:
- name
- website
- industry
- distributor_id

Acceptance:
- Client 自动绑定当前 Distributor
- 重复提交不创建重复 Client

## B-02 Create Service Request — P0

Acceptance:
- 必填字段校验
- 生成 SR ID
- 支持 Idempotency-Key

## B-03 Intake Review — P0

Acceptance:
- HQ 可接受 / 要求补充 / Reject
- 缺失字段结构化记录
- Distributor 可以看到 clarification request

## B-04 Clarification loop — P0

Acceptance:
- Distributor 补资料后回到 INTAKE_REVIEW
- 不创建第二个 Request

---

# 5. EPIC C — Technical Scoping

## C-01 Create Technical Scope — P0

Acceptance:
- 仅 HQ 创建
- Scope 有 version
- Scope 与 Request 关联

## C-02 Scope approval — P0

Acceptance:
- 未批准不能执行
- 批准后 Scope immutable

## C-03 Scope change — P1

Acceptance:
- 支持 Change Request
- 新 Scope version
- 原版本保留

---

# 6. EPIC D — Project / Work Item

## D-01 Create Project — P0

Acceptance:
- Approved Scope 才能创建
- 自动继承 distributor/client

## D-02 Create Work Item — P0

MVP types:
- MEASUREMENT
- DIAGNOSIS
- REPORT
- QA

Intervention / ReMeasurement 可以保留接口，但第一条商业 MVP 不必完整实现。

## D-03 Work Item state transition — P0

Acceptance:
- 后端校验合法 transition
- 记录 actor/time
- 非法 transition 返回 INVALID_STATE_TRANSITION

## D-04 Block / Rework — P1

Acceptance:
- 可以记录 blocked_reason
- 可以恢复
- QA failure 可以进入 Rework

---

# 7. EPIC E — GEO Core Integration

## E-01 Canonical Observation model — P0

Acceptance:
- adapter result 可以转换为 Observation
- 不把外部 adapter schema 当 Canonical schema

## E-02 Canonical Measurement model — P0

Acceptance:
- Measurement 有 provenance
- 可关联 Project / Work Item

## E-03 Evidence record — P0

Acceptance:
- evidence 可追溯到 measurement
- source / capture context 保留

---

# 8. EPIC F — open-geo Adapter

## F-01 Adapter interface — P0

先实现内部 interface + Mock Adapter。

Acceptance:
- Core 只依赖 MeasurementAdapter
- Mock 可以产生标准 MeasurementResult

## F-02 open-geo adapter — P1

Acceptance:
- QueryCapture 能映射到 Observation
- sources 与 citations 不混淆
- sampling metadata 保留
- adapter failure 可转换为标准 error

**注意：**如果真实 open-geo 集成需要额外运行环境，不阻塞 Core MVP；先用 Mock 验证边界。

---

# 9. EPIC G — Diagnosis / Findings

## G-01 Diagnosis object — P1

Acceptance:
- diagnosis 只能引用已有 evidence
- 不允许无 evidence 的 technical verdict

## G-02 Client-safe Findings — P0

Acceptance:
- HQ 可生成 Distributor-safe findings
- 不暴露 RawResponse/debug data

## G-03 Recommendation — P1

Acceptance:
- recommendation 可关联 diagnosis
- 不承诺 AI recommendation / revenue outcome

---

# 10. EPIC H — Delivery / Report

## H-01 Delivery Package — P0

Acceptance:
- report_id
- version
- scope_version
- findings
- created_by

## H-02 Client-safe report — P0

Acceptance:
- Distributor 可以查看
- HQ-only 信息过滤

## H-03 Report versioning — P0

Acceptance:
- v1/v2 均可追溯
- 不覆盖历史版本

---

# 11. EPIC I — QA

## I-01 QA checklist — P0

最小检查：

- Scope compliance
- Measurement completeness
- Evidence linkage
- Findings consistency
- Client-safe filtering

## I-02 Publish gate — P0

Acceptance:
- QA 未通过不能发布
- 只有 Reviewer/Admin 可以 Publish

---

# 12. EPIC J — Audit / Observability

## J-01 Audit event — P0

记录：
- actor
- action
- object
- state before/after
- timestamp
- correlation_id

## J-02 Request correlation — P0

每个 API command 生成/接受 correlation_id。

Acceptance:
- 可从 Request 查到 Project / Work Item / Delivery 操作链

## J-03 Basic operational log — P1

仅记录：
- request failure
- adapter failure
- state transition failure
- QA failure

不建设完整日志平台。

---

# 13. EPIC K — Distributor Portal MVP

## K-01 Client list — P0

## K-02 Client detail — P0

## K-03 Submit request — P0

## K-04 Request status — P0

## K-05 Project list — P0

## K-06 Project detail — P0

## K-07 Clarification response — P0

## K-08 View report — P0

Distributor 页面只展示 Client-safe data。

---

# 14. EPIC L — HQ Console MVP

## L-01 Request queue — P0

## L-02 Intake review — P0

## L-03 Scope editor — P0

## L-04 Project workspace — P0

## L-05 Work item execution state — P0

## L-06 Evidence / findings view — P1

## L-07 QA review — P0

## L-08 Publish delivery — P0

HQ Console 不需要做成复杂 GEO IDE。

---

# 15. Recommended Build Sequence

### Sprint 0 — Contract Skeleton

A-01 / A-02 / A-03
B-01 / B-02
C-01
D-01

**Exit:** 用户、Client、Request、Scope、Project 可以建立并隔离。

### Sprint 1 — Intake → Scope → Project

B-03 / B-04
C-02
D-02 / D-03
J-01 / J-02

**Exit:** 一条合法 Request 可以进入 Approved Project。

### Sprint 2 — Measurement Core

E-01 / E-02 / E-03
F-01

**Exit:** Mock Measurement 可以进入 Canonical GEO Core。

### Sprint 3 — Delivery

G-02
H-01 / H-02 / H-03
I-01 / I-02
K-04 / K-05 / K-06 / K-08
L-04 / L-07 / L-08

**Exit:** HQ 可以完成一次可交付的 client-safe report。

### Sprint 4 — Real Adapter

F-02
G-01 / G-03
J-03

**Exit:** 使用真实 open-geo 完成一条 Measurement → Evidence → Findings → Report 链路。

### Sprint 5 — Pilot Hardening

D-04
C-03
K-07
更多失败场景测试

**Exit:** 可以拿一个真实 Distributor / Client pilot。

---

# 16. MVP Test Scenarios

必须至少覆盖：

1. 正常 Request
2. 缺资料 Request
3. Distributor 越权读取
4. 未批准 Scope 执行
5. 重复提交同一 Request
6. 非法 State Transition
7. Measurement failure
8. Project blocked
9. QA failure → Rework
10. Report v1 → v2
11. Scope Change
12. Distributor 只能看到 client-safe result
13. HQ 能追踪完整 audit trail

---

# 17. MVP Exit Criteria

### Business
- 至少完成一条真实或高度仿真的 Distributor → HQ → Delivery 闭环。

### Technical
- 0 个 P0 security / contract blocker。
- 关键状态机测试全部通过。
- Idempotency 测试通过。
- Tenant isolation 测试通过。
- Report versioning 测试通过。

### GEO
- 至少一个 Measurement Adapter。
- Canonical Observation / Measurement / Evidence 可以形成完整链路。

### Commercial
- Distributor 无需技术操作即可提交需求、查看状态、获得报告。
- HQ 可以独立完成技术交付。

---

# 18. Deliberately Deferred

以下全部进入 Backlog，不阻塞 MVP：

- CRM
- Billing
- Commission
- Multi-level Distributor hierarchy
- Client direct login
- Advanced workflow engine
- GrowthBook
- PostHog
- Revenue attribution
- Automated intervention execution
- Advanced scheduling
- Full multi-region deployment
