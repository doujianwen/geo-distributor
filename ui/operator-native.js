/* Controlled integration copy of the canonical native operator UI. The original source is unchanged. */
/* GEO内容增长系统 - 前端 SPA（原生 JS，无构建步骤）。
   设计：浅色主题、SVG 图标、设计 Token；纯人工驱动（AI 步骤靠提示词复制+回填）。 */

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

const state = {
  meta: null,
  products: [],
  current: null, // 当前产品 id
  view: "dashboard",
};

let operatorViewEpoch = 0;
let MONITORS = []; // 当前产品的监测任务缓存，供检查表单选择

const operatorListState=new Map(), operatorListResults=new Map();
const operatorPrimaryLists={personas:['personas'],scenarios:['scenarios'],questions:['questions'],clusters:['clusters'],briefs:['briefs'],citations:['monitors','citations'],entities:['entities'],gaps:['content-gaps'],keywords:['keywords']};
const operatorCollectionNames={personas:'用户画像',scenarios:'场景',questions:'问句',clusters:'问题簇',briefs:'内容Brief',monitors:'监测任务',citations:'引用检查',entities:'实体', 'content-gaps':'内容缺口',keywords:'关键词'};
function operatorMountPagers(){
  const host=document.getElementById('view');if(!host)return;
  if(host.getAttribute('aria-busy')==='true')return;
  for(const collection of operatorPrimaryLists[state.view]||[]){
    const result=operatorListResults.get(collection);if(!result)continue;
    const signature=JSON.stringify([state.view,collection,result.page,result.total,result.q,result.status,result.pages]);
    let box=host.querySelector('[data-operator-pager="'+collection+'"]');
    if(box?.dataset.signature===signature)continue;
    if(!box){box=document.createElement('section');box.className='operator-native-pager';box.dataset.operatorPager=collection;host.prepend(box);}
    box.dataset.signature=signature;
    box.innerHTML=`<form><label>${esc(operatorCollectionNames[collection])}搜索 <input aria-label="搜索${esc(operatorCollectionNames[collection])}" maxlength="200" value="${esc(result.q||'')}" placeholder="名称、内容或来源"></label><button type="button" class="btn btn-sm" data-search>搜索</button><button class="btn btn-sm" type="button" data-reset>清除</button></form><div><button class="btn btn-sm" type="button" data-prev ${result.page<=1?'disabled':''}>上一页</button><span role="status">第 ${result.page} / ${Math.max(1,result.pages)} 页 · 共 ${result.total} 条${result.q?' · 搜索：'+esc(result.q):''} · 每页20条</span><button class="btn btn-sm" type="button" data-next ${result.page>=result.pages?'disabled':''}>下一页</button><label>跳至 <input data-page type="number" min="1" max="${Math.max(1,result.pages)}" value="${result.page}" aria-label="${esc(operatorCollectionNames[collection])}跳转页码" style="width:76px"> 页</label><button type="button" class="btn btn-sm" data-go>跳转</button>${['questions','keywords'].includes(collection)?'<button type="button" class="btn btn-sm" data-export>导出筛选结果 CSV</button>':''}<span data-export-status role="status"></span></div>`;
    const run=(patch)=>{if(!window.OperatorFrame.beforeNavigate())return;operatorListState.set(collection,{...(operatorListState.get(collection)||{page:1,q:''}),...patch});render();};
    const search=()=>run({page:1,q:box.querySelector('form input').value.trim()});
    box.querySelector('form').onsubmit=event=>event.preventDefault();
    box.querySelector('[data-search]').onclick=search;
    box.querySelector('form input').onkeydown=event=>{if(event.key==='Enter'){event.preventDefault();search();}};
    box.querySelector('[data-reset]').onclick=()=>run({page:1,q:''});
    box.querySelector('[data-prev]').onclick=()=>run({page:Math.max(1,result.page-1)});
    box.querySelector('[data-next]').onclick=()=>run({page:result.page+1});
    const jump=()=>{const input=box.querySelector('[data-page]'),value=Number(input.value);if(!Number.isInteger(value)||value<1||value>Math.max(1,result.pages)){input.setCustomValidity('请输入1至'+Math.max(1,result.pages)+'的整数页码');input.reportValidity();input.focus();return;}input.setCustomValidity('');run({page:value});};
    box.querySelector('[data-go]').onclick=jump;
    box.querySelector('[data-page]').oninput=event=>event.target.setCustomValidity('');
    box.querySelector('[data-page]').onkeydown=event=>{if(event.key==='Enter'){event.preventDefault();jump();}};
    const exportButton=box.querySelector('[data-export]');
    if(exportButton)exportButton.onclick=async()=>{exportButton.disabled=true;const note=box.querySelector('[data-export-status]');note.textContent='正在导出当前筛选的全部结果…';try{await window.OperatorFrame.exportCsv(collection,{q:result.q||'',...(result.status?{status:result.status}:{})});note.textContent='CSV 已准备，可在页面上方下载。';}catch(error){note.textContent=error.message;}finally{exportButton.disabled=false;}};
  }
}
window.OperatorNativePagination={mount:operatorMountPagers};

const NAV = [
  { id: "dashboard", label: "概览", icon: "ic-dashboard" },
  { id: "products", label: "产品", icon: "ic-box" },
  { id: "personas", label: "用户画像", icon: "ic-users" },
  { id: "scenarios", label: "场景", icon: "ic-map" },
  { id: "questions", label: "问句库", icon: "ic-message" },
  { id: "clusters", label: "问题簇", icon: "ic-layers" },
  { id: "briefs", label: "内容 Brief", icon: "ic-file" },
  { id: "citations", label: "引用追踪", icon: "ic-search" },
  { id: "trends", label: "趋势报告", icon: "ic-trend" },
  { id: "entities", label: "实体库", icon: "ic-tag" },
  { id: "gaps", label: "内容缺口", icon: "ic-target" },
  { id: "keywords", label: "关键词库", icon: "ic-tags" },
  { id: "seo", label: "SEO Growth", icon: "ic-trend" },
  { id: "prompts", label: "提示词库", icon: "ic-terminal" },
  { id: "manual", label: "操作手册", icon: "ic-file" },
];

const VIEW_TITLE = {
  dashboard: "概览", products: "产品", personas: "用户画像",
  scenarios: "场景", questions: "问句库", clusters: "问题簇",
  briefs: "内容 Brief", citations: "引用追踪", trends: "趋势报告", entities: "实体库",
  gaps: "内容缺口", keywords: "关键词库", prompts: "提示词库",
  seo: "SEO Growth（增长层）", manual: "操作手册",
};

/* ---------------- 基础设施 ---------------- */
async function api(method, path, body) {
  const list=path.match(/^\/products\/\d+\/([a-z-]+)$/);
  if(method==='GET'&&list&&(operatorPrimaryLists[state.view]||[]).includes(list[1])){
    const collection=list[1],view=state.view,params={...(operatorListState.get(collection)||{page:1,q:''}),page_size:20};
    if(collection==='briefs')params.status=briefTab==='idea'?'idea':briefTab==='guide'?'__adopted__':'__unregistered__';
    const result=await window.OperatorFrame.api('GET','/__paged/'+collection,params);
    if(view===state.view){operatorListResults.set(collection,{...result,q:params.q,status:params.status});setTimeout(operatorMountPagers,0);}
    return result.items;
  }
  return window.OperatorFrame.api(method, path, body);
}

