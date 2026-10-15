# B-2 Authentication｜Phase A 现状盘点 + Phase B 架构设计

> 状态：**设计已定，红队自审通过，进入实现**
> 前提：B-1 Tenant Isolation = PASS｜B-3 Security Gate = PASS｜B-5 CORS = PASS
> 目标：让 geo-distributor 安全接受来自 WordPress 的远程、多用户、跨 Tenant 请求
> 原则：**最小安全实现 + 可配置+ 后续可扩展**（不建设完整 SaaS IAM）

---

## Phase A｜现状盘点（READ-ONLY，全部实测）

### A.1 API 层

| 项 | 实测 |
|---|---|
| 端点总数 | **29**（clients 4 / projects 8 / measurements 2 / reports 2 / sync 4 / distribution 9） |
| `Authorization` / `Bearer` / `JWT` / `OAuth` / `APIKey` / `HTTPBearer` | **全部 0 hits** |
| `Depends`（依赖注入） | **0 hits** |
| `middleware` | 2 hits（仅 CORS） |
| `X-Tenant-ID` | 19 hits（Batch 2 引入的 tenant context） |
| `user_id` / `session` / `token` / `secret` | **全部 0 hits** |
| `role` | 1 hit（仅 `user_role="hq_technical"` 硬编码字符串，非权限校验） |
| 异常处理 | `app.py` **无 `exception_handler`** |

### A.2 模型层（**关键发现**）

`geo_distributor/models/tenant.py` **已定义完整的身份模型，但API 层零使用**：

| 模型 | 状态 | 被API 使用 |
|---|---|:-:|
| `Tenant`（`tenant_id` / `status` / `plan` / `is_active()`） | ✅ 已定义 | ❌ |
| `UserRole`（5 角色） | ✅ 已定义 | ❌ |
| `User`（`user_id` / `tenant_id` / `email` / `role` / `is_active`） | ✅ 已定义 | ❌ |
| `AuditEntry`（`action` / `resource_type` / `ip_address` / `reason`） | ✅ 已定义 | ❌ |

`UserRole` 五角色：
```
DISTRIBUTOR_ADMIN  DISTRIBUTOR_USER
HQ_TECHNICAL       HQ_MANAGEMENT
CLIENT_VIEWER
```

> **grep 确认：仅 4 个测试文件引用这些模型，`api/` 零引用。**
> 这意味着**无需新建用户体系**——模型已就位，只需接入。

### A.3 部署层

| 项 | 实测 |
|---|---|
| `start_api.sh` | `uvicorn api.app:app --host 127.0.0.1 --port $PORT --reload` |
| Docker / Dockerfile / docker-compose | **不存在** |
| nginx / 反向代理配置 | **不存在** |
| `.env` | **不存在**（仅 `.env.example`） |
| `GEO_DISTRIBUTOR_DB` | 环境变量（`persist` 模式） |
| 部署文档 | 无独立部署文档 |

> **注意 `--reload` 是开发模式标志，生产必须关闭。**

### A.4 WordPress 集成

| 项 | 实测 |
|---|---|
| 项目内 WP 集成代码 | **0**（仅 ADR-030 中作为 REFERENCE_ONLY 被提及） |
| WP 插件 | 项目内无|

### A.5 商业角色边界（`docs/01` 权威定义）

> **Distributor 卖；HQ 交付。Distributor 管客户关系；HQ 管技术真相。**
> Sampling / Measurement / Diagnosis / Technical Execution 默认集中在 HQ。
> 普通 Distributor 不要求具备技术能力。

**三方角色**：HQ（Intelligence + Technical Delivery）/ Distributor（Market Access / Sales / Client Relationship）/ Client

---

## Phase B｜架构设计

### B.1 安全模型（最小可实现）

**信任边界**：
```
WordPress（不可信外部）→ HTTPS → geo-distributor（内网/受控）→ geo-intent-system（冻结）
```

**核心原则**：
1. **认证（Authentication）** —— WordPress 用**共享密钥**证明「我是一个已注册的集成方」
2. **租户绑定（Tenant Binding）** —— 密钥唯一绑定一个 tenant；**服务端从密钥反查 tenant，不信任请求头**
3. **角色（Role）** —— 复用已存在的 5 个 `UserRole`，**不新建角色体系**
4. **授权（Authorization）** ——沿用 B-1 已实现的 tenant 隔离；HQ 角色可跨 tenant
5. **审计（Audit）** —— 复用已存在的 `AuditEntry`，记录写操作

### B.2 为什么不用 JWT / OAuth

| 方案 | 判断 |
|---|---|
| JWT | 需引入签名库+ 密钥轮换 + 时钟同步。**Stage 1（5-10 客户）无此需求** |
| OAuth2 / IdP | 需外部身份提供商。**超出当前范围** |
| **共享密钥 + tenant 绑定** | ✅ **采纳** —— 无新依赖（`hmac` + `secrets` 标准库），无状态，可配置 |

> **不把 geo-distributor 建成第二套完整 SaaS 用户系统**：WordPress 负责用户身份/登录/角色，
> geo-distributor 只负责**验证集成方 + 绑定租户**。

### B.3 认证方案（可配置 + 可扩展）

```
请求头：
  X-API-Key: <shared secret>        ← 必需，证明身份
  X-Tenant-ID: DST-A                ← 可选，仅作声明，会与密钥绑定值交叉校验
  X-WP-Role: distributor_admin      ← 可选，映射到 UserRole
```

