# GEO Distributor System V2 — Code-Level Red Team Audit

**Project**: `E:\GEO项目\技术层\geo-distributor\`
**Date**: 2026-09-17
**Auditor**: Agnes (Red Team Lens)
**Constraint**: Read-only audit. No production code modified.
**Tech Stack**: Python 3.13, dataclasses, in-memory repos, no ORM, no Web Framework

---

## 1. Executive Summary

---

## 2. Current Architecture

### 2.1 技术栈清单

| 层 | 技术 | 状态 |
|----|------|------|
| Language | Python 3.13 | ✅ |
| Package Mgmt | requirements.txt (playwright, pyyaml, httpx) | ✅ |
| Test | pytest-9.1.1, pytest-asyncio, anyio | ✅ 249 tests pass |
| Models | dataclasses + Enum (no ORM) | ✅ |
| Persistence | InMemoryRepository (dict-based) | ⚠️ 重启丢失 |
| Web API | **NONE**（no FastAPI/Flask/Starlette） | ❌ |
| CLI | main.py (argparse: demo/health/status/collect/report) | partial |
| Adapter Layer | BaseAdapter (ABC) → ElmoAdapter, GeoCollectorAdapter, MockMeasurementAdapter, OpenGeoAdapter | ✅ |
| Compatibility | PlatformObservation + map_geo_collector_observation / map_elmo_to_platform | ✅ |
| Guards | IdempotencyGuard, StateTransitionGuard | ✅ |
| Services | Intake/Scoping/Project/Delivery/Distribution/InterventionLoop/EvidenceLibrary/MeasurementAnalysis | ✅（骨架） |

### 2.2 目录结构（精简）

```
geo-distributor/
├── config/settings.yaml          # brand "Hydroviv", elmo api_key 明文
├── config/engines.yaml           # chatgpt/perplexity/gemini/google_ai selectors
├── main.py                       # CLI entry: demo/health/status/(collect+report stubs)
├── geo_distributor/
│   ├── adapters/
│   │   ├── base.py               # BaseAdapter ABC + ElmoAdapter + GeoCollectorAdapter
│   │   ├── elmo_client.py        # Elmo REST client (httpx)
│   │   ├── mock.py               # MockMeasurementAdapter + MockMeasurementService
│   │   └── opengeo.py            # OpenGeoAdapter (read from pre-collected JSON store)
│   ├── compatibility/
│   │   ├── base.py               # PlatformObservation dataclass
│   │   ├── elmo.py               # map_elmo_to_platform
│   │   └── opengeo.py
│   ├── models/
│   │   ├── tenant.py             # Tenant, User, UserRole, AuditEntry
│   │   ├── request.py            # ServiceRequest, BusinessContext, RequestStatus
│   │   ├── scope.py              # TechnicalScope, ScopeChangeType
│   │   ├── project.py            # Project, ProjectStatus, BlockedReason
│   │   ├── work_item.py          # WorkItem, WorkItemType, WorkItemStatus
│   │   ├── geo_core.py           # Evidence, Report, ReportVersion, Diagnosis, Measurement, Provider
│   │   ├── evidence.py           # ⚠️ DUPLICATE Evidence class
│   │   └── audit.py
│   ├── repositories/
│   │   ├── base.py               # InMemoryRepository (dict store)
│   │   ├── client_repo.py
│   │   ├── project_repo.py       # tenant_id filtered
│   │   ├── request_repo.py
│   │   └── work_item_repo.py
│   └── services/
│       ├── intake.py             # IntakeService (clarification loop)
│       ├── scoping.py            # ScopingService (versioned scope)
│       ├── project_service.py    # ProjectService (create from approved scope)
│       ├── delivery.py           # ReportService + DeliveryService
│       ├── distribution.py       # DistributionService (stub: 8 lines)
│       ├── intervention_loop.py  # InterventionExecution, BaselineMetrics, DeltaCalculator, ReMeasurementService
│       ├── measurement_analysis.py # aggregate_metrics
│       └── evidence_library.py   # EvidenceLibraryService
├── tests/                        # 27 files, 244+ test funcs, 249 pass, 1 skip
├── scripts/                      # e2e_test.py, e2e_explore.py, test_api.py, validation_window.py
├── sprint4-lab/cases/
│   ├── bookconv/baseline/        # observations.json (15 obs), query_set.json (40 queries), metrics.json
│   └── tjostrichink/baseline/    # observations.json (46 obs)
└── docs/FINAL_CODE_LEVEL_RED_TEAM_REPORT.md  # prior report claiming "156/156 PASS"
```

### 2.3 关键事实

- **geo-collector.db EXISTS** at `E:/GEO项目/技术层/geo-collector/geo_collector.db`（上游数据源存在）
- **Elmo API key IS HARDCODED** in config/settings.yaml:68 (`api_key: "5vGAUQo58wjhLiXp43bV3lvgIhF/AnIk6WxtREjevn4="`)
- **Brand is "Hydroviv"**（water filter brand, not BookConv or TJOstrichInk）
- **No web framework** anywhere in the codebase — `grep fastapi/flask/starlette/uvicorn/router` returns zero hits in geo_distributor/
- **Service Stage 完全不存在** — grep "ServiceStage|service_stage" 返回零结果
- **四阶段（网站诊断/竞品分析/优化提升/效果监控）完全不存在** — 仅在 README 文档中提到，代码中无任何对应实现

---

## 3. Object Reality Matrix

基于 V2 核心对象清单：Distributor / Client / Request / Scope / Project / Measurement / Evidence / Finding / QA / Report

| 对象 | 状态 | 文件位置 | 数据模型 | 持久化 | API | 测试 | 备注 |
|------|------|----------|----------|--------|-----|------|------|
| **Distributor** | PARTIAL | models/tenant.py:23 Tenant | tenant_id, name, status | InMemoryRepository | ❌ 无 | test_tenant_isolation_final.py | 只有 Tenant 概念，无 Distributor 角色边界；业务层通过 tenant_id 隔离 |
| **Client** | ABSENT | 无 | 无 | 无 | 无 | 无 | 系统中有 `client_id` 字段（project.py:57）但无独立 Client 模型。client_repo.py 存在但无对应的 Client 数据类定义 |
| **Request** | REAL | models/request.py:70 ServiceRequest, request.py:12 RequestStatus | request_id, tenant_id, client_id, status, business_context, clarification_requests | request_repo (InMemory) | ❌ | test_sprint0_contract_skeleton.py | 完整状态机（INTAKE → SCOPE_PENDING_APPROVAL → APPROVED） |
| **Scope** | REAL | models/scope.py:22 TechnicalScope | scope_id, request_id, version, change_type, data | 无独立 repo（可能内嵌在 ProjectService） | ❌ | test_sprint0_contract_skeleton.py | 版本化技术范围，通过 approve_scope() 流转 |
| **Project** | REAL | models/project.py:49 Project | project_id, tenant_id, client_id, request_id, scope_id, status, work_items | project_repo (InMemory, tenant filtered) | ❌ | test_sprint0_contract_skeleton.py, test_e2e_full_pipeline.py | Project 是真正的业务容器，含 WorkItem 引用、BlockedReason。ProjectStatus 有完整状态转换表 |
| **Measurement** | PARTIAL | models/geo_core.py:210 Measurement | measurement_id, observation_id, geo_score, brand_position, etc. | 无独立 repo（通过 observation_id 间接关联） | ❌ | test_models_v03.py | 有数据模型但无服务层调用；Observation 由 Adapter 产出 |
| **Evidence** | CONFLICT | models/evidence.py:17 Evidence vs geo_core.py:26 Evidence | 两定义字段不同！ | 无独立 repo | 无 | test_evidence.py | **P2 缺陷**：两个 Evidence 类字段不一致，造成混淆 |
| **Finding** | ABSENT | 无 | 无 | 无 | 无 | 无 | 系统中没有 Finding 模型；MockMeasurementService 内部生成 dict 但不持久化 |
| **QA** | PARTIAL | services/delivery.py:18 QAResult | passed, issues, warnings | 内存列表 | 内嵌在 DeliveryService | test_e2e_full_pipeline.py | QA 是轻量检查（5项），无独立 QA 对象 |
| **Report** | REAL | models/geo_core.py:74 Report | report_id, project_id, type, versions[] | ReportService._reports (内存 dict) | ❌ | test_e2e_full_pipeline.py, test_sprint4_real_adapter.py | 有版本管理、is_client_safe、内容过滤 |

**关键结论**：
- ✅ Project 是真正的业务容器（满足 V2 要求）
- ❌ Client 对象缺失 — `client_id` 只是字符串字段，无独立生命周期
- ❌ Finding 对象缺失 — 这是 V2 诊断→机会→行动链条的关键断裂点
- ⚠️ Evidence 存在双定义冲突（models/evidence.py vs models/geo_core.py）
- ⚠️ QA 是过程性检查而非独立对象

---

## 4. V2 Four-Stage Mapping

V2 要求的四阶段：网站诊断 / 竞品分析 / 优化提升 / 效果监控

| 客户阶段 | 当前代码对象 | 当前 API | 当前 UI | 当前数据 | 测试 | 状态 |
| ---- | ------ | ------ | ----- | ---- | -- | ------------------- |
| **网站诊断** | 部分 — Measurement + Evidence + Diagnosis 模型存在，但无独立"诊断服务" | ❌ 无 | ❌ 无 | ⚠️ OpenGeoAdapter 读已落盘 JSON | ✅ test_sprint4_real_adapter.py | **PARTIAL**（有模型无服务） |
| **竞品分析** | ❌ 无 | ❌ 无 | ❌ 无 | ❌ 无 | ❌ 无 | **ABSENT** |
| **优化提升** | 部分 — InterventionRecommendation (intervention_loop.py:42) 存在，但无 Finding 关联 | ❌ 无 | ❌ 无 | ⚠️ 干预建议是文档概念 | ✅ test_intervention_loop.py | **CONCEPT ONLY** |
| **效果监控** | 部分 — ReMeasurementService (intervention_loop.py:157) 存在，但依赖 adapter 采集 | ❌ 无 | ❌ 无 | ⚠️ 仅计算 Delta，无实时管线 | ✅ test_sprint4_remearsurement_harness.py | **PARTIAL**（有计算无管线） |

**关键发现**：
- **Service Stage 字段完全不存在** — Project 模型中无 service_stage 字段
- **四阶段是纯文档概念** — 代码中无任何对应实现
- **竞品分析完全缺失** — 无 competitor 模型、无对比逻辑
- **优化提升只是干预建议文档** — 无实际执行机制

---

## 5. Three-System Boundary Audit

### 5.1 AI Visibility Diagnostic System（AI Visibility 诊断系统）

**当前代码边界**：
- ✅ PlatformObservation 契约（compatibility/base.py）
- ✅ Adapter 层（ElmoAdapter, GeoCollectorAdapter, MockMeasurementAdapter, OpenGeoAdapter）
- ✅ Measurement 模型（models/geo_core.py:210）
- ✅ Evidence 模型（models/evidence.py:17, models/geo_core.py:26 — **冲突！**）
- ❌ **Finding 模型缺失** — 这是诊断→机会链条的关键断裂点
- ❌ **Diagnosis 服务缺失** — 只有模型，无服务层实现

**结论**：诊断系统的**数据契约已定义**，但**执行链路不完整**（缺 Finding、缺诊断服务）。

### 5.2 GEO 内容运营系统

**当前代码边界**：
- ❌ **完全不存在** — 代码库中无任何内容生产/发布/迭代相关组件
- ⚠️ InterventionRecommendation 是"建议"，不是"内容运营"
- ⚠️ 干预建议与内容生产之间没有接口

**结论**：GEO 内容运营系统是**纯文档概念**，代码中零实现。

### 5.3 GEO Distributor System（GEO 分销系统）

**当前代码边界**：
- ✅ Tenant/User/RBAC（models/tenant.py）
- ✅ ServiceRequest 状态机（models/request.py）
- ✅ TechnicalScope 版本化（models/scope.py）
- ✅ Project 业务容器（models/project.py）
- ✅ Report 版本管理（models/geo_core.py:74）
- ✅ 租户隔离（repositories/* 都有 tenant_id 过滤）
- ⚠️ DistributionService 是 stub（services/distribution.py:8，仅 8 行）

**结论**：分销系统的**商业交付骨架完整**，但**测量链路未接入**。

### 5.4 三系统边界总结

| 系统 | 代码实现 | 边界清晰度 |
|------|----------|------------|
| AI Visibility Diagnostic | PARTIAL（有契约无执行） | ⚠️ 模糊 — Finding 缺失导致无法输出 |
| GEO Content Operating | ABSENT | ❌ 无边界 |
| GEO Distributor | REAL（骨架完整） | ✅ 清晰 |

**三系统耦合问题**：
- DistributionService (services/distribution.py) 完全未实现
- 没有定义三个系统之间的接口契约
- Sprint4 的 OpenGeoAdapter 直接读取 JSON 文件，绕过了真实的诊断系统

---

## 6. Elmo Adapter Audit

### 6.1 完整调用链追踪

```
main.py:38-40 → ElmoAdapter() / GeoCollectorAdapter()
    ↓
