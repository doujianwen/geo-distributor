# ADR-004: GeoLook as Action / Verification Adapter

**状态：** Accepted
**日期：** 2026-09-10
**版本：** V0.1

---

## 上下文

GeoLook 具备 Action Ticket、Owner、Effort、Acceptance Criteria、Before/Current/Target、Re-open、Verification、Delivery Package、Content Workbench、Site Audit、Citation/Source analysis 等能力。

## 决策

**GeoLook 不作为本系统 Core。**

定位：
> **Action / Verification Adapter + External Methodology Reference**

## 可复用方向

- Action Ticket
- Owner
- Effort
- Acceptance Criteria
- Before / Current / Target
- Re-open
- Verification
- Delivery Package
- Content Workbench
- Site Audit
- Citation / Source analysis

## 风险

GeoLook 的 Verification 不等同于 Causal Effect。

因此：
> **Verification Complete ≠ Intervention Caused Improvement**

外部评分规则、方法规则也不能自动成为本系统 Canonical Methodology。

## Consequence

GeoLook 的能力通过 Adapter 接入，HQ Core 决定最终诊断结论和干预策略。