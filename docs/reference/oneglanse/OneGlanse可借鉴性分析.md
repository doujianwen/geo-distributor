# OneGlanse 可借鉴性分析与二次开发路径

> 分析时间：2026-09-13
> 分析对象：`E:\GEO项目\技术层\GEO海外分销系统\oneglanse`
> 对照系统：`E:\一人公司\独立站\geoflow\geo-intent-system`（用户意图挖掘系统）
> 分析方式：源码级实证（读取实际实现，非文档推断）

---

## 〇、结论先行

**四条核心判断：**

1. **"意图挖掘系统更实用"这个感觉是对的，但结论要修正** —— 意图系统更实用的原因是**它有业务出口**（挖意图 → 生成内容 → 发布 bookconv），而 OneGlanse 只是个仪表盘，量完就结束。这是**产品层缺失**，不是技术层缺失。
2. **但在技术层，OneGlanse 领先一个身位** —— 它用真实浏览器登录态抓取 5 个 AI 平台的原生回答 + 引用源；意图系统的"AI 可见度"模块目前**产出的很可能是假数据**（详见第一节铁证）。
3. **两者不是竞品，是上下游** —— 意图系统负责"找问题"，OneGlanse 负责"验证答案"。合并后才是 GEO 的完整闭环。
4. **二次开发的最优路径是"拆件"而非"整体二开"** —— OneGlanse 的可复用资产只有 2 块（Provider 抓取层 + 分析提示词），其余多租户 SaaS 脚手架对一人公司是纯负担。

---

## 一、必须先处理的问题：意图挖掘系统的 AI 可见度数据不可信

**这是本文最高优先级的发现。** 在讨论"借鉴 OneGlanse"之前，需要先知道意图系统当前的可见度数据是怎么来的。

### 1.1 铁证：主路径存在必崩的代码错误

`app/ai_query/openai_search.py` 第 153-160 行：

```python
opener = self._create_opener()
req = opener.open(
    json.dumps(payload).encode("utf-8"),   # ← 位置参数应为 fullurl，这里传的是请求体
    headers=headers,                        # ← urllib 的 open() 不接受 headers 关键字
    method="POST",                          # ← 也不接受 method 关键字
)
data = json.loads(resp.read().decode("utf-8"))   # ← resp 从未定义，NameError
```

`urllib.request.OpenerDirector.open()` 的签名是 `open(fullurl, data=None, timeout=...)`，**不接受 `headers` 与 `method` 参数**。这段代码必然抛 `TypeError`，随后被 `except Exception` 捕获并返回 `result="error"`。

第 160 行的 `resp` 甚至没有定义（`NameError`），说明**这条路径从未成功执行过一次**。

**后果**：`query()` 方法（第 117-131 行）的逻辑是"主路径返回 error 就降级"，所以每次调用都会跳过真实搜索，直接落到降级路径。

### 1.2 降级路径：让 LLM 凭空猜答案

`_query_with_fallback()` 使用的提示词（`SEARCH_ANALYSIS_PROMPT`，第 26-55 行）：

```
请基于你的知识，判断 AI 搜索引擎对以上查询的回答会如何表现：
1. 是否会在回答中引用 {brand_name} 的具体内容？
...
注意：
- {brand_name} 是新站，大多数查询可能返回 not_found
- 请基于合理的 SEO/GEO 知识判断，不要编造不存在的引用
- 如果认为不太可能引用，直接返回 not_found
```

这**不是测量，是让模型编造测量结果**。提示词甚至预先引导模型"大多数查询可能返回 not_found"——这会系统性压低引用率，把模型的先验偏见写成数据库里的"事实"。

### 1.3 兜底路径：纯关键词启发式

`_query_mock()`（第 229-251 行）：

```python
cited = any(k in t for k in ["best", "review", "comparison", "vs", "alternative"])
```

**只要查询语句里含 "best"，就直接判定为 `cited`。** 这是确定性伪造。

### 1.4 与既有硬规则冲突

此实现直接违反本项目已确立的硬规则：

> **数据不可用即报 unknown，绝不伪造** —— 假数据比没数据更危险。

`citations` 表中那些 `cited` / `brand_only` / `not_found` 结果，来源是"LLM 猜测"或"关键词命中"，而非真实 AI 问答。基于这些数据做的任何判断（包括"Bing AI 引用 147 次但 Google 自然流量为 0"类分析如果引用了该表）都需要重新校准。

**处置建议**：立即在 `citations` 表增加 `source` 字段标记数据来源（`real` / `llm_guess` / `mock`），把历史数据标为不可信，后续所有关于 AI 可见度的结论显式声明数据来源。

---

## 二、两套系统的真实定位

