# 统一 GEO 增长工作区：独立架构审计（2026-10-19）

状态：初轮独立架构审计完成；实现复验尚未进行。本文件为独立审计记录，不是第二份执行指令。

## 已核事实

1. 唯一核心在 `E:/一人公司/独立站/geoflow/geo-intent-system`，门户在 `E:/GEO项目/技术层/geo-distributor`。核心祖先 `E:/一人公司/独立站/AGENTS.md` 已读取；未发现适用于核心 app 的更深 AGENTS。
2. 核心 diagnosis_service、action_service、seo_growth_service、data_quality 均接受显式 sqlite3.Connection；相对导入可在独立包名下解析。独立 Python 导入实验加载五模块（含 database）成功，未加载 app.main，未打开或修改真实数据库。
3. Diagnosis 与 Action 有冻结枚举、去重、证据同源及状态机。发布态要求 URL、时间、内容哈希、标题四快照；关闭 Action 不自动解决 Diagnosis。应直接复用，不在门户实现第二套诊断/行动模型。
4. 多个核心服务自行 commit；data_quality.set_observation_disposition 自行 BEGIN IMMEDIATE。门户外层事务不能直接保证核心操作与门户日志、幂等记录的共同原子性。
5. 核心数据库只有 site/product 及关系约束，没有 tenant/client 授权。门户认证不能因服务调用成功便认为已隔离租户。
6. sync_geo_collector_to_growth_loop_v1.py 明确是内部运维工具，源库只读、默认预览，可显式目标库，但不具有多租户权限边界。旧 import_geo_collector.py 是 legacy citations 投影，不能当 canonical 导入。
7. compute_delta_r4_r5.py 等脚本是冻结真实特定批次脚本：默认真实数据库、硬编码 run/question/provider/surface，部分指标绑定特定竞品；不得改常量后当通用接口。data_quality.delta_pair_quality_guard 可复用；现有脚本不是通用 Delta 服务。
8. data_quality 允许没有复核行的历史数据以 UNREVIEWED 兼容，明确 HOLD/REJECTED 不可进入诊断/Delta；门户不得伪造 APPROVED 以绕过该规则。

## 必须满足的条件

| 条件 | 最小实现要求 |
|---|---|
| 唯一核心 | 服务端固定核心根目录与代码来源；独立包名加载；不导入 app.main，不跑其启动迁移，不改核心文件，不把核心包复制到门户 |
| 明确绑定 | HQ 明确 project → tenant/client → core site/product；验证 site.source_product_id；一个 site/product 不可跨不同 tenant/client 共享；变更绑定需冲突校验和审计 |
| 不自动附会历史 | 名称/域名相同不能自动认领历史 site；现有真实项目与历史核心的绑定须显式授权；缺绑定显示可操作的待配置原因 |
| 授权逐级校验 | 每次请求重查身份、客户激活、项目归属和绑定；question/product、evidence/observation/run/site、diagnosis/site、action/site、publication/action、delta/run 对均校验 |
| 职责分离 | HQ 可执行授权范围内生命周期；渠道在所属客户范围协作；END_CUSTOMER 只能自己企业并按能力与任务归属编辑；CLIENT_VIEWER 永远只读；不是所有写动作只做 can_write |
| 写入一致性 | 选择同一核心连接上的事务适配或明确恢复机制；持久 operation key、请求指纹、对象 ID、结果；故障后重试不得重复发布/生成新对象；旧版本应返回冲突 |
| 安全导入 | 服务端白名单源、固定 brand/domain/product；预览及应用来源哈希一致；不能由浏览器传任意文件路径；canonical observation/evidence 关联保留来源；禁止自动补发历史/外部通知 |
| 真实采集边界 | 无可调用采集器时显示申请/待采集及实际原因，不能用 demo fixture 声称已调用真实采集；任何付费/外部操作保留既有门禁 |
| Delta 完整性 | 不能复制冻结脚本为新算法；复用单一质量守卫及冻结比较纪律，缺通用计算器必须明确交付范围与后续门槛；同 prompt/provider/model/surface/market/language/config、有效 run 对才可比较 |
| 客户可见范围 | 原始证据脱敏、内部路径/密钥/内部评论不出 DTO；不能只给最终报告，也不能把全部内部草稿直接公开；公开模块可见性与 Action 执行权限分别控制 |
| 演示隔离 | 虚拟 site/product/observations 仅专用库，显著标记；不得导入到真实核心或给既有真实行补写案例 |