function esc(s) {
  if (s === null || s === undefined) return "";
  return String(s).replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function prioBadge(p) {
  const map = { P0: "badge-p0", P1: "badge-p1", P2: "badge-p2", "暂缓": "badge-low", "未评分": "badge-none" };
  const cls = map[p] || "badge-line";
  return `<span class="badge ${cls}">${esc(p || "未评分")}</span>`;
}

function toast(msg) {
  let t = $(".toast");
  if (!t) { t = document.createElement("div"); t.className = "toast"; document.body.appendChild(t); }
  t.textContent = msg; t.classList.add("show");
  clearTimeout(t._t); t._t = setTimeout(() => t.classList.remove("show"), 2200);
}

function icon(id, cls = "") {
  return `<svg class="icon ${cls}"><use href="#${id}"></use></svg>`;
}

/* ---------------- 弹窗 ---------------- */
function openModal(title, bodyHtml, opts = {}) {
  const root = $("#modal-root");
  const fsCls = opts.fullscreen ? " fullscreen" : "";
  root.innerHTML = `
    <div class="modal-backdrop${fsCls}" id="mb">
      <div class="modal">
        <div class="modal-head"><h3>${esc(title)}</h3><button class="x-btn" id="mx">×</button></div>
        <div class="modal-body" id="mb-body">${bodyHtml}</div>
        <div class="modal-foot">
          <button class="btn" id="mc">取消</button>
          <button class="btn btn-primary" id="ms">${esc(opts.saveText || "保存")}</button>
        </div>
      </div>
    </div>`;
  $("#mx").onclick = closeModal;
  $("#mc").onclick = closeModal;
  $("#mb").onclick = (e) => { if (e.target.id === "mb") closeModal(); };
  if (opts.onSave) $("#ms").onclick = () => opts.onSave(closeModal);
  if (opts.onOpen) opts.onOpen($("#mb-body"));
}
function closeModal() { $("#modal-root").innerHTML = ""; }

/* ---- 轻量 Markdown 渲染器（零依赖，先转义再解析） ---- */
function renderMarkdown(md) {
  if (!md || !md.trim()) return '<div class="md-empty">暂无内容。在左侧编辑框输入或粘贴 Markdown，右侧实时预览。</div>';
  // 先转义 HTML 防注入
  let h = esc(md);
  const lines = h.split("\n");
  let html = [];
  let inUl = false, inOl = false, inTable = false, tableHeader = false;
  const closeLists = () => { if (inUl) { html.push("</ul>"); inUl = false; } if (inOl) { html.push("</ol>"); inOl = false; } };
  const closeTable = () => { if (inTable) { html.push("</tbody></table>"); inTable = false; tableHeader = false; } };

  for (let raw of lines) {
    const line = raw;
    // 表格（含 | 的行）
    if (line.trim().startsWith("|") && line.trim().endsWith("|")) {
      closeLists();
      const cells = line.trim().slice(1, -1).split("|").map(c => c.trim());
      // 分隔行 |---|---|
      if (cells.every(c => /^:?-+:?$/.test(c))) { continue; }
      if (!inTable) { html.push("<table><thead>"); inTable = true; tableHeader = true; }
      const tag = tableHeader ? "th" : "td";
      if (tableHeader) { html.push("<tr>" + cells.map(c => `<${tag}>${inlineMd(c)}</${tag}>`).join("") + "</tr></thead><tbody>"); tableHeader = false; }
      else { html.push("<tr>" + cells.map(c => `<${tag}>${inlineMd(c)}</${tag}>`).join("") + "</tr>"); }
      continue;
    }
    closeTable();
    // 标题
    if (/^###\s/.test(line)) { closeLists(); html.push(`<h3 class="md-h3">${inlineMd(line.replace(/^###\s/, ""))}</h3>`); continue; }
    if (/^##\s/.test(line)) { closeLists(); html.push(`<h2 class="md-h2">${inlineMd(line.replace(/^##\s/, ""))}</h2>`); continue; }
    if (/^#\s/.test(line)) { closeLists(); html.push(`<h1 class="md-h1">${inlineMd(line.replace(/^#\s/, ""))}</h1>`); continue; }
    // 分隔线
    if (/^---+\s*$/.test(line)) { closeLists(); html.push("<hr>"); continue; }
    // 引用
    if (/^>\s?/.test(line)) { closeLists(); html.push(`<blockquote>${inlineMd(line.replace(/^>\s?/, ""))}</blockquote>`); continue; }
    // 有序列表
    if (/^\d+\.\s/.test(line)) { if (!inOl) { closeLists(); html.push("<ol>"); inOl = true; } html.push(`<li>${inlineMd(line.replace(/^\d+\.\s/, ""))}</li>`); continue; }
    // 无序列表
    if (/^[-*]\s/.test(line)) { if (!inUl) { closeLists(); html.push("<ul>"); inUl = true; } html.push(`<li>${inlineMd(line.replace(/^[-*]\s/, ""))}</li>`); continue; }
    // 空行
    if (!line.trim()) { closeLists(); continue; }
    // 段落
    closeLists();
    html.push(`<p>${inlineMd(line)}</p>`);
  }
  closeLists(); closeTable();
  return html.join("\n");
}
function inlineMd(s) {
  // 行内：**bold**、`code`、[link](url)
  return s
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/`(.+?)`/g, "<code>$1</code>")
    .replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>');
}

/* ---------------- 通用表单字段 ---------------- */
function field(label, inputHtml) {
  return `<label class="field"><span>${esc(label)}</span>${inputHtml}</label>`;
}
function opt(list, selected) {
  return list.map((v) => `<option ${v === selected ? "selected" : ""}>${esc(v)}</option>`).join("");
}

/* 产品级意图体系：优先用产品自带 schema，否则回退全局 INTENT_CLASSES */
function currentIntentClasses() {
  const p = state.products.find((x) => x.id === state.current);
  const schema = p && p.intent_schema;
  if (Array.isArray(schema) && schema.length) return schema;
  return state.meta.intent_classes;
}

/* ---------------- 初始化 ---------------- */
async function init() {
  state.meta = await api("GET", "/meta");
  state.products = await api("GET", "/products");
  state.current = state.products[0] ? state.products[0].id : null;
  renderProductSwitch();
  if (!state.current) {
    state.view = "products";
  }
  state.llm = await api("GET", "/llm/status");
  renderAiStatus();
  renderNav();
  /* hash 路由（2026-10-15 验收修复）：支持刷新/直链恢复视图，如 #/questions */
  const h = (location.hash || "").replace(/^#\/?/, "");
  if (h && NAV.some((n) => n.id === h)) state.view = h;
  setView(state.view);
  window.addEventListener("hashchange", () => {
    const v = (location.hash || "").replace(/^#\/?/, "");
    if (v && NAV.some((n) => n.id === v) && v !== state.view) setView(v);
  });
}

function renderAiStatus() {
  const el = $("#ai-status");
  if (!el || !state.llm) return;
  if (state.llm.disabled || state.llm.available === false || state.llm.mode === "manual") {
    el.className = "ai-chip mock";
    el.textContent = "人工作业可用 · 自动模型未开放";
    el.title = "评分、分类与内容可人工维护；模型调用尚未开放，不产生外部调用或模拟结果。";
  } else if (state.llm.mock) {
    el.className = "ai-chip mock";
    el.textContent = "AI 演示模式";
    el.title = "未配置 LLM_API_KEY：AI 草稿由确定性启发式生成。配置 key 后即走真实模型。";
  } else {
    el.className = "ai-chip real";
    el.textContent = "AI 真实模型 · " + (state.llm.model || "");
    el.title = "AI 生产走真实 LLM（" + (state.llm.base_url || "") + "）";
  }
}

function renderNav() {
  const nav = $("#nav");
  nav.innerHTML = NAV.map((n) =>
    `<button type="button" class="nav-item ${n.id === state.view ? "active" : ""}" data-view="${n.id}" aria-current="${n.id === state.view ? "page" : "false"}">
       ${icon(n.icon)}<span>${esc(n.label)}</span></button>`
  ).join("");
  $$(".nav-item", nav).forEach((el) =>
    el.onclick = () => setView(el.dataset.view));
}

function renderProductSwitch() {
  const sel = $("#product-switch");
  sel.innerHTML = state.products.map((p) =>
    `<option value="${p.id}" ${p.id === state.current ? "selected" : ""}>${esc(p.name)}</option>`
  ).join("");
  sel.onchange = () => { state.current = Number(sel.value); render(); };
}

function setView(v) {
  if(window.OperatorFrame.beforeNavigate && !window.OperatorFrame.beforeNavigate()) return;
  closeModal();
  state.view = v;
  window.OperatorFrame.view(v);
  if (("#/" + v) !== location.hash) {
    try { history.replaceState(null, "", "#/" + v); } catch (e) { location.hash = "#/" + v; }
  }
  renderNav();
  $("#view-title").textContent = VIEW_TITLE[v] || v;
  render();
}

function render() {
  operatorViewEpoch++;
  window.OperatorFrame.view(state.view);
  const v = state.view;
  const epoch = operatorViewEpoch;
  const host = $("#view");
  host.setAttribute("aria-busy", "true");
  host.innerHTML = '<p role="status">正在读取，请稍候…</p>';
  const map = {
    dashboard: renderDashboard, products: renderProducts, personas: renderPersonas,
    scenarios: renderScenarios, questions: renderQuestions, clusters: renderClusters,
    briefs: renderBriefs, citations: renderCitations, trends: renderTrends, entities: renderEntities,
    gaps: renderContentGaps, keywords: renderKeywords, prompts: renderPrompts,
    seo: renderSeoGrowth, manual: renderManual,
  };
  Promise.resolve((map[v] || renderDashboard)()).catch(e => {
    if(epoch !== operatorViewEpoch) return;
    window.OperatorFrame.showError(e.message, () => render());
  }).finally(() => {
    if(epoch !== operatorViewEpoch) return;
    host.setAttribute("aria-busy", "false");
    operatorMountPagers();
  });
}

function requireProduct() {
  if (state.current) return true;
  if (typeof _operatorViewEpoch !== "undefined" && _operatorViewEpoch !== operatorViewEpoch) return; $("#view").innerHTML = `<div class="empty">
    ${icon("ic-box", "icon")}
    <p>请先在「产品」中创建一个产品，再录入该产品的意图数据。</p>
    <p>请由总部管理先为当前项目开通产品与站点，再进入专业作业。</p>
  </div>`;
  return false;
}

/* ================= 概览 ================= */
async function renderDashboard() {
  const _operatorViewEpoch = operatorViewEpoch;
  if (!requireProduct()) return;
  const pid = state.current;
  const d = await api("GET", `/products/${pid}/dashboard`);
  const p = d.priority_distribution;
  const maxP = Math.max(1, ...Object.values(p));
  const distBars = Object.entries(p).map(([k, v]) =>
    `<div style="margin-bottom:8px">
       <div style="display:flex;justify-content:space-between;font-size:12px"><span>${esc(k === "null" || k === "undefined" || !k ? "待分类" : k)}</span><span>${v}</span></div>
       <div class="bar"><span style="width:${(v / maxP) * 100}%;background:var(--p-${k})"></span></div>
     </div>`).join("");
  const briefBars = Object.entries(d.brief_status).map(([k, v]) =>
    `<span class="chip">${esc(k === "null" || k === "undefined" || !k ? "状态未登记" : k)} · ${v}</span>`).join("") || '<span class="muted">暂无</span>';

  if (typeof _operatorViewEpoch !== "undefined" && _operatorViewEpoch !== operatorViewEpoch) return; $("#view").innerHTML = `
    <div class="grid cards">
      ${statCard("问句总数", d.questions_total)}
      ${statCard("已评分", d.questions_scored)}
      ${statCard("P0 高优", p.P0, "var(--p-P0)")}
      ${statCard("问题簇", d.clusters)}
      ${statCard("内容 Brief", d.briefs)}
      ${statCard("活跃监测", d.active_monitors)}
      ${statCard("待复测", d.monitors_due, "var(--c-warning)")}
      ${statCard("引用追踪记录", d.citations)}
      ${statCard("内容缺口", d.content_gaps || 0)}
    </div>

    <div class="two-col" style="margin-top:18px">
      <div class="panel">
        <div class="panel-head"><h2>优先级分布</h2></div>
        <div class="panel-body">${distBars}</div>
      </div>
      <div class="panel">
        <div class="panel-head"><h2>闭环进度</h2></div>
        <div class="panel-body">
          <div class="kv">
            <dt>品牌被提及率</dt><dd><b style="color:var(--c-success)">${d.citations ? Math.round(d.brand_mention_rate * 100) + "%" : "—"}</b>（${d.brand_mentioned}/${d.citations}）</dd>
            <dt>内容被引用率</dt><dd><b>${d.citations ? Math.round(d.content_mention_rate * 100) + "%" : "—"}</b>（${d.content_mentioned}/${d.citations}）</dd>
            <dt>平均被引位置</dt><dd>${d.avg_position ? "#" + d.avg_position : "—"}</dd>
            <dt>Brief 状态</dt><dd>${briefBars}</dd>
            <dt>实体 / 画像 / 场景</dt><dd>${d.entities} / ${d.personas} / ${d.scenarios}</dd>
          </div>
        </div>
      </div>
    </div>

    <div class="panel">
      <div class="panel-head"><h2>下一步建议</h2></div>
      <div class="panel-body">
        ${nextHint(d)}
      </div>
    </div>

    <div class="panel" style="border-left:3px solid var(--c-accent)">
      <div class="panel-head">
        <h2>实时 AI 引用查询</h2>
        <span class="muted">自动外采尚未开放；可人工登记实际检查记录</span>
      </div>
      <div class="panel-body" style="display:flex;align-items:center;gap:14px;flex-wrap:wrap">
        <div style="flex:1;min-width:240px">
          <div style="font-size:13px;color:var(--c-text);margin-bottom:4px">
            当前有 <b>${d.active_monitors}</b> 个监测任务；可进入引用追踪维护任务与检查记录
          </div>
          <div class="muted" style="font-size:12px">
            自动任务、费用授权与持久队列完成验收前，不调用外部模型，也不生成模拟引用结果
          </div>
        </div>
        <button class="btn btn-primary" id="dash-realtime-btn">${icon("ic-bolt")} 一键实时查询</button>
        <button class="btn btn-sm" id="dash-open-citations">查看完整报告 →</button>
      </div>
    </div>`;

  $("#dash-realtime-btn").onclick = async () => {
    const monitors = await api("GET", `/products/${pid}/monitors`);
    if (!monitors.length) { toast("暂无监测任务，请先到「引用追踪闭环」生成"); return; }
    await realtimeQueryForm(monitors);
    const d2 = await api("GET", `/products/${pid}/dashboard`);
    Object.assign(d, d2);
    toast("查询完成，引用数据已刷新");
  };
  $("#dash-open-citations").onclick = () => { state.view = "citations"; render(); };
}
function statCard(label, num, color) {
  return `<div class="card"><div class="stat-num" style="${color ? `color:${color}` : ""}">${num}</div>
    <div class="stat-label">${esc(label)}</div></div>`;
}
function nextHint(d) {
  if (d.questions_total === 0) return "<p class='muted'>从「问句库」开始采集用户原话（来源选 Reddit/PAA/Forum 等）。</p>";
  if (d.questions_scored < d.questions_total) return "<p class='muted'>还有问句未评分，进入「问句库」用四维滑块打分，系统会自动算出 P0/P1/P2。</p>";
  if (d.clusters === 0) return "<p class='muted'>高分问句已就绪，进入「问题簇」把它们聚类成内容主题。</p>";
  if (d.briefs === 0) return "<p class='muted'>已有问题簇，进入「问题簇」点击「生成 Brief」产出内容计划。</p>";
  if (d.citations === 0) return "<p class='muted'>内容已规划，发布后到「AI 引用追踪」验证 ChatGPT/Gemini 是否引用你。</p>";
  return "<p class='muted'>已有流程记录；请继续核验来源与采集条件，记录数量不能证明增长效果。</p>";
}

/* ================= 产品 ================= */
async function renderProducts() {
  const _operatorViewEpoch = operatorViewEpoch;
  const list = await api("GET", "/products");
  state.products = list;
  renderProductSwitch();
  if (typeof _operatorViewEpoch !== "undefined" && _operatorViewEpoch !== operatorViewEpoch) return; $("#view").innerHTML = `
    <div class="panel">
      <div class="panel-head"><h2>产品列表</h2>
        <button class="btn btn-primary btn-sm" id="add-p">${icon("ic-plus", "icon-sm")} 新建产品</button></div>
      <div class="panel-body">
        ${list.length ? `<table><thead><tr><th>名称</th><th>目标市场</th><th>目标客户</th><th>说明</th><th></th></tr></thead><tbody>
          ${list.map((p) => `<tr>
            <td><b>${esc(p.name)}</b>${p.id === state.current ? ' <span class="badge badge-success">当前</span>' : ""}</td>
            <td>${esc(p.market)}</td><td>${esc(p.target_customer)}</td><td class="muted">${esc(p.description)}</td>
            <td class="row-actions">
              <button class="btn btn-sm" data-act="use" data-id="${p.id}">设为当前</button>
              <button class="btn btn-sm" data-act="edit" data-id="${p.id}">编辑</button>
              <button class="btn btn-sm btn-icon" data-act="del" data-id="${p.id}" title="删除">${icon("ic-trash", "icon-sm")}</button>
            </td></tr>`).join("")}
        </tbody></table>` : `<div class="empty">${icon("ic-box")}<p>还没有产品。点击右上角「新建产品」开始。</p></div>`}
      </div>
    </div>`;
  $("#add-p").onclick = () => productForm(null);
  $$("[data-act]").forEach((b) => {
    const id = Number(b.dataset.id);
    if (b.dataset.act === "use") b.onclick = () => { state.current = id; render(); };
    if (b.dataset.act === "edit") b.onclick = () => productForm(list.find((x) => x.id === id));
    if (b.dataset.act === "del") b.onclick = async () => {
      if (!confirm("删除该产品及其全部意图数据？")) return;
      await api("DELETE", `/products/${id}`);
      if (state.current === id) state.current = null;
      await renderProducts();
      toast("已删除");
    };
  });
}

function productForm(p) {
  const isEdit = !!p;
  const schemaVal = (p && Array.isArray(p.intent_schema) && p.intent_schema.length)
    ? p.intent_schema.join("\n") : "";
  const body = `
    ${field("产品名称", `<input class="input" id="f-name" value="${esc(p?.name || "")}">`)}
    ${field("目标市场", `<input class="input" id="f-market" value="${esc(p?.market || "")}" placeholder="如：欧美 B2B">`)}
    ${field("目标客户", `<input class="input" id="f-cust" value="${esc(p?.target_customer || "")}">`)}
    ${field("产品说明", `<textarea class="textarea" id="f-desc">${esc(p?.description || "")}</textarea>`)}
    ${field("领域意图体系", `<textarea class="textarea" id="f-schema" placeholder="每行一个，如：\n设备兼容\nAI 喂料\n遗留格式\n隐私安全\n对比选型\n操作教程\n场景方案">${esc(schemaVal)}</textarea><div class="muted" style="font-size:11px">留空则沿用全局 12 类通用意图。问句「意图分类」下拉将使用此列表。</div>`)}
  `;
  openModal(isEdit ? "编辑产品" : "新建产品", body, {
    onSave: async (close) => {
      const raw = $("#f-schema").value.trim();
      const schema = raw ? raw.split(/[\n,，]+/).map((s) => s.trim()).filter(Boolean) : null;
      const payload = {
        name: $("#f-name").value.trim(),
        market: $("#f-market").value.trim(),
        target_customer: $("#f-cust").value.trim(),
        description: $("#f-desc").value.trim(),
        intent_schema: schema,
      };
      if (!payload.name) return toast("请填写产品名称");
      if (isEdit) await api("PUT", `/products/${p.id}`, payload);
      else { const r = await api("POST", "/products", payload); state.current = r.id; }
      close(); await renderProducts(); toast("已保存");
    },
  });
}

/* ================= 用户画像 ================= */
async function renderPersonas() {
  const _operatorViewEpoch = operatorViewEpoch;
  if (!requireProduct()) return;
  const list = await api("GET", `/products/${state.current}/personas`);
  if (typeof _operatorViewEpoch !== "undefined" && _operatorViewEpoch !== operatorViewEpoch) return; $("#view").innerHTML = panelWithAdd("用户画像", "新建画像", "persona",
    list.length ? `<table><thead><tr><th>名称</th><th>描述</th><th>痛点</th><th>目标</th><th></th></tr></thead><tbody>
      ${list.map((x) => `<tr><td><b>${esc(x.name)}</b></td><td class="muted">${esc(x.description)}</td>
        <td class="muted">${esc(x.pain_points)}</td><td class="muted">${esc(x.goals)}</td>
        <td class="row-actions"><button class="btn btn-sm" data-edit="${x.id}">编辑</button>
        <button class="btn btn-sm btn-icon" data-del="${x.id}">${icon("ic-trash", "icon-sm")}</button></td></tr>`).join("")}
    </tbody></table>` : emptyHint("ic-users", "还没有画像，点击右上角新建。"));
  wireCrud(list, "persona", "/personas", (x) => x.id, personaForm);
}
function personaForm(x) {
  const body = `
    ${field("画像名称", `<input class="input" id="f-name" value="${esc(x?.name || "")}">`)}
    ${field("描述", `<textarea class="textarea" id="f-desc">${esc(x?.description || "")}</textarea>`)}
    ${field("痛点", `<textarea class="textarea" id="f-pain">${esc(x?.pain_points || "")}</textarea>`)}
    ${field("目标", `<textarea class="textarea" id="f-goal">${esc(x?.goals || "")}</textarea>`)}
  `;
  openModal(x ? "编辑画像" : "新建画像", body, {
    onSave: async (close) => {
      const payload = { product_id: state.current, name: $("#f-name").value.trim(),
        description: $("#f-desc").value.trim(), pain_points: $("#f-pain").value.trim(), goals: $("#f-goal").value.trim() };
      if (!payload.name) return toast("请填写名称");
      if (x) await api("PUT", `/personas/${x.id}`, payload);
      else await api("POST", "/personas", payload);
      close(); await renderPersonas(); toast("已保存");
    },
  });
}

/* ================= 场景 ================= */
async function renderScenarios() {
  const _operatorViewEpoch = operatorViewEpoch;
  if (!requireProduct()) return;
  const list = await api("GET", `/products/${state.current}/scenarios`);
  if (typeof _operatorViewEpoch !== "undefined" && _operatorViewEpoch !== operatorViewEpoch) return; $("#view").innerHTML = panelWithAdd("场景", "新建场景", "scenario",
    list.length ? `<table><thead><tr><th>名称</th><th>阶段</th><th>描述</th><th></th></tr></thead><tbody>
      ${list.map((x) => `<tr><td><b>${esc(x.name)}</b></td><td>${prioBadge(x.stage)}</td>
        <td class="muted">${esc(x.description)}</td>
        <td class="row-actions"><button class="btn btn-sm" data-edit="${x.id}">编辑</button>
        <button class="btn btn-sm btn-icon" data-del="${x.id}">${icon("ic-trash", "icon-sm")}</button></td></tr>`).join("")}
    </tbody></table>` : emptyHint("ic-map", "还没有场景，点击右上角新建。"));
  wireCrud(list, "scenario", "/scenarios", (x) => x.id, scenarioForm);
}
function scenarioForm(x) {
  const body = `
    ${field("场景名称", `<input class="input" id="f-name" value="${esc(x?.name || "")}">`)}
    ${field("阶段", `<select class="select" id="f-stage">${opt(state.meta.stages, x?.stage)}</select>`)}
    ${field("描述", `<textarea class="textarea" id="f-desc">${esc(x?.description || "")}</textarea>`)}
  `;
  openModal(x ? "编辑场景" : "新建场景", body, {
    onSave: async (close) => {
      const payload = { product_id: state.current, name: $("#f-name").value.trim(),
        stage: $("#f-stage").value, description: $("#f-desc").value.trim() };
      if (!payload.name) return toast("请填写名称");
      if (x) await api("PUT", `/scenarios/${x.id}`, payload);
      else await api("POST", "/scenarios", payload);
      close(); await renderScenarios(); toast("已保存");
    },
  });
}

/* ================= 问句库（核心） ================= */
async function renderQuestions() {
  const _operatorViewEpoch = operatorViewEpoch;
  if (!requireProduct()) return;
  const list = await api("GET", `/products/${state.current}/questions`);
  const personas = await api("GET", `/products/${state.current}/personas`);
  const intentOpts = currentIntentClasses();
  if (typeof _operatorViewEpoch !== "undefined" && _operatorViewEpoch !== operatorViewEpoch) return; $("#view").innerHTML = `
    <div class="panel">
      <div class="panel-head"><h2>问句库（本页${list.length}条）</h2>
        <div class="actions">
          <button class="btn btn-sm" id="ai-score-batch">${icon("ic-sparkles", "icon-sm")} AI 评分(未评)</button>
          <button class="btn btn-primary btn-sm" id="add-q">${icon("ic-plus", "icon-sm")} 新增问句</button>
        </div></div>
      <div class="panel-body" style="padding:0">
        ${list.length ? `<table><thead><tr><th style="width:34%">用户原话</th><th>意图</th><th>来源</th><th>阶段</th><th>评分</th><th></th></tr></thead><tbody>
          ${list.map((q) => `<tr>
            <td>${esc(q.text)}<div class="muted" style="font-size:11px">${esc(q.notes || "")}</div></td>
            <td>${q.intent_class ? `<span class="chip">${esc(q.intent_class)}</span>` : '<span class="muted">—</span>'}</td>
            <td class="muted">${esc(q.source)}</td>
            <td>${q.stage ? prioBadge(q.stage) : "—"}</td>
            <td>${q.total !== null ? `<b>${q.total}</b> ${prioBadge(q.priority)}` : prioBadge("未评分")}</td>
            <td class="row-actions">
              <button class="btn btn-sm" data-ai="${q.id}">${icon("ic-sparkles", "icon-sm")} AI 打分</button>
              <button class="btn btn-sm" data-edit="${q.id}">编辑</button>
              <button class="btn btn-sm" data-cluster="${q.id}">分配簇</button>
              <button class="btn btn-sm btn-icon" data-del="${q.id}">${icon("ic-trash", "icon-sm")}</button>
            </td></tr>`).join("")}
        </tbody></table>` : `<div class="empty" style="padding:30px">${icon("ic-message")}<p>还没有问句。点击「新增问句」开始采集用户原话。</p></div>`}
      </div>
    </div>`;
  $("#add-q").onclick = () => questionForm(null, personas);
  $("#ai-score-batch").onclick = aiScoreBatch;
  $$("[data-edit]").forEach((b) => b.onclick = () => questionForm(list.find((q) => q.id == b.dataset.edit), personas));
  $$("[data-del]").forEach((b) => b.onclick = async () => {
    if (!confirm("删除该问句？")) return; await api("DELETE", `/questions/${b.dataset.del}`); await renderQuestions(); toast("已删除");
  });
  $$("[data-cluster]").forEach((b) => b.onclick = () => assignClusterModal(Number(b.dataset.cluster)));
  $$("[data-ai]").forEach((b) => b.onclick = () => aiScoreOne(list.find((q) => q.id == b.dataset.ai)));
}

function questionForm(q, personas) {
  const v = (k) => (q ? q[k] : "");
  const body = `
    ${field("用户原话", `<textarea class="textarea" id="f-text">${esc(v("text"))}</textarea>`)}
    <div class="two-col">
      ${field("来源", `<select class="select" id="f-source">${opt(state.meta.sources, v("source") || "manual")}</select>`)}
      ${field("意图分类", `<select class="select" id="f-intent"><option value="">未分类</option>${opt(currentIntentClasses(), v("intent_class"))}</select>`)}
    </div>
    <div class="two-col">
      ${field("用户阶段", `<select class="select" id="f-stage"><option value="">未选</option>${opt(state.meta.stages, v("stage"))}</select>`)}
      ${field("情感倾向", `<select class="select" id="f-sent"><option value="">未选</option>${opt(state.meta.sentiments, v("sentiment"))}</select>`)}
    </div>
    ${field("关联画像", `<select class="select" id="f-persona"><option value="">未关联</option>${personas.map((p) => `<option value="${p.id}" ${p.id === v("persona_id") ? "selected" : ""}>${esc(p.name)}</option>`).join("")}</select>`)}
    <div style="margin-top:6px;border-top:1px solid var(--c-border);padding-top:12px">
      <b>GEO Score（四维 1-5，系统自动算总分与优先级）</b>
      ${slider("commercial", "商业价值", v("commercial"))}
      ${slider("citation", "AI 引用潜力", v("citation"))}
      ${slider("brand", "品牌植入机会", v("brand"))}
      ${slider("competition", "内容竞争(难度)", v("competition"))}
      <div class="score-preview"><span>实时：</span><span class="num" id="f-total">—</span>${prioBadge("未评分")}<span id="f-prio-wrap"></span></div>
    </div>
    ${field("备注", `<textarea class="textarea" id="f-notes">${esc(v("notes"))}</textarea>`)}
  `;
  openModal(q ? "编辑问句" : "新增问句", body, {
    onOpen: () => bindScorePreview(),
    onSave: async (close) => {
      const payload = {
        product_id: state.current,
        text: $("#f-text").value.trim(),
        source: $("#f-source").value,
        intent_class: $("#f-intent").value || null,
        stage: $("#f-stage").value || null,
        sentiment: $("#f-sent").value || null,
        persona_id: Number($("#f-persona").value) || null,
        commercial: scoreInputValue('commercial'),
        citation: scoreInputValue('citation'),
        brand: scoreInputValue('brand'),
        competition: scoreInputValue('competition'),
        notes: $("#f-notes").value.trim() || null,
      };
      if (!payload.text) return toast("请填写用户原话");
      if (q) await api("PUT", `/questions/${q.id}`, payload);
      else await api("POST", "/questions", payload);
      close(); await renderQuestions(); toast("已保存");
    },
  });
}
function slider(key, label, val) {
  const checked = val !== null && val !== undefined && val !== "";
  return `<div class="slider-row">
    <label>${esc(label)}</label>
    <input type="range" min="1" max="5" step="1" id="f-${key}" value="${checked ? val : 3}" data-score="1" data-on="${checked?'1':'0'}">
    <span class="slider-val" id="fv-${key}">${checked ? val : "—"}</span>
  </div>`;
}
function numOrNull(v) { return v === "" || v === null ? null : Number(v); }
function scoreInputValue(key){const input=$('#f-'+key);return input?.dataset.on==='1'?Number(input.value):null;}
function bindScorePreview() {
  const keys = ["commercial", "citation", "brand", "competition"];
  const update = () => {
    const vals = keys.map((k) => { const el = $("#f-" + k); return el && el.dataset.on === "1" ? Number(el.value) : null; });
    const active = vals.filter((x) => x !== null);
    if (active.length === 4) {
      const total = active.reduce((a, b) => a + b, 0);
      const prio = total >= 17 ? "P0" : total >= 14 ? "P1" : total >= 10 ? "P2" : "暂缓";
      $("#f-total").textContent = total;
      $("#f-prio-wrap").innerHTML = prioBadge(prio);
    } else {
      $("#f-total").textContent = "—";
      $("#f-prio-wrap").innerHTML = prioBadge("未评分");
    }
  };
  keys.forEach((k) => {
    const el = $("#f-" + k);
    if (!el) return;
    el.oninput = () => { el.dataset.on='1'; $("#fv-" + k).textContent = el.value; update(); };
  });
  update();
}

async function assignClusterModal(qid) {
  const clusters = await api("GET", `/products/${state.current}/clusters`);
  const assigned = await api("GET", `/questions/${qid}/clusters`);
  if (!clusters.length) { toast("请先到「问题簇」创建簇"); return; }
  const body = `<p class="muted">为该问句选择所属问题簇（可多选）：</p>${clusters.map((c) =>
    `<label style="display:block;padding:7px 0;border-bottom:1px solid var(--c-border)">
      <input type="checkbox" class="cc" value="${c.id}" ${assigned.includes(c.id) ? "checked" : ""}>
      <b>${esc(c.name)}</b> <span class="muted">(${esc(c.parent_topic || "")})</span></label>`).join("")}`;
  openModal("分配问题簇", body, {
    saveText: "保存分配",
    onSave: async (close) => {
      const chosen = $$(".cc").filter((c) => c.checked).map((c) => Number(c.value));
      for (const cid of clusters) {
        const has = chosen.includes(cid.id);
        const was = assigned.includes(cid.id);
        if (has && !was) await api("POST", `/questions/${qid}/cluster/${cid.id}`);
        if (!has && was) await api("DELETE", `/questions/${qid}/cluster/${cid.id}`);
      }
      close(); await renderQuestions(); toast("已更新分配");
    },
  });
}

/* ================= 问题簇 ================= */
async function renderClusters() {
  const _operatorViewEpoch = operatorViewEpoch;
  if (!requireProduct()) return;
  const list = await api("GET", `/products/${state.current}/clusters`);
  if (typeof _operatorViewEpoch !== "undefined" && _operatorViewEpoch !== operatorViewEpoch) return; $("#view").innerHTML = `
    <div class="panel">
      <div class="panel-head"><h2>问题簇（${list.length}）</h2>
        <div class="actions">
          <button class="btn btn-sm" id="ai-cluster">${icon("ic-sparkles", "icon-sm")} AI 聚类(未归类)</button>
          <button class="btn btn-primary btn-sm" id="add-c">${icon("ic-plus", "icon-sm")} 新建问题簇</button>
        </div></div>
      <div class="panel-body">
        ${list.length ? list.map((c) => `<div class="prompt-card" style="margin-bottom:12px">
          <div style="display:flex;justify-content:space-between;align-items:center">
            <div><b>${esc(c.name)}</b> <span class="muted">· ${esc(c.parent_topic || "")}</span>
              <span class="badge badge-line">${c.question_count} 问句</span></div>
            <div class="row-actions">
              <button class="btn btn-sm" data-aibrief="${c.id}">${icon("ic-sparkles", "icon-sm")} AI 生成</button>
              <button class="btn btn-sm" data-gen="${c.id}">${icon("ic-bolt", "icon-sm")} 生成 Brief</button>
              <button class="btn btn-sm" data-q="${c.id}">查看问句</button>
              <button class="btn btn-sm" data-edit="${c.id}">编辑</button>
              <button class="btn btn-sm btn-icon" data-del="${c.id}">${icon("ic-trash", "icon-sm")}</button>
            </div>
          </div>
          <div class="muted" style="margin-top:6px">${esc(c.description || "")}</div>
        </div>`).join("") : emptyHint("ic-layers", "还没有问题簇，点击右上角新建。")}
      </div>
    </div>`;
  $("#add-c").onclick = () => clusterForm(null);
  $("#ai-cluster").onclick = aiCluster;
  $$("[data-edit]").forEach((b) => b.onclick = () => clusterForm(list.find((c) => c.id == b.dataset.edit)));
  $$("[data-del]").forEach((b) => b.onclick = async () => {
    if (!confirm("删除该问题簇？问句关联会一并解除。")) return;
    await api("DELETE", `/clusters/${b.dataset.del}`); await renderClusters(); toast("已删除");
  });
  $$("[data-gen]").forEach((b) => b.onclick = async () => {
    if (!confirm("根据该簇问句自动生成一篇内容 Brief？")) return;
    await api("POST", `/clusters/${b.dataset.gen}/generate-brief`);
    toast("Brief 已生成，去「内容 Brief」查看"); await renderClusters();
  });
  $$("[data-aibrief]").forEach((b) => b.onclick = () => {
    const c = list.find((x) => x.id == b.dataset.aibrief);
    aiBrief(Number(b.dataset.aibrief), c.name);
  });
  $$("[data-q]").forEach((b) => b.onclick = () => showClusterQuestions(Number(b.dataset.q)));
}
function clusterForm(c) {
  const body = `
    ${field("簇名称", `<input class="input" id="f-name" value="${esc(c?.name || "")}">`)}
    ${field("父主题", `<input class="input" id="f-topic" value="${esc(c?.parent_topic || "")}" placeholder="如：GEO 是什么">`)}
    ${field("描述", `<textarea class="textarea" id="f-desc">${esc(c?.description || "")}</textarea>`)}
  `;
  openModal(c ? "编辑问题簇" : "新建问题簇", body, {
    onSave: async (close) => {
      const payload = { product_id: state.current, name: $("#f-name").value.trim(),
        parent_topic: $("#f-topic").value.trim(), description: $("#f-desc").value.trim() };
      if (!payload.name) return toast("请填写名称");
      if (c) await api("PUT", `/clusters/${c.id}`, payload);
      else await api("POST", "/clusters", payload);
      close(); await renderClusters(); toast("已保存");
    },
  });
}
async function showClusterQuestions(cid) {
  const cluster = (await api("GET", `/products/${state.current}/clusters`)).find((c) => c.id === cid);
  const qs = await api("GET", `/clusters/${cid}/questions`);
  openModal(`问题簇问句 · ${cluster.name}`, `
    <p class="muted">共 ${qs.length} 条问句（按评分降序）：</p>
    ${qs.length ? qs.map((q) => `<div style="padding:8px 0;border-bottom:1px solid var(--c-border)">
      ${q.total !== null ? `<b>${q.total}</b> ${prioBadge(q.priority)} ` : ""}${esc(q.text)}</div>`).join("") : '<p class="muted">该簇暂无问句，去「问句库」分配。</p>'}
  `, { saveText: "关闭", onSave: (close) => close() });
}

/* ================= 内容 Brief ================= */
let briefTab = "idea"; // "idea" | "guide"

async function renderBriefs() {
  const _operatorViewEpoch = operatorViewEpoch;
  if (!requireProduct()) return;
  const list = await api("GET", `/products/${state.current}/briefs`);
  const clusters = await api("GET", `/products/${state.current}/clusters`);
  const ideaList = list.filter((b) => b.status === "idea");
  const guideList = list.filter((b) => ["writing","published","updated"].includes(b.status));
  const unregisteredList = list.filter((b) => !["idea","writing","published","updated"].includes(b.status));
  const active = briefTab === "idea" ? ideaList : briefTab === "guide" ? guideList : unregisteredList;
  const statusCounts=operatorListResults.get('briefs')?.status_counts;
  const ideaN = statusCounts?.idea??ideaList.length, guideN = statusCounts?.adopted??guideList.length;
  if (typeof _operatorViewEpoch !== "undefined" && _operatorViewEpoch !== operatorViewEpoch) return; $("#view").innerHTML = `
    <div class="panel">
      <div class="panel-head"><h2>内容 Brief（本页${active.length}条）</h2>
        <button class="btn btn-primary btn-sm" id="add-b">${icon("ic-plus", "icon-sm")} 新建 Brief</button></div>
      <div class="panel-body">
        <div style="display:flex;gap:0;margin-bottom:12px;border-bottom:1px solid var(--c-border)">
          <button class="btn btn-sm ${briefTab==="idea"?"btn-primary":""}" id="tab-idea" style="border-radius:4px 4px 0 0;border-bottom:none;margin-bottom:-1px;position:relative;z-index:1">草稿 <span class="badge ${ideaN?"badge-p1":"badge-line"}" style="margin-left:4px">${ideaN}</span></button>
          <button class="btn btn-sm ${briefTab==="guide"?"btn-primary":""}" id="tab-guide" style="border-radius:4px 4px 0 0;border-bottom:none;margin-bottom:-1px;position:relative;z-index:1">已采纳 <span class="badge ${guideN?"badge-success":"badge-line"}" style="margin-left:4px">${guideN}</span></button>
          <button class="btn btn-sm ${briefTab==="unregistered"?"btn-primary":""}" id="tab-unregistered">状态未登记 <span class="badge badge-line">${statusCounts?.unregistered??unregisteredList.length}</span></button>
        </div>
        ${active.length ? active.map((b) => `<div class="prompt-card" style="margin-bottom:12px">
          <div style="display:flex;justify-content:space-between;align-items:center">
            <div><b>${esc(b.title)}</b> ${statusBadge(b.status)} ${b.content_type ? `<span class="badge badge-line">${esc(b.content_type)}</span>` : ""}</div>
            <div class="row-actions">
              ${b.status === "idea" ? `<button class="btn btn-sm btn-primary" data-adopt="${b.id}">采纳</button>` : ""}
              <button class="btn btn-sm" data-edit="${b.id}">编辑</button>
              <button class="btn btn-sm btn-icon" data-del="${b.id}">${icon("ic-trash", "icon-sm")}</button>
            </div>
          </div>
          ${b.target_url ? `<div class="muted" style="margin-top:4px">目标 URL：${esc(b.target_url)}</div>` : ""}
          ${b.assigned_to || b.channel ? `<div class="muted" style="font-size:12px">负责人：${esc(b.assigned_to || "—")} · 渠道：${esc(b.channel || "—")}</div>` : ""}
          ${b.body ? `<pre style="white-space:pre-wrap;background:var(--c-surface-2);padding:10px;border-radius:6px;margin-top:8px;max-height:200px;overflow:auto;font-size:12px">${esc(b.body)}</pre>` : ""}
        </div>`).join("") : emptyHint("ic-file", briefTab==="idea"?"暂无草稿 Brief。可在「问题簇」点击「生成 Brief」或「AI Brief」自动产出。":"暂无已采纳的 Brief。在「草稿」中点击「采纳」推进到写作。")}
      </div>
    </div>`;
  // tab switching
  const switchTab=tab=>{briefTab=tab;operatorListState.set('briefs',{...(operatorListState.get('briefs')||{}),page:1});renderBriefs();};
  $("#tab-idea").onclick = () => switchTab('idea');
  $("#tab-guide").onclick = () => switchTab('guide');
  $("#tab-unregistered").onclick = () => switchTab('unregistered');
  // actions
  $("#add-b").onclick = () => briefForm(null, clusters);
  $$("[data-edit]").forEach((b) => b.onclick = () => briefForm(list.find((x) => x.id == b.dataset.edit), clusters));
  $$("[data-del]").forEach((b) => b.onclick = async () => {
    if (!confirm("删除该 Brief？")) return; await api("DELETE", `/briefs/${b.dataset.del}`); await renderBriefs(); toast("已删除");
  });
  $$("[data-adopt]").forEach((b) => b.onclick = async () => {
    if (!confirm("采纳此 Brief？将状态从「草稿」推进为「写作中」，可用于实际内容生产。")) return;
    await api("POST", `/briefs/${b.dataset.adopt}/adopt`, { target_status: "writing" });
    toast("✅ 已采纳，状态 → 写作中");
    briefTab = "guide"; // auto-switch to guide tab after adopt
    await renderBriefs();
  });
}
function statusBadge(s) {
  const map = { idea: "badge-line", writing: "badge-p2", published: "badge-success", updated: "badge-p1" };
  return `<span class="badge ${map[s] || "badge-line"}">${esc(s || "状态未登记")}</span>`;
}
function briefForm(b, clusters) {
  const body = `
    <div class="brief-meta-bar">
      ${field("标题", `<input class="input" id="f-title" value="${esc(b?.title || "")}">`)}
      ${field("问题簇", `<select class="select" id="f-cluster"><option value="">未关联</option>${clusters.map((c) => `<option value="${c.id}" ${c.id === b?.cluster_id ? "selected" : ""}>${esc(c.name)}</option>`).join("")}</select>`)}
      <div class="field field-sm"><span>状态</span><select class="select" id="f-status">${b&&!state.meta.brief_status.includes(b.status)?'<option value="" selected>请选择确认后的状态</option>':""}${opt(state.meta.brief_status, b?b.status:"idea")}</select></div>
      <div class="field field-sm"><span>类型</span><select class="select" id="f-type">${opt(state.meta.content_types, b?.content_type || "article")}</select></div>
      <div class="field field-sm"><span>目标URL</span><input class="input" id="f-url" value="${esc(b?.target_url || "")}"></div>
    </div>
    <div class="split-pane">
      <div class="pane pane-editor">
        <div class="pane-label">Markdown 编辑（可从外部粘贴）</div>
        <textarea id="f-body" placeholder="在此输入或粘贴 Markdown 正文…&#10;&#10;# 标题&#10;## H2 小节&#10;**加粗** · 列表 · 表格&#10;[链接](https://…)">${esc(b?.body || "")}</textarea>
      </div>
      <div class="pane pane-preview">
        <div class="pane-label">实时预览</div>
        <div id="md-preview"></div>
      </div>
    </div>`;
  openModal(b ? "编辑 Brief" : "新建 Brief", body, { fullscreen: true, saveText: "保存" });
  // 实时预览
  const ta = $("#f-body"), pv = $("#md-preview");
  const sync = () => { pv.innerHTML = renderMarkdown(ta.value); };
  sync();
  ta.addEventListener("input", sync);
  // Tab keeps standard keyboard focus navigation; Ctrl+Enter saves explicitly.
  ta.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && e.ctrlKey) { e.preventDefault(); $("#ms").click(); }
  });
  // 保存
  $("#ms").onclick = async () => {
    const payload = { product_id: state.current, cluster_id: Number($("#f-cluster").value) || null,
      title: $("#f-title").value.trim(), content_type: $("#f-type").value, status: $("#f-status").value,
      target_url: $("#f-url").value.trim() || null, assigned_to: b?.assigned_to || null,
      channel: b?.channel || null, body: ta.value.trim() || null };
    if (!payload.title) return toast("请填写标题");
    if (!payload.status) return toast("请先确认并选择内容状态，历史缺失状态不会自动补为草稿。");
    if (b) await api("PUT", `/briefs/${b.id}`, payload);
    else await api("POST", "/briefs", payload);
    closeModal(); await renderBriefs(); toast("已保存");
  };
}

/* ================= 引用追踪闭环 ================= */
async function renderCitations() {
  const _operatorViewEpoch = operatorViewEpoch;
  if (!requireProduct()) return;
  const pid = state.current;
  const [monitors, checks, report, briefs] = await Promise.all([
    api("GET", `/products/${pid}/monitors`),
    api("GET", `/products/${pid}/citations`),
    api("GET", `/products/${pid}/citations/report`),
    api("GET", `/products/${pid}/briefs`),
  ]);
  MONITORS = monitors;

  const monitorRows = monitors.map((m) => `
    <tr>
      <td><b>${esc(m.query_text)}</b>
        ${m.source_type === "question" ? `<div class="muted" style="font-size:11px">来自高分问句 #${m.source_id}</div>` : ""}</td>
      <td class="muted">${esc(m.target_engines || "")}</td>
      <td>${freqBadge(m.frequency)}</td>
      <td>${m.last_checked ? esc(m.last_checked) : '<span class="muted">未检查</span>'}</td>
      <td>${resultBadge(m.last_result)} ${m.check_count ? `<span class="muted">· ${m.check_count}次</span>` : ""}</td>
      <td>${statusBadge(m.status)}</td>
      <td class="row-actions">
        <button class="btn btn-sm btn-primary" data-check="${m.id}">记录检查</button>
        <button class="btn btn-sm" data-medit="${m.id}">编辑</button>
        <button class="btn btn-sm btn-icon" data-mdel="${m.id}">${icon("ic-trash", "icon-sm")}</button>
      </td>
    </tr>`).join("");

  const checkRows = checks.map((c) => `
    <tr>
      <td>${esc(c.engine || "—")}</td>
      <td>${esc(c.query_text)}</td>
      <td>${resultBadge(c.result)}</td>
      <td>${c.position ? "#" + c.position : '<span class="muted">—</span>'}</td>
      <td class="muted">${esc(c.check_date || "")}</td>
      <td class="muted">${esc(c.sentiment || "")}</td>
      <td class="row-actions">
        <button class="btn btn-sm" data-cedit="${c.id}">编辑</button>
        <button class="btn btn-sm btn-icon" data-cdel="${c.id}">${icon("ic-trash", "icon-sm")}</button>
      </td>
    </tr>`).join("");

  const byEngine = report.by_engine.map((e) => `
    <div class="trend-card"><div class="tc-label">${esc(e.engine)}</div>
      <div class="tc-num">${Math.round(e.rate * 100)}%</div>
      <div class="muted" style="font-size:11px">被引 ${e.cited}/${e.total}</div></div>`).join("");
  const byCluster = report.by_cluster.map((e) => `
    <div class="trend-card"><div class="tc-label">${esc(e.cluster)}</div>
      <div class="tc-num">${Math.round(e.rate * 100)}%</div>
      <div class="muted" style="font-size:11px">被引 ${e.cited}/${e.total}</div></div>`).join("");
  const mv = report.movement;

  if (typeof _operatorViewEpoch !== "undefined" && _operatorViewEpoch !== operatorViewEpoch) return; $("#view").innerHTML = `
    <div class="panel compact-panel panel-monitor">
      <div class="panel-head"><h2>监测任务（${monitors.length}）</h2>
        <div class="actions">
          <button class="btn btn-primary btn-sm" id="realtime-btn">${icon("ic-bolt", "icon-sm")} 实时查询</button>
          <button class="btn btn-sm" id="baseline-btn">${icon("ic-plus", "icon-sm")} 基线速录</button>
          <button class="btn btn-sm" id="gen-mon">${icon("ic-activity", "icon-sm")} 从高分问句生成</button>
          <button class="btn btn-sm" id="add-mon">${icon("ic-plus", "icon-sm")} 新建监测任务</button>
        </div>
      </div>
      <div class="panel-body" style="padding:0">
        ${monitors.length ? `<table><thead><tr><th>监测查询</th><th>目标引擎</th><th>频率</th><th>最近检查</th><th>最新结果</th><th>状态</th><th></th></tr></thead><tbody>${monitorRows}</tbody></table>`
          : emptyHint("ic-search", "还没有监测任务。点击「从高分问句生成」一键把 P0/P1 问句变成持续监测队列。")}
      </div>
    </div>

    <div class="panel compact-panel panel-checks">
      <div class="panel-head"><h2>引用检查记录（${checks.length}）</h2>
        <span class="muted">每次在 AI 引擎实测后回填</span></div>
      <div class="panel-body" style="padding:0">
        ${checks.length ? `<table><thead><tr><th>引擎</th><th>查询语句</th><th>结果</th><th>位置</th><th>日期</th><th>情绪</th><th></th></tr></thead><tbody>${checkRows}</tbody></table>`
          : emptyHint("ic-search", "还没有检查记录。点击「实时查询」或「基线速录」添加。")}
      </div>
    </div>`;

  $("#gen-mon").onclick = async () => {
    const r = await api("POST", `/products/${pid}/monitors/generate`);
    toast(`已生成 ${r.created} 个监测任务（扫描 ${r.scanned} 个 P0/P1 问句）`);
    await renderCitations();
  };
  $("#add-mon").onclick = () => monitorForm(null);
  $("#baseline-btn").onclick = () => baselineForm(monitors);
  $("#realtime-btn").onclick = () => realtimeQueryForm(monitors);
  $$("[data-check]").forEach((b) => b.onclick = () => {
    const m = monitors.find((x) => x.id == b.dataset.check);
    citationForm(null, briefs, m);
  });
  $$("[data-medit]").forEach((b) => b.onclick = () => monitorForm(monitors.find((m) => m.id == b.dataset.medit)));
  $$("[data-mdel]").forEach((b) => b.onclick = async () => {
    if (!confirm("删除该监测任务及其检查历史？")) return;
    await api("DELETE", `/monitors/${b.dataset.mdel}`);
    await renderCitations(); toast("已删除");
  });
  $$("[data-cedit]").forEach((b) => b.onclick = () => citationForm(checks.find((c) => c.id == b.dataset.cedit), briefs, null));
  $$("[data-cdel]").forEach((b) => b.onclick = async () => {
    if (!confirm("删除该检查记录？")) return;
    await api("DELETE", `/citations/${b.dataset.cdel}`);
    await renderCitations(); toast("已删除");
  });
}

async function renderTrends() {
  const _operatorViewEpoch = operatorViewEpoch;
  if (!requireProduct()) return;
  const pid = state.current;
  const [monitors, report] = await Promise.all([
    api("GET", `/products/${pid}/monitors`),
    api("GET", `/products/${pid}/citations/report`),
  ]);

  /* 被引率格式化：<1% 保留 1 位小数（0.4% 不再被舍入成 0%），其余取整 */
  const fmtPct = (rate) => {
    if (!rate) return "0%";
    const pct = rate * 100;
    return pct < 1 ? (Math.round(pct * 10) / 10) + "%" : Math.round(pct) + "%";
  };
  /* 引擎呈现顺序：Bing AI 置顶（数据源为 BWT 聚合引用量，语义不同于逐问句被引率，故不显示百分比）→ ChatGPT → 其余（暂未持续监测，历史导入数据） */
  const MONITORED_ENGINES = ["Bing AI", "ChatGPT"];
  const bwt = report.bwt || { total: 0, series: [] };
  let bingCard;
  if (bwt.total > 0) {
    const last = bwt.series[bwt.series.length - 1];
    bingCard = '<div class="trend-card"><div class="tc-label">Bing AI</div>' +
      '<div class="tc-num">' + bwt.total.toLocaleString() + '</div>' +
      '<div class="muted" style="font-size:11px">BWT 累计引用（非被引率）· 最近 ' + esc((last.period_start || "").slice(5)) + '~' + esc((last.period_end || "").slice(5)) + ': ' + last.citations + ' 次</div></div>';
  } else {
    bingCard = '<div class="trend-card"><div class="tc-label">Bing AI</div>' +
      '<div class="tc-num">—</div>' +
      '<div class="muted" style="font-size:11px">外部监测（BWT）· 系统内暂无记录</div></div>';
  }
  const engineCards = [bingCard];
  const sortedEngines = [...report.by_engine].sort((a, b) => {
    const ia = MONITORED_ENGINES.indexOf(a.engine), ib = MONITORED_ENGINES.indexOf(b.engine);
    return (ia === -1 ? 99 : ia) - (ib === -1 ? 99 : ib);
  });
  sortedEngines.forEach((e) => {
    const unmonitored = !MONITORED_ENGINES.includes(e.engine);
    engineCards.push(`<div class="trend-card"><div class="tc-label">${esc(e.engine)}${unmonitored ? ' <span class="badge badge-line">暂未监测</span>' : ""}</div>
      <div class="tc-num">${fmtPct(e.rate)}</div>
      <div class="muted" style="font-size:11px">被引 ${e.cited}/${e.total}${unmonitored ? " · 历史导入" : ""}</div></div>`);
  });
  const byCluster = report.by_cluster.map((e) =>
    `<div class="trend-card"><div class="tc-label">${esc(e.cluster)}</div>
      <div class="tc-num">${fmtPct(e.rate)}</div>
      <div class="muted" style="font-size:11px">被引 ${e.cited}/${e.total}</div></div>`).join("");
  const mv = report.movement;

  if (typeof _operatorViewEpoch !== "undefined" && _operatorViewEpoch !== operatorViewEpoch) return; $("#view").innerHTML = `
    <div class="panel">
      <div class="panel-head"><h2>趋势总览</h2>
        <span class="muted">监测任务 ${monitors.length} · 最近一次检查时间：${monitors.length ? (monitors.reduce((a,m)=>a&&m.last_checked?a:m.last_checked,'')||'暂无') : '—'}</span></div>
      <div class="panel-body">
        <div class="trend-cards">
          <div class="trend-card"><div class="tc-label">环比提升</div><div class="tc-num" style="color:var(--c-success)">${mv.improved}</div><div class="muted" style="font-size:11px">监测项上升</div></div>
          <div class="trend-card"><div class="tc-label">环比回落</div><div class="tc-num" style="color:var(--c-danger)">${mv.regressed}</div><div class="muted" style="font-size:11px">监测项下降</div></div>
          <div class="trend-card"><div class="tc-label">持平</div><div class="tc-num">${mv.stable}</div><div class="muted" style="font-size:11px">无变化</div></div>
        </div>
      </div>
    </div>

    <div class="panel">
      <div class="panel-head"><h2>按引擎被引率</h2>
        <span class="muted">传统引用检查统计，与已复核测量分开；平台覆盖以实际记录为准</span></div>
      <div class="panel-body">
        <div class="trend-cards">${engineCards.join("") || '<span class="muted">暂无数据，请先在「引用追踪」记录检查</span>'}</div>
      </div>
    </div>

    <div class="panel">
      <div class="panel-head"><h2>按内容簇被引率</h2>
        <span class="muted">每个问题簇对应的内容被 AI 引用情况</span></div>
      <div class="panel-body">
        <div class="trend-cards">${byCluster || '<span class="muted">暂无（监测任务需关联高分问句所属簇）</span>'}</div>
      </div>
    </div>

    <div class="panel">
      <div class="panel-head"><h2>按月被引率走势</h2>
        <span class="muted">追踪被引率变化趋势</span></div>
      <div class="panel-body">
        ${trendChartSvg(report.over_time)}
      </div>
    </div>`;
}



/* ================= 操作手册 ================= */
/* 单一事实源：docs/新人操作指南.md，由后端 /api/manual 读取，前端零依赖 Markdown 渲染 */
async function renderManual() {
  const _operatorViewEpoch = operatorViewEpoch;
  let m;
  try {
    m = await api("GET", "/manual");
  } catch (e) {
    if (typeof _operatorViewEpoch !== "undefined" && _operatorViewEpoch !== operatorViewEpoch) return; $("#view").innerHTML = '<div class="empty"><p>手册加载失败：' + esc(e.message) + '</p></div>';
    return;
  }
  if (typeof _operatorViewEpoch !== "undefined" && _operatorViewEpoch !== operatorViewEpoch) return; $("#view").innerHTML = '<div class="panel"><div class="panel-head"><h2>操作手册</h2>' +
    '<span class="muted">来源 docs/新人操作指南.md · 更新于 ' + esc(m.updated_at || "—") + '</span></div>' +
    '<div class="panel-body manual-body"><h3>在当前工作区完成日常作业</h3><ol><li>先核对顶部客户、项目与产品/站点，再开始编辑。新资源需由总部开通并明确授权。</li><li>在问句库维护来源、意图、画像和四维评分；未评分保留为空。用搜索与分页查找，不需输入内部编号。</li><li>将问句分配到问题簇，生成模板Brief，修改后采纳为写作中。草稿采纳不会自动发布到网站。</li><li>通过内容缺口、实体和关键词库完善研究；关键词分类先预览再应用。</li><li>在引用追踪维护监测任务、人工回填实际检查；频率配置不代表自动采集已运行。</li><li>在增长证据与交付工作区登记实测、交由另一名获授权人员复核，再做诊断、优化、发布记录和复查。</li><li>外部模型与实时采集尚未开放。提示词库可辅助人工工作，使用外部工具前核对数据发送范围。</li></ol><p>如果遇到权限、数据版本或读取错误，请保留输入并按提示处理；不要换项目重试原记录。</p><details><summary>原系统历史操作手册（方法参考）</summary><p>下文涉及旧系统安装、启动地址、脚本与12视图说明，保留作历史参考；当前门户无需操作人员部署系统、配置密钥或调用旧接口。</p>' + renderMarkdown(m.markdown) + '</details></div></div>';
}

function resultBadge(r) {
  const map = { cited: ["badge-success", "被引"], brand_only: ["badge-info", "仅品牌"], not_found: ["badge-none", "未命中"] };
  const [cls, label] = map[r] || ["badge-line", "—"];
  return `<span class="badge ${cls}">${label}</span>`;
}
const MONITOR_FREQUENCY_LABELS = {weekly:'每周一次（每 7 天）',biweekly:'每两周一次（每 14 天）',monthly:'每月一次（按 30 天计算）'};
function freqBadge(f) {
  return `<span class="badge badge-line">${esc(MONITOR_FREQUENCY_LABELS[f] || f || MONITOR_FREQUENCY_LABELS.weekly)}</span>`;
}
function trendChartSvg(series) {
  if (!series || !series.length)
    return '<p class="muted">暂无趋势数据，去记录几次检查后这里会显示按月被引率走势。</p>';
  const W = 680, H = 160, pad = 28;
  const n = series.length;
  const x = (i) => pad + (W - 2 * pad) * (n === 1 ? 0.5 : i / (n - 1));
  const yv = (r) => H - pad - (H - 2 * pad) * (r || 0);
  const bars = series.map((s, i) => `<rect class="bar" x="${x(i) - 9}" y="${yv(s.rate)}" width="18" height="${H - pad - yv(s.rate)}"></rect>`).join("");
  const pts = series.map((s, i) => `${x(i)},${yv(s.rate)}`).join(" ");
  const dots = series.map((s, i) => `<circle class="dot" cx="${x(i)}" cy="${yv(s.rate)}" r="3.5"></circle><text x="${x(i)}" y="${H - 8}" font-size="9" text-anchor="middle">${esc(s.month)}</text>`).join("");
  return `<svg class="trend-svg" viewBox="0 0 ${W} ${H}" width="100%" preserveAspectRatio="none" style="max-height:180px">
    <line class="axis" x1="${pad}" y1="${H - pad}" x2="${W - pad}" y2="${H - pad}"></line>
    <line class="axis" x1="${pad}" y1="${pad}" x2="${pad}" y2="${H - pad}"></line>
    ${bars}
    <polyline class="line" points="${pts}"></polyline>
    ${dots}
    <text x="${pad}" y="${pad - 8}" font-size="9">被引率 100%</text>
  </svg>`;
}

function monitorForm(m) {
  const isEdit = !!m;
  const body = `
    ${field("监测查询语句", `<textarea class="textarea" id="f-q">${esc(m?.query_text || "")}</textarea>`)}
    ${field("目标引擎（逗号分隔）", `<input class="input" id="f-eng" value="${esc(m?.target_engines || (state.meta.engines||['ChatGPT','Gemini','Copilot','Perplexity']).join(','))}">`)}
    <div class="two-col">
      ${field("监测频率", `<select class="select" id="f-freq">${Object.entries(MONITOR_FREQUENCY_LABELS).map(([value,label])=>`<option value="${value}" ${value===(m?.frequency||'weekly')?'selected':''}>${label}</option>`).join('')}</select><p class="muted">用于安排人工检查和到期提示，不会自动触发采集。</p>`)}
      ${field("状态", `<select class="select" id="f-status">${opt(["active", "paused"], m?.status || "active")}</select>`)}
    </div>
    <div class="two-col">
      ${field("来源类型", `<select class="select" id="f-src"><option value="">手动</option><option value="question" ${m?.source_type === "question" ? "selected" : ""}>高分问句</option><option value="cluster" ${m?.source_type === "cluster" ? "selected" : ""}>问题簇</option><option value="content_gap" ${m?.source_type==='content_gap'?'selected':''}>内容缺口</option></select>`)}
      ${field("关联来源", `<select class="select" id="f-srcid"><option value="">暂不关联</option></select>`)}
    </div><div class="operator-source-picker"><label>搜索来源 <input class="input" id="f-source-search" maxlength="200"></label><button type="button" class="btn btn-sm" id="f-source-find">搜索</button><button type="button" class="btn btn-sm" id="f-source-prev">上一页</button><span id="f-source-page" role="status"></span><button type="button" class="btn btn-sm" id="f-source-next">下一页</button></div>`;
  openModal(isEdit ? "编辑监测任务" : "新建监测任务", body, {
    onOpen:()=>{
      let page=1,epoch=0,pages=1;
      async function load(){
        const generation=++epoch,type=$('#f-src').value,select=$('#f-srcid');
        if(!type){select.innerHTML='<option value="">暂不关联</option>';select.disabled=true;$('#f-source-page').textContent='手动监测，无需输入内部编号';return;}
        select.disabled=true;$('#f-source-page').textContent='正在读取来源…';
        try{
          const collection={question:'questions',cluster:'clusters',content_gap:'content-gaps'}[type];
          const result=await window.OperatorFrame.api('GET','/__paged/'+collection,{page,page_size:20,q:$('#f-source-search').value,ids:m?.source_type===type&&m?.source_id?String(m.source_id):''});
          if(epoch!==generation||!document.getElementById('f-srcid'))return;
          pages=Math.max(1,result.pages);const options=new Map([...result.items,...result.selected_items].map(row=>[row.id,row]));
          select.innerHTML='<option value="">请选择关联来源</option>'+[...options.values()].map(row=>`<option value="${row.id}" ${row.id===m?.source_id&&type===m?.source_type?'selected':''}>${esc(row.text||row.name||row.title||row.slug)}</option>`).join('');select.disabled=false;
          $('#f-source-page').textContent=`第${page}/${pages}页，共${result.total}条`;
          $('#f-source-prev').disabled=page<=1;$('#f-source-next').disabled=page>=pages;
        }catch(error){if(epoch===generation&&document.getElementById('f-source-page'))$('#f-source-page').textContent=error.message;}
      }
      $('#f-src').onchange=()=>{page=1;void load();};$('#f-source-find').onclick=()=>{page=1;void load();};
      $('#f-source-prev').onclick=()=>{page=Math.max(1,page-1);void load();};$('#f-source-next').onclick=()=>{page=Math.min(pages,page+1);void load();};void load();
    },
    onSave: async (close) => {
      const payload = {
        product_id: state.current, query_text: $("#f-q").value.trim(),
        target_engines: $("#f-eng").value.trim(), frequency: $("#f-freq").value,
        status: $("#f-status").value, source_type: $("#f-src").value || null,
        source_id: Number($("#f-srcid").value) || null,
      };
      if (!payload.query_text) return toast("请填写监测查询语句");
      if(payload.source_type&&!payload.source_id)return toast('请选择已授权的关联来源');
      if (isEdit) await api("PUT", `/monitors/${m.id}`, payload);
      else await api("POST", "/monitors", payload);
      close(); await renderCitations(); toast("已保存");
    },
  });
}

function citationForm(c, briefs, mon) {
  const isEdit = !!c;
  const preMon = mon ? mon.id : (c?.monitor_id || "");
  const preQuery = c?.query_text || (mon ? mon.query_text : "");
  const preEngine = c?.engine || (mon ? (mon.target_engines || "").split(",")[0] : "");
  const body = `
    ${field("所属监测任务", `<select class="select" id="f-mon"><option value="">未关联</option>${MONITORS.map((x) => `<option value="${x.id}" ${x.id == preMon ? "selected" : ""}>${esc(x.query_text)}</option>`).join("")}</select>`)}
    ${field("AI 引擎", `<select class="select" id="f-engine">${opt([...new Set([...state.meta.engines,...(c?.engine?[c.engine]:[])])], preEngine)}</select>`)}
    ${field("查询语句", `<textarea class="textarea" id="f-query">${esc(preQuery)}</textarea>`)}
    ${field("查询日期", `<input class="input" id="f-date" type="date" value="${esc(c?.query_date || "")}">`)}
    ${field("结果", `<select class="select" id="f-result">
        <option value="cited" ${c?.result === "cited" ? "selected" : ""}>被引（内容被引用）</option>
        <option value="brand_only" ${c?.result === "brand_only" ? "selected" : ""}>仅提及品牌</option>
        <option value="not_found" ${c?.result === "not_found" ? "selected" : ""}>未命中</option>
        <option value="" ${!c?.result ? "selected" : ""}>未填</option></select>`)}
    <div class="two-col">
      ${field("被引位置", `<input class="input" id="f-pos" type="number" min="1" value="${c?.position || ""}" placeholder="1=置顶">`)}
      ${field("情绪", `<select class="select" id="f-sent"><option value="">未选</option>${opt(["positive", "neutral", "negative"], c?.sentiment)}</select>`)}
    </div>
    ${field("被引内容 URL", `<input class="input" id="f-url" value="${esc(c?.cited_url || "")}">`)}
    ${field("关联 Brief", `<select class="select" id="f-brief"><option value="">未关联</option>${briefs.map((b) => `<option value="${b.id}" ${b.id === c?.brief_id ? "selected" : ""}>${esc(b.title)}</option>`).join("")}</select>`)}
    ${field("备注", `<textarea class="textarea" id="f-notes">${esc(c?.notes || "")}</textarea>`)}
  `;
  openModal(isEdit ? "编辑检查记录" : "记录本次检查", body, {
    onSave: async (close) => {
      const result = $("#f-result").value || null;
      const mentioned = result === "cited" ? 1 : 0;
      const brand_mentioned = (result === "cited" || result === "brand_only") ? 1 : 0;
      const payload = {
        product_id: state.current, monitor_id: Number($("#f-mon").value) || null,
        brief_id: Number($("#f-brief").value) || null, engine: $("#f-engine").value,
        query_text: $("#f-query").value.trim(), query_date: $("#f-date").value || null,
        result, position: Number($("#f-pos").value) || null, cited_url: $("#f-url").value.trim() || null,
        sentiment: $("#f-sent").value || null, mentioned, brand_mentioned,
        notes: $("#f-notes").value.trim() || null,
      };
      if (c) await api("PUT", `/citations/${c.id}`, payload);
      else await api("POST", "/citations", payload);
      close(); await renderCitations(); toast("已保存");
    },
  });
}

/* ---- 实时查询：调用 ChatGPT Search API ---- */
function realtimeQueryForm(allMonitors) {
  const queries = allMonitors.map((m) => m.query_text).filter(Boolean);
  if (!queries.length) {
    toast("请先创建监测任务", "warning");
    return;
  }

  const body = `
    <div class="info-box">
      将对以下 ${queries.length} 个查询执行实时 ChatGPT Search API 查询。<br>
      预计耗时：${Math.ceil(queries.length * 1.5)} 秒（每查询 1.5 秒延迟）。
    </div>
    <div class="query-list" style="max-height:200px;overflow:auto;margin:12px 0">
      ${queries.map((q, i) => `<div class="query-item">${i + 1}. ${esc(q)}</div>`).join("")}
    </div>
  `;
  openModal("实时查询 ChatGPT", body, {
    confirmText: "开始查询",
    onConfirm: async (close) => {
      close();
      const spinner = toast(`正在查询 ${queries.length} 个监测任务...`, "info", 60000);
      let success = 0, failed = 0;

      for (let i = 0; i < queries.length; i++) {
        const q = queries[i];
        const m = allMonitors.find((x) => x.query_text === q);

        try {
          const r = await api("POST", `/products/${state.current}/citations/realtime`, {
            query_text: q,
            monitor_id: m?.id || null,
            engine: "ChatGPT",
          });
          success++;
          console.log(`✅ ${q}: ${r.result}`);
        } catch (e) {
          failed++;
          console.error(`❌ ${q}: ${e.message}`);
        }

        // 延迟避免 rate limit
        if (i < queries.length - 1) {
          await new Promise((resolve) => setTimeout(resolve, 1500));
        }
      }

      toast(`查询完成：成功 ${success}，失败 ${failed}`, success > 0 ? "success" : "warning");
      await renderCitations();
    },
  });
}

/* ---- 基线速录：批量引用检查 ---- */
function baselineForm(allMonitors) {
  const ENGINES = (state.meta.engines && state.meta.engines.length) ? state.meta.engines : ["ChatGPT", "Gemini", "Perplexity", "Copilot"];
  // 优先级：content_gap > geo_audit > reddit > manual > gsc
  const priority = { content_gap: 0, geo_audit: 1, reddit: 2, manual: 3, gsc: 4 };
  const top = [...allMonitors].sort((a, b) =>
    (priority[a.source_type] ?? 9) - (priority[b.source_type] ?? 9)
  ).slice(0, 24);

  const today = new Date().toISOString().slice(0, 10);
  const resultOpts = (val) => `
    <option value="" ${!val ? "selected" : ""}>—</option>
    <option value="cited" ${val === "cited" ? "selected" : ""}>被引</option>
    <option value="brand_only" ${val === "brand_only" ? "selected" : ""}>仅品牌</option>
    <option value="not_found" ${val === "not_found" ? "selected" : ""}>未命中</option>`;

  const rows = top.map((m, i) => `
    <tr>
      <td style="max-width:260px"><b>${esc(m.query_text.slice(0, 70))}</b><br><span class="muted" style="font-size:10px">${esc(m.source_type || "")} · #${m.id}</span></td>
      ${ENGINES.map((eng) => `
        <td style="text-align:center">
          <select class="select bl-sel" data-mid="${m.id}" data-eng="${eng}" data-q="${esc(m.query_text)}" style="width:90px;font-size:11px;padding:2px 4px">${resultOpts("")}</select>
          <input class="input bl-pos" data-mid="${m.id}" data-eng="${eng}" type="number" min="1" placeholder="位" style="width:36px;font-size:11px;padding:2px;display:none;margin-top:2px">
        </td>`).join("")}
    </tr>`).join("");

  const body = `
    <div style="padding:12px 20px;border-bottom:1px solid var(--c-border);display:flex;gap:16px;align-items:center;flex-wrap:wrap">
      <label class="field" style="flex:0 0 auto"><span>检查日期</span><input class="input" id="bl-date" type="date" value="${today}" style="width:140px"></label>
      <span class="muted" style="font-size:12px">操作：逐行打开 ${esc(ENGINES.join('/'))}，输入问句，核对当前产品网站是否被引用，在下拉选结果。被引时填位置（1=置顶）。</span>
      <span class="badge badge-info" id="bl-count" style="margin-left:auto">已填 0 条</span>
    </div>
    <div style="flex:1;overflow:auto;padding:0 20px">
      <table style="width:100%;font-size:12px">
        <thead><tr><th style="text-align:left;padding:8px 4px">监测问句</th>
          ${ENGINES.map((e) => `<th style="text-align:center;padding:8px 4px">${esc(e)}</th>`).join("")}
        </tr></thead>
        <tbody>${rows}</tbody>
      </table>
    </div>`;

  openModal("基线速录 — 批量引用检查", body, { fullscreen: true, saveText: "保存基线" });

  // show/hide position input based on result selection
  const updateCount = () => {
    const filled = $$(".bl-sel").filter((s) => s.value).length;
    $("#bl-count").textContent = `已填 ${filled} 条`;
  };
  $$(".bl-sel").forEach((sel) => {
    sel.onchange = () => {
      const pos = $(`.bl-pos[data-mid="${sel.dataset.mid}"][data-eng="${sel.dataset.eng}"]`);
      if (pos) pos.style.display = (sel.value === "cited") ? "block" : "none";
      updateCount();
    };
  });

  // save
  $("#ms").onclick = async () => {
    const date = $("#bl-date").value || today;
    const items = [];
    $$(".bl-sel").forEach((sel) => {
      if (!sel.value) return;
      const posEl = $(`.bl-pos[data-mid="${sel.dataset.mid}"][data-eng="${sel.dataset.eng}"]`);
      items.push({
        monitor_id: Number(sel.dataset.mid) || null,
        engine: sel.dataset.eng,
        query_text: sel.dataset.q,
        result: sel.value,
        position: posEl && posEl.value ? Number(posEl.value) : null,
      });
    });
    if (!items.length) return toast("请至少填写一条检查结果");
    const r = await api("POST", `/products/${state.current}/citations/batch`, { product_id: state.current, query_date: date, items });
    toast(`✅ 基线已保存：${r.created} 条记录，覆盖 ${r.monitors_checked} 个监测`);
    closeModal();
    await renderCitations();
  };
}

/* ================= 实体库 ================= */
async function renderEntities() {
  const _operatorViewEpoch = operatorViewEpoch;
  if (!requireProduct()) return;
  const list = await api("GET", `/products/${state.current}/entities`);
  if (typeof _operatorViewEpoch !== "undefined" && _operatorViewEpoch !== operatorViewEpoch) return; $("#view").innerHTML = panelWithAdd("实体库", "新建实体", "entity",
    list.length ? `<table><thead><tr><th>名称</th><th>类型</th><th>说明</th><th></th></tr></thead><tbody>
      ${list.map((x) => `<tr><td><b>${esc(x.name)}</b></td><td><span class="chip">${esc(x.type || "")}</span></td>
        <td class="muted">${esc(x.description || "")}</td>
        <td class="row-actions"><button class="btn btn-sm" data-edit="${x.id}">编辑</button>
        <button class="btn btn-sm btn-icon" data-del="${x.id}">${icon("ic-trash", "icon-sm")}</button></td></tr>`).join("")}
    </tbody></table>` : emptyHint("ic-tag", "还没有实体。把品牌、产品、人物、功能沉淀进实体库，供 Brief 植入。"));
  wireCrud(list, "entity", "/entities", (x) => x.id, entityForm);
}
function entityForm(x) {
  const body = `
    ${field("实体名称", `<input class="input" id="f-name" value="${esc(x?.name || "")}">`)}
    ${field("类型", `<select class="select" id="f-type">${opt(state.meta.entity_types, x?.type)}</select>`)}
    ${field("说明", `<textarea class="textarea" id="f-desc">${esc(x?.description || "")}</textarea>`)}
  `;
  openModal(x ? "编辑实体" : "新建实体", body, {
    onSave: async (close) => {
      const payload = { product_id: state.current, name: $("#f-name").value.trim(),
        type: $("#f-type").value, description: $("#f-desc").value.trim() };
      if (!payload.name) return toast("请填写名称");
      if (x) await api("PUT", `/entities/${x.id}`, payload);
      else await api("POST", "/entities", payload);
      close(); await renderEntities(); toast("已保存");
    },
  });
}

/* ================= 内容缺口 ================= */
function gapStatusBadge(s) {
  const map = { planned: "badge-low", published: "badge-success", deprecated: "badge-none" };
  return `<span class="badge ${map[s] || "badge-line"}">${esc(s || "planned")}</span>`;
}

async function renderContentGaps() {
  const _operatorViewEpoch = operatorViewEpoch;
  if (!requireProduct()) return;
  const list = await api("GET", `/products/${state.current}/content-gaps`);
  if (typeof _operatorViewEpoch !== "undefined" && _operatorViewEpoch !== operatorViewEpoch) return; $("#view").innerHTML = `
    <div class="panel">
      <div class="panel-head"><h2>内容缺口（${list.length}）</h2>
        <div class="actions">
          <button class="btn btn-sm" id="gen-mon">${icon("ic-activity", "icon-sm")} 生成监测任务</button>
          <button class="btn btn-sm" id="seed-mon">${icon("ic-search", "icon-sm")} 全问句播种监测</button>
          <button class="btn btn-primary btn-sm" id="add-gap">${icon("ic-plus", "icon-sm")} 新增缺口</button>
        </div></div>
      <div class="panel-body" style="padding:0">
        ${list.length ? `<table><thead><tr><th style="width:22%">Slug</th><th>标题</th><th>意图</th><th>状态</th><th>已上线 URL</th><th></th></tr></thead><tbody>
          ${list.map((g) => `<tr>
            <td><code>${esc(g.slug)}</code></td>
            <td>${esc(g.title || "—")}</td>
            <td>${g.intent_class ? `<span class="chip">${esc(g.intent_class)}</span>` : "—"}</td>
            <td>${gapStatusBadge(g.status)}</td>
            <td class="muted" style="font-size:12px">${g.published_url ? `<a href="${esc(g.published_url)}" target="_blank" rel="noopener">${esc(g.published_url)}</a>` : "—"}</td>
            <td class="row-actions">
              <button class="btn btn-sm" data-edit="${g.id}">编辑</button>
              <button class="btn btn-sm btn-icon" data-del="${g.id}">${icon("ic-trash", "icon-sm")}</button>
            </td></tr>`).join("")}
        </tbody></table>` : `<div class="empty" style="padding:30px">${icon("ic-target")}<p>还没有内容缺口。把「404 高意图页」「待补内容」登记进来，一键生成监测任务追踪 AI 引用。</p></div>`}
      </div>
    </div>`;
  $("#add-gap").onclick = () => contentGapForm(null);
  $$("[data-edit]").forEach((b) => b.onclick = () => contentGapForm(list.find((g) => g.id == b.dataset.edit)));
  $$("[data-del]").forEach((b) => b.onclick = async () => {
    if (!confirm("删除该内容缺口？")) return;
    await api("DELETE", `/content-gaps/${b.dataset.del}`); await renderContentGaps(); toast("已删除");
  });
  $("#gen-mon").onclick = async () => {
    const r = await api("POST", `/products/${state.current}/monitors/generate`);
    toast(`已生成 ${r.created} 个监测任务（问句 ${r.scanned_questions} + 缺口 ${r.scanned_gaps}）`);
  };
  $("#seed-mon").onclick = async () => {
    const qs = await api("GET", `/products/${state.current}/questions`);
    const items = qs.map((q) => ({ query_text: q.text }));
    const r = await api("POST", `/products/${state.current}/monitors/seed`, { items });
    toast(`已播种 ${r.created} 个监测任务`);
  };
}

function contentGapForm(g) {
  const v = (k) => (g ? g[k] : "");
  const body = `
    ${field("Slug（页面标识，唯一）", `<input class="input" id="f-slug" value="${esc(v("slug"))}" placeholder="如：best-ebook-converter">`)}
    ${field("标题", `<input class="input" id="f-title" value="${esc(v("title"))}" placeholder="如：Best Ebook Converter 2026">`)}
    <div class="two-col">
      ${field("意图分类", `<select class="select" id="f-intent"><option value="">未分类</option>${opt(currentIntentClasses(), v("intent_class"))}</select>`)}
      ${field("状态", `<select class="select" id="f-status">${opt(["planned", "published", "deprecated"], v("status") || "planned")}</select>`)}
    </div>
    ${field("已上线 URL", `<input class="input" id="f-url" value="${esc(v("published_url"))}" placeholder="发布后填写，用于核对 AI 引用指向">`)}
    ${field("备注", `<textarea class="textarea" id="f-notes">${esc(v("notes"))}</textarea>`)}
  `;
  openModal(g ? "编辑内容缺口" : "新增内容缺口", body, {
    onSave: async (close) => {
      const payload = {
        product_id: state.current,
        slug: $("#f-slug").value.trim(),
        title: $("#f-title").value.trim() || null,
        intent_class: $("#f-intent").value || null,
        status: $("#f-status").value,
        published_url: $("#f-url").value.trim() || null,
        notes: $("#f-notes").value.trim() || null,
      };
      if (!payload.slug) return toast("请填写 Slug");
      if (g) await api("PUT", `/content-gaps/${g.id}`, payload);
      else await api("POST", "/content-gaps", payload);
      close(); await renderContentGaps(); toast("已保存");
    },
  });
}

/* ================= 提示词库 ================= */
async function renderPrompts() {
  const _operatorViewEpoch = operatorViewEpoch;
  const list = await api("GET", "/prompts");
  const grouped = {};
  list.forEach((p) => { (grouped[p.step] = grouped[p.step] || []).push(p); });
  if (typeof _operatorViewEpoch !== "undefined" && _operatorViewEpoch !== operatorViewEpoch) return; $("#view").innerHTML = `
    <div class="panel">
      <div class="panel-head"><h2>提示词库（${list.length}）</h2>
        <span class="muted">复制到 ChatGPT / Gemini 使用，结果回填系统</span></div>
      <div class="panel-body">
        ${Object.entries(grouped).map(([step, items]) => `
          <h3 style="margin:18px 0 10px;font-size:14px">${esc(step)}</h3>
          ${items.map((p) => `<div class="prompt-card" style="margin-bottom:12px">
            <div style="display:flex;justify-content:space-between;align-items:center">
              <b>${esc(p.name)}</b>
              <button class="btn btn-sm" data-copy="${p.id}">${icon("ic-terminal", "icon-sm")} 复制</button>
            </div>
            <pre>${esc(p.content)}</pre>
          </div>`).join("")}
        `).join("")}
      </div>
    </div>`;
  $$("[data-copy]").forEach((b) => b.onclick = async () => {
    const p = list.find((x) => x.id == b.dataset.copy);
    try { await window.OperatorFrame.copy(p.content); toast("已复制到剪贴板"); }
    catch (e) { toast("复制失败，请手动选择"); }
  });
}

/* ================= AI 辅助生产（草稿 + 人工审批） ================= */
function fullQuestionPayload(q, ov = {}) {
  return {
    product_id: state.current,
    text: ov.text ?? q.text,
    source: ov.source ?? q.source ?? "manual",
    persona_id: ov.persona_id ?? q.persona_id ?? null,
    scenario_id: ov.scenario_id ?? q.scenario_id ?? null,
    intent_class: ov.intent_class ?? q.intent_class ?? null,
    sentiment: ov.sentiment ?? q.sentiment ?? null,
    ai_answerable: ov.ai_answerable ?? q.ai_answerable ?? null,
    stage: ov.stage ?? q.stage ?? null,
    commercial: ov.commercial ?? q.commercial ?? null,
    citation: ov.citation ?? q.citation ?? null,
    brand: ov.brand ?? q.brand ?? null,
    competition: ov.competition ?? q.competition ?? null,
    notes: ov.notes ?? q.notes ?? null,
  };
}

async function aiScoreOne(q) {
  if (!q) return;
  let draft;
  try { draft = await api("POST", `/products/${state.current}/questions/${q.id}/ai-score`); }
  catch (e) { return toast("AI 评分失败：" + e.message); }
  const chips = [
    ["商业价值", draft.commercial], ["引用潜力", draft.citation],
    ["品牌机会", draft.brand], ["竞争难度", draft.competition],
  ].map(([k, v]) => `<div class="score-chip"><b>${v}</b><span>${k}</span></div>`).join("");
  const body = `
    <p class="muted">问句：${esc(q.text)}</p>
    <div class="score-chips">${chips}</div>
    <p>实时总分 <b>${draft.total}</b> ${prioBadge(draft.priority)}</p>
    <div class="ai-rationale">${esc(draft.rationale || "（无说明）")}</div>`;
  openModal("AI 评分草稿 · 人工审批", body, {
    saveText: "采纳并写入",
    onSave: async (close) => {
      await api("PUT", `/questions/${q.id}`, fullQuestionPayload(q, {
        commercial: draft.commercial, citation: draft.citation,
        brand: draft.brand, competition: draft.competition,
      }));
      close(); await renderQuestions(); toast("已写入评分");
    },
  });
}

async function aiScoreBatch() {
  const list = await api("GET", `/products/${state.current}/questions`);
  const unrated = list.filter((q) => q.total === null || q.priority === "未评分");
  if (!unrated.length) return toast("没有未评分的问句");
  if (!confirm(`AI 将为 ${unrated.length} 条未评分问句生成草稿，逐条确认后写入？`)) return;
  const drafts = [];
  for (const q of unrated) {
    try { drafts.push({ q, draft: await api("POST", `/products/${state.current}/questions/${q.id}/ai-score`) }); }
    catch (e) { toast("问句 #" + q.id + " 评分失败：" + e.message); }
  }
  if (!drafts.length) return;
  const body = drafts.map(({ q, draft }, i) => `
    <div class="draft-item">
      <div class="di-head">
        <label><input type="checkbox" class="adopt" value="${i}" checked> <b>${esc(q.text)}</b></label>
        ${prioBadge(draft.priority)}
      </div>
      <div class="score-chips">
        <div class="score-chip"><b>${draft.commercial}</b><span>商业</span></div>
        <div class="score-chip"><b>${draft.citation}</b><span>引用</span></div>
        <div class="score-chip"><b>${draft.brand}</b><span>品牌</span></div>
        <div class="score-chip"><b>${draft.competition}</b><span>竞争</span></div>
      </div>
      <div class="draft-q">总分 ${draft.total} · ${esc(draft.rationale || "")}</div>
    </div>`).join("");
  openModal(`AI 批量评分草稿（${drafts.length}）`, body, {
    saveText: "采纳选中项并写入",
    onSave: async (close) => {
      const chosen = $$(".adopt").filter((c) => c.checked).map((c) => drafts[Number(c.value)]);
      for (const { q, draft } of chosen) {
        await api("PUT", `/questions/${q.id}`, fullQuestionPayload(q, {
          commercial: draft.commercial, citation: draft.citation,
          brand: draft.brand, competition: draft.competition,
        }));
      }
      close(); await renderQuestions(); toast(`已写入 ${chosen.length} 条评分`);
    },
  });
}

async function aiCluster() {
  let draft;
  try { draft = await api("POST", `/products/${state.current}/ai-cluster`); }
  catch (e) { return toast("AI 聚类失败：" + e.message); }
  const clusters = draft.clusters || [];
  if (!clusters.length) return toast("没有未归类的问句，无需聚类");
  const body = clusters.map((c, i) => `
    <div class="draft-item">
      <div class="di-head">
        <label><input type="checkbox" class="cadopt" value="${i}" checked> <b>${esc(c.name)}</b>
          <span class="muted">（${c.question_ids.length} 问句）</span></label>
      </div>
      <div class="draft-q">${c.questions.map((q) => esc(q.text)).join("；") || "（无）"}</div>
    </div>`).join("");
  openModal(`AI 聚类草稿（${clusters.length} 簇）`, body, {
    saveText: "采纳并创建",
    onSave: async (close) => {
      const chosen = $$(".cadopt").filter((c) => c.checked).map((c) => clusters[Number(c.value)]);
      const payload = { clusters: chosen.map((c) => ({
        name: c.name, parent_topic: c.parent_topic || "", description: c.goal || "",
        question_ids: c.question_ids,
      })) };
      await api("POST", `/products/${state.current}/ai-cluster/apply`, payload);
      close(); await renderClusters(); toast(`已创建 ${chosen.length} 个问题簇`);
    },
  });
}

async function aiBrief(cid, clusterName) {
  let draft;
  try { draft = await api("POST", `/products/${state.current}/clusters/${cid}/ai-brief`); }
  catch (e) { return toast("AI 生成 Brief 失败：" + e.message); }
  const body = `
    <p class="muted">簇：${esc(clusterName)}</p>
    <div class="brief-preview"># ${esc(draft.main_question || "")}
## 核心结论
${esc(draft.core_conclusion || "")}
## 内容结构
${(draft.structure || []).map((s, i) => `${i + 1}. ${esc(s)}`).join("\n")}
## FAQ
${(draft.faqs || []).map((f) => "- " + esc(f)).join("\n")}
## 证据 / 素材
${(draft.evidence || []).map((e) => "- " + esc(e)).join("\n")}
## CTA
${esc(draft.cta || "")}</div>`;
  openModal("AI Brief 草稿 · 人工审批", body, {
    saveText: "采纳并创建 Brief",
    onSave: async (close) => {
      const md = `# ${draft.main_question || clusterName}\n## 核心结论\n${draft.core_conclusion || ""}\n` +
        `## 内容结构\n${(draft.structure || []).map((s, i) => `${i + 1}. ${s}`).join("\n")}\n` +
        `## FAQ\n${(draft.faqs || []).map((f) => "- " + f).join("\n")}\n` +
        `## 证据 / 素材\n${(draft.evidence || []).map((e) => "- " + e).join("\n")}\n## CTA\n${draft.cta || ""}`;
      await api("POST", "/briefs", {
        product_id: state.current, cluster_id: cid, title: draft.main_question || clusterName,
        content_type: draft.content_format || "article", status: "idea", body: md,
      });
      close(); await renderBriefs(); toast("Brief 已生成");
    },
  });
}

