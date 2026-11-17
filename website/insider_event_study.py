"""
Event study lanjutan dari insider_activity.py: bukan cuma "BUY/SELL insider
diikuti harga naik/turun atau tidak" (sudah dijawab lemah -- lihat memory
project_arah_harga_vs_aksi_insider), tapi tiga pemotongan yang mungkin
menyaring sinyal yang lebih tajam dari sinyal mentahnya:

1. BESARAN transaksi relatif terhadap turnover hari itu (value_idr / (Volume
   x Avg Price) dari Daily/Summary) -- dugaan: transaksi kecil dari
   karyawan (opsi MESOP dkk yang sudah disaring is_market_trade, tapi BUY/
   SELL kecil juga banyak) cuma noise, transaksi besar relatif ke turnover
   lebih mungkin bawa informasi.
2. SELARAS/TIDAK dengan Big Lot Flow ("Net Top5 All Lot" trailing 5 hari
   dari Daily/Summary -- ukuran broker besar/"bandar" yang sudah dipakai
   utilities.compute_cumulative_flow dan backtest_signal.py). Insider BUY
   pas bandar juga net-buy 5 hari terakhir vs insider BUY sendirian tanpa
   dukungan bandar.
3. PENGENDALI SAJA (is_controller dari insider_activity.py) vs bukan --
   badge_split sebelumnya menggabung Direktur/Komisaris/Pengendali jadi
   satu, di sini dipisah murni pengendali karena itu yang paling sering
   dianggap paling informatif secara teori.

PERINGATAN N: setiap pemotongan tambahan mengecilkan n lebih lanjut dari
yang sudah kecil (pooled cuma 2.563 BUY / 1.338 SELL, dan itu sendiri
belum lolos luar-sampel -- lihat project_arah_harga_vs_aksi_insider).
Silangan tiga cara potong ini BUKAN untuk cari kombinasi yang "menang",
tapi buat lihat apakah efek dari sinyal mentah itu terkonsentrasi di
sebagian sub-kelompok atau memang menyebar rata (kalau terkonsentrasi di
n kecil -- taruh curiga tinggi itu cuma kebetulan, bukan pola).

Run: python insider_event_study.py   (dari folder mana saja)
"""
try:
    from .runtime_paths import runtime_file as _runtime_file, market_file as _market_file, WEBSITE_DIR as _WEBSITE_DIR, PROJECT_DIR as _PROJECT_DIR, RUNTIME_DIR as _RUNTIME_DIR
except ImportError:
    from website.runtime_paths import runtime_file as _runtime_file, market_file as _market_file, WEBSITE_DIR as _WEBSITE_DIR, PROJECT_DIR as _PROJECT_DIR, RUNTIME_DIR as _RUNTIME_DIR
import os
import sys

import numpy as np
import pandas as pd

_WEBSITE_DIR = os.path.dirname(os.path.abspath(__file__))
_FLASK_DIR = os.path.dirname(_WEBSITE_DIR)
if _FLASK_DIR not in sys.path:
    sys.path.insert(0, _FLASK_DIR)

from website import insider_activity as ia
from website.config import DAILY_PATH

SUMMARY_DIR = os.path.join(DAILY_PATH, 'Summary')
HORIZONS = [1, 3, 5, 10, 20]
PRE_DAYS = 5
BANDAR_WINDOW = 5   # sama dengan SLOPE_DAYS di backtest_signal.py

_summary_cache = {}


def load_summary(ticker):
    """Date, Close, Volume, Avg Price, Net Top5 All Lot -- satu file dibaca sekali."""
    if ticker not in _summary_cache:
        path = os.path.join(SUMMARY_DIR, f'{ticker}_Summary.csv')
        if not os.path.exists(path):
            _summary_cache[ticker] = None
        else:
            try:
                cols = ['Date', 'Close', 'Volume', 'Avg Price', 'Net Top5 All Lot']
                df = pd.read_csv(path, usecols=cols)
                df['Date'] = pd.to_datetime(df['Date'], format='%d-%b-%y', errors='coerce')
                df = df.dropna(subset=['Date', 'Close']).sort_values('Date').reset_index(drop=True)
                df['bandar_roll'] = df['Net Top5 All Lot'].fillna(0).rolling(BANDAR_WINDOW).sum()
                df['turnover'] = df['Volume'].fillna(0) * df['Avg Price'].fillna(0)
                _summary_cache[ticker] = df
            except Exception:
                _summary_cache[ticker] = None
    return _summary_cache[ticker]


