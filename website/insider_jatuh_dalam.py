"""
Menjawab pertanyaan konkret: kalau saham lagi di zona JATUH DALAM (definisi
persis jatuh_dalam.py -- jatuh >40% dari puncak 60 hari, ADV >= Rp200jt/hari)
DAN ada insider BELI di situ, apa hasilnya lebih bagus daripada Jatuh Dalam
sendirian atau insider BELI sendirian?

Dipisah dari insider_divergence.py karena definisi "turun" di sana cuma
proxy kasar (return trailing 20 hari <= -5%). Di sini pakai definisi ASLI
jatuh_dalam.py (jatuh dari puncak 60 hari, bukan return 20 hari) supaya
bisa dibandingkan apel-ke-apel dengan screener yang sudah tervalidasi
luar-sampel itu.

BUKAN reuse angka BUKTI di jatuh_dalam.py (itu dihitung di semesta/periode
beda -- 865 emiten Jan-Sep 2026 vs sini cuma 409 emiten yang PERNAH ada
transaksi insider, April-Sep). Baseline zona dihitung ULANG di sini di
semesta+periode yang SAMA PERSIS dengan event insider, biar adil.

Run: python insider_jatuh_dalam.py
"""
import os
import sys

import numpy as np
import pandas as pd

_WEBSITE_DIR = os.path.dirname(os.path.abspath(__file__))
_FLASK_DIR = os.path.dirname(_WEBSITE_DIR)
if _FLASK_DIR not in sys.path:
    sys.path.insert(0, _FLASK_DIR)

from website import insider_activity as ia
from website import insider_event_study as ies
from website.config import DAILY_PATH

SUMMARY_DIR = os.path.join(DAILY_PATH, 'Summary')

PUNCAK_W = 60
DALAM = -40.0
MIN_ADV = 200e6
HORIZONS = [20, 40]

_cache = {}


def load_full(ticker):
    if ticker not in _cache:
        path = os.path.join(SUMMARY_DIR, f'{ticker}_Summary.csv')
        if not os.path.exists(path):
            _cache[ticker] = None
        else:
            try:
                df = pd.read_csv(path, usecols=['Date', 'Close', 'High', 'Volume']).fillna(0)
                df['Date'] = pd.to_datetime(df['Date'], format='%d-%b-%y', errors='coerce')
                df = df.dropna(subset=['Date']).sort_values('Date').reset_index(drop=True)
                puncak60 = df['High'].rolling(PUNCAK_W, min_periods=PUNCAK_W).max()
                df['dari_puncak'] = (df['Close'] / puncak60 - 1) * 100
                df['adv'] = df['Close'].rolling(20).mean() * df['Volume'].rolling(20).mean()
                df['in_zone'] = (df['dari_puncak'] <= DALAM) & (df['adv'] >= MIN_ADV)
                _cache[ticker] = df
            except Exception:
                _cache[ticker] = None
    return _cache[ticker]


def forward_returns_at(df, idx, horizons=HORIZONS):
    entry = df['Close'].iloc[idx]
    out = {}
    if entry == 0 or pd.isna(entry):
        return None
    for h in horizons:
        j = idx + h
        if j < len(df):
            out[h] = (df['Close'].iloc[j] - entry) / entry * 100
        else:
            out[h] = None
    return out


def main():
    df_insider = ia.load_all()
    events = ies.build_events(df_insider)
    tickers = sorted(events['ticker'].unique())

    # --- Baseline zona: semua ticker-hari di zona Jatuh Dalam, semesta+periode sama ---
    zone_rows = []
    for ticker in tickers:
        df = load_full(ticker)
        if df is None:
            continue
        idxs = df.index[df['in_zone']].tolist()
        for i in idxs:
            fr = forward_returns_at(df, i)
            if fr:
                zone_rows.append(fr)
    zone_df = pd.DataFrame(zone_rows)

    # --- Event insider yang jatuh persis di hari zona in_zone=True ---
    combo_rows = {'ACTION_TYPE_BUY': [], 'ACTION_TYPE_SELL': []}
    all_rows = {'ACTION_TYPE_BUY': [], 'ACTION_TYPE_SELL': []}
    n_buy_total = n_sell_total = 0
    n_buy_zone = n_sell_zone = 0
    for _, r in events.iterrows():
        df = load_full(r['ticker'])
        if df is None:
            continue
        idx = df['Date'].searchsorted(r['day'], side='left')
        if idx >= len(df):
            continue
        fr = forward_returns_at(df, idx)
        if fr is None:
            continue
        action = r['action']
        all_rows[action].append(fr)
        if action == 'ACTION_TYPE_BUY':
            n_buy_total += 1
        else:
            n_sell_total += 1
        if bool(df['in_zone'].iloc[idx]):
            combo_rows[action].append(fr)
            if action == 'ACTION_TYPE_BUY':
                n_buy_zone += 1
            else:
                n_sell_zone += 1

    print(f'Event insider total (bersih): BUY={n_buy_total}, SELL={n_sell_total}')
    print(f'...yang kejadian PAS lagi di zona Jatuh Dalam: BUY={n_buy_zone} ({n_buy_zone/max(n_buy_total,1)*100:.1f}%), '
          f'SELL={n_sell_zone} ({n_sell_zone/max(n_sell_total,1)*100:.1f}%)')

    def stats(rows, h):
        s = pd.Series([r[h] for r in rows if r.get(h) is not None])
        return s

    print(f"\n{'Kelompok':<38} {'Horizon':>8} {'n':>6} {'Mean%':>8} {'Median%':>9} {'Win%':>7}")
    for h in HORIZONS:
        z = zone_df[h].dropna() if h in zone_df else pd.Series(dtype=float)
        print(f"{'Baseline zona Jatuh Dalam (unconditional)':<38} {h:>7}h {len(z):>6} {z.mean():>8.2f} {z.median():>9.2f} {(z>0).mean()*100:>7.1f}")

        buy_zone = stats(combo_rows['ACTION_TYPE_BUY'], h)
        print(f"{'  + insider BELI (kombo)':<38} {h:>7}h {len(buy_zone):>6} "
              f"{(buy_zone.mean() if len(buy_zone) else float('nan')):>8.2f} "
              f"{(buy_zone.median() if len(buy_zone) else float('nan')):>9.2f} "
              f"{((buy_zone>0).mean()*100 if len(buy_zone) else float('nan')):>7.1f}")

        sell_zone = stats(combo_rows['ACTION_TYPE_SELL'], h)
        print(f"{'  + insider JUAL (kombo)':<38} {h:>7}h {len(sell_zone):>6} "
              f"{(sell_zone.mean() if len(sell_zone) else float('nan')):>8.2f} "
              f"{(sell_zone.median() if len(sell_zone) else float('nan')):>9.2f} "
              f"{((sell_zone>0).mean()*100 if len(sell_zone) else float('nan')):>7.1f}")

        buy_all = stats(all_rows['ACTION_TYPE_BUY'], h)
        print(f"{'Insider BELI (semua kondisi harga)':<38} {h:>7}h {len(buy_all):>6} "
              f"{buy_all.mean():>8.2f} {buy_all.median():>9.2f} {(buy_all>0).mean()*100:>7.1f}")
        print()


if __name__ == '__main__':
    main()
