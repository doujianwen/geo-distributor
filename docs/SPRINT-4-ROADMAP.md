# Sprint 4 路线图 — Real Measurement & Intervention Loop

**项目**: 海外 GEO 分销系统 MVP V0.1
**阶段**: Sprint 4A/B/C
**启动日期**: 2026-09-14
**状态**: 🟡 SPRINT 4 INFRASTRUCTURE COMPLETE — OUTCOME VALIDATION PENDING
**最终裁定**: 2026-09-16 二轮 CEO 审计（区分 Replay Validation / Engine Completed / Outcome Pending）

---

## 一、Sprint 目标

从「工程基线通过」转向「商业价值验证」。

核心问题：
> **我们能否在真实环境中证明 L2 → L3 的因果链条？**

---

## 二、Sprint 分解

### Sprint 4A: Real Measurement Integration

**目标**: MockAdapter → OpenGeoAdapter，验证真实采集链路

**交付物**:
1. `OpenGeoAdapter` 继承 `MeasurementAdapter`
2. 支持至少 2 个真实引擎（ChatGPT + Google）
3. 适配 `PlatformObservation` 输出契约
4. E2E 测试仍通过（174 tests green）

**验收标准**:
- [ ] 真实 API 调用成功返回 Observation
- [ ] Observation → Evidence → Finding 链路完整
- [ ] 错误处理（超时、限流、无效 API Key）
- [ ] 日志记录（采集耗时、成功率）

**禁止**: 修改 Core 模型、添加新业务实体

---

### Sprint 4B: Intervention Loop 🟡 ENGINE COMPLETED / VALIDATION PENDING

**目标**: 证明「建议 → 执行 → Re-measurement → Delta」链条

**交付物**:
1. ✅ `InterventionRecommendation` 模型（建议项）
2. ✅ `InterventionExecution` 模型（客户执行记录）
3. ✅ `ReMeasurementService`（重测量服务）
4. ✅ `DeltaCalculator`（效果计算器）
5. ✅ BookConv 真实干预已执行（3 篇文章写入代码库并注册，tsc 通过）

**已验证**（Engine 层面）:
```
Baseline Measurement (Day 0, 真实数据) ✅
Diagnosis → Findings (5 findings) ✅
Intervention Recommendations (5 recommendations) ✅
[客户执行] InterventionExecution ✅ (BookConv 3篇文章已部署)
Re-measurement Service (代码就绪，待触发)
DeltaCalculator (compute 逻辑已验证) ✅
```

**未验证**（Outcome 层面）:
```
Before → After → Delta  ← 需要 Day 7/14 真实重测数据
Intervention → AI Visibility 因果 ← 需要对照组排除 B/C/D 归因
```

**L3 Validation Audit 裁定**（2026-09-14）:
> 🔴 **UNKNOWN**（含 PARTIAL 进展，但未达证明）
> 当前证据强度：管道✅ / 基线✅ / 干预✅ / Outcome🔴
> 任何 YES 宣称均为夸大。

**正确状态表述**:
> **Sprint 4B: Engine Completed / Outcome Validation Pending**
> Delta 计算引擎已实现并测试通过。真实 Before/After/Delta 数据待 Day 7/14 重测。

---

### Sprint 4C: Evidence Library ✅ COMPLETED（2026-09-16）

**目标**: 建立可复用的 GEO 效果证据库

**交付物**:
1. ✅ `EvidenceRecord` 模型（Observation → Intervention → Outcome）— `services/evidence_library.py`
2. ✅ `EvidenceLibraryService`（query、aggregate、export、load_from_lab_cases）
3. ✅ `EvidenceDashboard`（内部 HQ 查看：summary / industry_report / top_n）
4. ✅ 导出功能（JSON + CSV，Client-safe）
5. ✅ 从 sprint4-lab 真实案例数据加载（自动读取 baseline metrics）

