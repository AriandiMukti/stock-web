"""Laporan berbasis aturan: membaca hasil simulasi lalu menyusun ringkasan, titik balik,
risiko, dampak event, dan rekomendasi. Teks **tebal** ditandai dengan dua bintang."""


def label_sent(x):
    if x <= -0.5:
        return "sangat negatif"
    if x <= -0.15:
        return "negatif"
    if x < 0.15:
        return "netral / campuran"
    if x < 0.5:
        return "positif"
    return "sangat positif"


def pct(x):
    return f"{int(x * 100 + 0.5)}%"


def pts(x):
    return f"{abs(x) * 100:.1f} poin"


def _smooth(s):
    return [sum(s[max(0, i - 1):i + 2]) / len(s[max(0, i - 1):i + 2]) for i in range(len(s))]


def _phases(series):
    """Pecah kurva sentimen menjadi fase naik / turun / stabil."""
    s = _smooth(series)
    labels = []
    for t in range(1, len(s)):
        d = s[t] - s[t - 1]
        labels.append("naik" if d > 0.008 else "turun" if d < -0.008 else "stabil")
    segs = []
    for t, lab in enumerate(labels, start=1):
        if segs and segs[-1][0] == lab:
            segs[-1][2] = t
        else:
            segs.append([lab, t, t])
    # gabungkan fase yang terlalu pendek ke fase sebelumnya
    merged = []
    for seg in segs:
        if merged and (seg[2] - seg[1] < 1 or merged[-1][0] == seg[0]):
            merged[-1][2] = seg[2]
        else:
            merged.append(seg)
    out = []
    for lab, a, b in merged:
        start, end = series[a - 1], series[b]
        delta = end - start
        if lab == "stabil" or abs(delta) < 0.03:
            verb = "relatif stabil"
        else:
            strong = abs(delta) > 0.2
            verb = ("naik tajam" if strong else "membaik") if delta > 0 else ("turun tajam" if strong else "memburuk")
        rng = f"Ronde {a}" if a == b else f"Ronde {a}–{b}"
        out.append(f"{rng}: sentimen {verb} ({start:+.2f} → {end:+.2f}).")
    return out


