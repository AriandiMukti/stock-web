"""
Fakta penyaring per emiten: bahan untuk bar filter bersama di semua daftar.

KENAPA MODUL INI ADA
Halaman tempat keputusan benar-benar diambil -- Portfolio, Best, Best Low,
Pattern Up -- sampai sekarang tidak punya penyaring sama sekali. Semua
saringan yang sudah terbukti berguna justru terkubur di halaman riset yang
jarang dibuka.

FILOSOFINYA: MEMBUANG, BUKAN MEMILIH.
Seluruh pengujian di app ini menunjukkan tidak ada aturan beli yang
bertahan di luar sampel (lihat screener_side.py dan pattern_miner.py).
Jadi penyaring di sini TIDAK berpura-pura memilih pemenang. Ia hanya
membuang yang tidak layak dinilai -- dan untuk itu tidak dibutuhkan klaim
prediktif sama sekali, cuma alasan kenapa sesuatu tak bisa dipercaya:

  1. DATA BASI. Emiten yang berkas hariannya tertinggal lebih dari 30 hari.
     Bukan sekadar lemah -- setiap metrik 20/60 hari di atasnya menghitung
     jendela yang sudah lewat, jadi angkanya menyesatkan, bukan kasar.

  2. TERLALU SEPI. Nilai transaksi harian di bawah Rp200 juta. Ambang ini
     bukan karangan: itu MIN_ADV milik pattern_miner, artinya emiten ini
     tidak pernah ikut satu pun pengujian yang mendasari app ini. Apa pun
     yang ditampilkan tentang mereka belum pernah divalidasi.

  3. SISI B. Top5 net beli 20 hari DAN harga 20 hari sudah naik >5%.
     Kelompok ini kalah di dalam sampel (-4,25 pp) maupun di luar sampel
     10 tahun (-0,95 pp win rate). Ini satu-satunya saringan yang berdiri
     di atas temuan statistik, dan karena itu paling lemah dasarnya --
     selisihnya kecil dan sempat berbalik di 2020-2022.

KENAPA SISI B DITANDAI, BUKAN DIBUANG OTOMATIS
Membuangnya diam-diam berarti memperlakukan temuan lemah seolah kuat --
persis kesalahan yang sudah berulang kali dikoreksi di modul lain.
Bawaannya: ditandai. Membuang harus dipilih sendiri oleh pengguna.

KENAPA TIDAK ADA YANG DISEMBUNYIKAN DIAM-DIAM
Setiap baris yang tersaring tetap bisa ditampilkan, lengkap dengan
alasannya ("data basi 47 hari"), bukan sekadar lenyap. Daftar yang
menyembunyikan tanpa penjelasan akan kehilangan kepercayaan pemakainya,
dan itu lebih merugikan daripada daftar yang berisik.

LAPIS
Dihitung dari nilai transaksi harian rata-rata 120 hari terakhir, bukan
kapitalisasi pasar (yang butuh jumlah saham beredar dan tidak selalu ada):
    Lapis 1  >= Rp100 M/hari      (32 emiten)
    Lapis 2  Rp10-100 M/hari      (128 emiten)
    Lapis 3  Rp200 jt - 10 M      (500 emiten)
    terlalu sepi < Rp200 jt       (210 emiten)
"""
try:
    from .runtime_paths import runtime_file as _runtime_file, market_file as _market_file, WEBSITE_DIR as _WEBSITE_DIR, PROJECT_DIR as _PROJECT_DIR, RUNTIME_DIR as _RUNTIME_DIR
except ImportError:
    from website.runtime_paths import runtime_file as _runtime_file, market_file as _market_file, WEBSITE_DIR as _WEBSITE_DIR, PROJECT_DIR as _PROJECT_DIR, RUNTIME_DIR as _RUNTIME_DIR
import os
import time
import glob
import pickle

import numpy as np
import pandas as pd

from .config import DAILY_PATH

SUMMARY_DIR = os.path.join(DAILY_PATH, 'Summary')
CACHE_FILE = str(_runtime_file('', 'stock_filter_cache.pkl'))
def _sumber_terbaru():
    """Hanya berkas Summary -- modul ini tidak membaca sumber lain."""
    from .kesegaran import summary_terbaru
    return summary_terbaru()

LOOK = 20
BASI_AMBANG = 30            # hari kalender
SEPI_AMBANG = 2e8           # Rp200 juta/hari -- MIN_ADV pattern_miner
TURUN_AMBANG = -5.0
NAIK_AMBANG = 5.0

LAPIS1 = 1e11               # Rp100 M/hari
LAPIS2 = 1e10               # Rp10 M/hari

# Kalimat alasan ditulis seperti orang bicara, dan selalu memuat angkanya --
# pembaca harus bisa menilai sendiri apakah penyaringannya masuk akal untuk
# emiten itu. Harus sama persis dengan static/js/stock_filter.js.
ALASAN = {
    'basi': 'Data terakhirnya %d hari lalu, jadi semua hitungan di app ini sudah basi.',
    'sepi': 'Cuma Rp%s sehari — terlalu sepi, order Anda sendiri yang akan menggerakkan harga.',
    'sisi_b': 'Harganya sudah naik %.1f%% dalam 20 hari. Kalau masuk sekarang, '
              'Anda masuk setelah harganya lari.',
}


