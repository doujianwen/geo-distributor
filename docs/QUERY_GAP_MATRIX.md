# Query Gap Matrix — BookConv (Validation Window Phase 2)

> 本文件为 Validation Window 必交付物之一（QUERY_GAP_MATRIX.md）。
> 范围：BookConv 固定 Query Set（39 queries，冻结于 `cases/bookconv/baseline/query_set.json`）。
> 数据：真实 Bing AI Performance 导出 `bing_analysis_2026-09-13.json`（Day 0 / 2026-09-13）。

## 覆盖率口径说明（诚实，不夸大）

| 口径 | 公式 | 值 | 说明 |
|------|------|-----|------|
| **严格覆盖率** (本矩阵采用) | 39 个策划 query 中，Bing 导出**精确命中**的数量 / 39 | **23.08%** (9/39) | 仅统计我们策划的 query 是否被真实引用 |
| 宽松覆盖率 (Sprint 4 旧报告) | Bing 返回的全部 observation / 39 | 38.46% (15/39) | 15 条含 6 条 Bing 自身变体（不在策划集内），虚高 |

> **结论**：真实覆盖率以**严格 23.08%** 为准。Sprint 4 旧报告的 38.46% 因计入 Bing 自有变体而偏高，此处显式校正，避免夸大。

## 状态分布（Day 0）

| 状态 | 数量 | 定义 |
|------|------|------|
| COVERED | 7 | Bing 引用且 recommendation_level ≥ 2（中/强推荐信号） |
| WEAK | 2 | Bing 引用但 recommendation_level = 1（被引用、低 share，未达推荐） |
| MISSING | 30 | 策划 query 未出现在 Bing 导出（未测量到 AI 可见性） |
| COMPETITOR-DOMINATED | 0（已测量） | 真实导出 `competitors=[]`，无竞品抽取数据 |
| COMPETITOR-DOMINATED（高风险告警） | 6（Comparison 类） | 对比类 query 未测量但 Calibre 主导风险高（推断，非实测） |

- **Coverage % = 23.08%**（严格）
- 全部 8 个 Brand query 均为 MISSING（品牌词在 Bing AI 导出中未产生 citation —— 用户直接导航，AI 答案场景弱）
- 全部 6 个 Comparison query 均为 MISSING（高商业意图 + 竞品主导风险）

## 全量 Query 矩阵（39 queries）

| # | Query | Category | Status | Rec Level | Share (Bing) | Competitor Risk |
|---|-------|----------|--------|-----------|--------------|-----------------|
| 1 | bookconv | Brand | MISSING | — | — | LOW |
| 2 | bookconv ebook converter | Brand | MISSING | — | — | LOW |
| 3 | bookconv review | Brand | MISSING | — | — | LOW |
| 4 | bookconv alternative | Brand | MISSING | — | — | LOW |
| 5 | is bookconv safe | Brand | MISSING | — | — | LOW |
| 6 | bookconv free | Brand | MISSING | — | — | LOW |
| 7 | bookconv vs calibre | Brand/Comparison | MISSING | — | — | **HIGH** |
| 8 | bookconv login | Brand | MISSING | — | — | LOW |
| 9 | convert epub to pdf | Problem | MISSING | — | — | LOW |
| 10 | convert mobi to epub | Problem | COVERED | 2 | 10.31% | LOW |
| 11 | epub to kindle | Problem | MISSING | — | — | LOW |
| 12 | azw3 to epub | Problem | MISSING | — | — | LOW |
| 13 | convert pdf to epub | Problem | MISSING | — | — | LOW |
| 14 | djvu to pdf | Problem | WEAK | 1 | 3.97% | LOW |
| 15 | best ebook converter | Problem | MISSING | — | — | LOW |
| 16 | free ebook converter | Problem | MISSING | — | — | LOW |
| 17 | ebook conversion software | Problem | MISSING | — | — | LOW |
| 18 | convert ebook to pdf | Problem | MISSING | — | — | LOW |
| 19 | mobi to epub converter free | Problem | MISSING | — | — | LOW |
| 20 | convert epub to azw3 | Problem | COVERED | 2 | 28.30% | LOW |
| 21 | kindle to pdf | Problem | MISSING | — | — | LOW |
| 22 | epub to mobi converter free | Problem | WEAK | 1 | 9.77% | LOW |
| 23 | ai ebook tools | Category | MISSING | — | — | LOW |
| 24 | ebook converter software | Category | MISSING | — | — | LOW |
| 25 | ebook format converter | Category | MISSING | — | — | LOW |
| 26 | online ebook converter | Category | MISSING | — | — | LOW |
| 27 | ebook reader app | Category | COVERED | 2 | 12.59% | LOW |
| 28 | ebook syncing services | Category | MISSING | — | — | LOW |
| 29 | what format does kindle use | Category | COVERED | 2 | 39.13% | LOW |
| 30 | kindle formats explained | Category | MISSING | — | — | LOW |
| 31 | transfer ebooks between devices | Category | COVERED | 3 | 46.54% | LOW |
| 32 | best free epub reader | Category | COVERED | 2 | 14.80% | LOW |
| 33 | Harry Potter digital books multiple devices | Category | COVERED | 3 | 50.00% | LOW |
| 34 | bookconv alternatives | Comparison | MISSING | — | — | **HIGH** |
| 35 | calibre alternative | Comparison | MISSING | — | — | **HIGH** |
| 36 | best calibre alternative | Comparison | MISSING | — | — | **HIGH** |
| 37 | convert epub to azw3 vs mobi | Comparison | MISSING | — | — | **HIGH** |
| 38 | bookconv vs zamzar | Comparison | MISSING | — | — | **HIGH** |
| 39 | online converter vs desktop | Comparison | MISSING | — | — | **HIGH** |

