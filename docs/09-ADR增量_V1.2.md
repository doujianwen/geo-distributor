# 海外 GEO 分销系统
## ADR 增量 V1.2

本版本对应 Implementation Readiness Audit V0.1、Technical Specification V0.1、MVP Backlog V0.1。

| ADR | 决策 |
|---|---|
| ADR-028 | Implementation Readiness 采用 Conditional Pass：关闭 P0 后进入编码 |
| ADR-029 | MVP 采用最小 Tenant / Ownership Isolation |
| ADR-030 | Command API 必须支持 Idempotency-Key |
| ADR-031 | 状态迁移由后端 transition guard 控制 |
| ADR-032 | Scope / Delivery Artifact 不可静默覆盖，采用 versioning |
| ADR-033 | MVP 必须保留最小 Audit Trail |
| ADR-034 | Client-safe Report 与 HQ Technical Report 分离生成 |
| ADR-035 | MVP 采用 Modular Monolith / 单一应用边界，不提前微服务化 |
| ADR-036 | Work Item MVP 采用有限类型 + 简单依赖，不建设通用 Workflow Builder |
| ADR-037 | open-geo 先以 Mock Adapter 验证 Core Boundary，再接真实 Adapter |
| ADR-038 | Client Direct IAM 暂缓，Distributor 作为商业入口 |
| ADR-039 | Intervention / ReMeasurement 保留接口，首个 MVP 不以完整自动执行为阻塞条件 |

## ADR-028 — Conditional Pass

Implementation Readiness Audit 结论为 Conditional Pass。原因不是架构方向不成立，而是身份、隔离、幂等、状态保护、版本和审计仍需实现级定义。

## ADR-029 — Minimal Tenant Isolation

MVP 采用 Distributor → Client → Project 的 ownership chain。暂不建设复杂组织层级。

## ADR-030 — Idempotent Commands

所有创建与状态迁移 command 必须支持 Idempotency-Key。

## ADR-031 — Backend Transition Guard

前端只能请求 transition，不能直接写 status。

## ADR-032 — Immutable Versioning

Scope 与 Delivery Artifact 均采用版本化，不做静默覆盖。

## ADR-033 — Minimal Audit Trail

MVP 必须能回答“谁、何时、对什么对象做了什么状态变化”。

## ADR-034 — Dual Report Generation

Client-safe Report 与 HQ Technical Report 在交付层明确分离。

## ADR-035 — Modular Monolith First

在当前规模下，不因未来多 Distributor / 多 Client 提前引入微服务、消息总线、分布式工作流。

## ADR-036 — Bounded Work Item Model

MVP 支持 Measurement、Diagnosis、Report、QA，并预留 Intervention / ReMeasurement；不建设任意 DAG 工作流编辑器。

## ADR-037 — Mock Before Real Adapter

先验证 Canonical Core 与 MeasurementAdapter 接口，再连接 open-geo。这样即使 open-geo 集成环境变化，也不会污染 Core。

## ADR-038 — No Client IAM Yet

首个商业 Pilot 由 Distributor 作为客户关系入口。Client 独立账号不是 MVP 必需条件。

## ADR-039 — Intervention / ReMeasurement Not MVP Blockers

能力层面必须保留，但首个商业闭环先验证 Measurement → Evidence → Findings → Delivery；否则会把尚未商业验证的 L3.5 过早工程化。
