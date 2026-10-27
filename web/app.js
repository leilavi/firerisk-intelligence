/* FireRisk Intelligence dashboard — talks only to the local backend (/api). No sample data. */
"use strict";

const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const SEV = ["normal", "watch", "warning", "high", "emergency"];
const LABEL = { normal: "Normal", watch: "Watch", warning: "Warning", high: "High risk", emergency: "Emergency", unknown: "Not enough data" };
const KIND = {
  incident: "Incident report", construction: "Works log", asset_service: "Repair / maintenance",
  inspection_check: "Daily checklist", generator_run: "Generator log", meter_episode: "Meter analysis",
  meter_reading: "Meter reading", vehicle_day: "Vehicle count",
};
const ZONE_ORDER = ["Roof", "F4", "F3", "F2", "F1", "B1"];
const rank = (s) => SEV.indexOf(s);

const ICON = {
  normal: '<svg width="14" height="14" viewBox="0 0 14 14" aria-hidden="true"><circle cx="7" cy="7" r="6" fill="currentColor" opacity=".18"/><path d="M4 7.2l2 2 4-4.4" stroke="currentColor" stroke-width="1.8" fill="none" stroke-linecap="round"/></svg>',
  watch: '<svg width="14" height="14" viewBox="0 0 14 14" aria-hidden="true"><path d="M1 7s2.3-4 6-4 6 4 6 4-2.3 4-6 4-6-4-6-4z" fill="none" stroke="currentColor" stroke-width="1.6"/><circle cx="7" cy="7" r="1.8" fill="currentColor"/></svg>',
  warning: '<svg width="14" height="14" viewBox="0 0 14 14" aria-hidden="true"><path d="M7 1.5l6 11H1z" fill="currentColor" opacity=".25" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round"/><path d="M7 5.5v3.3" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/><circle cx="7" cy="10.6" r=".9" fill="currentColor"/></svg>',
  high: '<svg width="14" height="14" viewBox="0 0 14 14" aria-hidden="true"><path d="M4.3 1h5.4L13 4.3v5.4L9.7 13H4.3L1 9.7V4.3z" fill="currentColor" opacity=".3" stroke="currentColor" stroke-width="1.3"/><path d="M7 3.8v4" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/><circle cx="7" cy="10" r="1" fill="currentColor"/></svg>',
  emergency: '<svg width="14" height="14" viewBox="0 0 14 14" aria-hidden="true"><path d="M7 1c1 2.8 4.3 4.5 4.3 8.2A4.3 4.3 0 0 1 2.7 9.2C2.7 7 4 6 4.7 4.3c.6 1.6 1.4 2.2 2.2 2.4C7.2 5 7.4 3 7 1z" fill="currentColor"/></svg>',
  unknown: '<svg width="14" height="14" viewBox="0 0 14 14" aria-hidden="true"><circle cx="7" cy="7" r="6" fill="none" stroke="currentColor" stroke-width="1.5" stroke-dasharray="2.2 1.6"/><path d="M5.3 5.4a1.8 1.8 0 1 1 2.4 1.7c-.5.2-.7.5-.7 1v.4" stroke="currentColor" stroke-width="1.4" fill="none" stroke-linecap="round"/><circle cx="7" cy="10.4" r=".8" fill="currentColor"/></svg>',
};
const lvl = (s, big) => `<span class="lvl ${esc(s)}${big ? " lg" : ""}">${ICON[s] || ""}${esc(LABEL[s] || s)}</span>`;
const org = (k, txt) => `<span class="org ${k}">${esc(txt || { source: "Source record", derived: "Derived from data", rule: "Rule result", ai: "AI (Muse Spark)", test: "Test" }[k])}</span>`;
const day = (iso) => (iso ? new Date(iso).toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" }) : "undated");
const dt = (iso) => (iso ? new Date(iso).toLocaleString("en-GB", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" }) : "—");
const ago = (iso) => { if (!iso) return "—"; const d = (Date.now() - new Date(iso)) / 864e5; return d < 1 ? "today" : d < 2 ? "yesterday" : `${Math.round(d)} days ago`; };
const chip = (id) => `<button class="chip" data-ev="${esc(id)}" title="Open source record">${esc(id.length > 30 ? id.slice(0, 28) + "…" : id)}</button>`;

async function api(path, opts) {
  const r = await fetch(path, opts);
  if (!r.ok) throw new Error(`${r.status} ${await r.text()}`);
  return r.json();
}
let S = null;
async function loadStatus() {
  S = await api("/api/status");
  $("#building").textContent = S.building;
  const oldest = S.sources.filter((x) => x.latest_record).map((x) => x.latest_record).sort().pop();
  const issues = S.sources_down.length + S.sources_stale.length;
  const sy = S.sync || {};
  const syncTxt = !sy.configured ? "" : sy.last && !sy.last.ok
    ? ` · <span style="color:var(--high-ink)">Drive update failed ${dt(sy.last.started_at)}</span>`
    : sy.last_ok_at ? ` · Drive checked ${dt(sy.last_ok_at)}` : "";
  $("#freshness").innerHTML = `Analysed <b>${dt(S.generated_at)}</b> · newest record ${ago(oldest)}${syncTxt}${issues ? ` · <span style="color:var(--high-ink)">${issues} source issue(s)</span>` : ""}`;
  const rb = $("#refresh");
  if (!rb.disabled) rb.textContent = sy.configured ? "Update from Drive" : "Re-run analysis";
  rb.title = sy.configured ? "Download the latest files from Google Drive, then re-run the analysis" : "Re-run the analysis on the current data snapshot";
  const ai = $("#ai-status");
  ai.textContent = S.ai.configured ? (S.ai.mode === "live" ? `AI ready · ${S.ai.model}` : "AI in TEST mode") : "AI not configured";
  ai.className = "aipill" + (S.ai.configured ? " on" : "");
}

/* ============================== Overview ============================== */
async function viewOverview() {
  const [alerts, assets, trends] = await Promise.all([api("/api/alerts"), api("/api/assets"), api("/api/trends")]);
  const active = alerts.filter((a) => !["resolved", "false_alarm"].includes(a.verification?.status));
  const byZone = {};
  active.forEach((a) => { if (!byZone[a.zone] || rank(a.severity) > rank(byZone[a.zone].severity)) byZone[a.zone] = a; });
  const floor = (z) => {
    const a = byZone[z]; const recs = S.zone_records[z] || 0;
    const st = a ? a.severity : recs ? "normal" : "unknown";
    const what = a ? esc(a.headline) : recs ? `No rule signal · ${recs} records checked` : "No records for this floor in the data";
    const tag = a ? "a" : "div";
    return `<${tag} class="floor ${st}" ${a ? `href="#/alert/${esc(a.alert_id)}"` : ""}>
      <span class="code">${esc(z)}</span><span class="what">${what}</span>
      <span>${a ? lvl(st) : st === "unknown" ? lvl("unknown") : `<span class="lamp" title="Normal"></span>`}</span></${tag}>`;
  };
  const whole = byZone.Building;
  const top = active.filter((a) => rank(a.severity) >= rank("warning")).slice(0, 4);
  $("#app").innerHTML = `
    <div class="hero">
      <section class="panel" aria-labelledby="zones-h">
        <h2 id="zones-h">Building zones</h2>
        <div class="building">${ZONE_ORDER.map(floor).join("")}
          ${whole ? `<a class="floor ground ${whole.severity}" href="#/alert/${esc(whole.alert_id)}"><span class="code">All</span><span class="what">${esc(whole.headline)}</span>${lvl(whole.severity)}</a>` : ""}
        </div>
        <p class="muted small" style="margin:12px 0 0">Colour = highest rule level in that zone. Grey = no records to judge.</p>
      </section>
      <section aria-labelledby="now-h">
        <div class="counts">
          <div class="count"><span class="n num">${S.active_alerts}</span><span class="l">active alerts</span></div>
          <div class="count serious"><span class="n num">${S.serious_alerts}</span><span class="l">high risk or emergency</span></div>
          <div class="count"><span class="n num">${S.abnormal_equipment}</span><span class="l">equipment with signals</span></div>
          <div class="count"><span class="n num">${S.zones_attention.length}</span><span class="l">zones need attention</span></div>
        </div>
        <h2 id="now-h" style="margin-bottom:10px">Needs attention now</h2>
        <div class="priority">${top.map(pcard).join("") || '<div class="empty">No alert at Warning level or above.</div>'}</div>
        ${S.sources_down.length || S.sources_stale.length ? `<div class="warnbox" style="margin-top:14px"><b>Data source issue.</b> ${[...S.sources_down.map((x) => `${esc(x.sheet || x.source)}: ${esc(x.error)}`), ...S.sources_stale.map((x) => `${esc(x.sheet || x.source)}: newest record ${x.age_days} days old`)].join("; ")}. <a href="#/quality">Check data sources</a></div>` : ""}
      </section>
    </div>
    <div class="grid2">
      <section class="panel"><h2>Fault records by hazard type, per week</h2>
        <p class="muted small" style="margin:-6px 0 10px">${org("source")}Counted from incident and repair records that contain a fault. Last 12 weeks.</p>
        ${stackChart(trends)}</section>
      <section class="panel"><h2>Equipment with signals</h2>
        ${assets.length ? `<div class="scroll" style="border:0"><table class="tbl"><thead><tr><th>Level</th><th>Equipment</th><th>Open</th><th>Last event</th></tr></thead><tbody>
        ${assets.slice(0, 8).map((r) => `<tr class="click" data-asset="${esc(r.asset_id)}"><td>${lvl(r.severity)}</td><td><b>${esc(r.name || r.asset_id)}</b><div class="muted small">${esc(r.asset_id)} · ${esc(r.zone || "")}</div></td><td class="num">${r.open_records}</td><td class="small">${day(r.last_event)}</td></tr>`).join("")}</tbody></table></div>
        <p style="margin:10px 0 0"><a href="#/equipment">All equipment</a></p>` : '<div class="empty">No equipment has a rule signal.</div>'}</section>
    </div>`;
  bindAssets();
}

function pcard(a) {
  return `<a class="pcard ${esc(a.severity)}" href="#/alert/${esc(a.alert_id)}">
    ${lvl(a.severity)}<span class="zone">${esc(a.zone_label)}</span><span class="stat">${esc(a.verification?.status || "new")}</span>
    <span class="head">${esc(a.headline)}</span>
    <span class="meta"><span>Act ${esc(a.deadline?.text || "—")}</span><span>${a.open_items} unresolved record(s)</span><span>Latest evidence ${day(a.last_seen)}</span>${a.ai ? `<span>${org(a.ai.mode === "test" ? "test" : "ai", a.ai.mode === "test" ? "AI test" : "AI reviewed")}</span>` : ""}</span></a>`;
}

const CAT = ["--cat1", "--cat2", "--cat3", "--cat4", "--cat5", "--cat6", "--cat7"];
const TAGNAME = { water_ingress: "Water ingress", electrical_room: "Electrical room", fire_detection: "Fire detection", backup_power: "Backup power", fire_water: "Fire water", mechanical_jam: "Mechanical jam", burnt_overheat: "Burnt / overheat", pa_system: "PA system", smoke_control: "Smoke exhaust", lightning: "Lightning", motor_equipment: "Motor" };
function stackChart(t) {
  const keys = Object.keys(t.hazard_records);
  if (!keys.length) return '<div class="empty">No fault records in the last 12 weeks.</div>';
  const W = 560, H = 190, P = 26, n = t.weeks.length, bw = (W - P * 2) / n - 6;
  const totals = t.weeks.map((_, i) => keys.reduce((s, k) => s + t.hazard_records[k][i], 0));
  const max = Math.max(1, ...totals);
  let bars = "";
  t.weeks.forEach((w, i) => {
    let y = H - P;
    keys.forEach((k, j) => {
      const v = t.hazard_records[k][i]; if (!v) return;
      const h = (v / max) * (H - P * 2);
      y -= h;
      bars += `<rect x="${P + i * ((W - P * 2) / n) + 3}" y="${y.toFixed(1)}" width="${bw.toFixed(1)}" height="${h.toFixed(1)}" rx="2" fill="var(${CAT[j % CAT.length]})"><title>Week of ${esc(w)}: ${v} × ${esc(TAGNAME[k] || k)}</title></rect>`;
    });
    if (totals[i]) bars += `<text x="${P + i * ((W - P * 2) / n) + 3 + bw / 2}" y="${(y - 4).toFixed(1)}" font-size="10" text-anchor="middle" fill="#4F5D6E">${totals[i]}</text>`;
  });
  const lbl = (i) => `<text x="${P + i * ((W - P * 2) / n) + 3 + bw / 2}" y="${H - 8}" font-size="10" text-anchor="middle" fill="#4F5D6E">${esc(day(t.weeks[i]).slice(0, 6))}</text>`;
  return `<svg class="spark" viewBox="0 0 ${W} ${H}" role="img" aria-label="Weekly fault records by hazard type">
    <line x1="${P}" x2="${W - P}" y1="${H - P}" y2="${H - P}" stroke="#DDE4EB"/>${bars}${[0, Math.floor(n / 2), n - 1].map(lbl).join("")}</svg>
    <div class="chart-legend">${keys.map((k, j) => `<span><i style="background:var(${CAT[j % CAT.length]})"></i>${esc(TAGNAME[k] || k)}</span>`).join("")}</div>`;
}

/* ============================== Alerts list ============================== */
async function viewAlerts() {
  const alerts = await api("/api/alerts");
  $("#app").innerHTML = `<h1>Alerts</h1>
    <p class="muted">Sorted by level, then most recent evidence. One alert per zone; open it to see the evidence.</p>
    <div class="filters" role="group" aria-label="Filter by level">
      ${[["all", "All"], ["warning", "Warning and above"], ["high", "High risk and above"]].map(([k, t], i) => `<button class="chipbtn" data-f="${k}" aria-pressed="${i === 0}">${t}</button>`).join("")}
      <label class="small muted" style="margin-left:8px"><input type="checkbox" id="hide-res" checked> Hide resolved</label>
    </div><div id="rows"></div>`;
  let f = "all";
  const render = () => {
    const hide = $("#hide-res").checked;
    const list = alerts.filter((a) => (f === "all" || rank(a.severity) >= rank(f)) && !(hide && ["resolved", "false_alarm"].includes(a.verification?.status)));
    $("#rows").innerHTML = list.map((a) => `<a class="arow ${esc(a.severity)}" href="#/alert/${esc(a.alert_id)}">
      <span>${lvl(a.severity)}<div class="stat" style="margin-top:6px">${esc(a.verification?.status || "new")}</div></span>
      <span><span class="t">${esc(a.zone_label)}</span><div>${esc(a.headline)}</div><div class="why">${esc(a.why)}</div></span>
      <span class="stat c3">Detected <b>${day(a.detected_at)}</b><br>Latest evidence <b>${day(a.last_seen)}</b></span>
      <span class="stat c4">Act <b>${esc(a.deadline?.text || "—")}</b><br>${a.open_items} unresolved</span></a>`).join("") || '<div class="empty">No alerts match this filter.</div>';
  };
  $$(".chipbtn").forEach((b) => b.addEventListener("click", () => { f = b.dataset.f; $$(".chipbtn").forEach((x) => x.setAttribute("aria-pressed", x === b)); render(); }));
  $("#hide-res").addEventListener("change", render);
  render();
}

/* ============================== Alert detail ============================== */
async function viewAlert(id) {
  const d = await api(`/api/alerts/${encodeURIComponent(id)}`);
  const a = d.alert, F = d.fields, sm = d.summary;
  const insufficient = F.assessment_class === "insufficient_evidence";
  const findings = d.evidence.filter((e) => e.role === "finding" && e.kind !== "meter_episode")
    .sort((x, y) => (y.is_open === true) - (x.is_open === true) || (y.timestamp || "").localeCompare(x.timestamp || ""));
  const episodes = d.evidence.filter((e) => e.kind === "meter_episode");
  const context = d.evidence.filter((e) => e.role === "context");
  const top = d.signals[0];
  const evRow = (e) => {
    const v = e.values || {};
    let val = "";
    if (e.kind === "meter_episode") val = `${fmtNum(v.peak)} <small>vs median ${fmtNum(v.median)} ${esc(v.unit || "")}${v.unit_verified ? "" : " (unit unverified)"}</small>`;
    else if (e.kind === "generator_run" && v.minutes != null) val = `${v.minutes} min<small>${v.fuel_stock_l != null ? `fuel ${v.fuel_stock_l} L` : ""}</small>`;
    return `<div class="evi"><span class="when">${day(e.timestamp)}</span>
      <span><span class="what">${esc(e.title)}</span>${e.is_open ? '<span class="open">● unresolved</span>' : ""}
        <div class="src">${org(e.origin)}${esc(KIND[e.kind] || e.kind)} · ${esc(e.source?.sheet || "")}${e.source?.row ? ` · row ${e.source.row}` : ""} ${chip(e.evidence_id)}</div>
        ${e.status ? `<div class="src">Status in source: ${esc(e.status)}</div>` : ""}</span>
      <span class="val">${val}</span></div>`;
  };
  const strong = a.links.filter((l) => !(l.types.length === 1 && l.types[0] === "same_zone_time_window"));
  const inv = d.investigation;

  $("#app").innerHTML = `
    <div class="crumbs"><a href="#/alerts">Alerts</a> / ${esc(a.zone_label)}</div>
    <div class="dhead">${lvl(a.severity, true)}<h1>${esc(a.zone_label)}</h1>${org("rule", "Rule result")}</div>
    <div class="layout"><div>
      <section class="q"><h2><span class="qn">1</span>What is abnormal?</h2>
        <p class="lead">${esc(F.headline)}</p>
        ${insufficient ? '<div class="insuff">Not enough data to confirm. The records below are signals, not a confirmed hazard.</div>' : `<p class="muted" style="margin:4px 0 0">${esc(F.assessment_text)}</p>`}
      </section>

      <section class="q"><h2><span class="qn">2</span>What evidence supports it?</h2>
        ${findings.slice(0, 6).map(evRow).join("")}
        ${d.trends.length ? `<h3 style="margin:16px 0 4px">Meter readings around each anomaly</h3><p class="muted small" style="margin:0 0 8px">${org("derived")}Daily consumption from the real readings, 7 days before and after. Dashed line = baseline median; ringed points = anomaly days; grey = missing or averaged days.</p>
          ${d.trends.slice(0, 2).map(trendChart).join("")}
          ${d.trends.length > 2 ? `<details><summary>${d.trends.length - 2} more meter windows</summary>${d.trends.slice(2).map(trendChart).join("")}</details>` : ""}` : ""}
        ${findings.length > 6 || episodes.length ? `<details><summary>All ${findings.length + episodes.length} evidence records</summary>${[...findings.slice(6), ...episodes].map(evRow).join("")}</details>` : ""}
        ${context.length ? `<details><summary>${context.length} context records that may contradict the alert</summary><p class="muted small">Latest daily checklists and scheduled generator runs. A passing checklist does not prove the issue is gone.</p>${context.map(evRow).join("")}</details>` : ""}
      </section>

      <section class="q"><h2><span class="qn">3</span>Why is this a risk?</h2>
        <ul style="margin:0 0 6px 18px;padding:0">${F.why_short.map((w) => `<li>${esc(w)}</li>`).join("")}</ul>
        <details><summary>Exact rule basis</summary><ul class="small">${F.why.map((w) => `<li>${esc(w)}</li>`).join("")}</ul></details>
        ${top ? `<h3 style="margin:14px 0 4px">How it could escalate: ${esc(top.title.toLowerCase())}</h3><ol class="chain">${top.fields.risk_chain.map((c) => `<li>${esc(c)}</li>`).join("")}</ol>
          <p class="muted small" style="margin:0">Trigger: ${esc(top.fields.trigger_condition)} Consequence: ${esc(top.fields.consequence)}</p>` : ""}
        <details><summary>All ${d.signals.length} rule signals in this zone</summary>
          ${d.signals.map((s) => `<div class="sig"><div class="row">${lvl(s.severity)}<b>${esc(s.title)}</b>${s.is_open ? '<span class="open">● unresolved</span>' : ""}<span class="muted small">${esc(s.rule_id)} · ${s.origin === "PORTED" ? "rule from the earlier skill" : "new rule"}</span></div>
            <div class="small">${esc(s.basis)}</div><div class="small muted">Comparison: ${esc(s.fields.comparison)}</div></div>`).join("")}</details>
        ${strong.length ? `<details><summary>${strong.length} links between records</summary><p class="muted small">Links show records worth checking together. They do not prove cause.</p>
          <div class="scroll"><table class="tbl"><thead><tr><th>Record</th><th>Record</th><th>Reason</th></tr></thead><tbody>${strong.slice(0, 40).map((l) => `<tr><td>${chip(l.a)}</td><td>${chip(l.b)}</td><td class="small">${l.reasons.map(esc).join("<br>")}</td></tr>`).join("")}</tbody></table></div></details>` : ""}
      </section>

      <section class="q"><h2><span class="qn">4</span>Which area and equipment?</h2>
        <p style="margin:0 0 10px">Zone <b>${esc(a.zone_label)}</b></p>
        <div class="assets">${F.affected_assets.map(([id, name]) => `<button class="asset" data-asset="${esc(id)}" style="cursor:pointer;text-align:left"><b>${esc(name || id)}</b><span class="muted small">${esc(id)}</span></button>`).join("") || '<span class="muted">No equipment code in the records.</span>'}</div>
        ${d.maintenance_history.length ? `<details><summary>Repair and inspection history of this equipment (${d.maintenance_history.length})</summary><div class="scroll"><table class="tbl"><thead><tr><th>Date</th><th>Record</th><th>Equipment</th><th>Status</th></tr></thead><tbody>
          ${d.maintenance_history.map((e) => `<tr class="click" data-ev="${esc(e.evidence_id)}"><td class="small">${day(e.timestamp)}</td><td>${esc(e.title)}<div class="muted small">${esc(KIND[e.kind] || e.kind)}</div></td><td class="small">${esc(e.asset_id)}</td><td class="small">${esc(e.status || "")}${e.is_open ? '<span class="open">● open</span>' : ""}</td></tr>`).join("")}</tbody></table></div></details>` : ""}
      </section>

      <section class="q"><h2><span class="qn">5</span>What should happen next?</h2>
        <p class="muted small" style="margin:-4px 0 8px">${org("rule")}Checks defined by the rule set for this level. Deadline: <b>${esc(F.deadline.text)}</b> (${esc(F.deadline.basis)}).</p>
        <ul class="actions">${dedupe(F.actions.map((x) => x.action)).map((x) => `<li><span class="box" aria-hidden="true"></span><span>${esc(x)}</span></li>`).join("")}</ul>
        ${top ? `<p class="small" style="margin:10px 0 0"><b>Close the alert when:</b> ${esc(top.fields.closure_condition)}</p>` : ""}
      </section>

      <section class="q"><h2><span class="qn">6</span>What is not verified?</h2>
        ${insufficient ? '<div class="insuff">Not enough data to confirm.</div>' : ""}
        <ul class="unk">${F.unknowns.map((u) => `<li>${esc(u)}</li>`).join("")}
          ${top ? top.fields.possible_causes.map((c) => `<li>Possible cause, not verified: ${esc(c.cause)} <span class="muted small">(${esc(c.basis)})</span></li>`).join("") : ""}
          ${d.data_quality.length ? `<li>${d.data_quality.length} data issue(s) in these records<details><summary>Show</summary>${d.data_quality.map((q) => `<div class="small">${chip(q.evidence_id)} ${esc(q.type.replace(/_/g, " "))}</div>`).join("")}</details></li>` : ""}</ul>
      </section>

      <section class="q ai" id="ai-panel"></section>
    </div>

    <aside class="side">
      <section class="q"><h2>Level and urgency</h2>
        <dl class="kv"><dt>Rule level</dt><dd>${lvl(a.severity)}</dd><dt>Urgency</dt><dd>${esc(F.urgency.label)}</dd><dt>Act</dt><dd><b>${esc(F.deadline.text)}</b></dd>
        <dt>Confidence</dt><dd>${esc(F.confidence.level)} <span class="muted small">— ${esc(F.confidence.reason)}</span></dd>
        <dt>Detected</dt><dd>${dt(sm.detected_at)}</dd><dt>Evidence from</dt><dd>${day(a.first_seen)} to ${day(a.last_seen)}</dd></dl></section>
      <section class="q"><h2>Verification</h2>${verifyBox(d)}</section>
      <section class="q"><h2>Alert history</h2>
        ${d.history.slice(0, 6).map((h) => `<div class="small" style="padding:4px 0">${dt(h.recorded_at)} ${lvl(h.severity)} <span class="muted">${h.open_items} open</span></div>`).join("") || '<span class="muted small">First analysis.</span>'}</section>
    </aside></div>`;
  renderAI(inv, a);
  bindEvidence(); bindAssets(); bindVerify(a.alert_id);
}

const fmtNum = (v) => (v == null ? "—" : Math.abs(v) >= 1000 ? Math.round(v).toLocaleString("en-GB") : (+v).toFixed(v % 1 ? 1 : 0));
const dedupe = (l) => [...new Set(l)];

function trendChart(t) {
  const pts = t.points; if (!pts.length) return "";
  const W = 600, H = 150, P = 30;
  const vals = pts.map((p) => p.value).filter((v) => v != null);
  const max = Math.max(...vals, t.median || 0) * 1.15 || 1;
  const x = (i) => P + (i * (W - P * 2)) / Math.max(1, pts.length - 1);
  const y = (v) => H - P - (v / max) * (H - P * 2);
  let line = "", pen = false, marks = "", gaps = "", labels = "";
  pts.forEach((p, i) => {
    const inEp = p.day >= t.start && p.day <= (t.end || t.start);
    if (inEp) gaps += `<rect x="${x(i) - 9}" y="${P - 8}" width="18" height="${H - P * 2 + 8}" fill="#FFE9D6" opacity=".7"/>`;
    if (p.value == null || p.flag === "negative_excluded") { pen = false; gaps += `<rect x="${x(i) - 3}" y="${P}" width="6" height="${H - P * 2}" fill="#DDE4EB"><title>${esc(p.day)}: ${esc(p.flag || "missing")}</title></rect>`; return; }
    line += `${pen ? "L" : "M"}${x(i).toFixed(1)},${y(p.value).toFixed(1)}`; pen = p.flag !== "averaged_gap";
    marks += p.spike ? `<circle cx="${x(i)}" cy="${y(p.value)}" r="6" fill="#fff" stroke="#EE7417" stroke-width="2.5"><title>${esc(p.day)}: ${fmtNum(p.value)} (${p.spike})</title></circle>`
      : `<circle cx="${x(i)}" cy="${y(p.value)}" r="2.6" fill="#3B6FB6"><title>${esc(p.day)}: ${fmtNum(p.value)}</title></circle>`;
    if (p.spike) labels += `<text x="${x(i)}" y="${y(p.value) - 11}" font-size="11" text-anchor="middle" font-weight="700" fill="#8A3A00">${fmtNum(p.value)}</text>`;
  });
  const med = t.median != null ? `<line x1="${P}" x2="${W - P}" y1="${y(t.median)}" y2="${y(t.median)}" stroke="#4F5D6E" stroke-dasharray="5 4"/><text x="${W - P}" y="${y(t.median) - 5}" font-size="10" text-anchor="end" fill="#4F5D6E">median ${fmtNum(t.median)}</text>` : "";
  return `<div style="margin:8px 0 14px"><div class="small"><b>${esc(t.meter_name || t.meter)}</b> <span class="muted">${esc(t.meter)} · ${esc(t.unit || "")}${t.unit_verified ? "" : " (unit not verified)"} · label: ${esc(t.label)}</span> ${chip(t.evidence_id)}</div>
    <svg class="spark" viewBox="0 0 ${W} ${H}" role="img" aria-label="Daily consumption around the anomaly">${gaps}${med}<path d="${line}" fill="none" stroke="#3B6FB6" stroke-width="2"/>${marks}${labels}
    <text x="${P}" y="${H - 8}" font-size="10" fill="#4F5D6E">${esc(day(pts[0].day))}</text><text x="${W - P}" y="${H - 8}" font-size="10" text-anchor="end" fill="#4F5D6E">${esc(day(pts[pts.length - 1].day))}</text></svg></div>`;
}

function verifyBox(d) {
  const cur = d.verification?.status || "new";
  const states = [["new", "New"], ["acknowledged", "Acknowledged"], ["investigating", "Investigating"], ["confirmed", "Confirmed on site"], ["resolved", "Resolved"], ["false_alarm", "False alarm"]];
  return `<div class="stack"><select id="vstatus" aria-label="Verification status">${states.map(([k, t]) => `<option value="${k}" ${k === cur ? "selected" : ""}>${t}</option>`).join("")}</select>
    <input type="text" id="vby" placeholder="Your name or role"><textarea id="vnote" placeholder="What was checked and the result"></textarea>
    <button class="btn" id="vsave">Save status</button><span class="small muted" id="vmsg"></span></div>
    <div class="small muted" style="margin-top:10px">${d.status_log.slice(0, 4).map((x) => `${dt(x.changed_at)} — ${esc(x.status.replace("_", " "))}${x.note ? `: ${esc(x.note)}` : ""}${x.changed_by ? ` (${esc(x.changed_by)})` : ""}`).join("<br>")}</div>
    <p class="small muted">Only a person can mark an alert “Confirmed on site”.</p>`;
}
function bindVerify(id) {
  $("#vsave").addEventListener("click", async () => {
    $("#vmsg").textContent = "Saving…";
    try { await api(`/api/alerts/${encodeURIComponent(id)}/status`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ status: $("#vstatus").value, note: $("#vnote").value || null, by: $("#vby").value || null }) }); route(); }
    catch (e) { $("#vmsg").textContent = "Could not save: " + e.message; }
  });
}

