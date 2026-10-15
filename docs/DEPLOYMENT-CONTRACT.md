# DEPLOYMENT CONTRACT — Stage-1 Commercial Pilot

> 建立时间：2026-10-06 16:50
> 依据：Phase 0 环境盘点（**全部实测**，非假设）
> 标注规则：`FACT`（实测确认）/ `ASSUMPTION`（合理推断）/ `UNKNOWN`（无法确定）

---

## 1. Environment

| 项 | 值 | 状态 |
|---|---|:-:|
| Host | `DESKTOP-IKRV41G` | **FACT** |
| OS | Windows（`win32`） | **FACT** |
| LAN IP | `172.19.0.1`（Hyper-V 虚拟网卡） | **FACT** |
| 防火墙 | `BlockInbound, AllowOutbound`（三profile 全部） | **FACT** |
| Python | 3.13.14（venv） | **FACT** |
| FastAPI / Uvicorn / Starlette | 0.141.1 / 0.53.0 / 1.6.0 | **FACT** |

---

## 2. WordPress

| 项 | 值 | 状态 |
|---|---|:-:|
| 安装位置 | `E:/xampp/htdocs` | **FACT** |
| WordPress 版本 | **7.1** | **FACT** |
| PHP 版本 | **8.2.12** | **FACT** |
| Web Server | Apache 2.4.58（XAMPP），OpenSSL 3.1.3 | **FACT** |
| 数据库 | MariaDB 10.4.32，已初始化 | **FACT** |
| 站点标题 | `Get Your B2B Brand Cited in ChatGPT, Perplexity & AI Ove…` | **FACT** |
| 现有用户 | `gino`(ID=1), `david`(ID=2, administrator) | **FACT** |
| 自定义 mu-plugins | `geo-schemas.php`（既有） | **FACT** |
| 服务端 HTTP 能力 | ✅ `wp_remote_request()` 可用 | **FACT** |
| 可改 `wp-config.php` | ✅ 已备份 `wp-config.php.pilot-backup` | **FACT** |

---

## 3. geo-distributor Backend

| 项 | 值 | 状态 |
|---|---|:-:|
| 路径 | `E:/GEO项目/技术层/geo-distributor` | **FACT** |
| 绑定地址 | `127.0.0.1`（**仅回环**） | **FACT** |
| 端口 | `8765` | **FACT** |
| 启动命令 | `uvicorn api.app:app --host 127.0.0.1 --port 8765 --no-server-header --no-access-log` | **FACT** |
| `--reload` | **未使用** ✅ | **FACT** |
| 运行环境 | `GEO_DISTRIBUTOR_ENV=production` | **FACT** |
| 数据库 | `data/pilot/geo.db`（SQLite persist） | **FACT** |
| 审计库 | `data/pilot/audit.db`（独立） | **FACT** |
| `.env` 文件 | **不存在**（密钥仅经进程环境变量注入） | **FACT** |

---

## 4. Reverse Proxy

| 项 | 值 | 状态 |
|---|---|:-:|
| nginx | **未安装** | **FACT** |
| **实际使用** | **Apache 2.4.58**（`mod_proxy` + `mod_headers` + `mod_rewrite`） | **FACT** |
| 配置位置 | `E:/xampp/apache/conf/extra/httpd-vhosts.conf` | **FACT** |
| 模板 | `deploy/apache/geo-distributor-pilot.conf` | **FACT** |
| 公开路径前缀 | `/geo-api/` | **FACT** |
| 目标 | `http://127.0.0.1:8765/` | **FACT** |
| 启用的模块 | `proxy`、`proxy_http`、`proxy_balancer`、`slotmem_shm`、`headers`、`rewrite` | **FACT** |
| `ServerTokens` | `Prod`（隐藏版本号） | **FACT** |

---

## 5. TLS / DNS / Certificate

| 项| 值 | 状态 |
|---|---|:-:|
| 真实域名 | **无** | **FACT** |
| DNS 解析 | **无**（hosts 无自定义条目） | **FACT** |
| 可信 CA 证书 | **无** | **FACT** |
| 443 监听 | **无** | **FACT** |
| HSTS | **未启用**（无真实 HTTPS，不启用） | **FACT** |

> **未伪造任何 HTTPS 条件。** 无证书即标CONDITIONAL，不用自签名冒充生产。

---

## 6. Network / Isolation

| 项 | 值| 状态 |
|---|---|:-:|
| 后端公网暴露 | **NO** —— 仅绑 `127.0.0.1` | **FACT** |
| `127.0.0.1:8765` | 可达（本机） | **FACT** |
| `172.19.0.1:8765` | **ConnectionRefused**（不可达） ✅ | **FACT** |
| 防火墙入站 | Block | **FACT** |

---

## 7. Public API Address

```
WordPress (PHP, same host)
    │  server-side HTTP (wp_remote_request)
    ▼
Apache :80  ──/geo-api/*──>  127.0.0.1:8765  (geo-distributor)
    │
    └──> WordPress 站点本体 (/)
```

