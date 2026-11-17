#!/usr/bin/env python3
"""
GA untuk tuning strategi trading saham
======================================

Strategi (long-only, cocok untuk saham Indonesia yang umumnya tidak bisa short):
  BELI : MA cepat di atas MA lambat (tren naik) DAN RSI di bawah "RSI maks"
         (supaya tidak membeli saat harga sudah terlalu panas).
  JUAL : MA cepat turun ke bawah MA lambat (tren patah), ATAU harga turun
         sebesar "stop-loss" dari harga beli.
  Setelah kena stop-loss, tunggu golden cross berikutnya sebelum beli lagi.
  Sinyal dihitung dari harga penutupan, transaksi dieksekusi di harga
  pembukaan HARI BERIKUTNYA, jadi tidak ada "mengintip masa depan".

Lima parameter yang dicari GA:
  MA cepat 5-50 hari, MA lambat 20-150 hari, periode RSI 5-30,
  RSI maks saat beli 50-90, stop-loss 3%-20%.

Fitness = Sharpe ratio tahunan SETELAH biaya transaksi, dikurangi penalti
kalau jumlah transaksinya terlalu sedikit (hasil dari 1-2 transaksi saja
belum bisa dipercaya).

Empat uji yang dijalankan:
  1. Latih di data lama, uji di data baru yang tidak pernah dilihat GA.
  2. Kestabilan: parameter terbaik digeser +/-10%. Pola yang nyata tidak
     hancur hanya karena parameternya sedikit berubah.
  3. Walk-forward: optimasi ulang tiap jendela waktu, lalu rangkai hanya
     hasil ujinya. Ini simulasi paling jujur dari pemakaian sungguhan.
  4. Kontrol data acak: urutan hari diacak sehingga semua pola waktu hilang,
     lalu GA dijalankan lagi. Kalau GA tetap "menemukan" strategi bagus di
     data acak, hasil bagus di data latih belum membuktikan apa-apa.

Cara pakai:
  pip install numpy pandas matplotlib yfinance
  python ga_tuning_trading.py                      # BBCA.JK dari Yahoo Finance
  python ga_tuning_trading.py --ticker TLKM.JK     # saham lain
  python ga_tuning_trading.py --csv harga.csv      # CSV sendiri: kolom Date, Open, Close
  python ga_tuning_trading.py --demo               # data contoh offline (GOOG 2004-2008)

Format CSV: tanggal YYYY-MM-DD, angka tanpa pemisah ribuan, harga sudah
disesuaikan (adjusted) untuk stock split.

Hasil: ringkasan di layar + grafik hasil_ga_trading.png.
Biaya transaksi, rentang parameter, dan pengaturan GA bisa diubah di
bagian PENGATURAN di bawah.

Ini alat riset dan belajar, bukan saran investasi.
"""

import argparse
import math
import sys
import time

import numpy as np
import pandas as pd
import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import matplotlib.transforms as mtransforms  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.ticker import FuncFormatter, MaxNLocator  # noqa: E402

try:
    sys.stdout.reconfigure(errors="replace")
except Exception:
    pass


# ======================================================================
# PENGATURAN
# ======================================================================

# Biaya per transaksi (contoh umum di BEI; sesuaikan dengan broker Anda).
FEE_BUY = 0.0015      # fee beli 0,15%
FEE_SELL = 0.0025     # fee jual 0,25% (biasanya sudah termasuk PPh final 0,1%)
SLIPPAGE = 0.0005     # selisih harga eksekusi 0,05% per transaksi
COST_BUY = FEE_BUY + SLIPPAGE
COST_SELL = FEE_SELL + SLIPPAGE

# Ruang pencarian GA: (nama, label, minimum, maksimum, bilangan bulat?)
PARAM_SPACE = [
    ("ma_fast", "MA cepat", 5, 50, True),
    ("ma_slow", "MA lambat", 20, 150, True),
    ("rsi_period", "Periode RSI", 5, 30, True),
    ("rsi_max", "RSI maks saat beli", 50, 90, True),
    ("stop_loss", "Stop-loss", 0.03, 0.20, False),
]
MIN_MA_GAP = 5          # MA lambat minimal 5 hari lebih panjang dari MA cepat

# Pengaturan GA
POP_SIZE = 50           # jumlah individu (kombinasi parameter) per generasi
GENERATIONS = 40        # jumlah generasi
TOURNAMENT_K = 3        # ukuran turnamen saat memilih induk
CROSSOVER_RATE = 0.9    # peluang dua induk dikawinkan
MUTATION_RATE = 0.2     # peluang tiap gen bermutasi
MUTATION_SCALE = 0.15   # besar mutasi, relatif terhadap rentang gen
ELITE = 2               # individu terbaik yang langsung lolos ke generasi berikut
MIN_TRADES_PER_YEAR = 2 # di bawah ini fitness dipotong penalti
TRADE_PENALTY = 1.0     # potongan Sharpe maksimum (kalau tidak ada transaksi sama sekali)

# Pengaturan uji
N_NEIGHBORS = 200       # jumlah variasi parameter untuk uji kestabilan
NEIGHBOR_STEP = 0.10    # besar pergeseran parameter (10%)
N_SHUFFLES = 5          # berapa kali data diacak untuk uji kontrol

NAMES = [p[0] for p in PARAM_SPACE]
SPEC = {p[0]: p for p in PARAM_SPACE}
WARMUP = max(SPEC["ma_slow"][3], SPEC["rsi_period"][3]) + 1  # hari pemanasan indikator


