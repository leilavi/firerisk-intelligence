/* FireRisk Intelligence dashboard - vanilla JS, talks only to the local backend (/api). */
"use strict";

const $ = (s, el = document) => el.querySelector(s);
const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const SEV = ["normal", "watch", "warning", "high", "emergency"];
const SEV_LABEL = { normal: "Normal", watch: "Watch", warning: "Warning", high: "High risk", emergency: "Emergency" };
const KIND_LABEL = {
  incident: "Incident report", construction: "Works log", asset_service: "Asset repair/maintenance",
  inspection_check: "Daily checklist", generator_run: "Generator log", meter_episode: "Meter analysis",
  meter_reading: "Meter reading", vehicle_day: "Vehicle count",
};
const sevBadge = (s) => `<span class="sev ${esc(s)}">${esc(SEV_LABEL[s] || s)}</span>`;
const fmt = (iso) => (iso ? new Date(iso).toLocaleString("en-GB", { dateStyle: "medium", timeStyle: "short" }) : "—");
const fmtDay = (iso) => (iso ? new Date(iso).toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" }) : "undated");

async function api(path, opts) {
  const r = await fetch(path, opts);
  if (!r.ok) throw new Error(`${r.status} ${await r.text()}`);
  return r.json();
}

let STATUS = null;

async function loadStatus() {
  STATUS = await api("/api/status");
  $("#building").textContent = `${STATUS.building} · v${STATUS.version}`;
  $("#generated").textContent = `Analysis ${fmt(STATUS.generated_at)}`;
  const ai = $("#ai-status");
  ai.textContent = STATUS.ai.configured ? `AI: ${STATUS.ai.model}` : "AI: not configured";
  ai.className = "pill " + (STATUS.ai.configured ? "ok" : "bad");
}

/* ------------------------------------------------------------------ views */
async function viewOverview() {
  const alerts = await api("/api/alerts");
  const s = STATUS;
  const counts = SEV.slice().reverse().map((k) => `<div class="card kpi"><div class="l">${SEV_LABEL[k]}</div><div class="n">${s.alert_counts[k] || 0}</div></div>`).join("");
  const sources = s.sources.map((x) => `
    <tr><td>${esc(x.source === "ops_data" ? "Operations data" : "Vehicle counts")}<div class="muted">${esc(x.sheet || "")}</div></td>
    <td>${x.error ? `<span class="tag open">${esc(x.error)}</span>` : esc(x.rows_read)}</td>
    <td>${fmt(x.latest_record)}</td>
    <td>${x.age_days ?? "—"} d ${x.stale ? '<span class="tag open">stale</span>' : ""}<div class="muted">${x.expected_cadence_days ? "expected ≤ " + x.expected_cadence_days + " d" : "event log"}</div></td>
    <td class="muted">${fmt(x.snapshot_at)}</td></tr>`).join("");
  $("#app").innerHTML = `
    <h1>Building fire-risk overview</h1>
    <div class="grid g4">${counts}<div class="card kpi"><div class="l">Evidence records</div><div class="n">${s.evidence_count}</div></div></div>
    <h2>Zone alerts</h2>
    <div class="grid g2">${alerts.map(alertCard).join("") || '<div class="card">No zone has a Watch-level signal or higher.</div>'}</div>
    <h2>Data sources (real operational data)</h2>
    <div class="table-wrap"><table><thead><tr><th>Source / tab</th><th>Rows read</th><th>Latest record</th><th>Age</th><th>Snapshot taken</th></tr></thead><tbody>${sources}</tbody></table></div>
    <p class="muted">The dashboard reflects the snapshot at the time shown; press “Re-run analysis” after the snapshot is refreshed.</p>`;
  bindAlertCards();
}

function alertCard(a) {
  const v = a.verification ? a.verification.status : "new";
  return `<div class="card click alert-card ${esc(a.severity)}" data-alert="${esc(a.alert_id)}">
    <div class="row">${sevBadge(a.severity)}<span class="tag">${esc(v.replace("_", " "))}</span>${a.open_items ? `<span class="tag open">${a.open_items} unresolved</span>` : ""}
    ${a.ai ? `<span class="tag ctx">AI: ${esc(SEV_LABEL[a.ai.ai_priority])}</span>` : ""}</div>
    <h3 style="margin-top:8px">${esc(a.title)}</h3>
    <div class="muted">${esc(a.summary)}</div>
    <ul class="basis">${a.severity_basis.slice(0, 3).map((b) => `<li>${esc(b)}</li>`).join("")}</ul>
    <div class="muted" style="margin-top:6px">Evidence from ${fmtDay(a.first_seen)} to ${fmtDay(a.last_seen)}</div></div>`;
}
function bindAlertCards() {
  document.querySelectorAll("[data-alert]").forEach((el) => el.addEventListener("click", () => (location.hash = `#/alert/${el.dataset.alert}`)));
}

async function viewAlerts() {
  const alerts = await api("/api/alerts");
  $("#app").innerHTML = `<h1>Aggregated alerts by zone</h1>
    <div class="row" style="margin-bottom:10px"><label>Minimum level <select id="minsev">${SEV.slice(1).map((k) => `<option value="${k}">${SEV_LABEL[k]}</option>`).join("")}</select></label></div>
    <div class="table-wrap"><table><thead><tr><th>Level</th><th>Zone / alert</th><th>Pathways</th><th>Evidence</th><th>Unresolved</th><th>Last evidence</th><th>Status</th><th>AI</th></tr></thead>
    <tbody id="rows"></tbody></table></div>`;
  const render = () => {
    const min = SEV.indexOf($("#minsev").value);
    $("#rows").innerHTML = alerts.filter((a) => SEV.indexOf(a.severity) >= min).map((a) => `
      <tr class="click" data-alert="${esc(a.alert_id)}"><td>${sevBadge(a.severity)}</td><td><strong>${esc(a.title)}</strong><div class="muted">${esc(a.summary)}</div></td>
      <td>${a.pathways.map((p) => `<span class="tag">${esc(p.replace(/_/g, " "))}</span>`).join("")}</td><td>${a.evidence_ids.length} + ${a.context_ids.length} ctx</td>
      <td>${a.open_items}</td><td>${fmtDay(a.last_seen)}</td><td>${esc(a.verification?.status || "new")}</td><td>${a.ai ? esc(SEV_LABEL[a.ai.ai_priority]) : "—"}</td></tr>`).join("");
    bindAlertCards();
  };
  $("#minsev").addEventListener("change", render);
  render();
}

async function viewAlert(id) {
  const d = await api(`/api/alerts/${encodeURIComponent(id)}`);
  const a = d.alert;
  const evById = Object.fromEntries(d.evidence.map((e) => [e.evidence_id, e]));
  window.__ev = evById;
  const signals = d.signals.map((s) => `<tr><td>${sevBadge(s.severity)}</td><td><strong>${esc(s.title)}</strong>
      <div class="muted">${esc(s.mechanism)}</div></td><td>${esc(s.basis)}</td>
      <td><span class="tag ${s.origin === "PORTED" ? "ported" : "new"}">${esc(s.rule_id)} · ${esc(s.origin)}</span>${s.is_open ? '<span class="tag open">unresolved</span>' : ""}</td>
      <td>${s.evidence_ids.map(chip).join("")}${s.context_ids.length ? `<div class="muted">context:</div>${s.context_ids.map(chip).join("")}` : ""}</td></tr>`).join("");
  const timeline = d.timeline.map((e) => `<div class="tl-item ${e.is_open ? "open" : e.role}">
      <div class="tl-date">${fmt(e.timestamp)} · ${esc(KIND_LABEL[e.kind] || e.kind)}${e.asset_id ? " · " + esc(e.asset_id) : ""}</div>
      <div><a href="javascript:void 0" data-ev="${esc(e.evidence_id)}">${esc(e.title)}</a> ${e.is_open ? '<span class="tag open">unresolved</span>' : ""} ${e.role === "context" ? '<span class="tag ctx">context</span>' : ""}</div>
      ${e.text && e.text !== e.title ? `<div class="muted">${esc(e.text.slice(0, 220))}</div>` : ""}</div>`).join("");
  const linkTypes = {};
  a.links.forEach((l) => l.types.forEach((t) => (linkTypes[t] = (linkTypes[t] || 0) + 1)));
  const strongLinks = a.links.filter((l) => !(l.types.length === 1 && l.types[0] === "same_zone_time_window"));
  const links = strongLinks.map((l) => `<tr><td>${chip(l.a)}</td><td>${chip(l.b)}</td><td>${l.types.map((t) => `<span class="tag">${esc(t.replace(/_/g, " "))}</span>`).join("")}</td><td>${l.reasons.map(esc).join("<br>")}</td></tr>`).join("");
  const evRows = d.evidence.slice().sort((x, y) => (y.timestamp || "").localeCompare(x.timestamp || "")).map((e) => `
      <tr class="click" data-ev="${esc(e.evidence_id)}"><td class="mono">${esc(e.evidence_id)}</td><td>${esc(KIND_LABEL[e.kind] || e.kind)}</td><td>${fmtDay(e.timestamp)}</td>
      <td>${esc(e.asset_id || "")}<div class="muted">${esc(e.asset_name || "")}</div></td><td>${esc(e.title)}</td><td>${esc(e.status || "")}</td>
      <td>${e.role === "context" ? '<span class="tag ctx">context</span>' : '<span class="tag">finding</span>'}</td>
      <td class="muted">${esc(e.source?.sheet || "")}${e.source?.row ? " · row " + e.source.row : ""}</td></tr>`).join("");
  const meters = Object.entries(d.meters).map(([m, x]) => `<div class="card"><h3>${esc(m)} — ${esc(x.meta?.name || "")}</h3>
      <div class="muted">Daily consumption, last 90 days (${esc(x.meta?.unit || "")}). Gaps are shown as gaps, never as zero.</div>${meterChart(x.calendar)}
      <div class="legend"><span><i style="background:#5aa9e6"></i>daily value</span><span><i style="background:#e04848"></i>spike/drop day</span><span><i style="background:#8d98a5"></i>baseline median</span><span><i style="background:#2a333d"></i>missing / averaged</span></div></div>`).join("");
  const media = d.media.length ? `<div class="table-wrap"><table><thead><tr><th>Record</th><th>Reference in source</th><th>Type</th><th>Status</th></tr></thead><tbody>${d.media.map((m) => `
      <tr><td>${chip(m.evidence_id)}</td><td class="mono">${esc(m.reference)}</td><td>${esc(m.type)}</td><td>${m.available ? `<a href="/api/media" target="_blank">available</a>` : '<span class="tag open">referenced, file not available</span>'}</td></tr>`).join("")}</tbody></table></div>`
    : '<p class="muted">No image or video references in this alert’s evidence.</p>';

  $("#app").innerHTML = `
    <p><a href="#/alerts">← All alerts</a></p>
    <div class="row">${sevBadge(a.severity)}<h1 style="margin:0">${esc(a.title)}</h1></div>
    <p class="muted">${esc(a.summary)} Evidence period ${fmtDay(a.first_seen)} – ${fmtDay(a.last_seen)}.</p>
    <div class="grid g2">
      <div class="card"><h3>Why this level (deterministic rules)</h3><ul class="basis">${a.severity_basis.map((b) => `<li>${esc(b)}</li>`).join("")}</ul>
        <p class="muted" style="margin-bottom:0">Rules are preliminary decision-support rules (see RISK_RULES.md); they do not compute probabilities.</p></div>
      <div class="card"><h3>Verification status</h3>${verificationBox(d)}</div>
    </div>
    <h2>Muse Spark investigation (Meta AI)</h2><div id="ai-panel">${aiPanel(d.investigation, a)}</div>
    <h2>Signals</h2><div class="table-wrap"><table><thead><tr><th>Level</th><th>Pathway</th><th>Rule basis</th><th>Rule</th><th>Evidence</th></tr></thead><tbody>${signals}</tbody></table></div>
    <h2>Timeline</h2><div class="card"><div class="timeline">${timeline}</div></div>
    ${meters ? `<h2>Related meters</h2><div class="grid g2">${meters}</div>` : ""}
    <h2>Cross-source links</h2>
    <p class="muted">${Object.entries(linkTypes).map(([t, n]) => `${esc(t.replace(/_/g, " "))}: ${n}`).join(" · ")}. Links mark relationships worth checking, not causation. Showing ${strongLinks.length} links with a reason beyond “same zone and time window”.</p>
    <div class="table-wrap"><table><thead><tr><th>Record A</th><th>Record B</th><th>Type</th><th>Reason</th></tr></thead><tbody>${links}</tbody></table></div>
    <h2>Evidence (traceable to source rows)</h2>
    <div class="table-wrap"><table><thead><tr><th>ID</th><th>Kind</th><th>Date</th><th>Asset</th><th>Record</th><th>Status</th><th>Role</th><th>Source</th></tr></thead><tbody>${evRows}</tbody></table></div>
    <h2>Images &amp; video</h2>${media}
    <h2>Alert history</h2><div class="table-wrap"><table><thead><tr><th>Analysis time</th><th>Level</th><th>Evidence</th><th>Unresolved</th></tr></thead><tbody>
      ${d.history.map((h) => `<tr><td>${fmt(h.recorded_at)}</td><td>${sevBadge(h.severity)}</td><td>${h.evidence_count}</td><td>${h.open_items}</td></tr>`).join("")}</tbody></table></div>`;
  bindEvidenceLinks();
  bindVerification(a.alert_id);
  bindAI(a.alert_id);
}

function chip(id) {
  return `<span class="chip" data-ev="${esc(id)}" title="Open evidence">${esc(id.length > 34 ? id.slice(0, 32) + "…" : id)}</span>`;
}

function verificationBox(d) {
  const cur = d.verification?.status || "new";
  const opts = ["new", "acknowledged", "investigating", "resolved", "false_alarm"].map((s) => `<option ${s === cur ? "selected" : ""} value="${s}">${s.replace("_", " ")}</option>`).join("");
  return `<div class="row"><select id="vstatus">${opts}</select><input type="text" id="vby" placeholder="Your name / role (optional)"></div>
    <textarea id="vnote" placeholder="Note (what was checked, by whom, result)"></textarea>
    <div class="row"><button class="btn" id="vsave">Save status</button><span class="muted" id="vmsg"></span></div>
    <div class="muted" style="margin-top:8px">${d.status_log.slice(0, 4).map((s) => `${fmt(s.changed_at)} · ${esc(s.status)}${s.note ? " — " + esc(s.note) : ""}${s.changed_by ? " (" + esc(s.changed_by) + ")" : ""}`).join("<br>")}</div>`;
}
function bindVerification(id) {
  $("#vsave").addEventListener("click", async () => {
    $("#vmsg").textContent = "Saving…";
    try {
      await api(`/api/alerts/${encodeURIComponent(id)}/status`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ status: $("#vstatus").value, note: $("#vnote").value || null, by: $("#vby").value || null }) });
      route();
    } catch (e) { $("#vmsg").textContent = "Failed: " + e.message; }
  });
}