/* ---------------- 复用组件 ---------------- */
function panelWithAdd(title, addLabel, _key, inner) {
  return `<div class="panel"><div class="panel-head"><h2>${esc(title)}</h2>
    <button class="btn btn-primary btn-sm" id="add-${_key}">${icon("ic-plus", "icon-sm")} ${esc(addLabel)}</button></div>
    <div class="panel-body" style="padding:0">${inner}</div></div>`;
}
function emptyHint(ic, msg) {
  return `<div class="empty" style="padding:30px">${icon(ic)}<p>${esc(msg)}</p></div>`;
}
function wireCrud(list, key, _base, idOf, formFn) {
  $("#add-" + key).onclick = () => formFn(null);
  $$("[data-edit]").forEach((b) => b.onclick = () => formFn(list.find((x) => idOf(x) == b.dataset.edit)));
  $$("[data-del]").forEach((b) => b.onclick = async () => {
    if (!confirm("删除该条目？")) return;
    await api("DELETE", `${_base}/${b.dataset.del}`);
    await render(); toast("已删除");
  });
}

/* ---------------- 启动 ---------------- */
window.OperatorFrame.ready.then(() => init()).catch((e) => {
  if (typeof _operatorViewEpoch !== "undefined" && _operatorViewEpoch !== operatorViewEpoch) return; $("#view").innerHTML = `<div class="empty"><p>加载失败：${esc(e.message)}</p>
    <p class="muted">请返回项目检查授权或重试；专业工作台不会直连未授权的原系统接口。</p></div>`;
});

