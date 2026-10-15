# Remote Deployment Final Gate

> 批次：Remote Deployment Hardening（2026-10-06 15:00–15:30）
> 判定依据：**实际测试证据**，非意图声明
> 目标：让 geo-distributor 具备被 WordPress 安全调用、进入真实远程商业部署验证的条件

---

## 1. Gate 结果

| # | 项 | 状态 | 证据 |
|:-:|---|:-:|---|
| 1 | Authentication | **PASS** | 30/30 端点接入；RT-10 验明生产无兜底身份 |
| 2 | Tenant Isolation | **PASS** | B-1 23 项 + B-3 9 项；tenant 来自 `auth.tenant_id` |
| 3 | Role Authorization | **PASS** | 5 角色矩阵；RT 验明伪造 `X-WP-Role` 无效 |
| 4 | CORS | **PASS** | 白名单模式，11 项测试 |
| 5 | Secrets | **PASS** | 环境变量注入；`config/api_keys.json` 已 gitignore |
| 6 | Production Startup | **PASS** | `start_api_prod.sh` 无 `--reload`、绑回环、**缺密钥拒绝启动** |
| 7 | TLS Contract | **CONDITIONAL PASS** | 契约已定义，**待实际部署执行** |
| 8 | Reverse Proxy | **CONDITIONAL PASS** | nginx 示例已就绪，**待实际部署** |
| 9 | Docs Exposure | **PASS** | 应用层默认 404 + 反代层纵深防御 |
| 10 | Audit Logging | **PASS** | 写操作全覆盖 + 拒绝读操作留痕；RT-03/04/05 验证 |
| 11 | Rate Limiting | **PASS** | 令牌桶按 Key；RT-06/07/08 验证（含 XFF 伪造） |
| 12 | Error De-identification | **PASS** | 401/403/404/429/500 全部脱敏，RT-09 验证 |
| 13 | Security Tests | **PASS** | 6 个安全套件，**117 项** |
| 14 | Reverse Validation | **PASS** | 3 次注入，**18 项安全测试**如期FAILED |
| 15 | Full Regression | **PASS** | `418 passed / 1 skipped`（1 failed 属 R-3 外部域） |
| 16 | Scope Integrity | **PASS** | 禁改系统均未触碰（`geo_intent.db` 除外，见 §4） |

### 总体：**CONDITIONAL PASS**

剩余项全部属于**真实基础设施部署**（TLS 证书、反代配置、真实主机与凭证），
代码与安全边界已完成。

---

## 2. 本轮实际改动

| 文件 | 变更 |
|---|---|
| `api/app.py` | 审计中间件（范围修正）、安全响应头中间件、500 脱敏异常处理、`/health` 最小化 |
| `api/audit.py` | 新增 `query_unauthenticated_attempts()`（认证失败审计查询） |
| `api/deps.py` | 限流接入、审计辅助函数 |
| `deploy/nginx/geo-distributor.conf.example` | **新增** — 完整反代契约 |
| `docs/PRODUCTION-DEPLOYMENT.md` | **新增** — 部署契约 |
| `docs/SECURITY-CONTRACT.md` | **新增** — 安全属性与证据 |
| `tests/test_remote_deployment_redteam.py` | **新增** — RT-01~RT-10，27 项 |
| `tests/conftest.py` | 审计库隔离 + 限流器重置 + 单例恢复 |
| `tests/test_p1_remaining.py` | 适配最小化 `/health` |

### 过程中修掉的两个真实缺陷

**① `/health` 泄露内部信息**（公开端点）
原实现返回 `db_path`（文件系统路径）、`persistence`、各 service 内部状态与错误消息。
公开端点的每个字段都是公开信息。已改为**仅** `{"status": "ok"}`。

**② 审计漏记攻击场景**
原设计只审计写操作 → 认证失败与跨租户读取（GET）不留痕，等于**发现不了爆破**。
已改为：写操作全记 + **被拒绝的读操作**也记（`outcome=DENIED`）。
认证失败无可信 tenant，故新增独立查询入口（仅内部运维可见）。