## 最小完整端到端验收链

必须从浏览器完成以下链，不能用有菜单或 JSON 返回成功代替：

1. HQ 为隔离测试客户绑定专用 site/product；渠道和终端能进入同一项目的 GEO 工作区，另一个客户不可访问。
2. 用户维护授权的品牌、页面、业务事实、问题；未授权只读身份写入 403，跨 site 引用被拒绝。
3. HQ 预览并确认一组有来源的观测，形成 canonical Run → Observation → Evidence；重试不重复，质量 HOLD 能阻止后续决策。
4. 从证据形成 Diagnosis，确认后创建关联 Action；客户看到本企业诊断和自己应执行的动作，能提交实质执行反馈，HQ 能复核。
5. 按冻结状态机批准 → 执行 → 创建具备四快照的 Publication → published；不存在发布记录时推进 published 被拒绝。
6. 导入/采集第二组真实来源的对照观测，先展示可比性；合格对才计算/读取 canonical Delta，复用 guarded attribution，结果为零/uncertain 亦如实显示；不得以完成 Action 声称增长或因果。
7. HQ 发布安全结果，客户及渠道查看证据、趋势、行动验证和报告；撤销权限/改绑/质量降级后新请求立即生效，不能从旧缓存绕过。
8. 服务重启后绑定、核心对象、操作幂等、权限及关联持久；并发、过期提交、401/403/429/5xx与快速路由切换均有可恢复行为。

## 当前裁决

独立服务加载方式技术可行。方案只有在上述绑定、逐级授权、写入一致性与完整闭环成立后才可称为统一 GEO 增长工作区完成。当前本记录不批准真实核心写入或生产开放；后续应依据实际实现复验。


## 第二轮独立设计审计

审计对象：`UNIFIED-GROWTH-REVIEW-20261019.md`，对照核心现有服务及冻结 Delta 脚本。审计方式：只读代码和方案；没有实施业务变更。

**裁决：条件通过进入定向补充；当前文本不能直接视为终审通过或实现验收通过。** 统一模块、复用核心、区分内容发布与报告发布方向正确；以下条件必须在唯一指令中变成可验证要求。

### 第二轮缺陷与定向补充

