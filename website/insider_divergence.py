"""
Menguji ulang kerangka fake_accumulation.py (harga x arus, grid 4x2) tapi
arusnya diganti dari Top5 broker jadi transaksi insider BUY/SELL.

KENAPA INI, BUKAN POTONGAN LAGI
insider_event_study.py sudah coba tiga potongan (besaran transaksi,
selaras bandar, pengendali-saja) dan SEMUA gagal menajamkan sinyal
mentahnya -- lihat memory project_arah_harga_vs_aksi_insider. Daripada
potong lagi tanpa alasan kuat (rawan p-hacking di data 6 bulan), pakai
kerangka yang SUDAH TERBUKTI kerja untuk arus broker di app ini:
fake_accumulation.py menemukan bahwa arus Top5 cuma informatif kalau
disilangkan dengan tren harga -- "beli saat harga turun" itu satu-satunya
sel dengan rata-rata positif, sementara "beli saat harga sudah naik
banyak" adalah akumulasi palsu. Insider adalah "pihak" yang berbeda dari
Top5 broker (identitasnya diketahui persis, bukan agregat 5 broker
teranonim yang berganti tiap hari) -- pantas diuji apa polanya sama,
lebih tajam, atau malah berlawanan.

METODOLOGI (menyalin fake_accumulation.py apa adanya supaya bisa
dibandingkan langsung):
- Kelompok harga = return WINDOW hari (default 20) SEBELUM tanggal
  transaksi insider (trailing, harga sudah begini duluan, insider baru
  bertindak) -- pakai PRICE_BUCKETS yang sama persis (turun <=-5%, datar
  -5%..5%, naik tipis 5%..20%, naik banyak >20%).
- Arus = BUY atau SELL insider (event ticker-hari bersih dari
  insider_event_study.build_events -- hari campuran dibuang).
- Hasil = return forward HORIZON hari (default 40, sama seperti
  fake_accumulation.py, supaya lintas-window bisa dibandingkan) sesudah
  tanggal transaksi.
- Baseline = semua hari bursa (bukan cuma hari event) di semesta ticker
  yang sama, horizon yang sama -- dari insider_event_study.unconditional_baseline.

BATAS: cuma April-Sep 2026 (insider), forward 40 hari otomatis membuang
event dari pertengahan Juli ke atas (kehabisan data ke depan) -- N per
sel bisa jauh lebih kecil dari fake_accumulation.py (yang punya broker
flow di SETIAP hari x SETIAP ticker, insider cuma pas ada transaksi).
Baca N tiap sel sebelum percaya angkanya.

Run: python insider_divergence.py
"""
import os
import sys

import pandas as pd

_WEBSITE_DIR = os.path.dirname(os.path.abspath(__file__))
_FLASK_DIR = os.path.dirname(_WEBSITE_DIR)
if _FLASK_DIR not in sys.path:
    sys.path.insert(0, _FLASK_DIR)

from website import insider_activity as ia
from website import insider_event_study as ies

PRICE_BUCKETS = [
    (-1e9, -5.0, 'turun'),
    (-5.0, 5.0, 'datar'),
    (5.0, 20.0, 'naik tipis'),
    (20.0, 1e9, 'naik banyak'),
]


def price_bucket(pct):
    for lo, hi, name in PRICE_BUCKETS:
        if lo < pct <= hi:
            return name
    return 'datar'


def trailing_return(sdf, entry_idx, window):
    start_idx = entry_idx - window
    if start_idx < 0:
        return None
    p0 = sdf['Close'].iloc[start_idx]
    p1 = sdf['Close'].iloc[entry_idx]
    if p0 in (0, None) or pd.isna(p0):
        return None
    return (p1 - p0) / p0 * 100


