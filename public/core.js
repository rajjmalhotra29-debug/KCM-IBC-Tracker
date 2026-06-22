/* KCM IBC Tracker — shared core (used by client.html and master.html).
   Renders the IBBI company feed: cards, search, filters, sort, pagination,
   research links, engage CTA, aggregate track record. NO client data here.
   master.js layers password/decryption/matching/settings on top via window.CORE. */
(function () {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const esc = (s) => (s == null ? "" : String(s)).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

  // ---- config / state ----
  const CFG = { brand: "kcm", dataUrl: "data.json", fallbackUrl: "data.json" };
  let DATA = null;
  let sortMode = "new";          // new | bid | fit
  let q = "", fStage = "", fSector = "", fMatched = false;
  const PAGE_SIZE = 30;
  let shown = PAGE_SIZE;

  const BRANDS = {
    kcm: { name: "KCM IBC Finder", glyph: "K",
      tagline: "Distressed-asset tracker — IBBI companies in IBC, updated daily",
      title: "KCM IBC Finder · K C Mehta & Co" },
    jarvis: { name: "Jarvis", glyph: "J",
      tagline: "Insolvency opportunity desk — IBBI companies in IBC",
      title: "Jarvis — IBC Origination Desk" },
  };

  // ---- helpers ----
  function toast(m) { const t = $("toast"); if (!t) return; t.textContent = m; t.classList.add("show"); setTimeout(() => t.classList.remove("show"), 2800); }
  function openModal(id) { const e = $(id); if (e) e.classList.add("show"); }
  function closeModal(id) { const e = $(id); if (e) e.classList.remove("show"); }
  function fmtCr(v) { return "₹" + (Math.round((+v || 0) * 10) / 10).toLocaleString("en-IN") + " cr"; }

  const MON = { jan:0,feb:1,mar:2,apr:3,may:4,jun:5,jul:6,aug:7,sep:8,oct:9,nov:10,dec:11 };
  function parseDate(s) {
    if (!s) return null; s = String(s).trim();
    let m = s.match(/^(\d{1,2})[-/](\d{1,2})[-/](\d{4})$/);          // DD-MM-YYYY
    if (m) return new Date(+m[3], +m[2] - 1, +m[1]);
    const p = s.split(/\s+/);                                         // DD Mon YYYY
    if (p.length === 3 && MON[p[1].slice(0,3).toLowerCase()] !== undefined) return new Date(+p[2], MON[p[1].slice(0,3).toLowerCase()], +p[0]);
    return null;
  }
  function today0() { const d = new Date(); d.setHours(0,0,0,0); return d; }
  function daysUntil(s) { const d = parseDate(s); return d ? Math.round((d - today0()) / 86400000) : null; }
  function announceTs(t) { const d = parseDate(t.admit) || parseDate(t.announcement_date); return d ? d.getTime() : 0; }
  function bidDays(t) { if (t.is_liq) return null; return daysUntil(t.form_g_by); }
  function claimsDays(t) { const d = daysUntil(t.claims_by); return d === null ? t.claims_days : d; }
  function dlClass(d) { if (d === null) return "dl-ok"; if (d < 0) return "dl-closed"; return d <= 5 ? "dl-urgent" : d <= 12 ? "dl-soon" : "dl-ok"; }
  function dlText(t) { const d = claimsDays(t); if (d === null) return t.claims_by || "—"; if (d < 0) return "claims closed · " + t.claims_by; return d + "d · claims by " + t.claims_by; }
  function stageInfo(t) {
    if (t.is_liq) return { key: "liq", label: "Liquidation · auction route", cls: "st-liq" };
    const d = claimsDays(t);
    if (d !== null && d >= 0) return { key: "early", label: "Early stage · claims open", cls: "st-early" };
    return { key: "soon", label: "Form G approaching", cls: "st-soon" };
  }

  // ---- card building blocks ----
  function researchLinks(t) {
    const name = t.name || "", qq = encodeURIComponent(name);
    const isPrivate = /\bPVT\b|\bPRIVATE\b/i.test(name);
    const links = isPrivate
      ? [{ cls: "tof", label: "Tofler", typ: "private", url: `https://www.tofler.in/search?query=${qq}` },
         { cls: "", label: "VCCEdge", typ: "sub", url: `https://www.vccedge.com/` }]
      : [{ cls: "scr", label: "Screener", typ: "listed", url: `https://www.screener.in/full-text-search/?q=${qq}` },
         { cls: "tof", label: "Tofler", typ: "filings", url: `https://www.tofler.in/search?query=${qq}` }];
    return `<div class="reslinks"><span class="reslabel">Financials</span>${links.map(l =>
      `<a class="reslink ${l.cls}" href="${l.url}" target="_blank" rel="noopener" title="Open ${esc(name)} on ${l.label}">${l.label} <span class="typ">${l.typ}</span><span class="ar">↗</span></a>`).join("")}</div>`;
  }
  function formgPanel(t) {
    if (t.is_liq) return `<div class="panel"><h4><span class="ic"></span>Process &amp; entry route</h4>
      <div class="prow"><span class="lab">Stage</span><span class="val">Liquidation</span></div>
      <div class="prow"><span class="lab">Acquisition route</span><span class="val">Asset sale via e-auction</span></div>
      <div class="prow"><span class="lab">Auction notice</span><span class="val"><span class="tag t-pending">AWAITED</span></span></div>
      <div class="prow"><span class="lab">Liquidator</span><span class="val">${esc(t.resolution_professional)}</span></div></div>`;
    return `<div class="panel"><h4><span class="ic"></span>Form G / process tracker</h4>
      <div class="prow"><span class="lab">Stage</span><span class="val">CIRP admitted · ${esc(t.admit)}</span></div>
      <div class="prow"><span class="lab">Form G (entry window)</span><span class="val"><span class="tag t-pending">PENDING</span></span></div>
      <div class="prow"><span class="lab">Expected by (≈75d)</span><span class="val">~ ${esc(t.form_g_by || '—')}</span></div>
      <div class="prow"><span class="lab">EoI contact</span><span class="val">${esc(t.resolution_professional)}</span></div></div>`;
  }
  function finPanel(t) {
    const d = claimsDays(t);
    const cs = (d !== null && d < 0) ? "collating (window closed)" : "collating (window open)";
    return `<div class="panel"><h4><span class="ic"></span>Financial snapshot</h4>
      <div class="prow"><span class="lab">Lead applicant / creditor</span><span class="val">${esc(t.applicant || '—')}</span></div>
      <div class="prow"><span class="lab">Total admitted claims</span><span class="val"><span class="tag t-live">${cs}</span></span></div>
      <div class="prow"><span class="lab">Revenue · net worth · debt</span><span class="val"><span class="tag t-sub">ON SUBSCRIPTION · MCA</span></span></div>
      <div class="prow"><span class="lab">Liquidation vs GC value</span><span class="val"><span class="tag t-locked">IN IM · ON EoI</span></span></div></div>`;
  }
  function engageBar(t) {
    return `<div class="engage"><span class="engage-q">Considering this asset for acquisition?</span>`
      + `<button class="engage-btn" data-co="${esc(t.name)}" onclick="CORE.openEngage(this)">Engage KCM on this asset →</button></div>`;
  }

  // ---- Engage form (lead → email to KCM via Web3Forms; mailto fallback) ----
  function ensureEngageModal() {
    if ($("engageModal")) return;
    document.body.insertAdjacentHTML("beforeend", `<div class="modal" id="engageModal"><div class="sheet">
      <div class="mhead"><div><h3>Engage K C Mehta &amp; Co</h3><div class="sub" id="engageRe">Tell us about your interest</div></div><button class="x" onclick="CORE.closeModal('engageModal')">✕</button></div>
      <div class="field"><label>Full name of contact person *</label><input id="eg_name"></div>
      <div class="field"><label>Name of your entity / company *</label><input id="eg_entity"></div>
      <div class="row2"><div class="field"><label>Email address *</label><input id="eg_email" type="email"></div><div class="field"><label>Phone (optional)</label><input id="eg_phone"></div></div>
      <div class="field"><label>Industry / sector of your company</label><input id="eg_sector"></div>
      <div class="field"><label>Brief description of your requirement / query *</label><textarea id="eg_req"></textarea></div>
      <input type="text" id="eg_botcheck" tabindex="-1" autocomplete="off" style="position:absolute;left:-9999px">
      <button class="btn primary" style="width:100%;justify-content:center" onclick="CORE.submitEngage()">Send to KCM</button>
      <div class="err" id="eg_err"></div><div class="ok" id="eg_ok"></div>
      <div class="sub" style="margin-top:6px;text-align:center;font-size:11px">Goes to KCM's M&amp;A advisory team.</div>
    </div></div>`);
  }
  let engageCo = "";
  function openEngage(btn) {
    engageCo = (btn && btn.dataset && btn.dataset.co) || "";
    // Preferred (M365): redirect to a Microsoft Form. Put the form's share/prefill link in
    // window.ENGAGE_FORM_URL; use {ASSET} where the company name should be pre-filled.
    const formUrl = window.ENGAGE_FORM_URL || "";
    if (formUrl) {
      const url = formUrl.includes("{ASSET}") ? formUrl.replace("{ASSET}", encodeURIComponent(engageCo)) : formUrl;
      window.open(url, "_blank", "noopener");
      return;
    }
    ensureEngageModal();
    $("engageRe").textContent = engageCo ? "Regarding: " + engageCo : "Tell us about your interest";
    ["eg_name","eg_entity","eg_email","eg_phone","eg_sector","eg_req"].forEach(i => { if ($(i)) $(i).value = ""; });
    $("eg_err").textContent = ""; $("eg_ok").textContent = "";
    openModal("engageModal"); setTimeout(() => $("eg_name") && $("eg_name").focus(), 50);
  }
  async function submitEngage() {
    const v = (id) => ($(id) ? $(id).value.trim() : "");
    const name = v("eg_name"), entity = v("eg_entity"), email = v("eg_email"), sector = v("eg_sector"), req = v("eg_req"), phone = v("eg_phone");
    $("eg_err").textContent = ""; $("eg_ok").textContent = "";
    if ($("eg_botcheck").value) return;                       // honeypot
    if (!name || !entity || !email || !req) { $("eg_err").textContent = "Please fill name, entity, email and requirement."; return; }
    if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) { $("eg_err").textContent = "Please enter a valid email address."; return; }
    const fields = { "Contact person": name, "Entity / Company": entity, "Email": email, "Phone": phone || "-",
      "Industry / Sector": sector || "-", "Requirement": req, "Asset of interest": engageCo || "-",
      "Source": "KCM IBC Finder (" + (window.MASTER_BLOB ? "master" : "public") + ")" };
    const subject = "KCM IBC Finder enquiry — " + (engageCo || entity);
    const key = window.ENGAGE_KEY || "";
    if (key) {
      try {
        const res = await fetch("https://api.web3forms.com/submit", {
          method: "POST", headers: { "Content-Type": "application/json", Accept: "application/json" },
          body: JSON.stringify({ access_key: key, subject, from_name: name, replyto: email, ...fields }),
        });
        const j = await res.json();
        if (j.success) { $("eg_ok").textContent = "Sent — KCM's M&A advisory team will be in touch."; setTimeout(() => closeModal("engageModal"), 1600); }
        else { $("eg_err").textContent = "Could not send: " + (j.message || "error") + "."; }
      } catch (e) { $("eg_err").textContent = "Network error — please try again."; }
    } else {
      const to = (DATA && DATA.contact_email) || "mna.advisory@kcmehta.com";
      const body = Object.entries(fields).map(([k, x]) => k + ": " + x).join("\n");
      window.location.href = `mailto:${to}?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(body)}`;
      $("eg_ok").textContent = "Opening your email app…";
    }
  }
  function matchRow(m) {
    const cls = m.conf_class === "g-ok" ? "prime" : m.conf_class === "g-warn" ? "mixed" : "cold";
    const fit = (m.synergy_type || "").toLowerCase();
    const fitLabel = { backward: "Backward", forward: "Forward", horizontal: "Horizontal" }[fit] || "Adjacency";
    return `<div class="match ${cls}">
      <div class="m-left">
        <div class="m-buyer">${esc(m.client)}</div>
        <span class="fit ${fit}">${fitLabel}</span>
        <div class="score"><div class="bar"><i style="width:${m.bar_w || Math.min(100, m.score * 2.5)}%"></i></div><b>${Math.round(m.score)}</b></div>
        <div class="matchedon"><b>matched on:</b> ${esc(m.matched_keywords || '—')}</div>
      </div>
      <div class="m-right">
        <div class="rat">${esc(m.rationale)}</div>
        <div class="gates">
          <span class="gate ${m.na_class || 'g-warn'}">29A <b>${esc(m.eligibility_29a || 'Verify')}</b></span>
          <span class="gate g-ok">KCM reach <b>${esc(m.reach || 'Verify')}</b></span>
          <span class="gate ${m.conf_class || 'g-warn'}">Data <b>${esc(m.confidence || 'MEDIUM')}</b></span>
        </div>
      </div>
    </div>`;
  }

  // ---- top-level renderers ----
  function applyBrand() {
    const b = (DATA && DATA.brand) || CFG.brand;
    const info = BRANDS[b] || BRANDS.kcm;
    document.body.dataset.brand = b;
    if ($("glyphLetter")) $("glyphLetter").textContent = info.glyph;
    if ($("brandName")) $("brandName").textContent = (CORE.titleOverride || info.name);
    if ($("tagline")) $("tagline").textContent = (CORE.taglineOverride || info.tagline);
    document.title = (CORE.titleOverride ? CORE.titleOverride + " · K C Mehta & Co" : info.title);
  }
  function setSrc() {
    const el = $("src"), t = $("srctxt"); if (!el || !t) return;
    el.className = "src snap"; t.textContent = "IBBI feed · updated " + (DATA ? DATA.generated : "");
  }
  function renderStats() {
    if (!$("stats")) return;
    const opps = DATA.opportunities;
    let soon = 0, liq = 0, matches = 0;
    opps.forEach(o => { const k = stageInfo(o.target).key; if (k === "liq") liq++; else if (k === "soon") soon++; matches += (o.match_count || 0); });
    const fourth = CORE.showMatches
      ? `<div class="stat amber"><div class="k">Client matches</div><div class="v">${matches}</div></div>`
      : `<div class="stat"><div class="k">Updated</div><div class="v" style="font-size:18px">${esc(DATA.generated || "—")}</div></div>`;
    $("stats").innerHTML = `
      <div class="stat teal"><div class="k">Live opportunities</div><div class="v">${opps.length}</div></div>
      <div class="stat amber"><div class="k">Approaching Form G</div><div class="v">${soon}</div></div>
      <div class="stat red"><div class="k">Liquidations</div><div class="v">${liq}</div></div>
      ${fourth}`;
  }
  function renderTrackRecord() {
    const el = $("trackRecord"); if (!el) return;
    const tr = (DATA && DATA.track_record) || { deals_closed: 0, value_fmv_inr_cr: 0 };
    if (!tr.deals_closed) { el.innerHTML = ""; return; }
    el.innerHTML = `<div class="trband">
      <div class="trcard"><div><div class="trk">Mandates Closed</div><div class="trv">${tr.deals_closed}</div><div class="trsub">Acquisition &amp; structuring by KCM</div></div></div>
      <div class="trcard gold"><div><div class="trk">Value Created · FMV</div><div class="trv">${fmtCr(tr.value_fmv_inr_cr)}</div><div class="trsub">Benefit enjoyed by clients</div></div></div>
    </div>`;
  }
  function populateSectors() {
    if (!$("fSector")) return;
    const sectors = new Set();
    (DATA.opportunities || []).forEach(o => {
      const s = (o.target.sector || "").trim();
      if (s && s.toLowerCase() !== "inferred from filing") s.split(/[,;]/).forEach(x => { const t = x.trim(); if (t) sectors.add(t); });
    });
    const sel = $("fSector"), cur = sel.value;
    sel.innerHTML = `<option value="">All sectors</option>` + [...sectors].sort().map(s => `<option value="${esc(s)}">${esc(s)}</option>`).join("");
    sel.value = cur;
  }

  function render() {
    if (!DATA || !$("list")) return;
    let rows = DATA.opportunities.slice();
    if (q) { const k = q.toLowerCase(); rows = rows.filter(o => (o.target.name + " " + o.target.sector + " " + o.target.applicant).toLowerCase().includes(k)); }
    if (fStage) rows = rows.filter(o => fStage === "liq" ? o.target.is_liq : !o.target.is_liq);
    if (fSector) rows = rows.filter(o => (o.target.sector || "").toLowerCase().includes(fSector.toLowerCase()));
    if (fMatched) rows = rows.filter(o => (o.match_count || 0) > 0);
    if ($("fClear")) $("fClear").style.display = (fStage || fSector || fMatched) ? "inline-block" : "none";

    if (sortMode === "new") rows.sort((a, b) => announceTs(b.target) - announceTs(a.target));
    else if (sortMode === "bid") rows.sort((a, b) => { const va = bidDays(a.target) ?? -1, vb = bidDays(b.target) ?? -1; return vb - va; });
    else rows.sort((a, b) => (b.matches?.[0]?.score ?? b.match_count ?? 0) - (a.matches?.[0]?.score ?? a.match_count ?? 0));

    let soon = 0, early = 0, liq = 0;
    rows.forEach(o => { const k = stageInfo(o.target).key; if (k === "soon") soon++; else if (k === "early") early++; else liq++; });
    const visible = rows.slice(0, shown);
    const sortLabel = sortMode === "new" ? "newest first" : sortMode === "bid" ? "days to bid" : "best fit";
    if ($("hiddenNote")) $("hiddenNote").innerHTML = `Showing ${visible.length} of ${rows.length} · sorted by <b>${sortLabel}</b> &nbsp;·&nbsp; <b style="color:var(--amber)">${soon} approaching Form G</b> · ${early} early-stage · ${liq} liquidation`;

    if (!rows.length) { $("list").innerHTML = `<div class="opp" style="padding:30px;text-align:center;color:var(--faint)">No companies match your search/filters.</div>`; if ($("loadMore")) $("loadMore").style.display = "none"; return; }

    $("list").innerHTML = visible.map((o, i) => {
      const t = o.target, si = stageInfo(t), bd = bidDays(t);
      const tools = (CORE.showMatches && typeof CORE.cardTools === "function") ? CORE.cardTools(o) : "";
      const matchesHtml = CORE.showMatches
        ? `<div class="matches">${tools}${(o.matches && o.matches.length)
            ? `<div class="mlabel">Matched clients · ${o.matches.length} (ranked by fit)</div>` + o.matches.map(matchRow).join("")
            : `<div class="nomatch">No company in your client master matches this opportunity yet.</div>`}</div>`
        : "";
      return `<div class="opp" style="animation-delay:${i * 40}ms">
        <div class="opp-head">
          <div class="opp-id">
            <div class="opp-name">${esc(t.name)} <span class="stagechip ${si.cls}">${si.label}${t.is_liq ? "" : (bd !== null ? " · ~" + bd + "d to bid" : "")}</span></div>
            <div class="vchain"><b>Sector ·</b> ${esc(t.sector || "inferred from filing")}</div>
            <div class="applicant">Applicant: ${esc(t.applicant || "—")}</div>
            ${researchLinks(t)}
          </div>
          <div class="opp-tags">
            <span class="stage ${t.stage_class}">${esc(t.stage_label || t.status)}</span>
            <span class="deadline">Claims <span class="dl-pill ${dlClass(claimsDays(t))}">${dlText(t)}</span></span>
            ${t.pa_pdf ? `<a class="formg-btn pdf" href="${esc(t.pa_pdf)}" target="_blank" rel="noopener">📄 Form A (PDF) ↗</a>` : ""}
            <a class="formg-btn" href="${esc(t.source_url || 'https://www.ibbi.gov.in/en/public-announcement')}" target="_blank" rel="noopener">Find on IBBI ↗</a>
            <span class="rp">${esc(t.resolution_professional)}</span>
          </div>
        </div>
        <div class="panels">${formgPanel(t)}${finPanel(t)}</div>
        ${matchesHtml}
        ${engageBar(t)}
      </div>`;
    }).join("");

    if ($("loadMore")) {
      if (rows.length > shown) { $("loadMore").style.display = "block"; $("loadMore").querySelector("button").textContent = `Load more · ${rows.length - shown} remaining`; }
      else $("loadMore").style.display = "none";
    }
  }

  function resetPaging() { shown = PAGE_SIZE; }
  function loadMore() { shown += PAGE_SIZE; render(); }

  async function load() {
    let data = null;
    try { data = await (await fetch(CFG.dataUrl, { cache: "no-store" })).json(); }
    catch (e) {
      if (CFG.fallbackUrl && CFG.fallbackUrl !== CFG.dataUrl) {
        try { data = await (await fetch(CFG.fallbackUrl, { cache: "no-store" })).json(); } catch (e2) {}
      }
    }
    if (!data && window.EMBEDDED_FEED) data = window.EMBEDDED_FEED;   // master: baked-in snapshot fallback
    if (!data) { toast("Could not load the IBBI feed."); return; }
    DATA = data;
    applyBrand(); setSrc(); renderTrackRecord(); populateSectors();
    if (typeof CORE.afterLoad === "function") CORE.afterLoad(DATA);  // master recomputes matches here
    renderStats(); render();
  }
  async function refresh() {
    const b = $("refreshBtn"); if (b) { b.classList.add("spinning"); b.disabled = true; }
    await load();
    if (b) { b.classList.remove("spinning"); b.disabled = false; }
    toast("Feed refreshed");
  }

  function wireControls() {
    const on = (id, ev, fn) => { const e = $(id); if (e) e[ev] = fn; };
    const setSort = (mode) => { sortMode = mode; ["sbNew","sbBid","sbFit"].forEach(id => { const e = $(id); if (e) e.classList.toggle("on", id === ({new:"sbNew",bid:"sbBid",fit:"sbFit"})[mode]); }); resetPaging(); render(); };
    on("sbNew", "onclick", () => setSort("new"));
    on("sbBid", "onclick", () => setSort("bid"));
    on("sbFit", "onclick", () => setSort("fit"));
    on("search", "oninput", (e) => { q = e.target.value.trim(); resetPaging(); render(); });
    on("fStage", "onchange", (e) => { fStage = e.target.value; resetPaging(); render(); });
    on("fSector", "onchange", (e) => { fSector = e.target.value; resetPaging(); render(); });
    on("fMatched", "onclick", () => { fMatched = !fMatched; $("fMatched").classList.toggle("on", fMatched); resetPaging(); render(); });
    on("fClear", "onclick", () => { fStage = fSector = ""; fMatched = false; if ($("fStage")) $("fStage").value = ""; if ($("fSector")) $("fSector").value = ""; if ($("fMatched")) $("fMatched").classList.remove("on"); resetPaging(); render(); });
  }

  // ---- public API ----
  const CORE = {
    showMatches: false,            // master sets true after unlock
    titleOverride: null, taglineOverride: null,
    esc, toast, openModal, closeModal, fmtCr, parseDate, MON,
    getData: () => DATA,
    render, resetPaging, refresh, matchRow,
    openEngage, submitEngage,
    async init(opts = {}) {
      Object.assign(CFG, opts);
      if (opts.brand) CFG.brand = opts.brand;
      wireControls();
      ensureEngageModal();
      if ($("loadMore")) $("loadMore").querySelector("button").onclick = loadMore;
      await load();
      // auto-refresh the feed every 20 minutes while the page is open
      const ms = opts.autoRefreshMs || 20 * 60 * 1000;
      if (ms) setInterval(() => { load(); }, ms);
    },
  };
  window.CORE = CORE;
  window.loadMore = loadMore;       // for inline onclick fallback
})();
