"use strict";

const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const md = (s) => esc(s).replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>").replace(/\*(.+?)\*/g, "<em>$1</em>");
const pct = (x) => Math.round(x * 100) + "%";
const sgn = (x) => (x >= 0 ? "+" : "−") + Math.abs(x).toFixed(2);
const sentLabel = (x) => x <= -0.5 ? "sangat negatif" : x <= -0.15 ? "negatif" : x < 0.15 ? "netral" : x < 0.5 ? "positif" : "sangat positif";

let PRESETS = [];
let preset = null;
let events = [];
let R = null;          // hasil simulasi yang sedang dilihat
let round = 0;
let timer = null;
let layout = null;     // posisi node jaringan
let hoverNode = -1;
let selected = -1;
let postIndex = {};
const history = [];

// ---------------------------------------------------------------- warna
let C = {};
function readColors() {
  const cs = getComputedStyle(document.documentElement);
  const v = (n) => cs.getPropertyValue(n).trim();
  const rgb = (h) => { h = h.replace("#", ""); return [0, 2, 4].map((i) => parseInt(h.substr(i, 2), 16)); };
  C = { neg: rgb(v("--neg")), pos: rgb(v("--pos")), mid: rgb(v("--mid")), grid: v("--grid"), muted: v("--muted"), ink: v("--ink"), surface: v("--surface") };
}
function opColor(o) {
  const t = Math.min(1, Math.abs(o) / 0.8);
  const to = o < 0 ? C.neg : C.pos;
  const c = C.mid.map((m, i) => Math.round(m + (to[i] - m) * t));
  return `rgb(${c[0]},${c[1]},${c[2]})`;
}

// ---------------------------------------------------------------- tooltip
const tip = $("#tooltip");
function showTip(html, x, y) {
  tip.innerHTML = html;
  tip.hidden = false;
  const w = tip.offsetWidth, h = tip.offsetHeight;
  let left = x + 14, top = y + 14;
  if (left + w > innerWidth - 8) left = x - w - 14;
  if (top + h > innerHeight - 8) top = y - h - 14;
  tip.style.left = Math.max(8, left) + "px";
  tip.style.top = Math.max(8, top) + "px";
}
const hideTip = () => { tip.hidden = true; };

// ---------------------------------------------------------------- form
async function init() {
  readColors();
  PRESETS = await (await fetch("/api/presets")).json();
  $("#preset").innerHTML = PRESETS.map((p) => `<option value="${p.key}">${esc(p.label)}</option>`).join("");
  $("#preset").onchange = () => selectPreset($("#preset").value);
  selectPreset(PRESETS[0].key);
  $("#addEvent").onclick = addEvent;
  $("#run").onclick = run;
  $$(".tabs button").forEach((b) => (b.onclick = () => showTab(b.dataset.tab)));
  $("#round").oninput = (e) => { stop(); setRound(+e.target.value); };
  $("#play").onclick = () => (timer ? stop() : play());
  $("#feedMode").onchange = renderFeed;
  $("#closeDrawer").onclick = closeAgent;
  $("#drawer").onclick = (e) => { if (e.target.id === "drawer") closeAgent(); };
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeAgent(); });
  document.addEventListener("click", (e) => {
    const a = e.target.closest("[data-agent]");
    if (a) openAgent(+a.dataset.agent);
  });
  matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => { readColors(); drawNet(); });
  new ResizeObserver(() => drawNet()).observe($("#net"));
  initNet();
}

function selectPreset(key) {
  preset = PRESETS.find((p) => p.key === key);
  $("#subjectLabel").textContent = preset.subject_label;
  $("#subject").value = preset.subject_default;
  $("#competitorField").hidden = !preset.competitor;
  $("#competitor").value = preset.competitor_default || "";
  $("#params").innerHTML = preset.params.map((p) => `
    <label class="field"><span>${esc(p.label)}</span>
      <div class="row"><input type="range" data-key="${p.key}" min="${p.min}" max="${p.max}" value="${p.default}"><output>${p.default}</output></div>
    </label>`).join("");
  $$("#params input").forEach((inp) => (inp.oninput = () => (inp.nextElementSibling.textContent = inp.value)));
  events = [];
  renderEvents();
}

function eventFromPreset(i, roundNo) {
  const e = preset.events[i];
  return { round: roundNo, kind: String(i), name: e.name, effect: e.effect, target: e.target, aw: e.aw };
}

function addEvent() {
  if (events.length >= 8) return;
  const rounds = +$("#rounds").value || 30;
  events.push(eventFromPreset(0, Math.max(1, Math.round(rounds / 3) + events.length * 3)));
  renderEvents();
}