function renderAI(inv, a) {
  const el = $("#ai-panel");
  const isTest = inv && inv.api_mode === "test";
  const tag = isTest ? org("test", "Test result (mock API) — not Muse Spark") : org("ai");
  const btn = `<button class="btn primary" id="ai-run" ${S.ai.configured ? "" : "disabled"}>${inv && inv.status === "ok" ? "Run a new AI explanation" : "Explain with Muse Spark"}</button>`;
  const head = `<h2 style="margin-bottom:6px">AI explanation ${tag}</h2><p class="muted small" style="margin:0 0 10px">Muse Spark reads the evidence above (names and record IDs are pseudonymised) and proposes hypotheses. It does not add data and does not change the rule level.</p>`;
  if (!S.ai.configured) { el.innerHTML = head + '<div class="warnbox">The Meta Model API key is not set on this computer (run setup_api_key.bat). Everything above works without AI.</div>' + btn; return; }
  if (!inv) { el.innerHTML = head + btn; bindAI(a.alert_id); return; }
  if (inv.status !== "ok") { el.innerHTML = head + `<div class="errbox">Last attempt ${dt(inv.created_at)} failed (${esc(inv.error_kind)}): ${esc(inv.error)}. The rule result above is unaffected.</div>` + btn; bindAI(a.alert_id); return; }
  const r = inv.result, v = inv.validation || {}, ra = r.risk_assessment;
  const ids = (l) => (l || []).map(chip).join("") || '<span class="muted small">none</span>';
  el.innerHTML = head + `
    <div class="small muted" style="margin-bottom:8px">${esc(inv.model)} · ${dt(inv.created_at)} · ${esc(inv.seconds)} s</div>
    ${v.ok === false ? `<div class="warnbox">${v.invalid_evidence_ids?.length ? `Removed ${v.invalid_evidence_ids.length} citation(s) to records that do not exist. ` : ""}${v.unsupported_facts?.length ? `${v.unsupported_facts.length} statement(s) had no valid source and are marked unsupported.` : ""}</div>` : ""}
    <p style="font-size:16px;margin:4px 0 10px">${esc(r.summary)}</p>
    <p class="small">AI priority ${lvl(ra.ai_priority)} · rule level ${lvl(a.severity)} — ${ra.agrees_with_rule_severity ? "agrees" : "differs"}: ${esc(ra.rationale)}</p>
    <details open><summary>Hypotheses (${r.hypotheses.length}) — not confirmed</summary>${r.hypotheses.map((h) => `<div class="hyp"><span class="plaus">${esc(h.plausibility)} plausibility</span> <b>${esc(h.cause)}</b><div class="small">${esc(h.reasoning)}</div><div class="small muted">Supports: ${ids(h.supporting_evidence_ids)} Contradicts: ${ids(h.contradicting_evidence_ids)}</div><div class="small"><i>How to verify:</i> ${esc(h.how_to_verify)}</div></div>`).join("")}</details>
    <details><summary>AI-suggested actions (${r.recommended_actions.length})</summary><ul class="actions">${r.recommended_actions.map((x) => `<li><span class="box" aria-hidden="true"></span><span><b>${esc(x.urgency.replace(/_/g, " "))}</b> — ${esc(x.action)} <span class="muted small">(${esc(x.responsible_role)})</span><br><span class="small muted">${esc(x.reason)}</span> ${ids(x.evidence_ids)}</span></li>`).join("")}</ul></details>
    <details><summary>Facts the AI read from the records (${r.observed_facts.length})</summary><ul style="margin:6px 0 0 18px;padding:0">${r.observed_facts.map((f) => `<li class="small">${esc(f.statement)} ${f.supported === false ? '<b style="color:var(--emergency)">unsupported</b>' : ""} ${ids(f.evidence_ids)}</li>`).join("")}</ul></details>
    <details><summary>Escalation pathway and missing information</summary><ol class="small">${r.escalation_pathway.map((s) => `<li>${esc(s.step)} <span class="muted">— if ${esc(s.condition)}</span></li>`).join("")}</ol><ul class="unk">${r.missing_information.map((m) => `<li><b>${esc(m.item)}</b> — ${esc(m.why_it_matters)}</li>`).join("")}</ul><p class="small"><b>Uncertainty:</b> ${esc(r.uncertainty)}</p></details>
    <div style="margin-top:12px">${btn}</div>`;
  bindAI(a.alert_id); bindEvidence();
}
function bindAI(id) {
  const b = $("#ai-run"); if (!b) return;
  b.addEventListener("click", async () => {
    b.disabled = true; b.innerHTML = '<span class="spinner"></span>Muse Spark is reading the evidence…';
    try { await api(`/api/alerts/${encodeURIComponent(id)}/investigate`, { method: "POST" }); } catch (e) { alert("The AI request failed: " + e.message); }
    route();
  });
}

