"""
Mesin penemu pola: menguji ribuan kombinasi metrik secara otomatis, bukan
satu per satu dengan tangan.

KENAPA INI ADA
Cara app ini menemukan pola selama ini: manusia menebak satu hipotesis, lalu
mengujinya. Sesi pembangunan Serapan Float dan Akumulasi Palsu berjalan
persis begitu -- tiga hipotesis diuji dengan tangan, dua gagal ("float
mengering", "penjual melebar"), satu berhasil (harga x arus). Itu kerja yang
seharusnya dilakukan mesin.

Modul ini membalik urutannya: enumerasi SEMUA kombinasi 1-3 arah dari metrik
yang tersedia, uji semuanya terhadap return ke depan, lalu tampilkan yang
paling menyimpang dari baseline.

MASALAH BESARNYA: MENGUJI RIBUAN HIPOTESIS ITU BERBAHAYA
Kalau 5.000 kombinasi diuji pada data acak sekalipun, sekitar 250 di antaranya
akan tampak "signifikan pada p<0,05" murni karena kebetulan. Menampilkan
temuan terbaik tanpa koreksi = memamerkan noise. Karena itu modul ini:

1. Menghitung p-value dua arah untuk tiap sel lewat uji proporsi terhadap
   baseline (win rate sel vs win rate populasi).
2. Mengoreksi pengujian berganda dengan Benjamini-Hochberg (FDR), bukan
   sekadar p mentah. Kolom `q` adalah p yang sudah dikoreksi.
3. Mensyaratkan sampel minimum, supaya sel berisi 12 pengamatan tidak pernah
   muncul sebagai "penemuan".
4. Melaporkan berapa banyak yang diuji, supaya pembaca tahu skala pencariannya.

Sel yang lolos q<0,10 layak dilihat. Yang tidak lolos TETAP DITAMPILKAN kalau
diminta, tapi ditandai jelas sebagai belum lolos koreksi.

BATASNYA
- Periode Jan-Sep 2026 (~8 bulan), didominasi pasar turun; semua return
  absolut negatif, jadi yang berarti adalah selisih terhadap baseline.
- Pengamatan tumpang tindih (jendela geser tiap 5 hari), jadi mereka tidak
  benar-benar independen -- p-value di sini lebih optimistis dari
  seharusnya. Perlakukan sebagai penyaring kandidat, bukan bukti akhir.
- Ini menemukan KORELASI dalam satu periode. Belum diuji di luar sampel.
"""
try:
    from .runtime_paths import runtime_file as _runtime_file, market_file as _market_file, WEBSITE_DIR as _WEBSITE_DIR, PROJECT_DIR as _PROJECT_DIR, RUNTIME_DIR as _RUNTIME_DIR
except ImportError:
    from website.runtime_paths import runtime_file as _runtime_file, market_file as _market_file, WEBSITE_DIR as _WEBSITE_DIR, PROJECT_DIR as _PROJECT_DIR, RUNTIME_DIR as _RUNTIME_DIR
import glob
import logging
import math
import os
import pickle
import time
from itertools import combinations

import numpy as np
import pandas as pd

from .config import DAILY_PATH

logger = logging.getLogger(__name__)

SUMMARY_DIR = os.path.join(DAILY_PATH, 'Summary')
CACHE_FILE = str(_runtime_file('', 'pattern_miner_cache.pkl'))
def _sumber_terbaru():
    """Hanya berkas Summary -- modul ini tidak membaca sumber lain."""
    from .kesegaran import summary_terbaru
    return summary_terbaru()

C = {
    'LOOK': 20,          # jendela pengukuran metrik
    'FWD': 40,           # horizon return
    'STEP': 5,           # jarak antar pengamatan (hari)
    'MIN_ADV': 200e6,    # Rp200 juta/hari
    'MIN_N': 120,        # sampel minimum sebuah sel supaya ikut diuji
    'MAX_ORDE': 3,       # kombinasi sampai 3 metrik
    'Q_AMBANG': 0.10,    # ambang FDR untuk disebut lolos
}

