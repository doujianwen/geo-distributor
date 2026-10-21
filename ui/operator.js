/* The professional native workbench shares identity, scope and the canonical write boundary. */
window.OperatorWorkspace = (() => {
  "use strict";
  let generation=0, disposeCurrent=null;
  const e=v=>String(v??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"})[c]);
  const key=()=>Array.from(crypto.getRandomValues(new Uint8Array(16)),v=>v.toString(16).padStart(2,"0")).join("");
  const views=new Set(["dashboard","products","personas","scenarios","questions","clusters","briefs","citations","trends","entities","gaps","keywords","seo","prompts","manual"]);
  async function render(o){
    disposeCurrent?.();
    const gen=++generation,alive=()=>gen===generation&&o.alive();
    const route=location.hash.slice(2).split("?")[0].split("/"),view=views.has(route[1])?route[1]:"dashboard";
    const args=new URLSearchParams(location.hash.split("?")[1]||"");
    let ws;
    try{ws=await o.api("GET","/growth/workspace");}catch(error){if(alive())o.shell("operator",`<section class="card"><h1>专业作业台暂时无法读取</h1><p role="alert">${e(error.message)}</p><button id="operator-retry" class="btn">重试</button></section>`);document.getElementById("operator-retry")?.addEventListener("click",o.refresh);return;}
    if(!alive())return;
    ws.projects=ws.projects.filter(p=>p.capabilities?.operate);
    const project=ws.projects.find(p=>String(p.project_id)===args.get("project")&&(!args.get("tenant")||String(p.tenant_id)===args.get("tenant")))||ws.projects[0];
    if(!project){o.shell("operator",'<section class="card"><h1>专业作业台</h1><p>尚无已授权项目。请联系管理员分配项目及作业权限。</p></section>');return;}
    const base="/growth/projects/"+encodeURIComponent(project.project_id);
    let selectedSite="",resources=[];
    const scoped=path=>path+(path.includes("?")?"&":"?")+"tenant_id="+encodeURIComponent(project.tenant_id)+(selectedSite?"&workspace_site_id="+encodeURIComponent(selectedSite):"");
    let context;
    try{
      resources=((await o.api("GET",scoped(base+"/resources"))).resources||[]).filter(r=>r.capabilities?.operate);
      if(!resources.length)throw new Error("该项目尚无授予您的专业作业资源，请联系总部配置具体产品与站点权限。");
      const resource=args.get("site")?resources.find(r=>String(r.site_id)===args.get("site")):resources[0];
      if(args.get("site")&&!resource)throw new Error("该产品与站点不在当前授权项目内，请返回项目重新选择。");
      selectedSite=resource?String(resource.site_id):"";
      context=await o.api("GET",scoped(base+"/operator/context"));
    }catch(error){if(alive()){o.shell("operator",`<section class="card"><h1>专业作业台尚未就绪</h1><p role="alert">${e(error.message)}</p><a class="btn" href="#/growth/overview?project=${encodeURIComponent(project.project_id)}&tenant=${encodeURIComponent(project.tenant_id)}&site=${encodeURIComponent(selectedSite)}">查看项目与资源绑定</a> <button class="btn ghost" id="operator-retry">重新读取</button></section>`);document.getElementById("operator-retry").onclick=o.refresh;}return;}
    if(!alive())return;
    const channel=key(),identity=String(project.tenant_id)+"/"+String(project.project_id),objectVersions={...(context.object_versions||{})};
    o.shell("operator",`<section class="operator-workspace"><header class="operator-heading"><div><p class="eyebrow">GEO 内容增长系统</p><h1>专业作业台</h1><p>保留原有 15 个模块与直接作业流程，围绕当前授权产品工作。</p></div><div class="operator-help-links"><a class="btn ghost" href="#/growth/overview?project=${encodeURIComponent(project.project_id)}&tenant=${encodeURIComponent(project.tenant_id)}&site=${encodeURIComponent(selectedSite)}">测量与交付</a><a class="btn ghost" href="${String(ws.role||"").startsWith("END_CUSTOMER")?"#/overview?project="+encodeURIComponent(project.project_id):"#/projects/"+encodeURIComponent(project.project_id)}">项目详情</a></div></header><div class="operator-context"><label for="operator-project">客户与项目<select id="operator-project">${ws.projects.map(p=>`<option value="${e(p.tenant_id+"/"+p.project_id)}" ${p===project?"selected":""}>${e(p.client_name+" · "+p.name)}</option>`).join("")}</select></label><label for="operator-resource">产品与站点<select id="operator-resource">${resources.map(r=>`<option value="${e(r.site_id)}" ${String(r.site_id)===selectedSite?"selected":""}>${e(r.name+" · "+r.domain)}</option>`).join("")}</select></label><p>${ws.sandbox?"交互演练：所有案例与数据均为虚拟构造。":"当前仅显示服务器核准绑定的产品与站点。"} 自动模型、实时外采及物理删除尚未开放。</p></div><p class="operator-status" id="operator-status" role="status">正在加载原生作业界面…</p><iframe class="operator-frame" id="operator-frame" title="GEO 专业作业台：15 个原生作业模块" sandbox="allow-scripts allow-modals" referrerpolicy="no-referrer"></iframe></section>`);
    document.querySelector('label[for="operator-project"]').firstChild.textContent='切换项目（客户 / 业务）';
    document.querySelector('.operator-context').insertAdjacentHTML('beforebegin',`<section class="operator-project-guide"><strong>当前项目：${e(project.client_name)}</strong><p>要切换业务，请点击下方项目名称或使用“切换项目”下拉框。问句库、问题簇等 15 个模块会一起切换到所选项目。</p>${ws.projects.length<=6?`<nav aria-label="切换项目" class="operator-project-shortcuts">${ws.projects.map(p=>`<button type="button" class="btn ${p===project?'':'ghost'}" data-switch-project="${e(p.tenant_id+'/'+p.project_id)}" ${p===project?'disabled aria-current="true"':''}>${e(p.client_name)}</button>`).join('')}</nav>`:''}</section>`);
    const frame=document.getElementById("operator-frame"),status=document.getElementById("operator-status");
    let queue=Promise.resolve(),unknown=null,closed=false,conflicted=false,currentView=view;
    function reply(id,result,error){if(alive()&&!closed)frame.contentWindow.postMessage({source:"geo-operator-host",channel,type:"response",id,result,error},"*");}
    async function request(message){
      const {method,path,body}=message;
      if(!["GET","POST","PUT","DELETE"].includes(method)||typeof path!=="string"||!path.startsWith("/")||path.startsWith("//")||path.includes("..")||path.includes("#")){reply(message.id,null,"无效的作业请求");return;}
      const write=method!=="GET",fingerprint=JSON.stringify([method,path,body]);
      const objectPath=path.split("?")[0].replace(/^\//,"").replace(/^products\/\d+\/keywords\/(\d+)$/,"keywords/$1");
      if(write&&conflicted){reply(message.id,null,"工作区已被其他人员修改，请复制保留当前输入并刷新页面，核对最新记录后再提交。");return;}
      if(write&&unknown&&unknown.fingerprint!==fingerprint){reply(message.id,null,"上次操作结果尚未确认，请先重试原操作，避免重复或顺序错乱。");return;}
      const operation=write?(unknown||{fingerprint,key:key(),revision:context.revision,objectVersion:objectVersions[objectPath]}):null;
      if(write){unknown=operation;status.textContent="正在保存；请等待确认后继续操作。";}
      let committed=false;
      try{
        const result=await o.api(method,scoped(base+"/operator/api"+path),body,write?{"If-Match":String(operation.revision),"Idempotency-Key":operation.key,...(method==="PUT"&&operation.objectVersion?{"If-Match-Object":operation.objectVersion}:{})}:{});
        committed=write;
        if(!alive())return;
        if(write){context=await o.api("GET",scoped(base+"/operator/context"));if(context.object_versions?.[objectPath])objectVersions[objectPath]=context.object_versions[objectPath];unknown=null;o.dirty?.(false);}
        else {
          const collection=objectPath.split("/").at(-1);
          if(Array.isArray(result)){for(const row of result)if(row?.id&&row._version)objectVersions[collection+"/"+row.id]=row._version;}
          else if(result?._version)objectVersions[objectPath]=result._version;
        }
        status.className="operator-status";status.textContent=write?"保存成功 · 当前资源版本 "+context.revision:"当前产品与站点已授权 · 版本 "+context.revision;
        reply(message.id,result);
      }catch(error){
        if(!alive())return;
        const uncertain=Number(error.status)>=500||error instanceof SyntaxError||error.message==="Failed to fetch"||/超时|timeout|network|fetch/i.test(error.message);
        if(write&&!uncertain&&!committed)unknown=null;
        status.className="operator-status error";status.textContent=error.message;
        if(/版本冲突|版本已|其他人修改|其他人员修改|stale|revision conflict|重新加载|刷新/i.test(error.message)){conflicted=true;status.textContent=error.message+" 请保留输入并刷新核对后再提交。";}
        reply(message.id,null,error.message);
      }
    }
    const listener=event=>{
      const m=event.data;
      if(!alive()||closed||event.source!==frame.contentWindow||!m||m.channel!==channel||m.source!=="geo-operator-frame")return;
      if(m.type==="ready"){frame.contentWindow.postMessage({source:"geo-operator-host",channel,type:"init"},"*");status.textContent="当前产品与站点已授权 · 版本 "+context.revision;}
      if(m.type==="api"){
        if(m.method==="GET")void request(m);else queue=queue.then(()=>request(m)).catch(()=>{});
      }
      if(m.type==='paged'){
        void (async()=>{
          try{
            if(!['questions','keywords','briefs','monitors','citations','content-gaps','entities','personas','scenarios','clusters'].includes(m.collection))throw new Error('无效列表');
            const values=new URLSearchParams();
            for(const [k,v] of Object.entries(m.params||{})){
              if(!['page','page_size','q','ids','priority','type','status','source','intent_class','engine','result','source_type','stage'].includes(k))throw new Error('无效筛选');
              values.set(k,String(v));
            }
            const result=await o.api('GET',scoped(base+'/operator/paged/'+m.collection+'?'+values));
            if(!alive())return;
            for(const row of [...result.items,...(result.selected_items||[])])if(row.id&&row._version)objectVersions[m.collection+'/'+row.id]=row._version;
            reply(m.id,result);
          }catch(error){reply(m.id,null,error.message);}
        })();
      }
      if(m.type==='export'){
        void(async()=>{
          try{
            if(!['questions','keywords'].includes(m.collection))throw new Error('此列表暂不支持导出');
            const params=new URLSearchParams();
            for(const [k,v] of Object.entries(m.params||{})){if(!['q','priority','intent_class','source','type'].includes(k))throw new Error('无效导出筛选');params.set(k,String(v));}
            const result=await o.api('GET',scoped(base+'/operator/export/'+m.collection+'?'+params));
            if(!alive())return;
            status.className='operator-status';status.replaceChildren();
            const customer=location.pathname.startsWith('/ui/customer/'),downloadParams=new URLSearchParams(params);downloadParams.set('workspace_site_id',selectedSite);if(!customer)downloadParams.set('tenant_id',project.tenant_id);
            const link=document.createElement('a');link.href=`${customer?'/ui/customer':'/ui'}/operator-export/${encodeURIComponent(project.project_id)}/${m.collection}?${downloadParams}`;link.download=result.filename;link.className='btn';link.textContent=`下载${m.collection==='questions'?'问句':'关键词'} CSV（${result.total} 条筛选结果）`;status.append(link);link.focus();
            reply(m.id,{total:result.total});
          }catch(error){reply(m.id,null,error.message);}
        })();
      }
      if(m.type==="dirty")o.dirty?.(Boolean(m.value));
      if(m.type==="frame-error"){status.className="operator-status error";status.textContent="专业界面运行错误："+String(m.message||"");}
      if(m.type==="view"&&views.has(m.view)){currentView=m.view;history.replaceState(null,"",`#/operator/${m.view}?project=${encodeURIComponent(project.project_id)}&tenant=${encodeURIComponent(project.tenant_id)}&site=${encodeURIComponent(selectedSite)}`);o.syncRoute?.();}
      if(m.type==="copy"&&typeof m.text==="string")navigator.clipboard.writeText(m.text).then(()=>{status.textContent="业务提示词已复制；请按数据保密要求使用外部工具。";reply(m.id,true);}).catch(()=>{status.textContent="浏览器未允许复制，请在提示词正文中选择并复制。";reply(m.id,null,"浏览器未允许复制，请手动选择文字。");});
      if(m.type==="external-link"&&typeof m.url==="string"){try{const url=new URL(m.url);if(["https:","http:"].includes(url.protocol)){status.replaceChildren();const link=document.createElement("a");link.href=url.href;link.target="_blank";link.rel="noopener noreferrer";link.textContent="打开所选外部资料："+url.hostname;status.append(link);}}catch{}}
    };
    window.addEventListener("message",listener);
    disposeCurrent=()=>{closed=true;window.removeEventListener("message",listener);};
    document.querySelectorAll('[data-switch-project]').forEach(button=>button.onclick=()=>{const p=ws.projects.find(p=>p.tenant_id+'/'+p.project_id===button.dataset.switchProject);if(p)location.hash=`#/operator/${currentView}?project=${encodeURIComponent(p.project_id)}&tenant=${encodeURIComponent(p.tenant_id)}`;});
    document.getElementById("operator-project").onchange=event=>{
      const p=ws.projects.find(p=>String(p.tenant_id)+"/"+String(p.project_id)===event.target.value);
      if(!p)return;location.hash=`#/operator/${currentView}?project=${encodeURIComponent(p.project_id)}&tenant=${encodeURIComponent(p.tenant_id)}`;
    };
    document.getElementById("operator-resource").onchange=event=>{
      location.hash=`#/operator/${currentView}?project=${encodeURIComponent(project.project_id)}&tenant=${encodeURIComponent(project.tenant_id)}&site=${encodeURIComponent(event.target.value)}`;
    };
    frame.src="/ui/operator-frame/?channel="+encodeURIComponent(channel)+"&view="+encodeURIComponent(view);
  }
  return {render,discard(){generation++;disposeCurrent?.();},clear(){generation++;disposeCurrent?.();}};
})();
