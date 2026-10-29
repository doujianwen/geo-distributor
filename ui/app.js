/* CSP-safe partner workspace: canonical business data via the session BFF. */
(() => {
  "use strict";
  const uiBase = /^\/(ui|portal)\/hq\//.test(location.pathname) ? "/ui/hq" : "/ui";
  const app = document.getElementById("app"),
    $ = (id) => document.getElementById(id);
  // 官网首页链接：动态取当前域名（生产/本地开发均正确），避免硬编码本地域。
  const homeLink = $("home-link");
  if (homeLink) homeLink.href = window.location.origin + "/";
  let session = null,
    epoch = 0,
    tenant = "",
    draft = null,
    step = 1,
    dirty = false,
    lastHash = location.hash || "#/dashboard";
  const state = {};
  let demoInfo = { enabled: false, url: "" };
  const demoBanner = () =>
    session?.is_demo
      ? '<div class="demo-banner" role="status"><strong>虚拟演示 · 所有客户、回答和效果数据均为构造案例</strong><span>只读体验，不代表真实平台测量或商业效果。</span><a href="http://geo-growth.local/portal/">返回真实工作区</a></div>'
      : demoInfo.url
        ? `<div class="demo-switch">${link(demoInfo.url, "查看虚拟案例演示")}</div>`
        : "";
  const services = {
    diagnosis: "GEO / SEO 诊断",
    competitor_analysis: "竞品 GEO / SEO 分析",
    intervention: "GEO 增长解决方案",
    measurement: "GEO / SEO 效果监控",
    full_geo_project: "完整 GEO 增长项目",
    visibility_audit: "GEO 诊断（历史）",
    remeasurement: "效果复测",
  };
  const statuses = {
    draft: "草稿",
    submitted: "待总部确认",
    intake_review: "总部受理中",
    clarification_required: "待补充资料",
    scoping: "范围拟定中",
    scope_pending_approval: "待总部批准",
    approved: "已确认 / 待启动",
    in_execution: "交付进行中",
    blocked: "交付受阻",
    qa: "质量检查",
    rework: "返工中",
    delivered: "已交付",
    accepted: "已验收",
    rejected: "未受理",
    cancelled: "已取消",
    changes_requested: "待调整",
    completed: "已完成",
    in_progress: "进行中",
    not_started: "未开始",
    pending_assignment: "待分配",
    assigned: "已分配",
    converted_client: "已建客户",
    converted_request: "已转需求",
    converted_project: "已转项目",
  };
  const roles = {
    DISTRIBUTOR_ADMIN: "渠道商管理员",
    DISTRIBUTOR_USER: "渠道商成员",
    CLIENT_VIEWER: "只读成员",
    HQ_TECHNICAL: "总部运营",
    HQ_MANAGEMENT: "总部管理",
  };
  const durations = {
    one_time: "单次交付",
    "1_month": "1 个月",
    "3_months": "3 个月",
    "6_months": "6 个月",
    "12_months": "12 个月",
    to_be_determined: "待方案确定",
  };
  const countries = {
    US: "美国",
    DE: "德国",
    GB: "英国",
    CA: "加拿大",
    AU: "澳大利亚",
    FR: "法国",
    JP: "日本",
    IT: "意大利",
    ES: "西班牙",
    NL: "荷兰",
    BR: "巴西",
    CN: "中国",
    SG: "新加坡",
    KR: "韩国",
    AE: "阿联酋",
    MX: "墨西哥",
  };
  const languages = [
    "English",
    "German",
    "Spanish",
    "French",
    "Japanese",
    "Chinese",
    "Italian",
    "Portuguese",
    "Korean",
  ];
  const reportTitle = (r) =>
    /^GEO Visibility Report for /.test(r.title || "")
      ? "GEO 可见性报告"
      : r.title || "交付报告";
  const reportText = (s) =>
    ({
      "Review key findings with your team.": "与客户团队核对报告中的关键发现。",
      "Prioritize high-severity findings for intervention.":
        "优先处理高严重程度的问题。",
      "Schedule follow-up measurement after 30 days.":
        "在 30 天后安排后续测量。",
      "Results are based on a limited sample of queries.":
        "结果基于有限的查询样本。",
      "AI visibility is dynamic and may change over time.":
        "AI 可见性会随时间变化。",
      "Findings are based on observed patterns, not causal relationships.":
        "发现基于观察到的现象，不代表因果关系。",
    })[s] || s;
  const actions = {
    submitted: "提交需求",
    clarification: "要求补充",
    supplement: "补充资料",
    scope: "拟定范围",
    approve: "批准需求",
    reject: "拒绝需求",
  };
  const esc = (v) =>
    String(v ?? "").replace(
      /[&<>"']/g,
      (c) =>
        ({
          "&": "&amp;",
          "<": "&lt;",
          ">": "&gt;",
          '"': "&quot;",
          "'": "&#39;",
        })[c],
    );
  const dt = (v) => {
    if (!v) return "未记录";
    if (/Z$|[+-]\d{2}:\d{2}$/.test(v)) {
      const d = new Date(v);
      if (!isNaN(d))
        return (
          new Intl.DateTimeFormat("zh-CN", {
            timeZone: "Asia/Shanghai",
            year: "numeric",
            month: "2-digit",
            day: "2-digit",
            hour: "2-digit",
            minute: "2-digit",
            second: "2-digit",
            hour12: false,
          }).format(d) + " 北京时间"
        );
    }
    return String(v).replace("T", " ").slice(0, 19) + "（源时间，未标注时区）";
  };
  const link = (href, text, cls = "") =>
    `<a class="${cls}" href="${esc(href)}">${esc(text)}</a>`;
  const chip = (s) =>
    `<span class="chip ${["blocked", "rejected"].includes(s) ? "err" : s === "clarification_required" ? "warn" : ""}">${esc(statuses[s] || s || "未记录")}</span>`;
  const notice = (s, k = "info") =>
    `<div class="notice ${k}" role="status">${esc(s)}</div>`;
  const empty = (s, href = "", text = "") =>
    `<div class="empty"><p>${esc(s)}</p>${href ? link(href, text, "btn") : ""}</div>`;
  const card = (title, body) =>
    `<section class="card"><h2>${esc(title)}</h2>${body}</section>`;
  const heading = (title, sub = "", buttons = "") =>
    `<div class="page-heading"><div><h1>${esc(title)}</h1><p class="muted">${esc(sub)}</p></div><div class="toolbar">${buttons}</div></div>`;
  const field = (id, title, html, error = "") =>
    `<div class="field"><label for="${id}">${esc(title)}</label>${html}<span class="field-error" id="${id}-error" role="alert">${esc(error)}</span></div>`;
  const input = (id, v = "", extra = "") =>
    `<input id="${id}" value="${esc(v)}" ${extra}>`;
  const area = (id, v = "", extra = "") =>
    `<textarea id="${id}" ${extra}>${esc(v)}</textarea>`;
  const opts = (items, value = "") =>
    Object.entries(items)
      .map(
        ([v, s]) =>
          `<option value="${esc(v)}" ${v === value ? "selected" : ""}>${esc(s)}</option>`,
      )
      .join("");
  const row = (label, value) =>
    `<div class="summary-row"><dt>${esc(label)}</dt><dd>${value}</dd></div>`;
  const scoped = (url, t = tenant) =>
    t
      ? url +
        (url.includes("?") ? "&" : "?") +
        "tenant_id=" +
        encodeURIComponent(t)
      : url;
  const obj = (type, id, t) =>
    "#/" +
    type +
    "/" +
    encodeURIComponent(id) +
    (session?.is_hq && t ? "?tenant=" + encodeURIComponent(t) : "");
  const backTo = section => session?.is_hq ? state.hqReturn?.[section] || "#/" + section : "#/" + section;
  const writer = () => session?.role === "DISTRIBUTOR_ADMIN";
  const name = (id, cs) => cs.find((c) => c.client_id === id)?.name || id;
  function website(url) {
    try {
      const u = new URL(url);
      return ["http:", "https:"].includes(u.protocol)
        ? link(u.href, url)
        : esc(url);
    } catch {
      return esc(url || "未提供");
    }
  }
  async function api(method, path, body, headers = {}) {
    const r = await fetch(uiBase + "/proxy" + path, {
      method,
      credentials: "same-origin",
      headers: {
        Accept: "application/json",
        ...(body ? { "Content-Type": "application/json" } : {}),
        ...headers,
      },
      ...(body ? { body: JSON.stringify(body) } : {}),
    });
    const data = await r.json().catch(() => null);
    if (!r.ok) {
      const d = data?.detail;
      const e = new Error(
        d === "No measurement available to deliver for this project" ? "此项目尚无可用测量，暂时不能生成技术报告。请先完成测量与核对。" : r.status === 429 ? "操作较频繁，请稍后重试；当前输入已保留。" : r.status >= 500
          ? "服务暂不可用，请稍后重试"
          : Array.isArray(d)
            ? d.map((x) => x.msg).join("；")
            : typeof d === "string"
              ? d
              : "请求未完成，请稍后重试",
      );
      e.status = r.status;
      if (r.status === 401 && session) {
        session = null;
        window.GrowthWorkspace?.clear();
        dirty=false;
        epoch++;
        paint();
        login("会话已失效，请重新登录后继续。");
      }
      throw e;
    }
    return data;
  }
  function paint() {
    document.body.classList.toggle("demo-mode", !!session?.is_demo);
    $("session-box").hidden = !session;
    document.title = session?.is_hq || uiBase.endsWith("hq") ? "总部工作台 · GEO" : "渠道商控制台 · GEO";
    $("workspace-title").textContent = session?.is_hq || uiBase.endsWith("hq") ? "总部管理与运营" : "渠道商控制台";
    const headquarters = session?.is_hq || uiBase.endsWith("hq");
    document.querySelector(".brand .sub").textContent = headquarters ? "受理 · 交付 · 结果协作" : "GEO 合作伙伴工作区";
    document.querySelector(".foot > span").textContent = headquarters ? "总部统筹受理与专业交付" : "Distributor sells; HQ delivers.";
    if (session)
      $("who").textContent =
        (roles[session.role] || session.role) + " · " + session.tenant_id;
  }
  function shell(active, html) {
    html = demoBanner() + html;
    const businessTabs = session.is_hq ? Object.entries(hqTitles) : [
      ["dashboard", "工作台"],
      ["leads", session.is_hq ? "线索分配" : "我的线索"],
      ["clients", "我的客户"],
      ["projects", session.is_hq ? "需求受理与项目" : "需求与项目"],
    ];
    // 角色感知排序：业务中枢(home)在前，GEO 交付/执行在后；功能说明始终最末
    const deliveryTabs = [["growth/overview", "增长证据与交付"], ["operator/dashboard", "专业作业台"]];
    const tabs = session.is_hq
      ? [...businessTabs, ...deliveryTabs, ...(session.role === 'HQ_MANAGEMENT' ? [["access", "账号与作业授权"]] : [])]
      : [...businessTabs, ...deliveryTabs];
    const allTabs = [...tabs, ["help", "功能说明"]];
    app.innerHTML = `<div class="workspace"><aside class="sidebar"><div class="workspace-label">${session.is_hq ? "GEO 总部管理与运营" : "GEO 合作伙伴工作区"}</div><button class="btn ghost menu-toggle" id="menu" aria-controls="nav" aria-expanded="false">工作区导航 · 展开</button><nav id="nav" aria-label="工作区导航">${allTabs.map(([k, s]) => `<a href="#/${k}" ${(k === active || (active === "growth" && k === "growth/overview")) ? 'class="on" aria-current="page"' : ""}>${s}</a>`).join("")}</nav><p class="sidebar-note">渠道商连接客户<br>总部负责专业交付</p></aside><div class="content" id="view" tabindex="-1">${html}</div></div>`;
    $("menu").onclick = () => {
      const open = $("menu").getAttribute("aria-expanded") !== "true";
      $("menu").setAttribute("aria-expanded", String(open));
      $("nav").classList.toggle("expanded", open);
    };
  }
  function failure(e, active) {
    if (!session) return;
    const geoMatch = location.hash.match(/^#\/geo\/([^?]+)/);
    shell(
      active,
      heading(
        "暂时无法读取",
        "",
        geoMatch
          ? link(
              obj("project", decodeURIComponent(geoMatch[1]), tenant),
              "返回项目",
              "btn ghost",
            )
          : "",
      ) +
        notice(e.message, "err") +
        '<button class="btn" id="retry">重新加载</button>',
    );
    $("retry").onclick = route;
  }
  function error(id, e) {
    if ($(id)) {
      $(id).innerHTML = notice(e.message, "err");
      $(id).scrollIntoView({ block: "nearest" });
    }
  }
  function list(id, rows, cols, render, filters = {}) {
    if (!$(id)) return;
    const s = (state[id] ||= { q: "", filter: "", page: 1 });
    function draw() {
      const found = rows.filter(
        (r) =>
          JSON.stringify(r).toLowerCase().includes(s.q.toLowerCase()) &&
          (!s.filter || r.status === s.filter),
      );
      const max = Math.max(1, Math.ceil(found.length / 20));
      s.page = Math.min(s.page, max);
      $(id).innerHTML =
        `<div class="list-tools"><label>搜索<input id="${id}-q" type="search" value="${esc(s.q)}" placeholder="名称、编号或关键词"></label>${Object.keys(filters).length ? `<label>状态<select id="${id}-filter"><option value="">全部状态</option>${opts(filters, s.filter)}</select></label>` : ""}<span>${found.length} 条记录</span></div><div class="table-wrap"><table><thead><tr>${cols.map((x) => `<th scope="col">${esc(x)}</th>`).join("")}</tr></thead><tbody>${
          found
            .slice((s.page - 1) * 20, s.page * 20)
            .map(render)
            .join("") ||
          `<tr><td colspan="${cols.length}">${empty(rows.length ? "没有符合条件的记录，可清空筛选。" : "暂无记录。")}</td></tr>`
        }</tbody></table></div><div class="pagination"><button class="btn ghost" id="${id}-prev" ${s.page === 1 ? "disabled" : ""}>上一页</button><span>${s.page} / ${max}</span><button class="btn ghost" id="${id}-next" ${s.page === max ? "disabled" : ""}>下一页</button></div>`;
      $(id + "-q").oninput = (e) => {
        const at = e.target.selectionStart;
        s.q = e.target.value;
        s.page = 1;
        draw();
        $(id + "-q").focus();
        $(id + "-q").setSelectionRange(at, at);
      };
      if ($(id + "-filter"))
        $(id + "-filter").onchange = (e) => {
          s.filter = e.target.value;
          s.page = 1;
          draw();
        };
      $(id + "-prev").onclick = () => {
        s.page--;
        draw();
      };
      $(id + "-next").onclick = () => {
        s.page++;
        draw();
      };
    }
    draw();
  }
  const reqRow = (r) =>
    `<tr><td>${link(obj("request", r.request_id, r.tenant_id), services[r.service] || r.service)}<small>${esc(r.request_id)}</small></td><td>${esc(r.client_name || r.client_id)}${session.is_hq ? `<small>${esc(r.tenant_id)}</small>` : ""}</td><td>${chip(r.status)}</td><td>${esc(dt(r.updated_at))}</td></tr>`;
  const projRow = (p) =>
    `<tr><td>${link(obj("project", p.project_id, p.tenant_id), services[p.service] || "GEO 服务项目")}<small>${esc(p.project_id)}</small></td><td>${esc(p.client_name || p.client_id)}</td><td>${chip(p.status)}</td><td>${esc(p.service_stage_label || "待确认")}</td><td>${esc(dt(p.updated_at))}</td></tr>`;
  const hqLabels = { access_inactive:"发布有效 · 客户访问已停用或档案缺失", visible: "客户当前可见", unpublished: "尚未向客户发布 · 待审查", withdrawn: "已撤回", invalid: "发布已失效", internal: "内部报告", pending: "待客户回复", submitted: "客户已提交 · 待团队处理", confirmed: "客户已确认 · 待团队处理", changes_requested: "客户要求修改 · 待团队处理", closed: "已处理关闭" };
  const hqTitles = { dashboard: "总部工作台", leads: "线索分配", requests: "需求受理", projects: "项目交付", clients: "客户与渠道", results: "结果与反馈", records: "操作记录" };
  const hqOps = { start: "启动交付", advance: "推进到下一阶段", complete: "完成当前阶段", block: "登记阻塞", resume: "解除阻塞并恢复" };
  const hqEvent = { ...actions, published:"发布客户待办", submit:"提交资料", changes_requested:"要求修改", assign: "分配线索", intake: "接收线索", convert_request: "线索转需求", start: "启动交付", advance: "推进服务阶段", complete: "完成阶段", block: "登记阻塞", resume: "恢复交付", create: "创建客户待办", respond: "客户答复", confirm: "客户确认", request_changes: "要求修改", close: "关闭待办", reopen: "重新请求确认", withdraw: "撤回", publish: "向客户发布" };
  const freshKey = () => "hq-" + crypto.getRandomValues(new Uint32Array(4)).join("-");
  function hqScope(data) {
    return `<div class="card hq-scope"><label for="hq-scope">当前查看范围<select id="hq-scope">${opts({ "": "全部渠道与总部直管", ...Object.fromEntries(data.tenants.map(t => [t.tenant_id, t.tenant_id === "HQ-INTAKE" ? "总部直管 / 待分配" : t.tenant_id])) }, state.hqTenant || "")}</select></label><p class="muted">数据读取于 ${esc(dt(data.generated_at))}。${session.role === "HQ_MANAGEMENT" ? "管理身份可批准需求。" : "运营 / 技术身份拟定范围，批准由总部管理完成。"}</p></div>`;
  }
  async function hqWorkspace(token, section, args) {
    const data = await api("GET", scoped("/hq/workspace", state.hqTenant || ""));
    if (token !== epoch || !session) return;
    const cs = data.clients, ps = data.projects, rs = data.requests;
    let body = "";
    if (section === "dashboard") {
      const tiles = [["待分配线索", "unassigned", "leads", "unassigned"], ["待拟服务范围", "scoping", "requests", "scoping"], ["待管理批准", "approval", "requests", "scope_pending_approval"], ["受阻项目", "blocked", "projects", "blocked"], ["待客户回复", "awaiting_customer", "results", "pending"], ["客户已答 · 待团队处理", "awaiting_team", "results", "team"], ["报告待审查与发布", "unpublished", "results", "unpublished"], ["客户发布已失效", "invalid", "results", "invalid"]];
      body = `<div class="kpi-grid hq-kpis">${tiles.map(([title, key, route, q]) => `<a class="card kpi-card" href="#/${route}?queue=${q}"><span>${esc(title)}</span><strong>${data.counts[key]}</strong><span class="small">查看完整队列 →</span></a>`).join("")}</div>` + card("今天从哪里开始", `<ol><li>先分配线索并核实需求资料，再拟定可交付范围。</li><li>批准后进入项目交付；生成技术报告后，另行审查并向客户发布。</li><li>处理客户答复；客户确认意见与完成阶段均不代表项目已验收。</li></ol>`) + card("需要关注的项目", '<div id="hq-attention"></div>');
    } else if (section === "clients") {
      body = card("渠道业务归属", '<div id="hq-tenants"></div>') + card("客户目录", '<div id="hq-clients"></div>');
    } else if (section === "results") {
      body = notice("技术报告生成、客户可见、项目验收分别记录。失效代表原报告或测量关联已变化，不能继续视为客户可见。") + card("报告与客户可见性", '<div id="hq-reports"></div>') + card("客户协作队列", '<div id="hq-reviews"></div>');
    } else if (section === "records") {
      body = notice("这里是已存储的业务处理记录，不包含全部安全访问日志。历史未记录的角色和时间保持未知；共享集成身份不能代表具体员工。", "warn") + card("业务处理记录", '<div id="hq-records"></div>');
    } else body = card(hqTitles[section], `<div id="hq-${section}"></div>`);
    shell(section, heading(hqTitles[section], "线索 → 需求确认 → 交付 → 客户结果与反馈", (section === "dashboard" ? "" : link("#/dashboard", "返回总部工作台", "btn ghost"))) + hqScope(data) + body);
    $("hq-scope").onchange = e => { state.hqTenant = e.target.value; route(); };
    const q = args.get("queue");
    const queueId = section + "|" + (q || "all");
    const queueStates = (state.hqQueueStates ||= {});
    function queueState(id, filter = "") {
      const key = queueId + "|" + id;
      state[id] = (queueStates[key] ||= {q:"",filter,page:1});
    }
    queueState("hq-requests", q === "scoping" ? "" : q || "");
    queueState("hq-projects", q || "");
    queueState("hq-leads", q === "unassigned" ? "" : q || "");
    queueState("hq-reports", ["unpublished","invalid"].includes(q) ? q : "");
    queueState("hq-reviews", q === "pending" ? "pending" : "");


    const requestRows = q === "scoping" ? rs.filter(r => ["submitted", "intake_review", "scoping"].includes(r.status)) : rs;
    if (section === "requests") list("hq-requests", requestRows, ["需求", "客户与渠道", "状态", "更新"], reqRow, { submitted: "待拟范围", intake_review: "受理中", clarification_required: "等待补充", scope_pending_approval: "待管理批准", approved: "已批准", rejected: "已拒绝" });
    if (section === "projects") list("hq-projects", ps, ["项目", "客户", "项目状态", "服务阶段", "更新"], p => projRow({...p, client_name: `${p.client_name} · ${p.tenant_id}`}), { approved: "待启动", in_execution: "执行中", blocked: "受阻", qa: "质量检查", delivered: "已交付", accepted: "已验收" });
    if (section === "dashboard") list("hq-attention", ps.filter(p => ["approved", "blocked", "rework", "changes_requested"].includes(p.status)), ["项目", "客户", "项目状态", "服务阶段", "更新"], projRow);
    if (section === "clients") {
      list("hq-tenants", data.tenants.filter(t => !state.hqTenant || t.tenant_id === state.hqTenant), ["渠道归属", "分配资格", "客户数", "项目数"], t => `<tr><td>${esc(t.tenant_id)}</td><td>${t.tenant_id === "HQ-INTAKE" ? "总部接收与直管" : t.assignable ? "已注册 · 可分配" : "历史业务归属 · 不可新分配"}</td><td>${t.clients}</td><td>${t.projects}</td></tr>`);
      list("hq-clients", cs.map(c => ({...c, status: c.is_active ? "active" : "inactive"})), ["客户", "渠道", "行业 / 网站", "状态"], c => `<tr><td>${link(obj("client", c.client_id, c.tenant_id), c.name)}</td><td>${esc(c.tenant_id)}</td><td>${esc(c.industry || "未提供")}<small>${website(c.website)}</small></td><td>${c.is_active ? "启用" : "停用"}</td></tr>`, {active: "启用", inactive: "停用"});
    }
    if (section === "leads") {

      list("hq-leads", (q === "unassigned" ? data.leads.filter(l=>["new","pending_assignment"].includes(l.intake_status)) : data.leads).map(l => ({...l, status:l.intake_status})), ["线索", "归属", "状态", "来源 / 更新"], l => `<tr><td>${link(obj("lead", l.lead_id, l.tenant_id), l.contact.company || l.contact.name || "官网线索")}</td><td>${esc(l.tenant_id === "HQ-INTAKE" ? "总部待分配 / 直管" : l.tenant_id)}</td><td>${chip(l.intake_status)}</td><td>${esc(l.source)}<small>${esc(dt(l.updated_at))}</small></td></tr>`, {pending_assignment:"待分配", hq_managed:"总部直管", assigned:"已分配", converted_client:"已建客户", converted_request:"已转需求"});
    }
    if (section === "results") {

      list("hq-reports", data.reports, ["报告", "客户与渠道", "客户可见性", "生成 / 办理"], r => `<tr><td>${r.status !== "internal" && r.title !== "原报告缺失" ? link(obj("report", r.report_id,r.tenant_id),r.title || "交付报告") : esc(r.title)}<small>版本 ${esc(r.version || "未记录")} · ${esc(r.report_id)}</small></td><td>${esc(r.client_name)}<small>${esc(r.tenant_id)}</small></td><td>${esc(hqLabels[r.status])}</td><td>${esc(dt(r.created_at))}<small>${link(obj("project",r.project_id,r.tenant_id),"进入项目办理发布")}</small></td></tr>`, {visible:hqLabels.visible,unpublished:hqLabels.unpublished,withdrawn:hqLabels.withdrawn,invalid:hqLabels.invalid,access_inactive:hqLabels.access_inactive,internal:hqLabels.internal});
      list("hq-reviews", q === "team" ? data.reviews.filter(r => ["submitted","confirmed","changes_requested"].includes(r.status)) : data.reviews, ["客户待办", "客户与渠道", "处理状态", "更新"], r => `<tr><td>${link(obj("project",r.project_id,r.tenant_id),r.title)}</td><td>${esc(r.client_name)}<small>${esc(r.tenant_id)}</small></td><td>${esc(hqLabels[r.status] || r.status)}</td><td>${esc(dt(r.updated_at))}</td></tr>`, {pending:hqLabels.pending,submitted:hqLabels.submitted,confirmed:hqLabels.confirmed,changes_requested:hqLabels.changes_requested,closed:hqLabels.closed,withdrawn:hqLabels.withdrawn});
    }
    if (section === "records") {
      const targets = {request:"request",lead:"lead",review:"project",publication:"project",project:"project"};
      list("hq-records", data.events, ["时间 / 来源", "业务操作", "对象 / 渠道", "角色与说明"], e => `<tr><td>${esc(dt(e.at))}<small>${esc({request:"需求受理",lead:"线索",review:"客户协作",publication:"客户发布",project:"交付操作"}[e.source] || "未记录")}</small></td><td>${esc(hqEvent[e.action] || e.action)}</td><td>${link(obj(targets[e.source], ["review","publication"].includes(e.source) ? e.project_id : e.object_id,e.tenant_id), e.client_name === "客户未记录" ? e.object_id : e.client_name)}<small>${esc(e.tenant_id)}</small></td><td>${esc(roles[e.role] || e.role || "未记录")}<small>${esc(e.note)}</small></td></tr>`);
    }
  }
  async function hqLeadDetail(id, token) {
    const [lead,data] = await Promise.all([api("GET", "/leads/" + encodeURIComponent(id)), api("GET","/hq/workspace")]);
    if (token !== epoch || !session) return;
    const choices = {"HQ-INTAKE":"总部直管（先建档，需求仍须确认）", ...Object.fromEntries(data.tenants.filter(t=>t.assignable).map(t=>[t.tenant_id,t.tenant_id]))};
    shell("leads", heading(lead.contact.company || lead.contact.name || "官网线索", id, link(backTo("leads"),"返回线索队列","btn ghost")) + card("线索与需求", `<dl>${row("所属范围",esc(lead.tenant_id))}${row("状态",chip(lead.intake_status))}${row("联系人",esc(lead.contact.name))}${row("邮箱",esc(lead.contact.email))}${row("网站",website(lead.contact.domain))}${row("业务需求",esc(lead.message))}${row("来源",esc(lead.source)+" · "+esc(dt(lead.created_at)))}</dl><div class="toolbar">${lead.client_id?link(obj("client",lead.client_id,lead.tenant_id),"进入关联客户","btn ghost"):""}${lead.request_id?link(obj("request",lead.request_id,lead.tenant_id),"进入关联需求","btn ghost"):""}${lead.project_id?link(obj("project",lead.project_id,lead.tenant_id),"进入关联项目","btn ghost"):""}</div>`) + card("分配与后续处理", `<div id="hq-lead-msg"></div>${["new","pending_assignment","hq_managed"].includes(lead.intake_status) && !lead.client_id ? `<form id="hq-assign-form">${field("hq-assign-tenant","选择接收渠道",`<select id="hq-assign-tenant">${opts(choices, "")}</select>`)}${field("hq-client-name","客户名称",input("hq-client-name",lead.contact.company || lead.contact.name,'required maxlength="200"'))}<p>确认后在所选渠道建档；重复提交返回原关联，不重复建客户。不会立即创建项目。</p><button class="btn">确认分配并建档</button></form>` : notice("此线索已经分配或建档，不能重复改派。")}${lead.client_id && !lead.request_id ? '<button class="btn ghost" id="hq-convert">创建待确认需求</button>' : ""}`));
    if ($("hq-assign-form")) $("hq-assign-form").onsubmit = async e => {
      e.preventDefault(); const b=e.submitter, target=$("hq-assign-tenant").value;
      if(!confirm(`确认把“${$("hq-client-name").value}”分配到“${choices[target]}”并建档？`)) return;
      b.disabled=true;
      try { await api("POST","/leads/"+encodeURIComponent(id)+"/assign",{tenant_id:target,create_client:true,client_name:$("hq-client-name").value}); dirty=false; route(); }
      catch(err) {error("hq-lead-msg",err);b.disabled=false;}
    };
    if ($("hq-convert")) $("hq-convert").onclick = async e => {
      if(!confirm("根据原线索创建待总部确认需求？批准前不会创建正式项目。"))return;
      e.target.disabled=true;
      try {const r=await api("POST","/leads/"+encodeURIComponent(id)+"/convert",{business_question:lead.message});dirty=false;location.hash=obj("request",r.request_id,r.tenant_id);}
      catch(err){error("hq-lead-msg",err);e.target.disabled=false;}
    };
  }

  async function dashboard(token) {
    const [cs, ps, rs] = await Promise.all([
      api("GET", "/clients"),
      api("GET", "/projects"),
      api("GET", "/requests"),
    ]);
    if (token !== epoch) return;
    const needs = rs.filter((r) => r.status === "clarification_required"),
      pending = rs.filter((r) =>
        [
          "submitted",
          "intake_review",
          "scoping",
          "scope_pending_approval",
        ].includes(r.status),
      );
    const running = ps.filter((p) =>
      ["in_execution", "qa", "rework", "blocked", "changes_requested"].includes(
        p.status,
      ),
    );
    shell(
      "dashboard",
      heading(
        "工作台",
        "查看待处理事项，继续客户交付。",
        writer()
          ? link("#/client/new", "新建客户", "btn ghost") +
              link("#/request/new", "提交需求", "btn")
          : "",
      ) +
        `<div class="kpi-grid">${[
          ["待补充资料", needs.length],
          ["待总部确认", pending.length],
          ["进行中项目", running.length],
          ["客户总数", cs.length],
        ]
          .map(
            ([s, n]) =>
              `<div class="card kpi-card"><span class="muted">${s}</span><strong>${n}</strong></div>`,
          )
          .join("")}</div>` +
        card(
          "待处理需求",
          rs.length
            ? '<div id="dash-req"></div>'
            : empty(
                "从建立第一位客户开始。",
                writer() ? "#/client/new" : "",
                "新建客户",
              ),
        ) +
        card("最近项目", '<div id="dash-proj"></div>'),
    );
    rs.forEach((r) => (r.client_name = name(r.client_id, cs)));
    ps.forEach((p) => (p.client_name = name(p.client_id, cs)));
    list(
      "dash-req",
      [...needs, ...pending],
      ["需求", "客户", "状态", "更新"],
      reqRow,
    );
    list(
      "dash-proj",
      ps
        .slice()
        .sort((a, b) => b.updated_at.localeCompare(a.updated_at))
        .slice(0, 8),
      ["项目", "客户", "项目状态", "服务阶段", "更新"],
      projRow,
    );
  }
  async function clients(token) {
    const cs = await api("GET", "/clients");
    if (token !== epoch) return;
    shell(
      "clients",
      heading(
        "我的客户",
        "从客户进入需求、项目和报告。",
        writer() ? link("#/client/new", "新建客户", "btn") : "",
      ) + card("客户列表", '<div id="clients-list"></div>'),
    );
    list(
      "clients-list",
      cs,
      ["客户", "网站", "行业", "状态"],
      (c) =>
        `<tr><td>${link("#/client/" + c.client_id, c.name)}</td><td>${website(c.website)}</td><td>${esc(c.industry || "未提供")}</td><td>${c.is_active ? "启用" : "停用"}</td></tr>`,
    );
  }
  function newClient() {
    if (!writer()) {
      shell("clients", notice("当前角色不能创建客户。"));
      return;
    }
    shell(
      "clients",
      heading("新建客户", "创建后可直接提交服务需求。") +
        card(
          "客户资料",
          `<form id="client-form" novalidate><div id="client-msg"></div><div class="form-grid">${field("c-name", "客户名称 *", input("c-name", "", 'required maxlength="200"'))}${field("c-industry", "行业", input("c-industry", "", 'maxlength="100"'))}${field("c-web", "网站", input("c-web", "", 'type="url" maxlength="500" placeholder="https://example.com"'))}${field("c-email", "联系邮箱", input("c-email", "", 'type="email" maxlength="200"'))}</div><div class="toolbar"><button class="btn">创建客户</button>${link(draft ? "#/request/new" : "#/clients", "取消", "btn ghost")}</div></form>`,
        ),
    );
    $("client-form").onsubmit = async (e) => {
      e.preventDefault();
      let invalid = null;
      ["c-name", "c-web", "c-email"].forEach(
        (id) => ($(id + "-error").textContent = ""),
      );
      if (!$("c-name").value.trim()) {
        $("c-name-error").textContent = "请填写客户名称";
        invalid = $("c-name");
      }
      if ($("c-web").value && !/^https?:\/\//i.test($("c-web").value)) {
        $("c-web-error").textContent = "网站须以 http:// 或 https:// 开头";
        invalid ||= $("c-web");
      }
      if (!$("c-email").validity.valid) {
        $("c-email-error").textContent = "请填写有效邮箱";
        invalid ||= $("c-email");
      }
      if (invalid) {
        invalid.focus();
        return;
      }
      const b = e.submitter;
      b.disabled = true;
      try {
        const c = await api("POST", "/clients", {
          name: $("c-name").value.trim(),
          industry: $("c-industry").value.trim(),
          website: $("c-web").value.trim(),
          contact_email: $("c-email").value.trim(),
        });
        if (draft) {
          draft.client_id = c.client_id;
          location.hash = "#/request/new";
        } else location.hash = "#/client/" + c.client_id;
      } catch (err) {
        error("client-msg", err);
      } finally {
        b.disabled = false;
      }
    };
  }
  async function clientDetail(id, token) {
    const [c, ps, rs] = await Promise.all([
      api("GET", scoped("/clients/" + encodeURIComponent(id))),
      api("GET", scoped("/projects")),
      api("GET", scoped("/requests")),
    ]);
    if (token !== epoch) return;
    shell(
      "clients",
      heading(
        c.name,
        "客户档案",
        writer()
          ? link(
              "#/request/new?client=" + encodeURIComponent(id),
              "为此客户提交需求",
              "btn",
            )
          : "",
      ) +
        card(
          "基本资料",
          `<dl>${row("网站", website(c.website))}${row("行业", esc(c.industry || "未提供"))}${row("邮箱", esc(c.contact_email || "未提供"))}${row("状态", c.is_active ? "启用" : "停用")}</dl>`,
        ) +
        card("关联需求", '<div id="client-req"></div>') +
        card(
          "GEO 效果、项目与报告",
          '<p class="muted">选择项目查看 GEO 效果、历史批次与交付报告。</p><div id="client-proj"></div><div id="client-geo-links"></div>',
        ),
    );
    list(
      "client-req",
      rs.filter((r) => r.client_id === id),
      ["需求", "客户", "状态", "更新"],
      reqRow,
    );
    list(
      "client-proj",
      ps.filter((p) => p.client_id === id),
      ["项目", "客户", "项目状态", "服务阶段", "更新"],
      projRow,
    );
    $("client-geo-links").innerHTML = ps
      .filter((p) => p.client_id === id)
      .map((p) =>
        link(
          obj("geo", p.project_id, p.tenant_id),
          "查看 GEO 效果 · " + (services[p.service] || p.project_id),
          "btn ghost",
        ),
      )
      .join(" ");
  }
  async function projects(token) {
    const [ps, rs, cs] = await Promise.all([
      api("GET", "/projects"),
      api("GET", "/requests"),
      api("GET", "/clients"),
    ]);
    if (token !== epoch) return;
    rs.forEach((r) => (r.client_name = name(r.client_id, cs)));
    ps.forEach((p) => (p.client_name = name(p.client_id, cs)));
    shell(
      "projects",
      heading(
        session.is_hq ? "需求受理与项目" : "需求与项目",
        "需求经总部确认后进入正式项目。",
        writer() ? link("#/request/new", "提交需求", "btn") : "",
      ) +
        card("待确认需求", '<div id="req-list"></div>') +
        card("交付项目", '<div id="proj-list"></div>') +
        card("已处理需求", '<div id="req-history"></div>'),
    );
    const closed = (r) =>
      ["approved", "rejected", "cancelled", "delivered", "accepted"].includes(
        r.status,
      );
    list(
      "req-list",
      rs.filter((r) => !closed(r)),
      ["需求", "客户", "状态", "更新"],
      reqRow,
      {
        submitted: "待总部确认",
        clarification_required: "待补充",
        intake_review: "受理中",
        scope_pending_approval: "待批准",
      },
    );
    list(
      "req-history",
      rs.filter(closed),
      ["需求", "客户", "状态", "更新"],
      reqRow,
      { approved: "已批准", rejected: "未受理" },
    );
    list(
      "proj-list",
      ps,
      ["项目", "客户", "项目状态", "服务阶段", "更新"],
      projRow,
      {
        approved: "待启动",
        in_execution: "进行中",
        blocked: "受阻",
        delivered: "已交付",
        accepted: "已验收",
      },
    );
  }
  function collect() {
    if (!draft) return;
    if ($("d-client"))
      Object.assign(draft, {
        client_id: $("d-client").value,
        service: $("d-service").value,
        business_question: $("d-question").value,
        target_products: $("d-products")
          .value.split(/[,，]/)
          .map((s) => s.trim())
          .filter(Boolean),
      });
    if ($("d-market"))
      Object.assign(draft, {
        market_scope: $("d-market").value,
        service_duration: $("d-duration").value,
        target_market: [
          ...new Set(
            [...document.querySelectorAll('[name="country"]:checked')]
              .map((x) => x.value)
              .concat(
                $("custom-country")
                  .value.split(/[,，]/)
                  .map((x) => x.trim().toUpperCase())
                  .filter(Boolean),
              ),
          ),
        ],
        target_languages: [
          ...new Set(
            [...document.querySelectorAll('[name="language"]:checked')]
              .map((x) => x.value)
              .concat(
                $("custom-language")
                  .value.split(/[,，]/)
                  .map((x) => x.trim())
                  .filter(Boolean),
              ),
          ),
        ],
      });
  }
  function picker(kind, items, selected) {
    const entries = Array.isArray(items)
      ? items.map((s) => [s, s])
      : Object.entries(items).map(([v, s]) => [v, v + " · " + s]);
    return `<div class="picker"><input type="search" id="search-${kind}" aria-label="搜索${kind === "country" ? "国家/地区" : "语言"}" placeholder="搜索选项"><div class="picker-options" id="options-${kind}">${entries.map(([v, s]) => `<label><input type="checkbox" name="${kind}" value="${esc(v)}" ${selected.includes(v) ? "checked" : ""}>${esc(s)}</label>`).join("")}</div><p class="selected" id="selected-${kind}"></p></div>`;
  }
  function bindPicker(kind) {
    $("search-" + kind).oninput = (e) =>
      document
        .querySelectorAll("#options-" + kind + " label")
        .forEach(
          (l) =>
            (l.hidden = !l.textContent
              .toLowerCase()
              .includes(e.target.value.toLowerCase())),
        );
    const update = () =>
      ($("selected-" + kind).textContent =
        "已选：" +
        ([...document.querySelectorAll(`[name="${kind}"]:checked`)]
          .map((x) => x.value)
          .join("、") || "暂无"));
    document
      .querySelectorAll(`[name="${kind}"]`)
      .forEach((x) => (x.onchange = update));
    update();
  }
  async function newRequest(token, client) {
    if (!writer()) {
      shell("projects", notice("当前角色不能提交需求。"));
      return;
    }
    const cs = await api("GET", "/clients");
    if (token !== epoch) return;
    if (!draft) {
      draft = {
        client_id: client || "",
        service: "diagnosis",
        business_question: "",
        target_products: [],
        market_scope: "global",
        target_market: [],
        target_languages: [],
        service_duration: "to_be_determined",
        _key: Array.from(crypto.getRandomValues(new Uint32Array(4)), (v) =>
          v.toString(16).padStart(8, "0"),
        ).join(""),
      };
      step = 1;
    }
    const active = cs.filter((c) => c.is_active);
    if (!active.length) {
      shell(
        "projects",
        heading("提交服务需求") +
          empty(
            "请先建立客户档案，再继续本次需求。",
            "#/client/new",
            "创建客户",
          ),
      );
      return;
    }
    function draw(errors = {}) {
      const steps = ["客户与服务", "市场与语言", "核对并提交"];
      let html = "";
      if (step === 1)
        html = `<div class="form-grid">${field("d-client", "客户 *", `<select id="d-client"><option value="">请选择客户</option>${opts(Object.fromEntries(active.map((c) => [c.client_id, c.name])), draft.client_id)}</select>`, errors.client)}${field("d-service", "服务类型 *", `<select id="d-service">${opts(Object.fromEntries(Object.entries(services).filter(([k]) => !["visibility_audit", "remeasurement"].includes(k))), draft.service)}</select>`)}</div>${link("#/client/new", "＋ 新建客户")}${field("d-question", "希望解决的业务问题 *", area("d-question", draft.business_question, 'maxlength="3000" placeholder="例如：品牌在美国买家的 AI 搜索中为何很少出现"'), errors.question)}${field("d-products", "目标产品 / 服务", input("d-products", draft.target_products.join("，"), 'placeholder="多个产品用逗号分隔"'))}`;
      if (step === 2)
        html = `<div class="form-grid">${field("d-market", "市场范围", `<select id="d-market">${opts({ global: "全球市场", single: "单一国家/地区", multi: "多个国家/地区" }, draft.market_scope)}</select>`, errors.market)}${field("d-duration", "期望服务期限", `<select id="d-duration">${opts(durations, draft.service_duration)}</select>`)}</div><p class="muted">期望期限须经总部确认；全球市场允许不逐国选择。</p><fieldset><legend>目标国家 / 地区</legend>${picker("country", countries, draft.target_market)}${field("custom-country", "其他国家/地区代码", input("custom-country", draft.target_market.filter((v) => !countries[v]).join(", "), 'placeholder="例如：SE, NO"'), errors.country)}</fieldset><fieldset><legend>目标语言</legend>${picker("language", languages, draft.target_languages)}${field("custom-language", "其他目标语言", input("custom-language", draft.target_languages.filter((v) => !languages.includes(v)).join(", "), 'placeholder="多个语言用逗号分隔"'))}</fieldset>`;
      if (step === 3)
        html =
          notice(
            "提交后进入总部受理。报价、最终范围和周期尚未确认；批准后才创建正式项目。",
          ) +
          `<dl>${row("客户", esc(name(draft.client_id, cs)))}${row("服务", esc(services[draft.service]))}${row("业务问题", esc(draft.business_question))}${row("目标产品", esc(draft.target_products.join("、") || "待确认"))}${row("市场范围", esc({ global: "全球市场", single: "单一市场", multi: "多个市场" }[draft.market_scope]))}${row("国家 / 地区", esc(draft.target_market.join("、") || "全球市场，待总部细化"))}${row("语言", esc(draft.target_languages.join("、") || "待确认"))}${row("期望期限", esc(durations[draft.service_duration]))}</dl>`;
      shell(
        "projects",
        heading("提交服务需求", "三步提交，返回上一步会保留输入。") +
          `<ol class="steps">${steps.map((s, i) => `<li ${step === i + 1 ? 'class="current" aria-current="step"' : ""}><span>${i + 1}</span>${s}</li>`).join("")}</ol>` +
          card(
            steps[step - 1],
            `<form id="draft-form" novalidate><div id="draft-msg" aria-live="polite"></div>${html}<div class="toolbar"><button type="button" class="btn ghost" id="prev">${step === 1 ? "取消" : "上一步"}</button><button class="btn" id="next">${step === 3 ? "提交需求" : "下一步"}</button></div></form>`,
          ),
      );
      if (step === 2) {
        bindPicker("country");
        bindPicker("language");
      }
      $("draft-form").oninput = () => (dirty = true);
      $("prev").onclick = () => {
        collect();
        if (step > 1) {
          step--;
          draw();
        } else if (!dirty || confirm("离开将放弃未提交的需求，确定离开？")) {
          dirty = false;
          draft = null;
          location.hash = "#/projects";
        }
      };
      $("draft-form").onsubmit = async (e) => {
        e.preventDefault();
        collect();
        const errors = {};
        if (step === 1) {
          if (!draft.client_id) errors.client = "请选择客户";
          if (!draft.business_question.trim())
            errors.question = "请填写希望解决的问题";
        }
        if (step === 2) {
          if (
            draft.market_scope === "single" &&
            draft.target_market.length !== 1
          )
            errors.market = "单一市场请准确选择一个国家/地区";
          if (draft.market_scope === "multi" && draft.target_market.length < 2)
            errors.market = "多个市场至少选择两个国家/地区";
          if (draft.target_market.some((s) => !/^[A-Z]{2}$/.test(s)))
            errors.country = "请使用两位字母国家/地区代码";
        }
        if (Object.keys(errors).length) {
          draw(errors);
          $(
            errors.client
              ? "d-client"
              : errors.question
                ? "d-question"
                : errors.market
                  ? "d-market"
                  : "custom-country",
          ).focus();
          return;
        }
        if (step < 3) {
          step++;
          draw();
          return;
        }
        const b = $("next");
        b.disabled = true;
        try {
          const { _key, ...body } = draft;
          const r = await api("POST", "/requests", body, {
            "Idempotency-Key": _key,
          });
          dirty = false;
          draft = null;
          step = 1;
          location.hash = "#/request/" + r.request_id;
        } catch (err) {
          error("draft-msg", err);
        } finally {
          b.disabled = false;
        }
      };
    }
    draw();
  }
  async function requestDetail(id, token) {
    const r = await api("GET", scoped("/requests/" + encodeURIComponent(id)));
    const c = await api(
      "GET",
      scoped(
        "/clients/" + encodeURIComponent(r.client_id),
        session.is_hq ? r.tenant_id : "",
      ),
    );
    if (token !== epoch) return;
    const wf = r.workflow || {},
      bc = r.business_context || {},
      scope = wf.scope,
      closed = [
        "approved",
        "rejected",
        "cancelled",
        "delivered",
        "accepted",
      ].includes(r.status);
    let controls = "";
    if (!closed && session.is_hq)
      controls = `<form id="scope-form"><div class="form-grid">${field("scope-summary", "确认服务范围 *", area("scope-summary", scope?.summary || "", 'required maxlength="3000"'))}${field("scope-duration", "确认周期 *", input("scope-duration", scope?.confirmed_duration || "", 'required maxlength="200" placeholder="例如：资料齐备后 3 个工作日"'))}</div>${field("scope-deliverables", "交付物 *（每行一项）", area("scope-deliverables", (scope?.deliverables || []).join("\n"), "required"))}${field("scope-exclusions", "排除项（每行一项）", area("scope-exclusions", (scope?.exclusions || []).join("\n")))}<button class="btn ghost" ${r.status === "clarification_required" ? "disabled" : ""}>保存确认范围</button></form><hr>${field("review-note", "补充要求 / 拒绝原因", area("review-note"))}<div class="toolbar"><button class="btn ghost" data-action="clarification">要求补充资料</button>${session.role === "HQ_MANAGEMENT" ? `<button class="btn" data-action="approve" ${r.status !== "scope_pending_approval" ? "disabled" : ""}>批准并创建项目</button><button class="btn danger" data-action="reject">拒绝需求</button>` : '<p class="muted">范围保存后，由总部管理角色批准。</p>'}</div>`;
    if (r.status === "clarification_required" && (writer() || (session.is_hq && r.tenant_id === "HQ-INTAKE")))
      controls =
        notice((r.clarification_request?.questions || []).join("；")) +
        `<form id="supplement-form">${field("supplement", "补充资料 *", area("supplement", "", 'required maxlength="3000"'))}<button class="btn">提交补充</button></form>`;
    shell(
      "projects",
      heading(
        services[r.service] || "服务需求",
        id,
        link(session.is_hq ? backTo("requests") : "#/projects", "返回列表", "btn ghost"),
      ) +
        card(
          "受理状态",
          chip(r.status) +
            (r.project_id
              ? link(
                  obj("project", r.project_id, r.tenant_id),
                  "进入关联项目",
                  "btn ghost",
                )
              : "") +
            (r.status === "rejected"
              ? notice(wf.rejection_reason || "总部未受理此需求", "warn")
              : "") +
            `<p class="muted">${r.project_id ? "需求已确认，交付状态请进入项目查看。" : "总部批准前不会创建正式项目。"}</p>`,
        ) +
        card(
          "客户需求",
          `<dl>${row("客户", link(obj("client", c.client_id, r.tenant_id), c.name))}${row("业务问题", esc(bc.business_question || "未记录"))}${row("目标产品", esc((bc.target_products || []).join("、") || "待确认"))}${row("国家 / 地区", esc((bc.target_market || []).join("、") || "全球市场或待细化"))}${row("语言", esc((bc.target_languages || []).join("、") || "待确认"))}${row("期望期限", esc(durations[bc.service_duration] || "待确认"))}${wf.supplement ? row("补充资料", esc(wf.supplement)) : ""}</dl>`,
        ) +
        card(
          "总部确认结果",
          scope
            ? `<dl>${row("范围", esc(scope.summary))}${row("确认周期", esc(scope.confirmed_duration))}${row("交付物", esc(scope.deliverables.join("；")))}${row("排除项", esc(scope.exclusions.join("；") || "无"))}${row("批准时间", esc(dt(scope.approved_at)))}</dl>`
            : empty("服务范围尚未确认。"),
        ) +
        (controls
          ? card(
              "处理需求",
              '<div id="review-msg" aria-live="polite"></div>' + controls,
            )
          : "") +
        card(
          "处理记录",
          wf.history?.length
            ? `<ol class="timeline">${wf.history.map((h) => `<li><strong>${esc(actions[h.action] || h.action)}</strong> · ${esc(roles[h.role] || h.role)}<small>${esc(dt(h.at))}</small><p>${esc(h.note)}</p></li>`).join("")}</ol>`
            : empty("历史需求未记录受理过程。"),
        ),
    );
    let scopeEdited = false;
    async function send(action, extra = {}) {
      const buttons = [...document.querySelectorAll("#view button")];
      buttons.forEach((b) => (b.disabled = true));
      try {
        await api(
          "POST",
          scoped("/requests/" + encodeURIComponent(id) + "/" + action, r.tenant_id),
          { revision: wf.revision || 0, ...extra },
        );
        dirty = false;
        route();
      } catch (e) {
        error("review-msg", e);
        buttons.forEach((b) => (b.disabled = false));
        const approve = document.querySelector('[data-action="approve"]');
        if (approve) approve.disabled = r.status !== "scope_pending_approval" || scopeEdited;
        if ($("scope-form"))
          $("scope-form").querySelector("button").disabled =
            r.status === "clarification_required";
      }
    }
    if ($("scope-form"))
      $("scope-form").oninput = () => {
        scopeEdited = true;
        const b = document.querySelector('[data-action="approve"]');
        if (b) b.disabled = true;
      };
    if ($("scope-form"))
      $("scope-form").onsubmit = (e) => {
        e.preventDefault();
        const lines = (id) =>
          $(id)
            .value.split("\n")
            .map((s) => s.trim())
            .filter(Boolean);
        send("scope", {
          scope: {
            summary: $("scope-summary").value,
            confirmed_duration: $("scope-duration").value,
            deliverables: lines("scope-deliverables"),
            exclusions: lines("scope-exclusions"),
          },
        });
      };
    document.querySelectorAll("[data-action]").forEach(
      (b) =>
        (b.onclick = () => {
          const action = b.dataset.action,
            note = $("review-note").value.trim();
          if (action !== "approve" && !note) {
            $("review-note-error").textContent = "请填写说明";
            $("review-note").focus();
            return;
          }
          if (
            action === "approve" &&
            !confirm("确认按已保存的范围和周期批准，并创建正式项目？")
          )
            return;
          send(action, { note });
        }),
    );
    if ($("supplement-form"))
      $("supplement-form").onsubmit = (e) => {
        e.preventDefault();
        send("supplement", { note: $("supplement").value });
      };
  }
  async function projectDetail(id, token) {
    const p = await api("GET", scoped("/projects/" + encodeURIComponent(id)));
    const [st, rp, cl] = await Promise.allSettled([
      api("GET", scoped("/projects/" + encodeURIComponent(id) + "/stage")),
      api("GET", scoped("/reports?project_id=" + encodeURIComponent(id))),
      api("GET", scoped("/clients/" + encodeURIComponent(p.client_id))),
    ]);
    if (token !== epoch || !session) return;
    const rs = rp.status === "fulfilled" ? rp.value : [];
    rs.sort((a, b) => b.created_at.localeCompare(a.created_at));
    const scope = p.request_summary?.scope;
    const reports =
      rp.status === "rejected"
        ? notice("报告读取失败，请重试；这不代表报告尚未生成。", "err") +
          '<button class="btn ghost" id="reports-retry">重试读取报告</button>'
        : rs.length
          ? `<ul class="report-list">${rs.map((r) => `<li>${link(obj("report", r.report_id, p.tenant_id), reportTitle(r))}<small>${esc(r.report_id)} · v${esc(r.version)} · ${esc(dt(r.created_at))}</small></li>`).join("")}</ul>`
          : empty("报告尚未生成。总部完成交付后将在这里展示。");
    const stages =
      st.status === "fulfilled"
        ? Object.values(st.value.stages || {})
            .map(
              (s) =>
                `<li><strong>${esc(s.stage_label || s.label || s.stage)}</strong>${chip(s.status)}<small>${esc(dt(s.completed_at || s.started_at))}</small></li>`,
            )
            .join("")
        : "";
    const findings = rs[0]?.key_findings || p.key_findings || [];
    shell(
      "projects",
      heading(
        services[p.service] || "GEO 服务项目",
        id,
        link(obj("geo", id, p.tenant_id), "查看 GEO 效果与依据", "btn") +
          link(backTo("projects"), "返回列表", "btn ghost"),
      ) +
        (state.deliveryFlash?.project === id ? notice(state.deliveryFlash.text) : "") +
        card(
          "项目概况",
          `<dl>${row("客户", cl.status === "fulfilled" ? link(obj("client", p.client_id, p.tenant_id), cl.value.name) : esc(p.client_id) + "（资料暂不可用）")}${row("项目状态", chip(p.status))}${row("服务阶段", esc(p.service_stage_label))}${row("阶段完成比例", esc(p.stage_progress) + "%（不代表项目已验收）")}${row("最近更新", esc(dt(p.updated_at)))}${row("关联需求", link("#/request/" + p.request_id, p.request_id))}</dl>${p.blocked_reason ? notice("阻塞原因：" + p.blocked_reason.reason + "；需要：" + p.blocked_reason.required_action, "warn") : ""}`,
        ) +
        card(
          "已确认范围",
          scope
            ? `<p>${esc(scope.summary)}</p><p>确认周期：${esc(scope.confirmed_duration)}</p><p>交付物：${esc(scope.deliverables.join("；"))}</p>`
            : empty("历史项目未记录总部确认快照，请与总部核对服务范围。"),
        ) +
        card(
          "服务阶段",
          stages
            ? `<ol class="stage-list">${stages}</ol>`
            : notice("阶段信息暂不可用，请稍后重试。", "warn"),
        ) +
        card("交付报告", reports) +
        card(
          "关键发现与下一步",
          findings.length
            ? `<ul>${findings.map((f) => `<li>${esc(typeof f === "string" ? f : f.statement || f.title || "")}${f.recommendation ? `<p class="muted">建议：${esc(f.recommendation)}</p>` : ""}</li>`).join("")}</ul>`
            : empty(
                rp.status === "rejected"
                  ? "报告未能读取，关键发现暂不可用。"
                  : "尚无已发布的关键发现。",
              ),
        ) +
        card(
          "客户协作与结果发布",
          '<div id="client-collaboration" role="status">正在读取客户协作记录…</div>',
        ) +
        (session.is_hq
          ? card(
              "总部交付操作",
              `<div id="delivery-msg"></div><form id="hq-operation-form"><div class="toolbar">${Object.entries(hqOps).filter(([k])=>!["block","resume"].includes(k)).map(([k,v])=>`<button type="button" class="btn ghost" data-hq-operation="${k}" ${k === "start" ? p.status !== "approved" ? "disabled" : "" : p.status !== "in_execution" || (k === "advance" && p.service_stage === "effect_monitoring") ? "disabled" : ""}>${v}</button>`).join("")}</div>${field("hq-operation-note","阻塞原因 / 恢复说明",area("hq-operation-note","",'maxlength="3000"'))}${field("hq-required-action","阻塞时需要完成的行动",area("hq-required-action","",'maxlength="1000"'))}${field("hq-block-owner","阻塞处理方",`<select id="hq-block-owner">${opts({HQ:"总部",DISTRIBUTOR:"渠道商",CLIENT:"客户"},"HQ")}</select>`)}<div class="toolbar"><button type="button" class="btn ghost" data-hq-operation="block" ${p.status !== "in_execution" ? "disabled" : ""}>登记阻塞</button><button type="button" class="btn ghost" data-hq-operation="resume" ${p.status !== "blocked" ? "disabled" : ""}>解除阻塞并恢复</button></div></form><hr><button class="btn" data-delivery="deliver">生成现有测量的技术报告</button><p class="muted">范围版本 ${esc(scope?.version || 1)}；沿用此范围版本的报告幂等保护。此操作不自动向终端客户发布，也不将项目标为已验收。无测量或QA未通过会明确失败。</p>`,
            )
          : ""),
    );
    delete state.deliveryFlash;
    if ($("reports-retry")) $("reports-retry").onclick = route;
    loadClientCollaboration(p, rs, token);
    if ($("hq-operation-form")) $("hq-operation-form").onsubmit = e=>e.preventDefault();
    document.querySelectorAll("[data-hq-operation]").forEach(b => {
      const key=freshKey();
      b.onclick=async()=>{
        const action=b.dataset.hqOperation;
        if(!confirm(`确认对“${cl.status === "fulfilled" ? cl.value.name : p.client_id}”执行“${hqOps[action]}”？当前阶段：${p.service_stage_label}。`))return;
        const payload={action,expected_updated_at:p.updated_at,note:$("hq-operation-note").value,required_action:$("hq-required-action").value,owner:$("hq-block-owner").value};
        const buttons=[...document.querySelectorAll("[data-hq-operation]")]; const disabled=buttons.map(x=>x.disabled);buttons.forEach(x=>x.disabled=true);
        try {await api("POST",scoped("/hq/projects/"+encodeURIComponent(id)+"/operation"),payload,{"Idempotency-Key":key}); dirty=false;if(token===epoch)route();}
        catch(e){if(token===epoch){error("delivery-msg",e);buttons.forEach((x,i)=>x.disabled=disabled[i]);}}
      };
    });
    document.querySelectorAll("[data-delivery]").forEach(
      (b) =>
        (b.onclick = async () => {
          if (!confirm("确认根据本项目已有测量生成技术报告？不会自动向终端客户发布。")) return;
          b.disabled = true;
          try {
            const delivery = await api(
              "POST",
              scoped(
                "/projects/" +
                  encodeURIComponent(id) +
                  "/" +
                  b.dataset.delivery,
              ),
              b.dataset.delivery === "deliver"
                ? { scope_version: scope?.version || 1 }
                : {},
            );
            if (delivery.status === "QA_FAILED" || delivery.qa_result?.passed === false) throw new Error("报告已生成但质量检查未通过，不能视为成功交付；请核对测量与报告内容。");
            state.deliveryFlash = {project:id,text:delivery.status === "ALREADY_DELIVERED" ? "此范围版本已有报告，本次返回原报告，未重复生成；客户可见性请另行核对。" : "技术报告已生成，尚不代表向客户发布或项目已验收。"};
            dirty=false;
            if(token===epoch) route();
          } catch (e) {
            if(token!==epoch)return;
            error("delivery-msg", e);
            b.disabled = false;
          }
        }),
    );
  }
  async function loadClientCollaboration(p, reports, token) {
    const host = $("client-collaboration");
    if (!host) return;
    try {
      const [pubs, reviews] = await Promise.all([
        api(
          "GET",
          scoped(
            "/client-publications?project_id=" +
              encodeURIComponent(p.project_id),
          ),
        ),
        api(
          "GET",
          scoped(
            "/client-reviews?project_id=" + encodeURIComponent(p.project_id),
          ),
        ),
      ]);
      if (token !== epoch || !session || !$("client-collaboration")) return;
      const manage = writer() || session.is_hq;
      const reviewStatus = {
        pending: "待客户处理",
        submitted: "客户已答复",
        confirmed: "客户已确认",
        changes_requested: "客户要求修改",
        closed: "已处理关闭",
        withdrawn: "已撤回",
      };
      $("client-collaboration").innerHTML =
        `<p>客户只能看到总部明确发布的版本。客户确认意见不会自动验收项目。</p><div id="collab-msg"></div><h3>结果发布</h3>${pubs.length ? `<ul>${pubs.map((r) => `<li>${esc(reports.find((x) => x.report_id === r.report_id)?.title || "交付报告")} · ${r.currently_visible ? "客户可见" : r.status === "withdrawn" ? "已撤回" : "不可见（来源已变更）"}${session.is_hq && r.status === "published" ? ` <button class="btn ghost" data-withdraw-publication="${esc(r.publication_id)}">撤回客户可见版本</button>` : ""}</li>`).join("")}</ul>` : empty("尚无明确向客户发布的报告。")}${session.is_hq && reports.length ? `<label for="publish-report">选择已有报告<select id="publish-report">${reports.map((r) => `<option value="${esc(r.report_id)}">${esc(reportTitle(r))} · v${r.version} · ${esc(dt(r.created_at))}</option>`).join("")}</select></label><button class="btn ghost" id="publish-to-customer">审查并向客户发布</button>` : ""}<h3>客户待办</h3>${reviews.length ? reviews.map((r) => `<article class="customer-review"><h4>${esc(r.title)} · ${esc(reviewStatus[r.status] || r.status)}</h4><p>${esc(r.instructions)}</p>${r.response ? `<p>客户答复：${esc(r.response.note)}</p>` : ""}${r.resolution ? `<p>处理说明：${esc(r.resolution)}</p>` : ""}<details><summary>处理历史</summary><ol>${r.history.map((e) => `<li>${esc(dt(e.at))} · ${esc(e.by)} · ${esc(hqEvent[e.action] || e.action)}<p>${esc(e.note)}</p></li>`).join("")}</ol></details>${manage && !["closed", "withdrawn"].includes(r.status) ? `<form data-process-review="${esc(r.review_id)}"><label>处理方式<select name="action">${r.status !== "pending" ? '<option value="close">处理并关闭</option><option value="reopen">补充说明并重新请求客户确认</option>' : ""}<option value="withdraw">撤回待办</option></select></label><label>客户可见处理说明<textarea name="note" required maxlength="3000"></textarea></label><button class="btn ghost">保存处理结果</button></form>` : ""}</article>`).join("") : empty("暂无客户待办。")}${
          manage
            ? `<details><summary>发布新的客户待办</summary><form id="create-client-review"><label for="review-kind">待办类型<select id="review-kind"><option value="material_request">资料请求</option><option value="content_review">内容确认</option><option value="report_feedback">报告反馈</option></select></label><label for="review-title">客户可见标题<input id="review-title" required maxlength="160"></label><label for="review-instructions">客户可见说明<textarea id="review-instructions" required maxlength="3000"></textarea></label><label for="review-report">关联已发布报告（报告反馈必选）<select id="review-report"><option value="">不关联报告</option>${pubs
                .filter((x) => x.currently_visible)
                .map(
                  (x) =>
                    `<option value="${esc(x.report_id)}">${esc(reports.find((r) => r.report_id === x.report_id)?.title || "交付报告")}</option>`,
                )
                .join(
                  "",
                )}</select></label><p class="small muted">不索取密码、密钥。不会发送邮件或自动改变交付状态。</p><button class="btn">向该项目客户发布待办</button></form></details>`
            : ""
        }`;
      async function send(path, body, key, b) {
        b.disabled = true;
        try {
          await api(
            "POST",
            scoped(path),
            body,
            key ? { "Idempotency-Key": key } : {},
          );
          dirty = false;
          if (token === epoch) loadClientCollaboration(p, reports, token);
        } catch (e) {
          error("collab-msg", e);
          b.disabled = false;
        }
      }
      if ($("publish-to-customer"))
        $("publish-to-customer").onclick = (e) => {
          if (confirm("确认审查并向该项目客户发布选中报告？"))
            send(
              "/client-publications",
              { report_id: $("publish-report").value },
              null,
              e.target,
            );
        };
      document.querySelectorAll("[data-withdraw-publication]").forEach(
        (b) =>
          (b.onclick = () => {
            const r = pubs.find(
              (x) => x.publication_id === b.dataset.withdrawPublication,
            );
            if (confirm("撤回后客户将不能查看该版本及其关联结果，确认撤回？"))
              send(
                "/client-publications/" + r.publication_id + "/withdraw",
                { revision: r.revision },
                null,
                b,
              );
          }),
      );
      if ($("create-client-review")) {
        const key =
          "review-" + crypto.getRandomValues(new Uint32Array(4)).join("-");
        $("create-client-review").onsubmit = (e) => {
          e.preventDefault();
          send(
            "/client-reviews",
            {
              project_id: p.project_id,
              kind: $("review-kind").value,
              title: $("review-title").value,
              instructions: $("review-instructions").value,
              report_id: $("review-report").value || null,
            },
            key,
            e.submitter,
          );
        };
      }
      document.querySelectorAll("[data-process-review]").forEach((form) => {
        const key =
          "process-" + crypto.getRandomValues(new Uint32Array(4)).join("-");
        form.onsubmit = (e) => {
          e.preventDefault();
          const r = reviews.find(
            (r) => r.review_id === form.dataset.processReview,
          );
          send(
            "/client-reviews/" + r.review_id + "/process",
            {
              revision: r.revision,
              action: form.elements.action.value,
              note: form.elements.note.value,
            },
            key,
            e.submitter,
          );
        };
      });
    } catch (e) {
      if (token === epoch && $("client-collaboration"))
        $("client-collaboration").innerHTML =
          notice("客户协作读取失败，请重新加载。", "err") +
          '<button class="btn ghost" id="collab-retry">重新读取客户协作</button>';
      if ($("collab-retry"))
        $("collab-retry").onclick = () =>
          loadClientCollaboration(p, reports, token);
    }
  }
  const sourceLabel = (source) =>
    ({
      "fictional-demo": "虚拟构造数据",
      opengeo: "已保存的平台测量数据",
      "geo-collector-db": "已保存的平台测量数据",
      elmo: "已保存的平台测量数据",
    })[source] || "来源待核对";
  const metricLabels = {
    mention_rate: "品牌提及率",
    recommendation_rate: "推荐比例（等级 ≥ 2）",
    citation_rate: "回答引用可用率",
  };
  const percent = (v) => (v == null ? "暂不可用" : `${v}%`);
  function metricCards(b) {
    return `<div class="kpi-grid geo-kpis">${Object.entries(metricLabels)
      .map(
        ([k, label]) =>
          `<section class="card kpi-card"><span>${esc(label)}</span><strong>${percent(b.metrics[k])}</strong><p class="small muted">${esc(b.metric_notes[k])}</p></section>`,
      )
      .join(
        "",
      )}</div><p class="small muted">指标为所选整批结果，不随问题或平台筛选重算。回答引用可用率不等于品牌被引用率；推荐比例不是平台排名。</p>`;
  }
  async function geoDetail(id, token) {
    const g = await api(
      "GET",
      scoped("/projects/" + encodeURIComponent(id) + "/geo"),
    );
    if (token !== epoch || !session) return;
    const s = (state["geo-" + id] ||= { batch: "", engine: "", q: "" });
    const batches = g.batches;
    if (!batches.some((b) => b.measurement_id === s.batch))
      s.batch = batches.at(-1)?.measurement_id || "";
    const reportsResult = await Promise.allSettled([
      api("GET", scoped("/reports?project_id=" + encodeURIComponent(id))),
    ]);
    if (token !== epoch || !session) return;
    const reports =
      reportsResult[0].status === "fulfilled"
        ? reportsResult[0].value.sort((a, b) =>
            b.created_at.localeCompare(a.created_at),
          )
        : null;
    const top = heading(
      "GEO 效果与依据",
      "所属客户的已保存结果；每批独立展示",
      link(obj("project", id, tenant), "返回项目", "btn ghost") +
        link(obj("client", g.client_id, tenant), "返回客户", "btn ghost"),
    );
    shell(
      "projects",
      top +
        (batches.length
          ? `${card("选择测量批次", `<label for="geo-batch">历史批次<select id="geo-batch">${batches.map((b) => `<option value="${esc(b.measurement_id)}" ${s.batch === b.measurement_id ? "selected" : ""}>${esc(dt(b.collected_at))} · ${esc(b.measurement_id)}${b.is_demo ? " · 虚拟" : ""}</option>`).join("")}</select></label>`)}${card("历史表现", `<p class="muted small">各批次独立展示；范围变化时不能把数值直接解释为增长。</p><div class="table-wrap"><table><thead><tr><th>批次时间</th><th>品牌提及率</th><th>推荐比例</th><th>回答引用可用率</th></tr></thead><tbody>${batches.map((b) => `<tr><td>${esc(dt(b.collected_at))}</td><td>${percent(b.metrics.mention_rate)}</td><td>${percent(b.metrics.recommendation_rate)}</td><td>${percent(b.metrics.citation_rate)}</td></tr>`).join("")}</tbody></table></div>`)}<div id="geo-content"></div>`
          : card(
              "GEO 数据",
              empty(
                "尚未采集 GEO 数据。总部发布测量结果后将在此展示；这不代表效果为零。",
              ),
            )) +
        card(
          "报告、发现与下一步",
          reports === null
            ? notice("报告读取失败，可重新加载；不代表尚无报告。", "err") +
                '<button id="geo-report-retry" class="btn ghost">重新加载报告</button>'
            : reports.length
              ? `<ul>${reports.map((r) => `<li>${link(obj("report", r.report_id, r.tenant_id), reportTitle(r))}</li>`).join("")}</ul><p class="small muted">以下发现来自最新发布报告 ${esc(reports[0].report_id)} · ${esc(dt(reports[0].created_at))}，不随所选测量批次变化。</p>${(reports[0]?.key_findings || []).map((f) => `<p>${esc(f.statement)} ${esc(f.recommendation || "")}</p>`).join("")}<p>执行进展见项目阶段；尚无已发布的行动归因或商业转化数据。</p>`
              : empty("暂无已发布报告与建议；不会根据失败样本自动生成结论。"),
        ) +
        card(
          "范围与局限",
          `<ul>${g.limitations.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>`,
        ),
    );
    if ($("geo-report-retry")) $("geo-report-retry").onclick = route;
    if (!batches.length) return;
    function draw() {
      const b = batches.find((b) => b.measurement_id === s.batch),
        ctx = b.context;
      const trend = b.comparison;
      $("geo-content").innerHTML =
        card(
          "本批数据范围",
          `<dl>${row("批次", esc(b.measurement_id))}${row("来源", esc(sourceLabel(b.source)))}${row("样本", `${b.total_samples} 条已保存 · ${b.valid_samples} 条成功且质量通过 · ${b.unavailable_samples} 条不可用`)}${row("观测窗口", esc(b.period || "未完整记录，不能核验"))}${row("市场 / 语言", esc((ctx.market || "未记录") + " / " + (ctx.language || "未记录")))}${row("品牌", esc(ctx.brand || "未记录"))}</dl>`,
        ) +
        metricCards(b) +
        card(
          "与上一批的变化",
          `<p>${esc(trend.note)}</p>${Object.entries(metricLabels)
            .map(
              ([k, label]) =>
                `<p>${esc(label)}：${trend.delta_pp[k] == null ? "不可比较" : `${trend.delta_pp[k] > 0 ? "+" : ""}${trend.delta_pp[k]} 个百分点`}</p>`,
            )
            .join("")}`,
        ) +
        card(
          "问题结果与依据",
          `<div class="list-tools"><label for="geo-engine">平台<select id="geo-engine"><option value="">全部平台</option>${opts(Object.fromEntries([...new Set(b.observations.map((o) => o.engine))].map((e) => [e, e])), s.engine)}</select></label><label for="geo-search">搜索问题<input id="geo-search" type="search" value="${esc(s.q)}"></label></div><p class="muted small">只显示已发布摘要与安全引用；没有摘要不代表没有回答。</p><div id="geo-results"></div>`,
        );
      function results() {
        const found = b.observations.filter(
          (o) =>
            (!s.engine || o.engine === s.engine) &&
            o.prompt_text.toLowerCase().includes(s.q.toLowerCase()),
        );
        const visible = found.slice(0, s.limit || 20);
        $("geo-results").innerHTML =
          `<p role="status">${found.length} 条结果，展示 ${visible.length} 条</p><div class="geo-observations">${visible.map((o) => `<article class="geo-observation"><h3>${esc(o.prompt_text)}</h3><p class="small muted">${esc(o.engine)} · ${esc(dt(o.timestamp))}</p><p class="small muted">问题分类：${esc(o.category || "未发布分类")}</p><p>${o.status === "success" ? "采集成功且质量通过" : "结果不可用"} · 品牌：${o.brand_status === "UNKNOWN" ? "未知" : o.brand_mentioned ? "已提及" : "未提及"} · 推荐等级：${o.recommendation_level == null ? "未知" : o.recommendation_level}</p>${o.reason ? notice(o.reason, "warn") : ""}${o.excerpt ? `<blockquote>${esc(o.excerpt)}</blockquote>` : '<p class="muted">暂无已发布的回答摘要。</p>'}<p>回答引用：${o.citations_status === "extracted" ? "已提取" : "未完整提供"}</p>${o.citations.map((c) => `<a href="${esc(c.url)}" target="_blank" rel="noopener noreferrer">${esc(c.title || c.url)}</a>`).join(" · ")}<p>观察到的竞品：${o.competitors.length ? esc(o.competitors.map((c) => c.name).join("、")) : "未提供（不代表不存在）"}</p></article>`).join("") || empty("没有符合条件的问题结果。")}</div>${found.length > visible.length ? '<button class="btn ghost" id="geo-more">再显示 20 条</button>' : ""}`;
        if ($("geo-more"))
          $("geo-more").onclick = () => {
            s.limit = (s.limit || 20) + 20;
            results();
          };
      }
      $("geo-engine").onchange = (e) => {
        s.engine = e.target.value;
        s.limit = 20;
        results();
      };
      $("geo-search").oninput = (e) => {
        s.q = e.target.value;
        s.limit = 20;
        results();
      };
      results();
    }
    $("geo-batch").onchange = (e) => {
      s.batch = e.target.value;
      s.engine = "";
      s.limit = 20;
      draw();
    };
    draw();
  }
  async function reportDetail(id, token) {
    const r = await api("GET", scoped("/reports/" + encodeURIComponent(id)));
    if (token !== epoch) return;
    const q = r.data_quality || {};
    shell(
      "projects",
      heading(
        "交付报告",
        id,
        link(
          obj("project", r.project_id, r.tenant_id),
          "返回项目",
          "btn ghost",
        ) + '<button class="btn" id="print-report">打印 / 保存 PDF</button>',
      ) +
        `<article class="report-document"><div class="report-brand">GEO 增长系统 · 客户交付报告</div><h1>${esc(reportTitle(r))}</h1><p class="muted">${esc(r.report_id)} · 版本 ${esc(r.version)} · ${esc(dt(r.created_at))}</p>${card("阅读说明", notice(q.note || "报告缺少可核验的指标口径，数值不作为当前效果结论。", "warn") + "<p>本报告呈现交付与观察，不承诺排名、询盘或收入增长。</p>")}${card("数据范围", `<dl>${row("有效样本数", q.valid_queries == null ? "未提供" : esc(q.valid_queries))}${row("测量窗口", esc(q.period || "未提供"))}${row("数据来源", esc(q.source ? sourceLabel(q.source) : "未提供"))}${row("指标状态", q.status === "verified" ? "已核验关联批次；不代表因果验证" : "历史口径待核验；缺失、未采集与实测零值不可混同")}</dl>`)}${r.geo_snapshot ? card("本报告 GEO 指标", metricCards(r.geo_snapshot)) : ""}${card("关键发现与建议", r.key_findings?.length ? `<ol>${r.key_findings.map((f) => `<li><strong>${esc(f.statement || f.title || "发现")}</strong>${f.recommendation ? `<p>${esc(f.recommendation)}</p>` : ""}</li>`).join("")}</ol>` : empty("本报告未记录关键发现。"))}${card("下一步", r.next_steps?.length ? `<ul>${r.next_steps.map((s) => `<li>${esc(reportText(s))}</li>`).join("")}</ul>` : empty("下一步由总部确认。"))}${card("局限与方法说明", `<ul>${(r.limitations || []).map((s) => `<li>${esc(reportText(s))}</li>`).join("")}</ul><p>观察到变化不等于证明因果；单次观察不代表长期趋势。</p>`)}</article>`,
    );
    $("print-report").onclick = () => window.print();
  }
  async function leads(token) {
    const [rs, tenants] = await Promise.all([
      api(
        "GET",
        session.is_hq
          ? "/leads?tenant_id=" +
              encodeURIComponent(state.leadQueue || "HQ-INTAKE")
          : "/leads",
      ),
      session.is_hq
        ? api("GET", "/leads/assignable-tenants").then((x) => x.tenants || [])
        : Promise.resolve([]),
    ]);
    if (token !== epoch) return;
    shell(
      "leads",
      heading(
        session.is_hq ? "线索分配" : "我的线索",
        session.is_hq
          ? "分配客户后，提交需求进入总部确认。"
          : "仅显示总部已分配给你的线索。",
      ) +
        (session.is_hq
          ? card(
              "查看队列",
              `<label for="lead-queue">线索所属渠道商</label><select id="lead-queue">${opts({ "HQ-INTAKE": "待分配（总部）", ...Object.fromEntries(tenants.map((t) => [t, t])) }, state.leadQueue || "HQ-INTAKE")}</select>`,
            )
          : "") +
        card(
          "线索列表",
          rs.length
            ? rs
                .map(
                  (r) =>
                    `<section class="lead-entry"><h3>${esc(r.contact.company || r.contact.name || "网站线索")}</h3>${chip(r.intake_status)}<p class="muted">来源：${esc(r.source)} · ${esc(dt(r.created_at))}</p><p>${esc(r.message)}</p><p>${esc(r.contact.email)} · ${website(r.contact.domain)}</p><div class="toolbar">${r.client_id ? link(obj("client", r.client_id, r.tenant_id), "进入客户", "btn ghost") : ""}${r.request_id ? link("#/request/" + r.request_id, "查看需求", "btn ghost") : ""}${r.project_id ? link(obj("project", r.project_id, r.tenant_id), "查看项目", "btn ghost") : ""}</div>${session.is_hq && !r.client_id ? `<label for="assign-${esc(r.lead_id)}">分配给渠道商</label><select id="assign-${esc(r.lead_id)}">${opts(Object.fromEntries(tenants.map((t) => [t, t])))}</select><button class="btn ghost" data-assign="${esc(r.lead_id)}">分配并创建客户</button>` : ""}${session.is_hq && r.client_id && !r.request_id ? `<button class="btn ghost" data-convert="${esc(r.lead_id)}">创建待确认需求</button>` : ""}<div id="lead-msg-${esc(r.lead_id)}"></div></section>`,
                )
                .join("")
            : empty(
                session.is_hq
                  ? "当前队列没有线索。"
                  : "暂无分配线索，也可直接为客户提交需求。",
                writer() ? "#/request/new" : "",
                "提交需求",
              ),
        ),
    );
    if ($("lead-queue"))
      $("lead-queue").onchange = (e) => {
        state.leadQueue = e.target.value;
        route();
      };
    document.querySelectorAll("[data-assign],[data-convert]").forEach(
      (b) =>
        (b.onclick = async () => {
          const id = b.dataset.assign || b.dataset.convert;
          b.disabled = true;
          try {
            const r = rs.find((x) => x.lead_id === id);
            await api(
              "POST",
              "/leads/" + id + (b.dataset.assign ? "/assign" : "/convert"),
              b.dataset.assign
                ? {
                    tenant_id: $("assign-" + id).value,
                    create_client: true,
                    client_name: r.contact.company || r.contact.name,
                  }
                : { business_question: r.message },
            );
            route();
          } catch (e) {
            error("lead-msg-" + id, e);
            b.disabled = false;
          }
        }),
    );
  }
  function login(message = "") {
    app.innerHTML = `<section class="card login-card"><div class="report-brand">GEO 合作伙伴工作区</div><h1>${uiBase.endsWith("hq") ? "登录总部工作台" : "登录渠道商控制台"}</h1><p class="muted">使用总部提供的接入密钥登录。</p><div id="login-msg">${message ? notice(message, "warn") : ""}</div><form id="login-form">${field("key", "接入密钥", input("key", "", 'type="password" required autocomplete="off"'))}<button class="btn">登录</button></form><p class="small muted">密钥不保存在浏览器，后续请求使用受保护的会话。</p>${link(uiBase.endsWith("hq") ? "/ui/" : "/ui/hq/", uiBase.endsWith("hq") ? "进入渠道商工作区" : "进入总部工作区", "btn ghost")}</section>`;
    const loginCard = document.getElementById('login-form').closest('section');
    loginCard.querySelector('h1').textContent='登录 GEO 工作区';
    loginCard.querySelector('p.muted').textContent='使用自己的账号登录，工作区由总部开通。';
    const accountLink=document.createElement('a');accountLink.className='btn';accountLink.href=window.location.origin + '/?geo_workspace_login=1';accountLink.textContent='使用我的网站账号登录';
    if(!demoInfo.identity_enabled){accountLink.removeAttribute('href');accountLink.setAttribute('aria-disabled','true');accountLink.textContent='个人账号入口待总部配置';}
    document.getElementById('login-msg').before(accountLink);
    const maintenance=document.createElement('details');maintenance.innerHTML='<summary>集成维护入口</summary>';
    document.getElementById('login-form').before(maintenance);maintenance.append(document.getElementById('login-form'));
    loginCard.querySelectorAll('a[href="/ui/"],a[href="/ui/hq/"]').forEach(a=>a.remove());
    if (uiBase.endsWith("hq") && demoInfo.enabled) {
      $("login-form").insertAdjacentHTML("afterend", '<div class="demo-login"><hr><h2>总部虚拟演示</h2><p>独立虚拟数据，只读体验。批准、分配和发布操作在演示中不会写入。</p><div class="toolbar"><button class="btn" data-hq-demo="management">进入总部管理演示</button><button class="btn ghost" data-hq-demo="operations">进入总部运营演示</button></div></div>');
      document.querySelectorAll("[data-hq-demo]").forEach(b => b.onclick = async () => {
        b.disabled = true;
        try {
          const r = await fetch(uiBase + "/demo-session?role=" + b.dataset.hqDemo, {method:"POST", credentials:"same-origin"});
          if(!r.ok) throw Error("总部演示暂不可用，请重试");
          session = await r.json(); paint(); route();
        } catch(e) {error("login-msg",e);b.disabled=false;}
      });
    } else if (demoInfo.enabled || demoInfo.url) {
      const panel = document.createElement("div");
      panel.className = "demo-login";
      panel.innerHTML =
        "<hr><h2>先体验虚拟案例</h2><p>全部为虚拟客户与构造数据，只读演示，不代表真实效果。</p>" +
        (demoInfo.enabled
          ? '<button class="btn" id="enter-demo">进入虚拟案例演示</button>'
          : link(demoInfo.url + (uiBase.endsWith("hq") ? "hq/" : ""), uiBase.endsWith("hq") ? "进入总部虚拟演示" : "进入虚拟案例演示", "btn ghost"));
      $("login-form").after(panel);
      if ($("enter-demo"))
        $("enter-demo").onclick = async (e) => {
          e.target.disabled = true;
          try {
            const r = await fetch(uiBase + "/demo-session", {
              method: "POST",
              credentials: "same-origin",
            });
            const s = await r.json();
            if (!r.ok || !s.ok) throw Error("演示服务暂不可用，请稍后重试");
            session = s;
            paint();
            if (!/^#\/(geo|project|report|growth)\//.test(location.hash))
              location.hash = "#/growth/overview";
            route();
          } catch (e) {
            $("login-msg").innerHTML = notice(e.message, "err");
            if ($("enter-demo")) $("enter-demo").disabled = false;
          }
        };
    }
    $("login-form").insertAdjacentHTML(
      "afterend",
      '<p><a href="/ui/customer/">终端客户工作区</a></p>',
    );
    $("login-form").onsubmit = async (e) => {
      e.preventDefault();
      const b = e.submitter;
      b.disabled = true;
      try {
        const r = await fetch(uiBase + "/session", {
            method: "POST",
            credentials: "same-origin",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ api_key: $("key").value.trim() }),
          }),
          s = await r.json();
        if (!r.ok || !s.ok)
          throw new Error(
            r.status === 429
              ? "登录尝试过于频繁，请稍后再试"
              : "密钥无效，请核对后重试",
          );
        session = s;
        $("key").value = "";
        paint();
        if (location.hash === "#/login") location.hash = "#/dashboard";
        else route();
      } catch (e) {
        $("login-msg").innerHTML = notice(e.message, "err");
      } finally {
        b.disabled = false;
      }
    };
  }
  async function help(token) {
    shell(
      "help",
      heading("渠道商控制台 · 功能说明", "各模块用途与进入条件一览。") +
        card("整体定位", '<p class="muted">Distributor sells; HQ delivers. 渠道商连接客户、推进商机；总部负责专业交付。所有数据按当前租户（tenant）隔离。</p>') +
        card("工作台 · 生意面总览", '<p>渠道商每日进入的第一屏，回答「今天该跟什么、哪些客户要推进」。</p><p class="muted">数据来源：当前租户下的需求、项目、客户。</p><ul><li><b>KPI 卡片</b>：待补充资料、待总部确认、进行中项目、客户总数</li><li><b>待处理需求</b>：待补充资料（clarification_required）/ 待总部确认（submitted、intake_review、scoping、scope_pending_approval）</li><li><b>最近项目</b>：按更新时间取最近 8 个</li><li>有写权限（writer）的账号才显示「新建客户」「提交需求」</li></ul>') +
        card("专业作业台 · 交付面执行台", '<p>进入某个<b>已授权项目</b>做 GEO 内容增长优化操作的地方。按「项目 + 资源（产品/站点）」双重隔离，需项目授予 <code>operate</code>（作业）能力才出现内容。</p><p class="muted">进入前置：① /growth/workspace 中 capabilities.operate 为真的项目；② 项目下至少一个授予你 operate 的资源。</p><p>任一不满足即显示空状态：<i>尚无已授权项目。请联系管理员分配项目及作业权限。</i></p><p><b>子模块</b>：概览 · 产品 · 用户画像 · 场景 · 问句 · 聚类 · 简报 · 引用 · 趋势 · 实体 · 差距 · 关键词 · SEO · 提示词 · 手册</p><p class="muted">写操作走 If-Match 版本校验 + 幂等键；问句/关键词支持分页与 CSV 导出；引用检查属传统记录，不替代质量复核后的测量。</p>') +
        card("增长证据与交付 · 看结果", '<p>客户/项目维度的 GEO 效果证据模块。与作业台区别：它是「看结果」，作业台是「做执行」。</p>') +
        card("我的线索 / 我的客户 / 需求与项目", '<ul><li><b>我的线索</b>：渠道商自己的线索池</li><li><b>我的客户</b>：客户列表 + 新建客户（writer 可建）+ 客户详情（档案 / 关联需求 / 项目 / 跳转 GEO 效果）</li><li><b>需求与项目</b>：需求受理与项目交付进度</li></ul>') +
        card("模块间流转", '<p class="muted">线索 →(建客户)→ 需求 →(总部确认/审批)→ 项目（进行中）→ 专业作业台（执行 GEO 优化）→ 增长证据与交付（看效果）</p>') +
        card("为什么专业作业台可能是空的", '<p>渠道商管理员默认是「客户与项目管理」身份，未必被授到具体项目的 operate 能力。所以工作台能看（管客户/项目），专业作业台空着（还没被授权进项目实操）——这是设计如此，不是故障。补一个项目级作业授权即可。</p>')
    );
  }
  async function route() {
    if (!session) {
      login();
      return;
    }
    const token = ++epoch;
    const [path, query = ""] = (location.hash || "#/dashboard")
        .slice(1)
        .split("?"),
      parts = path.split("/").filter(Boolean),
      args = new URLSearchParams(query);
    tenant = session.is_hq ? args.get("tenant") || "" : "";
    const active = session.is_hq && Object.hasOwn(hqTitles, parts[0]) ? parts[0] : ["clients", "client"].includes(parts[0])
      ? "clients"
      : parts[0] === "leads"
        ? "leads"
        : ["request", "project", "projects", "report", "geo"].includes(parts[0])
          ? "projects"
          : parts[0] === "growth"
            ? "growth"
            : parts[0] === "help"
              ? "help"
              : "dashboard";
    shell(
      active,
      card("正在加载", '<p class="muted" role="status">正在获取最新记录…</p>'),
    );
    try {
      if (parts[0] === "operator") {
        await window.OperatorWorkspace.render({api,shell,refresh:route,alive:()=>token===epoch&&!!session,dirty:value=>{dirty=value;},syncRoute:()=>{lastHash=location.hash;}});
      } else if (parts[0] === "access" && session.role === 'HQ_MANAGEMENT') {
        await window.WorkspaceAccess.render({api,shell,refresh:route,alive:()=>token===epoch&&!!session,dirty:value=>{dirty=value;}});
      } else if (parts[0] === "access") {
        // VC-12：越权访问必须显式反馈，不能静默回退到工作台。
        shell(active, card("无权限查看", '<p>当前身份无权查看「账号与作业授权」。该区域仅对总部管理身份开放，权限由总部统一分配。</p><p><a class="btn ghost" href="#/dashboard">返回工作台</a></p>'));
      } else if (parts[0] === "help") {
        await help(token);
      } else if (parts[0] === "growth") {
        await window.GrowthWorkspace.render({
          api, shell, refresh:route, alive:()=>token===epoch && !!session,
          dirty:value=>{dirty=value;}
        });
      } else if (session.is_hq && Object.hasOwn(hqTitles, parts[0] || "dashboard"))
        await hqWorkspace(token, parts[0] || "dashboard", args);
      else if (session.is_hq && parts[0] === "lead" && parts[1]) await hqLeadDetail(decodeURIComponent(parts[1]), token);
      else if (parts[0] === "clients") await clients(token);
      else if (parts[0] === "client" && parts[1] === "new") newClient();
      else if (parts[0] === "client" && parts[1])
        await clientDetail(decodeURIComponent(parts[1]), token);
      else if (parts[0] === "projects") await projects(token);
      else if (parts[0] === "request" && parts[1] === "new")
        await newRequest(token, args.get("client"));
      else if (parts[0] === "request" && parts[1])
        await requestDetail(decodeURIComponent(parts[1]), token);
      else if (parts[0] === "project" && parts[1])
        await projectDetail(decodeURIComponent(parts[1]), token);
      else if (parts[0] === "geo" && parts[1])
        await geoDetail(decodeURIComponent(parts[1]), token);
      else if (parts[0] === "report" && parts[1])
        await reportDetail(decodeURIComponent(parts[1]), token);
      else if (parts[0] === "leads") {
        if (parts[1] && session.is_hq)
          state.leadQueue = decodeURIComponent(parts[1]);
        await leads(token);
      } else if (session.is_hq) await hqWorkspace(token, "dashboard", args);
      else await dashboard(token);
      if (token === epoch) $("view")?.focus({ preventScroll: true });
    } catch (e) {
      if (token === epoch) failure(e, active);
    }
  }
  window.addEventListener("hashchange", () => {
    const next = location.hash,
      allowed = !session?.is_hq && !lastHash.startsWith("#/growth") && (next.startsWith("#/request/new") || next === "#/client/new");
    if (dirty && !allowed) {
      if (!confirm("离开将放弃未提交内容，确定离开？")) {
        history.replaceState(null, "", lastHash);
        return;
      }
      dirty = false;
      draft = null;
      window.GrowthWorkspace?.discard();
    }
    if (session?.is_hq) {
      const from = lastHash.match(/^#\/(dashboard|leads|requests|projects|clients|results|records)(?:\?|$)/);
      const to = next.match(/^#\/(request|project|client|lead)\//);
      if (from && to) (state.hqReturn ||= {})[{request:"requests",project:"projects",client:"clients",lead:"leads"}[to[1]]] = lastHash;
    }
    if (draft) collect();
    lastHash = next;
    route();
  });
  app.addEventListener("input", e => {
    if (session?.is_hq && !location.hash.startsWith('#/access') && (e.target.closest("form") || e.target.id === "review-note") && !e.target.closest("#login-form")) dirty = true;
  });
  window.addEventListener("beforeunload", (e) => {
    if (dirty) {
      e.preventDefault();
      e.returnValue = "";
    }
  });
  $("logout").onclick = async () => {
    if (dirty && !confirm("退出将放弃未提交内容，确定退出？")) return;
    try {
      const r = await fetch(uiBase + "/session", {
        method: "DELETE",
        credentials: "same-origin",
      });
      if (!r.ok) throw Error();
      session = null;
      window.GrowthWorkspace?.clear();
      dirty = false;
      draft = null;
      epoch++;
      paint();
      location.hash = "#/login";
      login();
    } catch {
      alert("退出未完成，请稍后重试");
    }
  };
  Promise.all([
    fetch(uiBase + "/session", { credentials: "same-origin" }).then((r) => r.json()),
    fetch(uiBase + "/demo-info")
      .then((r) => r.json())
      .catch(() => ({ enabled: false, url: "" })),
  ])
    .then(([s, d]) => {
      demoInfo = d;
      return s;
    })
    .then((s) => {
      session = s.ok ? s : null;
      paint();
      route();
    })
    .catch(() => login("暂时无法连接登录服务，请稍后刷新。"));
})();