/* ================= 关键词库 ================= */
let KEYWORDS = [];
let KEYWORD_STATS = null;

async function renderKeywords() {
  const _operatorViewEpoch = operatorViewEpoch;
  try {
    KEYWORDS = await api("GET", `/products/${state.current}/keywords`);
    KEYWORD_STATS = await api("GET", `/products/${state.current}/keywords/statistics`);
  } catch (e) {
    if (typeof _operatorViewEpoch !== "undefined" && _operatorViewEpoch !== operatorViewEpoch) return; return $("#view").innerHTML = `<div class="empty"><p>加载失败：${esc(e.message)}</p></div>`;
  }

  const totalKeywords = KEYWORD_STATS?.total_keywords || 0;
  const totalHits = KEYWORD_STATS?.total_hits || 0;
  const noIntent = KEYWORD_STATS?.unclassified ?? null;

  // 统计卡片
  const statsHtml = `
    <div class="stats-row">
      ${statCard("总关键词数", totalKeywords)}
      ${statCard("总命中次数", totalHits)}
      ${statCard("有分类", noIntent===null?'待核对':totalKeywords-noIntent)}
      ${statCard("待分类", noIntent===null?'待核对':noIntent)}
    </div>
  `;

  // 分类统计
  const byTypeHtml = Object.entries(KEYWORD_STATS?.by_type || {}).map(([type, count]) =>
    `<div class="stat-item"><span class="muted">${type}</span><b>${count}</b></div>`
  ).join('');

  const byPriorityHtml = Object.entries(KEYWORD_STATS?.by_priority || {}).map(([pri, count]) =>
    `<div class="stat-item"><span class="muted">${pri}</span><b>${count}</b></div>`
  ).join('');

  // 顶部命中标题列表
  const topHitsHtml = (KEYWORD_STATS?.top_hit_keywords || []).map(kw => `
    <div class="keyword-row" style="padding:8px 0;border-bottom:1px solid var(--border)">
      <span class="kw-name">${esc(kw.name)}</span>
      <span class="muted">${esc(kw.type)}</span>
      <span class="badge badge-p${kw.priority?.replace('P', '') || '2'}">${esc(kw.priority || 'P2')}</span>
      <span class="hit-count">${kw.usage_count} 次命中</span>
    </div>
  `).join('') || '<p class="muted">暂无命中记录</p>';

  // 关键词表格
  const keywordsHtml = KEYWORDS.map(kw => `
    <tr data-kid="${kw.id}">
      <td><b>${esc(kw.name)}</b></td>
      <td><code>${esc(String(kw.pattern||'').substring(0, 50))}${String(kw.pattern||'').length > 50 ? '...' : ''}</code></td>
      <td><span class="badge badge-line">${esc(kw.type)}</span></td>
      <td>${kw.intent_class ? `<span class="badge badge-p1">${esc(kw.intent_class)}</span>` : '<span class="muted">—</span>'}</td>
      <td>${prioBadge(kw.priority)}</td>
      <td>${kw.usage_count || 0}</td>
      <td>
        <button class="btn btn-sm" data-edit-kw="${kw.id}">${icon("ic-edit", "icon-sm")}</button>
        <button class="btn btn-sm btn-danger" data-del-kw="${kw.id}">${icon("ic-delete", "icon-sm")}</button>
      </td>
    </tr>
  `).join('') || '<tr><td colspan="7" class="empty-cell">暂无关键词，点击"新建关键词"开始</td></tr>';

  if (typeof _operatorViewEpoch !== "undefined" && _operatorViewEpoch !== operatorViewEpoch) return; $("#view").innerHTML = `
    <div class="panel">
      <div class="panel-head">
        <h2>关键词库</h2>
        <div style="display:flex;gap:8px">
          <button class="btn" id="btn-batch-classify">${icon("ic-refresh", "icon-sm")} 批量分类问句</button>
          <button class="btn btn-primary" id="btn-add-kw">${icon("ic-plus", "icon-sm")} 新建关键词</button>
        </div>
      </div>
      <div class="panel-body">
        ${statsHtml}
      </div>
    </div>

    <div class="two-col" style="margin-top:12px">
      <div class="panel">
        <div class="panel-head"><h2>分类统计</h2></div>
        <div class="panel-body">
          <div class="kv">
            <dt>按类型</dt><dd>${byTypeHtml}</dd>
            <dt>按优先级</dt><dd>${byPriorityHtml}</dd>
          </div>
        </div>
      </div>
      <div class="panel">
        <div class="panel-head"><h2>热门关键词</h2></div>
        <div class="panel-body" style="padding:0">
          ${topHitsHtml}
        </div>
      </div>
    </div>

    <div class="panel" style="margin-top:12px">
      <div class="panel-head"><h2>关键词列表</h2></div>
      <div class="panel-body" style="padding:0;overflow-x:auto">
        <table class="data-table">
          <thead>
            <tr>
              <th>名称</th><th>匹配模式</th><th>类型</th><th>意图分类</th><th>优先级</th><th>命中数</th><th>操作</th>
            </tr>
          </thead>
          <tbody id="kw-table-body">
            ${keywordsHtml}
          </tbody>
        </table>
      </div>
    </div>
  `;

  // 绑定事件
  $("#btn-add-kw").onclick = () => openKeywordForm(null);
  $$("[data-edit-kw]").forEach(btn => btn.onclick = () => openKeywordForm(KEYWORDS.find(k => k.id == btn.dataset.editKw)));
  $$("[data-del-kw]").forEach(btn => btn.onclick = async () => {
    if (!confirm("删除该关键词？关联的命中记录也会被删除。")) return;
    await api("DELETE", `/products/${state.current}/keywords/${btn.dataset.delKw}`);
    await renderKeywords();
    toast("已删除");
  });
  $("#btn-batch-classify").onclick = batchClassifyByKeywords;
}

