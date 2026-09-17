# OneGlanse 参考资料（外部开源，非本项目代码）

> 本目录只存放**参考资料**。OneGlanse 源码不在本仓库内，也不参与本项目的构建。

---

## 一、它是什么

| 项 | 值 |
|---|---|
| 性质 | 第三方开源项目（GitHub: `aryamantodkar/oneglanse`），**非自研** |
| 实际路径 | `E:\GEO项目\技术层\GEO海外分销系统\oneglanse` |
| 引入方式 | 曾作为 git submodule 引入；2026-09-17 目录整合时从本仓库移除 |
| 体积 | 约 1.2 GB（含 `node_modules`） |
| 技术栈 | Next.js 15 + React 19 + tRPC + Drizzle ORM + BullMQ/Redis + PostgreSQL 16 + ClickHouse |
| 浏览器自动化 | Camoufox + Playwright，支持 5 个 AI Provider |

**它的定位：候选基座 / 参考对象，不是「海外 GEO 分销系统」的实现。**
本仓库的 `geo_distributor/` 才是自研代码。

---

## 二、为什么不把它搬进本仓库

1. **性质不同** —— 它是对照组，不是本体。混进来会让"哪些是我们写的代码"变得模糊。
2. **软链会断** —— pnpm workspace 的 `node_modules` 全是符号链接，跨目录搬迁后链接指向旧绝对路径，必须重装依赖才能跑。
3. **体积不划算** —— 1.2 GB 第三方源码与 Python MVP 同仓，没有收益。

---

## 三、审计结论（2026-09-13，源码级实证）

详见 [OneGlanse可借鉴性分析.md](OneGlanse可借鉴性分析.md)。四条核心判断：

1. **"意图挖掘系统更实用"的感觉是对的，但结论要修正** —— 意图系统更实用是因为它有业务出口（挖意图 → 生成内容 → 发布 bookconv），而 OneGlanse 只是个仪表盘，量完就结束。这是**产品层缺失**，不是技术层缺失。
2. **技术层 OneGlanse 领先一个身位** —— 它用真实浏览器登录态抓取 5 个 AI 平台的原生回答 + 引用源；意图系统的"AI 可见度"模块当时产出的很可能是假数据。
3. **两者不是竞品，是上下游** —— 意图系统负责"找问题"，OneGlanse 负责"验证答案"，合并后才是 GEO 完整闭环。
4. **二次开发最优路径是"拆件"而非"整体二开"** —— 可复用资产只有 2 块：**Provider 抓取层** + **分析提示词**；其余多租户 SaaS 脚手架对一人公司是纯负担。

> ⚠️ 同批审计还发现了一个 P0：`geo-intent-system` 的 `app/ai_query/openai_search.py` 第 153-160 行存在必崩代码（`urllib.open()` 不接受 `headers`/`method` 关键字参数），导致 AI 可见度数据实际返回 `"error"`。处理 OneGlanse 之前应先修这个。

---

## 四、怎么把它跑起来

见 [启动说明.md](启动说明.md)（双击 `启动OneGlanse.bat`，或 `pnpm local`）。

> 注意：WorkBuddy 沙箱内无法拉起长驻服务（进程树会被回收 + 内存上限），必须你自己双击运行。

---

## 五、目录内文档

| 文档 | 内容 |
|---|---|
| [启动说明.md](启动说明.md) | 本地启动 / 停止 / 排错，含已修复的 6 个历史坑 |
| [二次开发审计方案.md](二次开发审计方案.md) | 技术栈、数据库 Schema、tRPC 路由盘点与改造方案 |
| [OneGlanse可借鉴性分析.md](OneGlanse可借鉴性分析.md) | 与 geo-intent-system 的对照分析、可复用资产清单、二开路径 |