function renderEvents() {
  const segOpts = [`<option value="all">Semua orang</option>`].concat(preset.segments.map((s) => `<option value="${s.key}">${esc(s.label)}</option>`));
  $("#events").innerHTML = events.map((e, i) => `
    <div class="event" data-i="${i}">
      <label>Ronde<input type="number" min="1" data-f="round" value="${e.round}"></label>
      <label>Event<select data-f="kind">
        ${preset.events.map((p, k) => `<option value="${k}" ${e.kind === String(k) ? "selected" : ""}>${esc(p.name)}</option>`).join("")}
        <option value="custom" ${e.kind === "custom" ? "selected" : ""}>Kustom…</option>
      </select></label>
      <button type="button" class="rm" data-rm="${i}" aria-label="Hapus event">✕</button>
      ${e.kind === "custom" ? `<label class="full">Nama event<input type="text" data-f="name" value="${esc(e.name)}" maxlength="80"></label>` : ""}
      <label class="full">Sasaran<select data-f="target">${segOpts.map((o) => o.replace(`value="${e.target}"`, `value="${e.target}" selected`)).join("")}</select></label>
      <label class="full">Pengaruh ke opini: <output>${e.effect >= 0 ? "+" : ""}${Math.round(e.effect * 100)}</output>
        <input type="range" min="-100" max="100" data-f="effect" value="${Math.round(e.effect * 100)}"></label>
      <label class="full">Menambah orang yang tahu: <output>${Math.round(e.aw * 100)}%</output>
        <input type="range" min="0" max="100" data-f="aw" value="${Math.round(e.aw * 100)}"></label>
    </div>`).join("");
  $$("#events .event").forEach((row) => {
    const e = events[+row.dataset.i];
    $$("[data-f]", row).forEach((inp) => {
      inp.oninput = () => {
        const f = inp.dataset.f;
        if (f === "round") e.round = +inp.value;
        else if (f === "name") e.name = inp.value;
        else if (f === "target") e.target = inp.value;
        else if (f === "effect") { e.effect = inp.value / 100; inp.previousElementSibling.textContent = (inp.value >= 0 ? "+" : "") + inp.value; }
        else if (f === "aw") { e.aw = inp.value / 100; inp.previousElementSibling.textContent = inp.value + "%"; }
        else if (f === "kind") {
          if (inp.value === "custom") Object.assign(e, { kind: "custom", name: "Event kustom" });
          else Object.assign(e, eventFromPreset(+inp.value, e.round));
          renderEvents();
        }
      };
    });
  });
  $$("#events [data-rm]").forEach((b) => (b.onclick = () => { events.splice(+b.dataset.rm, 1); renderEvents(); }));
  $("#addEvent").disabled = events.length >= 8;
}