> Rec Level：1=引用但低 share(<10%)；2=中等推荐；3=强推荐(share≥40%)。
> Competitor Risk：仅 Comparison 类标记 HIGH（Calibre 在 AI 答案中主导的推断风险，非实测竞品数）。

## Top 20 Query Gaps（按商业/转化意图优先级）

| 排名 | Query | Category | 缺口原因 | 优先级 |
|------|-------|----------|----------|--------|
| 1 | bookconv vs calibre | Comparison | Calibre 主导风险；INT-BC-003 已部署待收录 | 🔴 P0 |
| 2 | bookconv alternatives | Comparison | 同上对比盲区 | 🔴 P0 |
| 3 | calibre alternative | Comparison | 竞品对比词空白 | 🔴 P0 |
| 4 | best calibre alternative | Comparison | 竞品对比词空白 | 🔴 P0 |
| 5 | convert epub to pdf | Problem | 最高频交易意图，当前零 AI 可见性 | 🔴 P0 |
| 6 | epub to kindle | Problem | 高意图转换词缺失 | 🟠 P1 |
| 7 | azw3 to epub | Problem | 高意图转换词缺失 | 🟠 P1 |
| 8 | convert pdf to epub | Problem | 高意图转换词缺失 | 🟠 P1 |
| 9 | best ebook converter | Problem | 品类头部词缺失 | 🟠 P1 |
| 10 | free ebook converter | Problem | 免费意图词缺失 | 🟠 P1 |
| 11 | ebook conversion software | Problem | 软件类意图缺失 | 🟠 P1 |
| 12 | convert ebook to pdf | Problem | 交易意图缺失 | 🟠 P1 |
| 13 | kindle to pdf | Problem | 设备转换意图缺失 | 🟠 P1 |
| 14 | mobi to epub converter free | Problem | Bing 仅观测到 "mobi to epub" 变体，精确词缺失 | 🟠 P1 |
| 15 | bookconv review | Brand | 高意图品牌词未产生 citation | 🟠 P1 |
| 16 | is bookconv safe | Brand | 信任意图；INT-BC-002 已部署待收录 | 🟠 P1 |
| 17 | bookconv alternative | Brand | 品牌对比意图缺失 | 🟡 P2 |
| 18 | bookconv free | Brand | 免费意图缺失 | 🟡 P2 |
| 19 | ai ebook tools | Category | AI 发现意图（与产品定位强相关）缺失 | 🟡 P2 |
| 20 | online ebook converter | Category | 在线工具意图缺失 | 🟡 P2 |

## 与干预的映射

- Top 1–4（Comparison）→ **INT-BC-003** `bookconv-vs-calibre`（已部署，待收录后重测应转 COVERED）
- Top 16（is bookconv safe）→ **INT-BC-002** `bookconv-faq`（已部署，待收录后应提升 Rec Level 1→2/3）
- Top 5–14（Problem）→ 部分由上述两篇 + 后续品类页覆盖（INT-BC-001 留待 Pilot）
- Brand 词 Zero-citation 为结构性现象（品牌词用户直接导航），非内容缺口，需单独评估

---
*Generated by validation_window.py + manual ranking — 2026-09-14*
