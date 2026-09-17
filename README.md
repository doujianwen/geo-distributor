# GEO Platform — 海外 GEO 分销系统

**版本：** V0.4.0
**阶段：** A1.7 ElmoAdapter MVP
**项目负责人（技术）：** Gino

---

## 项目定位

面向海外市场的 GEO（Generative Engine Optimization）商业产品，
支持分销、渠道合作、代理销售模式。

目标客户：海外企业 / B2B / DTC 品牌 / SEO Agency / GEO Service Provider

---

## 架构（V0.4）

```
Commercial Layer (this project)
        │
        ▼
 Adapter Layer
   ┌────┴────┐
   │         │
GeoCollector  Elmo  ← 接口已定义，等待 A1.6.1 通过后实现
   │         │
   └────┬────┘
        ▼
 Compatibility Layer  ← ★★★ A1.6 主战场
        │
        ▼
 PlatformObservation  （统一契约）
        │
        ▼
 Evidence → Measurement → Diagnosis → Recommendation
```

**核心原则：**
- 所有 Adapter 输出同一份 `PlatformObservation`，上层业务不感知数据来源
- Elmo 与 GeoCollector 可互换，future-proof
- 不修改 geo-collector 源码（Upstream First）
- 先验证（Compatibility Report + Upstream Audit），后实现（ElmoAdapter）
- Evidence 是可验证的核心价值，不是附带的元数据

---

## A1.7 审计结论

| 审计项 | 结论 | 文档 |
|--------|------|------|
| A1.7 ElmoAdapter MVP | PASS | [A1.7_ELMO_ADAPTER_REPORT.md](A1.7_ELMO_ADAPTER_REPORT.md) |
| ADR-005: Observation First | Accepted | [docs/ADRs/ADR-005-observation-first.md](docs/ADRs/ADR-005-observation-first.md) |
| ADR-006: Upstream Before Adapter | Accepted | [docs/ADRs/ADR-006-upstream-before-adapter.md](docs/ADRs/ADR-006-upstream-before-adapter.md) |
| ADR-007: Evidence First | Accepted | [docs/ADRs/ADR-007-evidence-first.md](docs/ADRs/ADR-007-evidence-first.md) |

---

## 目录结构

```
geo-distributor/
├── config/
│   ├── settings.yaml       # 商业产品配置
│   └── engines.yaml        # 引擎选择器配置
├── docs/
│   ├── 00-strategy/         # ★ 商业战略层（规划 / 经济模型 / 验证方法）
│   ├── reference/oneglanse/ # 第三方开源参考资料（非本项目代码）
│   └── ADRs/
│       ├── ADR-005-observation-first.md
│       ├── ADR-006-upstream-before-adapter.md
│       └── ADR-007-evidence-first.md
├── geo_distributor/
│   ├── config/__init__.py  # 配置加载（支持环境变量覆盖）
│   ├── models/__init__.py  # 商业模型 + GEO 链路模型
│   ├── compatibility/      # ★★★ A1.6 主战场
│   │   ├── base.py         # PlatformObservation + 映射函数
│   │   └── __init__.py
│   ├── adapters/
│   │   └── base.py         # BaseAdapter / ElmoAdapter / GeoCollectorAdapter
│   ├── services/           # 业务编排（A1.7 细化）
│   └── main.py             # CLI 入口
├── tests/
│   ├── test_config.py
│   ├── test_models.py
│   ├── test_models_v03.py
│   ├── test_adapters.py
│   ├── test_compatibility.py
│   ├── test_evidence.py
│   ├── test_elmo_client.py
│   └── test_elmo_compatibility.py
├── logs/ exports/
├── A1.6_Compatibility_Report.md
├── A1.6.1_Upstream_Stability_Audit.md
├── A1.6_V0.3_UPDATE.md
├── README.md
└── requirements.txt
```

---

## 数据模型（V0.3 完整链路）

```
Prompt → Observation → Evidence → Citation → Measurement → Diagnosis → Recommendation
```