async function run() {
  const params = {};
  $$("#params input").forEach((i) => (params[i.dataset.key] = +i.value));
  const body = {
    preset: preset.key, subject: $("#subject").value, competitor: $("#competitor").value, params,
    population: +$("#population").value, rounds: +$("#rounds").value, runs: +$("#runs").value, seed: +$("#seed").value,
    events: events.map(({ round, name, effect, target, aw }) => ({ round, name, effect, target, aw })),
  };
  const btn = $("#run");
  btn.disabled = true;
  $("#status").textContent = "Menjalankan simulasi…";
  const t0 = performance.now();
  try {
    const res = await fetch("/api/simulate", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    if (!res.ok) throw new Error("Server error " + res.status);
    const data = await res.json();
    $("#status").textContent = `Selesai dalam ${((performance.now() - t0) / 1000).toFixed(1)} detik.`;
    history.unshift({ when: new Date(), data });
    showResult(data);
  } catch (err) {
    $("#status").textContent = "Gagal: " + err.message;
  } finally {
    btn.disabled = false;
  }
}

// ---------------------------------------------------------------- hasil
function showResult(data) {
  stop();
  R = data;
  selected = -1;
  postIndex = {};
  for (const p of R.detail.posts) if (p.a >= 0) (postIndex[p.a + ":" + p.t] ||= []).push(p);
  $("#empty").hidden = true;
  $("#results").hidden = false;
  renderKpis();
  renderReport();
  renderHistory();
  const rounds = R.config.rounds;
  $("#round").max = rounds;
  $("#actHint").textContent = `${R.preset.neg_label} vs ${R.preset.pos_label}, median dan rentang 10–90%.`;
  buildCharts();
  startLayout();
  setRound(rounds);
}

function kpi(label, val, rng) {
  return `<div class="card kpi"><div class="lab">${esc(label)}</div><div class="val">${val}</div><div class="rng">${rng}</div></div>`;
}

function renderKpis() {
  const a = R.agg, last = (k, q = "p50") => a[k][q][a[k][q].length - 1];
  const polar = last("polar");
  $("#kpis").innerHTML = [
    kpi("Sentimen akhir", sgn(last("mean_op")), `${sentLabel(last("mean_op"))} · awal ${sgn(a.mean_op.p50[0])}`),
    kpi(R.preset.neg_label, pct(last("neg_action")), `rentang ${pct(last("neg_action", "p10"))}–${pct(last("neg_action", "p90"))}`),
    kpi(R.preset.pos_label, pct(last("pos_action")), `rentang ${pct(last("pos_action", "p10"))}–${pct(last("pos_action", "p90"))}`),
    kpi("Tahu isu ini", pct(last("aware")), `dari ${R.config.population} agen`),
    kpi("Polarisasi", polar.toFixed(2), polar > 0.5 ? "tinggi, terbelah" : polar > 0.3 ? "sedang" : "rendah"),
  ].join("");
}

function divbar(o) {
  const w = Math.min(1, Math.abs(o)) * 50;
  const style = o < 0 ? `right:50%;width:${w}%;background:var(--neg)` : `left:50%;width:${w}%;background:var(--pos)`;
  return `<div class="divbar" role="img" aria-label="opini ${sgn(o)}"><i style="${style}"></i></div>`;
}

function renderReport() {
  const r = R.report;
  const list = (items) => `<ul>${items.map((x) => `<li>${md(x)}</li>`).join("")}</ul>`;
  const agentBtn = (id, h) => `<button class="link" data-agent="${id}">@${esc(h)}</button>`;
  $("#tab-report").innerHTML = `
    <div class="report card"><p class="headline">${md(r.headline)}</p>${list(r.summary)}</div>
    <div class="report cols">
      <div class="card"><h2>Alur cerita</h2>${list(r.phases)}</div>
      <div class="card"><h2>Titik balik</h2>${r.turning_points.length ? r.turning_points.map((t) => `<div class="tp"><span class="r">Ronde ${t.round}</span><span>${md(t.text)}</span></div>`).join("") : `<p class="note">Tidak ada perubahan tajam; opini bergerak perlahan.</p>`}</div>
    </div>
    ${r.event_effects.length ? `<div class="report card"><h2>Dampak tiap event</h2><p class="note">Dibandingkan dengan simulasi yang sama tanpa event tersebut.</p>${list(r.event_effects.map((e) => e.text))}</div>` : ""}
    <div class="report card"><h2>Per segmen (akhir simulasi)</h2>
      <div class="table-wrap"><table>
        <thead><tr><th>Segmen</th><th class="num">Jumlah</th><th>Opini</th><th class="num"></th><th class="num">${esc(R.preset.neg_label)}</th><th class="num">${esc(R.preset.pos_label)}</th><th>Status</th></tr></thead>
        <tbody>${r.segments.map((s) => `<tr><td>${esc(s.label)}</td><td class="num">${s.size}</td><td>${divbar(s.op)}</td><td class="num">${sgn(s.op)}</td><td class="num">${pct(s.neg)}</td><td class="num">${pct(s.pos)}</td><td>${esc(s.verdict)}</td></tr>`).join("")}</tbody>
      </table></div>
    </div>
    <div class="report cols">
      <div class="card"><h2>Sinyal risiko</h2>${r.risks.length ? r.risks.map((x) => `<div class="risk"><span class="badge ${x.level}">${x.level === "tinggi" ? "▲ Tinggi" : "● Sedang"}</span><span>${md(x.text)}</span></div>`).join("") : `<p class="note">Tidak ada risiko besar terdeteksi.</p>`}</div>
      <div class="card"><h2>Akun paling berpengaruh</h2>
        <table><thead><tr><th>Akun</th><th>Segmen</th><th class="num">Opini akhir</th></tr></thead>
        <tbody>${r.key_agents.map((k) => `<tr><td>${agentBtn(k.id, k.handle)}</td><td>${esc(k.seg)}</td><td class="num">${sgn(k.final_op)}</td></tr>`).join("")}</tbody></table>
        <p class="note">Klik akun untuk melihat ceritanya.</p>
      </div>
    </div>
    <div class="report cols">
      <div class="card"><h2>Rekomendasi</h2>${list(r.recommendations)}</div>
      <div class="card"><h2>Coba eksperimen berikutnya</h2>${list(r.experiments)}</div>
    </div>
    <p class="note">${esc(r.method)}</p>`;
}

function renderHistory() {
  const el = $("#tab-history");
  if (!history.length) { el.innerHTML = ""; return; }
  const last = (a, k) => a[k].p50[a[k].p50.length - 1];
  el.innerHTML = `<div class="card"><h3>Riwayat simulasi (sesi ini)</h3><p class="hint">Bandingkan skenario. Riwayat hilang saat halaman di-refresh.</p>
    <div class="table-wrap"><table><thead><tr><th>Waktu</th><th>Skenario</th><th>Parameter</th><th>Event</th><th class="num">Sentimen</th><th class="num">Aksi negatif</th><th class="num">Aksi positif</th><th></th></tr></thead>
    <tbody>${history.map((h, i) => {
      const d = h.data, a = d.agg;
      return `<tr${d === R ? ' style="font-weight:600"' : ""}><td>${h.when.toLocaleTimeString("id-ID")}</td><td>${esc(d.preset.label)}<br><span class="note">${esc(d.config.subject)}</span></td>
        <td class="note">${Object.entries(d.config.params).map(([k, v]) => `${esc(k)}=${v}`).join(", ")}</td>
        <td class="note">${d.events.map((e) => `R${e.round} ${esc(e.name)}`).join("<br>") || "–"}</td>
        <td class="num">${sgn(last(a, "mean_op"))}</td><td class="num">${pct(last(a, "neg_action"))}</td><td class="num">${pct(last(a, "pos_action"))}</td>
        <td><button class="link" data-hist="${i}">Buka</button></td></tr>`;
    }).join("")}</tbody></table></div></div>`;
  $$("[data-hist]", el).forEach((b) => (b.onclick = () => { showResult(history[+b.dataset.hist].data); showTab("report"); }));
}

function showTab(name) {
  $$(".tabs button").forEach((b) => b.setAttribute("aria-selected", b.dataset.tab === name));
  $$(".tab").forEach((t) => (t.hidden = t.id !== "tab-" + name));
  if (name === "sim") drawNet();
}

// ---------------------------------------------------------------- pemutar
function setRound(t) {
  round = t;
  $("#round").value = t;
  $("#roundLabel").textContent = `Ronde ${t} / ${R.config.rounds}`;
  drawNet();
  renderFeed();
  renderSegBars();
  charts.forEach((c) => c.setCursor(t));
}
function play() {
  if (round >= R.config.rounds) setRound(0);
  $("#play").textContent = "❚❚ Jeda";
  timer = setInterval(() => {
    if (round >= R.config.rounds) return stop();
    setRound(round + 1);
  }, 450);
}
function stop() {
  clearInterval(timer);
  timer = null;
  $("#play").textContent = "▶ Putar";
}

// ---------------------------------------------------------------- feed
function renderFeed() {
  if (!R) return;
  const ag = R.detail.agents, segs = R.preset.segments;
  let posts;
  if ($("#feedMode").value === "all") posts = R.detail.posts.filter((p) => p.a >= 0).sort((a, b) => b.reach - a.reach).slice(0, 50);
  else posts = R.detail.posts.filter((p) => p.t === round).sort((a, b) => (b.news ? 1e9 : b.reach) - (a.news ? 1e9 : a.reach)).slice(0, 80);
  if (!posts.length) {
    $("#feed").innerHTML = `<p class="hint">${round === 0 ? "Ronde 0 adalah kondisi awal. Tekan Putar untuk melihat obrolan berjalan." : "Tidak ada postingan di ronde ini."}</p>`;
    return;
  }
  $("#feed").innerHTML = posts.map((p) => {
    if (p.news) return `<div class="post news"><div class="avatar" style="background:var(--ink-2)">📰</div><div><div class="who"><b>Event</b> · ronde ${p.t}</div><div class="txt">${esc(p.text)}</div><div class="meta">memengaruhi ${p.reach} orang yang sudah tahu</div></div></div>`;
    const a = ag[p.a];
    return `<div class="post"><div class="avatar" style="background:${opColor(p.s)}">${esc(a.name[0])}</div><div>
      <div class="who"><button class="link" data-agent="${a.id}"><b>${esc(a.name)}</b></button> @${esc(a.handle)} · ${esc(segs[a.seg].label)} · R${p.t}</div>
      <div class="txt">${esc(p.text)}</div>
      <div class="meta">🔁 ${p.rs} dibagikan · 👁 ${p.reach} jangkauan · opini ${sgn(p.s)}</div></div></div>`;
  }).join("");
}

function renderSegBars() {
  const sm = R.shown_metrics.seg_mean[round];
  $("#segRound").textContent = `· ronde ${round}`;
  $("#segbars").innerHTML = R.preset.segments.map((s, i) => `<div class="segrow"><span>${esc(s.label)}</span>${sm[i] == null ? `<span class="hint">belum ada yang tahu</span><span></span>` : `${divbar(sm[i])}<span class="mono" style="text-align:right">${sgn(sm[i])}</span>`}</div>`).join("");
}

// ---------------------------------------------------------------- grafik
let charts = [];
function buildCharts() {
  const a = R.agg;
  const evs = R.events;
  charts = [
    lineChart($("#chartSent"), { series: [{ name: "Sentimen", color: "var(--pos)", band: a.mean_op }], yMin: -1, yMax: 1, ticks: [-1, -0.5, 0, 0.5, 1], fmt: sgn, events: evs }),
    lineChart($("#chartAct"), {
      series: [
        { name: R.preset.neg_label, color: "var(--neg)", band: a.neg_action },
        { name: R.preset.pos_label, color: "var(--pos)", band: a.pos_action },
      ],
      yMin: 0, yMax: niceMax(Math.max(...a.neg_action.p90, ...a.pos_action.p90)), fmt: pct, events: evs,
    }),
  ];
}
function niceMax(v) {
  for (const m of [0.05, 0.1, 0.2, 0.3, 0.5, 0.75, 1]) if (v <= m) return m;
  return 1;
}

function lineChart(el, o) {
  const W = 560, H = 230, ml = 44, mr = 16, mt = 12, mb = 26;
  const n = o.series[0].band.p50.length;
  const X = (t) => ml + (t / (n - 1)) * (W - ml - mr);
  const Y = (v) => mt + (1 - (v - o.yMin) / (o.yMax - o.yMin)) * (H - mt - mb);
  const ticks = o.ticks || [0, 0.25, 0.5, 0.75, 1].map((f) => o.yMin + f * (o.yMax - o.yMin));
  const path = (arr) => arr.map((v, t) => `${t ? "L" : "M"}${X(t).toFixed(1)},${Y(v).toFixed(1)}`).join("");
  const xt = [];
  const step = n > 40 ? 10 : 5;
  for (let t = 0; t < n; t += step) xt.push(t);
  let svg = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(o.series.map((s) => s.name).join(", "))}">`;
  svg += ticks.map((v) => `<line x1="${ml}" x2="${W - mr}" y1="${Y(v)}" y2="${Y(v)}" style="stroke:${v === 0 && o.yMin < 0 ? "var(--axis)" : "var(--grid)"}" stroke-width="1"/><text x="${ml - 6}" y="${Y(v) + 4}" text-anchor="end">${o.fmt(v)}</text>`).join("");
  svg += xt.map((t) => `<text x="${X(t)}" y="${H - 8}" text-anchor="middle">${t}</text>`).join("");
  svg += `<line x1="${ml}" x2="${W - mr}" y1="${H - mb}" y2="${H - mb}" style="stroke:var(--axis)"/>`;
  svg += o.events.map((e) => `<line x1="${X(e.round)}" x2="${X(e.round)}" y1="${mt}" y2="${H - mb}" style="stroke:var(--muted)" stroke-dasharray="3 3"/><path d="M${X(e.round) - 4},${mt - 2}L${X(e.round) + 4},${mt - 2}L${X(e.round)},${mt + 4}Z" style="fill:var(--muted)"/>`).join("");
  for (const s of o.series) {
    const b = s.band;
    const area = path(b.p90) + b.p10.map((v, t) => `L${X(t).toFixed(1)},${Y(v).toFixed(1)}`).reverse().join("") + "Z";
    svg += `<path d="${area}" style="fill:${s.color};opacity:.14"/>`;
    svg += `<path d="${path(b.p50)}" style="fill:none;stroke:${s.color};stroke-width:2;stroke-linejoin:round"/>`;
  }
  svg += `<line class="cur" y1="${mt}" y2="${H - mb}" style="stroke:var(--ink-2)" stroke-width="1" opacity=".5"/>`;
  svg += `<line class="hov" y1="${mt}" y2="${H - mb}" style="stroke:var(--ink)" stroke-width="1" visibility="hidden"/>`;
  svg += o.series.map((s, i) => `<circle class="hd hd${i}" r="4" style="fill:${s.color};stroke:var(--surface);stroke-width:2" visibility="hidden"/>`).join("");
  svg += `<rect x="${ml}" y="0" width="${W - ml - mr}" height="${H}" fill="transparent" style="cursor:crosshair"/></svg>`;
  const legend = o.series.length > 1 ? `<div class="legend" style="margin-bottom:6px">${o.series.map((s) => `<span><i class="dot" style="background:${s.color}"></i>${esc(s.name)}</span>`).join("")}</div>` : "";
  el.innerHTML = legend + svg;
  const root = $("svg", el);
  const hov = $(".hov", root), cur = $(".cur", root);
  const tAt = (ev) => {
    const r = root.getBoundingClientRect();
    const x = ((ev.clientX - r.left) / r.width) * W;
    return Math.max(0, Math.min(n - 1, Math.round(((x - ml) / (W - ml - mr)) * (n - 1))));
  };
  root.addEventListener("mousemove", (ev) => {
    const t = tAt(ev);
    hov.setAttribute("x1", X(t)); hov.setAttribute("x2", X(t)); hov.setAttribute("visibility", "visible");
    o.series.forEach((s, i) => { const c = $(".hd" + i, root); c.setAttribute("cx", X(t)); c.setAttribute("cy", Y(s.band.p50[t])); c.setAttribute("visibility", "visible"); });
    const evs = o.events.filter((e) => e.round === t);
    showTip(`<div class="t">Ronde ${t}</div>${o.series.map((s) => `<div class="r"><span><i class="sw" style="background:${s.color}"></i>${esc(s.name)}</span><b>${o.fmt(s.band.p50[t])}</b></div><div class="r note"><span></span><span>${o.fmt(s.band.p10[t])} s/d ${o.fmt(s.band.p90[t])}</span></div>`).join("")}${evs.map((e) => `<div class="note">Event: ${esc(e.name)}</div>`).join("")}<div class="note">Klik untuk lompat ke ronde ini</div>`, ev.clientX, ev.clientY);
  });
  root.addEventListener("mouseleave", () => { hov.setAttribute("visibility", "hidden"); $$(".hd", root).forEach((c) => c.setAttribute("visibility", "hidden")); hideTip(); });
  root.addEventListener("click", (ev) => { stop(); setRound(tAt(ev)); });
  return { setCursor: (t) => { cur.setAttribute("x1", X(t)); cur.setAttribute("x2", X(t)); } };
}