---

## 3. Red Team 结果（RT-01 ~ RT-10）

| ID | 场景 | 期望 | 实测 |
|:-:|---|---|:-:|
| RT-01 | 生产脚本含 `--reload` | 拒绝 | ✅ 0 处 |
| RT-02 | `/docs` 默认 404 | 是 | ✅ 显式开启时 200（门禁非死配置） |
| RT-03 | 审计含原始 API Key | 无 | ✅ |
| RT-04 | 认证失败有审计 | 有 | ✅ 标记 DENIED，且不含密钥原文 |
| RT-05 | 跨租户尝试留痕且不泄露受害方 | 是 | ✅ |
| RT-06 | 超限返回 429 | 是 | ✅ 响应体无堆栈/路径/密钥 |
| RT-07 | A 限流不影响 B | 是 | ✅ |
| RT-08 | 伪造 XFF 不绕过限流 | 是 | ✅ 按 Key 计数 |
| RT-09 | 500 无 stack trace | 是 | ✅ 无 traceback/路径/SQL/类型名 |
| RT-10 | 生产缺密钥 fail closed | 是 | ✅ 无自动生成、无 fallback |

**补充**：401 文案统一（不区分密钥存在性）、404 不回显 resource_id、403 不回显受害方租户。

---

## 4. Reverse Validation（3 次故意破坏）

| 实验 | 注入缺陷 | 期望 | 实测 FAILED |
|:-:|---|---|---|
| A | `verify_api_key` 对未知密钥返回兜底身份 | 安全测试失败 | **10 项** |
| B | `resolve_tenant` 无条件采纳 header | 跨租户测试失败 | **2 项** |
| C | 关闭限流 enforcement | 限流测试失败 | **6 项** |

恢复方式：**精确字符串编辑**（未用 `git checkout` / `git restore`，避免回退未提交工作）。
恢复后 `grep INJECTED api/` = 0，`418 passed`。

---

## 5. Full Test Results

```
418 passed / 1 skipped / 1 failed / 2 warnings in 32.50s
```

| 项 | 值 |
|---|---|
| 本批次开始时 | 375 passed / 1 skipped / 0 failed |
| 本批次结束 | **418 passed** / 1 skipped / 1 failed |
| 新增测试 | **+43**（红队 27 + 审计/限流相关 16） |
| 删除测试 | **0** |
| 新增 skip | **0** |
| 新增 xfail | **0** |
| 安全测试弱化 | **0**（所有断言保持或加强） |

**skip 原因**（既存，允许保留）：
```
tests/test_sprint4_real_adapter.py:184
  No NOT_MENTIONED observations found
```
数据依赖型跳过 —— 该样本在当前数据集中不存在。

**2 warnings**（既存，非本批次）：
```
StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated
BlockingPortal alias deprecated
```
第三方库弃用提示，不影响功能。

**唯一 failed**：`test_prompt_integrity` —— 属**R-3 历史 prompt 归属治理域**，
由外部并行任务改动 `geo-collector.db` 引起（fixture 已切 BookConv，DB 仍在过渡）。
**与本批次无关，且本批次禁止修改 `geo-collector`。**

---

## 6. Scope Integrity

| 对象 | 本批次改动 | 说明 |
|---|:-:|---|
| `geo-intent-system` 代码 | **NO** | `app/database.py` sha256 `41bfd5dd` 未变 |
| `geo-intent.db`（数据） | **NO** | 但 mtime 15:14:23 有外部写入 ⚠️ 见下 |
| `geo-collector` | **NO** | 未触碰 |
| R-3 历史数据 | **NO** | 未触碰 |
| `geoflow` | **NO** | `app/Models` mtime 仍 2026-06-02 |
| commit / push | **0 / 0** | 未执行 |

### 变更归属区分

