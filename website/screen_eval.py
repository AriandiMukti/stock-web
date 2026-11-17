"""
Rekam jejak screen otomatis app: Consol, Retail Sell, Consol Low, Retail
Sell Low.

KENAPA MODUL INI ADA
App ini setiap hari menghasilkan rekomendasi lewat empat screen di menu
Screens, tapi belum pernah ada yang mengukur apakah rekomendasi itu
benar-benar berhasil. Modul ini menjawabnya dengan metode yang sama
seperti Scanner Lab: rekonstruksi keanggotaan screen di SETIAP hari
bursa, ukur hasil 20 hari kemudian, bandingkan dengan baseline pasar.

KENAPA BUKAN WATCHLIST (Best / Best Low / Pattern Up)
Awalnya itu yang mau diukur, tapi ternyata tidak bisa: ketiganya
dikurasi MANUAL, tidak ada kriteria untuk direkonstruksi (analyze.py cuma
menyegarkan metriknya lewat refresh_watchlist_metrics, tidak pernah
mengisinya). Satu-satunya jejaknya ada di tabel WatchlistHistory, dan itu
baru berisi 99 baris dalam 6 hari -- penambahan terbarunya bahkan baru
berumur sehari, sedangkan mengukur hasil butuh 20 hari bursa. Jadi yang
bisa diukur sekarang hanyalah screen yang algoritmik.

TEMUAN UTAMA
Kriteria di sini disalin dari analyze.py (classify_stock + consol).
Hasilnya, per Sep 2026, terhadap baseline pasar -1,33%:

    Consol Low        n=  236   -0,46%   win 47,5%   +0,87pp
    Retail Sell Low   n=3.141   -2,09%   win 42,2%   -0,76pp
    Retail Sell       n=2.705   -4,60%   win 40,0%   -3,27pp
    Consol            n=  153   -6,62%   win 40,5%   -5,29pp

Hanya Consol Low yang mengungguli pasar. Gabungan keempatnya -1,90pp di
BAWAH baseline.

Yang paling berguna justru kontras Consol vs Consol Low: kriteria polanya
IDENTIK, yang beda cuma ambang nilai transaksi -- dan hasilnya berlawanan.
Dipecah per tier, penurunannya monoton:

    5-10 M    n=137   -0,70%   win 40,9%   +0,63pp
    10-20 M   n= 99   -0,14%   win 56,6%   +1,19pp
    20-50 M   n= 91   -4,48%   win 40,7%   -3,15pp
    50-150 M  n= 28   -9,73%   win 39,3%   -8,40pp
    >150 M    n= 34   -9,82%   win 41,2%   -8,49pp

Pola yang sama bekerja di saham sepi dan gagal di saham ramai. Ini
menguatkan temuan Scanner Lab dari arah yang sepenuhnya berbeda: di sana
lonjakan VOLUME yang merugikan, di sini nilai TRANSAKSI besar. Dua
analisis independen, satu kesimpulan -- keramaian itu mahal.

BATASNYA
Periodenya ~6 bulan dan didominasi pasar turun. Win rate terbaik pun cuma
56,6% pada sampel 99 kejadian. Angka di sini rekam jejak historis, bukan
prediksi.
"""
try:
    from .runtime_paths import runtime_file as _runtime_file, market_file as _market_file, WEBSITE_DIR as _WEBSITE_DIR, PROJECT_DIR as _PROJECT_DIR, RUNTIME_DIR as _RUNTIME_DIR
except ImportError:
    from website.runtime_paths import runtime_file as _runtime_file, market_file as _market_file, WEBSITE_DIR as _WEBSITE_DIR, PROJECT_DIR as _PROJECT_DIR, RUNTIME_DIR as _RUNTIME_DIR
import os
import warnings

import pandas as pd
import numpy as np

from .config import DAILY_PATH

SUMMARY_DIR = os.path.join(DAILY_PATH, 'Summary')
CACHE_FILE = str(_runtime_file('', 'screen_eval_cache.pkl'))

FORWARD_DAYS = 20
MARKET_BASELINE_20D = -1.33

# Disalin dari analyze.py -- sumber kebenarannya di sana.
VALUE_AVG_PARAM = 20     # analyze.py:147
VALUE_AVG_PARAM2 = 5     # analyze.py:148
P_SURGE = 4              # analyze.py:27
P_KONSOL = 5             # analyze.py:28