| 维度 | geo-intent-system | OneGlanse |
|------|-------------------|-----------|
| **所在层** | 输入层（Demand Discovery） | 输出层（Citation Measurement） |
| **核心动作** | 挖掘意图 → 聚类 → Brief → 发布 | 抓 AI 回答 → 抽引用源 → 打分 |
| **覆盖引擎** | 名义 1 个（实际走 Mock） | 5 个：ChatGPT / Perplexity / Gemini / Claude / Google AI Overview |
| **数据真实性** | 推测值 + 关键词启发式 | 真实浏览器抓取 |
| **业务出口** | 有（内容生产闭环，已发布到 bookconv） | 无（止于 Dashboard） |
| **技术栈** | Python + SQLite，单机可跑 | pnpm monorepo + Next.js 15 + Postgres + ClickHouse + Redis + Docker |
| **资源占用** | 低 | 高（本地实测 16GB 内存机器跑不动 Next dev） |
| **可交付给客户** | 需包装 | 需包装 |

**判断**：用户"感觉意图系统更实用"是准确的体验，但归因需要修正——不是意图系统技术更好，而是**它的链路完整、有产出**。OneGlanse 是半成品产品 + 高质量引擎。

---

## 三、OneGlanse 值得借鉴的三块资产

### 3.1 Provider 抓取层（最有技术壁垒，最难自研）

**位置**：`apps/agent/src/core/providers/`

```
providers/
├── types.ts                    ← ProviderConfig 接口，声明式注册，新增平台零侵入
├── chatgpt/  ├── index.ts
│             └── lib/{dismissAuthModal,extractSources,pageLifecycle}.ts
├── perplexity/ ├── index.ts
│               └── lib/{extractSources,navigation}.ts
├── gemini/    ├── index.ts
│              └── lib/{extractSources,pageLifecycle,session}.ts
├── claude/    ├── index.ts
│              └── lib/{extractSources,pageLifecycle}.ts
├── ai-overview/ ├── index.ts
│                └── lib/{expand,extractSources,pageLifecycle,session}.ts
└── _shared/{google.ts, rawSourcesDom.ts, resetProviderPage.ts, sourceUtils.ts}
```

**为什么值钱**：

1. **真实的引用源抽取**。以 Perplexity 为例（`perplexity/lib/extractSources.ts`），它注入到页面的 DOM 提取器精确定位 `[role="tabpanel"][aria-labelledby*="citations"]`，遍历 `a[href^="http"]`，用"文本长度排序取最长者为 `citedText`、次长为 `title`"的启发式把引用条目的**标题 + 被引用原文**一起取回。这比只拿 URL 有价值得多——`citedText` 是判断"AI 引用了你哪句话"的唯一依据。
2. **反检测与鲁棒性**。用 Camoufox（Firefox 反指纹分支）而非普通 Chromium；`humanBehavior.js` 做类人按键；提交策略有 `["native","enter","force","dispatch"]` 四级降级；每个阶段都有 hook（`beforeSubmitHook` / `afterSubmitHook` / `betweenPromptsHook` / `beforeRetryHook`）。这些细节是踩坑踩出来的。
3. **声明式扩展**。`ProviderConfig` 接口把所有平台差异收敛到一个对象里，新增平台只需写一个 config 文件并在 `index.ts` 注册——**其他文件不用改**。

**这是意图系统最缺的一块**：`openai_search.py` 只有一个名义上的 OpenAI 适配器，且已证实走不通。

### 3.2 分析提示词（复用价值最高，零耦合）

**位置**：`packages/services/dist/analysis/analysisPrompt.js`（438 行）

这是整个项目里**最可复制的资产**，因为它与代码零耦合，纯文本，可直接搬进任何 LLM 调用。

它解决的问题是：**如何让 LLM 稳定地、不吹牛地给一个品牌在 AI 回答中的表现打分**。核心机制：

| 机制 | 做法 | 价值 |
|------|------|------|
| 反幻觉策略 | "ZERO HALLUCINATION POLICY" + "QUOTE-OR-DEFAULT"：每个分数必须能指回原文的具体词句，否则取保守值 | 抑制 LLM 编造依据 |
| 反通胀指令 | "ANTI-INFLATION MANDATE"：明确指出 LLM 系统性高分倾向，"pretty good" 不给 80+ | 解决 LLM 打分普遍虚高 |
| 响应质量门 | 先分类为 REFUSAL / ECHO-ONLY / SUBSTANTIVE 三种，只对第三种做完整分析 | 避免把"重复问题"当成提及 |
| 绝对排名算法 | 区分 local rank（子分类内序号）与 absolute rank（全文阅读序），并给出多分类场景的算例表 | 解决 LLM 回答的分类嵌套结构 |
| 五维可见度 | Coverage 25% + Placement 25% + Structural Prominence 20% + Frequency 15% + Contextual Framing 15% | 可解释、可加权的综合分 |
| 情绪校准决策树 | 明确区间映射：81+ 必须出现明确最高级措辞；列了优缺点则上限 79；仅提及无评价 = 50 | 把主观判断变成规则 |
| 假设性提及封顶 | 品牌只出现在 LLM 的反问句里 → visibility ≤ 15，sentiment = 50 | 处理最容易被误判的场景 |
| 竞品去重 | 附属产品合并到母公司（Zoho CRM + Bigin → Zoho），rankPosition 取最早出现 | 避免竞品列表碎片化 |
| 交叉验证清单 | 输出前强制自检 12 条一致性规则 | 结构化输出质量兜底 |