# ======================================================================
# FORMAT ANGKA (gaya Indonesia: 1.234,5)
# ======================================================================

BULAN = ["Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agu", "Sep", "Okt", "Nov", "Des"]


def _indo(s):
    return s.replace(",", "#").replace(".", ",").replace("#", ".")


def _missing(x):
    return x is None or (isinstance(x, float) and math.isnan(x))


def fnum(x, d=2):
    return "-" if _missing(x) else _indo(f"{x:,.{d}f}")


def fpct(x, d=1, sign=True):
    if _missing(x):
        return "-"
    return _indo(f"{x * 100:{'+' if sign else ''},.{d}f}%")


def fdate(d):
    return pd.Timestamp(d).strftime("%Y-%m-%d")


def fval(name, v):
    return fpct(v, 1, sign=False) if name == "stop_loss" else str(int(v))


def describe(p):
    return (f"MA {p['ma_fast']}/{p['ma_slow']}, RSI({p['rsi_period']}) < {p['rsi_max']}, "
            f"stop-loss {fpct(p['stop_loss'], 1, sign=False)}")


def header(title):
    print("\n" + "=" * 74 + f"\n{title}\n" + "=" * 74)


# ======================================================================
# DATA
# ======================================================================

def clean(df):
    df = df[["Open", "Close"]].apply(pd.to_numeric, errors="coerce").dropna()
    df = df[(df["Open"] > 0) & (df["Close"] > 0)]
    return df[~df.index.duplicated(keep="last")].sort_index()


def load_demo():
    """Harga harian GOOG 2004-2008 yang ikut terpasang bersama matplotlib."""
    from matplotlib import cbook
    r = cbook.get_sample_data("goog.npz")["price_data"]
    df = pd.DataFrame({"Open": r["open"], "Close": r["close"]}, index=pd.to_datetime(r["date"]))
    return clean(df), "GOOG 2004-2008 (data contoh offline)"


def load_yahoo(ticker, start):
    try:
        import yfinance as yf
    except ImportError:
        sys.exit("Paket yfinance belum terpasang. Jalankan: pip install yfinance")
    df = yf.download(ticker, start=start, auto_adjust=True, progress=False)
    if df is None or df.empty:
        sys.exit(f"Data {ticker} gagal diunduh. Cek kode saham (contoh: BBCA.JK) dan koneksi internet.")
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df.index = pd.to_datetime(df.index)
    if df.index.tz is not None:
        df.index = df.index.tz_localize(None)
    return clean(df), f"{ticker} (Yahoo Finance)"


def load_csv(path):
    raw = pd.read_csv(path)
    cols = {c.strip().lower(): c for c in raw.columns}

    def pick(*names):
        return next((cols[n] for n in names if n in cols), None)

    dcol = pick("date", "tanggal", "datetime", "time")
    ccol = pick("close", "penutupan", "tutup", "terakhir", "adj close", "adj_close")
    ocol = pick("open", "pembukaan", "buka")
    if dcol is None or ccol is None:
        sys.exit("CSV harus punya kolom tanggal (Date) dan harga penutupan (Close).")
    df = pd.DataFrame({"Close": raw[ccol].to_numpy()}, index=pd.to_datetime(raw[dcol]))
    if ocol is not None:
        df["Open"] = raw[ocol].to_numpy()
    else:
        print("Catatan: kolom Open tidak ada, transaksi dieksekusi di harga penutupan hari sinyal.")
        df = df.sort_index()
        df["Open"] = df["Close"].shift(1)
    return clean(df), path


class Market:
    """Harga + semua indikator. Dihitung sekali di awal supaya GA cepat."""

    def __init__(self, df):
        self.dates = df.index
        self.n = len(df)
        self.open = df["Open"].tolist()
        self.close = df["Close"].tolist()
        years = (df.index[-1] - df.index[0]).days / 365.25
        self.dpy = self.n / years  # hari bursa per tahun (BEI sekitar 240-245)

        close = df["Close"]
        self.sma = {p: close.rolling(p).mean().tolist()
                    for p in range(SPEC["ma_fast"][2], SPEC["ma_slow"][3] + 1)}

        delta = close.diff()
        gain, loss = delta.clip(lower=0), -delta.clip(upper=0)
        self.rsi = {}
        for p in range(SPEC["rsi_period"][2], SPEC["rsi_period"][3] + 1):
            avg_gain = gain.ewm(alpha=1 / p, adjust=False, min_periods=p).mean()  # rata-rata Wilder
            avg_loss = loss.ewm(alpha=1 / p, adjust=False, min_periods=p).mean()
            rsi = 100 - 100 / (1 + avg_gain / avg_loss)
            rsi[(avg_gain == 0) & (avg_loss == 0)] = 50.0
            self.rsi[p] = rsi.tolist()


def shuffled(df, rng):
    """Acak urutan hari. Tiap hari membawa gap semalam dan gerak intraday aslinya,
    jadi distribusi return sama persis, tapi semua pola urutan waktu hilang."""
    o = df["Open"].to_numpy(float)
    c = df["Close"].to_numpy(float)
    gap = o[1:] / c[:-1]          # pembukaan hari ini / penutupan kemarin
    intraday = c[1:] / o[1:]      # penutupan / pembukaan hari yang sama
    idx = rng.permutation(len(gap))
    gap, intraday = gap[idx], intraday[idx]
    new_c = c[0] * np.concatenate([[1.0], np.cumprod(gap * intraday)])
    new_o = np.concatenate([[o[0]], new_c[:-1] * gap])
    return pd.DataFrame({"Open": new_o, "Close": new_c}, index=df.index)


