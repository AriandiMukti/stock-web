"""
Jurnal maju Penemu Pola: mencatat keadaan tiap emiten SEBELUM hasilnya ada.

KENAPA MODUL INI ADA
====================
Semua angka di Penemu Pola in-sample -- pola dicari DAN diuji di data yang
sama: Jan-Sep 2026, satu rezim pasar turun (baseline win 38,3%, mean
-2,24%). Koreksi Benjamini-Hochberg di dalamnya mengendalikan pengujian
berganda di dalam satu dataset; ia tidak tahu apa-apa soal kebetulan
periode. Catatan VALIDASI_OOS di pattern_miner.py sudah menunjukkan
akibatnya: diuji di 10 tahun data lain, selisih 6-18 poin persen menyusut
jadi ~1 poin.

Yang belum pernah ada di app ini: bukti KE DEPAN. Modul ini mencatat
potret metrik tiap emiten setiap hari bursa, lalu -- 40 hari bursa
kemudian -- mengukur apa yang benar-benar terjadi.

Nilainya bukan karena metodenya lebih canggih, tapi karena lookahead
secara struktural tidak mungkin: barisnya sudah ditulis ke disk sebelum
returnnya ada. Tidak ada cara membocorkan masa depan ke berkas yang
ditulis lebih dulu. Backtest apa pun harus dipercaya soal itu; jurnal
tidak perlu dipercaya.

KENAPA YANG DICATAT KEADAAN, BUKAN DAFTAR SAHAM PER POLA
========================================================
Godaan pertamanya menyimpan "pola X hari ini berisi 18 emiten berikut".
Itu menua dengan buruk: begitu batas keranjang di FITUR digeser atau
MAX_ORDE diubah, seluruh riwayat jadi tidak sebanding dan harus dibuang --
padahal riwayat maju justru yang paling mahal, karena tidak bisa dikejar
dengan menghitung ulang. Satu-satunya cara mendapatkannya adalah menunggu.

Yang disimpan di sini tujuh metrik MENTAH per emiten per hari. Keranjangnya
dihitung ulang setiap kali dibaca. Dua akibatnya:

  1. Riwayat tetap berlaku setelah definisi keranjang diubah.
  2. Pola yang baru ditemukan BULAN DEPAN tetap bisa diuji terhadap
     catatan bulan ini -- tanpa pernah melihat masa depan, karena
     metriknya sendiri sudah terkunci di berkas sejak dulu.

KENAPA BAR BASI DIBUANG
=======================
Per 10 Sep 2026, 19 dari 646 emiten bar terakhirnya BUKAN hari bursa
terakhir -- suspend, atau memang tidak diperdagangkan berhari-hari.
Mencatatnya di bawah tanggal hari ini akan memulai jendela 40 harinya di
masa lalu, jadi sebagian hasilnya sudah terjadi pada saat dicatat. Itu
persis lookahead yang mau dihindari modul ini. Baris yang tanggal barnya
bukan hari bursa terakhir dilewati, dan jumlahnya dilaporkan.

BENTUK BERKAS
=============
CSV append-only, bukan pickle dan bukan tabel di database aplikasi.
Alasannya sama untuk ketiganya: berkas ini harus bisa dipercaya
bertahun-tahun. CSV bisa dibuka, di-diff, dan diperiksa tanpa menjalankan
app; pickle tidak. Dan ia SENGAJA tidak bernama *_cache.pkl supaya tidak
pernah ikut terhapus saat cache dibersihkan -- cache bisa dibangun ulang,
jurnal tidak.
"""
try:
    from .runtime_paths import runtime_file as _runtime_file, market_file as _market_file, WEBSITE_DIR as _WEBSITE_DIR, PROJECT_DIR as _PROJECT_DIR, RUNTIME_DIR as _RUNTIME_DIR
except ImportError:
    from website.runtime_paths import runtime_file as _runtime_file, market_file as _market_file, WEBSITE_DIR as _WEBSITE_DIR, PROJECT_DIR as _PROJECT_DIR, RUNTIME_DIR as _RUNTIME_DIR

import os
import time
import pickle

import numpy as np
import pandas as pd

from .pattern_miner import C, FITUR, SUMMARY_DIR, _bucket, build_matrix

JURNAL_FILE = str(_runtime_file('', 'pola_jurnal.csv'))
CACHE_FILE = str(_runtime_file('', 'pola_jurnal_cache.pkl'))

# Sampel minimum sebuah pola sebelum angka majunya ditampilkan. Jauh lebih
# kecil dari MIN_N=120 milik pattern_miner, dan memang harus: yang di sana
# menyaring ribuan sel hasil pencarian (di situ n kecil = kebetulan yang
# lolos), yang di sini cuma menampilkan hasil pola yang sudah terpilih.
MIN_N_MAJU = 30

KOLOM = ['tanggal', 'stock', 'close', 'harga', 'top5', 'ritel',
         'volume', 'nilai', 'pembeli', 'volatil']