/* ============================== Equipment ============================== */
async function viewEquipment() {
  const rows = await api("/api/assets");
  $("#app").innerHTML = `<h1>Equipment with rule signals</h1><p class="muted">Equipment named in a rule signal, highest level first. Open a row for its full record history.</p>
    <div class="scroll"><table class="tbl"><thead><tr><th>Level</th><th>Equipment</th><th>Zone</th><th>Signals</th><th>Unresolved</th><th>Last event</th></tr></thead><tbody>
    ${rows.map((r) => `<tr class="click" data-asset="${esc(r.asset_id)}"><td>${lvl(r.severity)}</td><td><b>${esc(r.name || r.asset_id)}</b><div class="muted small">${esc(r.asset_id)}</div></td><td>${esc(r.zone || "")}</td><td class="small">${r.signals.map(esc).join("<br>")}</td><td class="num">${r.open_records}</td><td class="small">${day(r.last_event)}</td></tr>`).join("")}</tbody></table></div>`;
  bindAssets();
}

/* ============================== Events / quality / media ============================== */
async function viewEvents() {
  const evs = await api("/api/events");
  const kinds = [...new Set(evs.map((e) => e.kind))];
  $("#app").innerHTML = `<h1>Fire-relevant event history</h1><p class="muted">Records that carry a fire-safety tag, and meter-analysis episodes. Hover a tag to see the matched words.</p>
    <div class="filters"><select id="fk" style="width:auto"><option value="">All record types</option>${kinds.map((k) => `<option value="${k}">${esc(KIND[k] || k)}</option>`).join("")}</select>
    <input type="text" id="fq" placeholder="Search text" style="width:220px"><span class="muted small" id="fc"></span></div>
    <div class="scroll"><table class="tbl"><thead><tr><th>Date</th><th>Type</th><th>Zone</th><th>Record</th><th>Tags</th><th>Status</th></tr></thead><tbody id="erows"></tbody></table></div>`;
  const render = () => {
    const k = $("#fk").value, q = $("#fq").value.toLowerCase();
    const list = evs.filter((e) => (!k || e.kind === k) && (!q || (e.title + " " + e.text).toLowerCase().includes(q)));
    $("#fc").textContent = `${list.length} records`;
    $("#erows").innerHTML = list.map((e) => `<tr class="click" data-ev="${esc(e.evidence_id)}"><td class="small">${day(e.timestamp)}</td><td class="small">${org(e.origin)}${esc(KIND[e.kind] || e.kind)}</td><td>${esc(e.zone || "—")}</td>
      <td>${esc(e.title)}</td><td>${(e.tags || []).filter((t) => !["checklist_pass", "fault"].includes(t.tag)).map((t) => `<span class="org source" title="matched: ${esc(t.term)}">${esc(TAGNAME[t.tag] || t.tag)}</span>`).join("")}</td>
      <td class="small">${esc(e.status || "")}${e.is_open ? '<span class="open">● open</span>' : ""}</td></tr>`).join("");
    bindEvidence();
  };
  $("#fk").addEventListener("change", render); $("#fq").addEventListener("input", render); render();
}