function openKeywordForm(kw) {
  const isEdit = !!kw;
  const body = `
    <div class="form-grid">
      ${field("关键词名称", `<input id="kw-name" value="${esc(kw?.name || '')}" placeholder="如：推荐类">`)}
      ${field("匹配模式", `<input id="kw-pattern" value="${esc(kw?.pattern || '')}" placeholder="如：best|recommend|top">`)}
      ${field("类型", `
        <select id="kw-type">
          ${['keyword', 'phrase', 'intent', 'entity'].map(t =>
            `<option ${t === (kw?.type || 'keyword')} value="${t}">${t}</option>`
          ).join('')}
        </select>
      `)}
      ${field("意图分类", `
        <select id="kw-intent">
          <option value="">（不分类）</option>
          ${state.meta.intent_classes.map(ic =>
            `<option ${ic === (kw?.intent_class || '')} value="${ic}">${ic}</option>`
          ).join('')}
        </select>
      `)}
      ${field("优先级", `
        <select id="kw-priority">
          ${['P0', 'P1', 'P2', '暂缓'].map(p =>
            `<option ${p === (kw?.priority || 'P2')} value="${p}">${p}</option>`
          ).join('')}
        </select>
      `)}
      ${field("备注", `<input id="kw-notes" value="${esc(kw?.notes || '')}" placeholder="可选说明">`)}
    </div>
  `;
  openModal(isEdit ? "编辑关键词" : "新建关键词", body, {
    saveText: "保存",
    onSave: async (close) => {
      const payload = {
        name: $("#kw-name").value.trim(),
        pattern: $("#kw-pattern").value.trim(),
        type: $("#kw-type").value,
        intent_class: $("#kw-intent").value || null,
        priority: $("#kw-priority").value,
        notes: $("#kw-notes").value.trim() || null,
      };
      if (!payload.name || !payload.pattern) return toast("名称和匹配模式必填");
      try {
        if (isEdit) {
          await api("PUT", `/products/${state.current}/keywords/${kw.id}`, payload);
        } else {
          await api("POST", `/products/${state.current}/keywords`, payload);
        }
        close();
        await renderKeywords();
        toast("已保存");
      } catch (e) {
        toast("保存失败：" + e.message);
      }
    },
  });
}