**真实验证地址**：`http://127.0.0.1/geo-api/`

---

## 8. Endpoint Policies

| 项 | 策略 | 状态 |
|---|---|:-:|
| Health | `GET /geo-api/health` → 200 `{"status":"ok"}` | **FACT** |
| Health 泄露 | 无 db_path / 路径 / 内部状态 | **FACT** |
| Docs | `/geo-api/docs` → **403**（反代拒绝） | **FACT** |
| OpenAPI | `/geo-api/openapi.json` → **403**（反代拒绝） | **FACT** |
| 应用层 docs | 默认 404（需 `GEO_DISTRIBUTOR_EXPOSE_DOCS=1` 才开） | **FACT** |
| 安全响应头 | `nosniff` / `DENY` / `no-referrer` / `default-src 'none'`（单值，无重复） | **FACT** |
| `Server` 头 | `Apache`（无版本号） | **FACT** |

---

## 9. Auth / Tenant / Rate Limit / Audit

| 项 | 配置 | 状态 |
|---|---|:-:|
| Auth 机制 | `X-API-Key` 共享密钥，常数时间比较 | **FACT** |
| 密钥存储 | 进程环境变量 + WordPress `wp-config.php` 常量 | **FACT** |
| 密钥入 git | **NO**（`.gitignore:41` 保护 `.pilot_key_*`） | **FACT** |
| Tenant 解析 | **从密钥绑定值反查**，不从 header 读 | **FACT** |
| header 冲突 | → 403 | **FACT** |
| 限流 | 令牌桶，按 API Key，process-local | **FACT** |
| 限流参数 | `RATE_LIMIT=120/min`，`BURST=40` | **FACT** |
| 审计 | 独立 SQLite，写操作全记 + 被拒读操作记| **FACT** |
| 审计含密钥 | **NO**（实测两个 key 均未出现） | **FACT** |

---

## 10. Backup / Rollback

| 项 | 位置 | 状态 |
|---|---|:-:|
| `wp-config.php` 备份 | `E:/xampp/htdocs/wp-config.php.pilot-backup` | **FACT** |
| Apache 主配置备份 | **未创建** ⚠️ 见下 | — |
| vhost 备份 | **未创建** ⚠️ 见下 | — |
| geo-distributor DB | `data/pilot/geo.db`（未备份） | **FACT** |
| 审计库 | `data/pilot/audit.db`（未备份） | **FACT** |

### Rollback 命令（可执行）

```bash
# 1. 回滚 WordPress 配置
cp "E:/xampp/htdocs/wp-config.php.pilot-backup" "E:/xampp/htdocs/wp-config.php"

# 2. 移除桥接插件
del "E:/xampp/htdocs/wp-content/mu-plugins/geo-distributor-bridge.php"

# 3. 回滚 Apache 反代（删除 vhost 段后重启）
#    编辑 E:/xampp/apache/conf/extra/httpd-vhosts.conf
#    移除"===== geo-distributor Stage-1 Pilot ====="整个段
"E:/xampp/apache/bin/httpd.exe" -f "E:/xampp/apache/conf/httpd.conf" -t
# 停Apache → 重新后台启动

# 4. 停止后端（kill监听 127.0.0.1:8765 的进程）

# 5. 恢复数据（如有需要）
#    geo.db / audit.db 保留即可，无破坏性变更
```

**Rollback 触发条件**：认证异常 / 租户越权 / 后端暴露 / 审计失效 / 限流失效

**⚠️ 未完成项**：Apache `httpd.conf` 与 `httpd-vhosts.conf` 的原始备份未创建（在被要求前已修改）。
恢复依据：本文件 §4 与 `deploy/apache/geo-distributor-pilot.conf` 模板足以手工重建。

---

## 11. Log / Logging

| 项 | 配置 |
|---|---|
| 后端访问日志 | **关闭**（`--no-access-log`） |
| 审计日志 | `data/pilot/audit.db`（含 action/tenant/user/role/outcome/timestamp/ip/reason） |
| Apache 错误日志 | `E:/xampp/apache/logs/error.log` |
| **API Key 记录** | **无** —— 应用层不记录，反代 `Header always unset X-API-Key` |

---

## 12. 已知限制（如实记录）

| # | 限制 | 影响 |
|:-:|---|---|
| 1 | **无 HTTPS** | API Key 明文传输（同机 loopback 风险低，跨主机部署前必须补） |
| 2 | **无 DNS/域名** | 只能用 `127.0.0.1` 或 `localhost` |
| 3 | 限流 process-local | 多实例时总额度 = 配置 × 实例数 |
| 4 | 无自动密钥轮换 | 移除注册表即吊销 |
| 5 | Apache 配置无原始备份 | Rollback 需手工重建（模板已就绪） |
| 6 | HSTS 未启用 | 无真实 HTTPS 前不启用是正确的 |