# ======================================================================
# BACKTEST
# ======================================================================

def run_strategy(m, p, start, end, log=None):
    """Jalankan strategi dari indeks start s.d. end-1. Mulai tanpa posisi,
    dan posisi yang masih terbuka ditutup di akhir periode (bayar biaya jual).
    Hasil: return harian, return per transaksi, porsi waktu di pasar."""
    fast, slow = m.sma[p["ma_fast"]], m.sma[p["ma_slow"]]
    rsi, rsi_max = m.rsi[p["rsi_period"]], p["rsi_max"]
    sl_level = 1.0 - p["stop_loss"]
    o, c = m.open, m.close
    keep_buy, keep_sell = 1.0 - COST_BUY, 1.0 - COST_SELL

    rets = [0.0] * (end - start)
    trades = []
    in_pos, armed, pending, reason = False, True, 0, ""
    entry_px = growth = 0.0
    days_exposed = 0

    for i in range(end - start):
        t = start + i
        # 1) Eksekusi order kemarin di harga pembukaan hari ini
        if pending == 1:
            in_pos, entry_px = True, o[t]
            growth = c[t] / o[t] * keep_buy
            rets[i] = growth - 1.0
            days_exposed += 1
            if log is not None:
                log.append((t, "beli", o[t], ""))
        elif pending == -1:
            in_pos = False
            g = o[t] / c[t - 1] * keep_sell
            rets[i] = g - 1.0
            growth *= g
            trades.append(growth - 1.0)
            days_exposed += 1
            if log is not None:
                log.append((t, "jual", o[t], reason))
        elif in_pos:
            g = c[t] / c[t - 1]
            rets[i] = g - 1.0
            growth *= g
            days_exposed += 1
        pending = 0

        # 2) Baca sinyal di harga penutupan hari ini (dieksekusi besok pagi)
        if in_pos:
            if c[t] <= entry_px * sl_level:
                pending, armed, reason = -1, False, "stop-loss"
            elif fast[t] < slow[t]:
                pending, reason = -1, "tren patah"
        elif fast[t] < slow[t]:
            armed = True  # tren sudah reset, boleh beli lagi di golden cross berikutnya
        elif armed and fast[t] > slow[t] and rsi[t] < rsi_max:
            pending = 1

    if in_pos:  # tutup posisi di akhir periode
        rets[-1] = (1.0 + rets[-1]) * keep_sell - 1.0
        growth *= keep_sell
        trades.append(growth - 1.0)
        if log is not None:
            log.append((end - 1, "jual", c[end - 1], "akhir periode"))
    return rets, trades, days_exposed / (end - start)


def buy_and_hold(m, start, end):
    """Beli di pembukaan hari pertama, jual di penutupan hari terakhir."""
    o, c = m.open, m.close
    rets = [c[t] / c[t - 1] - 1.0 for t in range(start, end)]
    rets[0] = c[start] / o[start] * (1.0 - COST_BUY) - 1.0
    rets[-1] = (1.0 + rets[-1]) * (1.0 - COST_SELL) - 1.0
    return rets


def sharpe(rets, dpy):
    r = np.asarray(rets, float)
    sd = r.std(ddof=1)
    return float(r.mean() / sd * math.sqrt(dpy)) if sd > 1e-12 else 0.0


def stats(rets, trades, exposure, dpy):
    r = np.asarray(rets, float)
    eq = np.concatenate([[1.0], np.cumprod(1.0 + r)])
    return dict(
        total=eq[-1] - 1.0,
        cagr=eq[-1] ** (dpy / len(r)) - 1.0 if eq[-1] > 0 else -1.0,
        sharpe=sharpe(r, dpy),
        mdd=float((eq / np.maximum.accumulate(eq) - 1.0).min()),
        trades=None if trades is None else len(trades),
        win=float(np.mean(np.asarray(trades) > 0)) if trades else float("nan"),
        exposure=exposure,
    )


# ======================================================================
# GENETIC ALGORITHM
# ======================================================================

def to_params(genome):
    return dict(zip(NAMES, genome))


def repair(genome):
    """Bulatkan, jepit ke rentang yang diizinkan, dan pastikan MA cepat < MA lambat."""
    g = list(genome)
    for k, (_, _, lo, hi, is_int) in enumerate(PARAM_SPACE):
        v = min(max(g[k], lo), hi)
        g[k] = int(round(v)) if is_int else round(float(v), 3)
    f, s = NAMES.index("ma_fast"), NAMES.index("ma_slow")
    if g[f] >= g[s]:
        g[f], g[s] = g[s], g[f]
    if g[s] - g[f] < MIN_MA_GAP:
        g[s] = min(SPEC["ma_slow"][3], g[f] + MIN_MA_GAP)
    return tuple(g)


def random_genome(rng):
    return repair([rng.integers(lo, hi + 1) if is_int else rng.uniform(lo, hi)
                   for (_, _, lo, hi, is_int) in PARAM_SPACE])


def tournament(pop, fit, rng):
    idx = rng.integers(0, len(pop), TOURNAMENT_K)
    return pop[max(idx, key=lambda i: fit[i])]


