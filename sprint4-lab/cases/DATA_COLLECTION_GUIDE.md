# Day 7 / Day 14 重测数据采集指南（Replay 模式，零凭据）

本指南说明如何拿到 **Milestone 1 Outcome** 所需的真实重测数据，使 Sprint 4B 的
"Before → After → Delta" 从 UNKNOWN 推进到可验证。

> 模式：🟡 Replay（手动重新导出与基线**同源**的数据），**不是** Live API。
> 为什么不用 Live API：ChatGPT/Perplexity 实时调用接口已预留，但凭据受限未激活
> （见 `docs/SPRINT-4-ROADMAP.md` 二轮审计结论）。Replay 同样能产出真实的
> Before/After 对比，且零凭据、可一键复现。

---

## 一、BookConv（CASE-001，Bing AI Performance 来源）

1. 登录 Bing Webmaster Tools → 站点 `bookconv.com`
2. 进入 **AI Performance Overview**（或 AISearchQueries / AIPageStats）
3. 按与基线相同的 39 个 query（见 `bookconv/baseline/query_set.json`）逐项记录：
   - 该 query 下 BookConv 是否被提及（brand_mentioned）
   - 是否被引用（citations）
   - recommendation_level（0=未推荐 / 1=提及 / 2=推荐 / 3=强推荐）
   - first_mention_position、competitors
4. 导出的原始数据用既有映射 `map_bing_ai_performance_row` 转为 observations schema，
   **或**直接按 `observations.DAY7.json` 模板逐条填真实值。
5. 运行：
   ```bash
   python scripts/sprint4_remeasure.py run --case bookconv \
       --input sprint4-lab/cases/bookconv/remeasurement/observations.DAY7.json
   ```

## 二、TJOstrichInk（CASE-002，GSC 来源）

1. 登录 Google Search Console → 站点 `tjostrichink.com`
2. 进入 **Performance → Queries**，按 `tjostrichink/baseline/query_set.json`（30 queries）记录：
   - 该 query 下 TJOstrichInk 是否被 AI 概览/富媒体提及
   - 是否出现在 AI Mode / 第三方 AI 答案中（需人工核对或导出 GSC + 手动标记）
3. 将结果填入 `observations.DAY7.json` 模板（observations schema）。
4. 运行：
   ```bash
   python scripts/sprint4_remeasure.py run --case tjostrichink \
       --input sprint4-lab/cases/tjostrichink/remeasurement/observations.DAY7.json
   ```

## 三、产物

每次 `run` 会在案例目录下产出：
- `remeasurement/metrics.json` —— 重测聚合指标（被 `EvidenceLibraryService.load_from_lab_cases()` 自动入库）
- `remeasurement/DELTA_REPORT.md` —— client-safe 的 Delta 报告（顶部标注 Replay 模式）
- `delta/delta.json` —— 原始 delta 数值

## 四、护栏（防伪造）

- 模板未填（全部 placeholder / not_collected）→ 脚本**拒绝**计算 delta，报错退出。
- 报告顶部强制标注 `DATA MODE: Replay`，不会与 Live API 混淆。
- 本 Delta 属 **Product Validation**（系统是否显示效果），**≠ Commercial Validation**（客户是否付费）。

## 五、何时做

- BookConv：3 篇文章已发布（约 2026-09-13 基线）。Day 7 ≈ 2026-09-20，Day 14 ≈ 2026-09-27。
- TJOstrichInk：基线同为 2026-09-14。Day 7/14 同理。
- 真实 Delta 依赖内容被搜索引擎/AI 重新收录，通常 7–14 天延迟，故 Day 7 可能信号弱，
  Day 14 更具参考性。