async function viewQuality() {
  const q = await api("/api/quality");
  const groups = {};
  q.issues.forEach((i) => (groups[i.type] = groups[i.type] || []).push(i));
  $("#app").innerHTML = `<h1>Data sources</h1><p class="muted">What the analysis read, how fresh it is, and what looked wrong. Freshness is judged by the newest record, because the file's modified time can lag behind app-written rows.</p>
    <div class="scroll"><table class="tbl"><thead><tr><th>Source</th><th>Tab</th><th>State</th><th>Rows read</th><th>In scope</th><th>Newest record</th><th>Snapshot taken</th></tr></thead><tbody>
    ${q.sources.map((s) => `<tr><td>${esc(s.source)}</td><td>${esc(s.sheet || "—")}</td><td>${s.error ? `${lvl("unknown")} <span class="small">${esc(s.error)}</span>` : s.stale ? `${lvl("warning")} <span class="small">older than expected (${s.age_days} d)</span>` : `${lvl("normal")} <span class="small">${s.expected_cadence_days ? `${s.age_days} d old` : "event log"}</span>`}</td>
      <td class="num">${esc(s.rows_read ?? "—")}</td><td class="num">${esc(s.in_scope ?? "—")}</td><td class="small">${dt(s.latest_record)}</td><td class="small">${dt(s.snapshot_at)}</td></tr>`).join("")}</tbody></table></div>
    ${syncPanel(await api("/api/sync"), q.sources)}
    <h2 style="margin:24px 0 10px">Issues found (${q.issues.length})</h2>
    ${Object.entries(groups).map(([k, l]) => `<details ${l.length < 6 ? "open" : ""}><summary>${esc(k.replace(/_/g, " "))} (${l.length})</summary><ul class="small">${l.map((i) => `<li>${i.evidence_id ? chip(i.evidence_id) : ""} ${esc(i.title || i.detail || i.meter || i.sheet || "")} ${i.date ? esc(i.date) : ""}</li>`).join("")}</ul></details>`).join("") || '<div class="empty">No data issues found.</div>'}`;
  bindEvidence();
}