# Metrik dan cara membaginya. Batas dipilih supaya tiap keranjang berisi
# cukup banyak pengamatan, bukan supaya hasilnya bagus.
FITUR = {
    'harga': {
        'label': 'Posisi harga 20h',
        'bins': [(-1e9, -5, 'turun'), (-5, 5, 'datar'), (5, 20, 'naik tipis'), (20, 1e9, 'naik banyak')],
    },
    'top5': {
        'label': 'Arus Top5 20h',
        'bins': [(-1e18, 0, 'jual'), (0, 1e18, 'beli')],
    },
    'ritel': {
        'label': 'Arus ritel 20h',
        'bins': [(-1e18, 0, 'ritel jual'), (0, 1e18, 'ritel beli')],
    },
    'volume': {
        'label': 'Volume vs 20h',
        'bins': [(0, 1, 'sepi'), (1, 2, 'normal'), (2, 1e9, 'ramai')],
    },
    'nilai': {
        'label': 'Nilai transaksi',
        'bins': [(0, 1e9, '< 1 M'), (1e9, 1e10, '1-10 M'), (1e10, 1e18, '> 10 M')],
    },
    'pembeli': {
        'label': 'Penjual vs pembeli',
        'bins': [(0, 0.9, 'pembeli ramai'), (0.9, 1.1, 'seimbang'), (1.1, 1e9, 'penjual ramai')],
    },
    'volatil': {
        'label': 'Volatilitas 20h',
        'bins': [(0, 2, 'tenang'), (2, 4, 'sedang'), (4, 1e9, 'liar')],
    },
}


# ==========================================================================
# UJI LUAR SAMPEL 10 TAHUN -- HASILNYA MENGECILKAN SEMUA ANGKA DI BAWAH.
#
# Semua "edge" yang dihasilkan modul ini berasal dari folder Daily:
# Jan-Sep 2026, satu rezim pasar turun (baseline win cuma 36,5%). Koreksi
# FDR di dalamnya TIDAK melindungi dari kebetulan periode -- ia hanya
# mengendalikan pengujian berganda di dalam satu dataset.
#
# Diuji pada folder Test: 21 emiten, 2016-2025, fitur direkonstruksi dari
# JSON mentah dan DIVERIFIKASI dulu di periode tumpang tindih 2026 --
# Net Top5 All Lot korelasi 1,000 (definisinya: 5 net-buyer teratas +
# 5 net-seller terbawah), Total Buyer/Seller 1,000, rasio volume 0,890.
# Fitur `ritel` tidak bisa direkonstruksi, jadi pola yang memakainya tidak
# teruji.
#
#   pola lolos FDR di kalibrasi          450
#   tak teruji (pakai fitur ritel)       147
#   tak teruji (sel terlalu kecil)        23
#   bisa diuji                           280
#
#   tanda bertahan di luar sampel     146/280 = 52,1%   (kebetulan = 50%)
#   uji binomial vs 50%                z=0,72, p=0,47
#   korelasi edge in-sample vs luar     0,099
#   rata-rata edge in-sample           -4,57 pp
#   rata-rata edge luar sampel         +0,95 pp
#
# Sebagai kelompok, 450 pola itu TIDAK LEBIH BAIK DARI LEMPAR KOIN.
#
# 14 pola bertahan lewat saringan ketat (tanda sama, signifikan >2se,
# n>=300, >=70% tahun searah), dengan konsistensi tingkat-tahun 73,4%
# (94/128, z=5,30). Tapi ke-14 itu DIPILIH setelah melihat hasil luar
# sampel, jadi besar edge-nya (+3 s.d. +9 pp) mengandung bias seleksi.
#
# Untuk menghindari sirkularitas, temanya dirumuskan jadi dua aturan
# tunggal lalu diuji SEKALI (tanpa penyaringan lanjutan):
#
#   A. harga 20h turun (beli saat lemah)     n=2462  edge +1,37  7/10 tahun
#   B. Top5 beli + harga naik (ikut bandar)  n=1998  edge -0,95  7/10 tahun
#
# Arahnya bertahan -- membeli saat lemah lebih baik daripada mengikuti
# akumulasi Top5 saat harga sudah naik -- tapi besarnya hanya ~1 poin
# persen, bukan 6-18 pp seperti tabel in-sample. Keduanya tidak signifikan
# sendiri-sendiri (t=1,36 dan -0,85; 7/10 tahun punya p=0,17).
#
# CARA MEMBACA HASIL MODUL INI: urutan dan arah pola masih informatif,
# ANGKA EDGE-NYA TIDAK. Perlakukan sebagai daftar hipotesis untuk diuji,
# bukan daftar sinyal siap pakai.
# ==========================================================================

