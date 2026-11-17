"""
Audit sisi: screener yang ada memilih sisi yang mana, dan apakah ia
menambah nilai di atas sisi itu sendiri.

LATAR
Uji 10 tahun terhadap Penemu Pola (folder Test, 21 emiten, 2016-2025)
menyisakan satu-satunya arah yang bertahan lintas periode:

    A. harga 20 hari TURUN >5%              -> +1,37 pp, 7/10 tahun
    B. Top5 BELI dan harga sudah naik >5%   -> -0,95 pp, 7/10 tahun

Arah itu BERLAWANAN dengan premis aplikasi ini, yang sebagian besar
modulnya mencari akumulasi Top5 lalu ikut masuk. Maka pertanyaan yang
belum pernah ditanyakan: saat sebuah saham muncul di screener, dia
sebenarnya sedang berdiri di sisi mana?

CARA UJI
Aturan tiap screener diputar ulang ke seluruh riwayat harian (bukan
memakai daftar yang tersimpan, yang cuma potret hari ini), lalu tiap
pilihan diklasifikasikan ke sisi A / B / lain-lain, dan dibandingkan
dengan hasil yang sebenarnya terjadi 40 hari kemudian.

Baseline dihitung PER PARUH periode, bukan sekali untuk seluruh rentang.
Ini bukan detail: baseline paruh 1 adalah 15,6% dan paruh 2 adalah 67,2%
-- menggabungkannya membuat jurang A-vs-B tampak 22 pp, padahal setelah
dibaselinekan dengan benar hanya 5,9 pp. Versi pertama audit ini tertipu
oleh persis itu.

HASIL (Mar-Jul 2026, 841 emiten, 22.375 pilihan screener diputar ulang)

    tanpa screener apa pun
        sisi A (harga turun)          +1,62 pp        <- pembanding
        sisi B (ikut bandar)          -4,25 pp
        jurang                         5,9 pp

    screener                    edge      vs sisi A saja
        Consol                  -6,49         -8,11
        Consol (low value)      -1,14         -2,76
        Retail Sell             -7,39         -9,01
        Retail Sell (low val)   -2,39         -4,01
        Skor Pola >=70          +0,76         -0,86

TEMUAN INTI: tidak ada satu pun screener yang mengalahkan aturan paling
sederhana yang mungkin -- "beli saham yang harganya 20 hari terakhir
turun". Skor Pola paling mendekati (-0,86), sisanya merusak.

Bahkan ketika dibatasi hanya ke sisi A, Retail Sell tetap -4,85 -- jadi
syarat "ritel jual" itu sendiri MENGHAPUS keunggulan sisi A, bukan
menambahnya.

DUKUNGAN SILANG: sisi A menghasilkan +1,62 pp di sini, dan +1,37 pp di
uji 10 tahun yang sepenuhnya terpisah. Dua angka itu dari dataset,
periode, dan semesta saham yang berbeda -- kecocokannya adalah alasan
utama temuan ini diperlakukan lebih serius daripada kalibrasi mana pun
di modul lain.

BATAS YANG HARUS DIINGAT
- Periode replay cuma Mar-Jul 2026 (butuh 40 hari ke depan, jadi ujung
  datanya terpotong). Arahnya didukung uji 10 tahun; besarnya tidak.
- Kering Screener tidak ikut diaudit: aturannya bergantung folder
  eksternal (Saham Kering), tidak bisa diputar ulang dari Summary saja.
- Skor Pola yang diputar ulang di sini memakai bagian yang murni berasal
  dari Summary (volume + arus ritel 20h). Komponen kepemilikan tidak
  tersedia per tanggal historis, jadi skornya pendekatan.

PERINGATAN TERPENTING: SEMUA ANGKA DI ATAS ADALAH WIN RATE, BUKAN UANG.

Win rate hanya menghitung SEBERAPA SERING menang, bukan seberapa besar.
Diperiksa ulang dalam satuan rata-rata return, dan hasilnya berbalik di
luar sampel (21 emiten, 2016-2025, horizon 40 hari):

    sisi      win rate         rata-rata return    rata menang / kalah
    pasar      51,4%              +6,04%
    A turun    52,8%  (+1,4)      +5,40%  (-0,64)   +20,44% / -11,39%
    B naik     50,5%  (-0,9)      +6,84%  (+0,80)   +25,64% / -12,30%

Sisi A memang lebih SERING menang, tapi menangnya lebih KECIL. Diukur
dengan uang, sisi A justru sedikit di bawah pasar dan sisi B sedikit di
atas -- kebalikan dari urutan win rate.

Per tahun, rata-rata return sisi A dikurangi rata-rata pasar tahun itu:
+3,68 / -0,68 / -1,06 / +0,68 / -5,05 / +2,06 / +0,17 / -1,58 / +1,49 /
+1,84. Enam positif, empat negatif, rata-rata +0,16% -- nol.

KESIMPULAN YANG BENAR, DAN HARUS DIPEGANG:
  1. Perbandingan antar screener TETAP SAH: dalam kedua satuan, tidak ada
     screener yang mengalahkan aturan sederhana "harga 20h turun".
     Dalam satuan return: Skor Pola -0,49, Consol low -3,39, Retail Sell
     low -3,49, Retail Sell -9,21, Consol -10,37.
  2. TAPI aturan sederhana itu sendiri BUKAN strategi yang menguntungkan.
     Keunggulan win rate-nya tidak berubah jadi uang di luar sampel.

Jadi audit ini adalah alasan untuk BERHENTI memakai screener yang ada
sebagai dasar beli -- bukan alasan untuk mulai membeli tiap saham yang
turun 5% dalam 20 hari. Belum ada aturan beli di aplikasi ini yang
terbukti menghasilkan uang di luar sampel.
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
CACHE_FILE = str(_runtime_file('', 'screener_side_cache.pkl'))
def _sumber_terbaru():
    """Hanya berkas Summary -- modul ini tidak membaca sumber lain."""
    from .kesegaran import summary_terbaru
    return summary_terbaru()

LOOK = 20
FWD = 40
VALUE_AVG_PARAM = 20      # miliar rupiah -- disalin dari analyze.py
VALUE_AVG_PARAM2 = 5
TURUN_AMBANG = -5.0
NAIK_AMBANG = 5.0

SISI_A = 'A. harga turun'
SISI_B = 'B. ikut bandar'
SISI_LAIN = 'lain-lain'

# Angka hasil uji 10 tahun (folder Test) -- ditulis di sini supaya
# tampilan bisa menyandingkan langsung tanpa menghitung ulang.
DUKUNGAN_OOS = {
    'sumber': 'folder Test: 21 emiten, 2016-2025, horizon 40 hari',
    'sisi_a': 1.37, 'sisi_a_tahun': '7/10',
    'sisi_b': -0.95, 'sisi_b_tahun': '7/10',
}

# Uji ulang dalam satuan RETURN, bukan win rate. Urutannya berbalik --
# lihat peringatan panjang di docstring modul.
UJI_RETURN = {
    'sumber': 'folder Test: 21 emiten, 2016-2025, horizon 40 hari',
    'pasar': 6.04,
    'sisi_a': {'win': 52.8, 'ret': 5.40, 'vs_pasar': -0.64,
               'menang': 20.44, 'kalah': -11.39},
    'sisi_b': {'win': 50.5, 'ret': 6.84, 'vs_pasar': 0.80,
               'menang': 25.64, 'kalah': -12.30},
    'tahun_sisi_a': [3.68, -0.68, -1.06, 0.68, -5.05, 2.06, 0.17, -1.58, 1.49, 1.84],
    'tahun_positif': 6, 'tahun_total': 10, 'tahun_rata2': 0.16,
    'edge_return_in_sample': {'sisi_a': 1.18, 'sisi_b': -2.72,
                              'Skor Pola >=70': -0.49, 'Consol (low value)': -3.39,
                              'Retail Sell (low value)': -3.49,
                              'Retail Sell': -9.21, 'Consol': -10.37},
    'kesimpulan': ('Sisi A lebih SERING menang tapi menangnya lebih KECIL. Diukur dengan '
                   'uang, sisi A justru -0,64% di bawah pasar dan sisi B +0,80% di atas -- '
                   'kebalikan dari urutan win rate. Perbandingan antar screener tetap sah '
                   '(semuanya kalah dari aturan sederhana dalam kedua satuan), tapi aturan '
                   'sederhana itu sendiri BUKAN strategi yang menguntungkan.'),
}


def _consol_at(o, c, v, i):
    """analyze.consol() dievaluasi pada indeks i sebagai baris terakhir."""
    p_surge, p_konsol = 4, 5
    tot = p_surge + p_konsol
    if i < 20 + tot:
        return False
    s0, s1 = i + 1 - tot, i + 1 - p_konsol
    k0 = i + 1 - p_konsol
    vs = v[s0:s1]
    if not len(vs) or not np.isfinite(vs).all():
        return False
    ma20 = np.nanmean(v[k0 - 20:k0])
    if not np.isfinite(ma20) or not (vs.mean() > ma20):
        return False
    ko, kc = o[k0:i + 1], c[k0:i + 1]
    hi = np.nanmax(np.concatenate([ko, kc]))
    lo = np.nanmin(np.concatenate([ko, kc]))
    if not (np.isfinite(hi) and np.isfinite(lo) and lo > 0):
        return False
    if (hi - lo) / lo > 0.07:
        return False
    return bool(v[k0:i + 1].mean() < vs.mean() * 0.75)


def _sisi(harga20, top5_20):
    if harga20 < TURUN_AMBANG:
        return SISI_A
    if top5_20 > 0 and harga20 > NAIK_AMBANG:
        return SISI_B
    return SISI_LAIN


def _bangun():
    """Putar ulang seluruh screener + semesta pembanding."""
    pilihan = []
    semesta = []
    for path in glob.glob(os.path.join(SUMMARY_DIR, '*_Summary.csv')):
        stock = os.path.basename(path)[:4]
        try:
            d = pd.read_csv(path)
            d['Date'] = pd.to_datetime(d['Date'], format='%d-%b-%y', errors='coerce')
            d = d.dropna(subset=['Date']).sort_values('Date').reset_index(drop=True)
        except Exception:
            continue
        n = len(d)
        if n < LOOK + FWD + 30:
            continue
        o = pd.to_numeric(d['Open'], errors='coerce').values
        c = pd.to_numeric(d['Close'], errors='coerce').values
        v = pd.to_numeric(d['Volume'], errors='coerce').values
        nt5 = pd.to_numeric(d.get('Net Top5 All Lot'), errors='coerce').fillna(0.0).values
        rt = pd.to_numeric(d.get('Retail'), errors='coerce').fillna(0.0).values
        ema10 = pd.Series(c).ewm(span=10, adjust=False).mean().values
        v20 = pd.Series(v).rolling(20).mean().values

        for i in range(LOOK + 30, n - FWD):
            c0, cs = c[i], c[i - LOOK]
            if not (np.isfinite(c0) and c0 > 0 and np.isfinite(cs) and cs > 0):
                continue
            harga20 = (c0 - cs) / cs * 100.0
            top5_20 = float(np.nansum(nt5[i - LOOK + 1:i + 1]))
            sisi = _sisi(harga20, top5_20)
            fwd = (c[i + FWD] - c0) / c0 * 100.0
            tgl = d['Date'].iloc[i]
            semesta.append({'date': tgl, 'sisi': sisi, 'fwd': fwd})

            nilai_m = (o[i] + c0) / 2 * v[i] / 1e9
            if not np.isfinite(nilai_m):
                continue
            is_consol = _consol_at(o, c, v, i) and (ema10[i] > ema10[i - 4])
            retail = rt[i]

            layar = []
            if nilai_m >= VALUE_AVG_PARAM:
                if is_consol:
                    layar.append('Consol')
                elif retail < 0:
                    layar.append('Retail Sell')
            elif VALUE_AVG_PARAM2 <= nilai_m < VALUE_AVG_PARAM:
                if is_consol:
                    layar.append('Consol (low value)')
                elif retail < 0:
                    layar.append('Retail Sell (low value)')

            vm = v[i] / v20[i] if (np.isfinite(v20[i]) and v20[i] > 0) else np.nan
            skor = 50.0
            if np.isfinite(vm):
                skor += 22 if vm < 1 else (8 if vm < 2 else (-12 if vm < 5 else -25))
            skor += 8 if float(np.nansum(rt[i - LOOK + 1:i + 1])) <= 0 else -6
            if skor >= 70:
                layar.append('Skor Pola >=70')

            for L in layar:
                pilihan.append({'stock': stock, 'date': tgl, 'layar': L,
                                'sisi': sisi, 'fwd': fwd})
    return pd.DataFrame(pilihan), pd.DataFrame(semesta)


def _edge(g, semesta, tengah):
    """
    Edge vs baseline PER PARUH. Menggabungkan baseline dua paruh yang
    berbeda jauh (15,6% vs 67,2%) melipatgandakan angkanya secara palsu.
    """
    tot, n = 0.0, 0
    for gm, sm in ((g['date'] <= tengah, semesta['date'] <= tengah),
                   (g['date'] > tengah, semesta['date'] > tengah)):
        gg, ss = g[gm], semesta[sm]
        if len(gg) < 30 or not len(ss):
            continue
        e = (float((gg['fwd'] > 0).mean()) - float((ss['fwd'] > 0).mean())) * 100
        tot += e * len(gg)
        n += len(gg)
    return (round(tot / n, 2), n) if n else (None, 0)


def audit(force=False):
    """Hasil audit sisi, siap ditampilkan."""
    if not force and os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, 'rb') as fh:
                cached = pickle.load(fh)
            if cached.get('ts', 0) >= _sumber_terbaru():
                hasil = dict(cached['data'])
                hasil['from_cache'] = True
                return hasil
        except Exception:
            pass

    t0 = time.time()
    pil, sem = _bangun()
    if pil.empty or sem.empty:
        return {'available': False, 'message': 'Tidak cukup data harian untuk audit.'}

    tengah = sem['date'].min() + (sem['date'].max() - sem['date'].min()) / 2
    edge_a, n_a = _edge(sem[sem['sisi'] == SISI_A], sem, tengah)
    edge_b, n_b = _edge(sem[sem['sisi'] == SISI_B], sem, tengah)

    baris = []
    for L, g in pil.groupby('layar'):
        e, n = _edge(g, sem, tengah)
        bagi = g['sisi'].value_counts(normalize=True) * 100
        per_sisi = {}
        for s in (SISI_A, SISI_B):
            gg = g[g['sisi'] == s]
            if len(gg) >= 150:
                es, _ = _edge(gg, sem, tengah)
                per_sisi[s] = es
        baris.append({
            'layar': L, 'n': int(len(g)), 'edge': e,
            'vs_sisi_a': round(e - edge_a, 2) if (e is not None and edge_a is not None) else None,
            'pct_a': round(float(bagi.get(SISI_A, 0.0)), 1),
            'pct_b': round(float(bagi.get(SISI_B, 0.0)), 1),
            'pct_lain': round(float(bagi.get(SISI_LAIN, 0.0)), 1),
            'edge_a': per_sisi.get(SISI_A),
            'edge_b': per_sisi.get(SISI_B),
        })
    baris.sort(key=lambda r: -(r['vs_sisi_a'] if r['vs_sisi_a'] is not None else -99))

    hasil = {
        'available': True,
        'rows': baris,
        'sisi': {'a': {'edge': edge_a, 'n': n_a}, 'b': {'edge': edge_b, 'n': n_b},
                 'jurang': round(edge_a - edge_b, 2) if (edge_a is not None and edge_b is not None) else None},
        'dukungan_oos': DUKUNGAN_OOS,
        'uji_return': UJI_RETURN,
        'periode': {'dari': str(sem['date'].min().date()), 'sampai': str(sem['date'].max().date())},
        'n_pilihan': int(len(pil)), 'n_semesta': int(len(sem)),
        'n_emiten': int(pil['stock'].nunique()),
        'horizon': FWD,
        'kesimpulan': ('Tidak ada satu pun screener yang mengalahkan aturan paling sederhana '
                       'yang mungkin: harga 20 hari terakhir turun. Kolom "vs sisi A" negatif '
                       'berarti screener itu merusak, bukan menambah. TAPI angka-angka ini win '
                       'rate: diukur dengan return, sisi A sendiri justru -0,64% di bawah pasar '
                       'di luar sampel. Ini alasan berhenti memakai screener yang ada, BUKAN '
                       'alasan mulai membeli tiap saham yang turun.'),
        'durasi_detik': round(time.time() - t0, 1),
        'as_of': time.strftime('%Y-%m-%d %H:%M'),
    }
    try:
        with open(CACHE_FILE, 'wb') as fh:
            pickle.dump({'ts': time.time(), 'data': hasil}, fh)
    except Exception:
        pass
    return hasil