adapters/base.py:46-259 → ElmoAdapter.collect_prompt()
    ↓
adapters/elmo_client.py:31-174 → ElmoClient
    ↓
httpx.AsyncClient() → GET/POST to Elmo REST API
```

**关键发现**：
1. **ElmoAdapter 是真实 HTTP 客户端**（elmo_client.py:65-114 使用 httpx）
2. **但生产环境未配置** — settings.yaml 中 elmo.enabled: true 但 base_url: "http://localhost:1515"
3. **API key 明文硬编码** — settings.yaml:68 `api_key: "5vGAUQo58wjhLiXp43bV3lvgIhF/AnIk6WxtREjevn4="`
4. **错误处理完善** — elmo_client.py:98-114 有重试、超时、401/403 处理

### 6.2 数据流向分析

```
ElmoAdapter.collect_prompt()
    ↓
ElmoClient.get_prompt(prompt_id) → GET /api/v1/prompts/{id}
    ↓
ElmoClient.list_runs(prompt_id) → GET /api/v1/prompts/{id}/runs
    ↓
ElmoClient.get_brand(brand_id) → GET /api/v1/brands/{brandId}
    ↓
compatibility/elmo.py:map_elmo_to_platform()
    ↓
PlatformObservation (统一输出)
```

**数据完整性检查**：
- ✅ prompt_id, prompt_text 保留
- ✅ brand_name, brand_domains 保留
- ✅ citations 保留
- ⚠️ run_id 在 raw_metadata 中，但不在 PlatformObservation 顶层字段（可能丢失）
- ⚠️ timestamp 来自 Elmo API，非采集时刻

### 6.3 数据来源分类

| 数据源 | 真实性 | 文件位置 | 说明 |
|--------|--------|----------|------|
| MockMeasurementAdapter | ❌ MOCK | adapters/mock.py:38-190 | 预定义 3 条 mock 响应，按 hash(query) 选择 |
| MockMeasurementService | ❌ MOCK | adapters/mock.py:192-276 | 完整 Measurement→Evidence→Finding 链路，但全是模拟数据 |
| ElmoAdapter | ⚠️ 骨架 | adapters/base.py:46-259 | HTTP 客户端存在，但需真实 Elmo 实例 |
| GeoCollectorAdapter | ⚠️ 依赖外部 | adapters/base.py:270-345 | 依赖 geo-collector 项目，无自动触发路径 |
| OpenGeoAdapter | ✅ 真实数据 | adapters/opengeo.py | 读取已落盘 JSON（sprint4-lab/cases/*） |

### 6.4 Mock 数据清单（⚠️ 高风险）

**adapters/mock.py:48-73** — 3 条预定义 MockRawResponse：
```python
MOCK_RESPONSES = [
    MockRawResponse(
        query="best industrial sensors manufacturer",
        answer_text="Top manufacturers include Acme Corp...",
        brand_in_answer=True,
        target_source_rank=1,
    ),
    # ... 共 3 条
]
```

**风险**：MockMeasurementService 是独立类（mock.py:192），**未被 services/ 层调用**。但 E2E 测试直接实例化它（test_e2e_full_pipeline.py:77-79），导致测试通过但**不验证真实链路**。

---

## 7. Data Model Audit

### 7.1 核心模型清单

| 模型 | 文件 | 字段数 | 状态机 | 备注 |
|------|------|--------|--------|------|
| Tenant | models/tenant.py:23 | 4 | TenantStatus (ACTIVE/INACTIVE/TRIAL) | 无独立 repo |
| User | models/tenant.py:50 | 5 | UserRole (DISTRIBUTOR/CLIENT/ADMIN/OPS) | 无独立 repo |
| ServiceRequest | models/request.py:70 | 8 | RequestStatus (INTAKE/SCOPE_PENDING/...) | ✅ 完整 |
| TechnicalScope | models/scope.py:22 | 5 | ScopeChangeType | 无独立 repo |
| Project | models/project.py:49 | 15 | ProjectStatus (10 状态) | ✅ 完整，含状态转换表 |
| WorkItem | models/work_item.py:40 | 8 | WorkItemStatus | ✅ 完整 |
| Evidence | models/evidence.py:17 | 8 | EvidenceLevel (E0-E4) | ⚠️ 与 geo_core.py 冲突 |
| Evidence | models/geo_core.py:26 | 6 | EvidenceLevel (E0-E4) | ⚠️ 与 evidence.py 冲突 |
| Report | models/geo_core.py:74 | 6 | ReportType (TECHNICAL/CLIENT) | ✅ 完整，含版本管理 |
| Measurement | models/geo_core.py:210 | 10 | 无 | 无独立 repo |
| Diagnosis | models/geo_core.py:234 | 6 | 无 | 无独立 repo |

### 7.2 关键问题

#### P1: Evidence 类冲突
- `models/evidence.py:17` 定义 Evidence（8 字段）
- `models/geo_core.py:26` 定义 Evidence（6 字段）
- **两个类同名但字段不同**，造成 import 混乱
- 建议：统一到一个文件，删除重复定义

#### P2: Client 模型缺失
- `repositories/client_repo.py` 存在，但**无 Client 数据类定义**
- `Project.client_id` 只是字符串字段
- **无法独立管理 Client 生命周期**

#### P3: Finding 模型完全缺失
- V2 要求：Finding 是 Measurement → Opportunity → Action 链条的关键节点
- 当前代码：**零 Finding 模型**
- MockMeasurementService 内部生成 dict 但不持久化
- **这是诊断系统最大的缺口**

#### P4: 持久化层局限
- 所有 Repository 使用 InMemoryRepository（dict 存储）
- **重启后数据丢失**
- 无 SQLAlchemy/SQLModel/Prisma 等 ORM
- 无数据库迁移（migrations/）
- **不适合生产环境**

---

## 8. API Contract Audit

### 8.1 API 现状

| API | 输入 | 输出 | 数据来源 | 是否真实 | 风险 |
|-----|------|------|----------|----------|------|
| main.py --mode health | adapter_name | status OK/DOWN | Adapter.health_check() | ⚠️ Mock 始终返回 True | 误导性健康检查 |
| main.py --mode status | 无 | DB stats | geo_collector.db | ✅ 真实 | 仅只读统计 |
| main.py --mode collect | project_config | **NOT IMPLEMENTED** | - | ❌ Stub | P0 阻塞 |
| main.py --mode report | project_id | **NOT IMPLEMENTED** | - | ❌ Stub | P0 阻塞 |
| main.py --mode demo | 无 | 静态打印 | 硬编码字符串 | ❌ 演示 | 误导成熟度评估 |

**关键发现**：
- **无 HTTP API** — 这是 CLI 工具，不是 Web 服务
- **collect/report 模式是 stub** — main.py:136 `print(f"[WARN] {args.mode} mode not yet implemented")`
- **demo 模式打印"全部 OK"** — 但实际能力远未达到

### 8.2 服务层接口

| 服务 | 方法 | 真实调用链 | 测试覆盖 |
|------|------|------------|----------|
| IntakeService.review() | ✅ 真实 | BusinessContext → ClarificationRequest | ✅ test_sprint0_contract_skeleton.py |
| ScopingService.create_scope() | ✅ 真实 | ServiceRequest → TechnicalScope | ✅ test_sprint0_contract_skeleton.py |
| ProjectService.submit_request() | ✅ 真实 | Request → Scope → Project | ✅ test_e2e_full_pipeline.py |
| ProjectService.approve_scope() | ✅ 真实 | Scope → Project (状态转换) | ✅ test_sprint0_contract_skeleton.py |
| DeliveryService.execute_delivery() | ✅ 真实 | Observations → Report → QA | ✅ test_e2e_full_pipeline.py |
| DistributionService | ❌ STUB | 8 行代码，无实现 | ❌ 无测试 |
| ReMeasurementService.remeasure() | ✅ 真实 | Adapter → BaselineMetrics | ✅ test_sprint4_remearsurement_harness.py |

---

## 9. Auth / Tenant / Role Audit

### 9.1 租户隔离验证

**test_security_red_team.py** 和 **test_tenant_isolation_final.py** 覆盖了 8 种攻击向量：

| 攻击向量 | 测试 | 结果 |
|----------|------|------|
| A: 直接 ID 查询 | test_request_by_b_id_from_a_context | ✅ 抛出 PermissionError |
| B: 更新越权 | test_update_project_cross_tenant | ✅ 抛出 PermissionError |
| C: 删除越权 | test_delete_request_cross_tenant | ✅ 抛出 PermissionError |
| D: 列表越权 | test_list_requests_cross_tenant | ✅ 只返回本租户数据 |
| E: 报告越权 | test_get_report_cross_tenant | ✅ 抛出 PermissionError |
| F: 嵌套对象越权 | test_nested_entity_isolation | ✅ 阻止访问 |
| G: 缓存污染 | test_cache_isolation | ✅ 隔离缓存 |
| H: 并发越权 | test_concurrent_access | ✅ 串行安全 |

**结论**：租户隔离机制**设计良好**，InMemoryRepository 的 tenant_id 过滤有效。

### 9.2 角色权限（RBAC）

**test_rbac_final.py** 覆盖了 6 种角色：

| 角色 | 能看什么 | 能改什么 | 能创建什么 |
|------|----------|----------|------------|
| DISTRIBUTOR | 自己的 Client/Project | 自己的 Request | Client, Request |
| CLIENT | 自己的 Project | 自己的 WorkItem | - |
| ADMIN | 全部 | 全部 | 全部 |
| OPS/TECHNICAL | 全部（只读） | 执行 WorkItem | - |

**测试覆盖**：249/250 tests pass，1 skipped（test_sprint4_real_adapter.py:184 跳过）

### 9.3 安全风险

| 风险项 | 存在 | 严重程度 | 说明 |
|--------|------|----------|------|
| API Key 硬编码 | ✅ | **P1** | settings.yaml:68 明文存储 Elmo API Key |
| 无 HTTPS | ✅ | P2 | 无 Web API，但未来接入需注意 |
| 无审计日志表 | ✅ | P2 | AuditEntry 有模型，但无独立查询接口 |
| 内存存储 | ✅ | P1 | 重启丢失，不适合生产 |
| 无 Rate Limiting | ✅ | P2 | 无请求频率限制 |

---

## 10. Test Audit

### 10.1 测试统计

| 指标 | 值 |
|------|-----|
| 测试文件数 | 27 |
| 测试函数数 | 244+ |
| 通过 | 249 |
| 失败 | 0 |
| 跳过 | 1 |
| 运行时间 | 13.90s |

**命令**：`.venv/Scripts/python.exe -m pytest tests/ -v -q`

### 10.2 测试质量分析

#### ✅ 高质量的测试
- **test_tenant_isolation_final.py** — 8 种攻击向量全覆盖，真实的越权检查
- **test_rbac_final.py** — 角色权限验证，覆盖 6 种角色
- **test_sprint0_contract_skeleton.py** — 26 个测试覆盖核心业务逻辑
- **test_redteam_*.py** — 5 个文件，20+ 测试，压力测试边界条件

#### ⚠️ 可疑的测试（"Fake Green" 风险）

| 测试文件 | 问题 | 风险等级 |
|----------|------|----------|
| test_e2e_full_pipeline.py | 使用 MockMeasurementService，不验证真实 Adapter | **P0** |
| test_sprint4_real_adapter.py | 1 个测试跳过（line 184），基于固定 JSON 数据 | P1 |
| test_elmo_client.py | 使用 MockTransport，不验证真实 HTTP 调用 | P2 |
| test_redteam_audit.py | 断言 status_code，不验证业务语义 | P2 |

### 10.3 E2E 测试真相

**test_e2e_full_pipeline.py:76-79** — 关键代码：
```python
mock_adapter = MockMeasurementAdapter()
mock_service = MockMeasurementService(adapter=mock_adapter)