async function batchClassifyByKeywords() {
  if (!confirm("将使用关键词库对无分类问句进行批量意图分类，生成草稿后需人工确认。是否继续？")) return;

  let draft;
  try {
    draft = await api("POST", `/products/${state.current}/questions/classify-by-keywords`);
  } catch (e) {
    return toast("分类失败：" + e.message);
  }

  if (draft.error) return toast(draft.error);
  if (!draft.drafts?.length) return toast("没有可分类的问句，或关键词库暂无有效分类规则");

  // 显示草稿列表
  const body = `
    <p class="muted">共 ${draft.total} 条待分类问句，其中 ${draft.classified} 条可分类</p>
    <div class="draft-list" style="max-height:400px;overflow-y:auto;margin-top:12px">
      ${draft.drafts.slice(0, 50).map((d, i) => `
        <div class="draft-item">
          <div class="di-head">
            <label><input type="checkbox" class="cls-adopt" value="${i}" checked> QID=${d.question_id}</label>
            <span class="badge badge-p1">${esc(d.proposed_intent)}</span>
            <span class="muted">置信度: ${(d.confidence * 100).toFixed(0)}%</span>
          </div>
          <div class="draft-q">${esc(d.matched_keywords.join(' | '))}</div>
        </div>
      `).join('')}
      ${draft.drafts.length > 50 ? `<p class="muted">... 还有 ${draft.drafts.length - 50} 条，请分批应用</p>` : ''}
    </div>
  `;

  openModal(`批量分类草稿（${draft.classified} 条）`, body, {
    saveText: "应用选中分类",
    onSave: async (close) => {
      const chosen = $$(".cls-adopt").filter(c => c.checked).map(c => draft.drafts[Number(c.value)]);
      if (!chosen.length) return toast("请至少选择一条分类草稿");
      try {
        await api("POST", `/products/${state.current}/questions/classify-by-keywords/apply`, { drafts: chosen });
        close();
        toast(`已应用 ${chosen.length} 条分类`);
        await render();
      } catch (e) {
        toast("应用失败：" + e.message);
      }
    },
  });
}


