# ADR-007: Evidence First GEO Architecture

**状态：** Accepted
**日期：** 2026-09-10
**版本：** V0.3

---

## 上下文

当前 GEO 链路为：

```
Observation → Citation → Measurement → Diagnosis
```

但这个链路缺少 **Evidence（证据）** 层。

在真实 GEO 方法论中，完整的因果链是：

```
Observation（看到了什么）
    ↓
Evidence（凭什么这么说——引用来源、上下文、可验证性）
    ↓
Measurement（量化评分——位置、等级、引用质量）
    ↓
Diagnosis（诊断结论——为什么是这个分数）
    ↓
Recommendation（改进建议—— actionable insight）
```

没有 Evidence 层，Measurement 就是空中楼阁：
- 一个 citation_count=5 的分数，如果没有证据链，商业客户无法验证
- Diagnosis 的 summary 和 findings 无法追溯到 Observation 的原始数据
- Recommendation 缺乏说服力，无法作为付费产品的核心交付物

---

## 决策

**在 Observation 和 Measurement 之间新增 Evidence 层。**

```
Prompt → Observation → Evidence → Citation → Measurement → Diagnosis → Recommendation
```

其中：
- `Evidence` 是对 Observation 的可验证支撑，包含：引用原文摘录、URL 来源、可信度评分
- `Citation` 保留，但语义收窄为"外部引用来源"（即 Evidence 的子集）
- `Recommendation` 作为 Diagnosis 的输出层，独立存在而非仅作为字段

---

## 约束

- ❌ 禁止删除现有 Citation 模型（保持兼容性）
- ❌ 禁止在不理解 Evidence 层业务价值前实现
- ✅ Evidence 是 Measurement 的前置输入
- ✅ Evidence 是 Diagnosis 的可追溯来源
- ✅ Recommendation 是 Diagnosis 的输出层，也是付费产品的核心交付物

---

## 后果

- 新增模型 `Evidence`：observation_id, source_type, content, credibility_score, verified_at
- Citation 保留但语义收窄为"外部引用"，与 Evidence 的关系为 1:N
- Measurement 计算时需引用 Evidence 的 credibility_score
- Diagnosis 的 findings 需可追溯到具体 Evidence 记录
- 付费产品的核心交付物从"报告"变为"带证据链的诊断 + 建议"

---

## 命名说明

Evidence 层是这个系统的核心竞争力：
- 没有它，系统只是"数据采集工具"
- 有了它，系统才是"GEO 诊断咨询平台"
- 客户付费买的是"可验证的洞察"，不是"数据"
