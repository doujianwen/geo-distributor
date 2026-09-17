# ADR-001: Own the Core

**状态：** Accepted
**日期：** 2026-09-10
**版本：** V0.1

---

## 上下文

系统中存在多种数据源：geo-collector（当前）、Elmo（候选 P1）、未来可能接入的其他 Provider。
不同源的数据结构各不相同，如果业务层直接依赖某个源的原生结构，将导致：

1. 切换源时需要修改业务代码
2. 多源对比困难（字段不对齐）
3. 未来扩展成本高
4. 方法论被外部项目定义的风险

## 决策

**核心 GEO 数据模型、证据模型、诊断模型与解释层由本系统自己拥有。**

```text
Core Domain Model (本系统拥有)
├── Prompt
├── Observation
├── Evidence
├── Citation
├── Measurement
├── Diagnosis
├── InterventionHypothesis
├── Experiment
├── ReMeasurement
├── ObservedEffect
└── Interpretation
```

外部开源项目通过 Adapter 接入，不定义 Canonical Model。

## Rationale

核心能力决定未来的方法论、数据资产、客户交付质量、多 Provider 能力与 Distributor 规模化，因此不能把 Canonical Model 绑定到某个第三方项目。

## Consequence

外部开源项目必须通过 Adapter 接入。