VALIDASI_OOS = {
    'sumber': 'folder Test: 21 emiten, 2016-2025 (di luar periode kalibrasi)',
    'verifikasi_fitur': {
        'Net Top5 All Lot': 1.000, 'Total Buyer': 1.000,
        'Total Seller': 1.000, 'rasio volume 20h': 0.890,
        'ritel': None,
    },
    'n_lolos_fdr': 450,
    'n_tak_teruji_ritel': 147,
    'n_tak_teruji_kecil': 23,
    'n_diuji': 280,
    'n_tanda_bertahan': 146,
    'persen_bertahan': 52.1,
    'p_binomial': 0.4733,
    'korelasi_edge': 0.099,
    'edge_in_rata2': -4.57,
    'edge_out_rata2': 0.95,
    'n_saringan_ketat': 14,
    'konsistensi_tahun': '94/128 = 73,4% (z=5,30)',
    'aturan_ringkas': [
        {'nama': 'harga 20h turun (beli saat lemah)', 'n': 2462,
         'edge': 1.37, 'tahun': '7/10', 't': 1.36},
        {'nama': 'Top5 beli + harga naik (ikut bandar)', 'n': 1998,
         'edge': -0.95, 'tahun': '7/10', 't': -0.85},
    ],
    'kesimpulan': ('Sebagai kelompok, pola-pola ini tidak lebih baik dari lempar koin '
                   '(52,1% vs 50%, p=0,47). Arah umumnya bertahan -- beli saat lemah '
                   'lebih baik daripada mengikuti akumulasi Top5 saat harga sudah naik -- '
                   'tapi besarnya hanya ~1 poin persen, bukan 6-18 pp seperti angka '
                   'in-sample. Pakai sebagai daftar hipotesis, bukan sinyal siap pakai.'),
}


def mine_if_cached(max_orde=None, min_n=None):
    """
    Sama seperti mine(), TAPI TIDAK PERNAH menghitung ulang -- kalau cache
    belum ada atau sudah basi, langsung mengembalikan available=False alih-
    alih memicu pemindaian ~900 berkas Summary (~1 menit saat dingin).

    Dipakai matches_for_stock() supaya Halaman Saham (dibuka berkali-kali
    sehari, bukan sekali seperti Penemu Pola) tidak pernah menunggu mesin
    ini menghitung ulang -- ia cuma membaca hasil yang sudah ada. Penemu
    Pola sendiri (atau cache warmup) yang bertanggung jawab menjaga cache
    tetap segar.
    """
    max_orde = max_orde or C['MAX_ORDE']
    min_n = min_n or C['MIN_N']
    key = 'mine_%d_%d' % (max_orde, min_n)
    if not os.path.exists(CACHE_FILE):
        return {'available': False, 'message': 'Penemu Pola belum pernah dihitung.'}
    try:
        with open(CACHE_FILE, 'rb') as fh:
            cached = pickle.load(fh)
        entry = cached.get(key)
        if entry and entry['ts'] >= _sumber_terbaru():
            hasil = dict(entry['result'])
            hasil['from_cache'] = True
            return hasil
    except Exception:
        pass
    return {'available': False, 'message': 'Cache Penemu Pola basi -- buka halaman Penemu Pola untuk menghitung ulang.'}


def matches_for_stock(stock, max_orde=None, min_n=None, top_n=8):
    """
    Temuan Penemu Pola mana saja yang emiten ini SEKARANG jatuh di
    keranjangnya -- dipakai Halaman Saham supaya statistik yang sama
    dengan Penemu Pola (win rate, vs baseline, q hasil FDR, dan hasil MAJU
    yang bebas lookahead dari pola_jurnal.py) bisa dibaca per-saham tanpa
    membangun ulang mesinnya. Diurutkan sama seperti tabel utama
    (|vs_baseline| lalu q), dipotong ke top_n.

    Dibaca dari cache saja (lihat mine_if_cached) -- kalau belum pernah
    dihitung, mengembalikan available=False, BUKAN memicu penghitungan
    ~1 menit di tengah permintaan Halaman Saham.
    """
    stock = (stock or '').strip().upper()
    hasil = mine_if_cached(max_orde=max_orde, min_n=min_n)
    if not hasil.get('available'):
        return hasil

    cocok = [dict(k) for k in (hasil.get('temuan') or []) if stock in (k.get('saham') or [])]
    cocok = cocok[:top_n]

    try:
        from .pola_jurnal import evaluasi
        pola_maju = evaluasi(hasil.get('temuan')).get('pola', {})
    except Exception:
        pola_maju = {}
    for k in cocok:
        k['maju'] = pola_maju.get(k['kunci'])

    return {
        'available': True,
        'stock': stock,
        'kini_tanggal': hasil.get('kini_tanggal'),
        'baseline': hasil.get('baseline'),
        'n_cocok': len(cocok),
        'temuan': cocok,
        'validasi_oos_kesimpulan': (hasil.get('validasi_oos') or {}).get('kesimpulan'),
    }