function aiPanel(inv, a) {
  const btn = `<button class="btn primary" id="ai-run" ${STATUS.ai.configured ? "" : "disabled"}>${inv ? "Run a new investigation" : "Run Muse Spark investigation"}</button>`;
  const notConf = STATUS.ai.configured ? "" : '<div class="warnbox">The Meta Model API key is not configured on this computer (run setup_api_key.bat). The rule-based alert above remains valid without AI.</div>';
  if (!inv) return `<div class="card ai">${notConf}<p class="muted">The rule engine assembled ${a.evidence_ids.length} evidence records and ${a.context_ids.length} context records for this zone. Muse Spark will reason over them (personal names and e-mails are pseudonymised before sending) and return hypotheses, an escalation pathway and recommended checks, each citing evidence IDs.</p>${btn}</div>`;
  if (inv.status !== "ok") return `<div class="card ai">${notConf}<div class="errbox">Last attempt (${fmt(inv.created_at)}) failed: ${esc(inv.error_kind)} — ${esc(inv.error)}</div>${btn}</div>`;
  const r = inv.result, v = inv.validation || {};
  const ids = (l) => (l || []).map(chip).join("") || '<span class="muted">none</span>';
  const ra = r.risk_assessment;
  return `<div class="card ai">
    <div class="row"><span class="label">AI-generated analysis · verify on site</span><span class="pill">${esc(inv.model)}</span><span class="pill">${fmt(inv.created_at)}</span><span class="pill">${esc(inv.seconds)} s · ${esc(inv.usage?.total_tokens ?? "?")} tokens</span>${btn}</div>
    ${v.ok ? "" : `<div class="warnbox">Validation: ${v.invalid_evidence_ids?.length ? "removed citations to unknown evidence IDs: " + v.invalid_evidence_ids.map(esc).join(", ") + ". " : ""}${v.unsupported_facts?.length ? v.unsupported_facts.length + " stated fact(s) had no valid evidence citation and are marked unsupported." : ""}</div>`}
    <p style="font-size:15px">${esc(r.summary)}</p>
    <div class="row"><span>Rule level ${sevBadge(a.severity)}</span><span>AI priority ${sevBadge(ra.ai_priority)}</span><span class="muted">${ra.agrees_with_rule_severity ? "agrees with rules" : "differs from rules"} — ${esc(ra.rationale)}</span></div>
    <h3 style="margin-top:14px">Observed facts</h3><ul class="basis">${r.observed_facts.map((f) => `<li>${esc(f.statement)} ${f.supported === false ? '<span class="tag open">unsupported</span>' : ""} ${ids(f.evidence_ids)}</li>`).join("")}</ul>
    <h3 style="margin-top:14px">Hypotheses (not confirmed)</h3>${r.hypotheses.map((h) => `<div class="hyp"><div class="row"><span class="plaus ${esc(h.plausibility)}">${esc(h.plausibility)}</span><strong>${esc(h.cause)}</strong><span class="tag">${esc(h.category)}</span></div>
      <div>${esc(h.reasoning)}</div><div class="muted">Supporting: ${ids(h.supporting_evidence_ids)} Contradicting: ${ids(h.contradicting_evidence_ids)}</div><div><em>How to verify:</em> ${esc(h.how_to_verify)}</div></div>`).join("")}
    <h3 style="margin-top:14px">Possible escalation pathway</h3><ol>${r.escalation_pathway.map((s) => `<li><strong>${esc(s.step)}</strong> — <span class="muted">if ${esc(s.condition)}</span> ${ids(s.evidence_ids)}</li>`).join("")}</ol>
    <h3>Recommended actions</h3><div class="table-wrap"><table><thead><tr><th>Urgency</th><th>Action</th><th>Reason</th><th>Role</th><th>Evidence</th></tr></thead><tbody>
      ${r.recommended_actions.map((x) => `<tr><td><span class="urg ${esc(x.urgency)}">${esc(x.urgency.replace(/_/g, " "))}</span></td><td>${esc(x.action)}</td><td>${esc(x.reason)}</td><td>${esc(x.responsible_role)}</td><td>${ids(x.evidence_ids)}</td></tr>`).join("")}</tbody></table></div>
    <h3 style="margin-top:14px">Missing information</h3><ul class="basis">${r.missing_information.map((m) => `<li><strong>${esc(m.item)}</strong> — ${esc(m.why_it_matters)}</li>`).join("")}</ul>
    <h3 style="margin-top:14px">Uncertainty</h3><p>${esc(r.uncertainty)}</p></div>`;
}
function bindAI(id) {
  const b = $("#ai-run");
  if (!b) return;
  b.addEventListener("click", async () => {
    b.disabled = true;
    b.innerHTML = '<span class="spinner"></span> Muse Spark is investigating…';
    try { await api(`/api/alerts/${encodeURIComponent(id)}/investigate`, { method: "POST" }); } catch (e) { alert("Investigation request failed: " + e.message); }
    route();
  });
}

