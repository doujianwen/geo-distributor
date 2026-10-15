# SECURITY CONTRACT

> geo-distributor 的安全属性、可观察证据与验证方式。
> 本文只写**已被测试证明**的行为，不写意图或计划。

---

## 1. 信任边界

```
WordPress（不可信外部，持有用户身份）
   │  HTTPS
   ▼
Reverse Proxy（TLS 终止 · IP 限流 · 清洗 forwarded headers）
   │  HTTP :8765（回环）
   ▼
geo-distributor（认证 · 授权 · 租户隔离 · 应用限流 · 审计）
   │
   ▼
geo-intent-system（Run#5 Freeze —— 不得修改）
```

**geo-distributor 不是第二套用户系统**。WordPress 负责用户身份/登录/门户；
geo-distributor 只负责：验证调用方是已注册集成方 + 绑定租户+ 授权 + 留痕。

---

## 2. 认证

### 机制

共享密钥（`X-API-Key`），无状态，无过期。

**为什么不用 JWT / OAuth**：Stage 1（5–10 客户）无签发、轮换、时钟同步需求。
共享密钥：零新依赖（标准库 `secrets`）、可配置、可吊销。
未来若需更细身份体系，可在**不改变调用契约**的前提下把 `verify_api_key`
的内部实现替换为 JWT 校验。

### 核心不变量

| 不变量 | 说明 |
|---|---|
| **tenant 从密钥反查** | 不从 `X-Tenant-ID` 读取。声明与绑定冲突 → 403 |
| header 缺失回落 | 未声明 tenant 时使用密钥绑定值，而非拒绝 |
| 无默认身份 | 认证失败返回 `None`，**绝不**返回兜底身份 |
| 生产无内置密钥 | 非 `dev/test/local` 时不加载任何内置 key |
| 常数时间比较 | `secrets.compare_digest`，防时序侧信道 |
| 401 文案一致 | 不区分「密钥不存在」与「密钥错误」，防信息泄漏 |

### 三者区分

| 概念 | 含义 | 本系统状态 |
|---|---|:-:|
| Authentication | 你是谁 | ✅ 共享密钥 |
| Authorization | 你能做什么 | ✅ 5 角色矩阵 |
| Tenant Context | 你声称属于谁 | ✅ 可选声明，被交叉校验 |

> `X-Tenant-ID` 是**声明**（claim），`X-API-Key` 才是**凭证**（credential）。
> 把前者当认证是本项目早期已修正的错误（B-2 缺口登记）。

---

## 3. 授权与租户隔离

### 角色矩阵

| 角色 | tenant 范围 | 写| 跨 tenant |
|---|:-:|:-:|:-:|
| `DISTRIBUTOR_ADMIN` | 本 tenant | ✅ | ❌ |
| `DISTRIBUTOR_USER` | 本 tenant | ✅ | ❌ |
| `CLIENT_VIEWER` | 本 tenant | ❌ | ❌ |
| `HQ_TECHNICAL` | 全部 | ✅ | ✅ |
| `HQ_MANAGEMENT` | 全部 | ✅ | ✅ |

角色**只来自密钥绑定**，忽略 `X-WP-Role` 之类的请求头声明 ——
否则任何人都能自称HQ。

### 租户隔离（B-1）

- 30/30 端点接入认证
- tenant 由 `auth.tenant_id` 提供，**不是** 原始 header
- 跨租户访问 → 403（声明冲突）或 404（资源不可见）
- 404 响应**不回显resource_id**（防资源存在性探测）
- 仓储层 `find_by_id_scoped()` 强制 tenant 作用域

> **曾经踩过的坑**：B-2 实施后，端点内仍写 `tenant_id = _require_tenant(header)`。
> B 的密钥不带 header 时得到空字符串 → 仓储层跳过校验 → **跨租户读取成功**。
> 教训：引入安全层后必须回头审计旧代码的**数据来源**，而不只是加一层。

---

## 4. 限流

进程内令牌桶，按 `X-API-Key` 计数。

| 属性 | 值 |
|---|---|
| 默认速率 | 120 /分钟 /租户 |
| 突发桶| 40 |
| 超限响应 | 429 + `Retry-After` + `X-RateLimit-*` |
| 429 体泄露 | 无（无堆栈/路径/密钥有效性/租户存在性） |
| 伪造 XFF 绕过 | ❌ 不可能（按 Key 不按 IP） |
| 跨租户干扰 | ❌ 不会（每Key 独立桶） |

> ⚠️ **单进程 / 单实例限定**。多实例时总额度 = 配置 × 实例数。
> 届时升级为 Redis 或网关限流。

---