// ---------------------------------------------------------------- jaringan
let layoutJob = 0;
function startLayout() {
  const n = R.detail.agents.length, edges = R.detail.edges;
  const x = new Float64Array(n), y = new Float64Array(n);
  for (let i = 0; i < n; i++) { const a = Math.random() * 6.283, r = Math.sqrt(Math.random()) * 0.5; x[i] = 0.5 + r * Math.cos(a); y[i] = 0.5 + r * Math.sin(a); }
  layout = { x, y };
  const job = ++layoutJob;
  const k = Math.sqrt(1 / n), k2 = k * k;
  const total = n > 600 ? 120 : 220;
  const perFrame = Math.max(1, Math.round(1.5e6 / (n * n)));
  let it = 0;
  const dx = new Float64Array(n), dy = new Float64Array(n);
  const step = () => {
    if (job !== layoutJob) return;
    for (let s = 0; s < perFrame && it < total; s++, it++) {
      const temp = 0.08 * (1 - it / total) + 0.002;
      dx.fill(0); dy.fill(0);
      for (let i = 0; i < n; i++) {
        for (let j = i + 1; j < n; j++) {
          const ddx = x[i] - x[j], ddy = y[i] - y[j];
          const d2 = ddx * ddx + ddy * ddy + 1e-6;
          const f = k2 / d2;
          dx[i] += ddx * f; dy[i] += ddy * f; dx[j] -= ddx * f; dy[j] -= ddy * f;
        }
      }
      for (const [a, b] of edges) {
        const ddx = x[a] - x[b], ddy = y[a] - y[b];
        const d = Math.sqrt(ddx * ddx + ddy * ddy) + 1e-6;
        const f = d / k;
        dx[a] -= ddx * f; dy[a] -= ddy * f; dx[b] += ddx * f; dy[b] += ddy * f;
      }
      for (let i = 0; i < n; i++) {
        dx[i] += (0.5 - x[i]) * 0.6; dy[i] += (0.5 - y[i]) * 0.6;
        const d = Math.sqrt(dx[i] * dx[i] + dy[i] * dy[i]) + 1e-9;
        const m = Math.min(d, temp);
        x[i] += (dx[i] / d) * m; y[i] += (dy[i] / d) * m;
      }
    }
    drawNet();
    if (it < total) requestAnimationFrame(step);
  };
  requestAnimationFrame(step);
}

