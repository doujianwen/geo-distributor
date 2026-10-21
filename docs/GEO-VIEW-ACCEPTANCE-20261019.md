# GEO 查看与虚拟演示验收

2026-10-19。本机实施验收通过；生产部署与真实客户效果验证不在本次通过范围。

## 使用入口
- 正常登录页 http://geo-growth.local/portal/ 增加“进入虚拟案例演示”，已登录页同样可切换。
- 独立演示 http://127.0.0.1:8767/ui/ ，点击“进入虚拟案例演示”，无需输入密钥。
- 客户→查看 GEO 效果，或项目→查看 GEO 效果与依据；演示横幅提供返回真实工作区。
- 展示报告 exports/geo-view-20261019/geo-demo-report.pdf（2页，每页虚拟水印）。
- 服务启动：先 scripts/start_portal_demo.ps1，再 scripts/start_portal_local.ps1；各脚本对已有监听端口拒绝覆盖。当前两服务均已启动。仅本机回环访问，不能把127.0.0.1链接当公网链接发给其他电脑。

## 覆盖矩阵
|能力/门槛|实现与证据|结论|
|---|---|---|
|所属客户GEO可见|客户/项目入口；安全批次接口，41项专项测试含跨租户401/403/404|通过|
|效果/历史/可比范围|品牌提及、推荐、回答引用可用率；历史表与批次；同范围多重采样签名和百分点差，缺失不比较|通过|
|依据/竞品/建议|问题、平台、时间、状态、明确发布摘要、白名单引用与竞品；已发布报告发现明确来源；未发布分类说明|通过|
|零值/未知/空/失败|三虚拟客户、四批次；完整0、部分失败/UNKNOWN、未采集；真实浏览器逐一验证|通过|
|真实路径可达|HTTP实际采集fixture有时区→主指标→明确关联报告；重放不改报告|通过|
|旧通路同等保护|旧原始measurements只允许HQ；客户portal安全投影+持久化；report列表/详情/portal统一is_client_safe|通过|
|演示隔离|独立库、独立tenant/cookie、仅viewer随机服务端key，禁真实key注册表；所有业务写403|通过|
|持久化/幂等/双会话|种子重复不增数据；真实进程重启重新种子后原批次保留；httpx同host双cookie共存，演示退出后主会话仍有效|通过|
|真实库不变|real-db-before.json与real-db-after.json，六张业务表逐表数量与payload SHA256一致|通过|
|读错/401/返回|Tabbit模拟503重试与返回项目、模拟401重新演示登录恢复GEO原路由，过滤返回后保留|通过|
|三视口/键盘|实际CSS宽1440/768/390无整页横溢出；筛选/搜索/批次切换；键盘Enter展开手机导航|通过|
|打印|原生浏览器A4打印，2页；固定水印修复后每页文本确认，并渲染PNG检查|通过|
|核心冻结|核心aggregate_metrics和delivery源文件未改，测量/归因计算未重建|通过|

## 测试与审计证据
- 90项相关自动测试全通过：test_geo_business_view、test_portal_workflow、test_channel_portal_service_intake_fields、test_leads_intake、test_security_red_team、test_redteam_idempotency、security/test_rbac_final。结果 exports/geo-view-20261019/tests.xml。
- 独立审计初次不通过，B1—B4定向修复后独立运行41项专项测试并通过。链路记录 GEO-VIEW-REVIEW-20261019.md；唯一正式执行指令 GEO-VIEW-EXECUTION-20261019.md。
- runtime-checks.json、real-db-before/after.json记录实际服务核验。所有秘密值均未写验收产物。
- 浏览器后台截图两次超时，未把空白截图当证据。改用真实浏览器在screen媒体样式下按目标宽度导出PDF，再渲染检查布局；geo-screen-*.pdf和geo-*-page-*.png。该证据是屏幕样式页面导出，不是前台原生截图。桌面首次加载中导出已被最后版本替换；以带page编号的最终图片为准。
- 对外打印文件和两张print-page图片为最后版本，确认每页水印。源字段fictional-demo在页面转换为“虚拟构造数据”。

## 当前边界
示例中的25%→75%及+50个百分点全部人为构造，不是增长实证。没有发布的SEO、行动/归因与商业转化数据保持空说明。原始回答、内部metadata和采集配置不向渠道显示。演示不导入真实库、不自动补历史线索，不发外部通知。新正式测量在证据完整时可展示；历史时间/状态/口径不足时仍降级，不编造数据。

演示种子仅能写专用portal-demo目录并拒绝非演示租户及ID；本轮已存在虚拟库的语言字段从English定向改为Chinese，使其与中文虚拟查询一致，仅更改虚拟数据。真实历史报告未改写。
