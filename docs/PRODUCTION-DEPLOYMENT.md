# PRODUCTION DEPLOYMENT CONTRACT

> 适用范围：`geo-distributor` 远程商业部署
> 状态：**可执行契约** —— 部署方按本文档配置即可，不需要读代码

---

## 1. 架构与信任边界

```
Internet
   │  HTTPS :443
   ▼
┌─────────────────────────────────┐
│ Reverse Proxy / Gateway (nginx) │  ← TLS 终止 · 限流 · 清洗 forwarded headers
└─────────────────────────────────┘
   │  HTTP :8765（仅回环）
   ▼
┌─────────────────────────────────┐
│ geo-distributor (FastAPI)        │  ← 认证 · 授权 · 租户隔离 · 应用层限流 · 审计
└─────────────────────────────────┘
   │
   ▼
geo-intent-system（Run#5 Freeze，不得修改）
```

### 不可违反的约束

| # | 约束 | 原因 |
|:-:|---|---|
| 1 | **后端端口不得直接暴露公网** | 绕过 TLS = 明文传输 `X-API-Key` = 等于没有认证 |
| 2 | **禁止把 `0.0.0.0` 当安全措施** | 它只解决「能不能连」，不解决「传输是否安全」。绑定回环 + 反代是唯一正确姿势 |
| 3 | TLS 必须在反代终止 | 应用层不处理证书，避免私钥落在应用机器 |
| 4 | 生产禁用 `--reload` | 热重载会监视文件系统、占用额外进程、并可能因文件变化产生非预期行为 |
| 5 | 密钥只经环境变量注入 | 不进配置文件、不进数据库、不进 git |

---

## 2. 启动方式

| 场景 | 脚本 | 特点 |
|---|---|---|
| 开发 | `./start_api.sh` | 带 `--reload`，`127.0.0.1` |
| **生产** | `./start_api_prod.sh` | **无 `--reload`**，强制 `production`，**缺密钥拒绝启动** |

生产启动前置检查（脚本已内置）：

```bash
# 必须由进程管理器或 .env 注入
export GEO_DISTRIBUTOR_ENV=production
export GEO_DISTRIBUTOR_API_KEYS='DST-001:sk-xxx:DISTRIBUTOR_ADMIN'
./start_api_prod.sh
```

> **缺 `GEO_DISTRIBUTOR_API_KEYS` 时脚本以退出码 1 拒绝启动** ——
> 宁可起不来，也不允许以无认证状态对外服务。

---

## 3. 环境变量契约

| 变量 | 必填 | 默认 | 说明 |
|---|:-:|---|---|
| `GEO_DISTRIBUTOR_ENV` | ✅ | — | 生产必须 `production`。非 `dev/test/local` 时**不加载任何内置密钥** |
| `GEO_DISTRIBUTOR_API_KEYS` | ✅ | — | 格式 `TENANT:KEY:ROLE[,...]`，见 §4 |
| `GEO_DISTRIBUTOR_DB` | 推荐 | `data/geo_distributor.db` | SQLite 路径。生产必须指向持久化目录 |
| `GEO_DISTRIBUTOR_AUDIT_DB` | 推荐 | `data/audit_log.db` | 审计库，**与业务库分离** |
| `GEO_DISTRIBUTOR_CORS_ORIGINS` | ✅ | 空（零跨域） | WordPress 域名，逗号分隔 |
| `GEO_DISTRIBUTOR_RATE_LIMIT` | ❌ | 120 | 每分钟请求数（每租户） |
| `GEO_DISTRIBUTOR_RATE_BURST` | ❌ | 40 | 突发上限 |
| `GEO_DISTRIBUTOR_EXPOSE_DOCS` | ❌ | 关闭 | 设为 `1` 才开放 `/docs` |

**密钥生成**：

```bash
python -c "import secrets; print('sk-' + secrets.token_urlsafe(32))"
```

