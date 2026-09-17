# ADR-005: Observation First Architecture

**状态：** Accepted
**日期：** 2026-09-10
**版本：** V0.2

---

## 上下文

系统中存在多种数据源：geo-collector（当前）、Elmo（候选 P1）、未来可能接入的其他 Provider。
不同源的数据结构各不相同，如果业务层直接依赖某个源的原生结构，将导致：

1. 切换源时需要修改业务代码
2. 多源对比困难（字段不对齐）
3. 未来扩展成本高

## 决策

**所有 Adapter 必须输出同一个 `PlatformObservation` 对象。**

```
Provider (any)
      ↓
  Adapter
      ↓
Compatibility Layer (mapping)
      ↓
PlatformObservation  ← 统一契约
      ↓
Business Layer (只依赖此对象)
```

## 约束

- ❌ 禁止业务层直接 import `storage.models.Observation`
- ❌ 禁止业务层直接依赖任何 Provider 的原生数据结构
- ✅ 所有外部数据必须通过 `compatibility/` 层的映射函数转换
- ✅ 新 Provider 只需实现一个 mapping 函数，不改业务层

## 后果

- 新增 Provider：只需实现一个 mapping 函数（~30行）
- 上游 schema 变更：只改 mapping 函数，不影响上层
- 多源对比：所有 Observation 字段对齐，可直接横向比较

---