def build_events(df_insider):
    """
    Satu baris per (ticker, tanggal) event bersih -- BUY-only atau SELL-only
    hari itu -- plus agregat yang dibutuhkan tiga pemotongan: total
    value_idr hari itu dan apakah ADA baris dengan is_controller=True.
    """
    trade = df_insider[df_insider['is_market_trade']].copy()
    trade = ia.enrich_prices(trade)
    trade['day'] = trade['date'].dt.normalize()

    events = []
    for (ticker, day), g in trade.groupby(['ticker', 'day']):
        actions = g['action_type'].unique()
        if len(actions) != 1:
            continue  # campuran BUY+SELL hari yang sama -> dibuang
        events.append({
            'ticker': ticker,
            'day': day,
            'action': actions[0],
            'value_idr': float(g['value_idr'].sum(skipna=True)),
            'is_controller': bool(g['is_controller'].any()),
            'n_rows': len(g),
        })
    return pd.DataFrame(events)


def measure_event(ticker, day, action):
    sdf = load_summary(ticker)
    if sdf is None or sdf.empty:
        return None
    pos = sdf['Date'].searchsorted(day, side='left')
    if pos >= len(sdf):
        return None
    entry_close = sdf['Close'].iloc[pos]
    if entry_close == 0 or pd.isna(entry_close):
        return None

    row = {
        'ticker': ticker, 'day': day, 'action': action, 'entry_idx': pos,
        'turnover': sdf['turnover'].iloc[pos],
        'bandar_roll': sdf['bandar_roll'].iloc[pos],
    }
    pre_idx = pos - PRE_DAYS
    if pre_idx >= 0 and pd.notna(sdf['Close'].iloc[pre_idx]) and sdf['Close'].iloc[pre_idx] != 0:
        row['pre_return_pct'] = (entry_close - sdf['Close'].iloc[pre_idx]) / sdf['Close'].iloc[pre_idx] * 100
    else:
        row['pre_return_pct'] = np.nan

    for h in HORIZONS:
        fwd_idx = pos + h
        if fwd_idx < len(sdf):
            fwd_close = sdf['Close'].iloc[fwd_idx]
            row[f'fwd_{h}d_pct'] = (fwd_close - entry_close) / entry_close * 100 if entry_close else np.nan
        else:
            row[f'fwd_{h}d_pct'] = np.nan
    return row


def unconditional_baseline(tickers, horizons=HORIZONS, pre_days=PRE_DAYS):
    rows = []
    for ticker in tickers:
        sdf = load_summary(ticker)
        if sdf is None or len(sdf) < max(horizons) + pre_days + 1:
            continue
        close = sdf['Close'].values
        n = len(close)
        for i in range(pre_days, n - max(horizons)):
            if close[i] == 0 or pd.isna(close[i]):
                continue
            rec = {}
            for h in horizons:
                rec[f'fwd_{h}d_pct'] = (close[i + h] - close[i]) / close[i] * 100
            rows.append(rec)
    return pd.DataFrame(rows)


def summarize(df, label, horizons=(5, 10, 20)):
    n = len(df)
    print(f'\n=== {label} (n={n}) ===')
    if n == 0:
        print('  (tidak ada data)')
        return
    if n < 30:
        print('  [!] n < 30 -- jangan percaya angka ini, cuma buat lihat arah kasar')
    print(f"{'Horizon':>8} {'Mean%':>8} {'Median%':>8} {'WinRate%':>9} {'n':>6}")
    for h in horizons:
        col = f'fwd_{h}d_pct'
        s = df[col].dropna()
        if s.empty:
            continue
        print(f"{h:>7}d {s.mean():>8.2f} {s.median():>8.2f} {(s > 0).mean()*100:>9.1f} {len(s):>6}")


