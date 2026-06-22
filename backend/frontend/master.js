/* KCM IBC Tracker — MASTER layer (confidential). Loaded only in master.html.
   Adds: password-unlock (AES-GCM decrypt of the embedded client master),
   in-browser merger-fit matching (port of matching/rules.py), and settings
   (add/edit/delete clients, export/import, change password).
   The client master never exists in plaintext on disk — only AES-GCM ciphertext. */
(function () {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const esc = CORE.esc, toast = CORE.toast, openModal = CORE.openModal, closeModal = CORE.closeModal;

  // ---------- crypto (Web Crypto; matches build_master.py exactly) ----------
  const ITERS = 200000, LS_KEY = "kcm_master_blob_v1";
  function b64ToBytes(b64) { const bin = atob(b64); const u8 = new Uint8Array(bin.length); for (let i = 0; i < bin.length; i++) u8[i] = bin.charCodeAt(i); return u8; }
  function bytesToB64(u8) { let s = "", CH = 0x8000; for (let i = 0; i < u8.length; i += CH) s += String.fromCharCode.apply(null, u8.subarray(i, i + CH)); return btoa(s); }
  async function deriveKey(password, salt, iters) {
    const base = await crypto.subtle.importKey("raw", new TextEncoder().encode(password), "PBKDF2", false, ["deriveKey"]);
    return crypto.subtle.deriveKey({ name: "PBKDF2", salt, iterations: iters, hash: "SHA-256" }, base, { name: "AES-GCM", length: 256 }, false, ["encrypt", "decrypt"]);
  }
  async function decryptBlob(blob, password) {
    const key = await deriveKey(password, b64ToBytes(blob.salt), blob.iter || ITERS);
    const pt = await crypto.subtle.decrypt({ name: "AES-GCM", iv: b64ToBytes(blob.iv) }, key, b64ToBytes(blob.ct)); // throws on wrong pw
    return JSON.parse(new TextDecoder().decode(pt));
  }
  async function encryptObj(obj, password) {
    const salt = crypto.getRandomValues(new Uint8Array(16)), iv = crypto.getRandomValues(new Uint8Array(12));
    const key = await deriveKey(password, salt, ITERS);
    const ct = new Uint8Array(await crypto.subtle.encrypt({ name: "AES-GCM", iv }, key, new TextEncoder().encode(JSON.stringify(obj))));
    return { v: 1, iter: ITERS, salt: bytesToB64(salt), iv: bytesToB64(iv), ct: bytesToB64(ct) };
  }

  // ---------- matching (port of matching/rules.py) ----------
  // Generic business words that create spurious overlaps — excluded from matching.
  const STOP = new Set(("the and for ltd limited pvt private llp of co company india indian manufacturer manufacturing "
    + "products product services service inc corp industries industry group holding holdings enterprise enterprises "
    + "solutions solution systems system global international overseas trading traders ventures venture technologies "
    + "technology tech corporation associates udyog new sri shree shri the project projects works unit units "
    + "national general standard prime true royal star sons brothers and").split(/\s+/));
  function toks() { const out = new Set(); for (const t of arguments) { const m = (t || "").toLowerCase().match(/[a-z][a-z\-]{3,}/g) || []; for (const w of m) if (!STOP.has(w)) out.add(w); } return out; }
  function overlap(a, b) {
    if (!a.size || !b.size) return [0, []];
    const [small, large] = a.size < b.size ? [a, b] : [b, a]; const common = [];
    for (const x of small) if (large.has(x)) common.push(x);
    if (!common.length) return [0, []];
    return [Math.min(85, 25 + (common.length / Math.min(a.size, b.size)) * 70), common];
  }
  // Match on BUSINESS terms only (sector / products / value-chain / synergy) — never company names,
  // which would create meaningless overlaps like two firms sharing the word "true".
  function clientTokens(c) { return toks(c.products, c.sector, c.value_chain, c.synergy_directions, c.customers_served); }
  function confOf(c) { const v = (c.confidence || "").toUpperCase(); if (v.startsWith("HIGH")) return ["HIGH", "g-ok"]; if (v.startsWith("LOW") || v.startsWith("UNVER")) return ["LOW", "g-bad"]; return ["MEDIUM", "g-warn"]; }
  function synergyOf(c) { const s = (c.synergy_directions || c.acquisition_thesis || "").toLowerCase(); for (const k of ["backward", "forward", "horizontal"]) if (s.includes(k)) return k; return "horizontal"; }
  function buildMatch(c, score, common) {
    const [conf, cc] = confOf(c);
    const rat = (c.acquisition_thesis || c.synergy_directions || "Same or adjacent line of business — potential consolidation / strategic fit.").slice(0, 220);
    return {
      client: c.name, synergy_type: synergyOf(c), score: Math.round(score), bar_w: score,
      rationale: rat, matched_keywords: common.slice(0, 8).join(", "),
      eligibility_29a: c.eligibility_29a || "Verify", na_class: /caution|concern|disqualif|29a/i.test(c.eligibility_29a || "") ? "g-warn" : "g-ok",
      reach: c.reach || "Verify reachability", confidence: conf, conf_class: cc,
    };
  }

  // ---------- state ----------
  let UNLOCKED = false, PASSWORD = null, CLIENTS = [], INDEX = new Map();
  let AI_KEY = "", AI_MODEL = "claude-sonnet-4-6";
  const ANALYSIS = {};   // company name -> cached AI analysis object
  function activeBlob() { try { const s = localStorage.getItem(LS_KEY); if (s) return JSON.parse(s); } catch (e) {} return window.MASTER_BLOB; }
  function buildIndex() {
    INDEX = new Map();
    CLIENTS.forEach((c, i) => { c._tok = clientTokens(c); for (const w of c._tok) { let a = INDEX.get(w); if (!a) INDEX.set(w, a = []); a.push(i); } });
  }
  function matchTarget(t) {
    const tt = toks(t.sector, t.products); const cand = new Set();   // IBBI sector/products only — not the name
    for (const w of tt) { const a = INDEX.get(w); if (a) for (const i of a) cand.add(i); }
    const out = [];
    for (const i of cand) { const [score, common] = overlap(CLIENTS[i]._tok, tt); if (score >= 25) out.push(buildMatch(CLIENTS[i], score, common)); }
    out.sort((a, b) => b.score - a.score); return out.slice(0, 5);
  }
  function recompute() {
    const data = CORE.getData(); if (!data) return;
    data.opportunities.forEach(o => { o.matches = UNLOCKED ? matchTarget(o.target) : []; o.match_count = o.matches.length; });
  }
  CORE.afterLoad = function () { if (UNLOCKED) recompute(); };   // re-match after a feed refresh

  // ---------- unlock ----------
  async function doUnlock() {
    const pw = $("mpw").value; $("mpwErr").textContent = "";
    if (!pw) { $("mpwErr").textContent = "Enter the master password."; return; }
    try {
      const data = await decryptBlob(activeBlob(), pw);
      CLIENTS = (data.clients || data).filter(c => c && c.name);
      AI_KEY = (data.ai && data.ai.key) || ""; AI_MODEL = (data.ai && data.ai.model) || "claude-sonnet-4-6";
      PASSWORD = pw; UNLOCKED = true; buildIndex();
      CORE.cardTools = cardTools;        // master-only per-card AI / IC-memo buttons
      CORE.showMatches = true; recompute(); CORE.render(); CORE.renderStatsSafe();
      closeModal("unlockModal"); chrome(); toast(`Unlocked · ${CLIENTS.length} clients matched`);
    } catch (e) { $("mpwErr").textContent = "Wrong password."; }
  }
  function lock() { UNLOCKED = false; PASSWORD = null; CLIENTS = []; INDEX = new Map(); AI_KEY = ""; CORE.cardTools = null; CORE.showMatches = false; recompute(); CORE.render(); CORE.renderStatsSafe(); chrome(); toast("Locked"); }

  // core doesn't expose renderStats directly; re-run via render path
  CORE.renderStatsSafe = function () { /* stats refresh piggybacks on render(); no-op hook */ };

  // ---------- persistence ----------
  async function persist() {
    const clean = CLIENTS.map(c => { const { _tok, ...rest } = c; return rest; });
    const blob = await encryptObj({ clients: clean, ai: { key: AI_KEY, model: AI_MODEL } }, PASSWORD);
    localStorage.setItem(LS_KEY, JSON.stringify(blob));
  }

  // ---------- header chrome ----------
  function chrome() {
    const el = $("authRow");
    $("tierPill").textContent = "MASTER"; $("tierPill").className = "demo-pill gold";
    if (!UNLOCKED) {
      el.innerHTML = `<span style="color:var(--faint);font-size:12px">Confidential · KCM only</span>
        <button class="refresh" onclick="MASTER.openUnlock()"><svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg> Unlock client matching</button>`;
    } else {
      el.innerHTML = `<button class="refresh" onclick="CORE.refresh()"><svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12a9 9 0 1 1-2.64-6.36"/><path d="M21 3v6h-6"/></svg> Refresh</button>
        <button class="btn" onclick="MASTER.openSettings()">Client master (${CLIENTS.length})</button>
        <button class="btn" onclick="MASTER.lock()">Lock</button>`;
    }
  }

  // ---------- settings: client list ----------
  function renderClientList(filter) {
    const f = (filter || "").toLowerCase();
    const rows = [];
    for (let i = 0; i < CLIENTS.length && rows.length < 100; i++) {
      const c = CLIENTS[i];
      if (f && !(`${c.name} ${c.sector}`.toLowerCase().includes(f))) continue;
      rows.push(`<div class="blrow"><div><div class="bn">${esc(c.name)}</div><div class="bs">${esc(c.sector || "—")}</div></div>
        <div style="display:flex;gap:10px"><button class="mini" onclick="MASTER.editClient(${i})">edit</button><button class="mini del" onclick="MASTER.delClient(${i})">delete</button></div></div>`);
    }
    const total = CLIENTS.length;
    $("clientCount").textContent = `${total.toLocaleString("en-IN")} clients`;
    $("clientList").innerHTML = rows.length ? rows.join("") + (total > 100 && !f ? `<div class="bs" style="text-align:center;padding:6px">Showing first 100 — use search to find more.</div>` : "") : `<div class="bs" style="padding:8px">No matching clients.</div>`;
  }

  let editIdx = -1;
  const FIELDS = ["name", "sector", "products", "customers_served", "value_chain", "synergy_directions", "acquisition_thesis", "eligibility_29a", "reach", "confidence", "notes"];
  function openClientForm(idx) {
    editIdx = idx;
    $("cfTitle").textContent = idx >= 0 ? "Edit client" : "Add client";
    const c = idx >= 0 ? CLIENTS[idx] : {};
    FIELDS.forEach(f => { if ($("cf_" + f)) $("cf_" + f).value = c[f] || ""; });
    $("cfErr").textContent = ""; openModal("clientFormModal");
  }
  async function saveClient() {
    const obj = {}; FIELDS.forEach(f => obj[f] = ($("cf_" + f) ? $("cf_" + f).value.trim() : ""));
    if (!obj.name) { $("cfErr").textContent = "Company name is required."; return; }
    if (editIdx >= 0) CLIENTS[editIdx] = { ...CLIENTS[editIdx], ...obj }; else CLIENTS.push(obj);
    buildIndex(); await persist(); recompute(); CORE.render();
    closeModal("clientFormModal"); renderClientList($("clientSearch").value); chrome(); toast("Saved");
  }
  async function delClient(i) {
    if (!confirm(`Delete "${CLIENTS[i].name}" from the client master?`)) return;
    CLIENTS.splice(i, 1); buildIndex(); await persist(); recompute(); CORE.render();
    renderClientList($("clientSearch").value); chrome(); toast("Deleted");
  }

  // ---------- export / import ----------
  function exportBlob() {
    const blob = activeBlob(); const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([JSON.stringify(blob)], { type: "application/json" }));
    a.download = "kcm_client_master.enc.json"; a.click();
  }
  async function importBlob(input) {
    if (!input.files.length) return;
    try {
      const txt = await input.files[0].text(); const blob = JSON.parse(txt);
      const data = await decryptBlob(blob, PASSWORD);  // must decrypt with current password
      CLIENTS = (data.clients || data).filter(c => c && c.name); buildIndex(); await persist();
      recompute(); CORE.render(); renderClientList(""); chrome(); toast(`Imported ${CLIENTS.length} clients`);
    } catch (e) { toast("Import failed (wrong file or password mismatch)."); }
    input.value = "";
  }

  // ---------- change password ----------
  async function changePassword() {
    const c1 = $("pwCur1").value, c2 = $("pwCur2").value, neu = $("pwNew").value;
    $("pwErr").textContent = ""; $("pwOk").textContent = "";
    if (!c1 || !c2 || !neu) { $("pwErr").textContent = "Fill all three fields."; return; }
    if (c1 !== c2) { $("pwErr").textContent = "The two current-password entries do not match."; return; }
    if (neu.length < 6) { $("pwErr").textContent = "New password must be at least 6 characters."; return; }
    try { await decryptBlob(activeBlob(), c1); } catch (e) { $("pwErr").textContent = "Current password is incorrect."; return; }
    PASSWORD = neu; await persist();   // re-encrypt working copy with the new password
    $("pwCur1").value = $("pwCur2").value = $("pwNew").value = "";
    $("pwOk").textContent = "Password changed. Use the new password from now on (this device).";
    toast("Password changed");
  }

  // ---------- per-card tools (master only) ----------
  function findOpp(co) { return (CORE.getData().opportunities || []).find(o => o.target.name === co); }
  function cardTools(o) {
    const co = esc(o.target.name);
    const done = ANALYSIS[o.target.name] ? " ✓" : "";
    return `<div class="cardtools">
      <button class="ctbtn ai" data-co="${co}" onclick="MASTER.aiAnalyze(this)">🤖 AI Deal Analysis${done}</button>
      <button class="ctbtn memo" data-co="${co}" onclick="MASTER.icMemo(this)">📄 IC Memo</button>
    </div>`;
  }

  // ---------- AI Deal Analyst (browser → Anthropic, your own key) ----------
  function openAiSettings() {
    if ($("ai_key")) $("ai_key").value = AI_KEY;
    if ($("ai_model_sel")) $("ai_model_sel").value = AI_MODEL;
    $("aiOk").textContent = ""; openModal("aiSettingsModal");
  }
  async function saveAiSettings() {
    AI_KEY = $("ai_key") ? $("ai_key").value.trim() : AI_KEY;
    AI_MODEL = ($("ai_model_sel") && $("ai_model_sel").value) || AI_MODEL;
    await persist();
    $("aiOk").textContent = AI_KEY ? "Saved — AI Deal Analyst is ON." : "Saved (no key — AI off).";
    toast("AI settings saved");
  }
  async function callClaude(system, user, maxTokens) {
    if (!AI_KEY) throw new Error("No Anthropic key set (Settings → AI settings).");
    const res = await fetch("https://api.anthropic.com/v1/messages", {
      method: "POST",
      headers: { "content-type": "application/json", "x-api-key": AI_KEY,
        "anthropic-version": "2023-06-01", "anthropic-dangerous-direct-browser-access": "true" },
      body: JSON.stringify({ model: AI_MODEL, max_tokens: maxTokens || 1024, system, messages: [{ role: "user", content: user }] }),
    });
    if (!res.ok) { let m = res.status; try { m = (await res.json()).error.message || m; } catch (e) {} throw new Error("Claude API: " + m); }
    const j = await res.json();
    return (j.content || []).filter(b => b.type === "text").map(b => b.text).join("").trim();
  }
  function parseJson(text) {
    text = (text || "").trim().replace(/^```(json)?/i, "").replace(/```$/, "").trim();
    const a = text.indexOf("{"), b = text.lastIndexOf("}");
    if (a < 0 || b < 0) return null;
    try { return JSON.parse(text.slice(a, b + 1)); } catch (e) { return null; }
  }
  const AI_SYSTEM = `You are a senior M&A analyst at K C Mehta & Co specialising in distressed-asset acquisitions under India's Insolvency & Bankruptcy Code. Given a distressed company in the IBC process and a shortlist of the firm's acquirer clients (already keyword-matched on sector), produce a crisp investment view. Reason about REAL strategic fit (backward/forward/horizontal integration, including indirect supply-chain links), Section 29A eligibility risk, deal-timeline urgency (Form G / EoI window), and which client is the best acquirer. Be commercially realistic and concise.
Return STRICT JSON only, no prose:
{"score":0-100,"recommendation":"one-line verdict","best_clients":["client name"],"theses":[{"client":"name","fit":"backward|forward|horizontal|adjacency","rationale":"1-2 sentences"}],"risks":["..."],"next_step":"a concrete action for KCM"}`;
  async function aiAnalyze(btn) {
    const co = btn.dataset.co, o = findOpp(co); if (!o) return;
    openModal("aiModal"); $("aiTitle").textContent = co;
    if (ANALYSIS[co]) { renderAnalysis(co); return; }
    if (!AI_KEY) { $("aiBody").innerHTML = `<div class="err">No Anthropic key set. Open <b>Settings → AI settings</b> and paste your key (sk-ant-…), then try again.</div>`; return; }
    $("aiBody").innerHTML = `<div class="bs" style="color:var(--muted)">Analysing with Claude…</div>`;
    const t = o.target;
    const clientLines = (o.matches || []).map(m => `- ${m.client} | ${m.synergy_type} fit | 29A: ${m.eligibility_29a} | reach: ${m.reach} | data: ${m.confidence}`).join("\n") || "(no keyword matches found)";
    const user = `DISTRESSED COMPANY (IBC):\nName: ${t.name}\nSector: ${t.sector}\nStage: ${t.stage_label || t.status}\nAdmitted: ${t.admit}\nApplicant/creditor: ${t.applicant}\nResolution professional: ${t.resolution_professional}\nClaims by: ${t.claims_by}\nForm G expected: ${t.form_g_by || "n/a (liquidation)"}\n\nSHORTLISTED KCM CLIENTS (acquirers):\n${clientLines}\n\nReturn the JSON view.`;
    try {
      const data = parseJson(await callClaude(AI_SYSTEM, user, 1200));
      if (!data) { $("aiBody").innerHTML = `<div class="err">Could not parse the AI response — try again.</div>`; return; }
      ANALYSIS[co] = data; renderAnalysis(co); CORE.render();
    } catch (e) { $("aiBody").innerHTML = `<div class="err">${esc(e.message)}</div>`; }
  }
  function renderAnalysis(co) {
    const d = ANALYSIS[co]; if (!d) return;
    const sc = Math.round(d.score || 0), col = sc >= 70 ? "var(--green)" : sc >= 45 ? "var(--amber)" : "var(--grey)";
    $("aiBody").innerHTML = `
      <div style="display:flex;align-items:center;gap:14px;margin-bottom:10px">
        <div style="font-family:'Fraunces',serif;font-size:34px;font-weight:600;color:${col}">${sc}</div>
        <div><div style="font-weight:700">${esc(d.recommendation || "")}</div>
        <div class="bs">Best fit: ${(d.best_clients || []).map(esc).join(", ") || "—"}</div></div>
      </div>
      <div class="mlabel">Synergy theses</div>
      ${(d.theses || []).map(x => `<div class="match mixed" style="margin-top:6px"><div class="m-right"><div class="m-buyer">${esc(x.client)} <span class="fit ${esc((x.fit || "").toLowerCase())}">${esc(x.fit || "")}</span></div><div class="rat">${esc(x.rationale)}</div></div></div>`).join("")}
      <div class="mlabel" style="margin-top:12px">Key risks</div>
      <ul style="font-size:13px;margin-left:18px">${(d.risks || []).map(r => `<li>${esc(r)}</li>`).join("")}</ul>
      <div class="mlabel" style="margin-top:12px">Recommended next step</div>
      <div style="font-size:13.5px">${esc(d.next_step || "")}</div>
      <div style="margin-top:14px"><button class="btn primary" onclick="MASTER.icMemoFor('${esc(co).replace(/'/g, "\\'")}')">📄 Build IC Memo</button></div>`;
  }

  // ---------- One-click IC Memo (client-side; Print/PDF + Word) ----------
  const MEMO_CSS = `body{font-family:Georgia,'Times New Roman',serif;color:#1a1a1a;line-height:1.5;margin:0}
  .memo{max-width:740px;margin:0 auto;padding:6px;font-size:13px}
  .memo-h{display:flex;justify-content:space-between;align-items:flex-start;border-bottom:2px solid #14213d;padding-bottom:8px;margin-bottom:12px}
  .memo-firm{font-size:10px;letter-spacing:.12em;color:#14213d;font-weight:bold;font-family:Arial,sans-serif}
  .memo-t{font-size:16px;color:#14213d;margin-top:3px}
  .memo-conf{font-size:9px;letter-spacing:.1em;color:#fff;background:#b1493a;padding:3px 8px;border-radius:3px;font-family:Arial,sans-serif}
  .memo h2{font-size:20px;color:#14213d;margin:6px 0 10px}
  .memo h3{font-size:12px;color:#14213d;border-bottom:1px solid #d2dae6;padding-bottom:3px;margin:16px 0 7px;text-transform:uppercase;letter-spacing:.04em;font-family:Arial,sans-serif}
  .memo table{width:100%;border-collapse:collapse;margin:6px 0}
  .memo-kv td{padding:4px 8px;border:1px solid #e3e8f0;font-size:12.5px}
  .memo-kv td:nth-child(odd){background:#f6f8fc;color:#5c6a83;width:20%;font-family:Arial,sans-serif;font-size:11px}
  .memo-tbl th{background:#14213d;color:#fff;padding:6px 8px;text-align:left;font-size:11px;font-family:Arial,sans-serif}
  .memo-tbl td{padding:5px 8px;border-bottom:1px solid #e3e8f0;font-size:12px}
  .memo ul{margin:4px 0 4px 18px}.memo p{margin:5px 0}
  .memo-foot{margin-top:18px;font-size:10px;color:#888;border-top:1px solid #e3e8f0;padding-top:8px}`;
  let memoStyleInjected = false;
  function memoHtml(o) {
    const t = o.target, a = ANALYSIS[t.name];
    const rows = (o.matches || []).map(m => `<tr><td>${esc(m.client)}</td><td>${esc(m.synergy_type)}</td><td style="text-align:center">${Math.round(m.score)}</td><td>${esc(m.eligibility_29a)}</td><td>${esc(m.confidence)}</td></tr>`).join("") || `<tr><td colspan="5">No keyword-matched clients.</td></tr>`;
    const ai = a ? `<h3>AI deal view — conviction ${Math.round(a.score || 0)}/100</h3>
      <p><b>${esc(a.recommendation || "")}</b> — best fit: ${(a.best_clients || []).map(esc).join(", ") || "—"}.</p>
      <ul>${(a.theses || []).map(x => `<li><b>${esc(x.client)}</b> (${esc(x.fit || "")}): ${esc(x.rationale)}</li>`).join("")}</ul>
      <p><b>Risks:</b> ${(a.risks || []).map(esc).join("; ") || "—"}</p>
      <p><b>Recommended next step:</b> ${esc(a.next_step || "")}</p>`
      : `<p style="color:#888"><i>Run "AI Deal Analysis" for a synergy view and conviction score.</i></p>`;
    return `<div class="memo">
      <div class="memo-h"><div><div class="memo-firm">K C MEHTA &amp; CO LLP · M&amp;A ADVISORY</div><div class="memo-t">Investment Committee Note — IBC Opportunity</div></div><div class="memo-conf">CONFIDENTIAL</div></div>
      <h2>${esc(t.name)}</h2>
      <table class="memo-kv">
        <tr><td>Sector</td><td>${esc(t.sector || "—")}</td><td>Process</td><td>${esc(t.stage_label || t.status)}</td></tr>
        <tr><td>Admitted</td><td>${esc(t.admit || "—")}</td><td>Claims by</td><td>${esc(t.claims_by || "—")}</td></tr>
        <tr><td>Form G (entry)</td><td>${esc(t.form_g_by || "n/a")}</td><td>Applicant / creditor</td><td>${esc(t.applicant || "—")}</td></tr>
        <tr><td>Resolution professional</td><td colspan="3">${esc(t.resolution_professional || "—")}</td></tr>
      </table>
      <h3>Matched KCM clients (acquirers)</h3>
      <table class="memo-tbl"><thead><tr><th>Client</th><th>Fit</th><th>Score</th><th>29A</th><th>Data</th></tr></thead><tbody>${rows}</tbody></table>
      ${ai}
      <h3>Financial snapshot</h3>
      <p>Revenue / EBITDA / net worth / debt — to be populated from VCCEdge / MCA. Liquidation vs going-concern value disclosed in the IM (on EoI).</p>
      <p class="memo-foot">Source: IBBI public announcements${t.pa_pdf ? " — Form A: " + esc(t.pa_pdf) : ""}. Prepared by KCM IBC Finder on ${new Date().toLocaleDateString("en-IN")}. Internal working note, not advice.</p>
    </div>`;
  }
  function icMemo(btn) { icMemoFor(btn.dataset.co); }
  function icMemoFor(co) {
    const o = findOpp(co); if (!o) return;
    closeModal("aiModal");
    if (!memoStyleInjected) { const s = document.createElement("style"); s.textContent = MEMO_CSS; document.head.appendChild(s); memoStyleInjected = true; }
    $("memoBody").innerHTML = memoHtml(o);
    openModal("memoModal");
  }
  function printMemo() {
    const w = window.open("", "_blank");
    w.document.write(`<html><head><title>IC Memo</title><meta charset="utf-8"><style>${MEMO_CSS}</style></head><body>${$("memoBody").innerHTML}</body></html>`);
    w.document.close(); w.focus(); setTimeout(() => w.print(), 300);
  }
  function downloadMemoDoc() {
    const html = `<html xmlns:o='urn:schemas-microsoft-com:office:office' xmlns:w='urn:schemas-microsoft-com:office:word'><head><meta charset='utf-8'><style>${MEMO_CSS}</style></head><body>${$("memoBody").innerHTML}</body></html>`;
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob(["﻿", html], { type: "application/msword" }));
    const name = (($("memoBody").querySelector("h2") || {}).textContent || "IC-Memo").replace(/[^a-z0-9]+/gi, "_").slice(0, 40);
    a.download = "IC_Memo_" + name + ".doc"; a.click();
  }

  // ---------- public hooks ----------
  window.MASTER = {
    openUnlock() { $("mpw").value = ""; $("mpwErr").textContent = ""; openModal("unlockModal"); setTimeout(() => $("mpw").focus(), 50); },
    doUnlock, lock,
    openSettings() { renderClientList(""); openModal("settingsModal"); },
    searchClients(v) { renderClientList(v); },
    openClientForm, editClient: openClientForm, saveClient, delClient,
    exportBlob, importBlob, openPassword() { $("pwErr").textContent = ""; $("pwOk").textContent = ""; openModal("pwModal"); }, changePassword,
    openAiSettings, saveAiSettings, aiAnalyze, icMemo, icMemoFor, printMemo, downloadMemoDoc,
  };

  // boot: load the public feed (no matches until unlocked)
  document.title = "KCM IBC Finder · Master · K C Mehta & Co";
  CORE.init({ brand: "kcm", dataUrl: (window.DATA_URL || "data.json"), fallbackUrl: "data.json" }).then(chrome);
})();