function meterChart(cal) {
  if (!cal || !cal.length) return '<p class="muted">No data.</p>';
  const W = 640, H = 180, P = 28;
  const vals = cal.map((c) => c.value).filter((v) => v != null);
  const max = Math.max(...vals, ...cal.map((c) => c.median || 0)) * 1.1 || 1;
  const x = (i) => P + (i * (W - 2 * P)) / Math.max(1, cal.length - 1);
  const y = (v) => H - P - (v / max) * (H - 2 * P);
  let path = "", pen = false, med = "", medPen = false, marks = "", gaps = "";
  cal.forEach((c, i) => {
    if (c.value == null || c.flag === "averaged_gap" || c.flag === "negative_excluded") {
      pen = false;
      gaps += `<rect x="${x(i) - 2}" y="${P}" width="4" height="${H - 2 * P}" fill="#2a333d"><title>${esc(c.day)}: ${esc(c.flag || "missing")}</title></rect>`;
      if (c.flag !== "averaged_gap") return;
    }
    if (c.value != null && c.flag !== "negative_excluded") { path += `${pen ? "L" : "M"}${x(i).toFixed(1)},${y(c.value).toFixed(1)}`; pen = c.flag !== "averaged_gap"; }
    if (c.median != null) { med += `${medPen ? "L" : "M"}${x(i).toFixed(1)},${y(c.median).toFixed(1)}`; medPen = true; }
    if (c.spike) marks += `<circle cx="${x(i)}" cy="${y(c.value)}" r="4" fill="#e04848"><title>${esc(c.day)}: ${c.value} (${c.spike}) vs median ${c.median}</title></circle>`;
  });
  const first = cal[0].day, last = cal[cal.length - 1].day;
  return `<svg class="chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="Daily consumption chart">${gaps}
    <path d="${med}" stroke="#8d98a5" stroke-dasharray="4 3" fill="none"/><path d="${path}" stroke="#5aa9e6" stroke-width="1.6" fill="none"/>${marks}
    <text x="${P}" y="${H - 8}" fill="#8d98a5" font-size="10">${esc(first)}</text><text x="${W - P}" y="${H - 8}" fill="#8d98a5" font-size="10" text-anchor="end">${esc(last)}</text>
    <text x="${P}" y="${P - 8}" fill="#8d98a5" font-size="10">max ${Math.round(max)}</text></svg>`;
}

