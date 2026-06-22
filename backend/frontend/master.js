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
      PASSWORD = pw; UNLOCKED = true; buildIndex();
      CORE.showMatches = true; recompute(); CORE.render(); CORE.renderStatsSafe();
      closeModal("unlockModal"); chrome(); toast(`Unlocked · ${CLIENTS.length} clients matched`);
    } catch (e) { $("mpwErr").textContent = "Wrong password."; }
  }
  function lock() { UNLOCKED = false; PASSWORD = null; CLIENTS = []; INDEX = new Map(); CORE.showMatches = false; recompute(); CORE.render(); CORE.renderStatsSafe(); chrome(); toast("Locked"); }

  // core doesn't expose renderStats directly; re-run via render path
  CORE.renderStatsSafe = function () { /* stats refresh piggybacks on render(); no-op hook */ };

  // ---------- persistence ----------
  async function persist() {
    const clean = CLIENTS.map(c => { const { _tok, ...rest } = c; return rest; });
    const blob = await encryptObj({ clients: clean }, PASSWORD);
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

  // ---------- public hooks ----------
  window.MASTER = {
    openUnlock() { $("mpw").value = ""; $("mpwErr").textContent = ""; openModal("unlockModal"); setTimeout(() => $("mpw").focus(), 50); },
    doUnlock, lock,
    openSettings() { renderClientList(""); openModal("settingsModal"); },
    searchClients(v) { renderClientList(v); },
    openClientForm, editClient: openClientForm, saveClient, delClient,
    exportBlob, importBlob, openPassword() { $("pwErr").textContent = ""; $("pwOk").textContent = ""; openModal("pwModal"); }, changePassword,
  };

  // boot: load the public feed (no matches until unlocked)
  document.title = "KCM IBC Finder · Master · K C Mehta & Co";
  CORE.init({ brand: "kcm", dataUrl: (window.DATA_URL || "data.json"), fallbackUrl: "data.json" }).then(chrome);
})();