let netGeom = null;
function initNet() {
  const cv = $("#net");
  cv.addEventListener("mousemove", (e) => {
    const i = nodeAt(e);
    if (i !== hoverNode) { hoverNode = i; drawNet(); }
    if (i < 0) return hideTip();
    const a = R.detail.agents[i], o = R.detail.ops[round][i], st = R.detail.states[round][i];
    const status = st === "u" ? "belum tahu" : st === "n" ? R.preset.neg_label : st === "p" ? R.preset.pos_label : "belum beraksi";
    showTip(`<div class="t">${esc(a.name)}</div><div class="note">@${esc(a.handle)} · ${esc(R.preset.segments[a.seg].label)}</div>
      <div class="r"><span>Opini</span><b>${st === "u" ? "–" : sgn(o)}</b></div><div class="r"><span>Status</span><span>${esc(status)}</span></div><div class="r"><span>Koneksi</span><span>${a.deg}</span></div>`, e.clientX, e.clientY);
  });
  cv.addEventListener("mouseleave", () => { hoverNode = -1; hideTip(); drawNet(); });
  cv.addEventListener("click", (e) => { const i = nodeAt(e); if (i >= 0) openAgent(i); });
}
function nodeAt(e) {
  if (!netGeom || !R) return -1;
  const r = $("#net").getBoundingClientRect();
  const mx = e.clientX - r.left, my = e.clientY - r.top;
  let best = -1, bd = 1e9;
  const { px, py, rad } = netGeom;
  for (let i = 0; i < px.length; i++) {
    const d = (px[i] - mx) ** 2 + (py[i] - my) ** 2;
    if (d < bd && d < (rad[i] + 4) ** 2) { bd = d; best = i; }
  }
  return best;
}
function drawNet() {
  const cv = $("#net");
  if (!R || !layout || !cv.clientWidth) return;
  const dpr = devicePixelRatio || 1, W = cv.clientWidth, H = cv.clientHeight;
  if (cv.width !== Math.round(W * dpr)) { cv.width = Math.round(W * dpr); cv.height = Math.round(H * dpr); }
  const ctx = cv.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, W, H);
  const { x, y } = layout, n = x.length;
  let x0 = Infinity, x1 = -Infinity, y0 = Infinity, y1 = -Infinity;
  for (let i = 0; i < n; i++) { x0 = Math.min(x0, x[i]); x1 = Math.max(x1, x[i]); y0 = Math.min(y0, y[i]); y1 = Math.max(y1, y[i]); }
  const pad = 16, s = Math.min((W - 2 * pad) / (x1 - x0 || 1), (H - 2 * pad) / (y1 - y0 || 1));
  const ox = (W - (x1 - x0) * s) / 2, oy = (H - (y1 - y0) * s) / 2;
  const px = new Float64Array(n), py = new Float64Array(n), rad = new Float64Array(n);
  const ag = R.detail.agents, ops = R.detail.ops[round], st = R.detail.states[round];
  const scale = Math.min(1.2, Math.max(0.6, Math.sqrt(W * H / n) / 25));
  for (let i = 0; i < n; i++) { px[i] = ox + (x[i] - x0) * s; py[i] = oy + (y[i] - y0) * s; rad[i] = (2 + Math.sqrt(ag[i].deg) * 0.9) * scale; }
  netGeom = { px, py, rad };
  ctx.lineWidth = 0.6;
  ctx.strokeStyle = C.grid;
  ctx.beginPath();
  for (const [a, b] of R.detail.edges) { ctx.moveTo(px[a], py[a]); ctx.lineTo(px[b], py[b]); }
  ctx.stroke();
  const focus = hoverNode >= 0 ? hoverNode : selected;
  if (focus >= 0) {
    ctx.strokeStyle = C.muted; ctx.lineWidth = 1; ctx.beginPath();
    for (const [a, b] of R.detail.edges) if (a === focus || b === focus) { ctx.moveTo(px[a], py[a]); ctx.lineTo(px[b], py[b]); }
    ctx.stroke();
  }
  for (let i = 0; i < n; i++) {
    ctx.beginPath();
    ctx.arc(px[i], py[i], rad[i], 0, 6.2832);
    if (st[i] === "u") { ctx.strokeStyle = C.muted; ctx.lineWidth = 1; ctx.stroke(); continue; }
    ctx.fillStyle = opColor(ops[i]); ctx.fill();
    ctx.strokeStyle = C.surface; ctx.lineWidth = 1; ctx.stroke();
    if (st[i] === "n" || st[i] === "p") {
      ctx.beginPath(); ctx.arc(px[i], py[i], rad[i] + 2, 0, 6.2832);
      ctx.strokeStyle = C.ink; ctx.lineWidth = 1.5; ctx.stroke();
    }
  }
  if (focus >= 0) {
    ctx.beginPath(); ctx.arc(px[focus], py[focus], rad[focus] + 4, 0, 6.2832);
    ctx.strokeStyle = C.ink; ctx.lineWidth = 2; ctx.stroke();
  }
}

