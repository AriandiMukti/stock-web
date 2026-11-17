"""
Sebaran Kabar -- simulasi bagaimana satu kabar tentang emiten menyebar di
komunitas investor (Stockbit, Telegram, grup), siapa yang ikut beli, siapa
yang telat, dan kapan orang dalam keluar. Tanpa AI/LLM: model berbasis agen
dengan aturan, diulang beberapa kali (Monte Carlo).

Pelengkap Digital Twin (website/twin/): Twin menjawab efek ke HARGA dan
order book; modul ini menjawab bagaimana NARASI-nya menyebar.

Isi paket:
    skenario.py  segmen pelaku, jenis kabar, data emiten (Ramai Dibahas, KSEI, Summary)
    engine.py    simulasi hari demi hari + Monte Carlo
    laporan.py   laporan berbasis aturan

Dipanggil dari views.py: /sebaran-kabar, /sebaran-kabar/konteks, /sebaran-kabar/jalankan.
"""
from .engine import clamp, run_batch, simulate
from .laporan import build_report
from .skenario import KABAR, bangun_preset, daftar_kabar, konteks_emiten

__all__ = ["daftar_kabar", "konteks_emiten", "jalankan"]


def _sanitize(raw):
    from ..models import stockList

    kabar = KABAR.get(raw.get("kabar")) or KABAR["rumor"]
    params = {}
    for spec in kabar["params"]:
        try:
            v = float((raw.get("params") or {}).get(spec["key"], spec["default"]))
        except (TypeError, ValueError):
            v = spec["default"]
        v = max(spec["min"], min(spec["max"], v))
        params[spec["key"]] = int(v) if float(v).is_integer() else v

    def num(key, default, lo, hi):
        try:
            return int(max(lo, min(hi, int(raw.get(key, default)))))
        except (TypeError, ValueError):
            return default

    kode = "".join(ch for ch in str(raw.get("kode") or "").upper() if ch.isalnum())[:6]
    if kode not in stockList:
        kode = "BBRI"
    cfg = {
        "kabar": kabar["key"], "kode": kode, "params": params,
        "population": num("population", 400, 100, 1000),
        "rounds": num("rounds", 20, 5, 60),
        "runs": num("runs", 12, 1, 30),
        "seed": num("seed", 42, 0, 10 ** 9),
        "profil": raw.get("profil", True) is not False,
    }
    try:
        konteks = konteks_emiten(kode)
    except Exception:
        konteks = None
    profil = (konteks or {}).get("profil") if cfg["profil"] else None
    preset = bangun_preset(kabar, params, profil)
    seg_keys = {s["key"] for s in preset["segments"]}
    events = []
    for e in (raw.get("events") or [])[:8]:
        try:
            events.append({
                "round": int(max(1, min(cfg["rounds"], int(e.get("round", 1))))),
                "name": str(e.get("name") or "Event")[:80],
                "effect": clamp(float(e.get("effect", 0))),
                "target": e.get("target") if e.get("target") in seg_keys else "all",
                "aw": clamp(float(e.get("aw", 0.1)), 0.0, 1.0),
            })
        except (TypeError, ValueError):
            continue
    events.sort(key=lambda e: e["round"])
    return cfg, preset, events, konteks


def jalankan(raw):
    """Satu permintaan dari halaman -> hasil lengkap siap-JSON (~1-3 detik untuk 400 agen x 12 run)."""
    cfg, preset, events, konteks = _sanitize(raw)
    seed = cfg["seed"]
    shown = simulate(cfg, preset, events, seed, detailed=True)
    main = run_batch(cfg, preset, events, cfg["runs"], seed, first=shown)

    # Dampak tiap event: dunia yang sama (seed sama) tanpa event itu.
    effects = []
    runs = max(4, min(cfg["runs"], 10))
    for idx, ev in enumerate(events):
        others = [e for k, e in enumerate(events) if k != idx]
        effects.append({"event": ev, "without": run_batch(cfg, preset, others, runs, seed)})

    return {
        "config": cfg,
        "events": events,
        "preset": {"key": preset["key"], "label": preset["label"], "neg_label": "Jual", "pos_label": "Beli",
                   "asumsi": preset["asumsi"],
                   "segments": [{"key": s["key"], "label": s["label"], "hub": s["hub"], "insider": s["insider"],
                                 "share": round(s["share"], 3)} for s in preset["segments"]]},
        "agg": main,
        "shown_metrics": shown["metrics"],
        "detail": shown["detail"],
        "report": build_report(cfg, preset, events, main, effects, shown, konteks),
    }