async function viewEvents() {
  const evs = await api("/api/events");
  const kinds = [...new Set(evs.map((e) => e.kind))];
  $("#app").innerHTML = `<h1>Fire-relevant event history</h1>
    <p class="muted">Records from all sources that carry a fire-safety tag, plus meter-analysis episodes. Tags show the exact matched term.</p>
    <div class="row" style="margin-bottom:10px"><select id="fk"><option value="">All kinds</option>${kinds.map((k) => `<option value="${k}">${esc(KIND_LABEL[k] || k)}</option>`).join("")}</select>
    <input type="text" id="fq" placeholder="Search text"><span class="muted" id="fc"></span></div>
    <div class="table-wrap"><table><thead><tr><th>Date</th><th>Kind</th><th>Zone</th><th>Record</th><th>Tags</th><th>Status</th></tr></thead><tbody id="erows"></tbody></table></div>`;
  const render = () => {
    const k = $("#fk").value, q = $("#fq").value.toLowerCase();
    const list = evs.filter((e) => (!k || e.kind === k) && (!q || (e.title + " " + e.text).toLowerCase().includes(q)));
    $("#fc").textContent = `${list.length} records`;
    $("#erows").innerHTML = list.map((e) => `<tr class="click" data-ev="${esc(e.evidence_id)}"><td>${fmtDay(e.timestamp)}</td><td>${esc(KIND_LABEL[e.kind] || e.kind)}</td><td>${esc(e.zone || "—")}</td>
      <td>${esc(e.title)}</td><td>${(e.tags || []).filter((t) => t.tag !== "checklist_pass").map((t) => `<span class="tag" title="matched: ${esc(t.term)}">${esc(t.tag.replace(/_/g, " "))}</span>`).join("")}</td>
      <td>${esc(e.status || "")} ${e.is_open ? '<span class="tag open">unresolved</span>' : ""}</td></tr>`).join("");
    window.__ev = Object.fromEntries(evs.map((e) => [e.evidence_id, e]));
    bindEvidenceLinks();
  };
  $("#fk").addEventListener("change", render);
  $("#fq").addEventListener("input", render);
  render();
}