def build_report(cfg, preset, events, agg, baseline, effects, shown):
    segs = preset["segments"]
    seg_label = {s["key"]: s["label"] for s in segs}
    det = shown["detail"]
    agents = det["agents"]
    m = agg["mean_op"]["p50"]
    R = len(m) - 1
    fin = {k: agg[k]["p50"][-1] for k in ("mean_op", "aware", "neg_action", "pos_action", "polar", "pct_pos", "pct_neg")}
    lo = {k: agg[k]["p10"][-1] for k in ("neg_action", "pos_action", "mean_op")}
    hi = {k: agg[k]["p90"][-1] for k in ("neg_action", "pos_action", "mean_op")}
    neg_l, pos_l = preset["neg_label"].lower(), preset["pos_label"].lower()

    # ---------------- ringkasan
    headline = (f"Reaksi publik terhadap **{cfg['subject']}** ({preset['label'].lower()}) "
                f"berakhir **{label_sent(fin['mean_op'])}** setelah {R} ronde.")
    peak_t = min(range(len(m)), key=lambda t: m[t])
    top_t = max(range(len(m)), key=lambda t: m[t])
    summary = [
        f"Sentimen rata-rata: **{m[0]:+.2f} → {fin['mean_op']:+.2f}** (rentang {lo['mean_op']:+.2f} s/d {hi['mean_op']:+.2f} dari {cfg['runs']} simulasi).",
        f"**{pct(fin['neg_action'])}** populasi memilih *{neg_l}* (rentang {pct(lo['neg_action'])}–{pct(hi['neg_action'])}).",
        f"**{pct(fin['pos_action'])}** populasi memilih *{pos_l}* (rentang {pct(lo['pos_action'])}–{pct(hi['pos_action'])}).",
        f"Yang tahu isu ini: **{pct(fin['aware'])}** dari {cfg['population']} orang. Di antara mereka {pct(fin['pct_pos'])} positif, {pct(fin['pct_neg'])} negatif.",
    ]
    if m[peak_t] < m[0] - 0.05 and peak_t not in (0, R):
        summary.append(f"Titik terendah di **ronde {peak_t}** ({m[peak_t]:+.2f}), lalu pulih ke {fin['mean_op']:+.2f}.")
    elif m[top_t] > m[0] + 0.05 and top_t not in (0, R):
        summary.append(f"Puncak sentimen di **ronde {top_t}** ({m[top_t]:+.2f}), lalu turun ke {fin['mean_op']:+.2f}.")

    # ---------------- titik balik
    ev_by_round = {}
    for e in events:
        ev_by_round.setdefault(e["round"], []).append(e["name"])
    posts_by_round = {}
    for p in det["posts"]:
        if p["a"] >= 0:
            posts_by_round.setdefault(p["t"], []).append(p)
    deltas = sorted(((m[t] - m[t - 1], t) for t in range(1, len(m))), key=lambda x: -abs(x[0]))
    turning = []
    for d, t in deltas[:3]:
        if abs(d) < 0.04:
            continue
        arah = "naik" if d > 0 else "turun"
        if t in ev_by_round:
            why = "dipicu event **" + "**, **".join(ev_by_round[t]) + "**"
        else:
            cands = posts_by_round.get(t - 1, []) + posts_by_round.get(t, [])
            cands = [p for p in cands if (p["s"] > 0) == (d > 0)]
            if cands:
                top = max(cands, key=lambda p: p["reach"])
                why = (f"terbawa postingan @{agents[top['a']]['handle']} yang menjangkau {top['reach']} orang: "
                       f"“{top['text']}”")
            else:
                why = "efek berantai dari obrolan di jaringan"
        turning.append({"round": t, "text": f"Sentimen {arah} {abs(d):.2f} — {why}."})
    turning.sort(key=lambda x: x["round"])

    # ---------------- segmen
    segrows = []
    for s in segs:
        f = agg["final_seg"][s["key"]]
        if f["op"] <= -0.35 or f["neg"] > 0.2:
            verdict = "paling berisiko"
        elif f["op"] >= 0.35:
            verdict = "pendukung kuat"
        elif f["aware"] < 0.4:
            verdict = "belum tersentuh"
        else:
            verdict = "mengambang"
        segrows.append({"key": s["key"], "label": s["label"], "op": round(f["op"], 2), "neg": round(f["neg"], 3),
                        "pos": round(f["pos"], 3), "aware": round(f["aware"], 2), "size": int(f["size"]),
                        "verdict": verdict})

    # ---------------- risiko
    risks = []
    if fin["neg_action"] > 0.15:
        risks.append({"level": "tinggi", "text": f"{pct(fin['neg_action'])} populasi {neg_l}. Ini dampak nyata, bukan sekadar keluhan."})
    elif fin["neg_action"] > 0.06:
        risks.append({"level": "sedang", "text": f"{pct(fin['neg_action'])} populasi {neg_l}."})
    if hi["neg_action"] - lo["neg_action"] > 0.1:
        risks.append({"level": "sedang", "text": f"Hasil sangat tergantung kebetulan (siapa yang viral duluan): {neg_l} bisa {pct(lo['neg_action'])} sampai {pct(hi['neg_action'])}."})
    if fin["polar"] > 0.5:
        risks.append({"level": "sedang", "text": f"Opini terpolarisasi (sebaran {fin['polar']:.2f}). Dua kubu makin sulit saling mendengar."})
    worst = min(segrows, key=lambda r: r["op"])
    if worst["op"] < -0.4:
        risks.append({"level": "tinggi", "text": f"Segmen **{worst['label']}** sangat negatif ({worst['op']:+.2f}) dan bisa menularkan ke segmen lain."})
    for s in segs:
        if s["hub"] and agg["final_seg"][s["key"]]["op"] < -0.2:
            risks.append({"level": "tinggi", "text": f"**{s['label']}** (akun paling banyak pengikut) bersikap negatif. Suara mereka memperbesar penolakan."})
    if m[peak_t] < -0.5 and peak_t < R:
        risks.append({"level": "sedang", "text": f"Ada fase krisis di ronde {peak_t} (sentimen {m[peak_t]:+.2f}) walau akhirnya pulih. Siapkan respons cepat untuk fase ini."})
    if fin["aware"] < 0.5:
        risks.append({"level": "sedang", "text": f"Hanya {pct(fin['aware'])} yang tahu. Kesimpulan sentimen berasal dari kelompok kecil."})

    # ---------------- dampak event
    event_effects = []
    for ef in effects:
        ev, w = ef["event"], ef["without"]
        d_neg = fin["neg_action"] - w["neg_action"]["p50"][-1]
        d_pos = fin["pos_action"] - w["pos_action"]["p50"][-1]
        d_op = fin["mean_op"] - w["mean_op"]["p50"][-1]
        good = d_op > 0.02 or d_neg < -0.01
        bad = d_op < -0.02 or d_neg > 0.01
        verdict = "membantu" if good and not bad else "merugikan" if bad and not good else "dampaknya kecil"
        event_effects.append({
            "name": ev["name"], "round": ev["round"], "verdict": verdict,
            "d_op": round(d_op, 3), "d_neg": round(d_neg, 3), "d_pos": round(d_pos, 3),
            "text": (f"**{ev['name']}** (ronde {ev['round']}) {verdict}: sentimen akhir {d_op:+.2f}, "
                     f"{neg_l} {'+' if d_neg >= 0 else '−'}{pts(d_neg)}, {pos_l} {'+' if d_pos >= 0 else '−'}{pts(d_pos)} "
                     f"dibanding tanpa event ini."),
        })

    # ---------------- agen kunci
    key_agents = sorted(agents, key=lambda a: -a["inf"])[:5]
    key_list = [{"id": a["id"], "handle": a["handle"], "seg": seg_label[segs[a["seg"]]["key"]],
                 "inf": a["inf"], "final_op": det["ops"][-1][a["id"]]} for a in key_agents]

    # ---------------- rekomendasi & eksperimen lanjutan
    stat = {
        "params": cfg["params"], "final": fin,
        "seg": {r["key"]: r for r in segrows},
        "has_positive_event": any(e["effect"] > 0 for e in events),
    }
    recs = preset["recs"](stat)
    if key_list and key_list[0]["final_op"] < -0.2:
        recs.append(f"Akun paling berpengaruh (@{key_list[0]['handle']}) negatif. Dekati akun-akun kunci lebih awal.")
    late = [e for e in events if e["effect"] > 0 and e["round"] > R / 3]
    if late:
        recs.append(f"Intervensi positif '{late[0]['name']}' baru muncul di ronde {late[0]['round']}. Uji majukan ke ronde 2–3; opini yang sudah mengeras sulit diubah.")
    if not recs:
        recs.append("Tidak ada sinyal bahaya besar. Pantau segmen yang masih mengambang.")

    experiments = [
        "Jalankan ulang dengan seed berbeda untuk melihat apakah polanya konsisten.",
        "Tambah satu event positif di ronde 2 dan bandingkan di tab Riwayat.",
    ]
    first_param = preset["params"][0]
    experiments.insert(0, f"Ubah **{first_param['label']}** dan bandingkan hasilnya dengan skenario ini.")
    if not events:
        neg_ev = next((e for e in preset["events"] if e["effect"] < 0), None)
        if neg_ev:
            experiments.append(f"Uji ketahanan: tambahkan event '{neg_ev['name']}' di tengah simulasi.")

    return {
        "headline": headline,
        "summary": summary,
        "phases": _phases(m),
        "turning_points": turning,
        "segments": segrows,
        "risks": risks,
        "event_effects": event_effects,
        "key_agents": key_list,
        "recommendations": recs,
        "experiments": experiments,
        "method": ("Ini model berbasis agen dengan aturan, bukan ramalan pasti. Angka berasal dari "
                   f"{cfg['runs']} kali simulasi (median dan rentang 10–90%). Gunakan untuk membandingkan "
                   "skenario dan mencari titik rawan, bukan untuk angka absolut."),
    }
