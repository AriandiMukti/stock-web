/* Halaman Sebaran Kabar (/sebaran-kabar). Mesinnya di website/sebaran/. */
(function () {
"use strict";

const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const md = (s) => esc(s).replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>").replace(/\*(.+?)\*/g, "<em>$1</em>");
const pct = (x) => Math.round(x * 100) + "%";
const pct1 = (x) => (x * 100).toFixed(1) + "%";
const sgn = (x) => (x >= 0 ? "+" : "−") + Math.abs(x).toFixed(2);
const sentLabel = (x) => x <= -0.5 ? "sangat negatif" : x <= -0.15 ? "negatif" : x < 0.15 ? "netral" : x < 0.5 ? "positif" : "sangat positif";
const rupiah = (x) => x >= 1e12 ? "Rp " + (x / 1e12).toLocaleString("id-ID", { maximumFractionDigits: 1 }) + " T" : "Rp " + Math.round(x / 1e9).toLocaleString("id-ID") + " M";
const csrf = () => ($('meta[name="csrf-token"]') || {}).content || "";

const KABAR = window.SK_KABAR || [];
let kabar = null;
let events = [];
let R = null;
let round = 0;
let timer = null;
let layout = null;
let hoverNode = -1;
let selected = -1;
let postIndex = {};
let charts = [];
const history = [];

// ---------------------------------------------------------------- warna (token situs)
let C = {};
function readColors() {
  const cs = getComputedStyle(document.documentElement);
  const v = (n) => cs.getPropertyValue(n).trim();
  const rgb = (h) => { h = h.replace("#", ""); return [0, 2, 4].map((i) => parseInt(h.substr(i, 2), 16)); };
  C = { neg: rgb(v("--distrib")), pos: rgb(v("--accum")), mid: rgb(v("--line")), grid: v("--line-soft"),
        dim: v("--text-dim"), ink: v("--text"), surface: v("--void") };
}
function opColor(o) {
  const t = Math.min(1, Math.abs(o) / 0.8);
  const to = o < 0 ? C.neg : C.pos;
  const c = C.mid.map((m, i) => Math.round(m + (to[i] - m) * t));
  return `rgb(${c[0]},${c[1]},${c[2]})`;
}

// ---------------------------------------------------------------- tooltip
const tip = $("#skTip");
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
function init() {
  readColors();
  $("#skKabar").innerHTML = KABAR.map((k) => `<option value="${k.key}">${esc(k.label)}</option>`).join("");
  $("#skKabar").onchange = () => selectKabar($("#skKabar").value);
  selectKabar(KABAR[0].key);
  $("#skAmbil").onclick = ambilKonteks;
  $("#skKode").addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); ambilKonteks(); } });
  $("#skAddEv").onclick = addEvent;
  $("#skRun").onclick = run;
  $$(".sk-tabs button").forEach((b) => (b.onclick = () => showTab(b.dataset.tab)));
  $("#skRound").oninput = (e) => { stop(); setRound(+e.target.value); };
  $("#skPlay").onclick = () => (timer ? stop() : play());
  $("#skFeedMode").onchange = renderFeed;
  $("#skClose").onclick = closeAgent;
  $("#skDrawer").onclick = (e) => { if (e.target.id === "skDrawer") closeAgent(); };
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeAgent(); });
  document.addEventListener("click", (e) => {
    const a = e.target.closest("[data-agent]");
    if (a && R) openAgent(+a.dataset.agent);
  });
  new ResizeObserver(() => drawNet()).observe($("#skNet"));
  initNet();
  if ($("#skKode").value) ambilKonteks();
}

function selectKabar(key) {
  const keep = {};
  $$("#skParams input").forEach((i) => (keep[i.dataset.key] = i.value));   // data emiten tetap saat ganti kabar
  kabar = KABAR.find((k) => k.key === key);
  $("#skParams").innerHTML = kabar.params.map((p) => {
    const v = keep[p.key] !== undefined ? keep[p.key] : p.default;
    return `<label class="sk-field"><span>${esc(p.label)}</span>
      <div class="sk-row"><input type="range" data-key="${p.key}" min="${p.min}" max="${p.max}" value="${v}"><output>${v}</output></div></label>`;
  }).join("");
  $$("#skParams input").forEach((inp) => (inp.oninput = () => (inp.nextElementSibling.textContent = inp.value)));
  events = [];
  renderEvents();
}

function setParam(key, val) {
  const inp = $(`#skParams input[data-key="${key}"]`);
  if (!inp) return;
  inp.value = val;
  inp.nextElementSibling.textContent = inp.value;
}