SCREEN_LABELS = {
    'consol': ('Consol', 'ConsolStocks'),
    'retailsell': ('Retail Sell', 'RetailSellStocks'),
    'consol_low': ('Consol Low', 'ConsolLowValueStocks'),
    'retailsell_low': ('Retail Sell Low', 'RetailSellLowValueStocks'),
}
# Peta balik: nama model yang dipakai URL /display-analyze?type=...
TYPE_TO_SCREEN = {model: key for key, (_, model) in SCREEN_LABELS.items()}


def _load(stock):
    path = os.path.join(SUMMARY_DIR, '%s_Summary.csv' % stock)
    try:
        df = pd.read_csv(path).fillna(0)
    except Exception:
        return None
    if df.empty or 'Date' not in df.columns:
        return None
    df['Date'] = pd.to_datetime(df['Date'], format='%d-%b-%y', errors='coerce')
    df = df.dropna(subset=['Date']).sort_values('Date').reset_index(drop=True)
    for col in ['Open', 'Close', 'Volume', 'Retail']:
        df[col] = pd.to_numeric(df.get(col), errors='coerce').fillna(0)
    return df


def classify_history(df):
    """
    Kategori screen untuk setiap hari, meniru analyze.classify_stock.

    Aslinya consol() memakai df.iloc[-9:-5] dan df.iloc[-5:] -- selalu
    relatif hari terakhir. Di sini acuannya digeser ke hari ke-i supaya
    bisa dievaluasi sepanjang riwayat: jendela surge i-8..i-5, jendela
    konsol i-4..i.

    Loop-nya membaca array numpy, bukan df.iloc: versi iloc membuat ~1.300
    objek pandas per saham dan makan ~0,5 detik untuk saham likuid -- dan
    fungsi ini jalan di setiap pembukaan Halaman Saham. Rata-rata memakai
    nanmean karena Series.mean() pandas melewati NaN; max/min sengaja
    TIDAK (values.max() di versi lama ikut NaN).
    """
    n = len(df)
    close, open_, vol, retail = df['Close'], df['Open'], df['Volume'], df['Retail']
    ema10 = close.ewm(span=10, adjust=False).mean().to_numpy()
    ma20_vol = vol.rolling(20).mean().to_numpy()
    value_b = (open_ + close) / 2 * vol / 1e9

    c, o = close.to_numpy(dtype=float), open_.to_numpy(dtype=float)
    v, ret, val = vol.to_numpy(dtype=float), retail.to_numpy(), value_b.to_numpy()

    cats = [None] * n
    total = P_SURGE + P_KONSOL
    with np.errstate(invalid='ignore'), warnings.catch_warnings():
        warnings.simplefilter('ignore', RuntimeWarning)  # nanmean irisan serba-NaN
        for i in range(total + 20, n):
            value = val[i]
            if value < VALUE_AVG_PARAM2:
                continue

            surge_vol = v[i - total + 1:i - P_KONSOL + 1]
            k_lo = i - P_KONSOL + 1
            ma20_at = ma20_vol[k_lo]
            if surge_vol.size == 0 or np.isnan(ma20_at):
                continue

            # np.max/np.min, bukan max()/min() bawaan: yang bawaan
            # membuang NaN tergantung urutan argumen.
            hi = np.max((c[k_lo:i + 1].max(), o[k_lo:i + 1].max()))
            lo = np.min((c[k_lo:i + 1].min(), o[k_lo:i + 1].min()))
            if lo <= 0:
                continue

            surge_mean = np.nanmean(surge_vol)
            is_consol = bool(
                surge_mean > ma20_at
                and (hi - lo) / lo <= 0.07
                and np.nanmean(v[k_lo:i + 1]) < surge_mean * 0.75
                and ema10[i] > ema10[k_lo])

            r = ret[i]
            if value >= VALUE_AVG_PARAM:
                cats[i] = 'consol' if is_consol else ('retailsell' if r < 0 else None)
            else:
                cats[i] = 'consol_low' if is_consol else ('retailsell_low' if r < 0 else None)
    return cats, value_b


def _all_stocks():
    if not os.path.isdir(SUMMARY_DIR):
        return []
    return sorted(n[:-len('_Summary.csv')] for n in os.listdir(SUMMARY_DIR)
                  if n.endswith('_Summary.csv'))


