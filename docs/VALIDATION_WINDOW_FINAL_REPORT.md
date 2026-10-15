# Validation Window Final Report — BookConv GEO Evidence Loop V1.0

> 本文件为 Validation Window 最终交付物（VALIDATION_WINDOW_FINAL_REPORT.md）。
> 上游：MVP V0.1 = PASS；Sprint 4 Lab = PARTIAL PASS（无真实 Delta）。
> 本阶段唯一目标：验证 **Diagnosis → Intervention → Delta** 是否成立。

## 1. Scope Freeze 遵守声明

✅ 本阶段**未新增任何产品功能**。仅产出验证基础设施与文档：
- `scripts/validation_window.py`（重测引擎，验证工具，非产品功能）
- 7 个交付文档 + intervention-ledger + case library 重结构
- 禁止清单全部未触碰：CRM / Billing / Commission / Portal / FastAPI / PostgreSQL / OpenGeo 新功能 / 新 Adapter / UI / Workflow Engine —— **均未开发**。

## 2. 已验证（真实，非伪造）

| 项目 | 状态 | 证据 |
|------|------|------|
| Baseline 测量（两站真实） | ✅ | BookConv 真实 Bing AI Performance；TJOstrichInk 真实 GSC |
| Query Set 冻结（39 queries） | ✅ | `cases/bookconv/baseline/query_set.json` |
| Diagnosis 可追溯 Findings | ✅ | 10 条 Finding 均 Observation→Evidence→Finding（Sprint 4 产出） |
| Intervention 真实执行（BookConv） | ✅ | 3 篇真实文章写入 bookconv 代码库并注册，tsc 通过；9-28 已确认在 origin/main（精确部署/收录时点不可考，shallow clone） |
| Intervention Ledger | ✅ | `INTERVENTION_LEDGER.md`（3 条独立记录） |
| Query Gap Matrix | ✅ | `QUERY_GAP_MATRIX.md`（9 Covered / 2 Weak / 30 Missing，严格 23.08%） |
| Day 0 时间线入库 | ✅ | `BOOKCONV_TIMELINE.md` + `cases/bookconv/timeline/timeline.json` |
| **Day 7 重测入库（真实）** | ✅ | 9-20 真实导出 → `bing_analysis_2026-09-20_day7.json` → 9/39 strict 覆盖 |
| **Day 14 重测入库（真实）** | ✅ | 9-27 真实导出 → `bing_analysis_2026-09-27_day14.json` → 10/39（convert epub to pdf 新增 WEAK） |
| **Day 30 重测入库（真实，闭合日终值）** | ✅ | **10-14 闭合日导出** → `bing_analysis_2026-10-14_day30close.json`（10-08 版保留为中间观测） |
| **四期 Delta 计算入库** | ✅ | `cases/bookconv/delta/delta.json`（Day30 vs Day0，由引擎机械计算） |
| 对照组基线 + 协议 | ✅ | `CONTROL_GROUP_REPORT.md`（TJOstrichInk，禁干预）；Day7/14/30 重导 ⛔ 未执行（无新导出） |
| 归因框架 + 数据填充 | ✅ | `DELTA_ATTRIBUTION.md`（A–E 已按真实数据归因 = E） |
| L3 审计 | ✅ | `L3_VALIDATION_AUDIT.md`（Day 30 终审：UNKNOWN，基于真实数据） |

## 3. 诚实留白（STAGED / BLOCKED，禁止编造）

| 项目 | 状态 | 原因 |
|------|------|------|
| 对照组 GSC Day 30 重导 | ✅ 已闭合（2026-10-14，二次修正） | 用户人工导出全 7 件族；同管线复测 + 窗口对齐日序列：**对照自身显著正向漂移（加权排名 9.86→5.16）**——初版「平稳」判读作废，B/D 在传统维度不可排除；Day7/14 快照缺失，仅可回溯 |
| 对照组 AI 引擎测量 | ⛔ BLOCKED | 5-query 采集集已定义（`manual_baseline_tjostrichink.json`），`is_real_capture: null`，从未真实采集 |
| 干预部署精确时点 | ⚠️ UNKNOWN | 本地 shallow clone；0c58c66（9-28）已确认在 origin/main，首次 push/部署时间不可考 |
| 窗口闭合日（10-14）当日导出 | ✅ **全闭合** | 传统维度 4 件 + **AI 维度 3 件**（AISearchQueriesReport 214 行 / AIPerformanceOverviewStats / AIPageStatsReport）均由用户人工导出并归档 `bookconv_data_asset/bing/`；AI 重测引擎已用闭合日导出重跑（幂等覆盖 Day30）。诚实标注：AI 导出内日序列数据止于 10-11（Bing 报表 3 天滞后），10-12/13/14 无数据 |
| Day0 vs Day7-30 聚合口径可比性 | ⚠️ 有限 | Day0 基于 top-15 行（含 6 条非冻结集 query），聚合 Delta 含机械口径偏差；真实信号以固定 9-query 面板为准 |

