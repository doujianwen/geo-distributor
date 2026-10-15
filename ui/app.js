/* 渠道商控制台 — 原生 JS，零依赖（CSP: script-src 'self' / style-src 'self'）。
 *
 * 安全要点：
 *  - 浏览器**从不持有 API Key**；登录时交给服务端换取会话 cookie，
 *    之后所有业务调用走 /ui/proxy/*，由服务端注入密钥。
 *  - 所有渲染走 esc()，不把上游数据直接拼进 innerHTML。
 *  - **不使用任何内联 style 属性**（CSP style-src 'self' 会拦截它们）；
 *    动态宽度走 w-0..w-100 工具类。
 */
(function () {
  "use strict";

  var app = document.getElementById("app");
  var sessionBox = document.getElementById("session-box");
  var whoEl = document.getElementById("who");
  var SESSION = null;

  /* ---------- utils ---------- */

  function esc(v) {
    return String(v === null || v === undefined ? "" : v)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }

  function h(html) { app.innerHTML = html; }

  function notice(kind, msg) {
    return '<div class="notice ' + kind + '">' + esc(msg) + "</div>";
  }

  function chip(text, kind) {
    return '<span class="chip ' + (kind || "") + '">' + esc(text) + "</span>";
  }

  function stageChip(stage) {
    var map = {
      site_diagnosis: "warn", competitor_analysis: "warn",
      optimization: "", effect_monitoring: "ok"
    };
    return chip(stage || "—", map[stage] || "");
  }

  function pct(n) {
    n = Number(n || 0);
    return isFinite(n) ? Math.max(0, Math.min(100, Math.round(n))) : 0;
  }

  /** 服务进度取值。
   *
   * 为什么不用 `progress_percent`：该字段在 `Project` 模型上**从未被赋值**
   * （`work_item_repo=None`，对应执行流未接线），本部署中恒为 0 —— 直接展示会
   * 让渠道商永远看到「0%」。四阶段工作流的真实进度是 `stage_progress`
   * （已完成阶段数 / 4），这才是门户要表达的「服务进度」。
   * 仅做展示层取值，不改任何 API 契约。
   */
  function progOf(p) {
    if (!p) { return 0; }
    var sp = p.stage_progress;
    if (typeof sp === "number" && isFinite(sp)) { return sp; }
    return p.progress_percent;
  }

  /** 进度宽度工具类（w-0 / w-5 / ... / w-100），避免内联 style。 */
  function wClass(n) {
    return "w-" + (Math.round(pct(n) / 5) * 5);
  }

  /* ---------- API ---------- */

  function api(method, path, body) {
    var opt = {
      method: method,
      credentials: "same-origin",
      headers: { "Accept": "application/json" }
    };
    if (body !== undefined && body !== null) {
      opt.headers["Content-Type"] = "application/json";
      opt.body = JSON.stringify(body);
    }
    return fetch("/ui/proxy" + path, opt).then(function (r) {
      return r.text().then(function (t) {
        var data = null;
        try { data = t ? JSON.parse(t) : null; } catch (e) { data = { detail: t }; }
        if (!r.ok) {
          var err = new Error((data && data.detail) ? data.detail : ("HTTP " + r.status));
          err.status = r.status;
          throw err;
        }
        return data;
      });
    });
  }

  function sessionApi(method, body) {
    var opt = { method: method, credentials: "same-origin", headers: {} };
    if (body) {
      opt.headers["Content-Type"] = "application/json";
      opt.body = JSON.stringify(body);
    }
    return fetch("/ui/session", opt).then(function (r) {
      return r.json().catch(function () { return null; });
    }).then(function (data) {
      if (!data || data.ok !== true) { return null; }
      return data;
    });
  }

  /* ---------- 路由 ---------- */

  function go(hash) { location.hash = hash; }

  function route() {
    var hash = (location.hash || "#/").replace(/^#/, "");
    var parts = hash.split("/").filter(Boolean);

    if (!SESSION) { renderLogin(); return; }

    if (parts.length === 0) { go("#/dashboard"); return; }
    if (parts[0] === "dashboard") { renderDashboard(); return; }
    if (parts[0] === "clients") { renderClients(); return; }
    if (parts[0] === "projects") { renderProjects(); return; }
    if (parts[0] === "leads") { renderLeads(parts[1] ? decodeURIComponent(parts[1]) : ""); return; }
    if (parts[0] === "project" && parts[1]) { renderProject(decodeURIComponent(parts[1])); return; }
    renderDashboard();
  }

  function nav(active) {
    function cls(k) { return k === active ? ' class="on"' : ""; }
    return '<div class="tabs">' +
      '<a href="#/dashboard"' + cls("dashboard") + '>概览</a>' +
      '<a href="#/leads"' + cls("leads") + '>' + (SESSION && SESSION.is_hq ? '线索分配' : '我的线索') + '</a>' +
      '<a href="#/clients"' + cls("clients") + '>我的客户</a>' +
      '<a href="#/projects"' + cls("projects") + '>我的项目</a>' +
      "</div>";
  }

  /* ---------- 登录 ---------- */

  function renderLogin() {
    sessionBox.hidden = true;
    h(
      '<section class="card login-card">' +
      "<h1>渠道商控制台</h1>" +
      '<p class="muted small">使用你的接入密钥登录。密钥仅在服务端使用，不会保存在浏览器。</p>' +
      '<div id="login-msg"></div>' +
      '<label for="k">接入密钥</label>' +
      '<input id="k" type="password" autocomplete="off" placeholder="sk-..." />' +
      '<div class="mt"><button class="btn" id="do-login">登录</button></div>' +
      "</section>"
    );
    var btn = document.getElementById("do-login");
    var input = document.getElementById("k");
    function submit() {
      var v = (input.value || "").trim();
      if (!v) { document.getElementById("login-msg").innerHTML = notice("err", "请输入密钥。"); return; }
      btn.disabled = true;
      sessionApi("POST", { api_key: v }).then(function (s) {
        btn.disabled = false;
        if (!s) { document.getElementById("login-msg").innerHTML = notice("err", "密钥无效或缺失。"); return; }
        SESSION = s;
        input.value = "";
        paintSession();
        go("#/dashboard");
      }).catch(function () {
        btn.disabled = false;
        document.getElementById("login-msg").innerHTML = notice("err", "登录失败，请稍后重试。");
      });
    }
    btn.addEventListener("click", submit);
    input.addEventListener("keydown", function (e) { if (e.key === "Enter") { submit(); } });
    input.focus();
  }

  function paintSession() {
    if (!SESSION) { sessionBox.hidden = true; return; }
    sessionBox.hidden = false;
    whoEl.textContent = SESSION.tenant_id + " · " + SESSION.role +
      (SESSION.can_write ? "" : "（只读）");
  }

  /* ---------- 概览 ---------- */

  function renderDashboard() {
    h(nav("dashboard") + '<section class="card"><p class="muted">正在加载概览…</p></section>');
    Promise.all([api("GET", "/clients"), api("GET", "/projects")])
      .then(function (res) {
        var clients = res[0] || [], projects = res[1] || [];
        var active = clients.filter(function (c) { return c.is_active; }).length;
        /* 状态比较统一小写化：API 返回小写 snake_case（如 "in_execution"），
           原实现按大写常量比较导致概览卡「进行中项目/已交付」恒为 0（2026-10-13 修复）。 */
        var stOf = function (p) { return String(p.status || "").toLowerCase(); };
        var running = projects.filter(function (p) {
          return stOf(p) === "in_execution" || stOf(p) === "approved";
        }).length;
        var delivered = projects.filter(function (p) { return stOf(p) === "delivered"; }).length;

        var recent = projects.slice().sort(function (a, b) {
          return String(b.updated_at || b.created_at || "").localeCompare(String(a.updated_at || a.created_at || ""));
        }).slice(0, 8);

        var rows = recent.length ? recent.map(function (p) {
          return "<tr>" +
            "<td><a href=\"#/project/" + encodeURIComponent(p.project_id) + "\">" + esc(p.project_id) + "</a></td>" +
            "<td>" + esc(p.client_id) + "</td>" +
            "<td>" + stageChip(p.service_stage_label || p.service_stage) + "</td>" +
            "<td>" + esc(p.status) + "</td>" +
            "<td>" + pct(progOf(p)) + "%</td>" +
            "</tr>";
        }).join("") : '<tr><td colspan="5" class="muted">暂无项目。</td></tr>';

        h(nav("dashboard") +
          '<div class="row">' +
          kpiCard("客户总数", clients.length) +
          kpiCard("启用客户", active) +
          kpiCard("进行中项目", running) +
          kpiCard("已交付", delivered) +
          "</div>" +
          '<section class="card mt">' +
          "<h2>最近项目</h2>" +
          "<table><thead><tr><th>项目</th><th>客户</th><th>阶段</th><th>状态</th><th>进度</th></tr></thead>" +
          "<tbody>" + rows + "</tbody></table>" +
          "</section>");
      })
      .catch(handleErr);
  }

  function kpiCard(label, val) {
    return '<div class="card"><div class="kpi">' + esc(val) + "</div>" +
      '<div class="kpi-label">' + esc(label) + "</div></div>";
  }

  /* ---------- 客户 ---------- */

  function renderClients() {
    h(nav("clients") + '<section class="card"><p class="muted">正在加载客户…</p></section>');
    api("GET", "/clients").then(function (list) {
      list = list || [];
      var rows = list.length ? list.map(function (c) {
        return "<tr>" +
          "<td>" + esc(c.name) + "</td>" +
          "<td>" + esc(c.industry || "—") + "</td>" +
          "<td>" + (c.website ? '<a href="' + esc(c.website) + '" target="_blank" rel="noopener noreferrer">' + esc(c.website) + "</a>" : "—") + "</td>" +
          "<td>" + (c.is_active ? chip("启用", "ok") : chip("停用", "err")) + "</td>" +
          "<td>" + esc((c.created_at || "").slice(0, 10)) + "</td>" +
          "</tr>";
      }).join("") : '<tr><td colspan="5" class="muted">还没有客户。</td></tr>';

      var canWrite = SESSION && SESSION.can_write;
      var form = canWrite
        ? '<section class="card"><h2>新建客户</h2><div id="c-msg"></div>' +
          '<div class="row">' +
          '<div class="col"><label for="cn">客户名称 *</label><input id="cn" /></div>' +
          '<div class="col"><label for="ci">行业</label><input id="ci" /></div>' +
          "</div>" +
          '<div class="row">' +
          '<div class="col"><label for="cw">网站</label><input id="cw" placeholder="https://" /></div>' +
          '<div class="col"><label for="ce">联系邮箱</label><input id="ce" type="email" /></div>' +
          "</div>" +
          '<div class="mt"><button class="btn" id="c-save">创建客户</button></div>' +
          "</section>"
        : notice("info", "当前身份为只读，无法创建客户。");

      h(nav("clients") +
        '<section class="card"><h2>我的客户（' + list.length + "）</h2>" +
        "<table><thead><tr><th>名称</th><th>行业</th><th>网站</th><th>状态</th><th>创建</th></tr></thead>" +
        "<tbody>" + rows + "</tbody></table></section>" + form);

      var save = document.getElementById("c-save");
      if (save) {
        save.addEventListener("click", function () {
          var body = {
            name: (document.getElementById("cn").value || "").trim(),
            industry: (document.getElementById("ci").value || "").trim(),
            website: (document.getElementById("cw").value || "").trim(),
            contact_email: (document.getElementById("ce").value || "").trim()
          };
          var box = document.getElementById("c-msg");
          if (!body.name) { box.innerHTML = notice("err", "请填写客户名称。"); return; }
          save.disabled = true;
          api("POST", "/clients", body).then(function () {
            renderClients();
          }).catch(function (e) {
            save.disabled = false;
            box.innerHTML = notice("err", "创建失败：" + e.message);
          });
        });
      }
    }).catch(handleErr);
  }

  /* ---------- 项目 ---------- */

  function renderProjects() {
    h(nav("projects") + '<section class="card"><p class="muted">正在加载项目…</p></section>');
    Promise.all([api("GET", "/projects"), api("GET", "/clients")]).then(function (res) {
      var list = res[0] || [], clients = res[1] || [];
      var rows = list.length ? list.map(function (p) {
        return "<tr>" +
          "<td><a href=\"#/project/" + encodeURIComponent(p.project_id) + "\">" + esc(p.project_id) + "</a></td>" +
          "<td>" + esc(p.client_id) + "</td>" +
          "<td>" + stageChip(p.service_stage_label || p.service_stage) + "</td>" +
          "<td>" + esc(p.status) + "</td>" +
          "<td>" + pct(progOf(p)) + "%</td>" +
          "</tr>";
      }).join("") : '<tr><td colspan="5" class="muted">还没有项目。</td></tr>';

      var canWrite = SESSION && SESSION.can_write;
      var options = clients.map(function (c) {
        return '<option value="' + esc(c.client_id) + '">' + esc(c.name) + "（" + esc(c.client_id) + "）</option>";
      }).join("");

      var form = canWrite
        ? '<section class="card"><h2>提交服务需求</h2>' +
          '<p class="muted small">渠道商仅提交客户需求；报价、最终服务范围与交付周期由总部确认。</p><div id="p-msg"></div>' +
          (clients.length ? "" : notice("info", "请先创建至少一个客户。")) +
          '<div class="row">' +
          '<div class="col"><label for="pc">客户 *</label><select id="pc">' + options + "</select></div>" +
          '<div class="col"><label for="ps">服务类型</label><select id="ps">' +
          '<option value="diagnosis">GEO / SEO 诊断</option>' +
          '<option value="competitor_analysis">竞品 GEO / SEO 分析</option>' +
          '<option value="intervention">GEO 增长解决方案</option>' +
          '<option value="measurement">GEO / SEO 效果监控</option>' +
          '<option value="full_geo_project">完整 GEO 增长项目</option>' +
          "</select></div>" +
          "</div>" +
          '<div class="row">' +
          '<div class="col"><label for="market-scope">市场范围</label><select id="market-scope">' +
          '<option value="single">单一国家/地区</option><option value="multi" selected>多个国家/地区</option><option value="global">全球市场</option>' +
          '</select></div>' +
          '<div class="col"><label for="service-duration">服务期限</label><select id="service-duration">' +
          '<option value="one_time">单次交付</option><option value="1_month">1 个月</option><option value="3_months">3 个月</option>' +
          '<option value="6_months">6 个月</option><option value="12_months">12 个月</option><option value="to_be_determined" selected>待方案确定</option>' +
          '</select></div></div>' +
          '<label for="pm">目标国家/地区（可多选；全球市场可留空）</label><select id="pm" multiple size="5">' +
          '<option value="US">US — 美国</option><option value="DE">DE — 德国</option><option value="GB">GB — 英国</option>' +
          '<option value="CA">CA — 加拿大</option><option value="AU">AU — 澳大利亚</option><option value="FR">FR — 法国</option><option value="JP">JP — 日本</option>' +
          '</select>' +
          '<label for="pm-custom">其他国家/地区代码（逗号分隔，可选）</label><input id="pm-custom" placeholder="例如：IT, ES, NL, BR" />' +
          '<p class="muted small">国家/地区与目标语言分开设置；全球市场不要求逐国勾选。可在下方补充任意国家或地区。</p>' +
          '<label for="target-languages">目标语言（可多选）</label><select id="target-languages" multiple size="5">' +
          '<option value="English">English</option><option value="German">German</option><option value="Spanish">Spanish</option>' +
          '<option value="French">French</option><option value="Japanese">Japanese</option><option value="Chinese">Chinese</option>' +
          '</select>' +
          '<label for="languages-custom">其他目标语言（逗号分隔，可选）</label><input id="languages-custom" placeholder="例如：Italian, Portuguese, Korean" />' +
          '<label for="pp">目标产品/服务（逗号分隔）</label><input id="pp" />' +
          '<label for="pq">业务问题</label><textarea id="pq" placeholder="我们的品牌为什么没有出现在 AI 回答里？"></textarea>' +
          '<div class="mt"><button class="btn" id="p-save"' +
          (clients.length ? "" : " disabled") + ">提交需求</button></div>" +
          "</section>"
        : notice("info", "当前身份为只读，无法提交服务需求。");

      h(nav("projects") +
        '<section class="card"><h2>我的项目（' + list.length + "）</h2>" +
        "<table><thead><tr><th>项目</th><th>客户</th><th>阶段</th><th>状态</th><th>进度</th></tr></thead>" +
        "<tbody>" + rows + "</tbody></table></section>" + form);

      var save = document.getElementById("p-save");
      if (save) {
        save.addEventListener("click", function () {
          function csv(id) {
            return (document.getElementById(id).value || "")
              .split(",").map(function (s) { return s.trim(); })
              .filter(function (s) { return s.length; });
          }
          function selectedValues(id) {
            var el = document.getElementById(id);
            return Array.prototype.filter.call(el.options, function (o) { return o.selected; })
              .map(function (o) { return o.value; });
          }
          function unique(values) {
            var seen = {};
            return values.filter(function (v) {
              var key = String(v).trim().toLowerCase();
              if (!key || seen[key]) { return false; }
              seen[key] = true;
              return true;
            });
          }
          var body = {
            tenant_id: SESSION.tenant_id,
            client_id: document.getElementById("pc").value,
            service: document.getElementById("ps").value,
            market_scope: document.getElementById("market-scope").value,
            target_market: unique(selectedValues("pm").concat(csv("pm-custom").map(function (v) { return v.toUpperCase(); }))),
            target_languages: unique(selectedValues("target-languages").concat(csv("languages-custom"))),
            service_duration: document.getElementById("service-duration").value,
            target_products: csv("pp"),
            business_question: (document.getElementById("pq").value || "").trim()
          };
          var box = document.getElementById("p-msg");
          if (!body.client_id) { box.innerHTML = notice("err", "请选择客户。"); return; }
          if (body.market_scope === "single" && body.target_market.length !== 1) {
            box.innerHTML = notice("err", "单一国家/地区请准确选择 1 个目标市场。"); return;
          }
          if (body.market_scope === "multi" && body.target_market.length < 2) {
            box.innerHTML = notice("err", "多个国家/地区请至少选择 2 个目标市场；全球市场可切换为全球。"); return;
          }
          save.disabled = true;
          api("POST", "/projects", body).then(function (p) {
            go("#/project/" + encodeURIComponent(p.project_id));
          }).catch(function (e) {
            save.disabled = false;
            box.innerHTML = notice("err", "提交失败：" + e.message);
          });
        });
      }
    }).catch(handleErr);
  }

  /* ---------- Website Lead / HQ assignment queue ---------- */

  function renderLeads(selectedTenant) {
    var isHq = !!(SESSION && SESSION.is_hq);
    selectedTenant = isHq ? (selectedTenant || "HQ-INTAKE") : "";
    h(nav("leads") + '<section class="card"><p class="muted">正在加载线索…</p></section>');

    var tenantsPromise = isHq
      ? api("GET", "/leads/assignable-tenants").then(function (x) { return x.tenants || []; })
      : Promise.resolve([]);
    var leadsPath = "/leads" + (isHq && selectedTenant ? "?tenant_id=" + encodeURIComponent(selectedTenant) : "");

    Promise.all([tenantsPromise, api("GET", leadsPath)]).then(function (res) {
      var tenants = res[0] || [];
      var leads = res[1] || [];
      var filterHtml = isHq
        ? '<div class="row"><div class="col"><label for="lead-filter">查看队列</label><select id="lead-filter">' +
          '<option value="HQ-INTAKE"' + (selectedTenant === "HQ-INTAKE" ? " selected" : "") + '>待分配（HQ）</option>' +
          tenants.map(function (t) { return '<option value="' + esc(t) + '"' + (selectedTenant === t ? " selected" : "") + '>' + esc(t) + '</option>'; }).join("") +
          '</select></div></div>'
        : '<p class="muted small">仅显示已分配给当前渠道商的线索；未分配线索由总部管理。</p>';

      var cards = leads.length ? leads.map(function (lead) {
        var contact = lead.contact || {};
        var status = lead.intake_status || "—";
        var content = '<section class="card sub lead-card">' +
          '<div class="row"><div class="col"><h2>' + esc(contact.company || contact.name || "网站线索") + '</h2>' +
          '<p class="small muted">' + esc(lead.lead_id) + ' · ' + esc(status) + '</p></div>' +
          '<div class="col"><p class="small">联系人：' + esc(contact.name || "—") + '</p>' +
          '<p class="small">邮箱：' + esc(contact.email || "—") + '</p>' +
          '<p class="small">网站：' + esc(contact.domain || "—") + '</p></div></div>' +
          '<p>' + esc(lead.message || "") + '</p>' +
          (lead.client_id ? '<p class="small muted">客户：' + esc(lead.client_id) + '</p>' : "") +
          (lead.project_id ? '<p class="small muted">项目：' + esc(lead.project_id) + '</p>' : "");

        if (isHq && lead.tenant_id === "HQ-INTAKE" && status === "pending_assignment") {
          var tenantOptions = tenants.map(function (t) { return '<option value="' + esc(t) + '">' + esc(t) + '</option>'; }).join("");
          content += '<div class="row"><div class="col"><label for="assign-' + esc(lead.lead_id) + '">分配给渠道商</label>' +
            '<select id="assign-' + esc(lead.lead_id) + '">' + tenantOptions + '</select></div>' +
            '<div class="col"><label for="client-' + esc(lead.lead_id) + '">客户名称</label><input id="client-' + esc(lead.lead_id) + '" value="' + esc(contact.company || contact.name || "Website Lead") + '" /></div></div>' +
            '<div class="mt"><button class="btn" data-assign="' + esc(lead.lead_id) + '">分配并创建客户</button></div>';
        } else if (isHq && lead.tenant_id !== "HQ-INTAKE" && lead.client_id && status !== "converted_project") {
          content += '<div class="mt"><button class="btn" data-convert="' + esc(lead.lead_id) + '">创建项目并进入总部交付</button></div>';
        }
        return content + '</section>';
      }).join("") : '<div class="empty">当前队列没有线索。</div>';

      h(nav("leads") + '<section class="card"><h1>' + (isHq ? '网站线索与人工分配' : '分配给我的线索') + '</h1>' +
        '<p class="muted small">网站线索先持久化，再进入 HQ 队列；不设置自动分配或佣金规则。</p>' + filterHtml + '</section>' + cards);

      var filter = document.getElementById("lead-filter");
      if (filter) { filter.addEventListener("change", function () { renderLeads(filter.value); }); }
      Array.prototype.forEach.call(document.querySelectorAll("[data-assign]"), function (btn) {
        btn.addEventListener("click", function () {
          var id = btn.getAttribute("data-assign");
          var tenant = document.getElementById("assign-" + id).value;
          var clientName = (document.getElementById("client-" + id).value || "").trim();
          btn.disabled = true;
          api("POST", "/leads/" + encodeURIComponent(id) + "/assign", {
            tenant_id: tenant, create_client: true, client_name: clientName
          }).then(function () { renderLeads(selectedTenant); }).catch(function (e) {
            btn.disabled = false;
            h(nav("leads") + notice("err", "分配失败：" + e.message) + '<p><a href="#/leads">返回线索</a></p>');
          });
        });
      });
      Array.prototype.forEach.call(document.querySelectorAll("[data-convert]"), function (btn) {
        btn.addEventListener("click", function () {
          var id = btn.getAttribute("data-convert");
          btn.disabled = true;
          api("POST", "/leads/" + encodeURIComponent(id) + "/convert", {
            target_market: [], target_products: [], business_question: ""
          }).then(function () { renderLeads(selectedTenant); }).catch(function (e) {
            btn.disabled = false;
            h(nav("leads") + notice("err", "创建项目失败：" + e.message) + '<p><a href="#/leads">返回线索</a></p>');
          });
        });
      });
    }).catch(handleErr);
  }

  /* ---------- 项目详情 ---------- */

  function renderProject(pid) {
    h(nav("projects") + '<section class="card"><p class="muted">正在加载项目…</p></section>');
    Promise.all([
      api("GET", "/projects/" + encodeURIComponent(pid)),
      api("GET", "/projects/" + encodeURIComponent(pid) + "/stage").catch(function () { return null; }),
      api("GET", "/reports?project_id=" + encodeURIComponent(pid)).catch(function () { return []; })
    ]).then(function (res) {
      var p = res[0], stage = res[1], reports = res[2] || [];

      /* 关键发现来源：项目级 key_findings 在本部署恒为空（执行流未接线），
         真正的发现随交付报告下发。因此项目级为空时回落到**最新一份报告**
         的 key_findings —— 否则渠道商会看到「暂无关键发现」而报告里明明有，
         这与「渠道商可以查看结果」直接冲突。 */
      function normFindings(list) {
        return (list || []).filter(function (x) { return x !== null && x !== undefined; });
      }
      function pickFindings() {
        var own = normFindings(p.key_findings);
        if (own.length) { return own; }
        // 按交付时间倒序（version 恒为 1，不能作为排序依据）
        var sorted = reports.slice().sort(byCreatedDesc);
        for (var i = 0; i < sorted.length; i++) {
          var rf = normFindings(sorted[i].key_findings);
          if (rf.length) { return rf; }
        }
        return [];
      }
      function findingLi(f) {
        if (typeof f === "string") { return "<li>" + esc(f) + "</li>"; }
        var sev = f.severity ? chip(f.severity, f.severity === "high" ? "err" : "warn") : "";
        var stmt = f.statement || f.title || f.summary || "";
        var rec = f.recommendation ? '<div class="small muted">建议：' + esc(f.recommendation) + "</div>" : "";
        if (!stmt && !rec) { return "<li>" + esc(JSON.stringify(f)) + "</li>"; }
        return "<li>" + esc(stmt) + " " + sev + rec + "</li>";
      }

      var findings = pickFindings();
      var findingsHtml = findings.length
        ? "<ul>" + findings.map(findingLi).join("") + "</ul>"
        : '<p class="muted small">暂无关键发现。</p>';

      var stagesHtml = "";
      if (stage && stage.stages) {
        stagesHtml = Object.keys(stage.stages).map(function (k) {
          var s = stage.stages[k] || {};
          return "<tr><td>" + esc(s.stage_label || s.label || k) + "</td><td>" +
            (s.status === "completed" ? chip("已完成", "ok")
              : s.status === "in_progress" ? chip("进行中", "warn")
              : chip("未开始")) + "</td></tr>";
        }).join("");
      }

      /* 报告展示策略：只完整呈现**最新一份**，其余折叠为「历史报告」。
       *
       * 为什么：`ReportService.create_report` 把 `version` 硬编码为 1，且
       * `POST /projects/{id}/deliver` 无幂等 —— 总部重复交付会产生多份**同名同版本**
       * 的报告。若全部平铺，渠道商会看到一叠无法区分的「v1」。
       * 服务层属 Stage-1 冻结基线（STAGE1-CODE-FREEZE §4「继续修改业务代码 = 破坏
       * 已验证基线」），故在展示层收敛：按交付时间倒序，只展开最新一份。
       */
      function byCreatedDesc(a, b) {
        return String(b.created_at || "").localeCompare(String(a.created_at || ""));
      }
      var sortedReports = reports.slice().sort(byCreatedDesc);
      var latest = sortedReports[0];
      var older = sortedReports.slice(1);

      function reportBody(r) {
        return '<p class="small muted">版本 v' + esc(r.version) + " · " +
          esc((r.created_at || "").slice(0, 19).replace("T", " ")) + "</p>" +
          '<p class="small">可见性评分：<strong>' + esc(r.visibility_score) + "</strong></p>" +
          (r.visibility_summary
            ? '<p class="small muted">提及率 ' + esc(r.visibility_summary.mention_rate || "—") +
              " · 推荐率 " + esc(r.visibility_summary.recommendation_rate || "—") +
              " · 查询数 " + esc(r.visibility_summary.total_queries || 0) + "</p>"
            : "") +
          (r.limitations && r.limitations.length
            ? '<p class="small muted">局限：' + esc(r.limitations.join("；")) + "</p>" : "") +
          (r.next_steps && r.next_steps.length
            ? '<p class="small"><strong>下一步</strong></p><ul>' +
              r.next_steps.map(function (s) { return "<li>" + esc(s) + "</li>"; }).join("") + "</ul>"
            : "");
      }

      var reportsHtml = latest
        ? '<section class="card sub">' +
            "<h2>" + esc(latest.title) + "</h2>" + reportBody(latest) + "</section>" +
            (older.length
              ? '<div class="empty">另有 ' + older.length + " 份历史报告（同一交付链路重复执行产生）：" +
                "<ul>" + older.map(function (r) {
                  return "<li>" + esc(r.report_id) + " · " +
                    esc((r.created_at || "").slice(0, 19).replace("T", " ")) + "</li>";
                }).join("") + "</ul></div>"
              : "")
        : '<div class="empty">报告尚未生成。总部完成交付后，报告会出现在这里。</div>';

      var serviceLabels = {
        visibility_audit: "GEO / SEO 诊断（旧记录）",
        diagnosis: "GEO / SEO 诊断",
        competitor_analysis: "竞品 GEO / SEO 分析",
        intervention: "GEO 增长解决方案",
        measurement: "GEO / SEO 效果监控",
        remeasurement: "GEO / SEO 效果监控",
        full_geo_project: "完整 GEO 增长项目"
      };
      var marketScopeLabels = { single: "单一国家/地区", multi: "多个国家/地区", global: "全球市场", unspecified: "未记录（历史项目）" };
      var durationLabels = {
        one_time: "单次交付", "1_month": "1 个月", "3_months": "3 个月",
        "6_months": "6 个月", "12_months": "12 个月", to_be_determined: "待方案确定"
      };
      var marketText = p.market_scope === "global"
        ? ("全球市场" + ((p.target_market || []).length ? "（重点：" + p.target_market.join(", ") + "）" : ""))
        : ((p.target_market || []).join(", ") || "待确认");
      var languageText = (p.target_languages || []).join(", ") || "待确认";
      h(nav("projects") +
        '<section class="card">' +
        "<h1>" + esc(p.project_id) + "</h1>" +
        '<p class="muted small">客户 ' + esc(p.client_id) + " · 状态 " + esc(p.status) + "</p>" +
        '<div class="chips">' + stageChip(p.service_stage_label || p.service_stage) + "</div>" +
        '<section class="card sub"><h2>客户需求概览</h2>' +
        '<p class="small">服务类型：' + esc(serviceLabels[p.service] || p.service || "历史项目，未记录") + '</p>' +
        '<p class="small">市场范围：' + esc(marketScopeLabels[p.market_scope] || p.market_scope || "未记录") + '</p>' +
        '<p class="small">目标国家/地区：' + esc(marketText) + '</p>' +
        '<p class="small">目标语言：' + esc(languageText) + '</p>' +
        '<p class="small">服务期限：' + esc(durationLabels[p.service_duration] || p.service_duration || "待方案确定") + '</p></section>' +
        '<div class="bar"><i class="' + wClass(progOf(p)) + '"></i></div>' +
        '<p class="small muted">进度 ' + pct(progOf(p)) + "%</p>" +
        "</section>" +
        '<section class="card"><h2>关键发现</h2>' + findingsHtml + "</section>" +
        (stagesHtml ? '<section class="card"><h2>交付阶段</h2><table><tbody>' + stagesHtml + "</tbody></table></section>" : "") +
        '<section class="card"><h2>交付报告</h2>' + reportsHtml + "</section>" +
        '<p class="small muted"><a href="#/projects">← 返回项目列表</a></p>');
    }).catch(handleErr);
  }

  /* ---------- 错误 ---------- */

  function handleErr(e) {
    if (e && e.status === 401) {
      SESSION = null;
      paintSession();
      renderLogin();
      return;
    }
    h('<section class="card">' + notice("err", "加载失败：" + (e && e.message ? e.message : "未知错误")) +
      '<p class="small"><a href="#/dashboard">返回概览</a></p></section>');
  }

  /* ---------- 启动 ---------- */

  document.getElementById("logout").addEventListener("click", function () {
    sessionApi("DELETE", null).then(function () {
      SESSION = null;
      paintSession();
      go("#/login");
      renderLogin();
    });
  });

  window.addEventListener("hashchange", route);

  sessionApi("GET", null).then(function (s) {
    if (s) {
      SESSION = s;
      paintSession();
    }
    route();
  }).catch(function () { route(); });
})();
