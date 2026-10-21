# 渠道商工作区实施与验收报告

日期：2026-10-19（Asia/Shanghai）  
实施依据：用户确认的《渠道商后台体验与功能优化规划 V0.1》。  
范围裁定：**LOCAL_WORKSPACE = PASS WITH RESIDUALS；PRODUCTION = BLOCKED（维持）**。

## 已交付

- 蓝白工作台、桌面侧栏、手机折叠菜单；客户搜索与详情、客户和项目关联。
- 三步需求提交、可搜索国家/语言多选、字段校验、上一步保留输入、离开确认。
- ServiceRequest 受理队列：总部技术要求补充和拟定范围，总部管理批准/拒绝；批准前没有正式项目。
- 确认范围、周期、交付物、排除项、审批人与处理记录持久化在既有需求的 workflow 快照中。
- 需求提交按租户及 Idempotency-Key 确定稳定请求 ID；批准以 SQLite BEGIN IMMEDIATE 原子写入请求和项目，稳定项目主键防重复。
- 服务端校验直接创建、启动、推进、完成、删除项目的总部权限；直接创建项目另限总部管理角色。线索转换先创建待确认需求。
- 需求、项目状态、服务阶段、报告可用性分别展示；阶段比例不再代表项目验收。
- 项目内报告列表、独立报告详情、历史报告读取、打印/保存 PDF；旧汇总缺少有效分母时不展示主指标，不改写存储数值。
- 读取错误不再伪装为未生成；会话失效重新登录后回到原报告，路由序号防止旧异步响应覆盖新页面。
- BFF 增加 requests 前缀及 Idempotency-Key 头白名单；HQ 通过受认证的 tenant_id 查询选择资源范围，普通身份越租户声明返回 403。

## 运行与数据基线

实际后台在 `E:/GEO项目/技术层/geo-distributor`，WordPress 目录只负责入口、反代配合及线索集成。

原 8765 服务未设置 GEO_DISTRIBUTOR_DB，使用内存存储。初次读取已配置渠道商租户的客户、项目和线索均为空，不能据此宣称历史数据库丢失。

本次已启用新的专用本地持久化库：

- 业务库：`data/portal-local.db`；审计库：`data/portal-local-audit.db`。
- 启动：`scripts/start_portal_local.ps1` → `scripts/run_portal_local.py`。
- 只监听 `127.0.0.1:8765`，经既有 Apache 入口 `/portal/` 和 `/ui/` 访问。
- 启动脚本使用独立 pythonw 进程，不依赖聊天终端存活；端口已有服务时拒绝重复启动。
- 最终重启后：clients=0、requests=0、projects=0、leads_intake=1，SQLite quick_check=ok；页面和资源均 200，在线 JS/CSS 与当前源文件一致。
- 存量其他业务数据库未迁入新工作区，未导入样例客户。验收数据仅在 `data/portal-acceptance/` 和独立 WordPress 测试表中。

### 已披露副作用与保留

1. WordPress 的既有接入密钥没有在后端注册，认证读取为 401。本次对齐了本地注册表，并增加独立 HQ_MANAGEMENT 本地身份；密钥不写入代码、报告或浏览器存储。
2. 对齐认证后、旧队列保护启用前，**既有 WP-Cron 自动推送了一条历史待重试线索**：`source=contact`、`source_lead_id=48`、`LEAD-396EA8306A`。这是实施顺序造成的副作用，不是本轮计划中的历史补发。
3. 未删除该记录。切换服务前导出其当前可读取投影并迁入新持久化库，保留来源 ID、原创建时间和远端编号。原队列内存中的内部逐项历史无法从公开投影完整恢复；原 HTTP 审计库保留，迁移记录未伪造旧审计事件。
4. WordPress 自动重试现在使用持久化的 `ggs_leads_auto_retry_min_id` 下限；旧待重试队列不自动补发，管理员的原有手工重试入口保留。隔离验证确认旧条目尝试次数为 0，新条目成功推送一次。
5. 早期复用既有线索测试时，其默认审计输出追加到 `data/audit_log.db`。未清理或改写旧审计条目；该测试 fixture 已补独立审计库，最终复验也显式隔离审计。

配置与迁移备份位于 `.workbuddy/backups/portal-20261019/`，在 Web 根外且被 Git 忽略。该目录包含敏感配置与线索投影，不应上传或分享。