## 4. 最终回答规格核心问题

> **「Diagnosis 能否产生可观测变化？」/「L2 → L3 是否成立？」**

**🔴 截至 Day 30 窗口闭合：UNKNOWN（未证明）——但这是数据支撑下的终审 UNKNOWN，非时间性挂起。**

- 已证明：验证闭环首次在真实数据上完整走通四期（Baseline→Diagnosis→Intervention→Re-measurement Day 0/7/14/30）。
- 未证明：干预目标 query（品牌/对比类 4 条）全窗口零出现，预期 Outcome（MISSING→COVERED）未观测到；面板正向变化全部位于非目标 query 且归因 = E（对照组缺失 + 部署时点不可考 + 并发内容操作未隔离）。

## 5. Final Success Criteria 对账（Day 30 终审）

| 标准 | 满足？ |
|------|--------|
| BookConv 至少完成一次完整 Baseline→Diagnosis→Intervention→Re-measurement | ✅ **完成**（四期真实数据 2026-09-13 / 09-20 / 09-27 / **10-14 闭合日**全部入库，Day30 以闭合日导出为终值） |
| 形成 Observation→Evidence→Finding→Intervention→Outcome 完整链路 | ✅ **链路闭合**（Outcome = 真实测量结果：目标 query 零出现 + 非目标面板变化，已如实记录于 DELTA_ATTRIBUTION） |
| 干预产生预期可观测变化（MISSING→COVERED） | 🔴 **未观测到**（目标 query 在 Day7/14/30 闭合版四期导出中零出现，含闭合日 10-14 共 214 行） |
| 对照组反事实 | ⚠️ 部分闭合 | GSC 传统维度 ✅（Day30 平稳，+2.62pp）；AI 维度 ⛔ 仍缺（5-query 集未采集）→ B/C/D 在 AI 维度无法排除 |
| 最终回答 L2→L3 是否成立 | 🔴 **UNKNOWN**（未证明；管道✅ 干预✅ 重测✅ / 目标 Outcome🔴 / 归因 E） |

**结论：Validation Window 结构性闭合 ✅（首次完整四期真实重测 + Delta 归因 + 终审裁定全部落盘），
但 L2→L3 因果命题维持 UNKNOWN。对冻结 3 篇干预文章的诚实定向结论 = 「预期影响未观测到（NOT OBSERVED）」，
因部署时点不可考 + 收录窗口边缘 + 并发干预未隔离 + 对照组缺失，不得终审为「干预无效（NO）」。**

## 6. 用户侧后续动作（若需重开窗口）

1. ~~人工登录 Bing Webmaster 导出 10-14 闭合日快照~~ ✅ 已完成（AI 3 件 + 传统 4 件，2026-10-14）
2. ~~人工登录 GSC 为 TJOstrichInk 重导同维度数据~~ ✅ 已完成（2026-10-14，归档至 `ostrich-ink/gsc-data-2026-10-14/`）
3. 按 `manual_baseline_tjostrichink.json` 的 5-query 集真实执行一次 AI 引擎采集（对照组 AI 维度）
4. 确认 3 篇干预文章的生产部署/收录时点（Vercel 部署日志 + GSC/Bing WM 收录记录）
5. 将窗口期全部并发内容操作补登记进 Intervention Ledger（消除归因混杂）
6. 满足上述后重跑：`.venv/Scripts/python.exe scripts/validation_window.py <新导出> <Day标签> <日期>`

## 7. 交付物清单

| 文件 | 路径 |
|------|------|
| Query Gap Matrix | `docs/QUERY_GAP_MATRIX.md` |
| Intervention Ledger | `docs/INTERVENTION_LEDGER.md` + `evidence-library/intervention-ledger/` |
| BookConv Timeline | `docs/BOOKCONV_TIMELINE.md` + `cases/bookconv/timeline/`（四期） |
| Control Group | `docs/CONTROL_GROUP_REPORT.md` |
| Delta Attribution | `docs/DELTA_ATTRIBUTION.md`（已填真实数据，归因 = E） |
| L3 Audit | `docs/L3_VALIDATION_AUDIT.md`（Day 30 终审 UNKNOWN） |
| Final Report | `docs/VALIDATION_WINDOW_FINAL_REPORT.md`（本文件） |
| 重测引擎 | `scripts/validation_window.py` |
| 真实重测输入 | `bookconv_data_asset/bing/bing_analysis_2026-09-20_day7.json` / `...09-27_day14.json` / `...10-08_day30.json`（中间观测）/ `...10-14_day30close.json`（**闭合日终值**）（由真实导出机械转换） |
| Case Library | `evidence-library/Case-001-BookConv/` + `Case-002-TJOstrichInk/`（含 timeline/delta/outcome） |

---
*Generated by Validation Window V1.0 — 2026-09-14 (framework) · 2026-10-14 (Day 30 窗口闭合终审)*
