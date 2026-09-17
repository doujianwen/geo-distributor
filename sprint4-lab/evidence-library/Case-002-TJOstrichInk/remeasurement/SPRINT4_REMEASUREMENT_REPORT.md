# Sprint 4 Re-measurement Report (Phase E)

> 本文件为 7 个必交付物之一（SPRINT4_REMEASUREMENT_REPORT.md）。

## 重测协议

- **原则**: 与 Baseline 使用**完全一致 Query Set**（见 `cases/bookconv/baseline/query_set.json`，42 queries）。
- **引擎**: 同 Baseline 的真实测量源（Bing AI Performance 导出），经 OpenGeoAdapter 映射。
- **工具**: `scripts/sprint4_remeasure.py` — 输入新导出 JSON，自动计算 Delta 并落盘。
- **禁止**: 手工编造 Delta；缺测 query 显式标记 NOT_COLLECTED。

## 当前状态：STAGED（待重爬）

| 阶段 | 状态 | 说明 |
|------|------|------|
| 干预部署 | ✅ 代码已落地 | 3 篇文章已写入 bookconv.com 代码库，待 `next build` + Vercel 部署 |
| 搜索引擎收录 | ⏳ 待发生 | 新页面被 Bing/Google 收录通常 3-7 天 |
| Bing AI 重新引用 | ⏳ 待发生 | AI 引擎重新抓取并引用新内容通常 7-14 天 |
| 真实重测 | ⏳ 待执行 | 下一次 Bing AI Performance 导出后运行 `sprint4_remeasure.py` |

## 为何不能现在给出真实 Delta

GEO 的可观测变化依赖**内容被 AI 引擎重新收录并引用**，这是搜索引擎/AI 爬虫的时间函数，
无法在部署当天测量。伪造当日 Delta 违反「数据不可用即报 unknown，绝不伪造」铁律。

## 重测执行命令（数据到位后）

```bash
.venv/Scripts/python.exe scripts/sprint4_remeasure.py <新 bing 导出 json>
```

该命令将：
1. 读取 `cases/bookconv/baseline/metrics.json`（v1 基线）
2. 映射新导出 → OpenGeoAdapter → 同 Query Set 重采
3. `DeltaCalculator.compute(baseline, remeasurement)` → `cases/bookconv/delta/delta.json`
4. 更新本重测报告与 DELTA_ANALYSIS

## 预期被影响的 Query（机制层面，非测量值）

- `/blog/bookconv-vs-calibre` → 应提升 `bookconv vs calibre` / `bookconv alternatives` 的 mention/citation
- `/blog/bookconv-faq` → 应提升 `is bookconv safe` / `bookconv review` 的 recommendation_level
- `/blog/why-bookconv` → 应强化实体信号，支撑长期 recommendation_rate
