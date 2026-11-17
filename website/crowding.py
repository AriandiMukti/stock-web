"""
Lensa keramaian: seberapa ramai sebuah saham diperdagangkan hari ini,
dan apa artinya menurut backtest.

KENAPA INI ADA
Dua analisis di app ini menemukan bahwa "keramaian" berkaitan dengan
hasil yang lebih buruk: Scanner Lab (lonjakan volume) dan Screen Eval
(nilai transaksi besar). Modul ini menerjemahkannya jadi penilaian yang
bisa dibaca sekilas di seluruh watchlist.

Matriksnya dihitung dari POPULASI UMUM (98.958 pengamatan, semua saham
semua hari) -- bukan dari sinyal scanner atau kemunculan screen, karena
saham watchlist bukan salah satu dari keduanya. Lihat catatan panjang di
atas GRID soal kenapa ini sempat salah dua kali.

YANG DITUNJUKKAN DATANYA
Nilai transaksi lebih menentukan daripada volume. Saham bernilai kecil
(< 20 M) rata-rata sekitar 0% apa pun volumenya, sampai volume melewati
5x. Saham bernilai besar memburuk seiring volume naik -- pada tier
50-150 M: -4,27 -> -6,49 -> -8,37 -> -11,43.

BATASNYA
Ini bukan sinyal beli/jual, dan bukan ramalan untuk saham tertentu.
Angka yang ditampilkan adalah rata-rata historis KELOMPOK tempat saham
itu berada hari ini. Win rate tertinggi pun cuma 45%, dan periodenya
~8 bulan yang didominasi pasar turun.
"""
import os

import pandas as pd

from .config import DAILY_PATH

SUMMARY_DIR = os.path.join(DAILY_PATH, 'Summary')

# Matriks hasil historis: rata-rata return 20 hari untuk tiap kombinasi
# (volume relatif x nilai transaksi), dari 98.958 pengamatan seluruh
# bursa, semua saham semua hari.
#
# DUA KALI DIPERBAIKI, DAN KEDUANYA LAYAK DICATAT.
#
# Versi pertama memakai label aman/waspada/bahaya buatan sendiri dengan
# aturan "ambil sisi terburuk". Hasilnya menyesatkan: BBRI, ADRO, TPIA
# semua ditandai "sangat ramai" padahal volumenya di bawah rata-rata --
# yang memicu cuma nilai transaksi besar, dan itu melekat pada UKURAN
# perusahaan, bukan keramaian sesaat.
#
# Versi kedua mengganti label dengan angka sel yang terukur, tapi
# matriksnya diambil dari 6.235 KEMUNCULAN SCREEN. Itu cacat yang lebih
# halus dan lebih serius: screen Consol secara eksplisit mensyaratkan
# volume MENURUN (volume konsol < 0,75x volume surge), jadi bucket
# sepinya berisi "sepi setelah lonjakan" -- populasi yang sama sekali
# beda dari saham watchlist sembarang yang dinilai halaman ini.
# Menerapkan statistik satu populasi ke populasi lain menghasilkan angka
# yang terlihat berwibawa tapi tidak berlaku. Terbukti keduanya memang
# tidak sepakat di sudut sepi: pada sinyal scanner (<1x, <20M) = -0,73%
# alias terbaik, pada kemunculan screen sel yang sama = -2,55% alias
# terburuk.
#
# Versi sekarang dihitung dari POPULASI UMUM -- semua saham, semua hari,
# tanpa syarat apa pun. Itu referensi yang benar untuk menilai saham
# watchlist sembarang, dan sampelnya 16x lebih besar.
#
# Yang ditunjukkan matriks baru berbeda dari cerita awal: NILAI TRANSAKSI
# yang dominan, volume memperkuatnya. Di saham bernilai kecil (< 20 M)
# volume nyaris tidak berpengaruh sampai melewati 5x. Efek volume paling
# jelas justru di saham bernilai besar: pada tier 50-150 M, hasilnya
# turun berurutan -4,27 -> -6,49 -> -8,37 -> -11,43 seiring volume naik.
VOL_BINS = [(0, 1, '< 1x'), (1, 2, '1 - 2x'), (2, 5, '2 - 5x'), (5, float('inf'), '> 5x')]
VALUE_BINS = [(0, 20, '< 20 M'), (20, 50, '20 - 50 M'),
              (50, 150, '50 - 150 M'), (150, float('inf'), '> 150 M')]

