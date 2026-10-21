/* Opaque-origin native view: all reads and writes cross the authorized parent bridge. */
window.OperatorFrame = (() => {
  "use strict";
  const params = new URLSearchParams(location.search), nonce = params.get("channel"), pending = new Map();
  let serial = 0, dirty = false, resolveReady;
  const ready = new Promise(resolve => { resolveReady = resolve; });
  const send = payload => parent.postMessage({ ...payload, channel: nonce, source: "geo-operator-frame" }, "*");
  const views = new Set(["dashboard","products","personas","scenarios","questions","clusters","briefs","citations","trends","entities","gaps","keywords","seo","prompts","manual"]);
  function api(method, path, body) {
    return new Promise((resolve, reject) => {
      const id = ++serial;
      const timer = setTimeout(() => { pending.delete(id); reject(new Error("请求超时，结果尚未确认。请重试原操作；不要重复创建另一份记录。")); }, 45000);
      pending.set(id, { resolve, reject, timer });
      if(path.startsWith('/__export/'))send({type:'export',id,collection:path.slice(10),params:body||{}});
      else if(path.startsWith('/__paged/'))send({type:'paged',id,collection:path.slice(9).split('?')[0],params:body||{}});
      else send({ type: "api", id, method, path, body });
    });
  }
  window.addEventListener("message", event => {
    const m = event.data;
    if (event.source !== parent || !m || m.channel !== nonce || m.source !== "geo-operator-host") return;
    if (m.type === "init") {
      const view = views.has(params.get("view")) ? params.get("view") : "dashboard";
      try { history.replaceState(null, "", location.pathname + location.search + "#/" + view); }
      catch { location.hash = "#/" + view; }
      resolveReady();
    }
    if (m.type === "response") {
      const p = pending.get(m.id); if (!p) return;
      clearTimeout(p.timer); pending.delete(m.id);
      if (m.error) p.reject(new Error(m.error)); else p.resolve(m.result);
    }
  });
  function setDirty(value) { dirty = value; send({ type: "dirty", value }); }
  function showError(message, retry) {
    const host = document.getElementById("view");
    host.replaceChildren(); const box = document.createElement("section"); box.className = "operator-load-error";
    const title = document.createElement("h2"); title.textContent = "暂时无法读取";
    const text = document.createElement("p"); text.textContent = message;
    const button = document.createElement("button"); button.className = "btn btn-primary"; button.textContent = "重试"; button.onclick = retry;
    box.append(title,text,button); host.append(box);
  }
  function enhanceModal(root) {
    const modal = root.querySelector(".modal"), save = root.querySelector("#ms"); if (!modal || !save || save.dataset.protected) return;
    save.dataset.protected = "true";
    modal.setAttribute("role","dialog"); modal.setAttribute("aria-modal","true");
    const heading = modal.querySelector("h3"); heading.id = "operator-dialog-title"; modal.setAttribute("aria-labelledby",heading.id);
    const old = save.onclick;
    save.onclick = async event => {
      if (save.disabled) return;
      save.disabled = true;
      modal.querySelector(".modal-error")?.remove();
      try { await old?.(event); if (!root.querySelector(".modal")) setDirty(false); }
      catch (error) {
        const note = document.createElement("p"); note.className = "modal-error"; note.setAttribute("role","alert"); note.textContent = error.message;
        modal.querySelector(".modal-body").prepend(note); note.tabIndex = -1; note.focus();
      } finally { save.disabled = false; }
    };
    const close = root.querySelector("#mx"); close?.setAttribute("aria-label","关闭对话框");
    for (const button of [close,root.querySelector("#mc")]) {
      if (!button) continue; const handler = button.onclick;
      button.onclick = event => { if (!dirty || confirm("关闭将放弃尚未保存的输入。继续关闭？")) { setDirty(false); handler?.(event); } };
    }
    const backdrop = root.querySelector("#mb"), oldBackdrop = backdrop.onclick;
    backdrop.onclick = event => { if (event.target === backdrop && dirty && !confirm("放弃尚未保存的输入？")) return; if(event.target === backdrop)setDirty(false); oldBackdrop?.(event); };
    modal.addEventListener("input", () => setDirty(true));
    modal.addEventListener("change", () => setDirty(true));
    const opener = document.activeElement;
    setTimeout(() => (modal.querySelector("input,textarea,select,button") || modal).focus(),0);
    modal.addEventListener("keydown", event => {
      const focusable = [...modal.querySelectorAll("button,input,select,textarea,a[href],[tabindex]")].filter(el => !el.disabled && el.tabIndex >= 0 && el.offsetParent);
      if (event.key === "Escape") { event.preventDefault(); close?.click(); opener?.focus(); }
      if (event.key === "Tab" && focusable.length) {
        if(event.shiftKey && document.activeElement === focusable[0]) { event.preventDefault(); focusable.at(-1).focus(); }
        else if(!event.shiftKey && document.activeElement === focusable.at(-1)) { event.preventDefault(); focusable[0].focus(); }
      }
    });
  }
  function prepareView() {
    for (const el of document.querySelectorAll('#add-p,[data-act="del"],[data-del],[data-mdel],[data-cdel],[data-del-kw]')) {
      el.disabled = true; el.title = el.id === "add-p" ? "请先在项目中建立授权资源绑定" : "物理删除未开放，避免破坏关联与证据链";
      el.setAttribute("aria-disabled","true");
    }
    for(const id of ["dash-realtime-btn","realtime-btn","realtime-query","ai-score-batch","ai-cluster"]){
      const el=document.getElementById(id);if(!el)continue;el.disabled=true;el.title="外部模型与实时采集未开放；可使用提示词、人工评分、人工建簇及检查记录";
    }
    document.querySelectorAll("[data-ai],[data-aibrief],[data-ai-score],[data-ai-brief]").forEach(el=>{el.disabled=true;el.title="自动模型未开放，请人工维护或使用提示词库";});
  }
  document.addEventListener("DOMContentLoaded", () => {
    new MutationObserver(() => { prepareView(); enhanceModal(document.getElementById("modal-root")); window.OperatorNativePagination?.mount(); }).observe(document.body,{childList:true,subtree:true});
    document.addEventListener("click", event => {
      const link=event.target.closest("a[href]"); if(!link)return;
      const href=link.getAttribute("href");
      if(href.startsWith("#"))return;
      event.preventDefault();
      try{const url=new URL(href);if(["https:","http:"].includes(url.protocol))send({type:"external-link",url:url.href});}catch{}
    });
    send({ type:"ready" });
  });
  window.addEventListener("unhandledrejection", event => { event.preventDefault(); if(event.reason?.message && !String(event.reason.message).includes("stale")) { const modal=document.querySelector(".modal-body"); if(modal){const note=document.createElement("p");note.className="modal-error";note.setAttribute("role","alert");note.textContent=event.reason.message;modal.prepend(note);} } });
  window.addEventListener("error", event => {
    if(event.filename && /operator-(native|frame)\.js/.test(event.filename))send({type:"frame-error",message:String(event.message||"专业界面运行错误")});
  });
  return {ready,api,exportCsv(collection,params){return api('GET','/__export/'+collection,params);},showError,enhanceModal,view(view){send({type:"view",view});},beforeNavigate(){if(dirty&&!confirm("切换模块将放弃未保存的输入。继续？"))return false;setDirty(false);return true;},copy(text){return new Promise((resolve,reject)=>{const id=++serial;const timer=setTimeout(()=>{pending.delete(id);reject(new Error("复制未获确认，请手动选择文字。"));},10000);pending.set(id,{resolve,reject,timer});send({type:"copy",id,text});});}};
})();
