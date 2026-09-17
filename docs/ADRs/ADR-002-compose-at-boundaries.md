# ADR-002: Compose at Explicitly Defined Boundaries

**状态：** Accepted
**日期：** 2026-09-10
**版本：** V0.1

---

## 上下文

存在诱惑：因为某个外部项目"功能很多"就整体引入。这会导致：
- Vendor lock-in
- 方法论被外部定义
- 未来替换成本高

## 决策

采用：
> **Compose at Explicitly Defined Boundaries**

而不是 Compose Everything 或 Fork Everything。

## Rules

外部系统必须回答：
1. 它解决什么问题？
2. 它的输入是什么？
3. 它的输出是什么？
4. 哪些数据属于本系统 Canonical Model？
5. 哪些能力由外部系统拥有？
6. 如何替换外部系统？

不能因为"项目功能很多"就整体引入。

## Consequence

每个外部集成必须有明确的边界定义。