## 5. 审计

| 属性 | 值 |
|---|---|
| 存储 | 独立 SQLite，与业务库分离 |
| 记录范围 | 所有写操作 + 被拒绝的读操作（401/403/404/429） |
| 不记录 | 成功 GET、原始 API Key、Authorization 头、任何 secret |
| 超长值 | 截断 2000 字符 |
| 失败策略 | 只记 warning，**绝不阻断业务** |

### 记录的字段

`timestamp` · `actor(user_id)` · `role` · `tenant_id` · `action` ·
`resource_type` · `resource_id` · `outcome` · `ip_address` · `request_id` · `reason`

### 查询入口的隔离

| 入口 | 隔离 |
|---|---|
| `query_audit(tenant_id=X)` | 强制按 tenant 过滤；`None` 返回**空**而非全部 |
| `query_unauthenticated_attempts()` | 仅内部运维；租户不应看到他人失败尝试 |

### 认证失败为何查不到

认证失败时没有可信 tenant（请求头声明可能是伪造的），这类记录 `tenant_id` 为空。
**这是设计而非缺陷** —— 否则会把伪造的 tenant 值当成可信身份存下来。

---

## 6. 错误脱敏

| 状态码 | 约束 |
|:-:|---|
| 401 | 文案统一，不区分密钥/租户/用户是否存在 |
| 403 | 不回显受害方租户 |
| 404 | 不回显 resource_id |
| 429 | 只说明限流 |
| 500 | 无 stack trace / 文件路径 / SQL / 异常类型名 / 对象 repr |

安全响应头（应用层 + 反代层双份）：HSTS / `nosniff` / `DENY` / `no-referrer` / 严 CSP。
应用层同时移除 `Server` 与 `X-Powered-By`。

---

## 7. 公开面

| 端点 | 认证 | 说明 |
|---|:-:|---|
| `/health` | ❌ | **仅** `{"status": "ok"}`。已移除 `db_path` / 内部状态 |
| `/docs` `/openapi.json` `/redoc` | ❌ 默认 404 | 需显式开启**且**反代放行 |
| 其余 30 个 | ✅ | 全部需认证 |

---

## 8. 安全测试证据

| 套件 | 项数 | 覆盖 |
|---|---:|---|
| `test_auth_b2.py` | 23 | 认证/绑定/角色/配置/吊销 |
| `test_tenant_isolation_b1.py` | 23 | 跨租户读取/修改/删除 |
| `test_correlated_id_attack_b3.py` | 9 | 关联 ID 攻击 + 假门禁修正 |
| `test_audit_ratelimit.py` | 17 | 审计隔离 + 令牌桶 + 429 |
| `test_cors_config.py` | 11 | CORS 白名单 |
| `test_remote_deployment_redteam.py` | 27 | RT-01~RT-10 + 错误脱敏 |
| `test_redteam_tenant_isolation.py` | 7 | 仓储层隔离 |

### 反向验证（故意破坏 → 必失败）

| 注入缺陷 | 结果 |
|---|---|
| 认证对未知密钥返回兜底身份 | **10 security tests FAILED** |
| 允许 header 覆盖认证 tenant | **2 cross-tenant tests FAILED** |
| 关闭限流 enforcement | **6 rate-limit tests FAILED** |

> 每次注入后均精确编辑恢复（**未使用 `git checkout`**，避免回退未提交工作）。

---

## 9. 已知限制

| # | 限制 | 影响 | 何时处理 |
|:-:|---|---|---|
| 1 | 限流单进程 | 多实例时额度叠加 | 规模化时 |
| 2 | 共享密钥无法区分同租户内个体 | Stage 2 需求 | 引入用户模型时 |
| 3 | 无自动密钥轮换 | 支持手动移除即吊销 | 规模化时 |
| 4 | 审计未接入读取 API | 需直接查库或运维脚本 | 需要客户端查审计时 |
| 5 | 无分布式追踪 | 单实例够用 | 规模化时 |

---

## 10. 不可回退的约束

以下为**架构不变量**，任何后续改动不得破坏：

1. `tenant_id` 必须来自 `auth.tenant_id`，不得回退到读 `X-Tenant-ID`
2. 认证失败必须返回 `None`，不得返回任何默认身份
3. 404 不得回显 resource_id
4. 生产环境不得加载内置开发密钥
5. 审计查询不传 tenant 必须返回空，不得返回全部
6. `query_audit` 的 SQL 必须以 `WHERE tenant_id = ?` 开头
7. 限流必须按 API Key 计数，不得改为按 IP（会引入 XFF 伪造风险）
8. 生产启动脚本不得含 `--reload`
