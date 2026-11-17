"""
Akumulasi palsu: kapan "Top5 net beli" sebenarnya TIDAK berarti apa-apa.

KENAPA INI ADA
Pertanyaan aslinya: bisakah kita mendeteksi bandar yang menyamar -- jual
lewat banyak broker kecil supaya Top5 tetap terlihat akumulasi? Hipotesis
awalnya memakai kolom `Total Seller` (jumlah broker penjual, kolom yang
belum pernah dipakai app ini): kalau sebaran penjual melebar sementara Top5
tetap net beli, itu distribusi yang menyamar.

HIPOTESIS ITU DIUJI DAN GAGAL. 6.893 pengamatan, jendela 20 hari:
    terlihat akumulasi (harga naik + Top5 beli)      n=1440  win 29,4%
      + penjual melebar >= 1,10x                     n= 601  win 27,0%
      pembanding: tanpa tanda penyamaran             n= 282  win 29,8%
Selisih 27,0% vs 29,8% itu setipis noise. Pelebaran jumlah broker penjual
tidak memisahkan apa pun, jadi tidak dipakai sebagai sinyal di sini.

YANG JUSTRU DITEMUKAN
Sinyal penyamarannya bukan di jumlah broker, tapi di HARGA. 12.299
pengamatan, 4x2 sel, return 40 hari (baseline: rata2 -3,15%, win 36,5%):

  harga        arus          n     rata2   median   win%
  turun        Top5 beli   1549    +1,24    -2,44   42,9   <- satu-satunya rata2 positif
  turun        Top5 jual   4492    -0,55    -3,50   40,7
  datar        Top5 beli   1388    -1,93    -2,77   38,7
  datar        Top5 jual   1926    -4,43    -4,58   34,7
  naik tipis   Top5 beli   1043    -6,46   -10,40   28,9
  naik tipis   Top5 jual    880    -9,47   -13,52   26,1
  naik banyak  Top5 beli    655   -11,81   -17,99   24,3   <- sel terburuk
  naik banyak  Top5 jual    366   -11,55   -20,97   25,4

Dua hal yang dikatakan tabel ini:

1. Arus Top5 MEMANG menambah informasi -- tapi hanya dengan syarat. Di
   setiap kelompok harga kecuali "naik banyak", Top5 beli unggul 2-4 poin
   persen win rate dibanding Top5 jual. Jadi bukan omong kosong.

2. Begitu harga sudah lari >20%, keunggulan itu HILANG SAMA SEKALI: Top5
   beli 24,3% vs Top5 jual 25,4% -- membeli justru sedikit lebih buruk, dan
   selnya paling buruk di seluruh papan (median -17,99%). Inilah "akumulasi
   palsu" versi yang benar-benar terukur: bukan soal berapa banyak broker
   yang jual, tapi soal Top5 yang terlihat mengakumulasi saham yang sudah
   terlanjur naik banyak.

Setup terbaiknya justru kebalikan dari yang enak dilihat: harga TURUN
sementara Top5 net beli -- satu-satunya sel dengan rata-rata positif.

DAN EFEKNYA HANYA ADA DI JANGKA PENDEK
Grid dikalibrasi ulang untuk window 40 dan 60 hari, dan hasilnya BERUBAH
ARAH pada sel "naik banyak":
    window 20h : beli 24,5% vs jual 25,4%  -> membeli tidak membantu
    window 40h : beli 27,7% vs jual 24,6%  -> membeli membantu (+3,1)
    window 60h : beli 36,5% vs jual 27,1%  -> membeli sangat membantu (+9,4)
Jadi "akumulasi palsu" adalah gejala jangka pendek: Top5 yang terlihat
membeli SELAMA 20 HARI TERAKHIR di saham yang sudah lari tidak berarti
apa-apa, tapi akumulasi yang BERTAHAN 40-60 hari di saham yang sama tetap
membawa informasi. Karena itu daftar sel palsu tidak dipatok di kode,
melainkan dihitung ulang dari grid tiap window (fake_cells_for()).

BATASNYA
- Periode Jan-Sep 2026, ~8 bulan, didominasi pasar turun. Semua angka
  absolut negatif; yang berarti adalah selisih antar sel, bukan tandanya.
- Ini rata-rata KELOMPOK, bukan ramalan untuk satu saham.
- "Top5" bukan satu pihak; komposisinya berganti tiap hari.
"""
import os
import time