| 编号 | 严重性 | 缺陷与事实 | 可执行补充/验收证据 |
|---|---|---|---|
| IA01 | P0 | 新比较门面不是调用现成通用 Delta 函数：现存计算仅在批次脚本，计划新增实现不能伪称全部原函数复用 | 明确它是唯一核心里的加法参数化适配；仅保留三种既定 metric，逐项与冻结脚本定义/舍入对照测试；不复制到门户；冻结脚本文件与真实历史不变 |
| IA02 | P0 | 方案比较维度未列 request_config_hash、question_set_version；仅两个空值相等不证明可比；未写 run/observation 维度一致性 | 所有必要维度非空且相等；校验 Run=completed、同 site、唯一问题观测、观测与所属 Run 的 provider/model/surface一致、prompt_text实算hash匹配、时间严格前后；采集版本/请求配置/问题集版本纳入可比性或明确不支持；差异输出原因，不写数字Delta |
| IA03 | P1 | metrics JSON 与规范列冲突、bool/NaN/Infinity/负引用数可能制造虚假变化 | 三类指标明确单一来源，矛盾拒绝；mention只许合法0/1，citation非负整数，recommendation沿用冻结定义；缺失未知，拒绝非有限数与字符串含糊转换；零值回归证明 |
| IA04 | P0 | 延迟 commit 代理缺异常和嵌套SQL契约，核心函数同时使用Connection/cursor、commit/rollback及BEGIN IMMEDIATE | 外层连接先BEGIN IMMEDIATE；两类execute/执行批量/游标都受控；内层commit仅延迟，rollback必须回滚并标记rollback-only，不能异常被吞后仍提交元数据；内部重复BEGIN按定义处理；禁executescript/任意事务SQL绕过；真实外层commit仅一次，连接不逃逸 |
| IA05 | P0 | 并发与崩溃情况下，事先查版本和授权容易TOCTOU；跨库门户身份无法宣称与核心全事务 | 核心绑定/授权/版本/操作指纹在同一SQLite锁内复核；客户停用/凭据撤销请求重新认证；证明两个独立连接/进程同键同时提交只一组对象，同键异体409，旧版本409；注入核心已写、内部commit后、元数据事件前、外层commit前异常，全部无残留；重启重放返回同结果 |
| IA06 | P1 | 新编辑角色与“工作区授权”没有持久结构，Action准备/执行未定义任务归属，可能所有客户编辑者修改所有行动 | 默认无编辑grant；HQ管理明确授予 tenant/client/site 范围的 capability并记录revision；客户资料/问题维护与Action执行分别授权；Action需显式客户受派标记/受派主体，未受派只读；撤销grant下次请求403；客户不能改批准、质量、publication、delta和诊断终态 |
| IA07 | P0 | U09要求撤销策略，但正文只有固定hash，没有定义来源撤销、质量降级后旧已发布报告是否还能读 | 快照内容不可漂移；每次列/详情/打印检查报告发布有效、绑定与客户仍有效、来源观测质量和源指纹仍匹配；撤销/源变/降级后不向客户返回旧内容，显示需重审；恢复质量不可自动恢复原发布，可由HQ重新生成/发布新版本；保留内部审计，不重写旧快照 |
| IA08 | P0 | 绑定嵌套检查仅概述，内容计划/brief的product、keyword的site与product、evidence内部引用可绕过单site检查 | 显式资源解析白名单：product对象一律当前product，site对象一律当前site，两者兼有字段同时一致；question与场景画像/cluster关系核验，evidence→observation→run核验且question同product，action所有diagnosis/page/fact一致；报告快照仅引用本绑定可见来源；禁止客户端传任意表名/字段列或路径 |
| IA09 | P1 | 原归因引擎legacy_hits按时间扫描全库content_gaps/briefs，没有site条件，是现存保守规则 | 保留冻结引擎，不擅自修算法；UI如实提示legacy activity可令结果confounded且不泄露其他客户记录；隔离测试覆盖无关legacy记录导致保守结果，不能为演示删除记录或强置attributed；独立核心部署的多租户算法局限列入验收报告 |
| IA10 | P1 | 原服务Action note参数是no-op，界面“执行内容/反馈”可能没有真实落库 | 使用明确加法执行日志/受派资料结构持久记录提交内容与身份/时间，浏览器提交后刷新、重启仍可读；不把note参数调用当执行反馈已实现；不得覆盖冻结description或伪造Publication |
| IA11 | P1 | 人工录入HOLD只证明系统结构闭环，不能证明采集器已接入；“增长报告”名称可能放大结论 | 标注来源为人工登记/虚拟演练，保留证据原文及来源；未接实采明确显示待采集，不能按钮生成假完成；实际采集与效果验证单列未验收门槛，报表不宣称因果或真实增长 |

### 必须追加的验证矩阵