/* ================= SEO Growth（增长层，V1.0） ================= */
/* 数据来源：/api/sites/{sid}/growth-workbench、/api/sites/{sid}/seo/keywords、
   /api/sites/{sid}/competitor-gaps。site 由当前产品的 source_product_id 解析。 */
let SEO_SITE = null;

function trendBadge(t, delta) {
  if (t === "insufficient_data") return '<span class="badge badge-line">数据不足</span>';
  if (t === "single_point") return '<span class="badge badge-line">单点观测</span>';
  if (t === "not_comparable") return '<span class="badge badge-line">不可比</span>';
  if (t === "newly_observed") return '<span class="badge badge-p1">新进榜</span>';
  if (t === "disappeared") return '<span class="badge badge-p0">掉出榜</span>';
  if (t === "improved") return '<span class="badge badge-p0">↑ 提升</span>';
  if (t === "declined") return '<span class="badge badge-p1">↓ 下滑</span>';
  return '<span class="badge badge-p2">持平</span>';
}

const SEV_BADGE = { critical: "badge-p0", high: "badge-p1", medium: "badge-p2", low: "badge-low" };
const SEV_LABEL = { critical: "严重", high: "高", medium: "中", low: "低", info: "提示" };

/* 诊断类型释义：每类的中文名 / 含义 / 严重度由来 / 建议处理。
   严重度判定阈值来源：seo_growth_service.py（RANKING_DROP_THRESHOLD=5、
   STAGNATION_MIN_SPAN_DAYS=7、COMPETITOR_TOP=3、OUR_POOR_RANK=10、RANK_GAP_THRESHOLD=5） */
const DIAG_TYPE_INFO = {
  CITATION_GAP: {
    name: "引用缺口",
    meaning: "AI 已经能回答这个问题，但答案里没有引用你的内容。",
    severityWhy: "高价值问句在 AI 实测中未被引用，属增长缺口，测量流程创建时自动标记。",
    fix: "提升目标页的可引用性：页面开头给出可直接引用的结论段、补充数据与事实、保持品牌实体（名称/官网/简介）在各渠道一致。",
  },
  RANKING_DROP: {
    name: "排名下滑",
    meaning: "关键词排名与上一次可比观测相比明显下滑。",
    severityWhy: "自动规则：两次可比观测间排名下滑 ≥5 位即判为「高」。",
    fix: "排查近期页面改动与竞品动态；刷新目标页内容（更新时间/内容深度/内链），夺回排名。",
  },
  RANKING_STAGNATION: {
    name: "排名停滞",
    meaning: "关键词排名长期停在当前位置，没有改善迹象。",
    severityWhy: "自动规则：≥3 次可比观测、跨度 ≥7 天、净变化 <1 位、且排名仍在第 3 位之后，判为「中」。",
    fix: "内容需要突破而不是维护：扩写深度、加结构化数据（FAQ/HowTo）、补内链外链，或更换目标页。",
  },
  TARGET_PAGE_MISMATCH: {
    name: "目标页错配",
    meaning: "实际在搜索结果里排名的 URL 不是你为该关键词设定的目标页。",
    severityWhy: "自动规则：设定了目标页但观测到的排名 URL 不一致，判为「中」。",
    fix: "二选一：加强内链锚文本把权重导向目标页；或顺势把排名更好的那个页面设为目标页。",
  },
  COMPETITOR_ADVANTAGE: {
    name: "竞品占优",
    meaning: "竞品在该关键词上进入了 Top3，而我方排名还在 10 名开外。",
    severityWhy: "自动规则：竞品 Top3 且我方排名 >10，判为「高」。",
    fix: "对标竞品的这个页面：比较内容深度/新鲜度/外链，找出差距点逐项补齐。",
  },
  RANK_GAP: {
    name: "排名差距",
    meaning: "竞品排名领先我方 5 位以上。",
    severityWhy: "自动规则：与竞品排名差距 ≥5 位，判为「中」。",
    fix: "参考竞品占优页的内容结构做针对性强化，不必推翻重写。",
  },
  NO_ANSWER: {
    name: "无答案",
    meaning: "AI 对该问题给不出有效答案。",
    severityWhy: "由测量流程按当时的回答质量评估写入。",
    fix: "补一篇直接回答型内容（定义/步骤/对比表），让 AI 下次有料可引。",
  },
  MISSING_FACT: {
    name: "事实缺失",
    meaning: "AI 的回答缺少关键事实（价格/参数/品牌定位等）。",
    severityWhy: "由测量流程按事实重要度评估写入。",
    fix: "在权威页面补齐该事实并用结构化数据标注，等下一轮测量验证。",
  },
  MISSING_PAGE: {
    name: "缺落地页",
    meaning: "目前没有任何页面覆盖这个问题。",
    severityWhy: "由测量流程评估写入。",
    fix: "把该问句纳入内容计划，新建目标页。",
  },
  WEAK_CONTENT: {
    name: "内容薄弱",
    meaning: "有页面覆盖，但内容太薄，不足以被 AI 引用。",
    severityWhy: "由测量流程评估写入。",
    fix: "扩写：补证据、案例、FAQ，做到比排在前面竞品页更完整。",
  },
  RETRIEVAL_GAP: {
    name: "检索盲区",
    meaning: "内容存在且质量可以，但 AI 检索/召回不到它。",
    severityWhy: "由测量流程评估写入。",
    fix: "检查 sitemap 收录、内链入口、结构化数据与外链信号。",
  },
  REPRESENTATION_GAP: {
    name: "呈现缺口",
    meaning: "品牌被提及，但呈现不完整或有偏差。",
    severityWhy: "由测量流程评估写入。",
    fix: "统一各渠道的品牌事实口径，增加权威第三方来源。",
  },
  TECHNICAL_ACCESS_GAP: {
    name: "AI 抓取受阻",
    meaning: "AI 爬虫无法正常抓取你的内容（注意区别于 SEO 抓取问题）。",
    severityWhy: "由测量流程评估写入。",
    fix: "排查 robots.txt、页面是否纯 JS 渲染、服务可访问性。",
  },
  CONFLICTING_INFORMATION: {
    name: "信息冲突",
    meaning: "网络上关于你的品牌/产品存在互相矛盾的信息。",
    severityWhy: "由测量流程评估写入。",
    fix: "确定唯一事实源，逐一修正不一致的渠道信息。",
  },
  TECHNICAL_ISSUE: {
    name: "SEO 技术问题",
    meaning: "搜索引擎抓取/索引存在技术问题。",
    severityWhy: "由测量流程评估写入。",
    fix: "用 GSC 覆盖率报告定位问题页并修复。",
  },
  INTERNAL_COMPETITION: {
    name: "内耗竞争",
    meaning: "多个自己的页面在竞争同一关键词，分散权重。",
    severityWhy: "由测量流程评估写入。",
    fix: "合并重复页面或设置 canonical，保留一个主目标页。",
  },
  NO_ACTION_REQUIRED: {
    name: "无需行动",
    meaning: "检测通过，没有需要处理的问题。",
    severityWhy: "—",
    fix: "保持现状，按节奏复查即可。",
  },
};