async function ambilKonteks() {
  const kode = $("#skKode").value.trim().toUpperCase();
  $("#skKode").value = kode;
  if (!kode) return;
  $("#skCtx").innerHTML = `<span class="sk-dim">Membaca data ${esc(kode)}…</span>`;
  try {
    const res = await fetch("/sebaran-kabar/konteks?kode=" + encodeURIComponent(kode));
    const k = await res.json();
    if (!k.dikenal) { $("#skCtx").innerHTML = `<b>${esc(kode)}</b> tidak ada di daftar emiten.`; return; }
    Object.entries(k.saran || {}).forEach(([key, v]) => setParam(key, v));
    const rows = [];
    if (k.buzz) rows.push(k.buzz.peringkat
      ? `Ramai Dibahas: <b>${Math.round(k.buzz.total)}</b> obrolan/hari, peringkat <b>${k.buzz.peringkat}</b> dari ${k.buzz.n} <span class="sk-src">${esc(k.buzz.tanggal)}</span>`
      : `Ramai Dibahas: tidak muncul <span class="sk-src">${esc(k.buzz.tanggal)}</span>`);
    else rows.push(`<span class="sk-dim">Ramai Dibahas belum pernah ditarik.</span>`);
    if (k.ksei) rows.push(`Ritel <b>${k.ksei.pct_retail.toFixed(1)}%</b> · asing <b>${k.ksei.pct_foreign.toFixed(1)}%</b> <span class="sk-src">KSEI ${esc(k.ksei.bulan)}</span>`);
    else rows.push(`<span class="sk-dim">Data KSEI tidak ada untuk ${esc(kode)}.</span>`);
    if (k.harga) rows.push(`Close <b>${k.harga.close.toLocaleString("id-ID")}</b> · 5 hari <b>${k.harga.r5 >= 0 ? "+" : ""}${k.harga.r5.toFixed(1)}%</b> · nilai <b>${k.harga.nilai_m.toFixed(1)} M</b>/hari <span class="sk-src">${esc(k.harga.tgl)}</span>`);
    const p = k.profil || {};
    const prof = [];
    if (p.mcap) prof.push(`kapitalisasi <b>${rupiah(p.mcap)}</b>`);
    if (k.ksei) prof.push(`korporasi <b>${k.ksei.pct_korporasi.toFixed(0)}%</b>`);
    if (p.vol != null) prof.push(`ayunan harian <b>${p.vol.toFixed(1)}%</b>`);
    if (p.rawan != null) prof.push(`rawan goreng <b>${p.rawan.toFixed(2)}</b>`);
    if (prof.length) rows.push(prof.join(" · "));
    rows.push(`<span class="sk-dim">Slider 'sudah tahu', 'porsi ritel', dan 'naik 5 hari' sudah diisi dari data ini. Boleh diubah.</span>`);
    let html = rows.join("<br>");
    if (k.komunitas && k.komunitas.length) {
      html += `<details><summary>Komunitas yang terbentuk &amp; asumsinya</summary>
        <div style="margin-top:6px">${k.komunitas.map((s) => `${esc(s.label)} <b>${pct(s.share)}</b>`).join(" · ")}</div>
        <ul>${(k.asumsi || []).map((a) => `<li>Asumsi: ${esc(a)}</li>`).join("")}</ul></details>`;
    }
    $("#skCtx").innerHTML = html;
  } catch (err) {
    $("#skCtx").innerHTML = `<span class="sk-dim">Gagal membaca data: ${esc(err.message)}</span>`;
  }
}