def crossover(a, b, rng):
    """Uniform crossover: tiap gen anak diwarisi dari salah satu induk secara acak."""
    return repair([a[k] if rng.random() < 0.5 else b[k] for k in range(len(a))])


def mutate(genome, rng):
    g = list(genome)
    for k, (_, _, lo, hi, _) in enumerate(PARAM_SPACE):
        if rng.random() < MUTATION_RATE:
            g[k] += rng.normal(0.0, MUTATION_SCALE * (hi - lo))
    return repair(g)


def genetic_algorithm(m, start, end, seed, verbose=False):
    """Cari parameter dengan fitness tertinggi di data [start, end)."""
    rng = np.random.default_rng(seed)
    need = max(3, round(MIN_TRADES_PER_YEAR * (end - start) / m.dpy))
    cache = {}

    def fitness(genome):
        if genome not in cache:
            rets, trades, _ = run_strategy(m, to_params(genome), start, end)
            shortfall = max(0, need - len(trades)) / need
            cache[genome] = sharpe(rets, m.dpy) - TRADE_PENALTY * shortfall
        return cache[genome]

    pop = [random_genome(rng) for _ in range(POP_SIZE)]
    history = []
    for gen in range(1, GENERATIONS + 1):
        fit = [fitness(g) for g in pop]
        history.append((max(fit), float(np.median(fit))))
        if verbose and (gen == 1 or gen % 10 == 0):
            print(f"  Generasi {gen:>2}: fitness terbaik {fnum(max(fit)):>6} | median populasi {fnum(float(np.median(fit))):>6}")
        if gen == GENERATIONS:
            break
        order = sorted(range(len(pop)), key=lambda i: fit[i], reverse=True)
        nxt = [pop[i] for i in order[:ELITE]]          # elitisme
        while len(nxt) < POP_SIZE:
            a, b = tournament(pop, fit, rng), tournament(pop, fit, rng)
            child = crossover(a, b, rng) if rng.random() < CROSSOVER_RATE else a
            nxt.append(mutate(child, rng))
        pop = nxt

    best = max(cache, key=cache.get)
    return to_params(best), history, len(cache), need


# ======================================================================
# UJI-UJI
# ======================================================================

ROWS = [
    ("Return total", "total", fpct),
    ("Return per tahun", "cagr", fpct),
    ("Sharpe ratio", "sharpe", fnum),
    ("Max drawdown", "mdd", fpct),
    ("Jumlah transaksi", "trades", lambda v: "-" if v is None else str(v)),
    ("Win rate", "win", lambda v: fpct(v, 0, sign=False)),
    ("Waktu di pasar", "exposure", lambda v: fpct(v, 0, sign=False)),
]


def print_table(columns):
    w = max(13, max(len(h) for h, _ in columns) + 2)
    print("  " + " " * 18 + "".join(f"{h:>{w}}" for h, _ in columns))
    for label, key, f in ROWS:
        print("  " + f"{label:<18}" + "".join(f"{f(s[key]):>{w}}" for _, s in columns))


def print_trades(m, log, trades, limit=10):
    print(f"\n  Transaksi di data uji ({len(trades)} kali):")
    k = shown = 0
    for t, act, px, why in log:
        if act == "beli":
            if shown >= limit:
                break
            print(f"    {fdate(m.dates[t])}  beli @ {fnum(px):>9}")
        else:
            print(f"    {fdate(m.dates[t])}  jual @ {fnum(px):>9}  {fpct(trades[k]):>7}  ({why})")
            k += 1
            shown += 1
    if len(trades) > shown:
        print(f"    ... dan {len(trades) - shown} transaksi lainnya")


