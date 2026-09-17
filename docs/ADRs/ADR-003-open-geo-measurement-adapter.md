# ADR-003: open-geo as Measurement Adapter

**状态：** Accepted
**日期：** 2026-09-10
**版本：** V0.1

---

## 上下文

open-geo 是当前主要的高保真采集能力来源，具备真实浏览器环境、真实 AI 平台采样、QueryCapture、sources/citations 分离、screenshot、answer text、brand mention、source/citation rank 等能力。

## 决策

**open-geo 定位为：High-Fidelity Measurement Adapter**

而不是 GEO Core。

## Reason

open-geo 的优势使其适合 Observation-first / Evidence-first 架构，但不应该成为 Canonical Model 的定义者。

## Integration Boundary

**输入：**
```text
Query
Engine
Lens
Sampling Environment
Run Context
```

**输出：**
```text
QueryCapture
```

再由本系统转换为：
```text
RawResponse
Observation
Measurement
Evidence
```

## 禁止

- 不能直接把 open-geo 数据库结构作为本系统 Canonical Model
- 不能绕过 Adapter 直接调用 open-geo 内部函数
- 不能在 Service Contract 中暴露 open-geo schema

## Consequence

如果未来替换 open-geo，只需替换 Adapter，不影响上层业务。