/* 统计卡片：num 为纯计数；传入 targetId 时整卡可点击，平滑滚动到对应明细区；
   sub 为卡片下方小字副行（如分组计数） */
function seoStat(label, num, color, targetId, sub) {
  return '<div class="card' + (targetId ? " is-link" : "") + '"' +
    (targetId ? ' data-scroll="' + targetId + '" title="点击查看明细"' : "") + ">" +
    '<div class="stat-num"' + (color ? ' style="color:' + color + '"' : "") + ">" + num + "</div>" +
    '<div class="stat-label">' + esc(label) + "</div>" +
    (sub ? '<div class="stat-sub">' + esc(sub) + "</div>" : "") +
    "</div>";
}

async function renderSeoGrowth() {
  const _operatorViewEpoch = operatorViewEpoch;
  if (!requireProduct()) return;
  let html = "";
  try {
    if (!SEO_SITE || SEO_SITE.source_product_id !== state.current) {
      const sites = await api("GET", "/sites");
      SEO_SITE = sites.find((s) => s.source_product_id === state.current) || null;
    }
    if (!SEO_SITE) {
      if (typeof _operatorViewEpoch !== "undefined" && _operatorViewEpoch !== operatorViewEpoch) return; $("#view").innerHTML = '<div class="empty">' + icon("ic-trend") +
        '<p>当前产品尚未关联站点（sites.source_product_id）。请先在系统中登记站点。</p></div>';
      return;
    }
    const sid = SEO_SITE.id;
    const [wb, keywords, gaps] = await Promise.all([
      api("GET", "/sites/" + sid + "/growth-workbench"),
      api("GET", "/sites/" + sid + "/seo/keywords"),
      api("GET", "/sites/" + sid + "/competitor-gaps"),
    ]);

    const c = wb.counters || {};
    const p0Count = (wb.action_queue || []).filter((a) => a.priority === "P0").length;
    const dueCount = (wb.reviews_due || []).length;
    const diagList = wb.open_diagnoses || [];
    const openDiag = diagList.length;
    const seoDiagCount = diagList.filter((d) => d.scope_type === "keyword").length;
    /* 质量可见性（2026-10-14 下游传播审计 R3）：schema 不可用时显式声明，
       避免 held_evidence_count=0 被误读为"已审核且干净"（fail-visible） */
    if (wb.quality_schema_available === false) {
      html += '<div class="panel" style="margin-top:16px;border-left:4px solid #c0392b">' +
        '<div class="panel-body"><b style="color:#c0392b">⚠ 质量审核 schema 不可用</b>' +
        '<p class="muted" style="margin:6px 0 0">观测质量审核表缺失或不可访问：下方诊断的证据质量计数不可信（显示为 0），' +
        '观测 / Delta 读取端已按 fail-closed 拒绝返回。请先恢复 observation_quality_reviews 表再解读本页。</p></div></div>';
    }
    html += '<div class="stats-row">' +
      seoStat("活跃关键词", c.active_keywords ?? 0) +
      seoStat("排名观测", c.rank_observations ?? 0) +
      seoStat("P0 行动", p0Count, p0Count ? "#c0392b" : "", p0Count ? "sec-action-queue" : "") +
      seoStat("到期复查", dueCount, dueCount ? "#d35400" : "", dueCount ? "sec-reviews" : "") +
      seoStat("开放诊断", openDiag, openDiag ? "#c0392b" : "", openDiag ? "sec-diagnoses" : "",
        openDiag ? "SEO " + seoDiagCount + " / GEO " + (openDiag - seoDiagCount) : "") +
      seoStat("竞品数", c.competitors ?? 0) +
      '</div>';

    const dueHtml = (wb.reviews_due || []).map((a) =>
      '<div class="workbench-row">' +
      '<span class="badge badge-p' + (a.priority || "P3").replace("P", "") + '">' + esc(a.priority || "P3") + '</span>' +
      '<span class="wr-title">' + esc(a.title) + '</span>' +
      '<span class="wr-meta">复查 ' + esc(a.review_at || "—") + '</span></div>').join("")
      || '<p class="muted">暂无到期复查</p>';
    const queueHtml = (wb.action_queue || []).filter((a) => a.priority === "P0" || a.priority === "P1")
      .slice(0, 8).map((a) =>
      '<div class="workbench-row">' +
      '<span class="badge badge-p' + (a.priority || "P3").replace("P", "") + '">' + esc(a.priority || "P3") + '</span>' +
      '<span class="badge badge-line">' + esc(a.action_type) + '</span>' +
      '<span class="wr-title">' + esc(a.title) + '</span>' +
      '<span class="wr-meta">' + esc(a.status) + (a.expected_effect ? " · " + esc(a.expected_effect) : "") + '</span></div>').join("")
      || '<p class="muted">暂无 P0/P1 行动</p>';

    /* 开放诊断明细：按测量维度分两组（9-30 Red Team 裁决「两个 measurement dimension」的呈现层落地）——
       SEO 排名诊断（scope_type=keyword，来源 rank_observations）/ GEO 引用诊断（其余 scope，来源 observations AI 实测）；
       组内按严重度排序；可展开行 = 严重度徽章 + 类型中文名 + 完整标题 + 可点击跳转链接 */
    const sevLegend = '<div class="legend" style="margin-bottom:10px">' +
      '<span>严重度由系统规则自动判定（非人工打分）：</span>' +
      '<span class="badge badge-p0">高</span><span>下滑≥5位 / 竞品Top3而我方&gt;10 / 高价值问句未被引用</span>' +
      '<span class="badge badge-p1">中</span><span>停滞≥7天 / 目标页错配 / 竞品领先≥5位</span>' +
      '<span class="badge badge-low">低/提示</span><span>其余语义型诊断按测量评估</span></div>';
    const diagItemHtml = (d) => {
      const info = DIAG_TYPE_INFO[d.diagnosis_type]
        || { name: d.diagnosis_type || "—", meaning: "暂无释义。", severityWhy: "—", fix: "—" };
      const sevTxt = esc(SEV_LABEL[d.severity] || d.severity || "—");
      const refs = [];
      if (d.keyword_id) refs.push('<a class="ref-link" data-kw-ref="' + d.keyword_id + '" title="点击定位到排名表中的该关键词">关键词#' + d.keyword_id + '</a>');
      if (d.question_id) refs.push('<a class="ref-link" data-q-ref="' + d.question_id + '" title="点击查看该问句的 AI 实测记录">问句#' + d.question_id + '</a>');
      /* 质量可见性（2026-10-14 下游传播审计 R3）：锚定于 HOLD/REJECTED 观测的证据数 */
      const heldBadge = (d.held_evidence_count > 0)
        ? '<span class="badge badge-p0" title="该诊断锚定的证据中有 ' + d.held_evidence_count +
          ' 条处于 HOLD/REJECTED 处置，KPI 口径已将其排除">证据HOLD ' + d.held_evidence_count + '</span>'
        : "";
      return '<details class="diag-item">' +
        '<summary>' +
        '<span class="badge ' + (SEV_BADGE[d.severity] || "badge-line") + '">' + sevTxt + '</span>' +
        '<span class="badge badge-line">' + esc(info.name) + '</span>' +
        heldBadge +
        '<span class="wr-title">' + esc(d.title || "（无标题）") + '</span>' +
        (refs.length ? '<span class="wr-meta">' + esc(d.scope_type || "") + ' · ' + refs.join(" · ") + '</span>' : "") +
        '</summary>' +
        '<div class="diag-detail">' +
        '<p><b>是什么意思：</b>' + esc(info.meaning) + '</p>' +
        '<p><b>严重度为何是「' + sevTxt + '」：</b>' + esc(info.severityWhy) + '</p>' +
        '<p><b>建议怎么处理：</b>' + esc(info.fix) + '</p>' +
        '</div></details>';
    };
    const SEV_RANK = { critical: 0, high: 1, medium: 2, low: 3, info: 4 };
    const sortBySev = (arr) => arr.slice().sort((a, b) =>
      (SEV_RANK[a.severity] ?? 9) - (SEV_RANK[b.severity] ?? 9));
    const seoDiag = sortBySev(diagList.filter((d) => d.scope_type === "keyword"));
    const geoDiag = sortBySev(diagList.filter((d) => d.scope_type !== "keyword"));
    const diagGroupHtml = (label, list, hint) =>
      '<div class="diag-group-head"><b>' + esc(label) + '（' + list.length + '）</b>' +
      '<span class="muted">' + esc(hint) + '</span></div>' +
      (list.map(diagItemHtml).join("") || '<p class="muted">暂无</p>');
    const diagHtml = diagGroupHtml("SEO 排名诊断", seoDiag, "来源：关键词排名观测 · 处置：调排名 / 改页面") +
      diagGroupHtml("GEO 引用诊断", geoDiag, "来源：AI 实测问句 · 处置：改内容 / 补引用");

    const kwRows = keywords.slice(0, 20).map((k) =>
      '<tr data-seo-kw="' + k.id + '"><td><b>' + esc(k.name) + '</b></td>' +
      '<td>' + ((k.current_rank === null || k.current_rank === undefined)
        ? '<span class="muted">未排名</span>' : esc(k.current_rank)) + '</td>' +
      '<td>' + trendBadge(k.trend_status, k.delta_value) + '</td>' +
      '<td>' + (k.target_page_url ? '<code>' + esc(k.target_page_url) + '</code>'
        : '<span class="muted">未设</span>') + '</td></tr>').join("")
      || '<tr><td colspan="4" class="empty-cell">暂无 SEO 关键词；请到“测量与交付”维护已授权的 SEO 数据</td></tr>';

    const seoBehind = (gaps.seo && gaps.seo.behind || []).slice(0, 5);
    const geoBehind = (gaps.geo && gaps.geo.behind || []).slice(0, 5);
    const seoBehindHtml = seoBehind.map((b) =>
      '<div class="workbench-row">' +
      '<span class="wr-title">' + esc(b.keyword) + '</span> <span class="wr-meta">vs ' + esc(b.competitor) + '</span>' +
      '<span class="badge badge-p0">落后 ' + esc(Math.abs(b.gap)) + ' 位</span></div>').join("")
      || '<p class="muted">SEO 维度暂无落后项（或竞品观测不足）</p>';
    const geoBehindHtml = geoBehind.map((b) =>
      '<div class="workbench-row">' +
      '<span class="wr-title">' + esc(b.question || "") + '</span> <span class="wr-meta">(' + esc(b.provider || "") + ') vs ' + esc(b.brand) + '</span>' +
      '<span class="badge badge-p0">落后 ' + esc(Math.abs(b.gap)) + ' 位</span></div>').join("")
      || '<p class="muted">GEO 维度暂无落后项（或竞品观测不足）</p>';

    html += '<div class="panel" style="margin-top:16px">' +
      '<div class="panel-head"><h2>Today&#39;s Growth Work</h2></div>' +
      '<div class="panel-body"><h3 id="sec-reviews" style="margin:8px 0">到期复查</h3>' + dueHtml +
      '<h3 id="sec-action-queue" style="margin:16px 0 8px">P0/P1 行动队列</h3>' + queueHtml + '</div></div>' +
      '<div class="panel" style="margin-top:16px">' +
      '<div class="panel-head"><h2>开放诊断明细（' + openDiag + '）</h2>' +
      '<span class="muted">SEO / GEO 两组分开呈现 · 组内按严重度排序 · 点击行展开释义 · 点击 关键词# / 问句# 可跳转</span></div>' +
      '<div class="panel-body" id="sec-diagnoses">' + sevLegend + diagHtml + '</div></div>' +
      '<div class="panel" style="margin-top:16px">' +
      '<div class="panel-head"><h2>关键词排名（Top 20）</h2>' +
      '<span class="muted">站点 ' + esc(SEO_SITE.domain) + ' · 单点观测不显示趋势</span></div>' +
      '<div class="panel-body"><table><thead><tr><th>关键词</th><th>当前排名</th><th>趋势</th><th>目标页</th></tr></thead>' +
      '<tbody>' + kwRows + '</tbody></table></div></div>' +
      '<div class="panel" style="margin-top:16px">' +
      '<div class="panel-head"><h2>竞品差距（落后项 Top 5）</h2></div>' +
      '<div class="panel-body"><h3 style="margin:8px 0">SEO 维度</h3>' + seoBehindHtml +
      '<h3 style="margin:16px 0 8px">GEO 维度</h3>' + geoBehindHtml + '</div></div>';
  } catch (e) {
    html = '<div class="empty"><p>加载失败：' + esc(e.message) + '</p></div>';
  }
  if (typeof _operatorViewEpoch !== "undefined" && _operatorViewEpoch !== operatorViewEpoch) return; $("#view").innerHTML = html;
  $$("[data-scroll]").forEach((el) => {
    el.onclick = () => {
      const t = document.getElementById(el.dataset.scroll);
      if (t) t.scrollIntoView({ behavior: "smooth", block: "start" });
    };
  });
  $$(".ref-link").forEach((el) => {
    el.onclick = (ev) => {
      ev.preventDefault();
      ev.stopPropagation();
      if (el.dataset.kwRef) scrollToSeoKeyword(Number(el.dataset.kwRef));
      else if (el.dataset.qRef) openQuestionDetail(Number(el.dataset.qRef));
    };
  });
}

/* 诊断明细 → 关键词：定位到本页「关键词排名」表中的对应行并高亮闪烁 */
function scrollToSeoKeyword(kid) {
  const row = document.querySelector('tr[data-seo-kw="' + kid + '"]');
  if (!row) return toast("该关键词不在当前 Top 20 榜单内（可去 GSC 数据源补充观测）");
  row.scrollIntoView({ behavior: "smooth", block: "center" });
  row.classList.remove("row-flash");
  void row.offsetWidth; /* 重启动画 */
  row.classList.add("row-flash");
}

/* 诊断明细 → 问句：弹窗展示问句原文 + 该问句的 AI 实测观测记录 */
async function openQuestionDetail(qid) {
  let obs = [];
  let qText = "";
  try {
    obs = await api("GET", "/sites/" + SEO_SITE.id + "/observations?question_id=" + qid + "&limit=10");
    const qs = await api("GET", "/products/" + state.current + "/questions");
    const q = (qs || []).find((x) => x.id === qid);
    if (q) qText = q.text || "";
  } catch (e) { /* 明细加载失败不阻塞弹窗 */ }
  const obsRows = obs.map((o) =>
    '<tr><td>' + esc(o.provider || "—") + '</td>' +
    '<td>' + esc(o.surface || "—") + '</td>' +
    '<td>' + esc(o.mention_status || "—") + '</td>' +
    '<td>' + (o.citation_count ?? "—") + '</td>' +
    '<td>' + esc(String(o.observed_at || o.created_at || "").slice(0, 16)) + '</td></tr>').join("")
    || '<tr><td colspan="5" class="empty-cell">暂无该问句的 AI 实测记录</td></tr>';
  const body = (qText ? '<p style="margin:0 0 10px"><b>问句原文：</b>' + esc(qText) + '</p>' : "") +
    '<div style="max-height:360px;overflow-y:auto"><table><thead><tr>' +
    '<th>引擎</th><th>Surface</th><th>提及状态</th><th>引用数</th><th>观测时间</th></tr></thead>' +
    '<tbody>' + obsRows + '</tbody></table></div>';
  openModal("问句#" + qid + " 实测记录", body, {
    saveText: "去问句库",
    onSave: (close) => { close(); setView("questions"); },
  });
}