def run_backtest():
    """
    Rekonstruksi seluruh riwayat screen dan ukur hasilnya.

    Hanya hari PERTAMA sebuah saham masuk screen yang dihitung -- saham
    yang bertahan di screen seminggu bukan tujuh kejadian terpisah, dan
    menghitungnya berulang akan membuat saham yang lama nyangkut
    mendominasi statistik.
    """
    rows = []
    for stock in _all_stocks():
        df = _load(stock)
        if df is None or len(df) < 60:
            continue
        cats, value_b = classify_history(df)
        close = df['Close']
        for i, cat in enumerate(cats):
            if not cat or i + FORWARD_DAYS >= len(df):
                continue
            if i > 0 and cats[i - 1] == cat:
                continue
            entry = close.iloc[i]
            if entry <= 0:
                continue
            rows.append({
                'stock': stock,
                'date': df['Date'].iloc[i],
                'screen': cat,
                'value_b': float(value_b.iloc[i]),
                'fwd20': float((close.iloc[i + FORWARD_DAYS] - entry) / entry * 100),
            })
    return pd.DataFrame(rows)


def _summarize(frame):
    if frame.empty:
        return None
    mean = float(frame['fwd20'].mean())
    return {
        'n': int(len(frame)),
        'mean': round(mean, 2),
        'median': round(float(frame['fwd20'].median()), 2),
        'win_rate': round(float((frame['fwd20'] > 0).mean() * 100), 1),
        'vs_baseline': round(mean - MARKET_BASELINE_20D, 2),
    }


def build_report(force=False):
    """Ringkasan siap-tampil; di-cache karena rekonstruksinya ~1 menit."""
    import pickle

    newest = 0
    if os.path.isdir(SUMMARY_DIR):
        for name in os.listdir(SUMMARY_DIR):
            if name.endswith('_Summary.csv'):
                newest = max(newest, os.path.getmtime(os.path.join(SUMMARY_DIR, name)))

    if not force and os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, 'rb') as fh:
                cached = pickle.load(fh)
            if cached.get('built_at', 0) >= newest:
                cached['from_cache'] = True
                return cached
        except Exception:
            pass

    df = run_backtest()
    if df.empty:
        return {'available': False, 'message': 'Data harian belum cukup untuk backtest.'}

    screens = []
    for key, (label, model) in SCREEN_LABELS.items():
        stats = _summarize(df[df['screen'] == key])
        if stats:
            stats.update({'key': key, 'label': label, 'type': model})
            screens.append(stats)
    screens.sort(key=lambda r: r['vs_baseline'], reverse=True)

    # Tier nilai transaksi -- temuan paling berguna dari analisis ini,
    # karena memperlihatkan pola yang sama berbalik hasil tergantung
    # seramai apa sahamnya diperdagangkan.
    tiers = []
    bins = [(0, 5, '< 5 M'), (5, 10, '5 - 10 M'), (10, 20, '10 - 20 M'),
            (20, 50, '20 - 50 M'), (50, 150, '50 - 150 M'), (150, 1e12, '> 150 M')]
    consol_only = df[df['screen'].isin(['consol', 'consol_low'])]
    for lo, hi, label in bins:
        sel = df[(df['value_b'] >= lo) & (df['value_b'] < hi)]
        stats = _summarize(sel)
        if not stats:
            continue
        stats['label'] = label
        c = _summarize(consol_only[(consol_only['value_b'] >= lo)
                                   & (consol_only['value_b'] < hi)])
        stats['consol'] = c
        tiers.append(stats)

    payload = {
        'available': True,
        'baseline': MARKET_BASELINE_20D,
        'total': _summarize(df),
        'screens': screens,
        'tiers': tiers,
        'range': [df['date'].min().strftime('%Y-%m-%d'),
                  df['date'].max().strftime('%Y-%m-%d')],
        'built_at': __import__('time').time(),
        'from_cache': False,
    }
    try:
        with open(CACHE_FILE, 'wb') as fh:
            pickle.dump(payload, fh)
    except Exception:
        pass
    return payload


def screen_record_for(type_name):
    """Rekam jejak satu screen, untuk ditempel di halaman screen itu sendiri."""
    report = build_report()
    if not report.get('available'):
        return None
    key = TYPE_TO_SCREEN.get(type_name)
    if not key:
        return None
    for row in report['screens']:
        if row['key'] == key:
            return dict(row, baseline=report['baseline'], range=report['range'])
    return None