- 事务：各调用组合覆盖diagnosis新建与dedupe补证据、action新建及诊断推进、quality BEGIN、publication、三指标Delta与归因内部commit；中途失败所有领域表和operation/event/version零部分提交。
- 授权：HQ管理/技术、渠道管理员/成员、客户查看/编辑、CLIENT_VIEWER分别验证模块读取及每种写动作；跨tenant、同tenant不同client、同client不同site、未受派Action、撤销grant、停用客户、绑定修改全部回归。
- 数据：HOLD/REJECTED/schema缺失、重复观测、空/差异维度、prompt伪hash、时间倒序、未知/零/负/NaN/Inf、来源突变、legacy干扰、复核后再降级；都不能形成错误数值或可见快照。
- UI：真实表单创建/编辑→数据库对应唯一核心对象；客户确实提交受派执行内容；总部审批、四快照发布、后测、比较、报告分别有入口与返回；401/409/429/503和跨路由竞态不会丢稿/越范围。

补齐以上后，可以进入唯一正式执行指令与隔离实施；第二轮条件通过不等于实现复验通过。最小端到端链仍沿用上一节，不能删减为模块导航与只读结果展示。


### 第二轮补充稿复核结论

已复核主审新增的“第二轮缺陷定向补充与终审条件”及 `UNIFIED-GROWTH-EXECUTION-20261019.md`。主要缺口已纳入：报告源撤销、每请求持久授权与指派、事务代理rollback-only、完整比较维度/数值、演练与实际采集边界。

**设计阶段结论：条件通过，可以按唯一指令进入隔离实施。实现验收尚未通过。** IA01—IA11作为该指令引用的独立审计硬条件继续有效；执行反馈持久化、原归因legacy全库保守规则、失效报告不得自动复活、全部嵌套product/site关系、Run/Observation一致性及内层异常被捕获的rollback-only证据必须在实现复验中逐项检查。任何P0未闭合则实现验收不通过；不得以本设计结论替代运行证据。


## 独立实现首轮审计（开发过程中）

范围：新增唯一核心 `app/portal_contract.py`、门户 `api/growth_core.py` / `routers/growth.py`，登录认证差异及独立隔离测试。以下是开发中发现记录，非最终验收。

新增 `tests/test_growth_independent_audit.py`，复用明确临时目录的真实核心schema fixture；只操作隔离库，不改真实数据。首轮4项回归结果：1通过、3失败。

| 实现缺陷 | 级别 | 当前证据与修正要求 |
|---|---|---|
| 来源质量降级后无读取即恢复，旧报告可复活 | P0，修复复验通过 | 增加质量revision及quality写入同事务锁存快照invalidated后，APPROVED→HOLD→APPROVED之间无GET的独立回归已通过 |
| 客户仍读取HOLD来源的Delta与actioned诊断 | P1，未关闭 | 仅过滤observations/evidence，不过滤衍生结论；独立回归返回3条旧Delta。需复用既有quality eligibility与引用链判断，隐藏或明确停止展示失效结论 |
| 客户创建Action可将未确认open诊断提升actioned | P1，未关闭 | 编辑客户关联已知同站点open diagnosis创建行动返回200，核心单向联动即推进诊断；非HQ必须先核对诊断已确认且证据有效 |
| 比较复用同键历史Delta不核对冻结数值 | P1，未关闭 | 隔离库将旧Delta baseline_value改999，再比较仍comparable=true；复用前核对所有值/维度，不一致拒绝并保留历史原样 |

此外已报告：bind特殊路径没有持久幂等重放；资料对象当前仅新增无更新，SEO缺rank observation/diagnose入口，不能据此宣称十模块维护操作完整。原核心 Action.note 为no-op，执行反馈必须通过明确持久日志可读。待主审修复后重新独立运行与检查。


### 实现定向修复复验

独立复验确认前三项P1已修复：质量降级后衍生结论被过滤、客户不能用创建Action确认open诊断、三指标历史Delta在任何写入前全预检。绑定重试持久幂等、同渠道不同客户edit_question隔离亦通过。核心质量服务内部提交与报告失效标记共同回滚测试通过。原主审9项真实核心测试独立复跑通过。