def build_grid(window=20, horizon=40):
    df_insider = ia.load_all()
    events = ies.build_events(df_insider)

    rows = []
    for _, r in events.iterrows():
        sdf = ies.load_summary(r['ticker'])
        if sdf is None or sdf.empty:
            continue
        entry_idx = sdf['Date'].searchsorted(r['day'], side='left')
        if entry_idx >= len(sdf):
            continue
        trail = trailing_return(sdf, entry_idx, window)
        if trail is None:
            continue
        fwd_idx = entry_idx + horizon
        if fwd_idx >= len(sdf):
            continue
        entry_close = sdf['Close'].iloc[entry_idx]
        if entry_close in (0, None) or pd.isna(entry_close):
            continue
        fwd_close = sdf['Close'].iloc[fwd_idx]
        fwd_pct = (fwd_close - entry_close) / entry_close * 100
        rows.append({
            'ticker': r['ticker'], 'day': r['day'], 'action': r['action'],
            'price_bucket': price_bucket(trail), 'trail_pct': trail, 'fwd_pct': fwd_pct,
        })
    gdf = pd.DataFrame(rows)

    # Baseline unconditional dibagi per price_bucket juga (bukan cuma satu
    # angka global) -- supaya perbandingan adil per kelompok harga, bukan
    # cuma dibanding rata-rata pasar keseluruhan.
    tickers = sorted(gdf['ticker'].unique()) if not gdf.empty else []
    base_rows = []
    for ticker in tickers:
        sdf = ies.load_summary(ticker)
        if sdf is None or len(sdf) < window + horizon + 1:
            continue
        close = sdf['Close'].values
        n = len(close)
        for i in range(window, n - horizon):
            if close[i - window] in (0,) or pd.isna(close[i - window]) or close[i] == 0 or pd.isna(close[i]):
                continue
            trail = (close[i] - close[i - window]) / close[i - window] * 100
            fwd = (close[i + horizon] - close[i]) / close[i] * 100
            base_rows.append({'price_bucket': price_bucket(trail), 'fwd_pct': fwd})
    bdf = pd.DataFrame(base_rows)
    return gdf, bdf


def summarize_grid(gdf, bdf, window, horizon):
    print(f'\n=== Grid harga x aksi insider -- window={window}h, horizon={horizon}h ===')
    order = ['turun', 'datar', 'naik tipis', 'naik banyak']
    base_overall = bdf['fwd_pct']
    print(f"Baseline keseluruhan: n={len(base_overall)} mean={base_overall.mean():.2f}% win={(base_overall>0).mean()*100:.1f}%")
    print()
    print(f"{'Harga':<12} {'Aksi':<6} {'n':>6} {'Mean%':>8} {'Median%':>9} {'Win%':>7} {'BaseWin%':>9} {'Selisih':>8}")
    for pb in order:
        base_sub = bdf[bdf['price_bucket'] == pb]['fwd_pct']
        base_win = (base_sub > 0).mean() * 100 if len(base_sub) else float('nan')
        for action, label in [('ACTION_TYPE_BUY', 'BELI'), ('ACTION_TYPE_SELL', 'JUAL')]:
            sub = gdf[(gdf['price_bucket'] == pb) & (gdf['action'] == action)]['fwd_pct']
            if sub.empty:
                print(f"{pb:<12} {label:<6} {0:>6} {'--':>8} {'--':>9} {'--':>7} {base_win:>9.1f} {'--':>8}")
                continue
            win = (sub > 0).mean() * 100
            print(f"{pb:<12} {label:<6} {len(sub):>6} {sub.mean():>8.2f} {sub.median():>9.2f} {win:>7.1f} {base_win:>9.1f} {win-base_win:>+8.1f}")
        beli = gdf[(gdf['price_bucket'] == pb) & (gdf['action'] == 'ACTION_TYPE_BUY')]['fwd_pct']
        jual = gdf[(gdf['price_bucket'] == pb) & (gdf['action'] == 'ACTION_TYPE_SELL')]['fwd_pct']
        if len(beli) and len(jual):
            print(f"  -> BELI vs JUAL di kelompok '{pb}': win {  (beli>0).mean()*100:.1f}% vs {(jual>0).mean()*100:.1f}%  (selisih {(beli>0).mean()*100-(jual>0).mean()*100:+.1f}pp)")
        print()


if __name__ == '__main__':
    for window, horizon in [(20, 20), (20, 40)]:
        gdf, bdf = build_grid(window=window, horizon=horizon)
        summarize_grid(gdf, bdf, window, horizon)