// ---------------------------------------------------------------- cerita agen
function openAgent(id) {
  if (!R) return;
  selected = id;
  drawNet();
  const a = R.detail.agents[id], ag = R.detail.agents, P = R.preset;
  const seg = P.segments[a.seg].label;
  const traj = R.detail.ops.map((r) => r[id]);
  const states = R.detail.states.map((s) => s[id]);
  const last = states[states.length - 1];
  const finalStatus = last === "u" ? "tidak pernah tahu isu ini" : last === "n" ? P.neg_label : last === "p" ? P.pos_label : "tidak mengambil aksi";
  const h = (i) => `<button class="link" data-agent="${i}">@${esc(ag[i].handle)}</button>`;

  const items = [];
  items.push(["Awal", states[0] === "u"
    ? `Belum tahu isu ini. Kalau tahu, penilaian pribadinya ${sgn(a.latent0)} (${sentLabel(a.latent0)}).`
    : `Sudah tahu sejak awal. Penilaian pribadinya ${sgn(a.latent0)} (${sentLabel(a.latent0)}).`]);
  for (const e of a.log) {
    let txt = "";
    if (e.k === "aware") txt = e.via ? `Mulai tahu isu ini lewat event “${esc(e.via)}”.` : `Mulai tahu isu ini dari postingan ${h(e.by)}.`;
    else if (e.k === "event") txt = `Terkena event “${esc(e.name)}”: opini ${sgn(e.d)}.`;
    else if (e.k === "social") {
      if (e.backfire) txt = `Melihat ${e.n} postingan yang terlalu berbeda pendapat, malah makin yakin (${sgn(e.d)}).`;
      else txt = `Opini ${e.d > 0 ? "naik" : "turun"} ${Math.abs(e.d).toFixed(2)} setelah melihat ${e.n} postingan (${pct(e.neg)} negatif)${e.by != null ? `, paling terpengaruh ${h(e.by)}` : ""}.`;
    } else if (e.k === "action") txt = e.to === "neg" ? `<b>Memutuskan: ${esc(P.neg_label)}.</b>` : e.to === "pos" ? `<b>Memutuskan: ${esc(P.pos_label)}.</b>` : "Membatalkan keputusannya.";
    else if (e.k === "post") {
      const p = (postIndex[id + ":" + e.t] || []).find((q) => q.s === e.s);
      txt = `Memposting: “${esc(p ? p.text : "")}”${p && p.rs ? ` (dibagikan ${p.rs}×)` : ""}`;
    }
    items.push([`R${e.t}`, txt]);
  }

  $("#agentBody").innerHTML = `
    <h2 id="agentName">${esc(a.name)}</h2>
    <p class="hint">@${esc(a.handle)} · ${esc(seg)}</p>
    <p>Opini akhir <b>${last === "u" ? "–" : sgn(traj[traj.length - 1])}</b>, status: <b>${esc(finalStatus)}</b>.</p>
    <div class="chart" id="agentChart"></div>
    <div class="traits">
      <div><span>Koneksi</span><b>${a.deg}</b></div>
      <div><span>Keras kepala</span><b>${a.stub.toFixed(2)}</b></div>
      <div><span>Toleransi beda pendapat</span><b>${a.eps.toFixed(2)}</b></div>
      <div><span>Loyalitas</span><b>${a.loyal.toFixed(2)}</b></div>
      <div><span>Keaktifan posting</span><b>${pct(a.act)}</b></div>
      <div><span>Kepekaan isu</span><b>${a.sens.toFixed(2)}</b></div>
      <div><span>Pengaruh ke orang lain</span><b>${a.inf.toFixed(1)}</b></div>
    </div>
    <h3>Cerita agen</h3>
    <ul class="story">${items.map(([r, t]) => `<li><span class="r">${r}</span><span>${t}</span></li>`).join("")}</ul>`;
  const band = { p10: traj, p50: traj, p90: traj };
  const c = lineChart($("#agentChart"), { series: [{ name: "Opini agen", color: "var(--pos)", band }], yMin: -1, yMax: 1, ticks: [-1, 0, 1], fmt: sgn, events: R.events });
  c.setCursor(round);
  $("#drawer").hidden = false;
}
function closeAgent() {
  $("#drawer").hidden = true;
  selected = -1;
  hideTip();
  drawNet();
}

init();