async function viewQuality() {
  const q = await api("/api/quality");
  $("#app").innerHTML = `<h1>Data sources and data quality</h1>
    <div class="table-wrap"><table><thead><tr><th>Source</th><th>Tab</th><th>Rows read</th><th>In scope</th><th>Excluded (other branches)</th><th>Latest record</th><th>Stale?</th><th>Drive modifiedTime</th></tr></thead><tbody>
    ${q.sources.map((s) => `<tr><td>${esc(s.source)}</td><td>${esc(s.sheet || "")}</td><td>${esc(s.rows_read ?? "")}</td><td>${esc(s.in_scope ?? "")}</td><td>${esc(s.excluded_out_of_scope ?? "")}</td><td>${fmt(s.latest_record)}</td><td>${s.stale ? '<span class="tag open">yes</span>' : "no"}</td><td class="muted">${fmt(s.drive_modified_time)}</td></tr>`).join("")}</tbody></table></div>
    <p class="muted">Note: the Drive “modifiedTime” of the main sheet can lag behind its newest rows (app-written rows); freshness is judged from the newest record date.</p>
    <h2>Issues found (${q.issues.length})</h2>
    <div class="table-wrap"><table><thead><tr><th>Type</th><th>Detail</th></tr></thead><tbody>${q.issues.map((i) => `<tr><td>${esc(i.type)}</td><td class="mono">${esc(JSON.stringify(i))}</td></tr>`).join("")}</tbody></table></div>`;
}

