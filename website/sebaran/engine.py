"""
Engine Sebaran Kabar: model berbasis agen, tanpa AI/LLM. 1 ronde = 1 hari bursa.

Per hari:
  1. Event terjadwal (bantahan emiten, ARA, UMA, ...) menggeser opini segmen
     sasaran dan menambah orang yang tahu.
  2. Agen yang tahu memposting dengan peluang sebanding keaktifan, perhatian
     publik, dan kuatnya opini. Tetangga yang sependapat me-repost.
  3. Opini diperbarui dengan bounded confidence (Hegselmann-Krause): hanya
     postingan yang cukup dekat yang didengar, postingan negatif berbobot
     lebih (negativity bias), dan yang terlalu jauh malah membuat makin yakin.
  4. Opini ekstrem jadi transaksi: beli, jual, atau jual rugi (cut loss).
     Orang dalam tahu sejak hari pertama, beli duluan, lalu jual ke
     keramaian saat sentimen komunitas memuncak.

Simulasi diulang beberapa kali (Monte Carlo) untuk mendapat rentang hasil.
Ini dunia buatan untuk melatih cara berpikir, BUKAN ramalan harga -- efek
ke harga adalah urusan Digital Twin (website/twin/).
"""
import math
import random

NEG_BIAS = 0.3        # postingan negatif berbobot 30% lebih besar
SEE_PROB = 0.35       # peluang yang belum tahu jadi tahu, per postingan yang dilihat
ATTENTION_DECAY = 0.85
HABITUATION = 0.03    # penilaian pribadi pelan-pelan kembali ke sikap dasar

FIRST = ["Rina", "Budi", "Sari", "Andi", "Dewi", "Agus", "Putri", "Rizky", "Fitri", "Dimas", "Ayu", "Bayu",
         "Nadia", "Fajar", "Indah", "Yoga", "Maya", "Hendra", "Lestari", "Arif", "Wulan", "Eko", "Citra",
         "Gilang", "Nisa", "Reza", "Tika", "Wahyu", "Intan", "Doni", "Siska", "Ilham", "Mega", "Rudi",
         "Anisa", "Yusuf", "Dian", "Bagas", "Laras", "Kevin"]
LAST = ["Pratama", "Saputra", "Wijaya", "Santoso", "Lestari", "Hidayat", "Nugroho", "Kusuma", "Siregar",
        "Rahman", "Setiawan", "Putra", "Hasibuan", "Gunawan", "Halim", "Purba", "Maharani", "Utami"]
HUB_HANDLES = ["cuan_harian", "bandarmologi_id", "saham_receh", "analis_santai", "jurnal_trader", "info_emiten",
               "kabar_bursa", "rumor_saham", "teknikal_kopi", "investor_sabar", "radar_ara", "lapkeu_ringkas",
               "suara_ritel", "pasar_pagi", "skrining_harian", "dividen_hunter", "ngulik_emiten", "bursa_kini",
               "tape_reader", "valuasi_jujur"]

BUCKETS = ("vneg", "neg", "neu", "pos", "vpos")
SERIES = ("mean_op", "pct_pos", "pct_neg", "aware", "neg_action", "pos_action", "polar",
          "posts", "buy_flow", "sell_flow")


def clamp(x, lo=-1.0, hi=1.0):
    return lo if x < lo else hi if x > hi else x


def bucket(s):
    if s <= -0.5:
        return "vneg"
    if s <= -0.15:
        return "neg"
    if s < 0.15:
        return "neu"
    if s < 0.5:
        return "pos"
    return "vpos"


class _Fmt(dict):
    def __missing__(self, k):
        return "{" + k + "}"


def build_network(n, m, rng):
    """Jaringan scale-free Barabasi-Albert: sedikit akun sangat populer, mayoritas sedikit koneksi."""
    adj = [set() for _ in range(n)]
    for i in range(m + 1):
        for j in range(i + 1, m + 1):
            adj[i].add(j)
            adj[j].add(i)
    pool = [k for k in range(m + 1) for _ in range(m)]
    for v in range(m + 1, n):
        chosen = set()
        while len(chosen) < m:
            chosen.add(rng.choice(pool))
        for u in chosen:
            adj[v].add(u)
            adj[u].add(v)
            pool.extend((u, v))
    return [sorted(s) for s in adj]


