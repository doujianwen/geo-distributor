/* Management-only authorization UI. The server is authoritative on every command.
 * 2026-10-28 简化：审批置顶且一键批准；已批准/暂停仅显示状态与暂停恢复；
 * 项目作业与资源授权收进「高级」折叠区，日常审批用不到。后端契约不变。 */
(() => {
  const e = v => String(v ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const names = { read: '查看项目', prepare: '维护资料', operate: '专业作业', execute_assigned: '执行已指派行动', quality_review: '证据复核', report_publish: '报告发布' };
  const ROLE_OPTIONS = [
    ['END_CUSTOMER', '客户成员（只读）'],
    ['END_CUSTOMER_EDITOR', '客户成员（可编辑）'],
    ['DISTRIBUTOR_ADMIN', '渠道商管理员'],
    ['HQ_MANAGEMENT', '总部管理'],
    ['HQ_TECHNICAL', '总部运营'],
  ];

  window.WorkspaceAccess = { async render(o) {
    let identityInfo;
    try { identityInfo = await (await fetch('/ui/demo-info', { credentials: 'same-origin' })).json(); }
    catch { identityInfo = { identity_enabled: false }; }
    if (!o.alive()) return;

    let ws = null, subjects = null;
    try { ws = await o.api('GET', '/growth/workspace'); } catch {}
    try { subjects = await o.api('GET', '/growth/access/subjects'); } catch {}
    if (!o.alive()) return;

    const body =
      `<header class="page-heading"><h1>账号与作业授权</h1>`
      + `<p>本页主要做一件事：把「待开通」的网站账号<strong>一键批准</strong>进工作区。`
      + `下方的「高级资源授权」用于给项目分配作业能力，日常审批用不到，默认收起。</p></header>`
      + `<section class="card"><h2>个人账号开通申请</h2>`
      + `<p>网站账号登录后会进入「待开通」状态，在此批准即可获得工作区访问。账号密码仍由网站管理。</p>`
      + `<div id="identity-requests" role="status">正在读取…</div></section>`
      + advancedSection(ws, subjects);

    o.shell('access', body);
    await renderApprovals(o, identityInfo);
    if (ws && subjects) wireAdvanced(o, ws, subjects);
  } };

  // ---- 审批区（核心，置顶）----
  async function renderApprovals(o, identityInfo) {
    const box = document.getElementById('identity-requests');
    if (!identityInfo.identity_enabled) {
      box.textContent = '个人账号桥接尚未配置。完成网站账号交接配置后，可在此处理开通申请；演练身份不等于真实个人账号。';
      return;
    }
    let rows, directory;
    try {
      rows = await o.api('GET', '/identity/requests');
      directory = await o.api('GET', '/hq/workspace');
    } catch (err) { box.textContent = err.message; return; }
    if (!o.alive()) return;

    if (!rows.length) { box.innerHTML = '<p>暂无待开通申请。</p>'; return; }

    const tenants = (directory.tenants || []);
    const clients = (directory.clients || []).filter(c => c.is_active);
    const defaultTenant = tenants[0] ? tenants[0].tenant_id : '';
    const defaultClient = clients.find(c => c.tenant_id === defaultTenant);
    const defaultClientId = defaultClient ? defaultClient.client_id : '';

    box.innerHTML = rows.map((r, i) =>
      r.status === 'pending' ? pendingCard(r, i, tenants, clients, defaultTenant, defaultClientId) : summaryCard(r, i)
    ).join('');

    box.querySelectorAll('form[data-approve]').forEach(form => {
      const tenantSel = form.elements.tenant, roleSel = form.elements.role, clientSel = form.elements.client;
      const refreshClients = () => {
        clientSel.replaceChildren();
        const empty = document.createElement('option'); empty.value = ''; empty.textContent = '请选择所属客户'; clientSel.append(empty);
        for (const c of clients) { if (c.tenant_id !== tenantSel.value) continue; const op = document.createElement('option'); op.value = c.client_id; op.textContent = c.name; clientSel.append(op); }
        clientSel.value = form.dataset.client || '';
        const need = (roleSel.value || '').startsWith('END_CUSTOMER');
        clientSel.disabled = !need; clientSel.required = need;
      };
      tenantSel.onchange = refreshClients; roleSel.onchange = refreshClients; refreshClients();

      form.onsubmit = async ev => {
        ev.preventDefault();
        const r = rows[Number(form.dataset.approve)];
        const v = new FormData(form);
        const out = form.querySelector('[role=status]');
        const btn = form.querySelector('button');
        btn.disabled = true;
        try {
          await o.api('POST', '/identity/requests/' + encodeURIComponent(r.subject), {
            tenant: v.get('tenant'),
            role: v.get('role'),
            client: (v.get('role') || '').startsWith('END_CUSTOMER') ? (v.get('client') || null) : null,
            enabled: true,
          });
          out.textContent = '已批准开通。该人员需从网站重新进入工作区即可生效。';
          await renderApprovals(o, identityInfo);
        } catch (err) { out.textContent = err.message; btn.disabled = false; }
      };
    });

    box.querySelectorAll('button[data-toggle]').forEach(btn => {
      btn.onclick = async () => {
        const r = rows[Number(btn.dataset.toggle)];
        btn.disabled = true;
        try {
          await o.api('POST', '/identity/requests/' + encodeURIComponent(r.subject), {
            tenant: r.tenant,
            role: r.role,
            client: (r.role || '').startsWith('END_CUSTOMER') ? (r.client || null) : null,
            enabled: r.status !== 'approved',
          });
          await renderApprovals(o, identityInfo);
        } catch (err) { alert(err.message); btn.disabled = false; }
      };
    });
  }

  function pendingCard(r, i, tenants, clients, defaultTenant, defaultClientId) {
    const tenant = r.tenant || defaultTenant;
    const role = r.role || 'END_CUSTOMER';
    const client = r.client || defaultClientId;
    const tenantOpts = tenants.map(t => `<option value="${e(t.tenant_id)}" ${t.tenant_id === tenant ? 'selected' : ''}>${e(t.tenant_id)}</option>`).join('');
    return `<form data-approve="${i}" data-client="${e(client)}"><h3>${e(r.subject)}</h3>`
      + `<p class="muted">状态：待开通</p>`
      + `<label>组织范围<select name="tenant" required>${tenantOpts}</select></label>`
      + `<label>开通身份<select name="role">${ROLE_OPTIONS.map(([v, t]) => `<option value="${v}" ${v === role ? 'selected' : ''}>${t}</option>`).join('')}</select></label>`
      + `<label>客户编号（客户成员必填）<select name="client"></select></label>`
      + `<button class="btn btn-primary">批准开通</button>`
      + `<p role="status"></p></form>`;
  }

  function summaryCard(r, i) {
    const label = { approved: '已开通', suspended: '已暂停', rejected: '未通过' }[r.status] || r.status;
    const on = r.status === 'approved';
    return `<div class="approval-summary"><h3>${e(r.subject)}</h3>`
      + `<p class="muted">状态：${label} ｜ 身份：${e(r.role || '-')}${r.client ? ' ｜ 客户：' + e(r.client) : ''}</p>`
      + (r.status === 'rejected'
          ? '<p class="muted">该申请未通过，如需开通请在网站重新发起。</p>'
          : `<button class="btn" data-toggle="${i}">${on ? '暂停访问' : '恢复访问'}</button>`)
      + `</div>`;
  }

  // ---- 高级：项目作业与资源授权（默认收起）----
  function advancedSection(ws, subjects) {
    if (!ws || !subjects) return '';
    return `<details class="card"><summary>高级：项目作业与资源授权</summary>`
      + `<section><h2>项目作业权限</h2><form id="access-form">`
      + `<label>客户与项目<select id="access-project" required>${ws.projects.map(p => `<option value="${e(p.tenant_id + '/' + p.project_id)}">${e(p.client_name + ' · ' + p.name)}</option>`).join('')}</select></label>`
      + `<label>人员<select id="access-subject" required>${subjects.map(p => `<option value="${e(p.subject)}">${e(p.label)}</option>`).join('')}</select></label>`
      + `<fieldset><legend>本次保存的完整能力集合（全部取消即撤销）</legend>${Object.entries(names).map(([k, v]) => `<label><input type="checkbox" name="capability" value="${k}"> ${v}</label>`).join('')}</fieldset>`
      + `<button class="btn">保存授权</button><p id="access-result" role="status"></p></form>`
      + `<fieldset><legend>明确授权的产品与站点（新增资源不自动继承）</legend><div id="access-resources"></div></fieldset></section>`
      + `<section><h2>为上方选定项目开通新产品与站点</h2><p>仅创建独立的新资源；不会认领历史数据或自动给人员授予作业权。</p>`
      + `<form id="resource-create"><label>产品名称<input name="name" required maxlength="160"></label>`
      + `<label>完整网站地址<input name="domain" type="url" required maxlength="1000" placeholder="https://example.com"></label>`
      + `<button class="btn">开通新资源</button><p role="status"></p></form></section></details>`;
  }

  function wireAdvanced(o, ws, subjects) {
    const dirtyForms = new Set();
    const clean = form => { dirtyForms.delete(form); if (o.alive()) o.dirty?.(dirtyForms.size > 0); };
    document.getElementById('view').addEventListener('input', event => { const form = event.target.closest('form'); if (form && !['access-project', 'access-subject'].includes(event.target.id)) { dirtyForms.add(form); o.dirty?.(true); } });
    const project = () => ws.projects.find(p => p.tenant_id + '/' + p.project_id === document.getElementById('access-project').value);
    let loadVersion = 0;
    async function load() {
      const version = ++loadVersion, p = project(), subject = document.getElementById('access-subject').value;
      document.getElementById('access-form').querySelector('button').disabled = true;
      document.getElementById('access-resources').textContent = '正在读取此人员的资源授权…';
      document.querySelectorAll('[name=capability]').forEach(i => { i.checked = false; }); if (!p) return;
      const rows = await o.api('GET', `/growth/projects/${encodeURIComponent(p.project_id)}/access?tenant_id=${encodeURIComponent(p.tenant_id)}`);
      if (!o.alive() || version !== loadVersion) return;
      const resourceData = await o.api('GET', `/growth/projects/${encodeURIComponent(p.project_id)}/resources?tenant_id=${encodeURIComponent(p.tenant_id)}`);
      if (!o.alive() || version !== loadVersion) return;
      document.getElementById('access-resources').innerHTML = resourceData.resources.map(r => `<label><input type="checkbox" name="access-resource" value="${e(r.site_id)}" ${rows.some(row => row.subject === subject && row.site_id === r.site_id && row.enabled) ? 'checked' : ''}> ${e(r.name + ' · ' + r.domain)}</label>`).join('') || '<p>尚未绑定增长资源，请先从增长工作区开通。</p>';
      document.getElementById('access-resources').dataset.subject = subject;
      document.getElementById('access-form').querySelector('button').disabled = false;
      document.querySelectorAll('[name=capability]').forEach(i => i.checked = rows.some(r => r.subject === subject && r.capability === i.value && r.enabled));
    }
    document.getElementById('access-project').onchange = () => load().catch(show);
    document.getElementById('access-subject').onchange = () => load().catch(show);
    function show(err) { if (o.alive()) document.getElementById('access-result').textContent = err.message; }
    document.getElementById('access-form').onsubmit = async ev => { ev.preventDefault(); const p = project(); if (!p) return; const button = ev.target.querySelector('button'); button.disabled = true; try {
      await o.api('POST', `/growth/projects/${encodeURIComponent(p.project_id)}/access?tenant_id=${encodeURIComponent(p.tenant_id)}`, { subject: document.getElementById('access-subject').value, capabilities: [...document.querySelectorAll('[name=capability]:checked')].map(i => i.value), resource_ids: [...document.querySelectorAll('[name=access-resource]:checked')].map(i => Number(i.value)) });
      if (o.alive()) { document.getElementById('access-result').textContent = '授权已保存；撤销后下一次业务访问将重新校验。'; clean(ev.target); }
    } catch (err) { show(err); } finally { if (o.alive()) button.disabled = false; } };
    load().catch(show);
    let createKey = null;
    document.getElementById('resource-create').onsubmit = async ev => { ev.preventDefault(); const p = project(), form = ev.target, button = form.querySelector('button'), output = form.querySelector('[role=status]'); if (!p) return; button.disabled = true; createKey ||= crypto.randomUUID(); try { const values = new FormData(form); await o.api('POST', `/growth/projects/${encodeURIComponent(p.project_id)}/resources?tenant_id=${encodeURIComponent(p.tenant_id)}`, { name: values.get('name'), domain: values.get('domain') }, { 'Idempotency-Key': createKey }); if (!o.alive()) return; createKey = null; form.reset(); output.textContent = '新资源已开通，请在上方勾选资源并明确分配人员权限。'; await load(); } catch (err) { if (o.alive()) output.textContent = err.message; } finally { if (o.alive()) button.disabled = false; } };
  }
})();