measurement_result = await mock_service.execute_measurement(
    project_id=project_id,
    queries=["best industrial sensors manufacturer", ...],
    scope={"markets": ["US"], "engines": ["ChatGPT"]},
)
```

**结论**：E2E 测试使用 **MockMeasurementService**，不是真实 Adapter。测试验证的是「骨架」而非「真实测量能力」。

---

## 11. E2E Audit

### 11.1 真实流程追踪

```
Distributor (Tenant) 
    ↓
Client (ABSENT — 仅 client_id 字符串)
    ↓
Request ✅ (ServiceRequest, 完整状态机)
    ↓
Scope ✅ (TechnicalScope, 版本化)
    ↓
Project ✅ (Project, 10 状态转换)
    ↓
网站诊断 ⚠️ (OpenGeoAdapter 读 JSON，非实时采集)
    ↓
Measurement ✅ (模型存在，但无服务层调用)
    ↓
Evidence ⚠️ (双定义冲突，无独立 repo)
    ↓
Finding ❌ (完全缺失)
    ↓
优化建议 ⚠️ (InterventionRecommendation 文档概念)
    ↓
Report ✅ (版本管理，is_client_safe)
```

### 11.2 断点位置

| 断点 | 位置 | 说明 |
|------|------|------|
| ① Client 对象缺失 | models/project.py:57 | client_id 只是字符串 |
| ② Finding 模型缺失 | 无 | Measurement → Opportunity 链条断裂 |
| ③ 四阶段未实现 | 无 | 代码中无任何 Service Stage 逻辑 |
| ④ 无实时测量 | adapters/opengeo.py | 只读已落盘 JSON |
| ⑤ collect/report stub | main.py:136 | CLI 模式未实现 |
| ⑥ 无 Web API | 无 | 无法通过 HTTP 访问 |

---

## 12. BookConv / TJOstrichInk Validation Readiness

### 12.1 BookConv 数据

| 指标 | 值 |
|------|-----|
| observations.json | 15 条观测 |
| query_set.json | 40 个查询 |
| metrics.json | 聚合指标（mention_rate: 100%, recommendation_rate: 86.67%） |
| 数据性质 | ✅ **真实** — 来自 Bing AI Performance 导出 |

**关键发现**：
- `query_count: 15` vs `query_set.json: 40` — **覆盖率 37.5%**，不是 100%
- 观测数据来自 `bing_ai_performance_export`（`extraction_method: "bing_ai_performance_export"`）
- 这是**历史快照**，不是实时采集

### 12.2 TJOstrichInk 数据

| 指标 | 值 |
|------|-----|
| observations.json | 46 条观测 |
| 数据性质 | ✅ **真实** |

### 12.3 验证准备度矩阵

| 网站 | 是否能创建项目 | 是否能真实测量 | 是否能生成 Evidence | 是否能 Finding | 是否能 Report | 阻塞点 |
| ---- | ------- | ------- | -------------- | ----------- | ---------- | --- |
| BookConv | ✅ | ❌ (仅快照) | ⚠️ (基于快照) | ❌ | ✅ | 无实时测量 |
| TJOstrichInk | ✅ | ❌ (仅快照) | ⚠️ (基于快照) | ❌ | ✅ | 无实时测量 |

**结论**：两个网站都可以**加载历史数据生成报告**，但无法进行**实时测量**。

---

## 13. Red Team Findings

### P0 — Blocker（不解决无法真实客户验证）

| # | 问题 | 文件位置 | 影响 | 建议修复 |
|---|------|----------|------|----------|
| 1 | collect/report CLI 模式是 stub | main.py:136 | 无法执行真实测量和报告 | 实现 collect 模式，调用 ElmoAdapter/GeoCollectorAdapter |
| 2 | 无 Web API | 无 | 无法通过 HTTP 访问系统 | 添加 FastAPI/Flask，定义 REST API |
| 3 | Finding 模型缺失 | 无 | 诊断→机会→行动链条断裂 | 添加 Finding 模型，建立 Measurement→Finding 映射 |
| 4 | 无实时测量管线 | adapters/opengeo.py | 只能读历史 JSON，无法实时采集 | 实现 ElmoAdapter 真实调用，或集成 GeoCollectorAdapter |
| 5 | InMemoryRepository | repositories/base.py:72 | 重启数据丢失，不适合生产 | 添加 SQLAlchemy/SQLite 持久化层 |

### P1 — Must Change（真实客户验证前应解决）

| # | 问题 | 文件位置 | 影响 | 建议修复 |
|---|------|----------|------|----------|
| 6 | Evidence 类冲突 | models/evidence.py:17 vs geo_core.py:26 | import 混乱，维护困难 | 统一到 geo_core.py，删除 evidence.py |
| 7 | Client 模型缺失 | repositories/client_repo.py | 无法独立管理 Client 生命周期 | 添加 Client 数据类 |
| 8 | API Key 硬编码 | config/settings.yaml:68 | 安全风险，密钥泄露 | 使用环境变量或密钥管理服务 |
| 9 | Service Stage 缺失 | models/project.py | 四阶段工作流无法实现 | 添加 service_stage 字段到 Project |
| 10 | DistributionService stub | services/distribution.py:8 | 分销管理功能未实现 | 实现 DistributionService |

### P2 — Should Change（影响体验/可维护性）

| # | 问题 | 文件位置 | 影响 | 建议修复 |
|---|------|----------|------|----------|
| 11 | 无数据库迁移 | 无 | schema 变更困难 | 添加 Alembic/SQLModel migrations |
| 12 | 无 Rate Limiting | 无 | API 滥用风险 | 添加中间件限制请求频率 |
| 13 | 审计日志无查询接口 | models/audit.py | 无法追溯操作历史 | 添加 AuditService |
| 14 | Mock 数据在测试中过度使用 | tests/test_e2e_full_pipeline.py | 测试不验证真实链路 | 添加真实 Adapter 集成测试 |
| 15 | 测试覆盖率不均 | tests/ | 部分模块无测试 | 补充 intervention_loop.py, measurement_analysis.py 测试 |

### P3 — Later（MVP 不需要）

| # | 问题 | 建议 |
|---|------|------|
| 16 | 多语言支持 | 后续添加 i18n |
| 17 | 实时通知 | 后续添加 WebSocket/邮件通知 |
| 18 | 数据分析面板 | 后续添加 Grafana/Dashboard |

### NO CHANGE — 当前实现合理

| # | 组件 | 理由 |
|---|------|------|
| 19 | Project 状态机 | 10 状态设计合理，状态转换表完整 |
| 20 | 租户隔离机制 | 8 种攻击向量覆盖完整 |
| 21 | PlatformObservation 契约 | 统一 Adapter 输出格式，设计良好 |
| 22 | Report 版本管理 | is_client_safe + 版本列表，符合需求 |
| 23 | IdempotencyGuard | 防止重复提交，必要 |
| 24 | StateTransitionGuard | 强制状态机，防止非法转换 |

---

## 14. Minimum Change Set

### Must Change（P0 — 真实客户验证前必须解决）

**1. 实现 collect 模式**
- **为什么**：main.py:136 是 stub，无法执行真实测量
- **对应代码位置**：main.py, services/measurement_analysis.py
- **影响**：系统核心功能
- **不改的后果**：无法进行任何实时 GEO 测量
- **建议怎么改**：实现 `cmd_collect()` 函数，实例化 ElmoAdapter/GeoCollectorAdapter，执行采集，存储结果到 Project

**2. 实现 Web API**
- **为什么**：无 HTTP API，无法通过浏览器/客户端访问
- **对应代码位置**：新建 `api/` 目录，添加 FastAPI/Flask
- **影响**：所有用户交互
- **不改的后果**：系统只能 CLI 使用，无法产品化
- **建议怎么改**：添加 FastAPI，定义 `/clients`, `/projects`, `/measurements`, `/reports` 端点

**3. 添加 Finding 模型**
- **为什么**：V2 要求 Measurement → Finding → Opportunity → Action 链条
- **对应代码位置**：新建 `models/finding.py`
- **影响**：诊断系统的核心输出
- **不改的后果**：无法生成可执行的优化建议
- **建议怎么改**：定义 Finding 数据类，关联 observation_id，包含 category/severity/recommendation 字段

**4. 实现实时测量管线**
- **为什么**：OpenGeoAdapter 只读 JSON，无法实时采集
- **对应代码位置**：adapters/elmo_client.py, adapters/base.py
- **影响**：测量数据的真实性
- **不改的后果**：所有数据都是历史快照，无法验证当前状态
- **建议怎么改**：配置真实 Elmo API 凭据，实现 ElmoAdapter.collect_prompt() 真实调用

**5. 添加持久化层**
- **为什么**：InMemoryRepository 重启丢失数据
- **对应代码位置**：repositories/base.py
- **影响**：数据持久性
- **不改的后果**：每次重启清空所有数据
- **建议怎么改**：添加 SQLAlchemy + SQLite/PostgreSQL，实现 Repository 接口的 SQL 版本

### Should Change（P1 — 验证前应解决）

**6. 统一 Evidence 类定义**
- **为什么**：models/evidence.py 和 models/geo_core.py 有两个 Evidence 类
- **对应代码位置**：models/evidence.py, models/geo_core.py
- **影响**：代码维护和 import 清晰度
- **不改的后果**：import 混乱，可能导致类型错误
- **建议怎么改**：统一到 geo_core.py，删除 evidence.py

**7. 添加 Client 模型**
- **为什么**：ClientRepository 存在但无 Client 数据类
- **对应代码位置**：新建 `models/client.py`
- **影响**：Client 生命周期管理
- **不改的后果**：无法独立管理 Client
- **建议怎么改**：定义 Client 数据类，添加 CRUD 方法

**8. 移除硬编码 API Key**
- **为什么**：settings.yaml:68 明文存储密钥
- **对应代码位置**：config/settings.yaml
- **影响**：安全性
- **不改的后果**：密钥可能泄露到 Git 历史
- **建议怎么改**：使用环境变量 `ELMO_API_KEY`，从 settings.yaml 中移除

**9. 添加 Service Stage 字段**
- **为什么**：V2 要求四阶段工作流
- **对应代码位置**：models/project.py
- **影响**：四阶段状态管理
- **不改的后果**：无法跟踪项目所处阶段
- **建议怎么改**：添加 `service_stage` 字段（DIAGNOSIS/COMPETITIVE_ANALYSIS/OPTIMIZATION/MONITORING）

**10. 实现 DistributionService**
- **为什么**：services/distribution.py 是 stub
- **对应代码位置**：services/distribution.py
- **影响**：分销管理功能
- **不改的后果**：无法管理 Distributor-Client 关系
- **建议怎么改**：实现 create_organization, create_brand, create_project, run_project 方法

---

## 15. Second-Round Red Team

### Challenge 1: 有没有把"代码存在"误判成"业务能力存在"？

**自我批判**：
- ✅ 已识别：Finding 模型不存在（代码中零 Finding 引用）
- ✅ 已识别：Service Stage 不存在（grep 返回零结果）
- ✅ 已识别：DistributionService 是 stub（仅 8 行）
- ⚠️ 可能遗漏：InterventionRecommendation 是文档概念，但 test_intervention_loop.py 测试通过 —— 我标注为"CONCEPT ONLY"，但实际有计算逻辑（priority_score）。应改为 PARTIAL。

### Challenge 2: 有没有把 Mock/Fixture 当成真实能力？

**自我批判**：
- ✅ 已识别：MockMeasurementService 在 E2E 测试中被直接使用（test_e2e_full_pipeline.py:77-79）
- ✅ 已识别：OpenGeoAdapter 读取已落盘 JSON（adapters/opengeo.py:42-48）
- ⚠️ 需要澄清：Sprint4 的 BookConv/TJOstrichInk 数据是**真实的历史导出**（来自 Bing AI Performance），不是 Mock。区别在于：数据是真实的，但采集管线不存在。我已在报告中标注为"✅ 真实 — 来自 Bing AI Performance 导出"。

### Challenge 3: 有没有把 UI 当成后端能力？

**自我批判**：
- ✅ 已确认：无 Web UI，无 FastAPI/Flask/Starlette
- ✅ 已确认：只有 CLI（main.py）
- 无 UI 相关误判

### Challenge 4: 有没有因为 V2 架构而过度修改原有稳定代码？

**自我批判**：
- ✅ 未修改任何代码（读-only 审计）
- ✅ 建议仅停留在"建议修复"列
- 符合审计原则

### Challenge 5: 有没有把三个系统边界搞混？

**自我批判**：
- ✅ AI Visibility Diagnostic: 有契约（PlatformObservation）无执行（缺 Finding、缺诊断服务）
- ✅ GEO Content Operating: 完全缺失
- ✅ GEO Distributor: 骨架完整（Tenant→Request→Scope→Project→Report）
- 边界划分清晰

### Challenge 6: 有没有为了"四阶段"而错误新增复杂 Workflow 数据模型？

**自我批判**：
- ✅ 未建议新增复杂 Workflow 模型
- ✅ 仅建议添加简单的 service_stage 字段到 Project
- ✅ 符合"最小修改原则"

### Challenge 7: 有没有遗漏 Distributor/Client 的权限和数据隔离？

**自我批判**：
- ✅ 已验证：8 种攻击向量全部通过（test_tenant_isolation_final.py）
- ✅ 已验证：6 种角色权限覆盖完整（test_rbac_final.py）
- ✅ 未发现遗漏

### Challenge 8: 有没有遗漏真实 Provider/Collector/Measurement 的真实性问题？

**自我批判**：
- ✅ 已识别：ElmoAdapter 是真实 HTTP 客户端，但未配置生产凭据
- ✅ 已识别：GeoCollectorAdapter 依赖外部项目，无自动触发路径
- ✅ 已识别：OpenGeoAdapter 只读 JSON
- ✅ 已识别：MockMeasurementService 生成模拟数据
- 无遗漏

### Challenge 9: 有没有把 Report 当成业务闭环终点？

**自我批判**：
- ✅ 已指出：Report 之后应有 Finding → Opportunity → Action → Monitoring 闭环
- ✅ 已指出：当前系统止于 Report，无后续行动追踪
- 无误判

### Challenge 10: 如果明天拿 BookConv 和 TJOstrichInk 做第一次真实客户模拟，当前代码真正会在哪里失败？

**自我批判**：
- **失败点 1**：main.py --mode collect 是 stub，无法启动采集
- **失败点 2**：ElmoAdapter 无真实 API 凭据，health_check 返回 False
- **失败点 3**：无 Web API，无法通过浏览器创建项目
- **失败点 4**：Finding 缺失，无法生成优化建议
- **失败点 5**：四阶段未实现，无法跟踪项目进度
- **最小可行路径**：使用 OpenGeoAdapter 加载历史 JSON → 生成 Report —— 这条路径**可以工作**，但数据是历史快照，不是实时测量。

---

## 16. Final Verdict

### 问题 1: V2 架构是否与当前代码冲突？

**不冲突，但当前代码尚未实现 V2 要求。**
- ✅ Project 作为业务容器 —— 已实现
- ❌ Service Stage 字段 —— 缺失
- ❌ 四阶段工作流 —— 未实现
- ❌ Finding 模型 —— 缺失
- ✅ Tenant/Request/Scope/Report —— 已实现

**结论**：代码架构**兼容** V2，但**功能不完整**。需要添加 Service Stage、Finding 模型、实时测量管线。

### 问题 2: 哪些能力已经真实存在？

**真实能力（可立即使用）**：
1. ✅ Tenant/User/RBAC（models/tenant.py）
2. ✅ ServiceRequest 状态机（models/request.py）
3. ✅ TechnicalScope 版本化（models/scope.py）
4. ✅ Project 业务容器 + 10 状态转换（models/project.py）
5. ✅ WorkItem 管理（models/work_item.py）
6. ✅ Report 版本管理 + is_client_safe（models/geo_core.py:74）
7. ✅ 租户隔离（8 种攻击向量验证通过）
8. ✅ IntakeService / ScopingService / ProjectService / DeliveryService
9. ✅ PlatformObservation 契约（compatibility/base.py）
10. ✅ ElmoAdapter HTTP 客户端（需配置凭据）
11. ✅ OpenGeoAdapter（读取已落盘 JSON）
12. ✅ InterventionRecommendation 计算逻辑（intervention_loop.py:42-78）
13. ✅ DeltaCalculator（intervention_loop.py:137-154）

**测试验证**：249/250 tests pass，包括安全测试、租户隔离、RBAC。

### 问题 3: 哪些能力只是概念/UI/Mock？

**概念/Stub/Mock**：
1. ❌ Client 对象 —— 仅 client_id 字符串字段
2. ❌ Finding 模型 —— 完全缺失
3. ❌ Service Stage 字段 —— 完全缺失
4. ❌ 四阶段工作流 —— 纯文档概念
5. ❌ 竞品分析 —— 完全缺失
6. ❌ 实时测量管线 —— 只能读历史 JSON
7. ❌ collect/report CLI 模式 —— stub
8. ❌ Web API —— 不存在
9. ❌ DistributionService —— 8 行 stub
10. ⚠️ Evidence 类冲突 —— 两个定义不一致
11. ⚠️ MockMeasurementService —— 生成模拟数据，但未被 services/ 层调用（仅测试使用）

### 问题 4: 第一次真实客户验证前必须修改什么？

**P0 Blocker（5 项）**：
1. 实现 `cmd_collect()` — 调用 ElmoAdapter/GeoCollectorAdapter 执行真实测量
2. 添加 Web API — FastAPI/Flask，定义 REST 端点
3. 添加 Finding 模型 — Measurement → Finding → Opportunity 链条
4. 配置真实 Elmo API 凭据 — 或实现 GeoCollectorAdapter 真实调用
5. 添加持久化层 — SQLAlchemy + SQLite/PostgreSQL

**P1 Must Change（5 项）**：
6. 统一 Evidence 类定义
7. 添加 Client 数据类
8. 移除硬编码 API Key
9. 添加 Service Stage 字段
10. 实现 DistributionService

### 问题 5: 哪些东西现在明确不应该改？

**保持现状（24 项）**：
1. ✅ Project 状态机（10 状态，完整转换表）
2. ✅ 租户隔离机制（8 种攻击向量验证）
3. ✅ PlatformObservation 契约（统一 Adapter 输出）
4. ✅ Report 版本管理（is_client_safe + 版本列表）
5. ✅ IdempotencyGuard（防止重复提交）
6. ✅ StateTransitionGuard（强制状态机）
7. ✅ IntakeService（clarification loop）
8. ✅ ScopingService（版本化 scope）
9. ✅ ProjectService（submit_request + approve_scope）
10. ✅ DeliveryService + ReportService（execute_delivery + QA）
11. ✅ ReMeasurementService（基线重测）
12. ✅ DeltaCalculator（前后对比计算）
13. ✅ InterventionRecommendation（干预建议计算）
14. ✅ ElmoClient HTTP 客户端（重试、超时、认证）
15. ✅ GeoCollectorAdapter（依赖外部项目，设计合理）
16. ✅ OpenGeoAdapter（读取历史数据，透明处理）
17. ✅ MockMeasurementAdapter/Service（测试辅助，设计合理）
18. ✅ InMemoryRepository（MVP 阶段足够）
19. ✅ ADR 文档体系（ADR-005/006/007）
20. ✅ Sprint4 Lab 数据（BookConv/TJOstrichInk 真实历史数据）
21. ✅ 测试套件（249 tests，覆盖核心逻辑）
22. ✅ config/settings.yaml 结构
23. ✅ config/engines.yaml 配置
24. ✅ README.md 架构说明