const SYNC_STATUS = { updated: ["normal", "Updated"], unchanged: ["normal", "No change"], failed: ["unknown", "Failed, previous file kept"], ignored: ["unknown", "Ignored"] };
function syncPanel(sy, sources) {
  const errs = sources.filter((s) => s.sync_error);
  const head = `<h2 style="margin:24px 0 10px">Automatic updates from Google Drive</h2>`;
  if (!sy.configured) return `${head}<div class="empty">Not set up. The analysis uses the snapshot taken on ${dt(sources.find((s) => s.snapshot_at)?.snapshot_at)}. To update automatically, run <b>setup_drive_sync.bat</b> once (see README).</div>`;
  const rows = (sy.history || []).map((r) => `<tr><td class="small">${dt(r.started_at)}</td><td class="small">${esc(r.trigger === "auto" ? "automatic" : r.trigger)}</td>
    <td><b style="color:${r.ok ? "#1E6B3D" : "var(--high-ink)"}">${r.ok ? "✓ OK" : "✕ Failed"}</b> <span class="small">${r.ok ? (r.changed ? "new data" : "no change") : esc(r.error || "some files failed")}</span></td>
    <td class="small">${Object.entries(r.files || {}).map(([k, f]) => `${esc(k)}: ${esc((SYNC_STATUS[f.status] || ["", f.status])[1])}${f.error ? ` (${esc(f.error)})` : ""}`).join("<br>") || "—"}</td><td class="num">${esc(r.seconds ?? "—")}</td></tr>`).join("");
  return `${head}<p class="muted small">${sy.auto_minutes ? `Runs every ${sy.auto_minutes} min while the dashboard is open${sy.next_at ? `; next ${dt(sy.next_at)}` : ""}.` : "Automatic runs are off; use the Update from Drive button."} A file is replaced only after it opens as a valid workbook; otherwise the previous file is kept and its older date stays visible.</p>
    ${errs.length ? `<div class="warnbox"><b>Using an older file.</b> ${errs.map((s) => `${esc(s.sheet || s.source)}: ${esc(s.sync_error)}`).join("; ")}</div>` : ""}
    <div class="scroll"><table class="tbl"><thead><tr><th>Started</th><th>Trigger</th><th>Result</th><th>Files</th><th>Seconds</th></tr></thead><tbody>${rows || '<tr><td colspan="5" class="muted">No update has run yet.</td></tr>'}</tbody></table></div>`;
}