function eventFromPreset(i, roundNo) {
  const e = kabar.events[i];
  return { round: roundNo, kind: String(i), name: e.name, effect: e.effect, target: e.target, aw: e.aw };
}
function addEvent() {
  if (events.length >= 8) return;
  const hari = +$("#skHari").value || 20;
  events.push(eventFromPreset(0, Math.min(hari, Math.max(1, Math.round(hari / 4) + events.length * 3))));
  renderEvents();
}
function renderEvents() {
  const segOpts = [`<option value="all">Semua orang</option>`].concat(kabar.segments.map((s) => `<option value="${s.key}">${esc(s.label)}</option>`));
  $("#skEvents").innerHTML = events.map((e, i) => `
    <div class="sk-ev" data-i="${i}">
      <label>Hari<input class="form-control form-control-sm" type="number" min="1" data-f="round" value="${e.round}"></label>
      <label>Event<select class="form-select form-select-sm" data-f="kind">
        ${kabar.events.map((p, k) => `<option value="${k}" ${e.kind === String(k) ? "selected" : ""}>${esc(p.name)}</option>`).join("")}
        <option value="custom" ${e.kind === "custom" ? "selected" : ""}>Kustom…</option>
      </select></label>
      <button type="button" class="sk-rm" data-rm="${i}" aria-label="Hapus event">✕</button>
      ${e.kind === "custom" ? `<label class="sk-full">Nama event<input class="form-control form-control-sm" type="text" data-f="name" value="${esc(e.name)}" maxlength="80"></label>` : ""}
      <label class="sk-full">Sasaran<select class="form-select form-select-sm" data-f="target">${segOpts.map((o) => o.replace(`value="${e.target}"`, `value="${e.target}" selected`)).join("")}</select></label>
      <label class="sk-full">Pengaruh ke opini: <output>${e.effect >= 0 ? "+" : ""}${Math.round(e.effect * 100)}</output>
        <input type="range" min="-100" max="100" data-f="effect" value="${Math.round(e.effect * 100)}" style="accent-color:var(--accum)"></label>
      <label class="sk-full">Menambah yang tahu: <output>${Math.round(e.aw * 100)}%</output>
        <input type="range" min="0" max="100" data-f="aw" value="${Math.round(e.aw * 100)}" style="accent-color:var(--accum)"></label>
    </div>`).join("");
  $$("#skEvents .sk-ev").forEach((row) => {
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
  $$("#skEvents [data-rm]").forEach((b) => (b.onclick = () => { events.splice(+b.dataset.rm, 1); renderEvents(); }));
  $("#skAddEv").disabled = events.length >= 8;
}

async function run() {
  const params = {};
  $$("#skParams input").forEach((i) => (params[i.dataset.key] = +i.value));
  const body = {
    kabar: kabar.key, kode: $("#skKode").value.trim().toUpperCase(), params, profil: $("#skProfil").checked,
    population: +$("#skPop").value, rounds: +$("#skHari").value, runs: +$("#skRuns").value, seed: +$("#skSeed").value,
    events: events.map(({ round, name, effect, target, aw }) => ({ round, name, effect, target, aw })),
  };
  const btn = $("#skRun"), st = $("#skStatus");
  btn.disabled = true;
  st.className = "sk-status";
  st.textContent = "Menjalankan simulasi…";
  const t0 = performance.now();
  try {
    const res = await fetch("/sebaran-kabar/jalankan", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRFToken": csrf() },
      body: JSON.stringify(body),
    });
    if (!res.ok) throw new Error("server " + res.status);
    const data = await res.json();
    st.textContent = `Selesai dalam ${((performance.now() - t0) / 1000).toFixed(1)} detik.`;
    history.unshift({ when: new Date(), data });
    showResult(data);
  } catch (err) {
    st.className = "sk-status err";
    st.textContent = "Gagal: " + err.message;
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
  $("#skEmpty").hidden = true;
  $("#skResults").hidden = false;
  renderKpis();
  renderReport();
  renderHistory();
  $("#skRound").max = R.config.rounds;
  buildCharts();
  startLayout();
  setRound(R.config.rounds);
}

function kpi(label, val, sub) {
  return `<div class="content-card sk-kpi"><div class="l">${esc(label)}</div><div class="v">${val}</div><div class="s">${sub}</div></div>`;
}
function renderKpis() {
  const a = R.agg, ex = a.extra, last = (k, q = "p50") => a[k][q][a[k][q].length - 1];
  const peak = Math.round(ex.peak_round.p50);
  $("#skKpis").innerHTML = [
    kpi("Sentimen akhir", sgn(last("mean_op")), `${sentLabel(last("mean_op"))} · awal ${sgn(a.mean_op.p50[0])}`),
    kpi("Puncak obrolan", "hari " + peak, `${Math.round(a.posts.p50[peak] || 0)} postingan/hari`),
    kpi("Pegang posisi beli", pct(last("pos_action")), `jual ${pct(last("neg_action"))} · rentang beli ${pct(last("pos_action", "p10"))}–${pct(last("pos_action", "p90"))}`),
    kpi("Ritel masuk telat", ex.ritel_buyers.p50 > 0.02 ? pct(ex.late_buy.p50) : "–", ex.ritel_buyers.p50 > 0.02 ? `beli setelah puncak · cut loss ${pct(ex.cutloss.p50)}` : "hampir tidak ada ritel beli"),
    kpi("Orang dalam keluar", ex.insider_sell_round != null && ex.insider_sell_share >= 0.5 ? "hari " + ex.insider_sell_round : "–", ex.insider_sell_round != null ? `terjadi di ${pct(ex.insider_sell_share)} simulasi` : "tidak terjadi"),
  ].join("");
}

function divbar(o) {
  const w = Math.min(1, Math.abs(o)) * 50;
  const style = o < 0 ? `right:50%;width:${w}%;background:var(--distrib)` : `left:50%;width:${w}%;background:var(--accum)`;
  return `<div class="sk-div" role="img" aria-label="opini ${sgn(o)}"><i style="${style}"></i></div>`;
}

function renderReport() {
  const r = R.report;
  const list = (items) => `<ul>${items.map((x) => `<li>${md(x)}</li>`).join("")}</ul>`;
  $("#skTab-laporan").innerHTML = `
    <div class="content-card sk-card"><p class="sk-head">${md(r.headline)}</p>${list(r.summary)}</div>
    ${r.profil_dipakai && r.asumsi.length ? `<div class="content-card sk-card sk-asumsi">
      <h3>Profil saham yang dipakai <span class="sk-tag">ASUMSI · belum dikalibrasi</span></h3>
      <p class="sk-note">Data ${esc(R.config.kode)} mengubah komposisi dan perilaku komunitas lewat aturan di bawah. Arah tiap aturan masuk akal,
        tapi besarnya belum pernah diuji terhadap kabar nyata. Matikan "Sesuaikan komunitas dengan profil saham" untuk membandingkan.</p>
      ${list(r.asumsi)}
      <p class="sk-note mb-0">Komunitas: ${R.preset.segments.map((s) => `${esc(s.label)} ${pct(s.share)}`).join(" · ")}</p>
    </div>` : `<div class="content-card sk-card"><p class="sk-note mb-0">Profil saham <b>tidak</b> dipakai: komunitas sama untuk semua emiten, hanya tiga slider yang berbeda.</p></div>`}
    <div class="sk-cols">
      <div class="content-card sk-card"><h3>Alur cerita</h3>${list(r.phases)}</div>
      <div class="content-card sk-card"><h3>Titik balik</h3>${r.turning_points.length ? r.turning_points.map((t) => `<div class="sk-tp"><span class="r">Hari ${t.round}</span><span>${md(t.text)}</span></div>`).join("") : `<p class="sk-note">Tidak ada perubahan tajam; opini bergerak perlahan.</p>`}</div>
    </div>
    ${r.event_effects.length ? `<div class="content-card sk-card"><h3>Dampak tiap event</h3><p class="sk-note">Dibandingkan dengan dunia yang sama (seed sama) tanpa event tersebut.</p>${list(r.event_effects.map((e) => e.text))}</div>` : ""}
    <div class="content-card sk-card"><h3>Per kelompok pelaku (akhir simulasi)</h3>
      <div class="sk-tablewrap"><table class="sk-table">
        <thead><tr><th>Kelompok</th><th class="n">Orang</th><th>Opini</th><th class="n"></th><th class="n">Beli</th><th class="n">Jual</th><th>Status</th></tr></thead>
        <tbody>${r.segments.map((s) => `<tr><td>${esc(s.label)}</td><td class="n">${s.size}</td><td>${divbar(s.op)}</td><td class="n">${sgn(s.op)}</td><td class="n">${pct(s.pos)}</td><td class="n">${pct(s.neg)}</td><td>${esc(s.verdict)}</td></tr>`).join("")}</tbody>
      </table></div>
    </div>
    <div class="sk-cols">
      <div class="content-card sk-card"><h3>Sinyal risiko</h3>${r.risks.length ? r.risks.map((x) => `<div class="sk-risk"><span class="sk-badge ${x.level}">${x.level === "tinggi" ? "▲ Tinggi" : "● Sedang"}</span><span>${md(x.text)}</span></div>`).join("") : `<p class="sk-note">Tidak ada risiko besar terdeteksi.</p>`}</div>
      <div class="content-card sk-card"><h3>Akun paling berpengaruh</h3>
        <table class="sk-table"><thead><tr><th>Akun</th><th>Kelompok</th><th class="n">Opini akhir</th></tr></thead>
        <tbody>${r.key_agents.map((k) => `<tr><td><button class="sk-link" data-agent="${k.id}">@${esc(k.handle)}</button></td><td>${esc(k.seg)}</td><td class="n">${sgn(k.final_op)}</td></tr>`).join("")}</tbody></table>
        <p class="sk-note mt-2 mb-0">Klik akun untuk membaca ceritanya.</p>
      </div>
    </div>
    <div class="sk-cols">
      <div class="content-card sk-card"><h3>Yang perlu dicek</h3>${list(r.recommendations)}</div>
      <div class="content-card sk-card"><h3>Eksperimen berikutnya</h3>${list(r.experiments)}</div>
    </div>
    <p class="sk-note">${esc(r.method)}</p>`;
}

function renderHistory() {
  const el = $("#skTab-riwayat");
  const last = (a, k) => a[k].p50[a[k].p50.length - 1];
  el.innerHTML = `<div class="content-card sk-card"><h3>Riwayat simulasi (halaman ini)</h3><p class="sk-hint">Bandingkan skenario. Hilang saat halaman dimuat ulang.</p>
    <div class="sk-tablewrap"><table class="sk-table"><thead><tr><th>Jam</th><th>Emiten</th><th>Kabar</th><th>Profil</th><th>Parameter</th><th>Event</th><th class="n">Sentimen</th><th class="n">Beli</th><th class="n">Masuk telat</th><th></th></tr></thead>
    <tbody>${history.map((h, i) => {
      const d = h.data, a = d.agg;
      return `<tr${d === R ? ' style="color:var(--text)"' : ""}><td>${h.when.toLocaleTimeString("id-ID")}</td><td><b>${esc(d.config.kode)}</b></td><td>${esc(d.preset.label)}</td><td>${d.config.profil ? "ya" : "tidak"}</td>
        <td class="sk-note">${Object.entries(d.config.params).map(([k, v]) => `${esc(k)}=${v}`).join(", ")}</td>
        <td class="sk-note">${d.events.map((e) => `H${e.round} ${esc(e.name)}`).join("<br>") || "–"}</td>
        <td class="n">${sgn(last(a, "mean_op"))}</td><td class="n">${pct(last(a, "pos_action"))}</td><td class="n">${a.extra.ritel_buyers.p50 > 0.02 ? pct(a.extra.late_buy.p50) : "–"}</td>
        <td><button class="sk-link" data-hist="${i}">Buka</button></td></tr>`;
    }).join("")}</tbody></table></div></div>`;
  $$("[data-hist]", el).forEach((b) => (b.onclick = () => { showResult(history[+b.dataset.hist].data); showTab("laporan"); }));
}

function showTab(name) {
  $$(".sk-tabs button").forEach((b) => b.setAttribute("aria-selected", b.dataset.tab === name));
  $$(".sk-tab").forEach((t) => (t.hidden = t.id !== "skTab-" + name));
  if (name === "simulasi") drawNet();
}

// ---------------------------------------------------------------- pemutar
function setRound(t) {
  round = t;
  $("#skRound").value = t;
  $("#skRoundLab").textContent = `Hari ${t} / ${R.config.rounds}`;
  drawNet();
  renderFeed();
  renderSegBars();
  charts.forEach((c) => c.setCursor(t));
}
function play() {
  if (round >= R.config.rounds) setRound(0);
  $("#skPlay").textContent = "❚❚ Jeda";
  timer = setInterval(() => (round >= R.config.rounds ? stop() : setRound(round + 1)), 550);
}
function stop() {
  clearInterval(timer);
  timer = null;
  $("#skPlay").textContent = "▶ Putar";
}

// ---------------------------------------------------------------- feed
function renderFeed() {
  if (!R) return;
  const ag = R.detail.agents, segs = R.preset.segments;
  let posts;
  if ($("#skFeedMode").value === "all") posts = R.detail.posts.filter((p) => p.a >= 0).sort((a, b) => b.reach - a.reach).slice(0, 50);
  else posts = R.detail.posts.filter((p) => p.t === round).sort((a, b) => (b.news ? 1e9 : b.reach) - (a.news ? 1e9 : a.reach)).slice(0, 80);
  if (!posts.length) {
    $("#skFeed").innerHTML = `<p class="sk-hint">${round === 0 ? "Hari 0 adalah kondisi awal. Tekan Putar untuk melihat obrolan berjalan." : "Tidak ada postingan hari ini."}</p>`;
    return;
  }
  $("#skFeed").innerHTML = posts.map((p) => {
    if (p.news) return `<div class="sk-post news"><div class="sk-ava" style="background:var(--warn)">!</div><div><div class="who"><b>Event</b> · hari ${p.t}</div><div class="txt">${esc(p.text)}</div><div class="meta">memengaruhi ${p.reach} orang yang sudah tahu</div></div></div>`;
    const a = ag[p.a];
    return `<div class="sk-post"><div class="sk-ava" style="background:${opColor(p.s)}">${esc(a.name[0])}</div><div>
      <div class="who"><button class="sk-link" data-agent="${a.id}"><b>${esc(a.name)}</b></button> @${esc(a.handle)} · ${esc(segs[a.seg].label)} · H${p.t}</div>
      <div class="txt">${esc(p.text)}</div>
      <div class="meta">⟳ ${p.rs} repost · ${p.reach} jangkauan · opini ${sgn(p.s)}</div></div></div>`;
  }).join("");
}

function renderSegBars() {
  const sm = R.shown_metrics.seg_mean[round];
  $("#skSegRound").textContent = `· hari ${round}`;
  $("#skSegbars").innerHTML = R.preset.segments.map((s, i) => `<div class="sk-segrow"><span>${esc(s.label)}</span>${sm[i] == null ? `<span class="sk-hint mb-0">belum tahu</span><span></span>` : `${divbar(sm[i])}<span class="n">${sgn(sm[i])}</span>`}</div>`).join("");
}

// ---------------------------------------------------------------- grafik
function niceMax(v) {
  for (const m of [0.01, 0.02, 0.05, 0.1, 0.2, 0.3, 0.5, 0.75, 1]) if (v <= m) return m;
  return 1;
}
function niceCount(v) {
  const mag = Math.pow(10, Math.floor(Math.log10(Math.max(1, v))));
  for (const f of [1, 2, 2.5, 5, 10]) if (v <= f * mag) return f * mag;
  return 10 * mag;
}
function buildCharts() {
  const a = R.agg, evs = R.events;
  const maxPosts = niceCount(Math.max(...a.posts.p90, 1));
  const maxFlow = niceMax(Math.max(...a.buy_flow.p90, ...a.sell_flow.p90, 0.005));
  charts = [
    lineChart($("#skChSent"), { series: [{ name: "Sentimen", color: "var(--info)", band: a.mean_op }], yMin: -1, yMax: 1, ticks: [-1, -0.5, 0, 0.5, 1], fmt: sgn, events: evs }),
    lineChart($("#skChBuzz"), { series: [{ name: "Postingan", color: "var(--warn)", band: a.posts }], yMin: 0, yMax: maxPosts, fmt: (v) => Math.round(v), events: evs }),
    lineChart($("#skChFlow"), {
      series: [{ name: "Beli", color: "var(--accum)", band: a.buy_flow }, { name: "Jual", color: "var(--distrib)", band: a.sell_flow }],
      yMin: 0, yMax: maxFlow, fmt: maxFlow <= 0.05 ? pct1 : pct, events: evs,
    }),
  ];
}

function lineChart(el, o) {
  const W = 420, H = 210, ml = 46, mr = 12, mt = 12, mb = 24;
  const n = o.series[0].band.p50.length;
  const X = (t) => ml + (t / (n - 1)) * (W - ml - mr);
  const Y = (v) => mt + (1 - (v - o.yMin) / (o.yMax - o.yMin)) * (H - mt - mb);
  const ticks = o.ticks || [0, 0.25, 0.5, 0.75, 1].map((f) => o.yMin + f * (o.yMax - o.yMin));
  const path = (arr) => arr.map((v, t) => `${t ? "L" : "M"}${X(t).toFixed(1)},${Y(Math.min(o.yMax, v)).toFixed(1)}`).join("");
  const step = n > 40 ? 10 : 5;
  let svg = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(o.series.map((s) => s.name).join(", "))}">`;
  svg += ticks.map((v) => `<line x1="${ml}" x2="${W - mr}" y1="${Y(v)}" y2="${Y(v)}" style="stroke:${v === 0 && o.yMin < 0 ? "var(--line)" : "var(--line-soft)"}"/><text x="${ml - 6}" y="${Y(v) + 4}" text-anchor="end">${o.fmt(v)}</text>`).join("");
  for (let t = 0; t < n; t += step) svg += `<text x="${X(t)}" y="${H - 6}" text-anchor="middle">${t}</text>`;
  svg += `<line x1="${ml}" x2="${W - mr}" y1="${H - mb}" y2="${H - mb}" style="stroke:var(--line)"/>`;
  svg += o.events.map((e) => `<line x1="${X(e.round)}" x2="${X(e.round)}" y1="${mt}" y2="${H - mb}" style="stroke:var(--text-dim)" stroke-dasharray="3 3"/><path d="M${X(e.round) - 4},${mt - 3}L${X(e.round) + 4},${mt - 3}L${X(e.round)},${mt + 3}Z" style="fill:var(--warn)"/>`).join("");
  for (const s of o.series) {
    const b = s.band;
    const area = path(b.p90) + b.p10.map((v, t) => `L${X(t).toFixed(1)},${Y(Math.min(o.yMax, v)).toFixed(1)}`).reverse().join("") + "Z";
    svg += `<path d="${area}" style="fill:${s.color};opacity:.15"/>`;
    svg += `<path d="${path(b.p50)}" style="fill:none;stroke:${s.color};stroke-width:2;stroke-linejoin:round"/>`;
  }
  svg += `<line class="cur" y1="${mt}" y2="${H - mb}" style="stroke:var(--text-mid)" opacity=".5"/>`;
  svg += `<line class="hov" y1="${mt}" y2="${H - mb}" style="stroke:var(--text)" visibility="hidden"/>`;
  svg += o.series.map((s, i) => `<circle class="hd hd${i}" r="4" style="fill:${s.color};stroke:var(--surface);stroke-width:2" visibility="hidden"/>`).join("");
  svg += `<rect x="${ml}" y="0" width="${W - ml - mr}" height="${H}" fill="transparent" style="cursor:crosshair"/></svg>`;
  const legend = o.series.length > 1 ? `<div class="sk-legend mb-1">${o.series.map((s) => `<span><i class="sk-dot" style="background:${s.color}"></i>${esc(s.name)}</span>`).join("")}</div>` : "";
  el.innerHTML = legend + svg;
  const root = $("svg", el), hov = $(".hov", root), cur = $(".cur", root);
  const tAt = (ev) => {
    const r = root.getBoundingClientRect();
    const x = ((ev.clientX - r.left) / r.width) * W;
    return Math.max(0, Math.min(n - 1, Math.round(((x - ml) / (W - ml - mr)) * (n - 1))));
  };
  root.addEventListener("mousemove", (ev) => {
    const t = tAt(ev);
    hov.setAttribute("x1", X(t)); hov.setAttribute("x2", X(t)); hov.setAttribute("visibility", "visible");
    o.series.forEach((s, i) => { const c = $(".hd" + i, root); c.setAttribute("cx", X(t)); c.setAttribute("cy", Y(Math.min(o.yMax, s.band.p50[t]))); c.setAttribute("visibility", "visible"); });
    const evs = o.events.filter((e) => e.round === t);
    showTip(`<div class="t">Hari ${t}</div>${o.series.map((s) => `<div class="r"><span><i class="sw" style="background:${s.color}"></i>${esc(s.name)}</span><b>${o.fmt(s.band.p50[t])}</b></div><div class="r d"><span></span><span>${o.fmt(s.band.p10[t])} s/d ${o.fmt(s.band.p90[t])}</span></div>`).join("")}${evs.map((e) => `<div class="d">Event: ${esc(e.name)}</div>`).join("")}<div class="d">Klik untuk lompat ke hari ini</div>`, ev.clientX, ev.clientY);
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
  const dx = new Float64Array(n), dy = new Float64Array(n);
  let it = 0;
  const step = () => {
    if (job !== layoutJob) return;
    for (let s = 0; s < perFrame && it < total; s++, it++) {
      const temp = 0.08 * (1 - it / total) + 0.002;
      dx.fill(0); dy.fill(0);
      for (let i = 0; i < n; i++) {
        for (let j = i + 1; j < n; j++) {
          const ddx = x[i] - x[j], ddy = y[i] - y[j];
          const f = k2 / (ddx * ddx + ddy * ddy + 1e-6);
          dx[i] += ddx * f; dy[i] += ddy * f; dx[j] -= ddx * f; dy[j] -= ddy * f;
        }
      }
      for (const [a, b] of edges) {
        const ddx = x[a] - x[b], ddy = y[a] - y[b];
        const f = (Math.sqrt(ddx * ddx + ddy * ddy) + 1e-6) / k;
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
function stateLabel(st) {
  return st === "u" ? "belum tahu" : st === "n" ? "sudah jual" : st === "p" ? "pegang posisi beli" : "belum transaksi";
}
function initNet() {
  const cv = $("#skNet");
  cv.addEventListener("mousemove", (e) => {
    const i = nodeAt(e);
    if (i !== hoverNode) { hoverNode = i; drawNet(); }
    if (i < 0) return hideTip();
    const a = R.detail.agents[i], o = R.detail.ops[round][i], st = R.detail.states[round][i];
    showTip(`<div class="t">${esc(a.name)}</div><div class="d">@${esc(a.handle)} · ${esc(R.preset.segments[a.seg].label)}</div>
      <div class="r"><span>Opini</span><b>${st === "u" ? "–" : sgn(o)}</b></div><div class="r"><span>Status</span><span>${stateLabel(st)}</span></div><div class="r"><span>Pengikut</span><span>${a.deg}</span></div>`, e.clientX, e.clientY);
  });
  cv.addEventListener("mouseleave", () => { hoverNode = -1; hideTip(); drawNet(); });
  cv.addEventListener("click", (e) => { const i = nodeAt(e); if (i >= 0) openAgent(i); });
}
function nodeAt(e) {
  if (!netGeom || !R) return -1;
  const r = $("#skNet").getBoundingClientRect();
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
  const cv = $("#skNet");
  if (!R || !layout || !cv.clientWidth) return;
  const dpr = devicePixelRatio || 1, W = cv.clientWidth, H = cv.clientHeight;
  if (cv.width !== Math.round(W * dpr) || cv.height !== Math.round(H * dpr)) { cv.width = Math.round(W * dpr); cv.height = Math.round(H * dpr); }
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
  const scale = Math.min(1.2, Math.max(0.55, Math.sqrt(W * H / n) / 25));
  for (let i = 0; i < n; i++) { px[i] = ox + (x[i] - x0) * s; py[i] = oy + (y[i] - y0) * s; rad[i] = (2 + Math.sqrt(ag[i].deg) * 0.9) * scale; }
  netGeom = { px, py, rad };
  ctx.lineWidth = 0.6;
  ctx.strokeStyle = C.grid;
  ctx.beginPath();
  for (const [a, b] of R.detail.edges) { ctx.moveTo(px[a], py[a]); ctx.lineTo(px[b], py[b]); }
  ctx.stroke();
  const focus = hoverNode >= 0 ? hoverNode : selected;
  if (focus >= 0) {
    ctx.strokeStyle = C.dim; ctx.lineWidth = 1; ctx.beginPath();
    for (const [a, b] of R.detail.edges) if (a === focus || b === focus) { ctx.moveTo(px[a], py[a]); ctx.lineTo(px[b], py[b]); }
    ctx.stroke();
  }
  for (let i = 0; i < n; i++) {
    ctx.beginPath();
    ctx.arc(px[i], py[i], rad[i], 0, 6.2832);
    if (st[i] === "u") { ctx.strokeStyle = C.dim; ctx.lineWidth = 1; ctx.stroke(); continue; }
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

// ---------------------------------------------------------------- cerita pelaku
const AKSI = {
  akumulasi: "<b>Akumulasi diam-diam</b> sebelum kabar ramai.",
  distribusi: "<b>Jual ke keramaian</b> (distribusi) saat obrolan lewat puncak.",
  cutloss: "<b>Cut loss</b>: jual rugi setelah opininya berbalik.",
};
function openAgent(id) {
  selected = id;
  drawNet();
  const a = R.detail.agents[id], ag = R.detail.agents;
  const seg = R.preset.segments[a.seg];
  const traj = R.detail.ops.map((r) => r[id]);
  const states = R.detail.states.map((s) => s[id]);
  const last = states[states.length - 1];
  const h = (i) => `<button class="sk-link" data-agent="${i}">@${esc(ag[i].handle)}</button>`;
  const items = [["Awal", states[0] === "u"
    ? `Belum tahu kabar ini. Kalau tahu, penilaian pribadinya ${sgn(a.latent0)} (${sentLabel(a.latent0)}).`
    : `Sudah tahu sejak hari pertama. Penilaian pribadinya ${sgn(a.latent0)} (${sentLabel(a.latent0)}).`]];
  for (const e of a.log) {
    let txt = "";
    if (e.k === "aware") txt = e.via ? `Mulai tahu lewat event “${esc(e.via)}”.` : `Mulai tahu dari postingan ${h(e.by)}.`;
    else if (e.k === "event") txt = `Terkena event “${esc(e.name)}”: opini ${sgn(e.d)}.`;
    else if (e.k === "social") {
      txt = e.backfire
        ? `Melihat ${e.n} postingan yang terlalu berbeda pendapat, malah makin yakin (${sgn(e.d)}).`
        : `Opini ${e.d > 0 ? "naik" : "turun"} ${Math.abs(e.d).toFixed(2)} setelah membaca ${e.n} postingan (${pct(e.neg)} negatif)${e.by != null ? `, paling terpengaruh ${h(e.by)}` : ""}.`;
    } else if (e.k === "action") {
      txt = AKSI[e.kind] || (e.to === "pos" ? "<b>Beli.</b>" : e.to === "neg" ? "<b>Jual.</b>" : "Keluar dari posisi jual, kembali menunggu.");
    } else if (e.k === "post") {
      const p = (postIndex[id + ":" + e.t] || []).find((q) => q.s === e.s);
      txt = `Memposting: “${esc(p ? p.text : "")}”${p && p.rs ? ` (di-repost ${p.rs}×)` : ""}`;
    }
    items.push([`H${e.t}`, txt]);
  }
  $("#skAgent").innerHTML = `
    <h2 id="skAgentName">${esc(a.name)}</h2>
    <p class="sk-hint">@${esc(a.handle)} · ${esc(seg.label)}</p>
    <p style="font-size:13px;color:var(--text-mid)">Opini akhir <b style="color:var(--text)">${last === "u" ? "–" : sgn(traj[traj.length - 1])}</b> · status <b style="color:var(--text)">${stateLabel(last)}</b></p>
    <div class="sk-chart" id="skAgentChart"></div>
    <div class="sk-traits">
      <div><span>Pengikut</span><b>${a.deg}</b></div>
      <div><span>Keras kepala</span><b>${a.stub.toFixed(2)}</b></div>
      <div><span>Toleransi beda pendapat</span><b>${a.eps.toFixed(2)}</b></div>
      <div><span>Tahan tidak jual</span><b>${a.loyal.toFixed(2)}</b></div>
      <div><span>Keaktifan posting</span><b>${pct(a.act)}</b></div>
      <div><span>Kepekaan pada kabar</span><b>${a.sens.toFixed(2)}</b></div>
      <div><span>Pengaruh ke orang lain</span><b>${a.inf.toFixed(1)}</b></div>
    </div>
    <h3 style="font-size:13px;color:var(--text);margin:14px 0 0">Cerita</h3>
    <ul class="sk-story">${items.map(([r, t]) => `<li><span class="r">${r}</span><span>${t}</span></li>`).join("")}</ul>`;
  lineChart($("#skAgentChart"), { series: [{ name: "Opini", color: "var(--info)", band: { p10: traj, p50: traj, p90: traj } }], yMin: -1, yMax: 1, ticks: [-1, 0, 1], fmt: sgn, events: R.events }).setCursor(round);
  $("#skDrawer").hidden = false;
}
function closeAgent() {
  if ($("#skDrawer").hidden) return;
  $("#skDrawer").hidden = true;
  selected = -1;
  hideTip();
  drawNet();
}

init();
})();