## 接口及兼容性

新增：`POST/GET /requests`、`GET /requests/{id}`，以及 `POST /requests/{id}/{clarification|supplement|scope|approve|reject}`。

- 创建需要 Idempotency-Key；修改需要当前 workflow.revision。
- 旧页面修改返回 409；批准重试返回原关联项目。
- 创建必填客户、服务和业务问题；单市场一个国家，多市场至少两个，全球市场可不列国家。
- scope 保存确认范围、周期和交付物；批准后不可修改该快照，范围变化走新需求。
- ProjectOut 增加 blocked_reason 与 request_summary；ReportOut 增加 data_quality。历史 JSON 无需回填即可读取。
- 渠道商对旧 `POST /projects` 返回 403，改走需求接口；直接创建仅供总部管理角色兼容调用。
- 旧 `#/dashboard`、`#/clients`、`#/projects`、`#/project/{id}` 和总部线索队列链接继续可用。
- 未重做 Measurement、Evidence、Attribution 或交付计算服务；`geo_distributor/services/delivery.py` 未改。

## 验收证据

自动化：**49 项全部通过**，覆盖：

- 创建重放/冲突、批准前没有项目；澄清、补充、范围保存、批准和拒绝。
- 并发批准只有一个项目、SQLite 写入失败整体回滚、重建仓储后范围与审批记录可读。
- 内存后端兼容、BFF 幂等头透传、会话退出、保护路径和越租户拒绝。
- 普通渠道商不能批准或操作总部阶段，技术角色不能批准，只读不能写入。
- 既有交付幂等、角色守卫与服务字段回归；历史报告投影不改变原值。

测试文件：`tests/test_portal_workflow.py`、`tests/test_channel_portal_service_intake_fields.py`、`tests/test_leads_intake.py`、`tests/test_security_red_team.py`、`tests/test_redteam_idempotency.py`、`tests/security/test_rbac_final.py`。

真实浏览器（专用 8766 测试服务）：

- 创建客户 → 三步需求 → 技术拟定范围 → 管理批准 → 渠道商项目/报告读取，通过。
- 20 条分页、末页、搜索与筛选条件保留，通过。
- 手机菜单、字段错误、上一步保留输入、离开取消保护，通过。
- 报告 503 显示读取失败，未误显示空报告；401 返回登录并恢复报告，通过。
- 延迟客户读取后切换到项目，旧响应未覆盖新页面，通过。
- 实测 CSS 视口 1440、768、390 均无整页横向溢出。系统 DPR=1.5，截图使用 device 比例；早期 CSS 比例截图有捕获裁切，未据此判定页面缺陷。
- 桌面项目、平板报告、手机报告已视觉检查；实际 PDF 2 页已渲染逐页检查，质量说明、正文和局限未截断。

WordPress：`scripts/verify_wp_portal_intake.php` 在独立测试表完成真实写入、推送到隔离 API、远端编号回写及旧队列保护；另验证 HQ 分配后渠道商可读。没有发送外部邮件。保留的测试表：`portal_acc_20261019042707_ggs_leads`、`portal_acc_20261019044043_ggs_leads`。

证据目录：`exports/portal-20261019/`，含 tests.xml、三视口截图、打印 PDF、页面渲染图与源文件哈希清单。

## 剩余限制与回滚

- 正式域名、TLS、生产身份与发布门禁未在本轮关闭，生产状态继续 BLOCKED。
- 历史报告尚无可核验有效分母、测量窗口和来源关联；界面诚实标注缺失，不计算新的替代指标。这是交付口径限制，不代表测量数值已经核验。
- 总部审批使用既有集成身份；同角色共享集成密钥不是逐员工身份体系。独立客户登录、佣金、支付和跨会话草稿未纳入本期。
- 代码尚未提交或推送；Notion 未写入，本地报告为本次实施记录。

回滚前停本地服务并备份当前 SQLite；按文件恢复实施前的 `fbba012` 基线，不使用全库 reset/clean。凭据注册表原件与切换前数据库备份在上述受保护备份目录。新审批记录及其 workflow 快照必须保留，不能直接用旧序列化代码继续写入后再声称审批历史完整。仅需恢复样式时也应保留新的审批接口和权限边界，不能恢复旧的渠道商自动批准流程。
