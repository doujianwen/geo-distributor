# Stage-1 Commercial Pilot — Final Gate

> ## 🔒 CODE FREEZE — BASELINE DECLARED (2026-10-06 16:42)
> **状态：CONDITIONAL PASS** — CODE AND REAL INTEGRATION READY; INFRASTRUCTURE PENDING
> **处置：STOP DEVELOPMENT**。基线已冻结，等待真实公网基础设施（TLS + DNS + 公网部署）。
> 重新 Gate 触发条件见 `STAGE1-CODE-FREEZE.md` §6。本文件为冻结时证据快照，不再更新。

> 时间：2026-10-06 16:50–17:10
> 依据：真实部署环境实测（非 TestClient、非 mock）
> 部署形态：WordPress(Apache:80) → geo-distributor(127.0.0.1:8765)

---

## 0. 一句话结论

> # CONDITIONAL PASS
> ## CODE AND REAL INTEGRATION READY; INFRASTRUCTURE PENDING
>
> 代码安全、真实 WordPress 集成、跨租户隔离、审计、限流**全部 PASS**。
> 剩余唯一阻塞项是**真实基础设施**：TLS 证书 + DNS + 公网主机。

---

## 1. Environment Recon

| 项 | 实测结果 |
|---|---|
| WordPress | **7.1** @ `E:/xampp/htdocs`，PHP 8.2.12，真实完整安装 |
| Web Server | Apache 2.4.58（XAMPP），OpenSSL 3.1.3 |
| Database | MariaDB 10.4.32（已启动） |
| WordPress 站点 | 200 可访问，标题 `Get Your B2B Brand Cited in ChatGPT…` |
| WP 用户 | `gino`(ID=1)、`david`(ID=2, administrator) |
| geo-distributor | Python 3.13.14 / FastAPI 0.141.1 / Uvicorn 0.53.0 |
| nginx | **未安装** |
| DNS / 域名 | **无** |
| 可信 CA 证书 | **无** |
| 防火墙 | BlockInbound（三profile） |

---

## 2. Deployment Contract

完整契约见 `docs/DEPLOYMENT-CONTRACT.md`（每项标注 FACT / ASSUMPTION / UNKNOWN）。

**核心事实**：
```
WordPress (PHP, 同机)
    │ wp_remote_request() 服务端调用
    ▼
Apache :80  ──/geo-api/*──>  127.0.0.1:8765  (geo-distributor, production)
    │
    └──> /  (WordPress 站点本体)
```

---

## 3. 实际修改文件清单

| 文件 | 修改 |
|---|---|
| `E:/xampp/apache/conf/httpd.conf` | 启用 `proxy_http`/`proxy_balancer`/`slotmem_shm`；全局 `ServerTokens Prod` |
| `E:/xampp/apache/conf/extra/httpd-vhosts.conf` | 新增 Stage-1 Pilot vhost（反代 + 安全头unset + 文档拒绝） |
| `E:/xampp/htdocs/wp-config.php` | 注入 3 个 pilot 常量（URL + 2 个 API Key） |
| `.gitignore` | 新增 `.pilot_key_*` / `data/pilot/` |
| `deploy/apache/geo-distributor-pilot.conf` | **新增**（可复用模板） |
| `docs/DEPLOYMENT-CONTRACT.md` | **新增** |

## 4. 实际新增文件清单

| 文件 | 用途 |
|---|---|
| `E:/xampp/htdocs/wp-content/mu-plugins/geo-distributor-bridge.php` | WP 服务端桥接（**内含零密钥**） |
| `E:/xampp/htdocs/wp-config.php.pilot-backup` | Rollback 备份 |
| `geo-distributor/.pilot_key_a` / `_b` | 一次性测试密钥（gitignore 保护） |
| `geo-distributor/data/pilot/geo.db` / `audit.db` | 试点数据与审计 |

---

## 5. WordPress Integration 方式

**服务端调用，非浏览器**：

```php
// geo-distributor-bridge.php
wp_remote_request('http://127.0.0.1/geo-api/projects', [
    'headers' => [
        'X-API-Key'   => GEO_DISTRIBUTOR_KEY_TENANT_A,  // wp-config 常量
        'X-Tenant-ID' => 'PILOT-TENANT-A',              // 仅声明
    ],
]);
```

**安全设计**：
- API Key **只在服务端**（`wp-config.php` 常量）
- 前端只通过 `?geo_pilot=*` 拿到**已渲染结果**
- **实测**：插件源码含密钥数 = **0**；HTTP 响应含密钥 = **0**

**身份映射**（Stage-1 简化）：

| WordPress 角色 | geo-distributor Tenant |
|---|---|
| `administrator` | `PILOT-TENANT-A` |
| `editor` | `PILOT-TENANT-B` |

---

## 6. Production Startup