# ---------------------------------------------------------------------------
# MENCATAT
# ---------------------------------------------------------------------------
def _muat():
    """Isi jurnal sebagai DataFrame; kosong kalau berkasnya belum ada."""
    if not os.path.exists(JURNAL_FILE):
        return pd.DataFrame(columns=KOLOM)
    try:
        j = pd.read_csv(JURNAL_FILE, dtype={'tanggal': str, 'stock': str})
    except Exception:
        return pd.DataFrame(columns=KOLOM)
    # Berkasnya append-only, jadi baris ganda hanya muncul kalau pencatatan
    # pernah dijalankan dua kali untuk hari yang sama. Yang terakhir menang.
    return j.drop_duplicates(subset=['tanggal', 'stock'], keep='last')


def catat(kini=None):
    """
    Tambahkan potret hari bursa terakhir ke jurnal.

    `kini` adalah potret bar terakhir dari build_matrix(dengan_kini=True).
    Dioper dari mine() supaya pemindaian ~900 berkas Summary tidak terjadi
    dua kali dalam satu batch harian; kalau tidak dioper, dihitung sendiri.

    Idempoten per TANGGAL BAR (bukan per jam dinding): menjalankannya lagi
    di hari yang sama tidak menambah apa-apa. Itu penting karena mine()
    bisa dipicu ulang dari halaman lewat tombol Hitung Ulang.
    """
    if kini is None:
        _, kini = build_matrix(dengan_kini=True)
    if kini is None or kini.empty:
        return {'tercatat': 0, 'pesan': 'tidak ada potret untuk dicatat'}

    hari = kini['date'].max()
    segar = kini[kini['date'] == hari]
    tanggal = str(pd.Timestamp(hari).date())
    basi = int(len(kini) - len(segar))

    lama = _muat()
    if not lama.empty and (lama['tanggal'].astype(str) == tanggal).any():
        return {'tanggal': tanggal, 'tercatat': 0, 'dilewati_basi': basi,
                'sudah_ada': True}

    baris = segar.copy()
    baris['tanggal'] = tanggal
    baris = baris[KOLOM]
    baris.to_csv(JURNAL_FILE, mode='a', index=False,
                 header=not os.path.exists(JURNAL_FILE), float_format='%.6g')

    return {'tanggal': tanggal, 'tercatat': int(len(baris)),
            'dilewati_basi': basi, 'sudah_ada': False}


# ---------------------------------------------------------------------------
# MEMBACA
# ---------------------------------------------------------------------------
def _kalender():
    """
    Daftar hari bursa, diambil dari berkas Summary terbesar.

    Dipakai hanya untuk menjawab "tinggal berapa hari lagi baris tertua
    matang". Berkas terbesar dipakai sebagai wakil karena emiten paling
    likuid praktis tidak pernah bolong; emiten yang suspend punya kalender
    berlubang dan akan melaporkan sisa hari yang terlalu panjang.
    """
    import glob
    berkas = glob.glob(os.path.join(SUMMARY_DIR, '*_Summary.csv'))
    if not berkas:
        return []
    try:
        p = max(berkas, key=os.path.getsize)
        df = pd.read_csv(p, usecols=['Date'])
        d = pd.to_datetime(df['Date'], format='%d-%b-%y', errors='coerce')
        return sorted({str(x.date()) for x in d.dropna()})
    except Exception:
        return []


def _pasang_fwd(j):
    """
    Tambahkan kolom `fwd`: return C['FWD'] hari bursa setelah tiap baris.

    Harganya diambil dari berkas Summary, bukan dari jurnal itu sendiri.
    Jurnal hanya berisi hari-hari yang sempat tercatat -- kalau batch
    harian pernah gagal semalam, jendela 40 harinya akan terhitung dari
    baris yang salah. Summary adalah kalender yang sebenarnya.

    Baris yang belum genap 40 hari bursa dapat fwd = NaN: belum matang,
    bukan nol.
    """
    j = j.copy()
    j['fwd'] = np.nan
    if j.empty:
        return j

    for stock, grup in j.groupby('stock'):
        path = os.path.join(SUMMARY_DIR, '%s_Summary.csv' % stock)
        if not os.path.exists(path):
            continue
        try:
            df = pd.read_csv(path, usecols=['Date', 'Close'])
            df['Date'] = pd.to_datetime(df['Date'], format='%d-%b-%y', errors='coerce')
            df = df.dropna(subset=['Date']).sort_values('Date').reset_index(drop=True)
        except Exception:
            continue

        close = pd.to_numeric(df['Close'], errors='coerce').to_numpy()
        posisi = {str(d.date()): i for i, d in enumerate(df['Date'])}
        n = len(df)

        for idx, tanggal in zip(grup.index, grup['tanggal'].astype(str)):
            i = posisi.get(tanggal)
            if i is None:
                continue
            k = i + C['FWD']
            if k >= n:
                continue
            c0, c1 = close[i], close[k]
            if not np.isfinite(c0) or c0 <= 0 or not np.isfinite(c1):
                continue
            j.at[idx, 'fwd'] = (c1 - c0) / c0 * 100.0

    return j