async function viewMedia() {
  const m = await api("/api/media");
  const byKind = {};
  m.items.forEach((i) => (byKind[i.kind] = (byKind[i.kind] || 0) + 1));
  $("#app").innerHTML = `<h1>Photos &amp; video</h1>
    <div class="counts"><div class="count"><span class="n num">${m.summary.references}</span><span class="l">photo references in the logs</span></div>
    <div class="count"><span class="n num">${m.summary.available}</span><span class="l">files available here</span></div></div>
    <section class="panel"><p style="margin:0">The logs point to photos (daily checklists, incident reports), but those files are not connected yet, so nothing is analysed or shown here. When photos or survey videos are added to <b>${esc(m.summary.media_dir)}</b>, they are matched to their records by file name and appear in the related alert.</p>
    <p class="muted small">By record type: ${Object.entries(byKind).map(([k, n]) => `${esc(KIND[k] || k)} ${n}`).join(" · ")}</p></section>`;
}

/* ============================== Drawers ============================== */
function bindEvidence() { $$("[data-ev]").forEach((el) => { el.onclick = (ev) => { ev.preventDefault(); ev.stopPropagation(); openEvidence(el.dataset.ev); }; }); }
function bindAssets() { $$("[data-asset]").forEach((el) => { el.onclick = (ev) => { ev.preventDefault(); openAsset(el.dataset.asset); }; }); }
function openDrawer(title, html) { $("#drawer .drawer-head h2").textContent = title; $("#drawer-body").innerHTML = html; $("#drawer").hidden = false; bindEvidence(); $("#drawer-close").focus(); }