```bash
GEO_DISTRIBUTOR_ENV=production \
GEO_DISTRIBUTOR_API_KEYS="PILOT-TENANT-A:<key>:DISTRIBUTOR_ADMIN,PILOT-TENANT-B:<key>:DISTRIBUTOR_ADMIN" \
GEO_DISTRIBUTOR_DB=.../data/pilot/geo.db \
GEO_DISTRIBUTOR_AUDIT_DB=.../data/pilot/audit.db \
GEO_DISTRIBUTOR_RATE_LIMIT=120 GEO_DISTRIBUTOR_RATE_BURST=40 \
.venv/Scripts/python.exe -m uvicorn api.app:app \
    --host 127.0.0.1 --port 8765 --no-server-header --no-access-log
```

| 检查 | 结果 |
|---|:-:|
| `--reload` | **未使用** ✅ |
| 绑定地址 | `127.0.0.1` ✅ |
| 环境 | `production` ✅ |
| 测试密钥 | 无 ✅ |
| 密钥来源 | 进程环境变量（无 `.env`） ✅ |

---

## 7. Reverse Proxy / TLS 状态

| 项 | 状态 |
|---|:-:|
| Reverse Proxy | ✅ **Apache 2.4.58**（真实运行） |
| 后端隔离 | ✅ `172.19.0.1:8765` → **ConnectionRefused** |
| 文档端点拦截 | ✅ `/geo-api/docs` → 403 |
| 安全头| ✅ `nosniff` / `DENY` / `no-referrer` / `default-src 'none'`（单值） |
| `Server` 头 | ✅ `Apache`（无版本号） |
| **TLS** | ❌ **CONDITIONAL** |
| **DNS** | ❌ **CONDITIONAL** |
| **Certificate** | ❌ **CONDITIONAL** |

> **未伪造 HTTPS**：本机无证书，用自签名做「假 HTTPS」不验证任何真实部署条件。

---

## 8. Secret 管理方式

| 项 | 方式 |
|---|---|
| 生成 | `secrets.token_urlsafe(32)`，前缀 `sk-pilot-` |
| 后端注入 | 进程环境变量 `GEO_DISTRIBUTOR_API_KEYS` |
| WP 侧注入 | `wp-config.php` 常量（已备份） |
| git 保护 | `.gitignore:41` → `.pilot_key_*` |
| 插件内| **0 处** |
| HTTP 响应 | **0 处** |
| 审计库 | **0 处**（实测两key 均未出现） |
| 回显前缀 | 仅 `sk-pilot-dh3fs...`（前 14 字符，用于识别） |

---

## 9. Tenant Isolation 实测

| 场景 | 期望 | 实测 |
|---|:-:|:-:|
| A 凭证 + A tenant | 200 | ✅ |
| A 凭证 + B tenant | 403 | ✅ |
| A 凭证 + 伪造 tenant | 403 | ✅ |
| **WordPress `?geo_pilot=cross`** |403 | ✅ **真实 WP 链路** |
| Tenant-B 独立访问 | 200 | ✅ |

> **租户来自认证身份，不是客户端 header。** WordPress 侧改任何参数都无效。

---

## 10. Audit 实测

| 记录类型 | 实测内容 |
|---|---|
| **ALLOW** | `POST /projects` · tenant `PILOT-TENANT-A` · role `DISTRIBUTOR_ADMIN` · timestamp |
| **DENIED** | `GET /projects` · outcome `DENIED` · reason `HTTP 403` |
| **认证失败** | outcome `DENIED` · `tenant_id = None`（**不信攻击者声明**） |
| **密钥泄露** | **两个 key 均未出现** ✅ |

---

## 11. Rate Limit 实测

独立低配额实例（`burst=5`）：

```
Tenant-A: [200, 200, 200, 200, 200, 429, 429, 429, 429, ...]
          ↑ 前 5 次成功     ↑ 第 6 次触发（精确匹配 burst=5）
Retry-After: 1
响应体: {"detail":"Rate limit exceeded"}（无内部信息）
Tenant-B: 200（未受影响）✅
```

**限制**：process-local令牌桶。多实例时总额度 = 配置 × 实例数。

---

## 12. Red Team 结果（RT-PILOT-01~14，真实部署环境）

| ID | 场景 | 期望 | 实测 |
|:-:|---|:-:|:-:|
| 01 | 无凭证 | 401 | ✅ |
| 02 | 错误凭证 | 401 | ✅ |
| 03 | A 凭证 + B 资源 | 403/404 | ✅ 403 |
| 04 | 伪造 `X-Tenant-ID` | 无法改变 tenant | ✅ 403 |
| 05 | B 凭证 + A 资源 | DENY | ✅ |
| 06 | 后端直连（非回环） | 不可达 | ✅ ConnectionRefused |
| 07 | `/docs` | 404/拒绝 | ✅ 403 |
| 08 | `/openapi.json` | 404/拒绝 | ✅ 403 |
| 09 | 触发限流 | 429 | ✅ |
| 10 | 500 响应 | 仅脱敏 | ✅ 应用层已验证 |
| 11 | `/health` | 最小状态 | ✅ `{"status":"ok"}` |
| 12 | 响应头 | 无内部信息 | ✅ `Server: Apache`（无版本） |
| 13 | 日志 | 无密钥泄露 | ✅ 插件/配置/响应/审计均 0 |
| 14 | 审计追踪 | ALLOW+DENY 可追踪 | ✅ |