def _assign_segments(segs, deg, n, rng):
    counts = [max(1, round(s["share"] * n)) for s in segs]
    counts[max(range(len(segs)), key=lambda k: counts[k])] += n - sum(counts)
    by_deg = sorted(range(n), key=lambda i: -deg[i])
    hub_slots = [k for k, s in enumerate(segs) if s["hub"] for _ in range(counts[k])]
    other_slots = [k for k, s in enumerate(segs) if not s["hub"] for _ in range(counts[k])]
    rest = by_deg[len(hub_slots):]
    rng.shuffle(rest)
    seg_of = [0] * n
    for node, k in zip(by_deg[:len(hub_slots)], hub_slots):
        seg_of[node] = k
    for node, k in zip(rest, other_slots):
        seg_of[node] = k
    return seg_of


def simulate(cfg, preset, events, seed, detailed=False):
    rng = random.Random(seed)
    trng = random.Random(seed * 7919 + 17)  # khusus teks/nama, agar tidak mengubah dinamika
    n, R, p = cfg["population"], cfg["rounds"], cfg["params"]
    segs = preset["segments"]
    impact = preset["impact"](p)
    contro = preset["controversy"](p)
    awareness = p.get("awareness", 10) / 100
    neg_mult, pos_mult = preset["neg_mult"](p), preset["pos_mult"](p)
    distribusi = preset.get("distribusi", False)   # orang dalam beli duluan lalu jual ke keramaian
    insider_sell_mult = preset.get("insider_sell_mult", 1.0)   # saham tipis: keluarnya lebih pelan

    adj = build_network(n, 3, rng)
    deg = [len(a) for a in adj]
    logdeg = [math.log(2 + d) for d in deg]
    seg_of = _assign_segments(segs, deg, n, rng)
    insider = [segs[seg_of[i]]["insider"] for i in range(n)]
    ritel = [segs[seg_of[i]]["ritel"] for i in range(n)]

    def jit(v, sd, lo=0.0, hi=1.0):
        return max(lo, min(hi, v + rng.gauss(0, sd)))

    stub, act, eps, loyal, sens, latent, aware, base = [], [], [], [], [], [], [], []
    for i in range(n):
        s = segs[seg_of[i]]
        stub.append(jit(s["stub"], 0.1))
        act.append(jit(s["act"], 0.04, 0.005))
        eps.append(jit(s["eps"], 0.1, 0.1))
        loyal.append(jit(s["loyal"], 0.1))
        sens.append(jit(s["sens"], 0.2, 0.0, 2.0))
        base.append(clamp(s["bias"] + rng.gauss(0, 0.1)))
        latent.append(clamp(base[i] + impact * sens[i] * (0.7 + 0.6 * rng.random())
                            + rng.gauss(0, 0.12 * (1 + contro))))
        if s["insider"]:
            aware.append(True)
        else:
            aware.append(rng.random() < (min(1.0, awareness * 1.5 + 0.2) if s["hub"] else awareness))
    op = latent[:]
    state = [""] * n
    latent0 = latent[:]
    buy_round = [None] * n
    cut = [False] * n
    insider_sell = None

    by_round = {}
    for ev in events:
        by_round.setdefault(ev["round"], []).append(ev)

    metrics = {k: [] for k in SERIES}
    metrics["attention"] = []
    metrics["seg_mean"] = []

    def snapshot(n_posts, attention, buys, sells):
        idx = [i for i in range(n) if aware[i]]
        ops = [op[i] for i in idx]
        k = len(ops)
        mean = sum(ops) / k if k else 0.0
        metrics["mean_op"].append(mean)
        metrics["pct_pos"].append(sum(1 for o in ops if o > 0.2) / k if k else 0.0)
        metrics["pct_neg"].append(sum(1 for o in ops if o < -0.2) / k if k else 0.0)
        metrics["aware"].append(k / n)
        metrics["neg_action"].append(state.count("neg") / n)
        metrics["pos_action"].append(state.count("pos") / n)
        metrics["polar"].append(math.sqrt(sum((o - mean) ** 2 for o in ops) / k) if k else 0.0)
        metrics["posts"].append(n_posts)
        metrics["buy_flow"].append(buys / n)
        metrics["sell_flow"].append(sells / n)
        metrics["attention"].append(attention)
        sm = []
        for si in range(len(segs)):
            so = [op[i] for i in idx if seg_of[i] == si]
            sm.append(sum(so) / len(so) if so else None)
        metrics["seg_mean"].append(sm)

    if detailed:
        fmt = _Fmt(kode=cfg["kode"], **{k: v for k, v in p.items()})
        names, handles, used = [], [], set()
        hub_pool = HUB_HANDLES[:]
        trng.shuffle(hub_pool)
        for i in range(n):
            if segs[seg_of[i]]["hub"] and hub_pool:
                h = hub_pool.pop()
                names.append(h.replace("_", " ").title())
            else:
                f, l = trng.choice(FIRST), trng.choice(LAST)
                names.append(f"{f} {l}")
                h = f"{f.lower()}{l[:1].lower()}{trng.randint(1, 99)}"
            while h in used:
                h += str(trng.randint(0, 9))
            used.add(h)
            handles.append(h)
        logs = [[] for _ in range(n)]
        inf_score = [0.0] * n
        posts_out = []
        op_hist = [[round(o, 2) for o in op]]
        st_hist = ["".join("u" if not aware[i] else "." for i in range(n))]

    snapshot(0, 1.0, 0, 0)
    attention = 1.0
    for t in range(1, R + 1):
        attention = max(0.2, attention * ATTENTION_DECAY)
        evs = by_round.get(t, [])
        if evs:
            attention = min(1.0, attention + 0.5)

        # 1) event
        for ev in evs:
            hit = 0
            for i in range(n):
                if not aware[i] and rng.random() < ev["aw"]:
                    aware[i] = True
                    if detailed:
                        logs[i].append({"t": t, "k": "aware", "via": ev["name"]})
            for i in range(n):
                if ev["target"] != "all" and segs[seg_of[i]]["key"] != ev["target"]:
                    continue
                f = 1 - 0.5 * stub[i]
                latent[i] = clamp(latent[i] + ev["effect"] * 0.5 * f)
                if aware[i]:
                    before = op[i]
                    op[i] = clamp(op[i] + ev["effect"] * f * (0.6 + 0.8 * rng.random()))
                    hit += 1
                    if detailed and abs(op[i] - before) > 0.005:
                        logs[i].append({"t": t, "k": "event", "d": round(op[i] - before, 3), "name": ev["name"]})
            if detailed:
                posts_out.append({"t": t, "a": -1, "s": round(ev["effect"], 2), "text": ev["name"],
                                  "rs": 0, "reach": hit, "news": True})

        # 2) posting & repost
        posts, by_author, shared_by = [], {}, {}
        for i in range(n):
            if not aware[i]:
                continue
            if rng.random() < act[i] * attention * (0.4 + 1.2 * abs(op[i])) * (1 + 0.5 * contro):
                post = [i, clamp(op[i] + rng.gauss(0, 0.1)), 0, deg[i]]
                posts.append(post)
                by_author.setdefault(i, []).append(post)
        for post in posts:
            a, s = post[0], post[1]
            for j in adj[a]:
                if aware[j] and abs(op[j] - s) < eps[j] * 0.5 and rng.random() < act[j] * attention * abs(s) * 0.8:
                    post[2] += 1
                    post[3] += deg[j]
                    shared_by.setdefault(j, []).append(post)

        # 3) update opini (sinkron)
        new_op = op[:]
        newly = []
        for i in range(n):
            seen, ids = [], set()
            for j in adj[i]:
                for post in by_author.get(j, []) + shared_by.get(j, []):
                    if id(post) not in ids:
                        ids.add(id(post))
                        seen.append(post)
            if not aware[i]:
                if seen and rng.random() < 1 - (1 - SEE_PROB) ** len(seen):
                    newly.append(i)
                    if detailed:
                        top = max(seen, key=lambda q: q[3])
                        logs[i].append({"t": t, "k": "aware", "by": top[0]})
                continue
            latent[i] += HABITUATION * (base[i] - latent[i]) * (1 - attention)
            o = op[i]
            d = 0.05 * (latent[i] - o)
            if seen and not insider[i]:
                sw = ssum = 0.0
                within, out = [], []
                for post in seen:
                    a, s = post[0], post[1]
                    if abs(s - o) <= eps[i]:
                        w = logdeg[a] * (1 + NEG_BIAS if s < 0 else 1)
                        sw += w
                        ssum += w * s
                        within.append((a, s, w))
                    else:
                        out.append(s)
                if sw > 0:
                    d += (1 - stub[i]) * (ssum / sw - o) * 0.6
                    if detailed:
                        k = (1 - stub[i]) * 0.6 / sw
                        for a, s, w in within:
                            inf_score[a] += abs(w * (s - o) * k)
                elif out:
                    d += 0.04 * (1 + contro) * (1 if o >= sum(out) / len(out) else -1)
                if detailed and abs(d) > 0.03:
                    entry = {"t": t, "k": "social", "d": round(d, 3), "n": len(seen),
                             "neg": round(sum(1 for q in seen if q[1] < -0.15) / len(seen), 2)}
                    pushers = [(a, w * abs(s - o)) for a, s, w in within if (s - o) * d > 0]
                    if pushers:
                        entry["by"] = max(pushers, key=lambda x: x[1])[0]
                    elif not within:
                        entry["backfire"] = True
                    logs[i].append(entry)
            new_op[i] = clamp(o + d)
        op = new_op
        for i in newly:
            aware[i] = True
            op[i] = latent[i]

        # 4) transaksi
        crowd = [op[i] for i in range(n) if aware[i] and not insider[i]]
        crowd_mean = sum(crowd) / len(crowd) if crowd else 0.0
        # Obrolan sudah lewat puncak: hari ini lebih sepi dari hari teramai sejauh ini.
        past_peak = t > 2 and len(posts) <= 0.9 * max(metrics["posts"])
        heat = min(1.5, 0.15 + 1.2 * attention ** 1.5)   # transaksi ikut panasnya perhatian publik
        buys = sells = 0
        for i in range(n):
            if not aware[i]:
                continue
            o, st, before = op[i], state[i], state[i]
            kind = None
            if insider[i] and distribusi:
                if st == "" and o > 0.2 and rng.random() < 0.5:
                    state[i], kind = "pos", "akumulasi"
                    buy_round[i] = t
                elif (st == "pos" and t - buy_round[i] >= 2 and past_peak and crowd_mean > 0.15
                      and rng.random() < 0.4 * insider_sell_mult):
                    state[i], kind = "neg", "distribusi"
                    if insider_sell is None:
                        insider_sell = t
                elif st == "" and o < -0.3 and rng.random() < 0.4:
                    state[i] = "neg"
            elif st == "":
                if o < -0.45 and rng.random() < 0.10 * heat * (1 - loyal[i]) * neg_mult * (-o):
                    state[i] = "neg"
                elif o > 0.45 and rng.random() < 0.10 * heat * pos_mult * o:
                    state[i] = "pos"
                    buy_round[i] = t
            elif st == "pos" and o < 0.0 and rng.random() < 0.25 * (1 - 0.5 * loyal[i]):
                state[i], kind = "neg", "cutloss"
                cut[i] = True
            elif st == "neg" and o > 0.3 and rng.random() < 0.1:
                state[i] = ""
            if state[i] != before:
                if state[i] == "pos":
                    buys += 1
                elif state[i] == "neg":
                    sells += 1
                if detailed:
                    entry = {"t": t, "k": "action", "to": state[i] or "none"}
                    if kind:
                        entry["kind"] = kind
                    logs[i].append(entry)

        snapshot(len(posts), attention, buys, sells)

        if detailed:
            tpl = preset["templates"]
            for a, s, rs, reach in posts:
                posts_out.append({"t": t, "a": a, "s": round(s, 2), "rs": rs, "reach": reach,
                                  "text": trng.choice(tpl[bucket(s)]).format_map(fmt)})
                logs[a].append({"t": t, "k": "post", "s": round(s, 2)})
            op_hist.append([round(o, 2) for o in op])
            st_hist.append("".join("u" if not aware[i] else {"": ".", "pos": "p", "neg": "n"}[state[i]]
                                   for i in range(n)))

    # Masuk telat: pembelian ritel sesudah hari obrolan paling ramai.
    peak = max(range(1, R + 1), key=lambda t: metrics["posts"][t])
    buyers = [i for i in range(n) if ritel[i] and buy_round[i] is not None]
    extra = {
        "peak_round": peak,
        "late_buy": sum(1 for i in buyers if buy_round[i] > peak) / len(buyers) if buyers else 0.0,
        "cutloss": sum(1 for i in buyers if cut[i]) / len(buyers) if buyers else 0.0,
        "ritel_buyers": len(buyers) / max(1, sum(ritel)),
        "insider_sell_round": insider_sell,
    }
    result = {"metrics": metrics, "final_seg": _final_seg(segs, seg_of, op, aware, state, n), "extra": extra}
    if detailed:
        result["detail"] = {
            "agents": [{"id": i, "name": names[i], "handle": handles[i], "seg": seg_of[i], "deg": deg[i],
                        "stub": round(stub[i], 2), "eps": round(eps[i], 2), "loyal": round(loyal[i], 2),
                        "act": round(act[i], 3), "sens": round(sens[i], 2), "latent0": round(latent0[i], 2),
                        "inf": round(inf_score[i], 2), "log": logs[i]} for i in range(n)],
            "edges": [[i, j] for i in range(n) for j in adj[i] if i < j],
            "ops": op_hist,
            "states": st_hist,
            "posts": posts_out,
        }
    return result


