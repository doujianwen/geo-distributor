# B-2 Authentication｜实施完成报告 + 部署指引

> 状态：**已实施并验证**（`375 passed / 1 skipped / 0 failed`）
> 批次：B-2 Remote/Multi-user Commercial Deployment Authentication
> 上游：B-1 Tenant Isolation = PASS｜B-3 Security Gate = PASS｜B-5 CORS = PASS

---

## 一、交付清单

| # | 交付 | 文件 | 状态 |
|:-:|---|---|:-:|
| 1 | 认证核心 | `api/auth.py` | ✅ 新增 |
| 2 | FastAPI 依赖 | `api/deps.py` | ✅ 新增 |
| 3 | API 文档门控 | `api/app.py` | ✅ 修改 |
| 4 | 6 个 router 接入（30 端点全覆盖） | `api/routers/*.py` | ✅ 修改 |
| 5 | 配置登记 | `.env.example` / `.gitignore` | ✅ 修改 |
| 6 | 认证门禁测试 | `tests/test_auth_b2.py` | ✅ 新增 23 项 |
| 7 | 测试环境统一管理 | `tests/conftest.py` | ✅ 新增 |
| 8 | B-1/B-3 测试适配 | `tests/test_tenant_isolation_b1.py` 等 | ✅ 修改 |
| 9 | 设计文档 | `docs/B2-Authentication-Design.md` | ✅ 新增 |
| 10 | 缺口登记更新 | `docs/B2-Authentication-Gap.md` | ✅ 已解决 |

**端点覆盖**：`30 / 30`（AST 核验，无遗漏）

---

## 二、认证模型（最小可实现）

```
WordPress（不可信外部）──HTTPS──> geo-distributor ──> geo-intent-system（FROZEN）
```

**请求头**：
```
X-API-Key: <共享密钥>          ← 必需，证明身份
X-Tenant-ID: DST-A            ← 可选，仅作声明，会与密钥绑定值交叉校验
```

**核心设计**：**tenant 从密钥反查，而非从header 读取**。
这直接关闭了此前登记的「`X-Tenant-ID` 是声明而非证明」缺口。

**校验链**：
```
1. 缺/错 X-API-Key              → 401
2. 密钥未注册/已吊销            → 401
3. header tenant ≠ 密钥绑定值   → 403
4. 角色无权该操作（写）          → 403
→ 通过：AuthContext(tenant_id, role, user_id, is_hq)
```

**密钥注册表优先级**：
1. 环境变量 `GEO_DISTRIBUTOR_API_KEYS`（生产）
2. `config/api_keys.json`（开发，已 `.gitignore`）
3. 内置开发密钥（**仅** `GEO_DISTRIBUTOR_ENV` ∈ {dev,test,local}）

**格式**：`TENANT_ID:API_KEY:ROLE[,...]`

**注册表缓存**：按配置指纹缓存 —— 配置不变零开销，配置一变自动重载。
（不用模块级布尔缓存：那会让 `verify_api_key` 的引用在模块 reload 后仍指向旧表。）

---

## 三、角色权限矩阵

复用**已存在**的 `models/tenant.py::UserRole`（五角色），未新建角色体系。

| 角色 | tenant 范围 | 写权限 | 跨 tenant |
|---|:-:|:-:|:-:|
| `DISTRIBUTOR_ADMIN` | 本tenant | ✅ | ❌ |
| `DISTRIBUTOR_USER` | 本 tenant | ✅ | ❌ |
| `CLIENT_VIEWER` | 本 tenant | ❌ 仅读 | ❌ |
| `HQ_TECHNICAL` | 全部 | ✅ | ✅ |
| `HQ_MANAGEMENT` | 全部 | ✅ | ✅ |

**落地方式**：`AuthDep`（读） / `WriteDep`（写）两个依赖类型，30 端点按语义分配。

---

## 四、与既有成果的兼容（无回归）

| 既有设计 | 处理 |
|---|---|
| B-1 `_load_project` / `_load_client` 租户校验 | **未改**，仍作为第二道防线 |
| B-1 404 资源去标识化 | **保留** |
| B-3 `find_by_id_scoped` / `find_by_id_unscoped` / `find_by_id` | **未改** |
| B-5 CORS 白名单 | **保留**，WordPress 域名加入 `GEO_DISTRIBUTOR_CORS_ORIGINS` |
| `geoflow` | 未触碰（THIRD_PARTY） |
| `geo-intent-system` | 未触碰（Run#5 Freeze，sha256 一致） |
| `geo-collector` | 未触碰（mtime 未变） |

**关键修正**：端点内`tenant_id = _require_tenant(x_tenant_id)` 改为 `tenant_id = auth.tenant_id`。
前者读的是**原始 header**（B 的密钥无 header 时得到空字符串 → 跳过校验），
后者读**认证上下文**（已是可信值）。这处修正直接堵住一个真实的跨租户读取。

---

## 五、部署指引（远程商业部署前必读）

### 5.1 环境变量

