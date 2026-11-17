"""Laporan berbasis aturan untuk Sebaran Kabar. Teks **tebal** ditandai dua bintang."""


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
    """Pecah kurva sentimen jadi fase naik / turun / stabil."""
    s = _smooth(series)
    segs = []
    for t in range(1, len(s)):
        d = s[t] - s[t - 1]
        lab = "naik" if d > 0.008 else "turun" if d < -0.008 else "stabil"
        if segs and segs[-1][0] == lab:
            segs[-1][2] = t
        else:
            segs.append([lab, t, t])
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
        rng = f"Hari {a}" if a == b else f"Hari {a}–{b}"
        out.append(f"{rng}: sentimen {verb} ({start:+.2f} → {end:+.2f}).")
    return out


def build_report(cfg, preset, events, agg, effects, shown, konteks):
    segs = preset["segments"]
    seg_label = {s["key"]: s["label"] for s in segs}
    det = shown["detail"]
    agents = det["agents"]
    kode = cfg["kode"]
    m = agg["mean_op"]["p50"]
    posts = agg["posts"]["p50"]
    R = len(m) - 1
    last = lambda k, q="p50": agg[k][q][-1]
    fin = {k: last(k) for k in ("mean_op", "aware", "neg_action", "pos_action", "polar", "pct_pos", "pct_neg")}
    ex = agg["extra"]

    # ---------------- ringkasan
    headline = (f"Kabar **{preset['label'].lower()}** di **${kode}** berakhir **{label_sent(fin['mean_op'])}** "
                f"setelah {R} hari bursa.")
    # Median hari puncak per simulasi -- sama dengan dasar hitung "masuk telat" di engine.
    peak = max(1, min(R, int(ex["peak_round"]["p50"] + 0.5)))
    summary = [
        f"Sentimen komunitas: **{m[0]:+.2f} → {fin['mean_op']:+.2f}** (rentang {last('mean_op', 'p10'):+.2f} s/d {last('mean_op', 'p90'):+.2f} dari {cfg['runs']} simulasi).",
        f"Obrolan paling ramai di **hari ke-{peak}** (~{posts[peak]:.0f} postingan/hari di komunitas simulasi), lalu meredup.",
        f"**{pct(fin['pos_action'])}** komunitas memegang posisi beli di akhir; **{pct(fin['neg_action'])}** sudah jual.",
        f"Yang tahu kabar ini: **{pct(fin['aware'])}** dari {cfg['population']} orang.",
    ]
    if ex["ritel_buyers"]["p50"] > 0.02:
        summary.append(f"Dari ritel yang ikut beli, **{pct(ex['late_buy']['p50'])}** masuk SETELAH obrolan memuncak, "
                       f"dan **{pct(ex['cutloss']['p50'])}** akhirnya jual rugi.")
    if ex["insider_sell_round"] is not None and ex["insider_sell_share"] >= 0.5:
        summary.append(f"Orang dalam mulai **jual ke keramaian di hari ke-{ex['insider_sell_round']}** "
                       f"(terjadi di {pct(ex['insider_sell_share'])} simulasi).")

    # ---------------- titik balik
    ev_by_round = {}
    for e in events:
        ev_by_round.setdefault(e["round"], []).append(e["name"])
    posts_by_round = {}
    for p in det["posts"]:
        if p["a"] >= 0:
            posts_by_round.setdefault(p["t"], []).append(p)
    turning = []
    for d, t in sorted(((m[t] - m[t - 1], t) for t in range(1, len(m))), key=lambda x: -abs(x[0]))[:3]:
        if abs(d) < 0.04:
            continue
        arah = "naik" if d > 0 else "turun"
        if t in ev_by_round:
            why = "dipicu **" + "**, **".join(ev_by_round[t]) + "**"
        else:
            cands = [p for p in posts_by_round.get(t - 1, []) + posts_by_round.get(t, []) if (p["s"] > 0) == (d > 0)]
            if cands:
                top = max(cands, key=lambda p: p["reach"])
                why = f"terbawa postingan @{agents[top['a']]['handle']} (jangkauan {top['reach']}): “{top['text']}”"
            else:
                why = "efek berantai obrolan di komunitas"
        turning.append({"round": t, "text": f"Sentimen {arah} {abs(d):.2f} — {why}."})
    turning.sort(key=lambda x: x["round"])

    # ---------------- segmen
    segrows = []
    for s in segs:
        f = agg["final_seg"][s["key"]]
        if s["insider"]:
            verdict = "jual ke keramaian" if f["neg"] > 0.3 else "masih pegang" if f["pos"] > 0.3 else "diam"
        elif f["op"] <= -0.35 or f["neg"] > 0.2:
            verdict = "menekan jual"
        elif f["op"] >= 0.35:
            verdict = "paling bersemangat"
        elif f["aware"] < 0.4:
            verdict = "belum tahu"
        else:
            verdict = "mengambang"
        segrows.append({"key": s["key"], "label": s["label"], "op": round(f["op"], 2), "neg": round(f["neg"], 3),
                        "pos": round(f["pos"], 3), "aware": round(f["aware"], 2), "size": int(f["size"]),
                        "verdict": verdict})

    # ---------------- risiko
    risks = []
    if ex["late_buy"]["p50"] > 0.4 and ex["ritel_buyers"]["p50"] > 0.02:
        risks.append({"level": "tinggi", "text": f"Mayoritas pembelian ritel ({pct(ex['late_buy']['p50'])}) terjadi setelah puncak obrolan — pola 'beli karena ramai'."})
    if ex["insider_sell_round"] is not None and ex["insider_sell_share"] >= 0.5 and ex["insider_sell_round"] <= peak + 1:
        risks.append({"level": "tinggi", "text": f"Orang dalam jual (hari {ex['insider_sell_round']}) bersamaan dengan puncak obrolan (hari {peak}): keramaian ritel jadi likuiditas keluar mereka."})
    if ex["cutloss"]["p50"] > 0.15:
        risks.append({"level": "tinggi", "text": f"{pct(ex['cutloss']['p50'])} ritel yang beli akhirnya jual rugi."})
    if fin["polar"] > 0.5:
        risks.append({"level": "sedang", "text": f"Komunitas terbelah (sebaran {fin['polar']:.2f}): kubu pom-pom vs kubu skeptis saling tidak mendengar."})
    if last("neg_action", "p90") - last("neg_action", "p10") > 0.1:
        risks.append({"level": "sedang", "text": f"Hasil sangat tergantung siapa yang viral duluan: jual bisa {pct(last('neg_action', 'p10'))} sampai {pct(last('neg_action', 'p90'))}."})
    for s in segs:
        if s["hub"] and agg["final_seg"][s["key"]]["op"] > 0.4 and fin["mean_op"] < 0.1:
            risks.append({"level": "sedang", "text": f"**{s['label']}** masih sangat positif padahal komunitas sudah dingin. Waspadai ajakan beli yang tersisa."})
    b = (konteks or {}).get("buzz")
    if b and b.get("peringkat") and b["peringkat"] <= 20:
        risks.append({"level": "sedang", "text": f"${kode} sudah di peringkat {b['peringkat']} Ramai Dibahas ({b['tanggal']}). Kabar yang ramai biasanya ketemu SETELAH harga lari."})

    # ---------------- dampak event
    event_effects = []
    for ef in effects:
        ev, w = ef["event"], ef["without"]
        d_op = fin["mean_op"] - w["mean_op"]["p50"][-1]
        d_pos = fin["pos_action"] - w["pos_action"]["p50"][-1]
        d_neg = fin["neg_action"] - w["neg_action"]["p50"][-1]
        d_late = ex["late_buy"]["p50"] - w["extra"]["late_buy"]["p50"]
        event_effects.append({
            "name": ev["name"], "round": ev["round"],
            "text": (f"**{ev['name']}** (hari {ev['round']}): sentimen akhir {d_op:+.2f}, "
                     f"posisi beli {'+' if d_pos >= 0 else '−'}{pts(d_pos)}, jual {'+' if d_neg >= 0 else '−'}{pts(d_neg)}, "
                     f"ritel masuk telat {'+' if d_late >= 0 else '−'}{pts(d_late)} dibanding tanpa event ini."),
        })

    # ---------------- akun kunci
    key_list = [{"id": a["id"], "handle": a["handle"], "seg": seg_label[segs[a["seg"]]["key"]],
                 "inf": a["inf"], "final_op": det["ops"][-1][a["id"]]}
                for a in sorted(agents, key=lambda a: -a["inf"])[:5]]

    # ---------------- rekomendasi & eksperimen
    stat = {
        "params": cfg["params"], "final": fin, "seg": {r["key"]: r for r in segrows},
        "late_buy": ex["late_buy"]["p50"], "cutloss": ex["cutloss"]["p50"],
        "insider_sell_round": ex["insider_sell_round"] if ex["insider_sell_share"] >= 0.5 else None,
        "ada_event_resmi": any("resmi" in e["name"].lower() or "bantahan" in e["name"].lower() for e in events),
        "ada_event_positif": any(e["effect"] > 0 for e in events),
    }
    recs = preset["recs"](stat)
    recs.append(f"Mau tahu efeknya ke HARGA? Pakai Digital Twin dengan skenario 'Sentimen / berita' untuk ${kode}.")

    experiments = [f"Ubah **{preset['params'][0]['label']}** lalu bandingkan di tab Riwayat.",
                   "Jalankan ulang dengan seed berbeda: apakah pola masuk telat tetap muncul?"]
    neg_ev = next((e for e in preset["events"] if e["effect"] < 0), None)
    if neg_ev and not any(e["name"] == neg_ev["name"] for e in events):
        experiments.append(f"Tambah event '{neg_ev['name']}' di hari ke-{max(2, peak)} (puncak obrolan).")

    return {
        "headline": headline, "summary": summary, "phases": _phases(m), "turning_points": turning,
        "segments": segrows, "risks": risks, "event_effects": event_effects, "key_agents": key_list,
        "recommendations": recs, "experiments": experiments,
        "asumsi": preset.get("asumsi", []), "profil_dipakai": cfg.get("profil", False),
        "method": ("Model berbasis agen dengan aturan, bukan ramalan dan belum diuji maju terhadap kabar nyata. "
                   f"Angka berasal dari {cfg['runs']} simulasi (median dan rentang 10–90%). Gunakan untuk "
                   "membandingkan skenario dan melatih cara membaca keramaian, bukan sebagai sinyal beli/jual."),
    }
