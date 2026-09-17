# Sprint 4 Delta Analysis (Phase F)

> 本文件为 7 个必交付物之一（SPRINT4_DELTA_ANALYSIS.md）。

## Delta 计算口径（来自 DeltaCalculator）

```
mention_delta         = remeasurement.mention_rate      - baseline.mention_rate
citation_delta        = remeasurement.citation_rate     - baseline.citation_rate
recommendation_delta   = remeasurement.recommendation_rate - baseline.recommendation_rate
query_coverage_delta   = remeasurement.query_coverage    - baseline.query_coverage
avg_recommendation_level_delta = remeasurement.avg - baseline.avg
competitor_delta       = remeasurement.competitor_count  - baseline.competitor_count
```

## Baseline v1（真实测量，2026-09-13 快照）

| 案例 | Query Count | Mention% | Citation% | Recommendation% | Query Coverage% | Avg Rec Level |
|------|-------------|----------|-----------|-----------------|-----------------|---------------|
| CASE-001 BookConv | 15 | 100.0 | 100.0 | 86.67 | 38.46 | 2.133 |
| CASE-002 OSTRICH | 46 | 100.0 | 0.0 | 23.91 | 153.33 | 1.37 |

说明：
- BookConv 的 15 条为**真实 Bing AI 已引用 query**；其余 27 条目标 query 未进入 AI 引用测量（Coverage 38.46%）。
- OSTRICH 的 citation=0% 因 GSC 导出不含 AI citation 字段；Recommendation 由传统搜索排名推导（代理信号）。
- OSTRICH query_coverage=153.33% 表示真实 GSC query 数(46) 多于本实验策划 query set(30)，非异常。

## 测量 Delta（Measured）—— PENDING

| 指标 | Baseline v1 | Re-measure v2 | Delta | 状态 |
|------|-------------|---------------|-------|------|
| Mention Delta | 100.0 | — | — | ⏳ 待重测 |
| Citation Delta | 100.0 | — | — | ⏳ 待重测 |
| Recommendation Delta | 86.67 | — | — | ⏳ 待重测 |
| Query Coverage Delta | 38.46 | — | — | ⏳ 待重测 |
| Competitor Delta | 0 | — | — | ⏳ 待重测 |

> **真实 Delta 由 `scripts/sprint4_remeasure.py` 在下次 Bing AI Performance 导出后填入 `cases/bookconv/delta/delta.json`。**
> 当前禁止手工编造。

## 预期 Delta（Projected，机制层面，非测量值）

以下为**干预机制预期**，用于规划，不等同于已测量效果：

- `bookconv-vs-calibre` 上线 → 预期 `bookconv vs calibre` / `alternatives` 由 NOT_COLLECTED 转为 MENTIONED，提升 **Query Coverage** 与部分 **Recommendation**。
- `bookconv-faq` 上线 → 预期 `is bookconv safe` / `bookconv review` 的 recommendation_level 由 1 升至 2-3，提升 **Recommendation Rate**。
- `why-bookconv` 上线 → 预期实体信号增强，支撑长期 **Avg Rec Level** 与 **Competitor** 多样性（被多源引用）。

## Competitor Delta 限制

两案例 baseline 的 competitor_count 均为 0：真实导出（Bing AI Performance / GSC）未携带竞品抽取字段。
Competitor Delta 需在下一次采集启用竞品抽取（OpenGeoAdapter 兼容层已预留 `competitors` 字段）后补测。

## 结论

可观测变化的**证据链已建立到 Intervention 层**（Observation → Evidence → Finding → Intervention 已完成且真实）。
**Outcome 层（Delta）** 处于 STAGED 状态，待内容收录与重测。这是 GEO 验证的时间属性，非系统缺陷。