import pandas as pd

from .config import DAILY_PATH

SUMMARY_DIR = os.path.join(DAILY_PATH, 'Summary')

C = {
    'DAYS': 20,               # jendela penilaian harga & arus (default)
    'MIN_ROW_RATIO': 0.7,
    'MIN_ROWS_FLOOR': 10,
    'MIN_ADV_VALUE': 200e6,   # Rp200 juta/hari
}

ALLOWED_DAYS = (20, 40, 60)

# Batas kelompok harga (persen perubahan selama jendela).
PRICE_BUCKETS = [
    (-1e9, -5.0, 'turun'),
    (-5.0, 5.0, 'datar'),
    (5.0, 20.0, 'naik tipis'),
    (20.0, 1e9, 'naik banyak'),
]

# Grid dikalibrasi ULANG untuk tiap panjang window -- tidak bisa dipakai
# ulang begitu saja, karena hasilnya BERUBAH ARAH tergantung window.
#
# Perhatikan sel ('naik banyak'):
#   window 20h : beli 24,5% vs jual 25,4%  -> membeli TIDAK membantu
#   window 40h : beli 27,7% vs jual 24,6%  -> membeli membantu (+3,1)
#   window 60h : beli 36,5% vs jual 27,1%  -> membeli sangat membantu (+9,4)
#
# Artinya "akumulasi palsu" itu gejala JANGKA PENDEK: Top5 yang terlihat
# membeli selama 20 hari terakhir di saham yang sudah lari tidak berarti
# apa-apa, tapi akumulasi yang bertahan 40-60 hari di saham yang sama tetap
# membawa informasi. Karena itu sel "palsu" TIDAK dipatok di kode, melainkan
# dihitung dari grid: sel disebut palsu kalau Top5 beli tidak mengungguli
# Top5 jual pada kelompok harga yang sama.
#
# Semua horizon = return 40 hari supaya antar-window bisa dibandingkan.
GRIDS = {
    20: {
        'baseline': {'n': 12273, 'mean': -3.15, 'median': -5.22, 'win': 36.5, 'horizon': 40},
        'cells': {
            ('turun', 'beli'): {'n': 1546, 'mean': 1.27, 'median': -2.44, 'win': 43.0},
            ('turun', 'jual'): {'n': 4480, 'mean': -0.58, 'median': -3.51, 'win': 40.7},
            ('datar', 'beli'): {'n': 1383, 'mean': -1.92, 'median': -2.74, 'win': 38.8},
            ('datar', 'jual'): {'n': 1926, 'mean': -4.43, 'median': -4.58, 'win': 34.7},
            ('naik tipis', 'beli'): {'n': 1043, 'mean': -6.46, 'median': -10.40, 'win': 28.9},
            ('naik tipis', 'jual'): {'n': 879, 'mean': -9.47, 'median': -13.52, 'win': 26.2},
            ('naik banyak', 'beli'): {'n': 650, 'mean': -11.67, 'median': -17.93, 'win': 24.5},
            ('naik banyak', 'jual'): {'n': 366, 'mean': -11.55, 'median': -20.97, 'win': 25.4},
        },
    },
    40: {
        'baseline': {'n': 9923, 'mean': -2.72, 'median': -4.35, 'win': 38.5, 'horizon': 40},
        'cells': {
            ('turun', 'beli'): {'n': 1502, 'mean': 2.57, 'median': 0.00, 'win': 48.7},
            ('turun', 'jual'): {'n': 4648, 'mean': -1.33, 'median': -2.70, 'win': 42.0},
            ('datar', 'beli'): {'n': 800, 'mean': -2.05, 'median': -2.50, 'win': 40.0},
            ('datar', 'jual'): {'n': 1151, 'mean': -6.57, 'median': -6.84, 'win': 28.1},
            ('naik tipis', 'beli'): {'n': 625, 'mean': -5.07, 'median': -7.67, 'win': 31.4},
            ('naik tipis', 'jual'): {'n': 403, 'mean': -10.84, 'median': -13.08, 'win': 21.6},
            ('naik banyak', 'beli'): {'n': 542, 'mean': -8.40, 'median': -14.19, 'win': 27.7},
            ('naik banyak', 'jual'): {'n': 252, 'mean': -13.41, 'median': -18.61, 'win': 24.6},
        },
    },
    60: {
        'baseline': {'n': 7409, 'mean': -2.38, 'median': -3.82, 'win': 40.9, 'horizon': 40},
        'cells': {
            ('turun', 'beli'): {'n': 1111, 'mean': -1.47, 'median': -1.92, 'win': 45.1},
            ('turun', 'jual'): {'n': 3799, 'mean': -1.57, 'median': -2.94, 'win': 42.8},
            ('datar', 'beli'): {'n': 520, 'mean': -1.10, 'median': -1.12, 'win': 43.3},
            ('datar', 'jual'): {'n': 637, 'mean': -3.78, 'median': -4.86, 'win': 32.2},
            ('naik tipis', 'beli'): {'n': 418, 'mean': -1.91, 'median': -4.24, 'win': 40.4},
            ('naik tipis', 'jual'): {'n': 277, 'mean': -7.26, 'median': -8.90, 'win': 30.7},
            ('naik banyak', 'beli'): {'n': 455, 'mean': -4.90, 'median': -11.74, 'win': 36.5},
            ('naik banyak', 'jual'): {'n': 192, 'mean': -10.61, 'median': -17.22, 'win': 27.1},
        },
    },
}