def _bucket(nilai, bins):
    if nilai is None or not np.isfinite(nilai):
        return None
    for lo, hi, nama in bins:
        if lo < nilai <= hi:
            return nama
    return None


def _fitur_bar(stock, tanggal, close, vol, nt5, rt, tb, ts, ret1, i):
    """
    Hitung ketujuh metrik pada bar ke-i memakai jendela LOOK hari sebelumnya.

    Dipakai dua kali dengan makna berbeda: untuk pengamatan historis (yang
    punya return ke depan, jadi bisa diuji) dan untuk potret hari ini (yang
    belum punya return, jadi cuma bisa dicocokkan). Satu fungsi supaya
    keduanya DIJAMIN memakai definisi metrik yang sama -- kalau dihitung di
    dua tempat, satu perubahan definisi akan diam-diam membuat daftar saham
    tidak lagi cocok dengan pola yang diuji.
    """
    c0 = close.iloc[i - 1]
    cs = close.iloc[i - C['LOOK']]
    if not np.isfinite(c0) or c0 <= 0 or not np.isfinite(cs) or cs <= 0:
        return None
    v20 = vol.iloc[i - C['LOOK']:i]
    adv_value = float(v20.mean()) * c0
    if adv_value < C['MIN_ADV']:
        return None

    vol_mult = (float(v20.iloc[-1]) / float(v20.mean())) if v20.mean() > 0 else None
    tbm = float(tb.iloc[i - C['LOOK']:i].mean()) if tb is not None and tb.notna().any() else None
    tsm = float(ts.iloc[i - C['LOOK']:i].mean()) if ts is not None and ts.notna().any() else None

    return {
        'stock': stock,
        'date': tanggal,
        'harga': (c0 - cs) / cs * 100.0,
        'top5': float(nt5.iloc[i - C['LOOK']:i].sum()),
        'ritel': float(rt.iloc[i - C['LOOK']:i].sum()),
        'volume': vol_mult,
        'nilai': adv_value,
        'pembeli': (tsm / tbm) if (tbm and tsm and tbm > 0) else None,
        'volatil': float(ret1.iloc[i - C['LOOK']:i].std()),
    }


def _beri_keranjang(df):
    """Tambahkan kolom <fitur>_b berisi nama keranjang tiap metrik."""
    for f, spec in FITUR.items():
        df[f + '_b'] = df[f].apply(lambda v: _bucket(v, spec['bins']))
    return df


def build_matrix(dengan_kini=False):
    """
    Matriks pengamatan: satu baris per (saham, tanggal) dengan semua metrik
    + return ke depan.

    dengan_kini=True juga mengembalikan potret BAR TERAKHIR tiap saham --
    metrik yang sama, tanpa kolom `fwd` karena returnnya memang belum ada.
    Itulah yang dipakai untuk menjawab "saham mana yang SEKARANG kena pola
    ini". Pengamatan terbaru di matriks historis berumur FWD=40 hari bursa
    (~2 bulan), jauh terlalu basi untuk pertanyaan itu.
    """
    rows = []
    kini = []
    for path in glob.glob(os.path.join(SUMMARY_DIR, '*_Summary.csv')):
        stock = os.path.basename(path)[:4]
        try:
            df = pd.read_csv(path)
            df['Date'] = pd.to_datetime(df['Date'], format='%d-%b-%y', errors='coerce')
            df = df.dropna(subset=['Date']).sort_values('Date').reset_index(drop=True)
        except Exception:
            continue
        n = len(df)
        if n < C['LOOK'] + C['FWD'] + 5:
            continue

        close = pd.to_numeric(df['Close'], errors='coerce')
        vol = pd.to_numeric(df['Volume'], errors='coerce').fillna(0.0)
        nt5 = pd.to_numeric(df.get('Net Top5 All Lot'), errors='coerce').fillna(0.0)
        rt = pd.to_numeric(df.get('Retail'), errors='coerce').fillna(0.0)
        tb = pd.to_numeric(df.get('Total Buyer'), errors='coerce')
        ts = pd.to_numeric(df.get('Total Seller'), errors='coerce')
        ret1 = close.pct_change() * 100.0

        for i in range(C['LOOK'], n - C['FWD'], C['STEP']):
            c0 = close.iloc[i - 1]
            baris = _fitur_bar(stock, df['Date'].iloc[i - 1], close, vol, nt5, rt,
                               tb, ts, ret1, i)
            if baris is None:
                continue
            baris['fwd'] = (close.iloc[i + C['FWD'] - 1] - c0) / c0 * 100.0
            rows.append(baris)

        if dengan_kini:
            sekarang = _fitur_bar(stock, df['Date'].iloc[n - 1], close, vol, nt5, rt,
                                  tb, ts, ret1, n)
            if sekarang is not None:
                sekarang['close'] = float(close.iloc[n - 1])
                kini.append(sekarang)

    m = _beri_keranjang(pd.DataFrame(rows).dropna(subset=['fwd']))
    if not dengan_kini:
        return m
    k = _beri_keranjang(pd.DataFrame(kini)) if kini else pd.DataFrame()
    return m, k