async function openEvidence(id) {
  const e = await api(`/api/evidence/${encodeURIComponent(id)}`);
  const s = e.source || {};
  const vals = Object.entries(e.values || {}).filter(([k]) => !["derived_from", "instructions"].includes(k) && e.values[k] !== null && e.values[k] !== "")
    .map(([k, v]) => `<dt>${esc(k.replace(/_/g, " "))}</dt><dd>${esc(typeof v === "object" ? JSON.stringify(v) : v)}</dd>`).join("");
  openDrawer("Source record", `<p>${org(e.origin)}</p><h3>${esc(e.title)}</h3>
    <dl class="kv" style="margin-top:12px"><dt>Type</dt><dd>${esc(KIND[e.kind] || e.kind)}</dd><dt>Time</dt><dd>${dt(e.timestamp)}</dd>
    <dt>Equipment</dt><dd>${esc(e.asset_id || "—")} ${esc(e.asset_name || "")}</dd><dt>Zone</dt><dd>${esc(e.zone || "—")}</dd>
    <dt>Status in source</dt><dd>${esc(e.status || "—")}${e.is_open ? '<span class="open">● unresolved</span>' : ""}</dd>
    <dt>Original text</dt><dd>${esc(e.text || "—")}</dd>
    <dt>Hazard words</dt><dd>${(e.tags || []).filter((t) => t.tag !== "checklist_pass").map((t) => `<span class="org source">${esc(TAGNAME[t.tag] || t.tag)}: “${esc(t.term)}”</span>`).join(" ") || "—"}</dd>
    <dt>Data flags</dt><dd>${(e.flags || []).filter((f) => f !== "derived").map((f) => esc(f.replace(/_/g, " "))).join(", ") || "none"}</dd></dl>
    <h3 style="margin-top:18px">Where it comes from</h3>
    <dl class="kv"><dt>File</dt><dd>${esc(s.source_title)}</dd><dt>Tab</dt><dd>${esc(s.sheet)}</dd><dt>Row</dt><dd>${s.row ? esc(s.row) : "derived from the readings below"}</dd><dt>Record ID</dt><dd>${esc(s.record_id || "—")}</dd></dl>
    ${e.window ? `<h3 style="margin-top:18px">Daily values around this anomaly</h3>${trendChart({ points: e.window, median: e.values.median, start: e.timestamp.slice(0, 10), end: e.values.end, meter: e.asset_id, meter_name: e.asset_name, unit: e.values.unit, unit_verified: e.values.unit_verified, label: e.values.label, evidence_id: e.evidence_id })}` : ""}
    ${e.derived_records ? `<details><summary>${e.derived_records.length} meter readings used</summary><table class="tbl"><thead><tr><th>Time</th><th>Reading</th><th>Row</th></tr></thead><tbody>${e.derived_records.map((r) => `<tr><td class="small">${dt(r.timestamp)}</td><td class="num">${esc(r.values.reading)}</td><td class="num">${esc(r.source.row)}</td></tr>`).join("")}</tbody></table></details>` : ""}
    <h3 style="margin-top:18px">Values</h3><dl class="kv">${vals || "<dd>—</dd>"}</dl>
    ${e.media_refs?.length ? `<h3 style="margin-top:18px">Photos referenced (not connected yet)</h3>${e.media_refs.map((r) => `<div class="small muted">${esc(r)}</div>`).join("")}` : ""}
    <p class="small muted">Used in: ${(e.in_alerts || []).map(esc).join(", ") || "no alert"}</p>`);
}