def walk_forward(m, start, train_len, test_len, seed):
    windows, rets, trades, exposed = [], [], [], 0.0
    s, k = start, 0
    min_test = max(20, test_len // 3)
    while s + train_len + min_test <= m.n:
        te0 = s + train_len
        te1 = min(te0 + test_len, m.n)
        best, _, _, _ = genetic_algorithm(m, s, te0, seed + 1 + k)
        r, tr, ex = run_strategy(m, best, te0, te1)
        bh = buy_and_hold(m, te0, te1)
        windows.append(dict(te0=te0, te1=te1, params=best, trades=len(tr),
                            ret=float(np.prod(1 + np.asarray(r)) - 1),
                            bh=float(np.prod(1 + np.asarray(bh)) - 1)))
        rets += r
        trades += tr
        exposed += ex * (te1 - te0)
        s, k = s + test_len, k + 1
    return windows, rets, trades, exposed / max(1, len(rets))


def main():
    ap = argparse.ArgumentParser(description="GA untuk tuning strategi trading saham")
    src = ap.add_mutually_exclusive_group()
    src.add_argument("--ticker", help="kode saham Yahoo Finance, contoh BBCA.JK (default)")
    src.add_argument("--csv", help="file CSV dengan kolom Date, Open, Close")
    src.add_argument("--demo", action="store_true", help="data contoh offline (GOOG 2004-2008)")
    ap.add_argument("--start", default="2010-01-01", help="tanggal awal data Yahoo (default 2010-01-01)")
    ap.add_argument("--train-frac", type=float, help="porsi data latih (default 0.7, atau 0.6 untuk data < 8 tahun)")
    ap.add_argument("--wf-train-years", type=float, help="panjang jendela latih walk-forward, dalam tahun")
    ap.add_argument("--wf-test-months", type=float, help="panjang jendela uji walk-forward, dalam bulan")
    ap.add_argument("--shuffles", type=int, default=N_SHUFFLES, help="jumlah data acak untuk uji kontrol")
    ap.add_argument("--seed", type=int, default=42, help="seed acak, supaya hasil bisa diulang")
    ap.add_argument("--out", default="hasil_ga_trading.png", help="nama file grafik")
    args = ap.parse_args()
    t_start = time.time()

    # ---------------- Data ----------------
    if args.demo:
        df, name = load_demo()
    elif args.csv:
        df, name = load_csv(args.csv)
    else:
        df, name = load_yahoo(args.ticker or "BBCA.JK", args.start)
    m = Market(df)
    eval_days = m.n - WARMUP
    if eval_days < 2.5 * m.dpy:
        sys.exit("Data terlalu pendek. Butuh minimal sekitar 3 tahun data harian.")
    long_data = eval_days / m.dpy >= 8
    train_frac = args.train_frac or (0.7 if long_data else 0.6)
    wf_train_years = args.wf_train_years or (3.0 if long_data else 1.5)
    wf_test_months = args.wf_test_months or (12 if long_data else 3)
    wf_train = int(round(wf_train_years * m.dpy))
    wf_test = int(round(wf_test_months / 12 * m.dpy))
    split = WARMUP + int(eval_days * train_frac)

    header("DATA")
    print(f"  Sumber     : {name}")
    print(f"  Periode    : {fdate(m.dates[0])} s.d. {fdate(m.dates[-1])} ({m.n} hari bursa)")
    print(f"  Pemanasan  : {WARMUP} hari pertama hanya dipakai untuk menghitung indikator")
    print(f"  Data latih : {fdate(m.dates[WARMUP])} s.d. {fdate(m.dates[split - 1])} ({split - WARMUP} hari)")
    print(f"  Data uji   : {fdate(m.dates[split])} s.d. {fdate(m.dates[-1])} ({m.n - split} hari)")
    print(f"  Biaya      : beli {fpct(COST_BUY, 2, False)}, jual {fpct(COST_SELL, 2, False)} (termasuk slippage)")

    # ---------------- 1. GA di data latih, uji di data baru ----------------
    header("1. GA MENCARI PARAMETER DI DATA LATIH, LALU DIUJI DI DATA BARU")
    best, history, n_eval, need = genetic_algorithm(m, WARMUP, split, args.seed, verbose=True)
    print(f"  {n_eval} kombinasi parameter dievaluasi (penalti jika kurang dari {need} transaksi)")
    print(f"\n  Parameter terbaik: {describe(best)}\n")
    tr_rets, tr_trades, tr_exp = run_strategy(m, best, WARMUP, split)
    te_log = []
    te_rets, te_trades, te_exp = run_strategy(m, best, split, m.n, log=te_log)
    bh_tr, bh_te = buy_and_hold(m, WARMUP, split), buy_and_hold(m, split, m.n)
    s_tr, s_te = stats(tr_rets, tr_trades, tr_exp, m.dpy), stats(te_rets, te_trades, te_exp, m.dpy)
    b_tr, b_te = stats(bh_tr, None, 1.0, m.dpy), stats(bh_te, None, 1.0, m.dpy)
    print_table([("Latih: GA", s_tr), ("Latih: B&H", b_tr), ("Uji: GA", s_te), ("Uji: B&H", b_te)])
    print("  (B&H = beli-dan-tahan)")
    print_trades(m, te_log, te_trades)

    # ---------------- 2. Kestabilan ----------------
    header("2. KESTABILAN: PARAMETER TERBAIK DIGESER +/-10% (DI DATA LATIH)")
    base = s_tr["sharpe"]
    print(f"  Sharpe parameter terbaik: {fnum(base)}\n")
    for nm in NAMES:
        out = []
        for sgn in (-1, 1):
            q = dict(best)
            q[nm] = best[nm] * (1 + sgn * NEIGHBOR_STEP)
            q = to_params(repair([q[k] for k in NAMES]))
            out.append(f"{fval(nm, q[nm]):>6} -> Sharpe {fnum(sharpe(run_strategy(m, q, WARMUP, split)[0], m.dpy)):>5}")
        print(f"  {SPEC[nm][1]:<20} -10%: {out[0]}   +10%: {out[1]}")
    rng = np.random.default_rng(args.seed + 1000)
    nb_train = []
    for _ in range(N_NEIGHBORS):
        q = to_params(repair([best[k] * (1 + rng.uniform(-NEIGHBOR_STEP, NEIGHBOR_STEP)) for k in NAMES]))
        nb_train.append(sharpe(run_strategy(m, q, WARMUP, split)[0], m.dpy))
    nb_train = np.array(nb_train)
    nb_med = float(np.median(nb_train))
    nb_share = float(np.mean(nb_train >= 0.5 * base)) if base > 0 else 0.0
    stable = base > 0 and nb_med >= 0.5 * base
    print(f"\n  {N_NEIGHBORS} variasi acak (semua parameter digeser sekaligus, maks 10%):")
    print(f"  median Sharpe {fnum(nb_med)}, 10% terburuk di bawah {fnum(float(np.percentile(nb_train, 10)))}, "
          f"{fpct(nb_share, 0, False)} variasi masih >= separuh Sharpe terbaik")

    # ---------------- 3. Walk-forward ----------------
    header(f"3. WALK-FORWARD: LATIH {fnum(wf_train_years, 1)} TAHUN, UJI {fnum(wf_test_months, 0)} BULAN BERIKUTNYA, GESER, ULANGI")
    wins, wf_rets, wf_trades, wf_exp = walk_forward(m, WARMUP, wf_train, wf_test, args.seed)
    print(f"  {'#':>2}  {'Periode uji':<28}{'Parameter pilihan GA':<34}{'Strategi':>9}{'B&H':>9}")
    for k, w in enumerate(wins, 1):
        p = w["params"]
        par = f"MA {p['ma_fast']}/{p['ma_slow']}, RSI({p['rsi_period']})<{p['rsi_max']}, SL {fpct(p['stop_loss'], 1, False)}"
        per = f"{fdate(m.dates[w['te0']])} s.d. {fdate(m.dates[w['te1'] - 1])}"
        print(f"  {k:>2}  {per:<28}{par:<34}{fpct(w['ret']):>9}{fpct(w['bh']):>9}")
    wf0, wf1 = wins[0]["te0"], wins[-1]["te1"]
    wf_bh = buy_and_hold(m, wf0, wf1)
    s_wf, b_wf = stats(wf_rets, wf_trades, wf_exp, m.dpy), stats(wf_bh, None, 1.0, m.dpy)
    print()
    print_table([("Walk-fwd: GA", s_wf), ("Walk-fwd: B&H", b_wf)])

    # ---------------- 4. Kontrol data acak ----------------
    header("4. KONTROL: GA DIJALANKAN DI DATA YANG URUTAN HARINYA DIACAK")
    print("  Di data acak tidak ada pola apa pun. Sharpe yang 'ditemukan' GA di sini murni kebetulan.\n")
    rng = np.random.default_rng(args.seed + 2000)
    shuf = []
    for i in range(args.shuffles):
        ms = Market(shuffled(df, rng))
        b, _, _, _ = genetic_algorithm(ms, WARMUP, split, args.seed + 3000 + i)
        a = sharpe(run_strategy(ms, b, WARMUP, split)[0], ms.dpy)
        c = sharpe(run_strategy(ms, b, split, ms.n)[0], ms.dpy)
        shuf.append((a, c))
        print(f"  Data acak #{i + 1}  : Sharpe latih {fnum(a):>5} | Sharpe uji {fnum(c):>5}")
    print(f"  Data asli      : Sharpe latih {fnum(s_tr['sharpe']):>5} | Sharpe uji {fnum(s_te['sharpe']):>5}")
    shuf_max = max(a for a, _ in shuf) if shuf else float("nan")

    # ---------------- Kesimpulan ----------------
    header("KESIMPULAN OTOMATIS")
    checks = [
        (s_te["sharpe"] > b_te["sharpe"],
         f"Data uji      : Sharpe strategi {fnum(s_te['sharpe'])} vs beli-dan-tahan {fnum(b_te['sharpe'])}"),
        (stable,
         f"Kestabilan    : median Sharpe variasi {fnum(nb_med)} vs parameter terbaik {fnum(base)}"),
        (s_wf["sharpe"] > b_wf["sharpe"],
         f"Walk-forward  : Sharpe strategi {fnum(s_wf['sharpe'])} vs beli-dan-tahan {fnum(b_wf['sharpe'])}"),
        (bool(shuf) and s_tr["sharpe"] > shuf_max,
         f"Data acak     : Sharpe latih data asli {fnum(s_tr['sharpe'])} vs tertinggi di data acak {fnum(shuf_max)}"),
    ]
    for ok, text in checks:
        print(f"  [{'LULUS' if ok else 'GAGAL'}] {text}")
    n_ok = sum(ok for ok, _ in checks)
    if n_ok == len(checks):
        print("\n  Lulus semua uji. Layak diteliti lebih lanjut: uji di saham dan periode lain, lalu paper trading.")
    else:
        print(f"\n  Lulus {n_ok} dari {len(checks)} uji. Belum ada bukti kuat bahwa strategi ini punya keunggulan nyata.")

    make_chart(args.out, name, m, dict(
        best=best, split=split, history=history, tr_rets=tr_rets, te_rets=te_rets, bh_tr=bh_tr, bh_te=bh_te,
        nb_train=nb_train, base=base, wins=wins, wf_rets=wf_rets, wf_bh=wf_bh, shuf=shuf,
        real=(s_tr["sharpe"], s_te["sharpe"]), wf_label=(wf_train_years, wf_test_months)))
    print(f"\n  Grafik disimpan: {args.out}")
    print(f"  Selesai dalam {fnum(time.time() - t_start, 0)} detik. Ini alat riset, bukan saran investasi.")


# ======================================================================
# GRAFIK
# ======================================================================

SURFACE, INK, INK2, MUTED = "#fcfcfb", "#0b0b0b", "#52514e", "#898781"
GRID, AXIS = "#e1e0d9", "#c3c2b7"
C_GA, C_BH, C_GA_LIGHT = "#2a78d6", "#eb6834", "#86b6ef"


def make_chart(path, name, m, r):
    plt.rcParams.update({
        "font.family": "sans-serif", "font.size": 9.5,
        "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
        "axes.edgecolor": AXIS, "axes.linewidth": 0.8, "axes.labelcolor": INK2,
        "axes.spines.top": False, "axes.spines.right": False,
        "axes.grid": True, "axes.grid.axis": "y", "grid.color": GRID, "grid.linewidth": 0.8,
        "xtick.color": AXIS, "ytick.color": AXIS, "xtick.labelcolor": MUTED, "ytick.labelcolor": MUTED,
        "axes.titlesize": 11.5, "axes.titleweight": "bold", "axes.titlecolor": INK,
        "axes.titlelocation": "left", "legend.frameon": False, "legend.fontsize": 9,
    })
    pct = FuncFormatter(lambda v, _: "0%" if abs(v) < 1e-9 else _indo(f"{v * 100:+.0f}%"))

    def dec_axis(axis):
        """Label angka desimal; jumlah digit mengikuti jarak antar-tick supaya tidak ada label kembar."""
        ticks = axis.get_majorticklocs()
        step = float(np.min(np.diff(ticks))) if len(ticks) > 1 else 1.0
        d = max(1, int(-math.floor(math.log10(step)))) if step > 0 else 1
        axis.set_major_formatter(FuncFormatter(lambda v, _: _indo(f"{v:.{d}f}")))

    def date_axis(ax, i0, i1):
        years = (m.dates[i1 - 1] - m.dates[i0]).days / 365.25
        if years > 6:
            ax.xaxis.set_major_locator(mdates.YearLocator(base=1 if years <= 10 else 2))
            ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
        else:
            ax.xaxis.set_major_locator(mdates.MonthLocator(bymonth=[1, 7]))
            ax.xaxis.set_major_formatter(FuncFormatter(
                lambda x, _: (lambda d: str(d.year) if d.month == 1 else BULAN[d.month - 1])(mdates.num2date(x))))

    def cum_line(ax, i0, i1, rets, color):
        d = m.dates[i0 - 1:i1]  # mulai dari 0% di hari sebelum periode
        y = np.concatenate([[0.0], np.cumprod(1 + np.asarray(rets)) - 1])
        ax.plot(d, y, color=color, lw=1.8, solid_capstyle="round", solid_joinstyle="round", zorder=3)
        return d[-1], y[-1]

    def end_points(ax, pts):
        """Titik + nilai akhir di ujung kanan garis; label dilewati kalau bertabrakan."""
        lo, hi = ax.get_ylim()
        collide = len(pts) == 2 and abs(pts[0][1] - pts[1][1]) < 0.07 * (hi - lo)
        for x, y, color in pts:
            ax.scatter([x], [y], s=40, color=color, edgecolors=SURFACE, linewidths=1.5, zorder=4)
            if not collide:
                ax.annotate(fpct(y, 0), (x, y), xytext=(7, 0), textcoords="offset points",
                            va="center", fontsize=9, color=INK2)

    def subtitle(ax, text):
        ax.text(0, 1.015, text, transform=ax.transAxes, fontsize=8.8, color=INK2, va="bottom")

    fig = plt.figure(figsize=(12.5, 13.0))
    gs = fig.add_gridspec(3, 3, height_ratios=[1, 1, 0.92], left=0.07, right=0.965,
                          top=0.872, bottom=0.075, hspace=0.46, wspace=0.32)
    ax1, ax2 = fig.add_subplot(gs[0, :]), fig.add_subplot(gs[1, :])
    ax3, ax4, ax5 = (fig.add_subplot(gs[2, k]) for k in range(3))

    # 1) Data latih vs data uji
    split = r["split"]
    cum_line(ax1, WARMUP, split, r["tr_rets"], C_GA)
    cum_line(ax1, WARMUP, split, r["bh_tr"], C_BH)
    p_ga = cum_line(ax1, split, m.n, r["te_rets"], C_GA)
    p_bh = cum_line(ax1, split, m.n, r["bh_te"], C_BH)
    ax1.axhline(0, color=AXIS, lw=0.8, zorder=1)
    ax1.axvline(m.dates[split - 1], color=INK2, lw=1, zorder=2)
    ax1.set_title("1   Data latih vs data uji", pad=24)
    trans = mtransforms.blended_transform_factory(ax1.transData, ax1.transAxes)
    ax1.text(m.dates[WARMUP], 1.015, "DATA LATIH: GA mencari parameter di sini", transform=trans,
             fontsize=8.8, color=INK2, va="bottom")
    ax1.text(m.dates[split - 1], 1.015, "  DATA UJI: tidak pernah dilihat GA (return dihitung ulang dari 0%)",
             transform=trans, fontsize=8.8, color=INK2, va="bottom")
    ax1.yaxis.set_major_formatter(pct)
    ax1.set_ylabel("Return kumulatif")
    date_axis(ax1, WARMUP, m.n)
    span = m.dates[-1] - m.dates[WARMUP - 1]
    ax1.set_xlim(m.dates[WARMUP - 1], m.dates[-1] + span * 0.05)
    end_points(ax1, [(*p_ga, C_GA), (*p_bh, C_BH)])

    # 2) Walk-forward
    wins = r["wins"]
    i0, i1 = wins[0]["te0"], wins[-1]["te1"]
    p_ga = cum_line(ax2, i0, i1, r["wf_rets"], C_GA)
    p_bh = cum_line(ax2, i0, i1, r["wf_bh"], C_BH)
    for w in wins[1:]:
        ax2.axvline(m.dates[w["te0"] - 1], color=GRID, lw=1, zorder=1)
    ax2.axhline(0, color=AXIS, lw=0.8, zorder=1)
    ty, tm = r["wf_label"]
    ax2.set_title("2   Walk-forward: simulasi pemakaian sungguhan", pad=24)
    subtitle(ax2, f"Tiap jendela: GA dilatih {fnum(ty, 1)} tahun, lalu dipakai {fnum(tm, 0)} bulan berikutnya. "
                  f"Hanya hasil periode uji yang dirangkai ({len(wins)} jendela, dipisah garis tipis).")
    ax2.yaxis.set_major_formatter(pct)
    ax2.set_ylabel("Return kumulatif")
    date_axis(ax2, i0, i1)
    span = m.dates[i1 - 1] - m.dates[i0 - 1]
    ax2.set_xlim(m.dates[i0 - 1], m.dates[i1 - 1] + span * 0.05)
    end_points(ax2, [(*p_ga, C_GA), (*p_bh, C_BH)])

    # 3) Evolusi GA
    hist = r["history"]
    gens = np.arange(1, len(hist) + 1)
    ax3.plot(gens, [h[0] for h in hist], color=C_GA, lw=1.8, label="Individu terbaik")
    ax3.plot(gens, [h[1] for h in hist], color=MUTED, lw=1.8, label="Median populasi")
    ax3.set_title("3   Evolusi GA", pad=24)
    subtitle(ax3, "Fitness per generasi, di data latih")
    ax3.set_xlabel("Generasi")
    ax3.set_ylabel("Fitness (Sharpe)")
    ax3.xaxis.set_major_locator(MaxNLocator(integer=True, nbins=5))
    dec_axis(ax3.yaxis)
    ax3.legend(loc="lower right")

    # 4) Kestabilan
    nb, base = r["nb_train"], r["base"]
    counts, _, _ = ax4.hist(nb, bins=18, color=C_GA_LIGHT, rwidth=0.86, zorder=2)
    ax4.set_ylim(0, max(counts.max(), 1) * 1.35)  # ruang untuk label di atas batang
    ax4.axvline(base, color=INK, lw=1.3, zorder=3)
    lo, hi = ax4.get_xlim()
    right_side = base < (lo + hi) / 2
    ax4.annotate(f"parameter\nterbaik ({fnum(base)})", xy=(base, 0.98), xycoords=("data", "axes fraction"),
                 xytext=(5 if right_side else -5, 0), textcoords="offset points",
                 ha="left" if right_side else "right", va="top", fontsize=8.5, color=INK2)
    ax4.set_title("4   Kestabilan parameter", pad=24)
    subtitle(ax4, f"Sharpe {len(nb)} variasi parameter (maks ±10%)")
    ax4.set_xlabel("Sharpe di data latih")
    ax4.set_ylabel("Jumlah variasi")
    dec_axis(ax4.xaxis)

    # 5) Kontrol data acak: berlian biru = data asli, titik abu-abu = tiap data acak
    shuf = r["shuf"]
    if shuf:
        offs = np.linspace(-0.06, 0.06, len(shuf)) if len(shuf) > 1 else np.zeros(1)
        for j in range(2):
            ax5.scatter(j + 0.15 + offs, [s[j] for s in shuf], s=42, color=MUTED, edgecolors=SURFACE,
                        linewidths=1.2, zorder=3)
    ax5.scatter([-0.15, 0.85], list(r["real"]), s=120, marker="D", color=C_GA, edgecolors=SURFACE,
                linewidths=1.5, zorder=4)
    ax5.axhline(0, color=AXIS, lw=0.8, zorder=1)
    ax5.set_xticks([0, 1], ["Data latih", "Data uji"])
    ax5.set_xlim(-0.6, 1.6)
    ax5.set_title("5   Kontrol data acak", pad=24)
    subtitle(ax5, "Sharpe hasil GA: data asli vs data diacak")
    ax5.set_ylabel("Sharpe ratio")
    dec_axis(ax5.yaxis)
    ax5.legend(handles=[
        Line2D([], [], marker="D", ls="", ms=8, color=C_GA, mec=SURFACE, label="Data asli"),
        Line2D([], [], marker="o", ls="", ms=7, color=MUTED, mec=SURFACE, label="Data acak (tanpa pola)"),
    ], loc="upper center", bbox_to_anchor=(0.5, -0.1), ncol=2, handletextpad=0.3, columnspacing=1.2)

    # Judul, legenda, catatan
    fig.text(0.07, 0.978, "GA untuk tuning strategi trading", fontsize=15, weight="bold", color=INK, va="top")
    fig.text(0.07, 0.954, f"Data: {name}   |   Strategi: MA crossover + filter RSI + stop-loss   |   "
                          f"Biaya beli {fpct(COST_BUY, 2, False)}, jual {fpct(COST_SELL, 2, False)}",
             fontsize=9.5, color=INK2, va="top")
    fig.text(0.07, 0.936, f"Parameter terbaik di data latih: {describe(r['best'])}",
             fontsize=9.5, color=INK2, va="top")
    fig.legend(handles=[Line2D([], [], color=C_GA, lw=2), Line2D([], [], color=C_BH, lw=2)],
               labels=["Strategi GA", "Beli-dan-tahan"], loc="upper right", bbox_to_anchor=(0.968, 0.982), ncol=2)
    fig.text(0.07, 0.022, "Alat riset dan belajar, bukan saran investasi. Sharpe ratio = return dibagi volatilitas, "
                          "disetahunkan, setelah biaya transaksi.", fontsize=8.5, color=MUTED)
    fig.savefig(path, dpi=150)
    plt.close(fig)


if __name__ == "__main__":
    main()