def _p_proporsi(k, n, p0):
    """
    p-value dua arah, uji proporsi normal-approx: apakah win rate sel (k/n)
    berbeda dari baseline p0. Dipakai normal-approx karena n selalu >=
    MIN_N (120), jauh di atas ambang kelayakannya.
    """
    if n <= 0 or p0 <= 0 or p0 >= 1:
        return 1.0
    se = math.sqrt(p0 * (1 - p0) / n)
    if se == 0:
        return 1.0
    z = (k / n - p0) / se
    # 2 * (1 - Phi(|z|)) memakai erfc supaya tidak perlu scipy
    return max(0.0, min(1.0, math.erfc(abs(z) / math.sqrt(2))))


def _fdr(pvals):
    """Benjamini-Hochberg: p -> q. Mengembalikan daftar q sesuai urutan asal."""
    n = len(pvals)
    if n == 0:
        return []
    urut = sorted(range(n), key=lambda i: pvals[i])
    q = [0.0] * n
    prev = 1.0
    for rank, idx in enumerate(reversed(urut), start=1):
        i_rank = n - rank + 1
        nilai = min(prev, pvals[idx] * n / i_rank)
        q[idx] = nilai
        prev = nilai
    return q


def saham_pola(kunci, max_orde=None):
    """
    Temuan mana yang kuncinya `kunci` ("fitur~keranjang|fitur~keranjang").

    Dipakai halaman chart supaya daftar kodenya tidak perlu dititipkan
    lewat URL: kuncinya pendek, dan daftarnya selalu diambil ulang dari
    hasil mine() yang sama dengan yang dilihat di tabel -- jadi tidak bisa
    basi relatif terhadap angka di sebelahnya.
    """
    kunci = (kunci or '').strip()
    if not kunci:
        return None
    hasil = mine(max_orde=max_orde)
    if not hasil.get('available'):
        return None
    for k in hasil.get('temuan') or []:
        if k.get('kunci') == kunci:
            return k
    return None


