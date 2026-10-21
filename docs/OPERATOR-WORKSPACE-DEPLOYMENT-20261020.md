# 专业作业台配置与受控接入说明

> 2026-10-20 后续本机接入已执行，见 [真实接入验收](REAL-IDENTITY-HISTORY-ACCEPTANCE-20261020.md)。本机当前真实服务使用原历史核心库；空库和演练库不是真实历史真源。下文“本轮没有执行”的配置描述保留为此前时点，公网部署仍未执行。

日期：2026-10-20。与 V2.2 唯一执行指令及实施验收记录配套，不替代生产门禁。

## 本地演练

在 geo-distributor 目录运行 `scripts/start_growth_sandbox.ps1`。默认入口 `http://127.0.0.1:17669/ui/lab/`，仅绑定环回地址。若端口已占用，脚本确认所属进程后复用；不是本服务则拒绝覆盖。不要结束其他服务以抢占端口。

演练库为 `data/growth-sandbox/growth.db`，商业演练数据在 `data/growth-sandbox/portal-demo/`。所有案例均为虚拟。`credentials.local.json` 是仅服务器使用的随机凭据文件，不放报告、不提交版本库、不发给用户。演练角色按钮不能复制到正常登录流程。

只在隔离脚本中使用较高的请求限额（300 次/分钟、突发 100）；真实服务默认限额不随演练修改。出现 429 时等待后重试，不能当作空结果或自动创建另一份记录。

## 真实配置（本轮没有执行）

| 配置 | 用途 |
|---|---|
| `GEO_GROWTH_CORE_ROOT` | 指向唯一受控 geo-intent-system 源码根目录 |
| `GEO_GROWTH_WORKSPACE_DB` | 明确的工作区数据库路径；不是随意填写原真实历史库路径 |
| `GEO_IDENTITY_DB` | 独立身份数据库；不能与增长工作库或原核心数据库相同 |
| `GEO_IDENTITY_SECRET` | 至少 32 字节的服务端签名密钥，需与 WordPress 端一致 |
| `GEO_IDENTITY_ISSUER` | WordPress `home_url()` 去尾斜杠后的精确地址 |
| WordPress `GEO_WORKSPACE_IDENTITY_SECRET` | 与上述身份密钥一致，仅服务器配置 |
| WordPress `GEO_WORKSPACE_API_URL` | 受信任的服务端 API 根地址，插件追加 `/identity/exchange` |
| WordPress `GEO_WORKSPACE_CALLBACK_URL` | 固定工作区 `/ui/account/enter` HTTPS 地址 |

不在文档填入密钥值。门户商业服务需使用持久化 SQLite 配置及现有认证注册表。真实部署不能设置 `GEO_GROWTH_SANDBOX=1` 或使用测试服务账号例外 `GEO_OPERATOR_ALLOW_SERVICE_ACTORS=1`；后者只供隔离验收，不是用户个人账号替代方案。

真实 HTTPS 部署同时设置 `GEO_DISTRIBUTOR_COOKIE_SECURE=1`，确认反向代理回调路径、Cookie 范围和缓存策略正确；本地 HTTP 演练默认值不能沿用于公网。

新增 WordPress mu-plugin 为 `wp-content/mu-plugins/geo-workspace-identity.php`。只有访问 `?geo_workspace_login=1` 时触发交接；可用 `[geo_workspace_login]` 放置个人账号入口。密码仍由 WordPress 验证，不依据 WordPress 角色推断总部或客户权限。服务端密钥未配置时提示未开通，不静默切到演练。

## 开通与验收次序

1. 备份配置、商业库、工作库、身份库和当前源码。明确资源归属；原历史接入另批执行。
2. 部署兼容源码与受控适配文件，保留原核心代码。`app/operator_contract.py` 对原 `main.py`、`keywords.py`、`seed.py` 校验固定哈希，仅加载白名单具名定义；原文件变更会拒绝服务，不能通过删除校验继续运行。
3. 配置服务端身份交接，验证新个人登录处于待开通状态。总部通过现有受控管理员引导入口处理申请，明确租户、客户及角色，不通过前端选择角色获取权限。
4. 总部创建/选择项目产品站点，在权限页选择具体个人及具体资源，分别授予 read、prepare、operate、execute_assigned、quality_review、report_publish。新资源不自动继承授权。
5. 按验收报告的真实账号门槛逐项验证。特别验证总部运营不能读取未授权项目、客户不能跨客户/站点、撤权后旧页面不能提交、自录者不能自行复核。
6. 完成人类优化人员试用、旧入口写路径隔离与回退对账后，才进入既有生产裁决流程。

## 回退与故障处理

- 优先撤销相应个人资源操作权或停止目标项目写入，保留历史读取，不靠隐藏导航作为禁写措施。
- 回退需停止工作区写流量后恢复同一版本源码与匹配配置；新增领域数据保留待对账，不直接删除新表或覆盖原客户库。
- 商业停止/成员撤销与短命令的锁顺序是身份→商业→核心；不得在持锁区域添加外部模型/网络长任务。跨库不宣称具备断电全局原子性；异常恢复需核对事件及操作幂等记录。
- 接口 401 重新登录；403 核对明确授权；409 保留输入、刷新核对版本；429 等待；5xx/断网沿用原操作重试，不另建一份。前端已保留结果不明操作的幂等标识。
- 源码哈希不一致时停止该适配入口，升级白名单和操作矩阵并重新验收；受控界面副本也需随原核心变化评审，不能未经核对自动覆盖。
- 若发现历史归属冲突，先拒绝接入，列明映射冲突，不用演示数据补齐或修饰真实状态。