def grid_for(days):
    return GRIDS.get(days, GRIDS[C['DAYS']])


def fake_cells_for(days):
    """
    Sel "akumulasi palsu" dihitung dari grid, bukan dipatok: Top5 beli yang
    TIDAK mengungguli Top5 jual pada kelompok harga yang sama. Di window 20h
    ini menghasilkan ('naik banyak','beli'); di window 40h/60h tidak ada sel
    yang memenuhi -- dan itu memang temuannya.
    """
    cells = grid_for(days)['cells']
    out = set()
    for (pb, fb), stats in cells.items():
        if fb != 'beli':
            continue
        lawan = cells.get((pb, 'jual'))
        if lawan and stats['win'] <= lawan['win']:
            out.add((pb, fb))
    return out


def best_cell_for(days):
    cells = grid_for(days)['cells']
    return max(cells, key=lambda k: cells[k]['win']) if cells else None


# Penilaian dibaca dari selisih win rate terhadap baseline window itu,
# bukan dari tanda return absolutnya (periodenya pasar turun).
def verdict_for(cell, days):
    g = grid_for(days)
    stats = g['cells'].get(cell)
    if not stats:
        return 'netral', 'tidak ada data kelompok'
    diff = stats['win'] - g['baseline']['win']
    if diff >= 4:
        return 'hijau', 'historis di atas pasar'
    if diff >= 1:
        return 'kuning', 'historis setara pasar'
    if diff >= -5:
        return 'kuning', 'historis di bawah pasar'
    return 'merah', 'historis jauh di bawah pasar'


def _price_bucket(pct):
    for lo, hi, name in PRICE_BUCKETS:
        if lo < pct <= hi:
            return name
    return 'datar'


def _read(stock):
    path = os.path.join(SUMMARY_DIR, '%s_Summary.csv' % stock)
    if not os.path.exists(path):
        return None
    try:
        df = pd.read_csv(path)
    except Exception:
        return None
    if 'Date' not in df.columns or df.empty:
        return None
    df['Date'] = pd.to_datetime(df['Date'], format='%d-%b-%y', errors='coerce')
    df = df.dropna(subset=['Date']).sort_values('Date').reset_index(drop=True)
    return df if len(df) else None