def _lapis(nilai):
    if not np.isfinite(nilai):
        return None
    if nilai >= LAPIS1:
        return 'Lapis 1'
    if nilai >= LAPIS2:
        return 'Lapis 2'
    if nilai >= SEPI_AMBANG:
        return 'Lapis 3'
    return 'terlalu sepi'


def _rupiah(n):
    if not np.isfinite(n):
        return '—'
    if n >= 1e12:
        return '%.1f T' % (n / 1e12)
    if n >= 1e9:
        return '%.1f M' % (n / 1e9)
    if n >= 1e6:
        return '%.0f jt' % (n / 1e6)
    return '%.0f' % n


def _bangun():
    hasil = {}
    terbaru = None
    for path in glob.glob(os.path.join(SUMMARY_DIR, '*_Summary.csv')):
        stock = os.path.basename(path)[:4]
        try:
            d = pd.read_csv(path, usecols=['Date', 'Close', 'Volume', 'Net Top5 All Lot'])
            d['Date'] = pd.to_datetime(d['Date'], format='%d-%b-%y', errors='coerce')
            d = d.dropna(subset=['Date']).sort_values('Date')
        except Exception:
            continue
        c = pd.to_numeric(d['Close'], errors='coerce')
        v = pd.to_numeric(d['Volume'], errors='coerce')
        t = pd.to_numeric(d['Net Top5 All Lot'], errors='coerce').fillna(0.0)
        ok = c.notna() & v.notna()
        if ok.sum() < 25:
            continue
        tgl_akhir = d['Date'].max()
        terbaru = tgl_akhir if terbaru is None or tgl_akhir > terbaru else terbaru
        nilai = float((c[ok] * v[ok]).tail(120).mean())
        cc = c[ok].values
        harga20 = ((cc[-1] - cc[-LOOK - 1]) / cc[-LOOK - 1] * 100.0) if len(cc) > LOOK else np.nan
        top5_20 = float(t.tail(LOOK).sum())
        hasil[stock] = {
            'nilai': nilai, 'tgl': tgl_akhir, 'harga20': harga20,
            'top5_20': top5_20, 'n_hari': int(ok.sum()),
        }

    out = {}
    for stock, r in hasil.items():
        basi = int((terbaru - r['tgl']).days) if terbaru is not None else 0
        h20, t20 = r['harga20'], r['top5_20']
        if np.isfinite(h20) and h20 < TURUN_AMBANG:
            sisi = 'A'
        elif np.isfinite(h20) and t20 > 0 and h20 > NAIK_AMBANG:
            sisi = 'B'
        else:
            sisi = 'lain'
        out[stock] = {
            'lapis': _lapis(r['nilai']),
            'nilai': round(r['nilai'], 0) if np.isfinite(r['nilai']) else None,
            'nilai_label': _rupiah(r['nilai']),
            'basi': basi,
            'sisi': sisi,
            'harga20': round(float(h20), 2) if np.isfinite(h20) else None,
            'n_hari': r['n_hari'],
        }
    return out, terbaru


def facts(force=False):
    """{kode: fakta} untuk seluruh emiten. Di-cache 6 jam."""
    if not force and os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, 'rb') as fh:
                cached = pickle.load(fh)
            if cached.get('ts', 0) >= _sumber_terbaru():
                return cached['data']
        except Exception:
            pass

    t0 = time.time()
    data, terbaru = _bangun()
    hitung = {'Lapis 1': 0, 'Lapis 2': 0, 'Lapis 3': 0, 'terlalu sepi': 0}
    sisi_hitung = {'A': 0, 'B': 0, 'lain': 0}
    n_basi = 0
    for r in data.values():
        if r['lapis'] in hitung:
            hitung[r['lapis']] += 1
        sisi_hitung[r['sisi']] += 1
        if r['basi'] > BASI_AMBANG:
            n_basi += 1

    hasil = {
        'available': True,
        'facts': data,
        'total': len(data),
        'lapis_counts': hitung,
        'sisi_counts': sisi_hitung,
        'n_basi': n_basi,
        'ambang': {'basi': BASI_AMBANG, 'sepi': SEPI_AMBANG,
                   'turun': TURUN_AMBANG, 'naik': NAIK_AMBANG},
        'alasan': ALASAN,
        'tanggal_terbaru': str(terbaru.date()) if terbaru is not None else None,
        'durasi_detik': round(time.time() - t0, 1),
        'as_of': time.strftime('%Y-%m-%d %H:%M'),
    }
    try:
        with open(CACHE_FILE, 'wb') as fh:
            pickle.dump({'ts': time.time(), 'data': hasil}, fh)
    except Exception:
        pass
    return hasil