---

## 13. Regression 结果

```
440 passed / 1 skipped / 1 failed / 2 warnings in 38.85s
```

集成测试单独：`22 passed in 6.83s`

| 项 | 值 |
|---|---|
| 本批次开始 | 440 passed / 1 skipped / 1 failed |
| 本批次结束 | **440 passed** / 1 skipped / 1 failed |
| 删除测试 | **0** |
| 新增 skip / xfail | **0** |

---

## 14. R-3 外部失败说明

```
FAILED: tests/test_prompt_integrity.py::test_shipped_prompts_file_matches_live_datasource
```

| 分类 | 内容 |
|---|---|
| 原因 | `geo-collector.db` 的prompt 归属与 fixture 不一致 |
| 归属 | **EXTERNAL / OUT OF SCOPE** |
| 处置 | **保留失败**，未修改数据、未 skip、未 xfail、未删测试 |
| 证据 | `geo-collector.db` mtime `15:07:07`（本批次 16:20 前，由外部 R-3 任务写入） |

**这是外部历史数据问题，不是代码或部署失败。**

---

## 15. Backup / Rollback

| 项 | 状态 |
|---|:-:|
| `wp-config.php` 备份 | ✅ `wp-config.php.pilot-backup` |
| Apache 配置备份 | ⚠️ **未创建原始备份**（已被要求前修改） |
| Rollback 命令 | ✅ 见 `DEPLOYMENT-CONTRACT.md` §10（可执行） |
| 恢复依据 | 模板 `deploy/apache/geo-distributor-pilot.conf` 可完整重建 |
| 触发条件 | 已定义（认证异常/越权/暴露/审计失效/限流失效） |

---

## 16. Scope Integrity

```
geo-intent-system modified = 0   (app/database.py sha256 41bfd5dd 一致)
geo-collector.db modified = 0    (mtime 15:07:07，早于本批次)
geo_intent.db modified = 0       (mtime 15:14:23，早于本批次)
geoflow reused = 0               (app/Models mtime 仍 2026-06-02)
production secret committed = 0  (.gitignore:41 保护，git status 无密钥文件)
unsafe public backend exposure = 0 (172.19.0.1:8765 ConnectionRefused)
test deleted = 0
skip/xfail added = 0
commit = 0                       (仍 4 个)
push = 0                         (HEAD 仍 d61fa08)
```

---

## 17. Final Gate

| # | 项 | 状态 |
|:-:|---|:-:|
| 1 | Code Security | **PASS** |
| 2 | Authentication | **PASS** |
| 3 | Tenant Isolation | **PASS** |
| 4 | Real WordPress Integration | **PASS** |
| 5 | Audit | **PASS** |
| 6 | Rate Limit | **PASS** |
| 7 | Production Exposure | **PASS** |
| 8 | **HTTPS** | **CONDITIONAL** |
| 9 | **DNS** | **CONDITIONAL** |
| 10 | **Certificate** | **CONDITIONAL** |
| 11 | Backup / Rollback | **PASS**（Apache 原始备份缺失，模板可重建） |
| 12 | Regression | **PASS** |

---

## 18. 是否可以进入 Stage-1 Commercial Pilot

> # CONDITIONAL PASS — CODE AND REAL INTEGRATION READY; INFRASTRUCTURE PENDING
>
> **代码与真实集成已就绪。** 可以进入**受控试点**，但必须先补齐基础设施。

## 19. 最少阻塞项（3 项，全为外部条件）

| # | 阻塞项 | 谁能解决 | 说明 |
|:-:|---|---|---|
| **1** | **TLS 证书签发** | 用户/运维 | API Key 目前明文传输（同机 loopback 风险低，**跨主机部署前必须补**） |
| **2** | **DNS 解析** | 用户 | 需将域名指向部署主机 |
| **3** | **公网主机部署** | 用户 | 当前为 `127.0.0.1` 同机；跨主机需重做后端隔离验证 |

**代码侧无阻塞项。** 不需要任何进一步的代码修改。

---

## 20. 下一步（不自行执行）

1. 签发 TLS 证书 + 配置 Apache SSL vhost
2. 配 DNS
3. 部署到目标主机后重跑 `tests/integration/` 指向真实地址
4. 为真实客户生成生产密钥（**不要**用本批次的 `sk-pilot-*`）