---

## 4. 认证与角色

### 请求头

```
X-API-Key: <共享密钥>        # 必需
X-Tenant-ID: DST-001# 可选，仅作声明
```

**关键设计**：`tenant_id` **从密钥绑定值反查**，不从 `X-Tenant-ID` 读取。
请求头与绑定值冲突时返回 **403**；请求头缺失时回落到绑定值。

这意味着：`X-Tenant-ID` 是**声明**，`X-API-Key` 才是**凭证**。

### 角色

| 角色 | tenant 范围 | 写| 跨 tenant |
|---|:-:|:-:|:-:|
| `DISTRIBUTOR_ADMIN` | 本tenant | ✅ | ❌ |
| `DISTRIBUTOR_USER` | 本 tenant | ✅ | ❌ |
| `CLIENT_VIEWER` | 本 tenant | ❌ | ❌ |
| `HQ_TECHNICAL` | 全部 | ✅ | ✅ |
| `HQ_MANAGEMENT` | 全部 | ✅ | ✅ |

---

## 5. 反向代理要求（nginx）

完整示例见：`deploy/nginx/geo-distributor.conf.example`

### 必须做到

| # | 要求 | 反代层实现 |
|:-:|---|---|
| 1 | HTTP → HTTPS 跳转 | `return 308 https://$host$request_uri` |
| 2 | TLS 1.2+ | `ssl_protocols TLSv1.2 TLSv1.3` |
| 3 | 安全响应头 | HSTS / nosniff / DENY / CSP |
| 4 | **不记录 API Key** | 自定义 `log_format`，**不含** `$http_x_api_key` / `$http_authorization` |
| 5 | 请求体上限 | `client_max_body_size 8m` |
| 6 | 超时策略 | connect 10s / send 60s / read 120s |
| 7 | **覆盖 forwarded headers** | 用 `$remote_addr` 而非 `$proxy_add_x_forwarded_for` |
| 8 | 拒绝文档端点 | `location ~ ^/(docs\|redoc\|openapi\.json) { return 404; }` |
| 9 | IP 限流（第一层） | `limit_req_zone $binary_remote_addr` |
| 10 | 隐藏文件拒绝 | `location ~ /\. { deny all; }` |

### 关于 forwarded headers 的信任

**应用层不信任 `X-Forwarded-For` / `X-Forwarded-Proto`** ——
它们可被客户端任意伪造。

**责任划分**：
- 反代层**覆盖**（而非追加）这些头 → 应用读到的永远是真实来源
- nginx 配置必须使用 `$remote_addr`，**不可**用 `$proxy_add_x_forwarded_for`
  （后者会把客户端伪造的值追加进去，污染可信链）

### 限流：两层缺一不可

| 层 | 维度 | 挡什么 |
|---|---|---|
| nginx | IP | 无凭证的扫描 / 爆破 |
| 应用 | API Key | 单租户失控（nginx 看不到 API Key） |

---

## 6. 公开端点

| 端点 | 认证 | 返回内容 |
|---|:-:|---|
| `/health` | ❌ 公开 | **仅** `{"status": "ok"}` |
| `/docs` | ❌ 默认 404 | 需 `GEO_DISTRIBUTOR_EXPOSE_DOCS=1` **且**反代放行 |
| `/openapi.json` | ❌ 默认 404 | 同上 |
| `/redoc` | ❌ 默认 404 | 同上 |

`/health` 严格最小化的原因：它是公开端点，返回的每个字段都是公开信息。
原实现曾暴露 `db_path`（文件系统路径）与各service 内部状态 —— 已移除。

> `/health` 在 nginx 中配置了 `access_log off` —— 高频探活轮询会淹没访问日志。

---

## 7. 错误响应契约