**输出结构**（可直接对应数据库字段）：

```json
{
  "geoScore": { "overall": 0-100 },
  "presence": { "mentioned": bool, "visibility": 0-100 },
  "position": { "rankPosition": int|null },
  "sentiment": { "score": 0-100 },
  "recommendation": { "type": "top_pick|strong_alternative|conditional|mentioned_only|discouraged|not_mentioned" },
  "competitors": [{ "name", "domain", "visibility", "sentiment", "rankPosition", "isRecommended" }],
  "perception": { "coreClaims": [], "differentiators": [], "bestKnownFor", "pricingPerception" },
  "risks": { "items": [{ "severity" }] }
}
```

**这份提示词可以直接用来替换意图系统里那个"让 LLM 猜"的 `SEARCH_ANALYSIS_PROMPT`** —— 而且替换后不是从"假数据"变成"更好的假数据"，因为它的输入是 OneGlanse 抓回来的**真实回答文本**，提示词只负责在真实证据上做结构化提取。

### 3.3 数据模型（时序 + 多维）

**位置**：`packages/db/clickhouse-init/schema.sql`

```sql
analytics.prompt_responses (
    workspace_id, prompt_id, model_provider, response,
    sources Array(Tuple(title, cited_text, url, domain, favicon)),
    prompt_run_at, is_analysed
)
ORDER BY (workspace_id, prompt_run_at, model_provider, prompt_id)
```

**值得借鉴的设计**：`(prompt × provider × 时间)` 的三维主键，天然支持两类最重要的查询：
- **横切对比**：同一个问题，5 个平台谁提到了我、排第几
- **时间趋势**：同一个问题，我的引用排名在内容发布后有没有变化

第 2 点是关键——它让"发布内容 → AI 引用改善"这件事变成**可测量**的，而这正是意图系统当前断裂的一环。

---

## 四、不值得借鉴的部分（对一人公司是负担）

| 组件 | OneGlanse 的做法 | 为什么不建议搬 |
|------|------------------|----------------|
| 租户模型 | Better Auth + `organization` + `member` + `invitation` + `workspaces` + `workspace_members` 四层 | 一人公司/单客户场景纯属过度设计 |
| 存储三件套 | Postgres + ClickHouse + Redis 同时跑 | 本地实测内存不够；数据量级远未到需要 ClickHouse 的程度 |
| 队列 | BullMQ + Redis 做任务调度 | 串行跑 20 个 prompt 用 `for` 循环 + sleep 就够 |
| 全栈框架 | Next.js 15 + React 19 + tRPC + Drizzle | 只为看一个 Dashboard 不值得维护这套 |
| 部署 | Docker Compose 三容器 + VPS 脚本 | 运维成本远超收益，除非要卖 SaaS |

**一句话**：OneGlanse 是按"多租户 SaaS 产品"设计的，你要的是"内部 GEO 引擎"。两者的复杂度需求差一个数量级。

---

## 五、二次开发的两条路径

### 路径 A：拆件集成 —— 把 OneGlanse 当"引擎库"，不当"产品"（推荐）

**核心思路**：只抽出 Provider 抓取层 + 分析提示词，做成一个轻量本地服务，接进意图挖掘系统的 `citations` 表，替换掉现在的假数据源。

**目标架构**：

```
意图挖掘系统 (Python/SQLite)
  │
  ├─ 产出待验证 query 列表  ← 已有能力
  │
  └─→ 调用 citation-engine（新，从 OneGlanse 抽取）
        ├─ Provider 层：Camoufox 抓 ChatGPT/Perplexity/Gemini/Claude/AIO
        └─ 分析层：analysisPrompt 打分
              │
              └─→ 回写 citations 表
                    result / cited_url / position / sentiment
                    + geoScore / visibility / rankPosition
                    + source='real'  ← 关键：标记数据来源
```

**实施步骤（按依赖顺序）**：