def measure(stock, days=None, df=None, fake_cells=None, best_cell=None):
    """Tempatkan satu saham ke dalam grid. None kalau datanya tidak cukup."""
    days = days or C['DAYS']
    if fake_cells is None:
        fake_cells = fake_cells_for(days)
    if best_cell is None:
        best_cell = best_cell_for(days)
    if df is None:
        df = _read(stock)
    if df is None:
        return None

    win = df.tail(days)
    if len(win) < max(C['MIN_ROWS_FLOOR'], int(days * C['MIN_ROW_RATIO'])):
        return None

    def num(col):
        return (pd.to_numeric(win[col], errors='coerce')
                if col in win.columns else pd.Series(dtype=float))

    close = num('Close').dropna()
    if len(close) < 2:
        return None
    volume = num('Volume').fillna(0.0)
    net_top5 = num('Net Top5 All Lot').fillna(0.0)
    retail = num('Retail').fillna(0.0)
    total_seller = num('Total Seller')
    total_buyer = num('Total Buyer')

    last_close = float(close.iloc[-1])
    first_close = float(close.iloc[0])
    adv_value = float(volume.mean() or 0.0) * last_close
    if adv_value < C['MIN_ADV_VALUE'] or first_close <= 0:
        return None

    price_chg = (last_close - first_close) / first_close * 100.0
    top5_lot = float(net_top5.sum())
    pbucket = _price_bucket(price_chg)
    fbucket = 'beli' if top5_lot > 0 else 'jual'
    cell = (pbucket, fbucket)
    g = grid_for(days)
    stats = g['cells'].get(cell, {})
    verdict, verdict_label = verdict_for(cell, days)

    # Ditampilkan sebagai konteks saja -- diuji dan TIDAK terbukti memisahkan,
    # jadi tidak ikut menentukan penilaian.
    seller_ratio = None
    if total_seller.notna().any() and total_buyer.notna().any():
        tb = float(total_buyer.mean() or 0.0)
        if tb > 0:
            seller_ratio = round(float(total_seller.mean() or 0.0) / tb, 2)

    return {
        'stock': stock,
        'days': int(len(win)),
        'price_chg_pct': round(price_chg, 2),
        'top5_lot': round(top5_lot, 0),
        'retail_lot': round(float(retail.sum()), 0),
        'last_close': round(last_close, 2),
        'adv_value_juta': round(adv_value / 1e6, 1),
        'price_bucket': pbucket,
        'flow_bucket': fbucket,
        'cell': '%s + Top5 %s' % (pbucket, fbucket),
        'cell_n': stats.get('n'),
        'cell_mean': stats.get('mean'),
        'cell_median': stats.get('median'),
        'cell_win': stats.get('win'),
        'vs_baseline': (round(stats['win'] - g['baseline']['win'], 1) if stats else None),
        'verdict': verdict,
        'verdict_label': verdict_label,
        'is_fake': cell in fake_cells,
        'is_best': cell == best_cell,
        'seller_ratio': seller_ratio,
    }


def scan(stocks=None, days=None):
    """
    Tempatkan sekumpulan saham (default: seluruh emiten yang punya Summary)
    ke dalam grid, diurutkan dari sel terburuk lebih dulu -- gunanya
    menyaring, bukan memilih pemenang.
    """
    import glob

    days = days if days in ALLOWED_DAYS else C['DAYS']
    if stocks is None:
        stocks = sorted(os.path.basename(p)[:4]
                        for p in glob.glob(os.path.join(SUMMARY_DIR, '*_Summary.csv')))

    fake_cells = fake_cells_for(days)
    best_cell = best_cell_for(days)
    rows = []
    for stock in stocks:
        row = measure(stock, days=days, fake_cells=fake_cells, best_cell=best_cell)
        if row:
            rows.append(row)

    rows.sort(key=lambda r: (r['cell_win'] if r['cell_win'] is not None else 999,
                             -abs(r['price_chg_pct'])))

    counts = {}
    for r in rows:
        counts[r['cell']] = counts.get(r['cell'], 0) + 1

    g = grid_for(days)
    return {
        'available': True,
        'days': days,
        'allowed_days': list(ALLOWED_DAYS),
        'rows': rows,
        'total': len(rows),
        'counts': counts,
        'fake_count': sum(1 for r in rows if r['is_fake']),
        'best_count': sum(1 for r in rows if r['is_best']),
        'fake_cells': ['%s|%s' % c for c in sorted(fake_cells)],
        'best_cell': ('%s|%s' % best_cell) if best_cell else None,
        'grid': {'%s|%s' % k: v for k, v in g['cells'].items()},
        'baseline': g['baseline'],
        'as_of': time.strftime('%Y-%m-%d %H:%M'),
    }