def mine(force=False, max_orde=None, min_n=None):
    """Uji semua kombinasi fitur, kembalikan temuan terurut + ringkasan pencarian."""
    max_orde = max_orde or C['MAX_ORDE']
    min_n = min_n or C['MIN_N']
    key = 'mine_%d_%d' % (max_orde, min_n)

    if not force and os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, 'rb') as fh:
                cached = pickle.load(fh)
            entry = cached.get(key)
            if entry and entry['ts'] >= _sumber_terbaru():
                hasil = dict(entry['result'])
                hasil['from_cache'] = True
                return hasil
        except Exception:
            pass

    t0 = time.time()
    m, kini = build_matrix(dengan_kini=True)
    if m.empty:
        return {'available': False, 'message': 'Tidak ada pengamatan yang bisa dibentuk.'}

    # Potret hari ini dititipkan ke jurnal maju SEBELUM hasilnya ada (lihat
    # pola_jurnal.py). Ditaruh di sini, bukan sebagai tugas batch sendiri,
    # supaya pemindaian ~900 berkas Summary tidak terjadi dua kali sehari;
    # catat() idempoten per tanggal bar, jadi Hitung Ulang tidak menggandakan.
    # Dibungkus try: kegagalan mencatat tidak boleh menjatuhkan halamannya.
    try:
        from .pola_jurnal import catat
        catat(kini)
    except Exception:
        logger.exception('Gagal mencatat jurnal maju Penemu Pola')

    baseline_win = float((m['fwd'] > 0).mean())
    baseline = {
        'n': int(len(m)),
        'win': round(baseline_win * 100, 1),
        'mean': round(float(m['fwd'].mean()), 2),
        'median': round(float(m['fwd'].median()), 2),
    }

    fitur = list(FITUR.keys())
    kandidat = []
    diuji = 0
    dilewati_kecil = 0

    for orde in range(1, max_orde + 1):
        for kombo in combinations(fitur, orde):
            kolom = [f + '_b' for f in kombo]
            sub = m.dropna(subset=kolom)
            if sub.empty:
                continue
            for kunci, grup in sub.groupby(kolom, observed=True):
                diuji += 1
                n = len(grup)
                if n < min_n:
                    dilewati_kecil += 1
                    continue
                menang = int((grup['fwd'] > 0).sum())
                win = menang / n
                p = _p_proporsi(menang, n, baseline_win)
                nilai_kunci = kunci if isinstance(kunci, tuple) else (kunci,)
                kandidat.append({
                    'orde': orde,
                    'fitur': list(kombo),
                    'label': ' + '.join('%s: %s' % (FITUR[f]['label'], v)
                                        for f, v in zip(kombo, nilai_kunci)),
                    'nilai': list(nilai_kunci),
                    'n': n,
                    'win': round(win * 100, 1),
                    'vs_baseline': round((win - baseline_win) * 100, 1),
                    'mean': round(float(grup['fwd'].mean()), 2),
                    'median': round(float(grup['fwd'].median()), 2),
                    'p': p,
                })

    # Saham yang SEKARANG jatuh di keranjang yang sama. Inilah jembatan dari
    # "pola ini menang 62%" ke "jadi saya harus lihat apa hari ini" -- tanpa
    # ini halaman cuma memberi statistik yang tidak bisa ditindaklanjuti.
    for k in kandidat:
        k['saham'] = []
        if kini is None or kini.empty:
            continue
        sisa = kini
        for f, v in zip(k['fitur'], k['nilai']):
            sisa = sisa[sisa[f + '_b'] == v]
            if sisa.empty:
                break
        if not sisa.empty:
            k['saham'] = sorted(str(x) for x in sisa['stock'].unique())
        k['n_saham'] = len(k['saham'])
        # Identitas pola yang cukup pendek untuk masuk URL dan tidak
        # bergeser saat cache dibangun ulang -- beda dengan nomor urut
        # baris, yang berubah setiap kali urutan sortir berubah.
        k['kunci'] = '|'.join('%s~%s' % (f, v)
                              for f, v in zip(k['fitur'], k['nilai']))

    qs = _fdr([k['p'] for k in kandidat])
    for k, q in zip(kandidat, qs):
        k['q'] = q
        k['lolos'] = q < C['Q_AMBANG']
        k['p'] = round(k['p'], 5)
        k['q'] = round(q, 5)

    kandidat.sort(key=lambda k: (-abs(k['vs_baseline']), k['q']))
    lolos = [k for k in kandidat if k['lolos']]

    hasil = {
        'available': True,
        'baseline': baseline,
        'validasi_oos': VALIDASI_OOS,
        'temuan': kandidat,
        'n_temuan': len(kandidat),
        'n_lolos': len(lolos),
        'n_diuji': diuji,
        'kini_tanggal': (str(kini['date'].max())[:10]
                         if kini is not None and not kini.empty else None),
        'kini_n_emiten': int(len(kini)) if kini is not None else 0,
        'n_dilewati_kecil': dilewati_kecil,
        'fitur': {f: {'label': FITUR[f]['label'],
                      'keranjang': [b[2] for b in FITUR[f]['bins']]} for f in FITUR},
        'config': dict(C, MAX_ORDE=max_orde, MIN_N=min_n),
        'durasi_detik': round(time.time() - t0, 1),
        'as_of': time.strftime('%Y-%m-%d %H:%M'),
        'from_cache': False,
    }

    try:
        cached = {}
        if os.path.exists(CACHE_FILE):
            with open(CACHE_FILE, 'rb') as fh:
                cached = pickle.load(fh)
        cached[key] = {'ts': time.time(), 'result': hasil}
        with open(CACHE_FILE, 'wb') as fh:
            pickle.dump(cached, fh)
    except Exception:
        pass

    return hasil