# (rata-rata fwd20 %, win rate %, jumlah sampel)
GRID = {
    ('< 1x', '< 20 M'): (-0.13, 45.0, 64850), ('< 1x', '20 - 50 M'): (-3.79, 41.6, 2436),
    ('< 1x', '50 - 150 M'): (-4.27, 41.2, 1840), ('< 1x', '> 150 M'): (-3.81, 43.2, 1377),
    ('1 - 2x', '< 20 M'): (0.09, 45.2, 14566), ('1 - 2x', '20 - 50 M'): (-3.75, 41.0, 1345),
    ('1 - 2x', '50 - 150 M'): (-6.49, 34.1, 975), ('1 - 2x', '> 150 M'): (-6.21, 33.2, 1036),
    ('2 - 5x', '< 20 M'): (0.25, 43.1, 6236), ('2 - 5x', '20 - 50 M'): (-5.39, 31.6, 566),
    ('2 - 5x', '50 - 150 M'): (-8.37, 33.8, 447), ('2 - 5x', '> 150 M'): (-7.74, 35.9, 443),
    ('> 5x', '< 20 M'): (-2.07, 37.9, 2182), ('> 5x', '20 - 50 M'): (-7.72, 27.3, 322),
    ('> 5x', '50 - 150 M'): (-11.43, 26.9, 216), ('> 5x', '> 150 M'): (-8.29, 35.5, 121),
}

# Baseline populasi yang SAMA dengan matriks di atas. Angka -1,33% yang
# dipakai Scanner Lab berasal dari perhitungan dengan penyaringan berbeda;
# mencampurnya di sini akan membuat kolom "vs pasar" membandingkan dua
# populasi yang tidak sebanding.
MARKET_BASELINE_20D = -0.67

# Label sengaja MENDESKRIPSIKAN HASIL, bukan menghakimi kondisi. Versi
# sebelumnya memakai "Wajar / Perlu dilihat / Ramai / Sangat ramai" --
# campur aduk, karena tiga di antaranya menggambarkan keramaian sedangkan
# "Perlu dilihat" menggambarkan tindakan. Akibatnya sel paling sepi bisa
# dapat label lebih buruk daripada sel yang lebih ramai, padahal seluruh
# premisnya justru sebaliknya. Sekarang keramaian dilaporkan terpisah
# sebagai fakta netral, dan label ini bicara khusus soal hasil historis.
def _severity_from(vs_baseline):
    if vs_baseline >= -1:
        return 'setara'
    if vs_baseline >= -4:
        return 'bawah'
    if vs_baseline >= -7:
        return 'jauh'
    return 'sangat_jauh'


SEVERITY = {'setara': 0, 'bawah': 1, 'jauh': 2, 'sangat_jauh': 3}
VERDICT_LABEL = {
    'setara': 'Setara pasar',
    'bawah': 'Di bawah pasar',
    'jauh': 'Jauh di bawah pasar',
    'sangat_jauh': 'Sangat jauh di bawah pasar',
}

# Deskripsi keramaian, murni faktual, tidak mengandung penilaian.
CROWD_DESC = {'< 1x': 'sepi', '1 - 2x': 'normal',
              '2 - 5x': 'ramai', '> 5x': 'sangat ramai'}


def _bin_label(value, bins):
    if value is None or pd.isna(value):
        return None
    for lo, hi, label in bins:
        if lo <= value < hi:
            return label
    return None


