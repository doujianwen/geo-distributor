/* Management-only authorization UI. The server is authoritative on every command. */
(()=>{
  const e=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const names={read:'查看项目',prepare:'维护资料',operate:'专业作业',execute_assigned:'执行已指派行动',quality_review:'证据复核',report_publish:'报告发布'};
  window.WorkspaceAccess={async render(o){
    const ws=await o.api('GET','/growth/workspace');if(!o.alive())return;
    const subjects=await o.api('GET','/growth/access/subjects');if(!o.alive())return;
    const body=`<header class="page-heading"><h1>账号与作业授权</h1><p>人员身份、项目作业和质量复核分别开通。总部运营不会自动获得全部客户。</p></header><section class="card"><h2>项目作业权限</h2><form id="access-form"><label>客户与项目<select id="access-project" required>${ws.projects.map(p=>`<option value="${e(p.tenant_id+'/'+p.project_id)}">${e(p.client_name+' · '+p.name)}</option>`).join('')}</select></label><label>人员<select id="access-subject" required>${subjects.map(p=>`<option value="${e(p.subject)}">${e(p.label)}</option>`).join('')}</select></label><fieldset><legend>本次保存的完整能力集合（全部取消即撤销）</legend>${Object.entries(names).map(([k,v])=>`<label><input type="checkbox" name="capability" value="${k}"> ${v}</label>`).join('')}</fieldset><button class="btn">保存授权</button><p id="access-result" role="status"></p></form></section><section class="card"><h2>个人账号开通申请</h2><p>用户使用网站账号登录后进入待开通状态。账号密码仍由网站管理。</p><div id="identity-requests" role="status">正在读取…</div></section>`;
    o.shell('access',body);
    const dirtyForms=new Set(),clean=form=>{dirtyForms.delete(form);if(o.alive())o.dirty?.(dirtyForms.size>0);};
    document.getElementById('view').addEventListener('input',event=>{const form=event.target.closest('form');if(form&&!['access-project','access-subject'].includes(event.target.id)){dirtyForms.add(form);o.dirty?.(true);}});
    document.getElementById('access-form').insertAdjacentHTML('beforeend','<fieldset><legend>明确授权的产品与站点（新增资源不自动继承）</legend><div id="access-resources"></div></fieldset>');
    document.getElementById('access-form').closest('section').insertAdjacentHTML('afterend','<section class="card"><h2>为上方选定项目开通新产品与站点</h2><p>仅创建独立的新资源；不会认领历史数据或自动给人员授予作业权。</p><form id="resource-create"><label>产品名称<input name="name" required maxlength="160"></label><label>完整网站地址<input name="domain" type="url" required maxlength="1000" placeholder="https://example.com"></label><button class="btn">开通新资源</button><p role="status"></p></form></section>');
    const project=()=>ws.projects.find(p=>p.tenant_id+'/'+p.project_id===document.getElementById('access-project').value);
    let loadVersion=0;
    async function load(){const version=++loadVersion,p=project(),subject=document.getElementById('access-subject').value;
      document.getElementById('access-form').querySelector('button').disabled=true;
      document.getElementById('access-resources').textContent='正在读取此人员的资源授权…';
      document.querySelectorAll('[name=capability]').forEach(i=>{i.checked=false;});if(!p)return;
      const rows=await o.api('GET',`/growth/projects/${encodeURIComponent(p.project_id)}/access?tenant_id=${encodeURIComponent(p.tenant_id)}`);
      if(!o.alive()||version!==loadVersion)return;
      const resourceData=await o.api('GET',`/growth/projects/${encodeURIComponent(p.project_id)}/resources?tenant_id=${encodeURIComponent(p.tenant_id)}`);
      if(!o.alive()||version!==loadVersion)return;
      document.getElementById('access-resources').innerHTML=resourceData.resources.map(r=>`<label><input type="checkbox" name="access-resource" value="${e(r.site_id)}" ${rows.some(row=>row.subject===subject&&row.site_id===r.site_id&&row.enabled)?'checked':''}> ${e(r.name+' · '+r.domain)}</label>`).join('')||'<p>尚未绑定增长资源，请先从增长工作区开通。</p>';
      document.getElementById('access-resources').dataset.subject=subject;
      document.getElementById('access-form').querySelector('button').disabled=false;
      document.querySelectorAll('[name=capability]').forEach(i=>i.checked=rows.some(r=>r.subject===subject&&r.capability===i.value&&r.enabled));
    }
    document.getElementById('access-project').onchange=()=>load().catch(show);
    document.getElementById('access-subject').onchange=()=>load().catch(show);
    function show(err){if(o.alive())document.getElementById('access-result').textContent=err.message;}
    document.getElementById('access-form').onsubmit=async ev=>{ev.preventDefault();const p=project();if(!p)return;const button=ev.target.querySelector('button');button.disabled=true;try{
      await o.api('POST',`/growth/projects/${encodeURIComponent(p.project_id)}/access?tenant_id=${encodeURIComponent(p.tenant_id)}`,{subject:document.getElementById('access-subject').value,capabilities:[...document.querySelectorAll('[name=capability]:checked')].map(i=>i.value),resource_ids:[...document.querySelectorAll('[name=access-resource]:checked')].map(i=>Number(i.value))});
      if(o.alive()){document.getElementById('access-result').textContent='授权已保存；撤销后下一次业务访问将重新校验。';clean(ev.target);}
    }catch(err){show(err);}finally{if(o.alive())button.disabled=false;}};
    await load();
    let createKey=null;
    document.getElementById('resource-create').onsubmit=async ev=>{ev.preventDefault();const p=project(),form=ev.target,button=form.querySelector('button'),output=form.querySelector('[role=status]');if(!p)return;button.disabled=true;createKey ||= crypto.randomUUID();try{const values=new FormData(form);await o.api('POST',`/growth/projects/${encodeURIComponent(p.project_id)}/resources?tenant_id=${encodeURIComponent(p.tenant_id)}`,{name:values.get('name'),domain:values.get('domain')},{'Idempotency-Key':createKey});if(!o.alive())return;createKey=null;form.reset();output.textContent='新资源已开通，请在上方勾选资源并明确分配人员权限。';await load();}catch(err){if(o.alive())output.textContent=err.message;}finally{if(o.alive())button.disabled=false;}};
    try{
      const identityInfo=await fetch('/ui/demo-info',{credentials:'same-origin'}).then(r=>r.json());
      if(!o.alive())return;
      if(!identityInfo.identity_enabled){document.getElementById('identity-requests').textContent='个人账号桥接尚未配置。完成网站账号交接配置后，可在此处理开通申请；演练身份不等于真实个人账号。';return;}
      const rows=await o.api('GET','/identity/requests');if(!o.alive())return;
      document.getElementById('identity-requests').innerHTML=rows.length?rows.map((r,i)=>`<form data-membership="${i}"><h3>${e(r.subject)}</h3><p>状态：${e(r.status)}</p><label>组织范围<input name="tenant" value="${e(r.tenant||'')}" required maxlength="100"></label><label>开通身份<select name="role">${[['HQ_TECHNICAL','总部运营'],['HQ_MANAGEMENT','总部管理'],['DISTRIBUTOR_ADMIN','渠道商管理员'],['END_CUSTOMER_EDITOR','客户成员（可分配编辑能力）'],['END_CUSTOMER','客户成员（只读）']].map(([v,t])=>`<option value="${v}" ${r.role===v?'selected':''}>${t}</option>`).join('')}</select></label><label>客户编号（仅客户成员必填）<input name="client" value="${e(r.client||'')}" maxlength="100"></label><label><input name="enabled" type="checkbox" ${r.enabled?'checked':''}> 开通访问（取消可暂停）</label><button class="btn">保存成员权限</button><p role="status"></p></form>`).join(''):'暂无申请';
      if(rows.length){
        const directory=await o.api('GET','/hq/workspace');if(!o.alive())return;
        for(const form of document.querySelectorAll('[data-membership]')){
          const record=rows[Number(form.dataset.membership)],oldTenant=form.elements.tenant,oldClient=form.elements.client;
          const tenantSelect=document.createElement('select');tenantSelect.name='tenant';tenantSelect.required=true;
          for(const tenant of directory.tenants||[]){const option=document.createElement('option');option.value=tenant.tenant_id;option.textContent=tenant.tenant_id;tenantSelect.append(option);}
          tenantSelect.value=record.tenant||tenantSelect.options[0]?.value||'';oldTenant.replaceWith(tenantSelect);
          const clientSelect=document.createElement('select');clientSelect.name='client';oldClient.replaceWith(clientSelect);
          const updateClients=()=>{clientSelect.replaceChildren();const empty=document.createElement('option');empty.value='';empty.textContent='请选择所属客户';clientSelect.append(empty);for(const client of directory.clients||[]){if(client.tenant_id!==tenantSelect.value||!client.is_active)continue;const option=document.createElement('option');option.value=client.client_id;option.textContent=client.name;clientSelect.append(option);}clientSelect.value=record.client||'';clientSelect.disabled=!form.elements.role.value.startsWith('END_CUSTOMER');clientSelect.required=!clientSelect.disabled;};
          tenantSelect.onchange=updateClients;form.elements.role.onchange=updateClients;updateClients();
        }
      }
      document.querySelectorAll('[data-membership]').forEach(form=>form.onsubmit=async ev=>{ev.preventDefault();const record=rows[Number(form.dataset.membership)],values=new FormData(form),out=form.querySelector('[role=status]');try{await o.api('POST','/identity/requests/'+encodeURIComponent(record.subject),{tenant:values.get('tenant'),role:values.get('role'),client:values.get('client')||null,enabled:values.has('enabled')});out.textContent='已保存。该人员需从网站重新进入，再分配项目作业权限。';}catch(err){out.textContent=err.message;}});
    }catch(err){if(o.alive())document.getElementById('identity-requests').textContent=err.message;}
  }};
})();