def effect_vs_baseline(sub, baseline, horizons=(5, 10, 20)):
    for h in horizons:
        col = f'fwd_{h}d_pct'
        s = sub[col].dropna()
        b = baseline[col].dropna()
        if s.empty or b.empty:
            continue
        print(f"  {h:>3}d  n={len(s):<5} mean={s.mean():>6.2f}%  baseline={b.mean():>6.2f}%  efek={s.mean()-b.mean():>+6.2f}pp")


def main():
    df_insider = ia.load_all()
    events = build_events(df_insider)
    print(f'Total event ticker-hari bersih: {len(events)}')
    print(events['action'].value_counts())

    measured = []
    for _, r in events.iterrows():
        m = measure_event(r['ticker'], r['day'], r['action'])
        if m is None:
            continue
        m['value_idr'] = r['value_idr']
        m['is_controller'] = r['is_controller']
        measured.append(m)
    mdf = pd.DataFrame(measured)
    mdf.to_csv(str(_runtime_file('', 'insider_event_measured_v2.csv')), index=False)

    tickers_involved = sorted(mdf['ticker'].unique())
    baseline = unconditional_baseline(tickers_involved)
    summarize(baseline, 'BASELINE unconditional (semesta ticker yang sama, semua hari)')

    buy = mdf[mdf['action'] == 'ACTION_TYPE_BUY'].copy()
    sell = mdf[mdf['action'] == 'ACTION_TYPE_SELL'].copy()

    # ---------- 1. Besaran transaksi relatif terhadap turnover ----------
    print('\n\n########## POTONGAN 1: besaran transaksi relatif turnover hari itu ##########')
    for name, sub in [('BUY', buy), ('SELL', sell)]:
        rel = sub['value_idr'] / sub['turnover'].replace(0, np.nan)
        sub = sub.assign(rel_size=rel).dropna(subset=['rel_size'])
        if len(sub) < 10:
            print(f'{name}: data relative-size terlalu sedikit (n={len(sub)})')
            continue
        cutoff = sub['rel_size'].quantile(2/3)
        big = sub[sub['rel_size'] >= cutoff]
        small = sub[sub['rel_size'] < cutoff]
        print(f'\n-- {name}: rel_size cutoff (tertil atas) = {cutoff:.4f} (value_idr / turnover hari itu) --')
        print('BESAR (tertil atas, relatif ke turnover):')
        effect_vs_baseline(big, baseline)
        print('KECIL (2/3 bawah):')
        effect_vs_baseline(small, baseline)

    # ---------- 2. Selaras/tidak dengan Big Lot Flow (bandar) ----------
    print('\n\n########## POTONGAN 2: selaras vs tidak dengan Big Lot Flow (Net Top5 All Lot, rolling 5 hari) ##########')
    for name, sub, align_test in [
        ('BUY', buy, lambda x: x > 0),
        ('SELL', sell, lambda x: x < 0),
    ]:
        aligned = sub[align_test(sub['bandar_roll'])]
        not_aligned = sub[~align_test(sub['bandar_roll']) & sub['bandar_roll'].notna()]
        print(f'\n-- {name} --')
        print(f'SELARAS bandar (n={len(aligned)}):')
        effect_vs_baseline(aligned, baseline)
        print(f'TIDAK selaras bandar (n={len(not_aligned)}):')
        effect_vs_baseline(not_aligned, baseline)

    # ---------- 3. Pengendali saja vs bukan ----------
    print('\n\n########## POTONGAN 3: Pengendali saja vs bukan pengendali ##########')
    for name, sub in [('BUY', buy), ('SELL', sell)]:
        controller = sub[sub['is_controller']]
        non_controller = sub[~sub['is_controller']]
        print(f'\n-- {name} --')
        print(f'PENGENDALI (n={len(controller)}):')
        effect_vs_baseline(controller, baseline)
        print(f'BUKAN pengendali (n={len(non_controller)}):')
        effect_vs_baseline(non_controller, baseline)


if __name__ == '__main__':
    main()