**测试覆盖**: 39 个新测试（test_sprint4c_evidence_library.py）
- EvidenceRecord 属性/序列化/Client-safe
- CRUD（add/remove/get_by_case_id/add_from_dict）
- 查询过滤（industry/distributor/client/since/min_delta）
- 聚合统计（aggregate / aggregate_by_industry）
- 导出（JSON / CSV）
- Dashboard（summary / industry_report / top_n）
- 真实案例加载（BookConv + TJOstrichInk）
- 边界情况（空库、负Delta、混合符号、重复case_id）

**验收标准状态**:
- [x] 至少 3 个模拟案例入库（sample_service fixture: CASE-001/002/003）
- [x] 可按 industry/distributor/time 查询
- [x] 统计聚合（平均 Delta、中位数、分位数、positive_rate）
- [x] 不暴露 Internal Technical Data

**战略价值**: 这是 GEO 分销真正值钱的资产——不是代码，是可展示的效果证据。

---

**数据结构**:
```json
{
  "case_id": "CASE-001",
  "distributor_id": "DST-001",
  "client_id": "CLI-001",
  "industry": "industrial_sensors",
  "baseline_visibility_score": 23,
  "intervention": "content_optimization",
  "post_intervention_score": 45,
  "delta": 22,
  "time_to_result_days": 14,
  "evidence_refs": ["EVD-001", "EVD-002"],
  "created_at": "2026-09-14T00:00:00Z"
}
```

**验收标准**:
- [ ] 至少 3 个模拟案例入库
- [ ] 可按 industry/distributor/time 查询
- [ ] 统计聚合（平均 Delta、中位数、分位数）
- [ ] 不暴露 Internal Technical Data

**战略价值**:
> 这是 GEO 分销真正值钱的资产——不是代码，是可展示的效果证据。

---

## 三、冻结清单（Sprint 4 禁止）

| 功能 | 原因 |
|------|------|
| CRM | 放大器，待 L3 验证后 |
| Billing/Commission | 放大器，待 L3 验证后 |
| PostgreSQL 迁移 | MVP 用 InMemory，生产再迁移 |
| FastAPI Web API | 先用 CLI/service 验证，再做 API |
| Distributor Portal UI | 先用 API 验证，再做 UI |
| K8S/Kafka | 单体足够，待规模验证 |
| GeoLook full integration | 保持解耦，Adapter 模式 |
| AI Diagnosis Agent | MVP 用规则，等数据积累 |

---

## 四、里程碑（修正版，2026-09-16 二轮审计后）

| 里程碑 | 目标日期 | 验收标准 | 状态 |
|--------|----------|----------|------|
| 4A Replay Validation | Week 1 | 真实数据回放链路跑通（Bing/GSC → OpenGeoAdapter → PlatformObservation） | ✅ COMPLETED |
| 4B Engine | Week 2 | DeltaCalculator + ReMeasurementService 测试通过，BookConv 干预已执行 | ✅ COMPLETED |
| 4C Evidence Library | Week 3 | 39 新测试，Dashboard + Export + 真实案例加载 | ✅ COMPLETED |
| **Milestone 1: Outcome** | Week 4-6 | Day 7/14 重测拿到真实 Delta，L3 Audit 升级为 PARTIAL/YES | ⏳ PENDING（重测采集脚本已就绪，待真实数据填入） |
| **Milestone 2: Commercial** | Week 7+ | 首个付费客户验证 willingness to pay | 🔴 NOT STARTED |

---

## 五、风险

| 风险 | 概率 | 影响 | 缓解 |
|------|------|------|------|
| OpenGeo API 限流/失效 | 中 | 高 | Mock 兜底，记录失败原因 |
| 真实测量结果不稳定 | 高 | 中 | 多次采样取平均 |
| 客户执行记录缺失 | 中 | 高 | 手动录入接口 |
| Delta 不明显 | 高 | 中 | 选择敏感指标（brand mention count） |

---

## 六、成功标准（修正版，2026-09-16 二轮审计后）