async function openAsset(id) {
  const a = await api(`/api/assets/${encodeURIComponent(id)}`);
  openDrawer("Equipment", `<h3>${esc(a.name || id)}</h3><p class="muted small">${esc(id)}${a.meta?.zone ? ` · zone ${esc(a.meta.zone)}` : ""}</p>
    ${a.signals.length ? `<p>${a.signals.map((s) => `${lvl(s.severity)} ${esc(s.title)}`).join("<br>")}</p>` : '<p class="muted">No rule signal.</p>'}
    <h3 style="margin-top:14px">Record history (${a.records.length})</h3>
    <table class="tbl"><tbody>${a.records.map((e) => `<tr class="click" data-ev="${esc(e.evidence_id)}"><td class="small">${day(e.timestamp)}</td><td>${esc(e.title)}<div class="muted small">${esc(KIND[e.kind] || e.kind)} · ${esc(e.status || "")}</div></td></tr>`).join("") || '<tr><td class="muted">No records.</td></tr>'}</tbody></table>`);
}
$("#drawer-close").addEventListener("click", () => ($("#drawer").hidden = true));
document.addEventListener("keydown", (e) => { if (e.key === "Escape") $("#drawer").hidden = true; });

/* ============================== Router ============================== */
async function route() {
  const h = location.hash || "#/";
  $$("nav a").forEach((a) => a.classList.toggle("active", h === a.getAttribute("href") || (h.startsWith("#/alert/") && a.dataset.nav === "alerts")));
  try {
    if (!S) await loadStatus();
    if (h.startsWith("#/alert/")) return await viewAlert(decodeURIComponent(h.slice(8)));
    if (h === "#/alerts") return await viewAlerts();
    if (h === "#/equipment") return await viewEquipment();
    if (h === "#/events") return await viewEvents();
    if (h === "#/quality") return await viewQuality();
    if (h === "#/media") return await viewMedia();
    return await viewOverview();
  } catch (e) {
    $("#app").innerHTML = `<div class="errbox">The dashboard could not load data from the backend: ${esc(e.message)}. Check that run_dashboard is still running.</div>`;
  }
}
$("#refresh").addEventListener("click", async () => {
  const b = $("#refresh"); const drive = !!(S && S.sync && S.sync.configured);
  b.disabled = true; b.textContent = drive ? "Updating from Drive…" : "Analysing…";
  try {
    if (drive) {
      const r = await api("/api/sync", { method: "POST" });
      if (!r.ok) alertBar(r.busy ? r.error : `Drive update: ${r.error || "some files failed — the previous files were kept"}`);
    } else await api("/api/refresh", { method: "POST" });
    S = null; await route();
  } catch (e) { alertBar(`Update failed: ${e.message}`); }
  finally { b.disabled = false; if (S) loadStatus(); }
});
function alertBar(msg) {
  let el = $("#notice"); if (!el) { el = document.createElement("div"); el.id = "notice"; el.className = "notice"; el.setAttribute("role", "status"); document.body.appendChild(el); }
  el.innerHTML = `${esc(msg)} <button class="btn quiet" onclick="this.parentNode.remove()">Close</button>`;
}
// A background Drive update may produce a new analysis while the page is open: offer to reload, never re-render under the user.
setInterval(async () => {
  if (!S || document.hidden) return;
  try {
    const n = await api("/api/status");
    if (n.run_id !== S.run_id && !$("#notice")) {
      alertBar(`New analysis available (${dt(n.generated_at)}).`);
      const go = document.createElement("button"); go.className = "btn primary"; go.textContent = "Show";
      go.onclick = () => { $("#notice").remove(); S = null; route(); }; $("#notice").prepend(go);
    }
  } catch (e) { /* backend stopped; the next navigation shows the error */ }
}, 60000);
window.addEventListener("hashchange", () => { $("#drawer").hidden = true; window.scrollTo(0, 0); route(); });
route();