async function viewMedia() {
  const m = await api("/api/media");
  const byKind = {};
  m.items.forEach((i) => (byKind[i.kind] = (byKind[i.kind] || 0) + 1));
  $("#app").innerHTML = `<h1>Images &amp; video</h1>
    <div class="grid g4"><div class="card kpi"><div class="l">Media references in source logs</div><div class="n">${m.summary.references}</div></div>
    <div class="card kpi"><div class="l">Files available locally</div><div class="n">${m.summary.available}</div></div>
    <div class="card kpi"><div class="l">Unlinked local files</div><div class="n">${m.summary.unlinked_local_files}</div></div></div>
    <div class="warnbox" style="margin-top:14px">The operational logs reference photos (daily checklists, incident reports), but the image files are not yet accessible to this system. Place exported photos or survey videos in <span class="mono">${esc(m.summary.media_dir)}</span>; they are matched to records by file name. Muse Spark image description is prepared; SAM 3.1 segmentation is pending verification of its output format.</div>
    <p class="muted">References by record kind: ${Object.entries(byKind).map(([k, n]) => `${esc(KIND_LABEL[k] || k)}: ${n}`).join(" · ")}</p>`;
}

/* ------------------------------------------------------------------ evidence drawer */
function bindEvidenceLinks() {
  document.querySelectorAll("[data-ev]").forEach((el) => el.addEventListener("click", (ev) => { ev.stopPropagation(); openEvidence(el.dataset.ev); }));
}
async function openEvidence(id) {
  const e = await api(`/api/evidence/${encodeURIComponent(id)}`);
  const src = e.source || {};
  const vals = Object.entries(e.values || {}).filter(([k]) => k !== "derived_from").map(([k, v]) => `<dt>${esc(k)}</dt><dd>${esc(typeof v === "object" ? JSON.stringify(v) : v)}</dd>`).join("");
  $("#drawer-body").innerHTML = `<h3>${esc(e.title)}</h3>
    <dl><dt>Evidence ID</dt><dd class="mono">${esc(e.evidence_id)}</dd><dt>Kind</dt><dd>${esc(KIND_LABEL[e.kind] || e.kind)}</dd>
    <dt>Time</dt><dd>${fmt(e.timestamp)}</dd><dt>Asset</dt><dd>${esc(e.asset_id || "—")} ${esc(e.asset_name || "")}</dd><dt>Zone</dt><dd>${esc(e.zone || "—")}</dd>
    <dt>Status</dt><dd>${esc(e.status || "—")} ${e.is_open ? '<span class="tag open">unresolved</span>' : ""}</dd>
    <dt>Text (original)</dt><dd>${esc(e.text || "—")}</dd>
    <dt>Hazard tags</dt><dd>${(e.tags || []).map((t) => `<span class="tag">${esc(t.tag)}: “${esc(t.term)}”</span>`).join("") || "—"}</dd>
    <dt>Flags</dt><dd>${(e.flags || []).map((f) => `<span class="tag">${esc(f)}</span>`).join("") || "—"}</dd></dl>
    <h3 style="margin-top:16px">Source (traceability)</h3>
    <dl><dt>File</dt><dd>${esc(src.source_title)}</dd><dt>Tab</dt><dd>${esc(src.sheet)}</dd><dt>Row</dt><dd>${src.row ? esc(src.row) : "derived (see below)"}</dd><dt>Record ID</dt><dd class="mono">${esc(src.record_id || "—")}</dd></dl>
    <h3 style="margin-top:16px">Values</h3><dl>${vals || "<dd>—</dd>"}</dl>
    ${e.media_refs?.length ? `<h3 style="margin-top:16px">Media referenced</h3>${e.media_refs.map((r) => `<div class="mono">${esc(r)}</div>`).join("")}` : ""}
    ${e.derived_records ? `<h3 style="margin-top:16px">Derived from meter readings</h3>${e.derived_records.map((r) => `<div class="mono">${esc(r.evidence_id)} · ${fmt(r.timestamp)} · reading ${esc(r.values.reading)} · row ${esc(r.source.row)}</div>`).join("")}` : ""}
    <p class="muted">Appears in: ${(e.in_alerts || []).map(esc).join(", ") || "no alert"}</p>`;
  $("#drawer").hidden = false;
}
$("#drawer-close").addEventListener("click", () => ($("#drawer").hidden = true));

/* ------------------------------------------------------------------ router */
async function route() {
  const h = location.hash || "#/";
  document.querySelectorAll("nav a").forEach((a) => a.classList.toggle("active", h === a.getAttribute("href") || (h.startsWith("#/alert/") && a.dataset.nav === "alerts")));
  try {
    if (!STATUS) await loadStatus();
    if (h.startsWith("#/alert/")) return await viewAlert(decodeURIComponent(h.slice(8)));
    if (h === "#/alerts") return await viewAlerts();
    if (h === "#/events") return await viewEvents();
    if (h === "#/quality") return await viewQuality();
    if (h === "#/media") return await viewMedia();
    return await viewOverview();
  } catch (e) {
    $("#app").innerHTML = `<div class="errbox">Could not load: ${esc(e.message)}</div>`;
  }
}
$("#refresh").addEventListener("click", async () => {
  const b = $("#refresh");
  b.disabled = true; b.textContent = "Analysing…";
  try { await api("/api/refresh", { method: "POST" }); STATUS = null; await route(); } finally { b.disabled = false; b.textContent = "Re-run analysis"; }
});
window.addEventListener("hashchange", () => { $("#drawer").hidden = true; route(); });
route();