### Sprint 4 Infrastructure（已完成）
1. ✅ Replay Validation: BookConv + TJOstrichInk 真实数据链路跑通
2. ✅ Engine Completed: Intervention Loop 计算引擎 + 190+ 测试
3. ✅ Evidence Library: 39 新测试，Dashboard + Export + 真实案例加载
4. ✅ 全量测试: 243 passed, 1 skipped

### Milestone 1: Outcome Validation（待完成）
5. ⏳ Day 7/14 真实重测拿到 Before→After→Delta
   - **工具已就绪**：`scripts/sprint4_remeasure.py`（Replay 模式，零凭据）
     - `emit-template` 已为 bookconv(39)/tjostrichink(30) 生成占位模板
     - `run` 计算 Delta + 产出 client-safe DELTA_REPORT.md + metrics.json
     - 防伪造护栏：模板未填 → 拒绝计算
   - **待用户动作**：按 `sprint4-lab/cases/DATA_COLLECTION_GUIDE.md` 重新导出真实数据并填入
6. ⏳ 对照组（TJOstrichInk）排除 B/C/D 归因
7. ⏳ L3 Validation Audit 从 UNKNOWN 升级为 PARTIAL 或 YES

### Milestone 2: Commercial Validation（待开始）
8. ⏳ 首个付费客户愿意为 GEO 效果付钱
9. ⏳ 客单价 U-05 有真实数据
10. ⏳ 销售周期 U-07 有真实数据

### 不成功的信号
- ❌ 只有 Mock 数据，无真实 Export
- ❌ Delta 引擎测试通过但无真实 Before/After
- ❌ 证据库为空或只有模拟数据
- ❌ 无法回答「干预后 visibility 提升 X%」

---

---

## 七、二轮审计结论（2026-09-16）

### 关键区分：Replay vs Live

| 维度 | 状态 | 说明 |
|------|------|------|
| **Replay Validation** | ✅ COMPLETED | Bing/GSC 真实导出 → JSON → OpenGeoAdapter → PlatformObservation 链路跑通 |
| **Live API Integration** | 🟡 PENDING | ChatGPT/Perplexity 实时调用接口已预留，凭据受限未激活 |
| **Engine Completed** | ✅ COMPLETED | DeltaCalculator / ReMeasurementService 代码 + 测试通过 |
| **Outcome Validation** | 🔴 PENDING | Day 7/14 重测数据未就绪，L3 Audit 裁定 UNKNOWN |
| **Commercial Validation** | 🔴 NOT STARTED | 客户付费意愿未验证 |

### CEO 最终裁定

```
Sprint 4 Infrastructure = ✅ COMPLETE
包含：
  - Measurement (Replay Validation)
  - Evidence
  - Diagnosis
  - Report
  - Delta Engine
  - Evidence Library + Dashboard + Export

Sprint 4 Outcome = 🔴 PENDING
等待：
  - BookConv Day 7/14 重测
  - 真实 Before→After→Delta 数据
  - 对照组排除 B/C/D 归因

Sprint 4 Commercial = 🔴 NOT STARTED
等待：
  - 首个付费客户
  - 真实订单/现金流
```

### 下一步真正该做什么（按优先级）

1. **P0: Day 7/14 重测 BookConv** — 拿到真实 Delta，完成 Milestone 1
2. **P1: 申请 ChatGPT/Perplexity API 凭据** — 启用 Live API 模式
3. **P2: 准备 Commercial Pilot 客户** — 用 BookConv + TJOstrichInk 证据找付费客户

> Day 7/14 重测一旦出现真实 Lift 数据：
> - 项目从「能测量」进入「能证明价值」
> - 这才是 GEO 分销系统真正决定能否卖钱的里程碑

---

**创建日期**: 2026-09-14
**授权人**: CEO
**审计人**: Copilot-Prime + CEO 二轮审计
**最后更新**: 2026-09-16（二轮审计后状态修正）