**校验链**（`api/auth.py`）：
```
1. 缺 X-API-Key            → 401
2. 密钥不在注册表           → 401
3. 密钥被吊销/未启用        → 401
4. 请求头 X-Tenant-ID 与密钥绑定值不一致 → 403
5. 密钥绑定角色无权该操作    → 403
→ 通过：产出 AuthContext(tenant_id, user_id, role, is_hq)
```

**关键设计**：**tenant 从密钥反查**，而非从header 读取。
这直接关闭 Phase 0-B 记录的「`X-Tenant-ID` 是声明而非证明」缺口。

### B.4 密钥注册表（可配置，三种来源，按优先级）

| 优先级 | 来源 | 用途 |
|:-:|---|---|
| 1 | 环境变量 `GEO_DISTRIBUTOR_API_KEYS` | 生产：`DST-001:key1:DISTRIBUTOR_ADMIN,DST-002:key2:...` |
| 2 | `config/api_keys.json` | 开发：文件配置，**不入库**（加 `.gitignore`） |
| 3 | 内置开发密钥（仅当 `GEO_DISTRIBUTOR_ENV=dev`） | 本地测试，**生产环境恒不启用** |

> **不用数据库存密钥** —— 避免密钥随备份泄漏、避免 DB 泄漏即全量泄漏。

### B.5 角色权限矩阵（最小版）

| 角色 | tenant 范围 | 可写| 可跨 tenant |
|---|---|:-:|:-:|
| `DISTRIBUTOR_ADMIN` | 本tenant | ✅ | ❌ |
| `DISTRIBUTOR_USER` | 本 tenant | ✅ | ❌ |
| `CLIENT_VIEWER` | 本 tenant | ❌ 仅读 | ❌ |
| `HQ_TECHNICAL` | **全部** | ✅ | ✅ |
| `HQ_MANAGEMENT` | **全部** | ✅ | ✅ |

**读权限**：所有已认证角色
**写权限**：`CLIENT_VIEWER` 禁止
**跨 tenant**：仅 `HQ_*`

### B.6 与既有成果的兼容

| 既有设计 | 本批次处理 |
|---|---|
| `_require_tenant(x_tenant_id)` | **保留不动**，但改为接收 `AuthContext` 派生的 tenant |
| `find_by_id_scoped()` | **不改** |
| `find_by_id_unscoped()` | **不改** |
| 404 去标识化 | **保留** |
| CORS 白名单 | **保留**，WordPress 域名加入 `GEO_DISTRIBUTOR_CORS_ORIGINS` |

---

## Phase C｜红队自审

| # | 攻击 | 防御 | 判定 |
|---|---|---|:-:|
| R-1 | 无密钥直接调API | 401 | ✅ |
| R-2 | 用A 的密钥 + B 的 tenant header | 403（交叉校验不一致） | ✅ |
| R-3 | 用A 的密钥读B 的资源 | 404/403（tenant 从密钥反查） | ✅ |
| R-4 | 密钥泄漏后长期可用 | 支持吊销（注册表移除） | ✅ |
| R-5 | `CLIENT_VIEWER` 尝试写| 403（写权限矩阵） | ✅ |
| R-6 | `DISTRIBUTOR_*` 尝试跨 tenant | 403（仅 HQ 可跨） | ✅ |
| R-7 | 伪装 `X-WP-Role: hq_management` | 403（角色取自密钥，不信任header） | ✅ |
| R-8 | 生产环境误启用内置开发密钥 | `GEO_DISTRIBUTOR_ENV != dev` 时恒不加载 | ✅ |
| R-9 | 密钥进git | `config/api_keys.json` 加 `.gitignore` + 环境变量优先 | ✅ |
| R-10 | WordPress 侧未启用 HTTPS | **部署边界**：密钥仅经 HTTPS 传输，由反向代理保证 | ⚠️ 文档化 |
| R-11 | 时钟偏移导致 JWT 失效 | **不适用**（无状态密钥，无过期） | ✅ |
| R-12 | 暴力枚举密钥 | 标准库 `secrets.compare_digest` 常数时间比较 | ✅ |
| R-13 | 审计日志缺失 | 复用 `AuditEntry`，写操作必记 | ✅ |
| R-14 | B-1 回归 | 新认证层在 tenant 校验**之前**，不改变 tenant 语义 | ✅ 需回归测试 |

**红队结论**：无阻断项。R-10 为部署责任，文档化处理。

---

## Phase D｜实施范围

| # | 交付 | 文件 |
|---|---|---|
| 1 | 认证核心 | `api/auth.py`（新） |
| 2 | FastAPI 依赖 | `api/deps.py`（新） |
| 3 | 应用接入 | `api/app.py`（中间件 + 公开路径豁免） |
| 4 | 6 个 router 接入 | clients / projects / measurements / reports / sync / distribution |
| 5 | 配置 | `.env.example` / `.gitignore` |
| 6 | 测试 | `tests/test_auth_b2.py`（新） |
| 7 | 文档 | 本文件 + `docs/B2-Authentication-Gap.md` 更新 |

**不做**：不改 B-1 逻辑、不改仓储层、不建 Docker、不建 nginx 配置（文档化指引即可）、不碰geo-intent-system / geo-collector。