| # | 动作 | 说明 | 难度 |
|---|------|------|------|
| 1 | 在 `citations` 表加 `source` 字段 | 标记 `real`/`llm_guess`/`mock`，历史数据标为不可信 | 低 |
| 2 | 抽出 `analysisPrompt` 为独立模块 | 改成"输入真实回答文本 → 输出结构化 JSON"，**先只接真实数据** | 低 |
| 3 | 验证 Camoufox 在 Windows 可跑 | 直接用 oneglanse 的 node_modules 跑通一个 Perplexity 抓取 | 中 |
| 4 | 抽取 Provider 层为独立包 | 只保留 `providers/` + `_shared/` + `humanBehavior`，剥离 auth/queue/workspace 依赖 | 中高 |
| 5 | 接进意图系统 | Python 通过 subprocess/HTTP 调用，回写 citations | 中 |
| 6 | 加"发布前后对比" | 用 `prompt_run_at` 做时序对比，验证内容是否带来引用提升 | 低 |

**权衡**：

- 收益：直接补上"C 端内容发了，但不知道 AI 有没有引用"的闭环缺口；数据从伪造变真实
- 成本：中等，主要卡在第 3、4 步（Camoufox 跨平台 + 剥离依赖）
- 风险：**低** —— 不碰多租户、不碰部署，失败了也不影响现有系统
- 置信度：**高** —— 抓取层已在 OneGlanse 里跑通（本地实测能启动、能 bind 端口、返回过 200）

### 路径 B：整体二开成 SaaS 分销系统（`二次开发审计方案.md` 的方向）

**核心思路**：在 OneGlanse 上叠加 Partner 分销表（`partners` / `partner_customers` / `partner_settlements` / `invoices`），改造成可对外销售的渠道产品。

**权衡（透明化）**：

| 项 | 评估 |
|----|------|
| 前置条件 | 需要先有付费客户。当前无客户验证，先做产品是典型的顺序错误 |
| 工程量 | 多租户改造 + 支付结算 + 佣金分账 + 白标 + 部署运维，是 Product 级投入 |
| 风险 | **高**。三容器栈的运维是无底洞；已被本地环境问题（内存不足、Docker Hub 不可达、EPNB 权限）消耗大量时间 |
| 建议 | **推迟**。等路径 A 跑通、拿到 1-2 个客户的真实需求后再启动 |

**两条路径不冲突**：路径 A 是路径 B 的技术地基。先把引擎跑通，再决定要不要包装成产品。

---

## 六、与既有商业材料的衔接

同目录下的商业文档已给出分销模式假设（`_GEO 渠道商业模式的5个假设.md`、`单位经济模型.md`、`审计《GEO商业验证实验 V1.0》`）。本文不重复商业侧论证，只指出一个技术-商业的耦合点：

`二次开发审计方案.md` 中设计的 `cost_events` 表（专家工时 / 支持工时 / API 成本）**依赖一个前提：单位服务成本可测量**。而这个成本的大头（AI 抓取的算力 + 人工介入时长）只有在路径 A 跑通、抓取流程稳定后才有可靠的度量基础。因此**技术先行、成本模型跟进**是更稳的顺序。

---

## 七、下一步建议（按 ROI 排序）

| 优先级 | 动作 | 预期产出 | 耗时 |
|--------|------|----------|------|
| **P0** | 给 `citations` 表加 `source` 字段，标记历史数据来源 | 明确知道哪些数据能用、哪些不能用 | 低 |
| **P1** | 验证 Camoufox 在本机能否抓通 1 个平台（Perplexity 最简） | 一个真实回答 + 引用源 JSON | 中 |
| **P2** | 把 `analysisPrompt` 独立出来，接 P1 的真实回答跑一次 | 一份真实的品牌可见度评分报告 | 低 |
| **P3** | 决策：走路径 A（拆件）还是路径 B（SaaS） | 路线确认，避免两头投入 | 低 |
| — | 暂缓：Partner 分销表开发 | 等客户验证 | — |

---

## 附：关键文件索引

| 用途 | 路径 |
|------|------|
| 抓取层接口定义 | `oneglanse/apps/agent/src/core/providers/types.ts` |
| 引用源抽取示例 | `oneglanse/apps/agent/src/core/providers/perplexity/lib/extractSources.ts` |
| 分析提示词（核心资产） | `oneglanse/packages/services/dist/analysis/analysisPrompt.js` |
| 分析调度 | `oneglanse/packages/services/dist/analysis/runAnalysis.js` |
| 数据模型 | `oneglanse/packages/db/clickhouse-init/schema.sql` |
| 待修复的假数据源 | `geo-intent-system/app/ai_query/openai_search.py` |
| 引用检查脚本 | `geo-intent-system/scripts/run_citation_checks.py` |
| 数据模型审计方案 | `GEO海外分销系统/二次开发审计方案.md` |