### 平台层（Commercial Product）
- `Organization` — 客户组织
- `Account` — 用户账号
- `Brand` — 品牌
- `Project` — 采集项目
- `Run` — 运行记录
- `Report` — 汇总报告

### GEO 智能层（GEO Intelligence Chain）
- `Provider` — AI 搜索引擎元数据（V0.3 新增）
- `Prompt` — 采集 prompt 定义
- `Observation` — 单次采集结果
- `Evidence` — 可验证证据链（ADR-007，V0.4 模型化）
- `Citation` — 引用来源
- `Measurement` — GEO 指标测量（V0.3 新增）
- `Diagnosis` — GEO 诊断结论（V0.3 新增）

---

## 当前状态

| 组件 | 状态 | 说明 |
|------|------|------|
| PlatformObservation 契约 | ✅ OK | 所有 Adapter 统一输出 |
| GeoCollectorAdapter | ✅ OK | 可直接调用 geo-collector |
| ElmoAdapter | ✅ MVP | REST API, A1.7 完成 |
| Compatibility Mapping | ✅ OK | geo-collector + Elmo → Platform |
| Provider / Measurement / Diagnosis | ✅ OK | V0.3 新增 |
| Evidence 模型 | ✅ OK | ADR-007, V0.4 实现 |
| Elmo → Platform Mapping | ✅ OK | V0.4 实现 |
| DistributionService | 📝 TODO | A1.8+ |
| Web API | 📝 TODO | A1.8+ |

---

## 运行

```bash
# 骨架演示
python main.py --mode demo

# 查看上游数据状态
python main.py --mode status

# 测试适配器健康
python main.py --mode health
python main.py --mode health --adapter elmo

# 运行测试
python -m pytest tests/ -v
```

---

## 商业战略文档（规划层）

2026-09-17 整合：原 `E:\GEO项目\技术层\GEO海外分销系统` 的商业规划文档已迁入 `docs/00-strategy/`。
本仓库现同时承载该系统的**商业规划侧**与**技术实现侧**。

| 文档 | 内容 |
|------|------|
| [海外分销系统规划](docs/00-strategy/海外分销系统规划.md) | GEO Operating System 定位、V1→V4 路线图、渠道分账 |
| [海外GEO模式规划](docs/00-strategy/海外GEO模式规划.md) | 海外市场进入方式 |
| [单位经济模型](docs/00-strategy/单位经济模型.md) | 单客成本 / 收益结构 |
| [_GEO 渠道商业模式的5个假设](docs/00-strategy/_GEO%20渠道商业模式的5个假设.md) | 待验证假设清单 |
| [三方杠精](docs/00-strategy/三方杠精.md) | 反向质疑与压力测试 |
| [审计《GEO商业验证实验 V1.0》](docs/00-strategy/审计《GEO商业验证实验%20V1.0》这个验证方法.md) | 验证方法学审计 |

> ⚠️ 两套编号不是一回事：文档里的 V1→V4 是**商业路线图**（诊断 → 监测 → 运营 → 渠道分账），
> 代码的 V0.1→V0.4 是**技术版本**。不要对号入座。

第三方开源 oneglanse 的参考资料见 [docs/reference/oneglanse/README.md](docs/reference/oneglanse/README.md)。
其源码仍在 `E:\GEO项目\技术层\GEO海外分销系统\oneglanse`，**不属于本项目代码**。

---

## 版本历史

- **V0.1** — 初始脚手架（PASS WITH CHANGES，经审计）
- **V0.2** — 新增 Compatibility Layer，Observation 为核心模型，删除 FastAPI
- **V0.3** — 新增 Provider/Measurement/Diagnosis 模型，ADR×3 文档化，Elmo Compatibility Report（PARTIAL PASS）+ Upstream Stability Audit（CONDITIONAL YES）
- **V0.4** — ElmoAdapter MVP（REST API），Evidence 模型（ADR-007），53 tests pass
