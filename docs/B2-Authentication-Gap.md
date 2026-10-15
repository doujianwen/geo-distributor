# B-2｜Authentication Boundary Gap

**登记日期**：2026-10-06
**登记阶段**：Phase 1-1 Batch 3
**状态**：**OPEN / BLOCKED — ARCHITECTURAL DECISION REQUIRED**
**严重度**：P0（阻止系统被称为 production-grade authenticated API）

---

## 一、实测结论：当前系统零认证

### 1.1 认证机制搜索结果

在 `api/` 全目录搜索以下关键字，**零命中**：

```
Depends          HTTPBearer       APIKeyHeader      OAuth2
Authorization    jwt / JWT        session / Session
api_key / apikey Bearer           verify_token      authenticate   identity
```

全局中间件仅 1 个：`CORSMiddleware`（Batch 1A 修复后为白名单模式）。
**没有任何认证中间件、router 级依赖或 token 校验。**

### 1.2 未认证请求的实际行为（实测，非推断）

```
场景 1：零凭证 + 伪造 tenant header 读他人项目
  → 404（tenant 不匹配，B-1 生效）

场景 2：完全不带 header
  → 400 X-Tenant-ID header is required

场景 3：零凭证 + 声称自己是 Tenant A ← 关键
  创建 PRJ-xxxx（DST-AUTH-A）
  GET /projects/PRJ-xxxx  headers: {'X-Tenant-ID': 'DST-AUTH-A'}
  → 200 OK，拿到了 client_id
```

> **场景 3 是本登记的核心**：任何调用方只要知道或猜到 tenant_id，
> 就能以该租户身份读取全部数据。系统**无法证明调用者是谁**。

---

## 二、X-Tenant-ID 的真实角色

| 维度 | 现状 |
|---|---|
| 能做什么 | 表达「本次请求声称属于哪个租户」 |
| 不能做什么 | **不能证明调用者身份** —— 它是自述（claim），不是凭证（credential） |
| 是否可伪造 | ✅ 任何人可任意声称 |
| 命名建议 | 应理解为 `X-Declared-Tenant`，而非 `X-Authenticated-Tenant` |

### 三者的严格区分

```
Authentication  = 你是谁（identity）        ← 当前缺失
Authorization   = 你能做什么（permission）   ← 部分具备（tenant 隔离，B-1 已 PASS）
Tenant Context  = 你声称属于哪个租户        ← 具备（X-Tenant-ID）
```

**当前系统具备 Authorization 与 Tenant Context，但完全不具备 Authentication。**

> 因此**不能**通过把 `X-Tenant-ID` 包装成「认证」来关闭 B-2。
> 本登记拒绝这种做法。

---

## 三、已锁定的现状门禁

`tests/test_correlated_id_attack_b3.py::TestAuthenticationGapDocumented`

这两条测试**断言缺口存在**（通过 = 缺口仍在 = B-2 仍 OPEN）：

| 测试 | 断言内容 |
|---|---|
| `test_no_authentication_scheme_exists_yet` | 零凭证 + 声称 A → 仍返回 200 |
| `test_tenant_header_alone_proves_nothing` | tenant header 可完全伪造 |

> **实施认证后，这两条必须替换为「未认证请求被拒绝」的门禁。**
> 若届时仍通过，说明认证未真正生效。

---

## 四、最小可行认证边界（供架构决策参考，本轮不实施）

### 4.1 问题的真实形状

需要区分三种不同的需求，混在一起做必然过度设计：

| # | 需求 | 现状 | 是否本轮需要 |
|---|---|---|:-:|
| 1 | 防止「知道 tenant_id 就能冒充」 | ❌ 缺失 | ✅ 需要 |
| 2 | 防止「同一 tenant 内不同人互相操作」 | ❌ 缺失 | ⚠️ Stage 2 才需要 |
| 3 | 对外暴露给第三方（Distributor Portal） | — | ❌ 尚不需要 |

### 4.2 最小方案（对应需求 1）

**共享密钥 + tenant 绑定**（不引入用户/会话模型）：

```
请求头：
  X-Tenant-ID: DST-A
  X-API-Key: <该 tenant 的密钥>

服务端：
  api_key → tenant 绑定表校验
  校验通过 → 从密钥反查 tenant，与 X-Tenant-ID 比对
  不一致 → 403
  无密钥 → 401
```

| 优点 | 说明 |
|---|---|
| 无需用户模型 | 不引入 user/session/密码体系 |
| 无需 JWT 库 | 减少依赖面|
| 与现有 `X-Tenant-ID` 契约兼容 | 不破坏 B-1 已实现的 `_require_tenant` |
| 覆盖需求 1 | 解决「声称即可冒充」 |

|缺点 | 说明 |
|---|---|
| 无法区分同 tenant 内个体 | 需求 2 需另加身份层 |
| 密钥分发需人工 | Stage 1（5-10 客户）可接受 |

### 4.3 实施时必须同步改动

| 位置 | 改动 |
|---|---|
| 新增 `geo_distributor/auth.py` | 密钥校验 + tenant 绑定 + FastAPI dependency |
| `api/app.py` | 注册认证中间件或全局 dependency |
| 各router | 加 `Depends(require_tenant)`，并从**校验后的 tenant** 取值，**不再信任 header** |
| `.env.example` | 登记密钥变量（不写settings.yaml，避免入库） |
| `tests/test_correlated_id_attack_b3.py` | Part 3 两条缺口断言改为「未认证被拒」 |
| 新增测试 | 401 无凭证 / 403 密钥与 tenant 不符 / 200 合法凭证 |

### 4.4 实施前必须回答

| # | 问题 |
|---|---|
| Q1 | 密钥存SQLite 还是 `.env`？多租户需要动态增删，还是启动时静态配置？ |
| Q2 | 一个租户一个共享密钥，还是每用户一个？（决定能否支持需求 2） |
| Q3 | 密钥如何分发与轮换？ |
| Q4 | 现有 `X-Tenant-ID` header 是否保留，还是改为从密钥反查（更安全）？ |

---

## 五、当前系统的准确定位

> **geo-distributor 目前是一个「tenant 隔离的内部工具」，不是「authenticated API」。**

| 维度 | 状态 |
|---|---|
| Tenant 隔离（Authorization） | ✅ Batch 2 已 PASS |
| Correlated-ID 防护 | ✅ Batch 3 已 PASS |
| CORS 安全 | ✅ Batch 1 已 PASS |
| 身份认证（Authentication） | ❌ **OPEN** |
| **可对外暴露** | ❌ **否**（部署在 127.0.0.1，不应暴露到公网） |

`start_api.sh` 当前绑定 `127.0.0.1:8765` —— **该绑定本身是最后一道防线**，
在B-2 实施前**不得**改为 `0.0.0.0`。

---

## 六、状态

```
B-2 Status = BLOCKED / ARCHITECTURAL DECISION REQUIRED
Reason     = 需要引入认证体系（密钥/身份），超出「最小修复」范围
Implemented = 无（本轮零认证代码）
Blocked on  = 用户对 §4.2 最小方案的拍板
```

**本轮不实施半成品认证系统。**