```bash
GEO_DISTRIBUTOR_ENV=production
GEO_DISTRIBUTOR_API_KEYS=DST-001:sk-<random32>:DISTRIBUTOR_ADMIN,DST-002:sk-<random>:DISTRIBUTOR_USER
GEO_DISTRIBUTOR_CORS_ORIGINS=https://your-wordpress-site.com
GEO_DISTRIBUTOR_DB=/var/lib/geo-distributor/geo_distributor.db   # persist 模式
```

生成密钥：
```bash
python -c "import secrets;print(secrets.token_urlsafe(32))"
```

### 5.2 网络边界

| 项 | 要求 | 现状 |
|---|---|---|
| 绑定地址 | `127.0.0.1`（由反向代理对外） | `start_api.sh` 已是 `--host 127.0.0.1` ✅ |
| TLS | **必须**由反向代理终止 | ⚠️ 需部署时配置 |
| `--reload` | **生产必须关闭** | ⚠️ `start_api.sh` 当前带 `--reload`（见 5.4） |

### 5.3 反向代理要求

```nginx
server {
    listen 443 ssl http2;
    server_name api.your-domain.com;

    ssl_certificate     /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;

    location / {
        proxy_pass http://127.0.0.1:8765;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

> **不得**把 `8765` 端口直接暴露到公网 —— 绕过 TLS 即等于明文传输密钥。

### 5.4 生产启动命令

当前 `start_api.sh` 带 `--reload`（开发用），生产应改用：

```bash
.venv/Scripts/python.exe -m uvicorn api.app:app \
    --host 127.0.0.1 --port 8765
# 注意：不带 --reload
```

### 5.5 API 文档

默认**关闭**（404）。排查问题时临时开启：
```bash
GEO_DISTRIBUTOR_EXPOSE_DOCS=1
```

---

## 六、验证证据

### 6.1 双向验证（门禁有效性）

| 注入的漏洞 | 结果 |
|---|---|
| `verify_api_key` 对未知密钥返回有效上下文 | **4 FAILED** |
| `resolve_tenant` 无条件采纳 header 声明 | **2 FAILED** |
| 恢复 | **375 passed** |

> 两个独立攻击面均被门禁抓到，证明测试不是「跑通即通过」。

### 6.2 全量测试

```
375 passed, 1 skipped, 2 warnings in 26.65s
```

对比历史基线：
| 阶段 | 结果 |
|---|---|
| Phase 1-1 Batch 3 后| 352 passed / 1 skipped |
| **本批次后** | **375 passed / 1 skipped** |
| 增量 | +23（`test_auth_b2.py`） |

零删除、零 skip 增长、零 xfail、零弱断言。

### 6.3 契约演进（非弱化测试）

B-2 使部分既有测试的请求形态失效。**修改的是请求凭证，不是断言**：

| 变化 | 说明 |
|---|---|
| B-1/B-3 测试补 `X-API-Key` | 跨租户断言逻辑**完全不变** |
| 「无 tenant header 应拒绝」→ 「回落到密钥 tenant」 | 契约演进：`X-Tenant-ID` 由**必需**变**可选**（因 tenant 已可从密钥反查） |
| 「仅 tenant header 可读数据」→ 「返回 401」 | **断言方向反转**（缺口已关闭） |

---

## 七、遗留事项

| # | 事项 | 级别 | 说明 |
|---|---|:-:|---|
| 1 | TLS 与反向代理配置 | 🔴 部署方责任 | 本仓库不含 nginx/Docker 配置 |
| 2 | `start_api.sh` 的 `--reload` | 🟠 | 生产需关闭，建议改脚本或另建生产分支 |
| 3 | 密钥轮换机制 | 🟡 | 当前支持「从注册表移除即吊销」，无自动轮换 |
| 4 | 同租户内个体区分 | 🟡 | 共享密钥模型下不可区分（Stage 2 需求） |
| 5 | 审计日志落地 | 🟡 | `AuditEntry` 模型已存在，本批次未接入写入 |
| 6 | 限流 / 暴力破解防护 | 🟡 | `compare_digest` 防时序侧信道；无限流（建议反代层加） |
| 7 | WordPress 侧集成代码 | ⚠️ 不在范围 | 本项目内 WP 集成代码为零，需在 WP 侧实现 |

---

## 八、当前系统定位（更新）

> **geo-distributor 现在是一个「tenant 隔离 + 身份认证的 Delivery Engine」。**

| 能力 | 状态 |
|---|---|
| Tenant 隔离（B-1） | ✅ |
| Correlated-ID 防护（B-3） | ✅ |
| CORS 安全（B-5） | ✅ |
| 身份认证（B-2） | ✅ **本批次** |
| 授权（角色） | ✅ 五角色（复用既有模型） |
| 可对外暴露 | ⚠️ **需先完成 §5.2/5.3（TLS + 反代）** |

与商业架构原则的对应：
> **Distributor sells; HQ delivers.**
> `HQ_*` 角色可跨 tenant（履行交付职责）；`DISTRIBUTOR_*` 仅限本租户（守客户边界）。
