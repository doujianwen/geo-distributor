/* One role-aware workspace over canonical Growth objects; no parallel measurements. */
window.GrowthWorkspace = (() => {
  "use strict";
  const sections = {overview:"增长概览",brand:"品牌与网站",questions:"问题与内容",evidence:"测量与证据",diagnoses:"专业诊断",competitors:"竞品与 SEO",actions:"优化行动",publications:"内容发布",monitoring:"监控与验证",reports:"增长报告"};
  const e = v => String(v ?? "").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"})[c]);
  const label = {brand_mention:"品牌是否被提及（0 无 / 1 有）",citation_count:"回答引用数量",recommendation_level:"推荐等级（0–3）",MISSING_FACT:"缺少事实",MISSING_PAGE:"缺少页面",WEAK_CONTENT:"内容支撑不足",CITATION_GAP:"引用缺口",RETRIEVAL_GAP:"检索缺口",TECHNICAL_ACCESS_GAP:"访问受阻",NO_ACTION_REQUIRED:"无需行动",CONTENT_CREATE:"创建内容",CONTENT_UPDATE:"更新内容",FAQ_UPDATE:"完善问答",SCHEMA_UPDATE:"完善结构化数据",FACT_UPDATE:"更新业务事实",INTERNAL_LINK:"内链优化",TECHNICAL_FIX:"技术修复",DISTRIBUTION:"内容分发",manual:"人工登记",answer:"回答原文",SEARCH_RESULT:"搜索排名证据",planned:"待批准",approved:"已批准",in_progress:"执行中",published:"已发布",measured:"已复测",closed:"已关闭",dismissed:"已取消",open:"新发现",confirmed:"已确认",actioned:"已关联行动",resolved:"已解决",pending:"待测量",registered:"已登记测量",completed:"已完成",HOLD:"待质量复核",APPROVED:"质量已复核",REJECTED:"证据不合格",UNVERIFIED:"事实待核实",uncertain:"暂无法归因",attributed:"关联单一行动（非因果）",confounded:"存在混杂因素",invalidated:"来源失效",withdrawn:"已撤回",sandbox:"虚拟演练",live_collection:"平台采集登记"};
  const text=v=>e(label[v]??(v===null||v===undefined||v===""?"待确认":v));
  const card=(title,body)=>`<section class="card"><h2>${e(title)}</h2>${body}</section>`;
  const note=s=>`<p class="notice" role="status">${e(s)}</p>`;
  const key=()=>Array.from(crypto.getRandomValues(new Uint8Array(16)),v=>v.toString(16).padStart(2,"0")).join("");
  let generation=0, storedFilters={}, drafts={}, operationKeys={};
  const field=(name,title,kind="text",options=null,optional=false)=>({name,title,kind,options,optional});
  const f=field;
  const defs={
    bind:["开通新品牌工作区",[f("name","品牌名称"),f("domain","完整网站地址","url")]],
    page:["新增目标页面",[f("url","页面地址","url"),f("title","页面标题")]],
    fact:["新增事实版本",[f("fact_key","事实名称"),f("fact_text","事实内容","textarea"),f("source_ref","事实来源")]],
    question:["新增用户问题",[f("text","用户会提出的问题","textarea"),f("notes","说明","textarea",null,true)]],
    persona:["新增目标人群",[f("name","人群名称"),f("description","描述","textarea"),f("pain_points","主要困扰","textarea"),f("goals","目标","textarea")]],
    scenario:["新增使用场景",[f("name","场景名称"),f("description","场景描述","textarea"),f("stage","决策阶段")]],
    cluster:["新增主题",[f("name","主题名称"),f("parent_topic","上级主题","text",null,true),f("description","主题说明","textarea")]],
    entity:["新增品牌实体",[f("name","实体名称"),f("type","实体类型"),f("description","说明","textarea")]],
    brief:["新增内容任务",[f("title","内容标题"),f("body","内容提纲","textarea"),f("target_url","目标地址","url",null,true),f("content_type","内容形式")]],
    measurement_request:["申请采集或复测",[f("question_id","待测问题","select","questions"),f("note","采集要求与目标时间","textarea")]],
    observation:["登记已采集回答",[f("question_id","对应问题","select","questions"),f("request_id","关联测量申请","select","requests",true),f("provider","平台"),f("model","模型版本"),f("surface","产品入口"),f("language","语言"),f("market","国家或市场"),f("environment","数据环境","select",{sandbox:"虚拟演练",live_collection:"真实平台采集"}),f("question_set_version","问题集版本"),f("collector_version","采集工具版本"),f("request_config_hash","采集配置摘要"),f("started_at","采集开始时间（含时区）"),f("completed_at","采集完成时间（含时区）"),f("observed_at","回答观测时间（含时区）"),f("prompt_text","实际提问原文","textarea"),f("response_text","原始回答全文","textarea"),f("source_url","原始记录地址","url"),f("source_ref","可追溯的来源记录"),f("brand_mentioned","品牌提及（0 无，1 有）","number",null,true),f("citation_count","实际引用数量","number",null,true),f("recommendation_level","推荐等级（0–3）","number",null,true)]],
    quality:["复核证据质量",[f("observation_id","观测记录","select","observations"),f("disposition","复核结果","select",{HOLD:"继续暂缓",APPROVED:"批准使用",REJECTED:"拒绝使用"}),f("reason","判断依据","textarea"),f("evidence_checked","已核验原文与来源","checkbox")]],
    diagnosis:["根据证据创建诊断",[f("question_id","对应问题","select","questions"),f("evidence_ids","支撑证据","multi","evidence"),f("diagnosis_type","诊断类型","select",{MISSING_FACT:"缺少事实",MISSING_PAGE:"缺少页面",WEAK_CONTENT:"内容支撑不足",CITATION_GAP:"引用缺口",RETRIEVAL_GAP:"检索缺口",TECHNICAL_ACCESS_GAP:"访问受阻",NO_ACTION_REQUIRED:"无需行动"}),f("title","诊断标题"),f("finding","发现","textarea"),f("rationale","证据如何支持此判断","textarea"),f("target_context","优化目标（行动使用相同目标）"),f("page_ids","关联页面","multi","pages",true),f("fact_ids","关联事实","multi","facts",true)]],
    diagnosis_status:["更新诊断状态",[f("diagnosis_id","诊断","select","diagnoses"),f("status","目标状态","select",{confirmed:"确认诊断",resolved:"已解决",dismissed:"关闭此发现"})]],
    action:["创建优化行动",[f("diagnosis_ids","关联诊断","multi","diagnoses"),f("action_type","行动类型","select",{CONTENT_CREATE:"新建内容",CONTENT_UPDATE:"更新内容",FAQ_UPDATE:"完善 FAQ",SCHEMA_UPDATE:"结构化数据",FACT_UPDATE:"更新事实",INTERNAL_LINK:"内链",TECHNICAL_FIX:"技术修复",DISTRIBUTION:"分发"}),f("title","行动名称"),f("target_context","优化目标（与诊断一致）"),f("description","执行说明","textarea"),f("body","执行内容","textarea"),f("hypothesis","预期改善的原因","textarea",null,true),f("expected_effect","预期变化","textarea",null,true),f("review_at","复核时间（SEO 行动必填，含时区）","text",null,true),f("page_ids","目标页面","multi","pages",true),f("fact_ids","目标事实","multi","facts",true)]],
    action_status:["推进行动状态",[f("action_id","行动","select","actions"),f("status","目标状态","select",{approved:"批准执行",in_progress:"开始执行",published:"内容已发布",measured:"完成复测校验",closed:"关闭行动",dismissed:"取消行动"}),f("note","处理或执行说明","textarea")]],
    assignment:["指派客户执行",[f("action_id","行动","select","actions"),f("subject","已授权客户编辑","select","subjects")]],
    grant:["设置客户编辑授权",[f("subject","客户编辑身份","select","subjects"),f("enabled","允许维护资料并参与行动","checkbox")]],
    publication:["登记外站发布事实",[f("action_id","对应行动","select","actions"),f("page_id","发布页面","select","pages",true),f("published_url","实际发布地址","url"),f("published_at","实际发布时间（含时区）"),f("title_snapshot","发布时标题"),f("content_hash","发布内容摘要（SHA-256）")]],
    competitor:["维护竞品",[f("name","竞品名称"),f("domain","竞品域名"),f("source","发现来源"),f("notes","观察说明","textarea",null,true)]],
    keyword:["维护 SEO 关键词",[f("name","关键词"),f("search_intent","搜索意图"),f("target_page_id","目标页面","select","pages",true)]],
    compare:["比较基线与复测",[f("baseline","基线批次","select","runs"),f("comparison","复测批次","select","runs"),f("question","同一问题","select","questions")]],
    report:["发布固定增长报告",[f("title","报告标题")]],
    withdraw_report:["撤回增长报告",[f("report_id","报告","select","reports")]],
  };
  defs.brand=["编辑品牌资料",[f("name","品牌名称"),f("market","目标市场"),f("target_customer","目标客户"),f("description","品牌及产品说明","textarea")]];
  defs.rank=["登记搜索排名",[f("keyword_id","关键词","select","keywords"),f("competitor_id","竞品（留空为自身）","select","competitors",true),f("search_engine","搜索引擎","select",{google:"Google",bing:"Bing"}),f("rank","实际排名（未出现请留空）","number",null,true),f("url","观测页面","url",null,true),f("observed_at","观测时间（含时区）"),f("source_observation_id","原始记录编号"),f("notes","来源与核验说明","textarea")]];
  defs.seo_diagnosis=["运行关键词诊断",[f("keyword_id","关键词","select","keywords"),f("search_engine","搜索引擎","select",{google:"Google",bing:"Bing"})]];
  for(const [kind,group] of Object.entries({question:"questions",page:"pages",persona:"personas",scenario:"scenarios",cluster:"clusters",entity:"entities",brief:"briefs"})){
    defs["edit_"+kind]=["修改"+defs[kind][0].replace("新增",""),[f("object_id","选择已有记录","select",group),...defs[kind][1]]];
  }
  const prepare=new Set(["brand",...Object.keys(defs).filter(k=>k.startsWith("edit_")),"page","fact","question","persona","scenario","cluster","entity","brief","measurement_request","action"]);
  async function render(o){
    const gen=++generation, alive=()=>gen===generation&&o.alive();
    const parts=(location.hash.slice(2).split("?")[0]||"growth/overview").split("/");
    const section=sections[parts[1]]?parts[1]:"overview",args=new URLSearchParams(location.hash.split("?")[1]||"");
    const ws=await o.api("GET","/growth/workspace");if(!alive())return;
    let project=ws.projects.find(p=>p.project_id===args.get("project")&&(!args.get("tenant")||p.tenant_id===args.get("tenant")))||ws.projects[0];
    const href=(s,report="")=>`#/growth/${s}?project=${encodeURIComponent(project?.project_id||"")}&tenant=${encodeURIComponent(project?.tenant_id||"")}${report?"&report="+report:""}`;
    const shell=body=>{
      if(!alive())return;
      o.shell("growth",`<div class="growth-workspace">${ws.sandbox?note("交互演练 · 所有品牌、回答与效果均为虚拟构造；操作仅影响演练库，不代表平台实采或商业效果。"):""}<header class="page-heading"><div><p class="eyebrow">GEO 增长工作区</p><h1>${e(sections[section])}</h1><p class="muted">围绕同一品牌，从证据到行动，再到复测验证。</p></div></header><div class="growth-context"><label for="growth-project">客户与项目<select id="growth-project">${ws.projects.map(p=>`<option value="${e(p.tenant_id+"/"+p.project_id)}" ${p===project?"selected":""}>${e(p.client_name+" · "+p.name)}</option>`).join("")}</select></label><p>${e(ws.role.startsWith("END_CUSTOMER")?"当前企业范围":"按已授权的客户与项目展示")} · ${e(ws.role==="END_CUSTOMER_EDITOR"?"客户编辑":ws.role==="END_CUSTOMER"?"客户查看":"")}</p></div><nav class="growth-tabs" aria-label="GEO 功能模块">${Object.entries(sections).map(([s,t])=>`<a href="${e(href(s))}" ${s===section?'aria-current="page" class="on"':""}>${e(t)}</a>`).join("")}</nav><div id="growth-body">${body}</div></div>`);
      document.getElementById("growth-project").onchange=ev=>{
        const p=ws.projects.find(x=>x.tenant_id+"/"+x.project_id===ev.target.value);
        location.hash=`#/growth/${section}?project=${encodeURIComponent(p.project_id)}&tenant=${encodeURIComponent(p.tenant_id)}`;
      };
    };
    if(!project){shell(card("尚无可用项目",note("先在业务工作区建立客户、提交需求并由总部批准项目，再开通增长模块。")));return;}
    const scopedPath="/growth/projects/"+encodeURIComponent(project.project_id);
    const scope=path=>path+(path.includes("?")?"&":"?")+"tenant_id="+encodeURIComponent(project.tenant_id);
    let result;
    try{result=await o.api("GET",scope(scopedPath));}catch(err){if(alive()){shell(card("增长核心暂时无法读取",note(err.message)+'<button class="btn" id="growth-retry">重新读取</button>'));document.getElementById("growth-retry").onclick=o.refresh;}return;}
    if(!alive())return;
    const data=result.data||{},caps=result.capabilities||{};
    data.subjects=result.subjects||[];
    if(ws.readonly)for(const k of Object.keys(caps))if(k!=="read")caps[k]=false;
    const identity=project.tenant_id+"/"+project.project_id+"/"+section;
    const form=(op)=>{
      if(op==='grant')return ''; // Unified account/resource authorization lives in the management page.
      if(op==="bind"?!caps.manage:["grant","assignment"].includes(op)?!caps.manage:op==="quality"?!caps.quality_review:["report","withdraw_report"].includes(op)?!caps.report_publish:prepare.has(op)?!caps.prepare:op==="action_status"?!caps.execute:!caps.professional)return "";
      const [title,fields]=defs[op];
      return `<details class="growth-editor" ${drafts[identity+"/"+op]?"open":""}><summary>${e(title)}</summary><form data-growth-op="${op}"><p class="muted">${op==="observation"?"仅登记已取得的回答；默认为待复核。没有数据的指标请留空，不能填零替代。时间示例：2026-10-19T10:00:00+08:00。":op==="publication"?"记录您已在外站发布的事实，不会自动向外部发布内容。":op==="action_status"&&!caps.professional?"只能开始执行总部已指派给您的批准行动。":op==="grant"?"此授权与登录身份绑定，可随时撤销。":"提交后保存到唯一增长核心，所有操作可追溯。"}</p><div class="growth-fields">${fields.map(x=>{
        let options=x.options;if(typeof options==="string")options=data[options]||[];
        const saved=drafts[identity+"/"+op]?.[x.name];
        let input;
        if(x.kind==="select"||x.kind==="multi"){
          if(x.name==="status"&&op==="action_status"&&!caps.professional)options={in_progress:"开始执行"};
          const entries=Array.isArray(options)?options.map(r=>[r.subject||r.id,r.label||r.title||r.text||r.name||r.url||r.fact_key||(x.options==="observations"?"观测 "+r.id+" · "+text(r.quality):x.options==="runs"?"批次 "+r.id+" · "+(r.started_at||"")+" · "+text(r.environment):"记录 "+r.id)]):Object.entries(options||{});
          input=`<select name="${x.name}" ${x.kind==="multi"?"multiple size=3":""} ${x.optional?"":"required"}><option value="">${x.optional?"暂不关联":"请选择"}</option>${entries.map(([v,t])=>`<option value="${e(v)}" ${Array.isArray(saved)?saved.includes(String(v))?"selected":"":String(saved)===String(v)?"selected":""}>${e(t)}</option>`).join("")}</select>`;
        }else if(x.kind==="textarea")input=`<textarea name="${x.name}" rows="3" maxlength="${x.name==="response_text"||x.name==="body"?20000:3000}" ${x.optional?"":"required"}>${e(saved||"")}</textarea>`;
        else if(x.kind==="checkbox")input=`<input type="checkbox" name="${x.name}" ${saved?"checked":""}>`;
        else input=`<input name="${x.name}" type="${x.kind}" value="${e(saved??"")}" maxlength="3000" ${x.kind==="number"?'min="0" step="1"':""} ${x.optional?"":"required"}>`;
        return `<label>${e(x.title)}${x.optional?"（可留空）":""}${input}<span class="field-error" data-error="${x.name}"></span></label>`;
      }).join("")}</div><div role="alert" class="growth-error"></div><button class="btn" type="submit">${e(title)}</button></form></details>`;
    };
    const list=(title,key,cols)=>card(title,`<div class="growth-list" data-list="${key}"><label>搜索${e(title)}<input type="search" data-search="${key}" value="${e(storedFilters[identity+key]?.q||"")}" placeholder="名称、状态或关键词"></label><div class="growth-rows"></div><div class="pagination"><button class="btn ghost" data-page="-1">上一页</button><span class="growth-page"></span><button class="btn ghost" data-page="1">下一页</button></div></div>`);
    const lists={};
    const L=(title,k,cols)=>{lists[k]=cols;return list(title,k,cols);};
    let body="";
    if(!result.bound){body=card("开通增长核心",note(result.message)+form("bind"));}
    else if(section==="overview"){
      body=card(data.site.name,`<p>${e(data.site.domain)}</p><div class="growth-stats">${[["用户问题",data.questions.length],["测量批次",data.runs.length],["证据诊断",data.diagnoses.length],["优化行动",data.actions.length]].map(([t,v])=>`<div><strong>${v}</strong><span>${e(t)}</span></div>`).join("")}</div><p>当前工作区版本 ${data.revision}。这些是对象数量，不是项目完成率或增长分数。</p>`)+card("下一步",`<ol><li><a href="${e(href("brand"))}">核对品牌、页面与业务事实</a></li><li><a href="${e(href("questions"))}">维护问题和内容方向</a></li><li><a href="${e(href("evidence"))}">申请测量并核验证据</a></li><li><a href="${e(href("actions"))}">执行有证据支撑的优化行动</a></li><li><a href="${e(href("monitoring"))}">复测并查看可比性与归因边界</a></li></ol>`)+card("数据使用说明",result.limits.map(note).join(""))+form("grant")+L("本工作区处理记录","events",["operation","note","created_at"]);
    }else if(section==="brand")body=card("品牌资料",`<p>${e(data.product.name)}</p><p>${e(data.product.market||"市场待确认")}</p><p>${e(data.product.target_customer||"目标客户待确认")}</p><p>${e(data.product.description||"产品说明待补充")}</p>`)+form("brand")+L("目标页面","pages",["title","url","status"])+form("page")+form("edit_page")+L("业务事实及版本","facts",["fact_key","fact_text","status","version","source_ref"])+form("fact")+L("品牌实体","entities",["name","type","description"])+form("entity")+form("edit_entity");
    else if(section==="questions")body=L("用户问题","questions",["text","notes","source"])+form("question")+form("edit_question")+L("目标人群","personas",["name","description","pain_points","goals"])+form("persona")+form("edit_persona")+L("使用场景","scenarios",["name","description","stage"])+form("scenario")+form("edit_scenario")+L("内容主题","clusters",["name","parent_topic","description"])+form("cluster")+form("edit_cluster")+L("内容任务","briefs",["title","body","status","target_url"])+form("brief")+form("edit_brief");
    else if(section==="evidence")body=L("测量申请","requests",["question_id","note","status","run_id"])+form("measurement_request")+L("测量批次","runs",["started_at","provider","model","environment","status"])+form("observation")+L("回答与质量","observations",["prompt_text","response_text","quality","observed_at"])+form("quality")+L("证据来源","evidence",["evidence_type","observation_id","rank_observation_id","source_url","snippet"]);
    else if(section==="diagnoses")body=note("诊断基于已复核证据。新发现、确认、关联行动和解决分别记录。")+L("诊断记录","diagnoses",["title","diagnosis_type","finding","rationale","status"])+form("diagnosis")+form("diagnosis_status")+L("诊断的证据来源","diagnosis_links",["diagnosis","evidence"]);
    else if(section==="competitors")body=L("竞品档案","competitors",["name","domain","source","notes"])+form("competitor")+L("SEO 关键词","keywords",["name","search_intent","target_page_id"])+form("keyword")+L("搜索排名观测","rank_observations",["keyword_id","search_engine","rank","url","observed_at","source"])+form("rank")+form("seo_diagnosis")+note("未采集排名或竞品表现时不显示零值或构造排行榜；档案本身不代表竞品优劣。");
    else if(section==="actions")body=L("优化行动","actions",["title","action_type","description","body","target_context","status"])+form("action")+form("action_status")+form("assignment")+L("行动的诊断依据","action_links",["action","diagnosis"]);
    else if(section==="publications")body=note("内容发布记录与报告发布分别管理。登记外站发布需要地址、时间、标题和内容摘要四项快照。")+L("内容发布记录","publications",["action_id","published_url","published_at","title_snapshot","content_hash","publication_status"])+form("publication");
    else if(section==="monitoring")body=note("仅比较同一问题、同等采集条件且质量合格的观测。缺失、不可比、无变化分别表达；不把变化当作因果。")+form("compare")+L("可比性检查记录","comparisons",["baseline","comparison","question","result"])+L("指标变化及归因","deltas",["metric_name","baseline_value","comparison_value","delta_value","attribution_status"]);
    else if(section==="reports"){
      if(args.get("report")){
        const r=await o.api("GET",scope(scopedPath+"/reports/"+encodeURIComponent(args.get("report"))));if(!alive())return;
        body=reportHTML(r)+`<button class="btn" id="growth-print">打印 / 保存 PDF</button> <a class="btn ghost" href="${e(href("reports"))}">返回报告列表</a>`;
      }else body=L("固定增长报告","reports",["title","created_at","status","reason"])+form("report")+form("withdraw_report");
    }
    shell(body);if(!alive())return;
    if(document.getElementById("growth-print"))document.getElementById("growth-print").onclick=()=>window.print();
    Object.entries(lists).forEach(([k,cols])=>{
      const host=document.querySelector(`[data-list="${k}"]`),state=storedFilters[identity+k]||={q:"",page:1};
      const draw=()=>{
        const items=(data[k]||[]).filter(r=>JSON.stringify(r).toLowerCase().includes(state.q.toLowerCase())),max=Math.max(1,Math.ceil(items.length/20));state.page=Math.min(max,Math.max(1,state.page));
        host.querySelector(".growth-rows").innerHTML=items.slice((state.page-1)*20,state.page*20).map(r=>`<article class="growth-item">${cols.map(c=>`<p><strong>${e(names[c]||c)}：</strong>${c==="result"?e(formatComparison(r[c])):text(r[c])}</p>`).join("")}${k==="reports"&&r.valid?`<a class="btn ghost" href="${e(href("reports",r.id))}">阅读报告</a>`:""}</article>`).join("")||'<p class="empty">暂无符合条件的记录；这不代表指标为零。</p>';
        host.querySelector(".growth-page").textContent=`${items.length} 条 · ${state.page} / ${max}`;
        host.querySelector('[data-page="-1"]').disabled=state.page===1;host.querySelector('[data-page="1"]').disabled=state.page===max;
      };
      host.querySelector("input").oninput=ev=>{state.q=ev.target.value;state.page=1;draw();};host.querySelectorAll("[data-page]").forEach(b=>b.onclick=()=>{state.page+=Number(b.dataset.page);draw();});draw();
    });
    document.querySelectorAll("form[data-growth-op]").forEach(formEl=>{
      const op=formEl.dataset.growthOp,id=identity+"/"+op;
      const collect=()=>{
        const values={};defs[op][1].forEach(x=>{const el=formEl.elements[x.name];values[x.name]=x.kind==="multi"?Array.from(el.selectedOptions).map(x=>x.value).filter(Boolean):x.kind==="checkbox"?el.checked:el.value;});drafts[id]=values;return values;
      };
      formEl.oninput=()=>{collect();o.dirty(true);};
      formEl.onchange=ev=>{
        if(op.startsWith("edit_") && ev.target.name==="object_id"){
          const group=defs[op][1][0].options,item=(data[group]||[]).find(r=>r.id===Number(ev.target.value));
          if(item)defs[op][1].slice(1).forEach(x=>{formEl.elements[x.name].value=item[x.name]||"";});
        }
        formEl.oninput();
      };
      formEl.onsubmit=async ev=>{
        ev.preventDefault();const payload=collect();
        defs[op][1].forEach(x=>{if(payload[x.name]===""&&x.optional)delete payload[x.name];else if(x.kind==="number")payload[x.name]=Number(payload[x.name]);else if(x.kind==="multi")payload[x.name]=payload[x.name].map(Number);else if(x.name.endsWith("_id")||["baseline","comparison","question"].includes(x.name))payload[x.name]=payload[x.name]?Number(payload[x.name]):null;});
        const version=data.revision||0,fingerprint=JSON.stringify({version,payload});
        if(operationKeys[id]?.fingerprint!==fingerprint)operationKeys[id]={fingerprint,key:key()};
        const button=formEl.querySelector('button[type="submit"]'),error=formEl.querySelector(".growth-error");button.disabled=true;error.textContent="";
        try{
          const response=await o.api("POST",scope(scopedPath+"/"+op),{revision:version,payload},{"Idempotency-Key":operationKeys[id].key});
          if(!alive())return;
          delete drafts[id];delete operationKeys[id];o.dirty(false);
          if(response.comparable===false){error.textContent="已记录不可比原因："+response.reason;button.disabled=false;data.revision=response.revision;return;}
          o.refresh();
        }catch(err){if(!alive())return;error.textContent=err.message+"。输入已保留，请核对后重试。";const refresh=document.createElement("button");refresh.type="button";refresh.className="btn ghost";refresh.textContent="读取最新状态并保留输入";refresh.onclick=()=>{o.dirty(false);o.refresh();};error.append(refresh);error.tabIndex=-1;error.focus();button.disabled=false;}
      };
    });
  }
  function reportHTML(r){
    const d=r.data;
    const records=(items,render)=>items.length?items.map(x=>`<div class="growth-item">${render(x)}</div>`).join(""):"<p>本版暂无已确认记录，不代表指标为零。</p>";
    return `<article class="growth-report"><p class="eyebrow">GEO 增长报告 · 固定交付快照</p><h1>${e(r.title)}</h1><p>${e(d.site.name)} · ${e(d.site.domain)}</p><p>发布于 ${e(r.created_at)} · 报告版本 ${r.id}</p>${note(r.limits)}${card("业务摘要",`<p>本版覆盖 ${d.questions.length} 个问题、${d.runs.length} 个测量批次、${d.observations.length} 条回答观测，关联 ${d.diagnoses.length} 项发现及 ${d.actions.length} 项行动；另含 ${d.rank_observations.length} 条搜索排名观测。</p><p>项目验收、内容发布、复测完成分别判断；本报告不将行动状态换算为项目完成率。</p>`)}${card("发现与建议",records(d.diagnoses,x=>`<h3>${e(x.title||"证据诊断")}</h3><p>${text(x.diagnosis_type)} · ${text(x.status)}</p><p>${e(x.finding||"发现待补充")}</p><p>判断依据：${e(x.rationale||"待核验")}</p>`))}${card("优化行动",records(d.actions,x=>`<h3>${e(x.title)}</h3><p>${text(x.action_type)} · ${text(x.status)}</p><p>${e(x.description||"执行说明待补充")}</p><p>预期变化：${e(x.expected_effect||"未设置，不作效果承诺")}</p>`))}${card("复测变化与归因",records(d.deltas,x=>`<h3>${text(x.metric_name)}</h3><p>基线 ${text(x.baseline_value)} → 复测 ${text(x.comparison_value)}；变化 ${text(x.delta_value)}</p><p>${text(x.attribution_status)}</p><p>仅描述对应问题的观测差异，不证明行动导致增长。</p>`))}${card("测量范围与数据质量",records(d.runs,x=>`<p>${e(x.provider)} · ${e(x.model)} · ${e(x.language)} · ${e(x.market)}</p><p>${text(x.environment)} · ${text(x.status)}</p><p>${e(x.started_at)} 至 ${e(x.completed_at)}</p>`))}${card("搜索排名观测",records(d.rank_observations,x=>`<p>${e(x.search_engine)} · ${e(x.observed_at)}</p><p>实际排名：${x.rank===null?"未出现排名，不记为零":text(x.rank)}</p><p>${e(x.url||"观测页面待确认")}</p><p>${text(x.source)}；单条记录不能代表趋势。</p>`))}${card("证据摘录与来源",records(d.observations,x=>`<h3>${e(x.prompt_text)}</h3><p>${e((x.response_text||"").slice(0,3000))}</p><p>${text(x.quality)} · ${e(x.observed_at)}</p>`)+records(d.evidence,x=>`<p>${text(x.evidence_type)}：${e(x.source_url||x.snippet||"来源待确认")}</p>`))}${card("内容发布事实",records(d.publications,x=>`<p>${e(x.title_snapshot)}</p><p>${e(x.published_url)}</p><p>${e(x.published_at)} · ${text(x.publication_status)}</p>`))}${card("范围与局限","<p>单个问题与有限样本不能代表整体趋势。未采集或缺失的数据不计为零；存在不同条件或质量问题的观测不进入数值比较。归因表示窗口内关联，不证明因果。虚拟演练内容不代表真实平台采集或商业效果。</p>")}<p class="small muted">来源快照摘要：${e(r.source_hash)}</p></article>`;
  }
  function formatComparison(raw){try{const r=JSON.parse(raw);return r.comparable?"采集条件通过；已生成 "+r.delta_ids.length+" 条既有口径变化记录":"不可比较："+r.reason;}catch{return "检查记录待核对";}}
  const names={diagnosis:"关联诊断",evidence:"证据摘录",action:"关联行动",operation:"操作",rank:"实际排名",evidence_type:"证据类型",rank_observation_id:"排名记录",keyword_id:"关键词",search_engine:"搜索引擎",title:"名称",name:"名称",url:"地址",domain:"域名",status:"状态",source:"来源",notes:"说明",text:"问题",description:"说明",body:"执行内容",target_url:"目标地址",stage:"阶段",pain_points:"困扰",goals:"目标",parent_topic:"上级主题",type:"类型",fact_key:"事实",fact_text:"内容",version:"版本",source_ref:"来源记录",started_at:"开始时间",provider:"平台",model:"模型",environment:"环境",prompt_text:"实际问题",response_text:"原回答",quality:"质量",observed_at:"观测时间",source_url:"原始来源",snippet:"证据摘录",finding:"发现",rationale:"判断依据",diagnosis_type:"诊断类型",action_type:"行动类型",target_context:"优化目标",published_url:"发布地址",published_at:"发布时间",title_snapshot:"发布标题",content_hash:"内容摘要",publication_status:"发布状态",search_intent:"搜索意图",baseline:"基线批次",comparison:"复测批次",question:"问题",result:"检查结果",metric_name:"指标",baseline_value:"基线值",comparison_value:"复测值",delta_value:"变化",attribution_status:"归因判断",created_at:"生成时间",reason:"说明",question_id:"关联问题",run_id:"采集批次",action_id:"关联行动",observation_id:"关联观测",target_page_id:"目标页面",note:"要求"};
  return {render,discard(){generation++;drafts={};operationKeys={};},clear(){generation++;drafts={};operationKeys={};storedFilters={};}};
})();