新增真实SEO闭环检查：品牌编辑→问题修改→关键词→两次排名观测→原SEO服务诊断→总部确认全部成功；但客户可见该SEO诊断时evidence为空。原因是source及客户证据过滤仅覆盖Observation证据，没有纳入核心SEARCH_RESULT经metadata.rank_observation_id关联的排名证据。此为新增P1，要求按rank/site/keyword.product逐级验证后投影可追溯证据。当前独立7项结果6通过、1失败，实现暂不终审通过。


### 独立实现最终复验结论

**核心/API 独立实现复验通过；本轮已发现P0/P1缺陷均关闭，当前审阅范围未发现剩余阻断项。** 此结论限于已审核心门面、门户权限接口及隔离回归，不替代浏览器/三视口/生产实采验收。

最终独立运行：`python -m pytest tests/test_growth_independent_audit.py tests/test_growth_workspace.py -q --tb=short`，18项全部通过（独立9项 + 主审原9项）。全部以明确临时目录schema-only核心库和隔离门户数据运行。

独立9项证据：
1. 质量APPROVED→HOLD→APPROVED之间没有GET，旧报告仍失效。
2. HOLD来源的Delta和诊断不继续向客户展示。
3. 客户不能通过创建Action推进open诊断。
4. 同键历史Delta与冻结提取值冲突时拒绝比较且不改历史。
5. quality服务内层BEGIN/commit、质量event、快照失效、版本与幂等记录在故障后整体回滚。
6. 品牌与问题真实修改、SEO关键词/两次排名/核心诊断/总部确认后，客户能看到对应排名证据。
7. bind同key重试同结果；同渠道不同客户对象修改404，原对象不变。
8. 采集request_config差异、布尔伪指标均不能生成Delta。
9. 固定快照正文被篡改但hash不变时409，响应不返回正文。

代码复核确认：原核心Diagnosis/Action/Publication/SEO/DataQuality服务仍拥有业务规则；新增门面未调用app.main或硬编码历史Delta脚本；编辑授权每请求复核、Action执行需指派；嵌套site/product范围与报告撤销/来源完整性有服务端门槛；执行note通过独立事件持久化并按总部/本人范围投影。SEO无GEO observation_id的SEARCH_RESULT证据已按rank→keyword→site/product验证并返回。

限制沿用：冻结归因保留legacy全库时间活动干扰的保守结果，不能声称因果；虚拟/人工登记验收证明真实核心服务及结构闭环，不证明已接入实时外部采集或真实客户增长。生产门禁、原始源文件/历史数据hash及浏览器体验，由主审最终验收记录另列。


### 摘要格式约束加固后的最终复验

新增采集request_config_hash和内容发布hash的64位SHA-256格式校验后，独立测试将“不同配置”的第二个样本改成另一合法SHA-256，而不是不合法占位字串，保留“合法但不同配置不可比”的原测试意图。独立9项再次全部通过，结论不变：当前核心/API审阅范围没有剩余已发现P0/P1阻断。事务控制拒绝路径同时置rollback-only及bind重放重新核验绑定属于进一步加固，不放宽原有门槛。


### 关系投影与 SEO 复核日期最终增补复验

独立只读审阅 `growth_core.read` 新增diagnosis_links/action_links：查询起点只使用已完成客户安全投影的可见诊断/行动，随后对每个证据/诊断再做scoped核验；未新增任意对象读取入口，也未改变固定快照或计算。独立回归新增断言：HOLD后两种links均为空，已确认SEO诊断保留证据links，客户看不到其他主体planned行动links。

独立复核SEO Action分支：关联keyword诊断时要求唯一关键词与带时区review_at，调用原seo.create_seo_action，不通过通用Action入口绕过冻结复核日期；缺review_at实测422，合法日期创建成功且actions.review_at实际持久。GEO分支仍复用原Action服务。上述断言合并入现有独立9项，9项再次全部通过，无新增已发现P0/P1阻断。