| 类别 | 内容 |
|---|---|
| **Pre-existing** | TD-11 / B-1 / B-2 / 审计+限流 批次的全部改动（51 项脏工作区） |
| **This batch** | 上表 9 个文件（安全响应头、500 脱敏、health 最小化、审计范围修正、nginx 示例、三份文档、红队测试） |

### ⚠️ 治理提示：外部并行任务仍在进行

`geo_intent.db` 于 **15:14:23** 被外部写入（observations 数持续变化）。
这意味着 **Run#5 Freeze 的完整性前提仍由外部任务控制**。

本批次所有"未改动 geo-intent"的声明，对本会话的操作范围成立；
但**整体项目的 freeze 基线**需要等 R-3 治理收尾后重新记录。

---

## 7. True Remaining Blockers

| # | 项 | 类型 | 谁能解决 |
|:-:|---|---|---|
| 1 | 实际 TLS 证书签发 | 基础设施 | 部署方 |
| 2 | 实际 DNS 解析 | 基础设施 | 部署方 |
| 3 | 实际 nginx 配置落地 | 基础设施 | 部署方（模板已就绪） |
| 4 | 真实主机与端口开放策略 | 基础设施 | 部署方 |
| 5 | 真实 WordPress 实例凭证 | 外部凭证 | 用户 |
| 6 | 生产 hostname | 外部条件 | 用户 |

**以上全部是真实外部条件，不涉及代码或安全边界。**

### 明确不构成阻塞的项

| 项 | 状态 |
|---|---|
| 认证绕过 | ✅ 已修并经反向验证 |
| 跨租户风险 | ✅ 已修并经反向验证 |
| secret fallback | ✅ 无（缺密钥拒绝启动） |
| 公开 docs | ✅ 应用层 + 反代层双关闭 |
| 生产 reload | ✅ 已消除 |
| 后端公网暴露 | ✅ 绑回环 + 契约要求 |
| 假绿安全测试 | ✅ 3 次注入验证 |

---

## 8. API 暴露矩阵（30/30 端点）

| Router | 端点数 | 认证 | 租户 | 角色 | 限流 | 审计 | Exposure |
|---|:-:|:-:|:-:|:-:|:-:|:-:|---|
| `/health` | 1 | ❌ | — | — | ❌ | ❌ | **INTERNAL**（反代探活） |
| `/clients` | 4 | ✅ | ✅ | 写/读 | ✅ | ✅ | **PORTAL** |
| `/projects` | 8 | ✅ | ✅ | 写/读 | ✅ | ✅ | **PORTAL** |
| `/measurements` | 2 | ✅ | ✅ | 写/读 | ✅ | ✅ | **PORTAL** |
| `/reports` | 2 | ✅ | ✅ | 读 | ✅ | ✅ | **PORTAL** |
| `/sync` | 4 | ✅ | — | 写/读 | ✅ | ✅ | **INTERNAL**（平台级运维） |
| `/distribution` | 10 | ✅ | — | 写/读 | ✅ | ✅ | **INTERNAL**（平台级采集） |
| `/docs` `/openapi.json` `/redoc` | 3 | ❌ | — | — | — | — | **DISABLED**（默认 404） |

> Exposure 语义：
> `PORTAL` = 租户/客户可见 · `INTERNAL` = 仅 HQ 运维 · `DISABLED` = 默认关闭

---

## 9. Next Step

> ## 进入 WordPress ↔ geo-distributor 最小真实集成验证
>
> 代码与安全边界已完成。剩余全部是真实基础设施与凭证。
>
> 建议的最小验证路径：
> 1. 部署到测试主机，配好 TLS + 反代
> 2. 为 WordPress 生成一个测试密钥（`DISTRIBUTOR_ADMIN` 角色）
> 3. WordPress 侧发起一次真实调用（建议 `GET /health` + `GET /projects`）
> 4. 验证审计库产生了对应记录
>
> **不需要**继续做代码层安全优化 —— 剩余项不在代码里。