| 状态码 | 语义 | 不泄露 |
|---|---|---|
| 401 | 无效/缺失凭证 | 不区分「密钥不存在」与「密钥错误」；401 文案完全一致 |
| 403 | 已认证但越权 | 不回显受害方租户标识 |
| 404 | 资源不存在或不可见 | **不回显 resource_id**（B-1 去标识化） |
| 429 | 触发限流 | 不含 tenant存在性、密钥有效性、堆栈、路径 |
| 500 | 内部错误 | **不含** stack trace / 文件路径 / SQL / 异常类型名 / 对象 repr |

500 完整信息只进服务端日志。

---

## 8. 审计

| 项 | 说明 |
|---|---|
| 存储 | 独立 SQLite（`GEO_DISTRIBUTOR_AUDIT_DB`），与业务库分离 |
| 记录范围 | **所有写操作** + **被拒绝的读操作**（401/403/404/429） |
| 不记录 | 成功的 GET（噪声）、原始 API Key、Authorization 头、任何 secret |
| 失败策略 | 审计写入失败**只记warning，绝不阻断业务** |

查询入口：

| 函数 | 用途 | 可见范围 |
|---|---|---|
| `query_audit(tenant_id=...)` | 租户自己的操作记录 | 租户级 |
| `query_unauthenticated_attempts()` | 认证失败/探测痕迹 | **仅内部运维** |

> 认证失败时没有可信 tenant（请求头里的声明可能是伪造的），
> 因此这类记录 tenant_id 为空，只按租户查不到 —— 这是设计而非缺陷。

---

## 9. 限流

**实现**：进程内令牌桶（标准库，零外部依赖）。

> ⚠️ **单进程 / 单实例限定**。
> 多实例部署时每个进程独立计数，实际总额度 = 配置值 × 实例数。
> 届时应升级为 Redis 或网关层限流。Stage 1（5–10 客户）不需要。

配置（每租户维度，按 `X-API-Key` 计数）：

```bash
GEO_DISTRIBUTOR_RATE_LIMIT=120     # 每分钟请求数
GEO_DISTRIBUTOR_RATE_BURST=40     # 突发桶容量
```

超限响应含 `Retry-After` / `X-RateLimit-Limit` / `X-RateLimit-Remaining`。

**伪造 `X-Forwarded-For` 无法绕过** —— 限流按 API Key 计数，与来源 IP 无关。

---

## 10. 部署检查清单

- [ ] TLS 证书已签发，`https://` 可访问
- [ ] HTTP → HTTPS 跳转生效
- [ ] **后端 8765 端口未对公网开放**（`netstat` / 安全组双重确认）
- [ ] `GEO_DISTRIBUTOR_ENV=production`
- [ ] `GEO_DISTRIBUTOR_API_KEYS` 已注入（生产密钥，非 dev/test）
- [ ] `GEO_DISTRIBUTOR_CORS_ORIGINS` = WordPress 域名
- [ ] `GEO_DISTRIBUTOR_DB` / `GEO_DISTRIBUTOR_AUDIT_DB` 指向持久化目录
- [ ] 使用 `./start_api_prod.sh`（非 `start_api.sh`）
- [ ] nginx `log_format` 不含 API Key 头
- [ ] nginx 覆盖（非追加）forwarded headers
- [ ] nginx 限流已配置
- [ ] `/docs` 在应用层与反代层**双关闭**
- [ ] `GET /health` 只返回 `{"status":"ok"}`
- [ ] 审计库可写且有写操作记录
- [ ] WordPress 侧能拿到一个测试密钥完成端到端调用

---

## 11. 明确不在本契约范围内

以下属于后续规模化，**不在当前部署验证范围**：

OAuth server ·完整 IAM · SSO ·密码数据库 · Redis 集群 · Kubernetes ·
分布式追踪 · SIEM · 复杂 RBAC 引擎 · WordPress 插件完整开发 · 计费 · SaaS 自助门户

当前目标只有一个：**让 geo-distributor 具备被 WordPress 安全调用的条件。**