def measure(stock, df=None):
    """
    Ukur keramaian satu saham dari data harian terakhir.

    vol_mult dihitung terhadap rata-rata 20 hari SEBELUMNYA (di-shift satu
    hari) supaya hari yang sedang dinilai tidak ikut mengangkat rata-rata
    pembandingnya sendiri.
    """
    if df is None:
        path = os.path.join(SUMMARY_DIR, '%s_Summary.csv' % stock)
        if not os.path.exists(path):
            return None
        try:
            df = pd.read_csv(path).fillna(0)
        except Exception:
            return None
    if df is None or df.empty or 'Date' not in df.columns:
        return None

    df = df.copy()
    df['Date'] = pd.to_datetime(df['Date'], format='%d-%b-%y', errors='coerce')
    df = df.dropna(subset=['Date']).sort_values('Date')
    if len(df) < 22:
        return None
    for col in ['Open', 'Close', 'Volume']:
        df[col] = pd.to_numeric(df.get(col), errors='coerce').fillna(0)

    last = df.iloc[-1]
    vol_avg20 = df['Volume'].iloc[-21:-1].mean()
    vol_mult = float(last['Volume'] / vol_avg20) if vol_avg20 > 0 else None
    value_b = float((last['Open'] + last['Close']) / 2 * last['Volume'] / 1e9)

    vol_bin = _bin_label(vol_mult, VOL_BINS)
    val_bin = _bin_label(value_b, VALUE_BINS)
    cell = GRID.get((vol_bin, val_bin))
    if cell is None:
        return None

    mean, win_rate, sample = cell
    vs_baseline = round(mean - MARKET_BASELINE_20D, 2)
    verdict = _severity_from(vs_baseline)

    return {
        'stock': stock,
        'date': last['Date'].strftime('%Y-%m-%d'),
        'close': float(last['Close']),
        'vol_mult': round(vol_mult, 2) if vol_mult is not None else None,
        'vol_bin': vol_bin,
        # Keramaian dilaporkan sebagai fakta terpisah, tidak dicampur ke
        # dalam label hasil -- itu yang bikin versi lama membingungkan.
        'crowd_desc': CROWD_DESC.get(vol_bin),
        'value_b': round(value_b, 2),
        'value_bin': val_bin,
        # Angka historis KELOMPOK ini, bukan prediksi untuk saham ini.
        'cell_mean': mean,
        'cell_win_rate': win_rate,
        'cell_n': sample,
        'vs_baseline': vs_baseline,
        'verdict': verdict,
        'verdict_label': VERDICT_LABEL[verdict],
        'severity': SEVERITY[verdict],
        'why': ('Volume %s (%s), nilai transaksi %s. Saham di kombinasi ini '
                'historisnya %.2f%% dalam 20 hari, menang %.1f%% (n=%s) — '
                '%+.2fpp dibanding rata-rata pasar %.2f%%.'
                % (vol_bin, CROWD_DESC.get(vol_bin, '-'), val_bin, mean,
                   win_rate, f'{sample:,}'.replace(',', '.'), vs_baseline,
                   MARKET_BASELINE_20D)),
    }


def measure_many(stocks):
    """
    Ukur sekumpulan saham, diurutkan dari yang paling ramai.

    Diurutkan begitu karena kegunaan utama halaman ini adalah MENYARING
    yang berisiko, bukan memilih pemenang -- yang perlu dilihat lebih dulu
    adalah yang paling merah.
    """
    rows = []
    for stock in stocks:
        result = measure(stock)
        if result:
            rows.append(result)
    rows.sort(key=lambda r: (-r['severity'], -(r['vol_mult'] or 0)))

    counts = {'setara': 0, 'bawah': 0, 'jauh': 0, 'sangat_jauh': 0}
    for row in rows:
        counts[row['verdict']] += 1

    return {'available': True, 'rows': rows, 'counts': counts,
            'total': len(rows), 'missing': len(stocks) - len(rows)}
