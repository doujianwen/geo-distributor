# 海外 GEO 分销系统
## 技术架构 ADR 汇总 V1.1

本版本在 V1.0 基础上补充 HQ Technical Delivery / Service Contract Red-Team 审计后的决策。

| ADR | 决策 |
|---|---|
| ADR-001 | Own the Core |
| ADR-002 | Compose at Explicitly Defined Boundaries |
| ADR-003 | open-geo = High-Fidelity Measurement Adapter |
| ADR-004 | GeoLook = Action / Verification Adapter |
| ADR-005 | Observation First |
| ADR-006 | Evidence First |
| ADR-007 | Distributor 不承担标准技术采样 |
| ADR-008 | HQ Technical Delivery Centralized |
| ADR-009 | Two-System Architecture |
| ADR-010 | Technical Truth Owned by HQ |
| ADR-011 | Dual Report |
| ADR-012 | GrowthBook 暂不集成 |
| ADR-013 | PostHog 属于未来 Business Behavior Layer |
| ADR-014 | CRM 暂不建设 |
| ADR-015 | L4 Attribution 不承诺 |
| ADR-016 | Capability Ladder |
| ADR-017 | Commercial Claim Discipline |
| ADR-018 | 不过度治理 |
| ADR-019 | 当前优先级：L0-L2 + Distributor MVP |
| ADR-020 | Decision Change Protocol |
| ADR-021 | Service Request ≠ Project ≠ Work Item |
| ADR-022 | Intake Completeness Gate |
| ADR-023 | Technical Scope Freeze |
| ADR-024 | Source-of-Truth 分离 |
| ADR-025 | Query/Engine 变化按商业影响判断 Scope Change |
| ADR-026 | open-geo / GeoLook 不进入 Service Contract |
| ADR-027 | Distributor 只消费 Client-safe Technical Result |

## ADR-021 — Service Request ≠ Project ≠ Work Item

### Context
一个商业需求可能同时包含 Measurement、Diagnosis、Intervention、ReMeasurement。

### Decision
采用三层对象：

```text
Service Request → Project → Work Items
```

### Consequence
可以灵活组合服务，而不需要修改 Core。

---

## ADR-022 — Intake Completeness Gate

### Decision
所有 Service Request 必须经过 Intake Review。

资料不足时进入 `CLARIFICATION_REQUIRED`，不得直接进入技术执行。

### Rationale
降低 HQ 与 Distributor 之间的低效往返。

---

## ADR-023 — Technical Scope Freeze

### Decision
HQ 负责把商业需求转换为 Technical Scope。批准后冻结。

影响商业价格、周期、市场、Engine、Query Volume、Service Stage 或 Deliverable 的变化，必须进入 Scope Change。

### Rationale
防止技术团队在执行阶段不断扩大范围。

---

## ADR-024 — Source-of-Truth 分离

### Decision
Distributor Portal 是商业 Source of Truth；HQ System 是技术 Source of Truth。

采用：

```text
Command In → HQ → Result Out
```

而不是两个系统自由双向写入。

---

## ADR-025 — Scope Change 按商业影响判断

### Decision
Query / Engine 字段变化本身不等于 Scope Change。

如果只属于技术修正 → Revision/Rework。

如果改变价格、周期、范围、交付物 → Scope Change。

---

## ADR-026 — 外部项目不得成为 Service Contract

### Decision
open-geo、GeoLook 的内部 schema 不直接暴露为 Distributor Portal API。

原因：

1. 防止 Vendor/Open-source lock-in。
2. 防止外部项目改变 Canonical Model。
3. 保留替换 Adapter 的能力。

---

## ADR-027 — Distributor 只消费 Client-safe Technical Result

### Decision
Distributor 可以查看项目状态、关键发现、诊断摘要、建议和 Client-safe Report。

禁止直接访问：

- RawResponse
- Parser internals
- Validity Engine
- Provider internals
- Debug data
- Evidence grading internals

### Rationale
HQ 必须保持技术真相的完整性，同时让 Distributor 足够完成销售和客户关系工作。

---

# Final Architecture Principle

> Distributor sells; HQ delivers.
>
> Distributor owns the client relationship; HQ owns technical truth.
>
> Commercial requests enter through a stable Service Contract; technical execution remains inside HQ boundaries.
>
> External open-source projects provide capabilities through explicit adapters, never by redefining the Core.
