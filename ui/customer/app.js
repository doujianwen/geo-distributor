/* Customer task UI. All business access is through the customer-only session BFF. */
(() => {
  "use strict";
  const app = document.getElementById("app"),
    $ = (id) => document.getElementById(id);
  const BASE = "/ui/customer/",
    navs = {
      "growth/overview": "GEO 增长模块",
      "operator/dashboard": "专业作业台",
      overview: "服务概览",
      diagnosis: "网站诊断",
      competitors: "竞品观察",
      actions: "优化与待办",
      monitoring: "效果监控",
      reports: "报告",
    };
  const status = {
    approved: "待启动",
    in_execution: "服务进行中",
    blocked: "服务暂缓",
    qa: "质量复核中",
    rework: "调整中",
    delivered: "已交付",
    accepted: "已验收",
    changes_requested: "待调整",
    cancelled: "已取消",
    pending: "待我处理",
    submitted: "已答复，待团队处理",
    confirmed: "已确认，待团队处理",
    closed: "已处理关闭",
    withdrawn: "已撤回",
    not_started: "未开始",
    in_progress: "进行中",
    completed: "已完成",
  };
  const kinds = {
    material_request: "资料请求",
    content_review: "内容确认",
    report_feedback: "报告反馈",
  };
  const events = {
    published: "发布待办",
    submit: "提交资料",
    confirm: "确认内容",
    request_changes: "要求修改",
    close: "处理关闭",
    reopen: "重新请求确认",
    withdraw: "撤回待办",
  };
  const metrics = {
    mention_rate: "品牌提及率",
    recommendation_rate: "推荐比例（等级 ≥ 2）",
    citation_rate: "回答引用可用率",
  };
  let session = null,
    info = {},
    workspace = null,
    epoch = 0,
    selected = "",
    dirty = false,
    lastHash = location.hash || "#/overview";
  let drafts = {},
    filters = {},
    operatorAvailable = false;
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
  const url = (page, project = selected, extra = "") =>
    `#/${page}${project ? "?project=" + encodeURIComponent(project) : ""}${extra}`;
  const a = (href, text, cls = "") =>
    `<a href="${esc(href)}" class="${cls}">${esc(text)}</a>`;
  const card = (t, b) =>
    `<section class="card"><h2>${esc(t)}</h2>${b}</section>`;
  const note = (text, kind = "info") =>
    `<div class="notice ${kind}" role="status">${esc(text)}</div>`;
  const empty = (text) => `<p class="empty">${esc(text)}</p>`;
  const stamp = (v) => {
    if (!v) return "未记录";
    if (!/Z$|[+-]\d{2}:\d{2}$/.test(v))
      return String(v).replace("T", " ").slice(0, 19) + "（源时间未标时区）";
    const d = new Date(v);
    return isNaN(d)
      ? "时间待核对"
      : new Intl.DateTimeFormat("zh-CN", {
          timeZone: "Asia/Shanghai",
          year: "numeric",
          month: "2-digit",
          day: "2-digit",
          hour: "2-digit",
          minute: "2-digit",
          hour12: false,
        }).format(d) + " 北京时间";
  };
  const percent = (v) => (v == null ? "暂不可用" : `${v}%`);
  const title = (r) =>
    /^GEO Visibility Report for /.test(r.title) ? "GEO 可见性报告" : r.title;
  const idempotency = () =>
    Array.from(crypto.getRandomValues(new Uint8Array(16)), (v) =>
      v.toString(16).padStart(2, "0"),
    ).join("");
  function clearPrivate() {
    workspace = null;
    drafts = {};
    filters = {};
    window.GrowthWorkspace?.clear();
    window.OperatorWorkspace?.clear();
    operatorAvailable = false;
    dirty = false;
    selected = "";
  }
  async function api(path, body, key) {
    return workspaceApi(body ? "POST" : "GET", "/" + path, body, key ? {"Idempotency-Key":key} : {});
  }
  async function workspaceApi(method, path, body, headers = {}) {
    const target = new URL("http://workspace.invalid/" + path.replace(/^\//,""));
    target.searchParams.delete("tenant_id");
    target.searchParams.delete("client_id");
    const endpoint = target.pathname.replace(/^\//,"") + target.search;
    const write = method !== "GET";
    const r = await fetch(BASE + "proxy/customer/" + endpoint, {
      method,
      credentials: "same-origin",
      headers: {...(write ? {"Content-Type":"application/json"} : {}), ...headers},
      body: write ? JSON.stringify(body === undefined ? {} : body) : undefined,
    });
    const data = await r.json();
    if (r.status === 401) {
      session = null;
      epoch++;
      clearPrivate();
      paint();
      login("会话已失效，请重新登录。未提交内容已清除，避免被另一身份读取。");
      throw Error("会话已失效");
    }
    if (r.status === 429) throw Object.assign(Error("操作较频繁，请稍后再试。"), {status:r.status});
    if (r.status >= 500)
      throw Object.assign(Error("服务暂时无法读取，请稍后重试；这不代表没有结果。"), {status:r.status});
    if (!r.ok)
      throw Error(
        r.status === 409
          ? "记录已更新或本次内容冲突，请保留资料并刷新核对。"
          : typeof data.detail === "string"
            ? data.detail
            : r.status === 422
              ? "请核对必填内容与长度。"
              : "暂时无法读取，请稍后重试。",
      );
    return data;
  }
  function paint() {
    $("session-box").hidden = !session;
    $("customer-name").textContent = workspace?.client.name || "客户工作区";
    document.body.classList.toggle("demo-mode", !!session?.is_demo);
  }
  function shell(active, body) {
    app.innerHTML = `<div class="workspace"><aside class="sidebar"><div class="workspace-label">我的 GEO 增长服务</div><button class="btn ghost menu-toggle" id="menu" aria-controls="nav" aria-expanded="false">工作区导航 · 展开</button><nav id="nav" aria-label="客户工作区导航">${Object.entries(
      {...(operatorAvailable?{"operator/dashboard":"专业作业台"}:{}),"growth/overview":"GEO 增长模块",overview:"服务与交付",actions:"服务协作待办",reports:"历史交付报告"},
    )
      .map(
        ([k, v]) =>
          `<a href="${esc(url(k))}" ${(k === active || (active === "growth" && k === "growth/overview") || (active === "operator" && k === "operator/dashboard")) ? 'class="on" aria-current="page"' : ""}>${v}</a>`,
      )
      .join(
        "",
      )}</nav><p class="sidebar-note">查看已发布结果<br>协同服务团队改善</p></aside><div class="content" id="view" tabindex="-1">${session?.is_demo ? '<div class="demo-banner"><strong>虚拟演示 · 企业、结果与待办均为构造案例</strong><span>此入口仅展示一家虚拟企业，演示为只读。</span><a href="http://geo-growth.local/portal/customer/">返回真实客户入口</a></div>' : ""}<div class="customer-context">${workspace?.projects.length ? `<label for="project-choice">服务项目<select id="project-choice">${workspace.projects.map((p) => `<option value="${esc(p.project_id)}" ${p.project_id === selected ? "selected" : ""}>${esc(p.name)} · ${esc(p.stage_label)}</option>`).join("")}</select></label>` : ""}<p class="muted">${esc(workspace?.client.name || "")}</p></div>${body}</div></div>`;
    $("menu").onclick = () => {
      const b = $("menu"),
        open = b.getAttribute("aria-expanded") !== "true";
      b.setAttribute("aria-expanded", String(open));
      $("nav").classList.toggle("expanded", open);
    };
    if ($("project-choice"))
      $("project-choice").onchange = (e) => {
        const tab = (location.hash.match(/^#\/([^?]+)/) || [])[1];
        location.hash = url(tab?.startsWith("operator/") ? tab : navs[tab] ? tab : "overview", e.target.value);
      };
  }
  function problem(error, active) {
    if (!session) return;
    shell(
      active,
      card(
        "暂时无法读取",
        note(error.message, "err") +
          '<button class="btn" id="retry">重新加载</button>',
      ),
    );
    $("retry").onclick = route;
  }
  function login(message = "") {
    app.innerHTML = `<section class="card login-card"><div class="report-brand">我的 GEO 增长服务</div><h1>登录 GEO 工作区</h1><p>使用自己注册的账号与密码登录。总部开通权限后，系统会展示您所属的企业、项目与可用功能。</p><p><a class="btn" href="http://geo-growth.local/?geo_workspace_login=1">使用个人账号登录</a></p><div id="login-msg">${message ? note(message, "warn") : ""}</div><details><summary>维护与集成验证入口</summary><p class="small muted">此入口供已获授权的维护人员验证现有集成。</p><form id="login-form"><div class="field"><label for="access-code">维护访问码</label><input id="access-code" type="password" required maxlength="512" autocomplete="off"></div><button class="btn">验证访问</button></form></details>${info.demo ? '<hr><h2>先体验虚拟客户案例</h2><p>全部数据虚构，只读体验。</p><button class="btn ghost" id="demo-enter">进入客户演示</button>' : info.demo_url ? `<hr>${a(info.demo_url, "体验虚拟客户案例", "btn ghost")}` : ""}<p class="small muted">账号开通与项目授权请联系服务团队。维护访问码不保存在浏览器。</p></section>`;
    async function enter(isDemo) {
      const response = await fetch(
        BASE + (isDemo ? "demo-session" : "session"),
        {
          method: "POST",
          credentials: "same-origin",
          headers: { "Content-Type": "application/json" },
          body: isDemo
            ? undefined
            : JSON.stringify({ api_key: $("access-code").value.trim() }),
        },
      );
      const data = await response.json();
      if (!response.ok)
        throw Error(
          response.status === 429
            ? "登录过于频繁，请稍后再试。"
            : "访问码无效或权限已停用，请联系服务团队。",
        );
      clearPrivate();
      session = data;
      paint();
      route();
    }
    const personalLink=app.querySelector('a[href="http://geo-growth.local/?geo_workspace_login=1"]');
    if(personalLink&&!info.identity_enabled){personalLink.removeAttribute('href');personalLink.setAttribute('aria-disabled','true');personalLink.textContent='个人账号入口待总部配置';}
    $("login-form").onsubmit = async (e) => {
      e.preventDefault();
      e.submitter.disabled = true;
      try {
        await enter(false);
      } catch (err) {
        $("login-msg").innerHTML = note(err.message, "err");
        e.submitter.disabled = false;
      }
    };
    if ($("demo-enter"))
      $("demo-enter").onclick = async (e) => {
        e.target.disabled = true;
        try {
          await enter(true);
        } catch (err) {
          $("login-msg").innerHTML = note(err.message, "err");
          e.target.disabled = false;
        }
      };
  }
  const reportLinks = (rs) =>
    rs.length
      ? `<ul class="report-list">${rs.map((r) => `<li>${a(url("report", r.project_id, "&id=" + encodeURIComponent(r.report_id)), title(r))}<small>版本 ${esc(r.version)} · ${esc(stamp(r.created_at))}</small></li>`).join("")}</ul>`
      : empty("暂无向您发布的报告。服务团队发布后会在这里展示。");
  function findings(rs, limit = 20) {
    return rs.length
      ? `<div id="findings-container">${rs
          .slice(0, limit)
          .map(
            (r) =>
              `<div><p class="small muted">来源：${a(url("report", r.project_id, "&id=" + encodeURIComponent(r.report_id)), title(r))} · ${esc(stamp(r.created_at))}</p>${r.key_findings?.length ? `<ol>${r.key_findings.map((f) => `<li><strong>${esc(f.statement || "观察发现")}</strong><p>${esc(f.recommendation || "后续建议由服务团队确认")}</p></li>`).join("")}</ol>` : empty("本报告尚未记录诊断发现。")}</div>`,
          )
          .join(
            "",
          )}${rs.length > limit ? '<button class="btn ghost" id="findings-more">再显示 20 份报告的诊断</button>' : ""}</div>`
      : empty("尚无已发布的诊断结论。没有结论不代表网站没有问题。");
  }
  function metricCards(b) {
    return `<div class="kpi-grid geo-kpis">${Object.entries(metrics)
      .map(
        ([k, v]) =>
          `<section class="card kpi-card"><span>${esc(v)}</span><strong>${percent(b.metrics[k])}</strong><p class="small muted">${esc(b.metric_notes[k])}</p></section>`,
      )
      .join(
        "",
      )}</div><p class="small muted">以上为整批结果，不随下方问题筛选重算。回答引用可用率不等于品牌引用率，推荐比例不代表排名。</p>`;
  }
  function safeResults(b, competitors = false) {
    const f = (filters[selected] ||= { q: "", engine: "", limit: 20 });
    return `<div class="list-tools"><label for="engine">平台<select id="engine"><option value="">全部平台</option>${[...new Set(b.observations.map((o) => o.engine))].map((e) => `<option value="${esc(e)}" ${e === f.engine ? "selected" : ""}>${esc(e)}</option>`).join("")}</select></label><label for="query">搜索问题<input type="search" id="query" value="${esc(f.q)}"></label></div><div id="evidence-results"></div>`;
  }
  function bindResults(b, competitors = false) {
    const f = filters[selected];
    function draw() {
      const found = b.observations.filter(
        (o) =>
          (!f.engine || o.engine === f.engine) &&
          o.prompt_text.toLowerCase().includes(f.q.toLowerCase()),
      );
      $("evidence-results").innerHTML =
        `<p role="status">${found.length} 条已发布问题结果</p>${
          found
            .slice(0, f.limit)
            .map(
              (o) =>
                `<article class="customer-evidence"><h3>${esc(o.prompt_text)}</h3><p class="small muted">${esc(o.engine)} · ${esc(stamp(o.timestamp))}</p>${o.status !== "success" ? note("本条结果不可用，不能作为效果结论。", "warn") : ""}<p>品牌：${o.brand_status === "UNKNOWN" ? "未知" : o.brand_mentioned ? "已提及" : "未提及"} · 推荐等级：${o.recommendation_level == null ? "未知" : esc(o.recommendation_level)}</p>${competitors ? `<p>同条回答观察到的竞品：${o.competitors.length ? esc(o.competitors.map((c) => c.name).join("、")) : "未提供，不代表不存在"}</p>` : ""}${o.excerpt ? `<blockquote>${esc(o.excerpt)}</blockquote>` : '<p class="muted">暂无已发布的回答摘要。</p>'}<p>引用依据：${o.citations.length ? o.citations.map((c) => `<a href="${esc(c.url)}" target="_blank" rel="noopener noreferrer">${esc(c.title || c.url)}</a>`).join(" · ") : "暂未提供可打开的引用"}</p></article>`,
            )
            .join("") || empty("没有匹配的问题。")
        }${found.length > f.limit ? '<button class="btn ghost" id="evidence-more">再显示 20 条</button>' : ""}`;
      if ($("evidence-more"))
        $("evidence-more").onclick = () => {
          f.limit += 20;
          draw();
        };
    }
    $("engine").onchange = (e) => {
      f.engine = e.target.value;
      f.limit = 20;
      draw();
    };
    $("query").oninput = (e) => {
      f.q = e.target.value;
      f.limit = 20;
      draw();
    };
    draw();
  }
  function reviewCards(rows) {
    return rows.length
      ? rows
          .map(
            (r) =>
              `<article class="customer-review"><h3>${esc(r.title)}</h3><p class="small muted">${esc(kinds[r.kind])} · ${esc(status[r.status] || r.status)} · ${esc(stamp(r.updated_at))}</p><p>${esc(r.instructions)}</p>${r.report_id ? a(url("report", r.project_id, "&id=" + encodeURIComponent(r.report_id)), "查看关联报告") : ""}${r.response ? `<p>我的答复：${esc(r.response.note)}</p>` : ""}${r.resolution ? `<p>服务团队处理说明：${esc(r.resolution)}</p>` : ""}${r.status === "pending" ? `<form data-review="${esc(r.review_id)}"><label for="decision-${esc(r.review_id)}">我的意见<select id="decision-${esc(r.review_id)}">${r.kind === "material_request" ? '<option value="submit">提交资料说明</option>' : '<option value="confirm">确认此项内容</option><option value="request_changes">提出修改意见</option>'}</select></label><label for="note-${esc(r.review_id)}">${r.kind === "material_request" ? "资料说明（不填写密码、密钥等敏感信息）" : "意见说明"}</label><textarea id="note-${esc(r.review_id)}" required maxlength="3000" ${session.is_demo ? "disabled" : ""}></textarea><p class="small muted">提交仅记录本项意见，不会自动验收项目或批准服务范围。</p><div id="msg-${esc(r.review_id)}"></div><button class="btn" ${session.is_demo ? "disabled" : ""}>${session.is_demo ? "虚拟演示为只读" : "核对并提交"}</button></form>` : ""}<details><summary>处理记录</summary><ol>${r.history.map((e) => `<li>${esc(stamp(e.at))} · ${esc(e.by)} · ${esc(events[e.action] || e.action)}<p>${esc(e.note || "")}</p></li>`).join("")}</ol></details></article>`,
          )
          .join("")
      : empty("暂无已发布的客户待办。服务团队需要您配合时会在此说明。");
  }
  function bindReviews(rows) {
    document.querySelectorAll("[data-review]").forEach((form) => {
      const id = form.dataset.review,
        r = rows.find((r) => r.review_id === id),
        draft = (drafts[id] ||= {
          note: "",
          action: r.kind === "material_request" ? "submit" : "confirm",
          key: idempotency(),
        });
      const text = $("note-" + id),
        choice = $("decision-" + id);
      text.value = draft.note;
      choice.value = draft.action;
      const collect = () => {
        draft.note = text.value;
        draft.action = choice.value;
        dirty = true;
      };
      text.oninput = collect;
      choice.onchange = collect;
      form.onsubmit = async (e) => {
        e.preventDefault();
        if (!text.value.trim()) {
          $("msg-" + id).innerHTML = note("请填写意见说明。", "err");
          text.focus();
          return;
        }
        if (!confirm("确认提交这项意见？此操作不会自动验收项目。")) return;
        const b = e.submitter;
        b.disabled = true;
        try {
          await api(
            "reviews/" + encodeURIComponent(id) + "/respond",
            {
              revision: r.revision,
              action: choice.value,
              note: text.value.trim(),
            },
            draft.key,
          );
          delete drafts[id];
          dirty = false;
          route();
        } catch (err) {
          if ($("msg-" + id))
            $("msg-" + id).innerHTML = note(err.message, "err");
          b.disabled = false;
        }
      };
    });
  }
  async function route() {
    if (!session) {
      login();
      return;
    }
    const token = ++epoch;
    const [path, query = ""] = (location.hash || "#/overview")
      .slice(2)
      .split("?");
    const args = new URLSearchParams(query);
    const tab = navs[path] ? path : path === "report" ? "reports" : "overview";
    shell(
      tab,
      card("正在加载", '<p role="status">正在获取已发布的最新结果…</p>'),
    );
    try {
      try {
        const growth = await workspaceApi("GET", "/growth/workspace");
        if (token !== epoch || !session) return;
        operatorAvailable = growth.projects.some(p => p.capabilities?.operate);
      } catch (error) {
        operatorAvailable = false;
        if (!session || path.startsWith("growth/") || path.startsWith("operator/")) throw error;
      }
      if(path.startsWith("growth/") || path.startsWith("operator/") || !location.hash){
        const target = path.startsWith("operator/") ? window.OperatorWorkspace : window.GrowthWorkspace;
        await target.render({
          api:workspaceApi,
          shell,refresh:route,alive:()=>token===epoch && !!session,dirty:value=>{dirty=value;},syncRoute:()=>{lastHash=location.hash;}
        });
        return;
      }
      const ws = await api("workspace");
      if (token !== epoch || !session) return;
      workspace = ws;
      selected =
        args.get("project") || selected || ws.projects[0]?.project_id || "";
      paint();
      if (!ws.projects.length) {
        shell(
          tab,
          card(
            "欢迎进入客户工作区",
            empty("尚无已关联的服务项目。请联系服务团队确认服务安排。"),
          ),
        );
        return;
      }
      const p = await api("projects/" + encodeURIComponent(selected));
      if (token !== epoch || !session) return;
      const head = `<div class="page-heading"><div><h1>${esc(navs[tab])}</h1><p class="muted">${esc(p.stage_label)} · ${esc(status[p.status] || "状态待确认")} · 更新于 ${esc(stamp(p.updated_at))}</p></div></div>`;
      if (path === "report") {
        const r = await api(
          "reports/" + encodeURIComponent(args.get("id") || ""),
        );
        if (token !== epoch || !session) return;
        if (r.project_id !== selected) {
          location.hash = url(
            "report",
            r.project_id,
            "&id=" + encodeURIComponent(r.report_id),
          );
          return;
        }
        const q = r.data_quality || {};
        shell(
          "reports",
          head +
            a(url("reports", r.project_id), "返回报告列表", "btn ghost") +
            ' <button class="btn" id="print">打印 / 保存 PDF</button>' +
            `<article class="report-document"><div class="report-brand">GEO 增长服务 · 客户报告</div><h1>${esc(title(r))}</h1><p class="muted">版本 ${esc(r.version)} · ${esc(stamp(r.created_at))}</p>${card("阅读说明", note(q.note || "报告范围与数据口径待核对。", "warn"))}${card("数据范围", `<p>有效样本：${q.valid_queries == null ? "未提供" : esc(q.valid_queries)}</p><p>观测窗口：${esc(q.period || "未完整记录")}</p>`)}${r.geo_snapshot ? card("本报告指标", metricCards(r.geo_snapshot)) : ""}${card("发现与建议", findings([r]))}${card("下一步", `<ul>${(r.next_steps || []).map((t) => `<li>${esc(t)}</li>`).join("")}</ul>`)}${card("局限与方法说明", `<ul>${(r.limitations || []).map((t) => `<li>${esc(t)}</li>`).join("")}</ul><p>观察变化不代表因果，不承诺排名、询盘或收入增长。</p>`)}</article>`,
        );
        $("print").onclick = () => window.print();
        return;
      }
      if (tab === "reports") {
        const rs = await api(
          "reports?project_id=" + encodeURIComponent(selected),
        );
        if (token !== epoch || !session) return;
        shell(
          tab,
          head +
            card(
              "历史报告",
              '<label class="customer-report-search" for="report-search">搜索报告<input id="report-search" type="search"></label><div id="report-list"></div>',
            ),
        );
        const reportFilter = (filters["reports-" + selected] ||= {
          q: "",
          limit: 20,
        });
        $("report-search").value = reportFilter.q;
        const draw = () => {
          const found = rs.filter((r) =>
            (title(r) + " " + r.version)
              .toLowerCase()
              .includes($("report-search").value.toLowerCase()),
          );
          $("report-list").innerHTML =
            reportLinks(found.slice(0, reportFilter.limit)) +
            (found.length > reportFilter.limit
              ? '<button class="btn ghost" id="reports-more">再显示 20 份</button>'
              : "");
          if ($("reports-more"))
            $("reports-more").onclick = () => {
              reportFilter.limit += 20;
              draw();
            };
        };
        $("report-search").oninput = () => {
          reportFilter.q = $("report-search").value;
          reportFilter.limit = 20;
          draw();
        };
        draw();
        return;
      }
      const settled = await Promise.allSettled([
        api("projects/" + encodeURIComponent(selected) + "/geo"),
        api("reports?project_id=" + encodeURIComponent(selected)),
        api("reviews?project_id=" + encodeURIComponent(selected)),
      ]);
      if (token !== epoch || !session) return;
      const [geo, reports, reviews] = settled.map((s) =>
        s.status === "fulfilled" ? s.value : null,
      );
      const errors = settled.some((s) => s.status === "rejected")
        ? note("部分内容读取失败，这不代表没有结果。", "err") +
          '<button class="btn ghost" id="partial-retry">重新加载</button>'
        : "";
      let body = "";
      let b =
        geo?.batches.find((b) => b.measurement_id === args.get("batch")) ||
        geo?.batches.at(-1);
      if (tab === "overview")
        body = `<div class="customer-summary">${card("当前服务", `<p>${esc(p.name)}</p><p>服务阶段：${esc(p.stage_label)}</p><p>确认周期：${esc(p.confirmed_duration || "请与服务团队核对")}</p><p>交付内容：${esc(p.deliverables.join("；") || "请与服务团队核对")}</p><p>下一步：${esc(p.next_action)}</p>`)}${card("待我处理", reviews ? `<p>${reviews.filter((r) => r.status === "pending").length} 项待答复</p>${a(url("actions"), "查看资料与确认事项", "btn")}` : empty("待办暂时无法读取。"))}</div>${card("服务进展", `<ol class="stage-list">${p.stages.map((s) => `<li><strong>${esc(s.label)}</strong><span>${esc(status[s.status] || s.status)}</span></li>`).join("")}</ol><p class="small muted">服务阶段不代表效果评分或项目已验收。</p>`)}${b ? metricCards(b) : card("近期表现", empty("暂无向您发布的测量结果；这不代表效果为零。"))}${card("最新报告", reports ? reportLinks(reports.slice(0, 3)) : empty("报告暂时无法读取。"))}`;
      else if (tab === "diagnosis")
        body =
          card(
            "网站诊断与改善建议",
            reports ? findings(reports) : empty("诊断报告暂时无法读取。"),
          ) +
          card(
            "依据与验证",
            a(url("monitoring"), "查看已发布问题与依据", "btn ghost") +
              "<p>SEO技术诊断数据尚未发布时，不据此推断SEO表现。</p>",
          );
      else if (tab === "actions")
        body =
          card(
            "建议与执行安排",
            reports ? findings(reports) : empty("建议暂时无法读取。"),
          ) +
          card(
            "需要我提供或确认",
            reviews
              ? `<div id="customer-reviews-list">${reviewCards(reviews.slice(0, 20))}</div>${reviews.length > 20 ? '<button class="btn ghost" id="reviews-more">再显示 20 项待办</button>' : ""}`
              : empty("待办暂时无法读取。"),
          ) +
          note(
            "此处记录客户协作意见；实际优化执行与复测由服务团队安排，尚无已发布的行动归因数据。",
          );
      else if (geo) {
        body = card(
          "选择批次",
          geo.batches.length
            ? `<label for="batch">已发布测量批次<select id="batch">${geo.batches.map((x) => `<option value="${esc(x.measurement_id)}" ${x.measurement_id === b?.measurement_id ? "selected" : ""}>${esc(stamp(x.collected_at))}</option>`).join("")}</select></label>`
            : empty(
                "暂无向您发布的测量结果。可能尚未采集或仍待发布，请联系服务团队。",
              ),
        );
        if (b) {
          body += card(
            "本批范围",
            `<p>品牌：${esc(b.context.brand || "未记录")} · 市场/语言：${esc((b.context.market || "未记录") + " / " + (b.context.language || "未记录"))}</p><p>${b.total_samples} 条已保存，${b.valid_samples} 条采集成功且质量通过，${b.unavailable_samples} 条不可用。</p><p>观测窗口：${esc(b.period || "未完整记录")}</p>`,
          );
          if (tab === "monitoring")
            body +=
              metricCards(b) +
              card(
                "与上一已发布批次的变化",
                `<p>${esc(b.comparison.note)}</p>${Object.entries(metrics)
                  .map(
                    ([k, label]) =>
                      `<p>${esc(label)}：${b.comparison.delta_pp[k] == null ? "不可比较" : (b.comparison.delta_pp[k] > 0 ? "+" : "") + b.comparison.delta_pp[k] + " 个百分点"}</p>`,
                  )
                  .join(
                    "",
                  )}<p class="small muted">单批观察不是趋势；范围不足或变化时不比较。</p>`,
              );
          body += card(
            tab === "competitors" ? "竞品出现情况与依据" : "问题结果与依据",
            safeResults(b, tab === "competitors"),
          );
        }
        body += note(
          tab === "competitors"
            ? "这里只描述相同回答中的竞品观察，不是市场份额或完整竞品排名；SEO竞品数据尚未发布。"
            : "仅呈现已发布批次，不代表完整问题库覆盖；没有已发布的商业转化或归因数据。",
        );
      } else
        body = card("结果暂不可用", empty("测量结果读取失败，可重新加载。"));
      shell(tab, head + errors + body);
      if ($("partial-retry")) $("partial-retry").onclick = route;
      if ($("batch"))
        $("batch").onchange = (e) =>
          (location.hash = url(
            tab,
            selected,
            "&batch=" + encodeURIComponent(e.target.value),
          ));
      if ($("evidence-results")) bindResults(b, tab === "competitors");
      if (tab === "actions" && reviews) {
        bindReviews(reviews);
        let shown = 20;
        if ($("reviews-more"))
          $("reviews-more").onclick = () => {
            $("customer-reviews-list").insertAdjacentHTML(
              "beforeend",
              reviewCards(reviews.slice(shown, shown + 20)),
            );
            shown += 20;
            bindReviews(reviews);
            if (shown >= reviews.length) $("reviews-more").remove();
          };
      }
      if (reports && $("findings-more")) {
        let shown = 20;
        const bind = () => {
          if ($("findings-more"))
            $("findings-more").onclick = () => {
              shown += 20;
              $("findings-container").outerHTML = findings(reports, shown);
              bind();
            };
        };
        bind();
      }
      if (token === epoch) $("view")?.focus({ preventScroll: true });
    } catch (err) {
      if (token === epoch) problem(err, tab);
    }
  }
  window.addEventListener("hashchange", () => {
    if (dirty && !confirm("离开会放弃未提交的内容，确定离开？")) {
      history.replaceState(null, "", lastHash);
      return;
    }
    if (dirty) {
      window.GrowthWorkspace?.discard();
      window.OperatorWorkspace?.discard();
      drafts = {};
      dirty = false;
    }
    lastHash = location.hash;
    route();
  });
  window.addEventListener("beforeunload", (e) => {
    if (dirty) {
      e.preventDefault();
      e.returnValue = "";
    }
  });
  $("logout").onclick = async () => {
    if (dirty && !confirm("退出会放弃未提交内容，确定退出？")) return;
    try {
      const r = await fetch(BASE + "session", {
        method: "DELETE",
        credentials: "same-origin",
      });
      if (!r.ok) throw Error();
      session = null;
      epoch++;
      clearPrivate();
      paint();
      login();
    } catch {
      alert("退出未完成，请稍后重试。");
    }
  };
  Promise.all([
    fetch(BASE + "session", { credentials: "same-origin" }).then((r) =>
      r.json(),
    ),
    fetch(BASE + "info").then((r) => r.json()),
  ])
    .then(([s, i]) => {
      info = i;
      session = s.ok ? s : null;
      paint();
      route();
    })
    .catch(() => login("暂时无法连接服务，请稍后刷新。"));
})();