def _sumber_terbaru():
    from .kesegaran import berkas_terbaru, paling_baru, summary_terbaru
    return paling_baru(summary_terbaru(), berkas_terbaru(JURNAL_FILE))


def evaluasi(temuan=None, force=False, min_n=MIN_N_MAJU):
    """
    Hasil MAJU tiap pola: apa yang benar-benar terjadi pada emiten yang
    dicatat jurnal, dibanding baseline dari baris-baris yang sama.

    Baselinenya dihitung dari jurnal itu sendiri, bukan dari angka tetap
    -2,24% milik pattern_miner. Harus begitu: baris jurnal berasal dari
    rentang tanggal dan semesta yang berbeda, jadi membandingkannya dengan
    baseline periode lain akan mencampur efek pola dengan efek rezim --
    persis kesalahan yang ditemukan market_regime.py.
    """
    if temuan is None:
        from .pattern_miner import mine
        temuan = (mine() or {}).get('temuan') or []

    kunci_cache = (len(temuan), int(min_n))
    if not force:
        try:
            with open(CACHE_FILE, 'rb') as fh:
                simpan = pickle.load(fh)
            isi = simpan.get(kunci_cache)
            if isi and isi.get('ts', 0) >= _sumber_terbaru():
                hasil = dict(isi['result'])
                hasil['from_cache'] = True
                return hasil
        except Exception:
            pass

    t0 = time.time()
    j = _muat()
    hari = sorted(j['tanggal'].astype(str).unique()) if not j.empty else []

    hasil = {
        'available': True,
        'fwd_hari': C['FWD'],
        'min_n': int(min_n),
        'n_hari': len(hari),
        'n_baris': int(len(j)),
        'mulai': hari[0] if hari else None,
        'terakhir': hari[-1] if hari else None,
        'n_matang': 0,
        'n_hari_matang': 0,
        'sisa_hari_bursa': None,
        'baseline': None,
        'pola': {},
        'from_cache': False,
    }

    if not j.empty:
        for f, spec in FITUR.items():
            j[f + '_b'] = j[f].apply(lambda v: _bucket(v, spec['bins']))
        j = _pasang_fwd(j)
        matang = j.dropna(subset=['fwd'])
        hasil['n_matang'] = int(len(matang))
        hasil['n_hari_matang'] = int(matang['tanggal'].nunique()) if len(matang) else 0

        if not len(matang):
            # Belum ada yang matang -- katakan kapan bacaan pertamanya
            # datang, jangan cuma menampilkan kolom kosong.
            kal = _kalender()
            if kal and hari:
                sudah = len([d for d in kal if d > hari[0]])
                hasil['sisa_hari_bursa'] = max(0, C['FWD'] - sudah)
        else:
            fwd = matang['fwd'].to_numpy()
            dasar_win = float((fwd > 0).mean())
            hasil['baseline'] = {
                'n': int(len(fwd)),
                'win': round(dasar_win * 100, 1),
                'mean': round(float(fwd.mean()), 2),
                'median': round(float(np.median(fwd)), 2),
            }

            for k in temuan:
                sisa = matang
                for f, v in zip(k.get('fitur') or [], k.get('nilai') or []):
                    sisa = sisa[sisa[f + '_b'] == v]
                    if sisa.empty:
                        break
                n = len(sisa)
                if n < min_n:
                    continue
                v = sisa['fwd'].to_numpy()
                win = float((v > 0).mean())
                hasil['pola'][k['kunci']] = {
                    'n': int(n),
                    'win': round(win * 100, 1),
                    'mean': round(float(v.mean()), 2),
                    'median': round(float(np.median(v)), 2),
                    'vs_baseline': round((win - dasar_win) * 100, 1),
                }

    hasil['durasi_detik'] = round(time.time() - t0, 1)

    try:
        simpan = {}
        if os.path.exists(CACHE_FILE):
            with open(CACHE_FILE, 'rb') as fh:
                simpan = pickle.load(fh)
        simpan[kunci_cache] = {'ts': time.time(), 'result': hasil}
        with open(CACHE_FILE, 'wb') as fh:
            pickle.dump(simpan, fh)
    except Exception:
        pass

    return hasil


if __name__ == '__main__':
    print(catat())
    h = evaluasi(force=True)
    print('hari tercatat : %s (%s - %s)' % (h['n_hari'], h['mulai'], h['terakhir']))
    print('baris         : %s, matang %s' % (h['n_baris'], h['n_matang']))
    if h['baseline']:
        print('baseline maju : %s' % h['baseline'])
        print('pola berangka : %s' % len(h['pola']))
    else:
        print('belum matang  : sisa ~%s hari bursa' % h['sisa_hari_bursa'])
