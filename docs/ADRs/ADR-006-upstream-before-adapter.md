# ADR-006: Upstream Before Adapter

**状态：** Accepted
**日期：** 2026-09-10
**版本：** V0.2

---

## 上下文

Elmo 是当前 P1 候选开源系统。存在诱惑：提前实现 `ElmoAdapter` 以显示"进展"。
但这违反了我们建立的流程：审计 → 验证 → 决策 → 开发。

## 决策

**必须先完成 `A1.6 Compatibility Report`，再决定是否开发 `ElmoAdapter`。**

## 约束

- ❌ 禁止因 Elmo 是 P1 就提前实现 `ElmoAdapter`
- ✅ `ElmoAdapter` 接口已定义（V0.2），等待验证后填充实现
- ✅ `GeoCollectorAdapter` 作为 fallback 始终可用
