# 海外 GEO 分销系统｜统一状态机与实施序列 V0.1

> Status: IMPLEMENTATION BASELINE
> Version: V0.1
> Date: 2026-09-13
> Scope: 统一 State Machine 定义、实施优先级序列
> Reference: [01-总体架构](./01-海外GEO分销系统_总体架构与角色边界_V1.0.md), [03-Service Contract](./03-海外GEO分销系统_Service_Contract_V0.2.md), [05-HQ技术交付架构](./05-HQ技术交付架构_V0.1.md)

---

## 1. 背景

当前存在多个版本的 State Machine 描述：
- 03-V0.1 §7 定义了较完整的状态机
- 03-V0.2 简化为 Request + Project 两层
- 05 定义了 Work Item 概念

本文件整合所有版本，形成**单一权威 Source of Truth**。

---

## 2. 三层对象模型（统一）

```
Service Request  →  Project  →  Work Item
   (商业入口)      (商业容器)    (技术执行单位)
```

| 对象 | 归属 | 所有者 | 说明 |
|------|------|--------|------|
| Service Request | Portal | Distributor | 商业需求入口 |
| Project | HQ | HQ Technical Team | 技术交付容器 |
| Work Item | HQ | HQ Technical Team | 最小技术执行单位 |

### 2.1 关系规则

- 一个 Service Request 对应一个 Project
- 一个 Project 可包含多个 Work Item
- Work Item 之间可有依赖关系（DAG）
- Distributor 不直接管理 Work Item 技术状态

---

## 3. State Machine：Service Request

```
                          ┌──────────┐
                          │  DRAFT   │
                          └────┬─────┘
                               │ Submit
                               ▼
                          ┌──────────┐
                     ┌──→│SUBMITTED │
                     │   └────┬─────┘
                     │        │ Intake Review
                     │        ▼
                     │   ┌──────────────┐
                     │   │INTAKE_REVIEW │
                     │   └──┬───────┬───┘
                     │      │       │
                     │      │       │ INCOMPLETE
                     │      │       ▼
                     │      │  ┌───────────────────┐
                     │      └──│CLARIFICATION_REQ  │
                     │         └────────┬──────────┘
                     │                  │ Clarification Provided
                     │                  ▼
                     │            ┌─────────┐
                     │            │ SCOPING │
                     │            └────┬────┘
                     │                 │ Scope Ready
                     │                 ▼
                     │           ┌─────────────────────┐
                     │           │SCOPE_PENDING_APPROVAL│
                     │           └──────────┬──────────┘
                     │                      │ All Approvals
                     │                      ▼
                     │                ┌──────────┐
                     └───────────────→│ APPROVED │
                                      └────┬─────┘
                                           │ Start Execution
                                           ▼
                                      ┌──────────┐
                                      │DELIVERED │
                                      └────┬─────┘
                                           │ Accept / Reject
                                           ▼
                                      ┌──────────┐
                                      │ ACCEPTED │
                                      └──────────┘
```

### 异常状态

```
                    ┌──────────┐
                    │ CANCELLED │
                    └──────────┘
```

**触发条件：**
- CANCELLED：Distributor 主动取消 / 超期未付 / Client 取消

---

## 4. State Machine：Project

```
                    ┌──────────┐
                    │ APPROVED │
                    └────┬─────┘
                         │ Start
                         ▼
                  ┌───────────────┐
                  │ IN_EXECUTION  │
                  └───────┬───────┘
                          │
            ┌─────────────┼─────────────┐
            ▼             ▼             ▼
      ┌─────────┐  ┌──────────┐  ┌─────────┐
      │ BLOCKED │  │   QA     │  │ REWORK  │
      └────┬────┘  └────┬─────┘  └────┬────┘
           │             │             │
           │  Required:  │   FAIL      │  Fix & Re-test
           │  Client     │             │
           │  action     │             │
           ▼             ▼             ▼
    (等 Client      ┌──────────┐
     提供数据)       │ DELIVERED │
                    └────┬─────┘
                         │
                    ┌────┴────┐
                    ▼         ▼
              ACCEPTED    CHANGES_REQUESTED
                    │         │
                    └────┬────┘
                         │ Review
                         ▼
                    ┌──────────┐
                    │  DELIVERED│
                    │ (重新提交)│
                    └──────────┘
```

### 4.1 状态说明

| 状态 | 含义 | 责任方 |
|------|------|--------|
| APPROVED | Scope 已批准，准备执行 | HQ |
| IN_EXECUTION | 技术执行进行中 | HQ |
| BLOCKED | 外部依赖导致暂停 | Client / Distributor |
| REWORK | QA 发现需重做 | HQ |
| QA | 质量检查中 | HQ |
| DELIVERED | 交付物已生成 | HQ |
| ACCEPTED | 客户/Distributor 已接受 | Distributor |
| CHANGES_REQUESTED | 客户要求修改 | Distributor |

### 4.2 BLOCKED 记录要求

