# 项目长期记忆：海外 GEO 分销系统（geo-distributor）

## 目录约定（2026-09-17 整合后生效）

- **唯一主目录**：`E:\GEO项目\技术层\geo-distributor` —— 代码、文档、git 都在这里
- `E:\GEO项目\技术层\GEO海外分销系统` 已降级为 **oneglanse 第三方源码存放处**，不再放项目文档
- `oneglanse` = GitHub 第三方开源 `aryamantodkar/oneglanse`，**非自研**。审计结论是「拆件而非整体二开」，可复用资产只有两块：Provider 抓取层 + 分析提示词

## 两套版本号，不要对号入座

- **文档 V1→V4** = 商业路线图：诊断 → 监测 → 运营 → 渠道分账
- **代码 V0.1→V0.4** = 技术版本（当前 Sprint 4，191 tests 全绿）

## 目录结构

| 路径 | 内容 |
|------|------|
| `docs/00-strategy/` | 商业战略文档 6 份（规划 / 经济模型 / 假设 / 杠精 / 验证方法审计） |
| `docs/reference/oneglanse/` | 第三方开源参考资料（源码本体不在此仓库） |
| `docs/ADRs/` | 架构决策记录 7 个 |
| `.workbuddy/memory/` | 工作日志，**纳入版本控制** |

## 环境

- Python venv：`.\.venv\Scripts\python.exe`，测试命令 `pytest tests/ -q`
- 换行符：`.gitattributes` 固定 LF（`.bat` / `.ps1` 例外用 CRLF）
- 仓库目前**无 remote**

## 上游依赖（同在 `E:\GEO项目\技术层\`）

`geo-collector`、`elmo` —— 通过 Adapter 层接入，输出统一 `PlatformObservation`；不修改上游源码（Upstream First，ADR-006）