def _final_seg(segs, seg_of, op, aware, state, n):
    out = {}
    for si, s in enumerate(segs):
        members = [i for i in range(n) if seg_of[i] == si]
        aw = [i for i in members if aware[i]]
        m = len(members) or 1
        out[s["key"]] = {
            "op": sum(op[i] for i in aw) / len(aw) if aw else 0.0,
            "neg": sum(1 for i in members if state[i] == "neg") / m,
            "pos": sum(1 for i in members if state[i] == "pos") / m,
            "aware": len(aw) / m,
            "size": len(members),
        }
    return out


def _quantile(sorted_vals, q):
    if not sorted_vals:
        return 0.0
    k = (len(sorted_vals) - 1) * q
    lo = int(k)
    hi = min(lo + 1, len(sorted_vals) - 1)
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * (k - lo)


def aggregate(runs):
    R = len(runs[0]["metrics"]["mean_op"])
    agg = {}
    for key in SERIES:
        band = {"p10": [], "p50": [], "p90": []}
        for t in range(R):
            vals = sorted(r["metrics"][key][t] for r in runs)
            for q, name in ((0.1, "p10"), (0.5, "p50"), (0.9, "p90")):
                band[name].append(round(_quantile(vals, q), 4))
        agg[key] = band
    agg["final_seg"] = {
        k: {f: _quantile(sorted(r["final_seg"][k][f] for r in runs), 0.5)
            for f in ("op", "neg", "pos", "aware", "size")}
        for k in runs[0]["final_seg"]
    }
    ex = {}
    for f in ("late_buy", "cutloss", "ritel_buyers", "peak_round"):
        vals = sorted(r["extra"][f] for r in runs)
        ex[f] = {"p10": _quantile(vals, 0.1), "p50": _quantile(vals, 0.5), "p90": _quantile(vals, 0.9)}
    sells = sorted(r["extra"]["insider_sell_round"] for r in runs if r["extra"]["insider_sell_round"] is not None)
    ex["insider_sell_share"] = len(sells) / len(runs)
    ex["insider_sell_round"] = round(_quantile(sells, 0.5)) if sells else None
    agg["extra"] = ex
    return agg


def run_batch(cfg, preset, events, runs, base_seed, first=None):
    results = [first] if first else []
    for k in range(len(results), runs):
        results.append(simulate(cfg, preset, events, base_seed + k))
    return aggregate(results)