```json
{
  "blocked_reason": "client_access_missing",
  "blocked_since": "2026-09-13T00:00:00Z",
  "required_action": "Provide GA4 read access",
  "owner": "CLIENT"
}
```

---

## 5. State Machine：Work Item

```
                    ┌──────────┐
                    │ PENDING  │
                    └────┬─────┘
                         │ Dependencies Met
                         ▼
                  ┌───────────────┐
                  │ IN_PROGRESS   │
                  └───────┬───────┘
                          │
            ┌─────────────┼─────────────┐
            ▼             ▼             ▼
      ┌─────────┐  ┌──────────┐  ┌─────────┐
      │ BLOCKED │  │ COMPLETED│  │ FAILED  │
      └─────────┘  └──────────┘  └────┬────┘
                                       │ Retry (max 3)
                                       ▼
                                  ┌──────────┐
                                  │ FAILED   │
                                  └──────────┘
```

### 5.1 Work Item 类型

| 类型 | 说明 | 是否 Client-facing |
|------|------|-------------------|
| measurement | 数据采集与测量 | 是 |
| diagnosis | 诊断分析 | 是 |
| intervention | 干预执行 | 否（内部操作） |
| remeasurement | 重测验证 | 是 |

### 5.2 Work Item 依赖

MVP 阶段支持线性依赖，未来支持 DAG：

```text
WI-001 (measurement)
    ↓
WI-002 (diagnosis)
    ↓
WI-003 (intervention)
    ↓
WI-004 (remeasurement)
```

---

## 6. 实施优先级序列

### Phase 0：基础契约（P0）

| 任务 | 产出 | 依赖 |
|------|------|------|
| 0.1 | Service Contract V0.2 冻结 | 无 |
| 0.2 | State Machine 统一文档（本文档） | 0.1 |
| 0.3 | 数据模型定义（Portal + HQ） | 0.1 |

### Phase 1：核心流程（P1）

| 任务 | 产出 | 依赖 |
|------|------|------|
| 1.1 | Intake Module 实现 | 0.2, 0.3 |
| 1.2 | Scope Module 实现 | 1.1 |
| 1.3 | Project CRUD | 1.2 |
| 1.4 | Work Item 基础结构 | 1.3 |

### Phase 2：技术引擎（P2）

| 任务 | 产出 | 依赖 |
|------|------|------|
| 2.1 | Measurement Engine | 1.4 |
| 2.2 | Evidence Engine | 2.1 |
| 2.3 | Diagnosis Engine | 2.2 |
| 2.4 | open-geo Adapter 集成 | 2.1 |

### Phase 3：交付能力（P3）

| 任务 | 产出 | 依赖 |
|------|------|------|
| 3.1 | Report Generator（Client） | 2.3 |
| 3.2 | Report Generator（Technical） | 2.3 |
| 3.3 | QA Module | 3.1, 3.2 |
| 3.4 | Delivery Result 生成 | 3.3 |

### Phase 4：Portal MVP（P4）

| 任务 | 产出 | 依赖 |
|------|------|------|
| 4.1 | Client 管理 | 0.3 |
| 4.2 | Service Request 提交 | 1.1 |
| 4.3 | Project 状态查看 | 1.4, 3.4 |
| 4.4 | Report 下载 | 3.1 |
| 4.5 | Dashboard | 4.1-4.4 |

### Phase 5：商业闭环（P5）

| 任务 | 产出 | 依赖 |
|------|------|------|
| 5.1 | Renewal 管理 | 4.5 |
| 5.2 | Expansion 流程 | 4.5 |
| 5.3 | Notification System | 4.1-4.5 |

### Phase 6：高级能力（P6，Pilot）

| 任务 | 产出 | 依赖 |
|------|------|------|
| 6.1 | Intervention 执行 | 2.3 |
| 6.2 | Re-measurement | 6.1 |
| 6.3 | Observed Effect 计算 | 6.2 |

---

## 7. 关键里程碑

```
M1: Contract Freeze          → Phase 0 完成
M2: Core Flow Pass           → Phase 1 完成
M3: First Measurement Pass   → Phase 2 完成
M4: First Delivery Pass      → Phase 3 完成
M5: Portal MVP Live          → Phase 4 完成
M6: Commercial Loop          → Phase 5 完成
M7: Intervention Pilot       → Phase 6 完成
```

---

## 8. 退出标准

每个 Phase 完成标准：

| Phase | 退出标准 |
|-------|----------|
| P0 | 所有契约文档签字 |
| P1 | Intake → Scope → Project 端到端 Pass |
| P2 | 单次完整 Measurement + Evidence + Diagnosis 通过 QA |
| P3 | 首次 Client Report 生成并通过 QA |
| P4 | Portal 支持 Core 6 功能，Distributor 真实用户可用 |
| P5 | 第一个 Renewal 流程跑通 |
| P6 | Intervention + Re-measurement 闭环验证 |
