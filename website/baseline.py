"""
Baseline pasar yang bisa DIUKUR ULANG, bukan konstanta beku.

KENAPA MODUL INI ADA
====================
Empat modul memegang angka pembanding masing-masing:

    scanner.py         MARKET_BASELINE_20D = -1.33   (116.522 pengamatan)
    screen_eval.py     MARKET_BASELINE_20D = -1.33
    crowding.py        MARKET_BASELINE_20D = -0.67   (populasi matriksnya sendiri)
    portfolio_xray.py  BASELINE_PASAR      = 36.5    (win rate 40 hari)

Bedanya DISENGAJA dan sudah didokumentasikan di tempatnya masing-masing --
crowding.py bahkan menulis sendiri kenapa tidak boleh memakai -1,33.
Jadi masalahnya bukan "angkanya tidak seragam", dan modul ini tidak
berusaha menyatukannya.

Masalahnya: keempatnya hasil perhitungan SEKALI, lalu dibekukan ke dalam
kode, dan tidak ada satu pun yang pernah diukur ulang. Setiap kolom "vs
baseline" di seluruh app -- Scanner Lab, Screen Eval, Lensa Keramaian,
Rontgen Portofolio -- berdiri di atasnya. Kalau pasarnya bergeser, semua
penilaian itu ikut bergeser diam-diam: tidak ada yang rusak, tidak ada
yang lambat, tidak ada yang error. Persis mode kegagalan yang sama dengan
cache ber-TTL dulu, dan dengan angka ritel PSAB.

Modul ini menghitung ulang baseline dari data yang ADA SEKARANG, menyimpan
n dan periodenya, lalu membandingkannya dengan konstanta beku itu.
periksa() dipanggil dari kesehatan.py supaya penyimpangannya terlihat
sendiri, bukan menunggu seseorang curiga.

KENAPA NILAI BEKUNYA DIBACA DARI MODULNYA, BUKAN DISALIN KE SINI
================================================================
Menyalin -1,33 ke berkas ini akan membuat salinan KELIMA dari angka yang
sama, dan salinan kelima itu bisa ikut basi -- persis penyakit yang mau
diobati. TERDAFTAR di bawah menyebut nama modul dan nama variabelnya;
nilainya diambil lewat getattr saat dijalankan. Kalau seseorang mengubah
konstanta di modul asalnya, pemeriksaan di sini otomatis menguji angka
yang baru.

KENAPA ADA YANG SENGAJA TIDAK DIPERIKSA
=======================================
Baseline crowding berasal dari populasi matriksnya sendiri (keranjang
volume x nilai transaksi, 98.958 pengamatan). Filter itu tidak bisa
direkonstruksi di sini tanpa menyalin logikanya, dan salinan yang
menyimpang justru akan membuat pemeriksaan ini BERBOHONG -- melaporkan
penyimpangan yang sebenarnya cuma beda definisi. Jadi ia terdaftar
dengan semesta None: nilainya tetap ditampilkan, tapi tidak pernah
dibandingkan. Lebih baik mengaku tidak tahu daripada mengarang.
"""
try:
    from .runtime_paths import runtime_file as _runtime_file, market_file as _market_file, WEBSITE_DIR as _WEBSITE_DIR, PROJECT_DIR as _PROJECT_DIR, RUNTIME_DIR as _RUNTIME_DIR
except ImportError:
    from website.runtime_paths import runtime_file as _runtime_file, market_file as _market_file, WEBSITE_DIR as _WEBSITE_DIR, PROJECT_DIR as _PROJECT_DIR, RUNTIME_DIR as _RUNTIME_DIR

import glob
import os
import pickle
import time

import numpy as np
import pandas as pd

from .config import DAILY_PATH

SUMMARY_DIR = os.path.join(DAILY_PATH, 'Summary')
CACHE_FILE = str(_runtime_file('', 'baseline_cache.pkl'))

HORIZON = (20, 40)

# Rp200 juta/hari -- MIN_ADV pattern_miner. Dipakai ulang, bukan dipilih
# baru, supaya "likuid" berarti hal yang sama di kedua modul.
LIKUID_ADV = 2e8
ADV_LOOK = 20

SEMESTA = {
    'semua': 'Semua emiten, semua hari bursa, tanpa saringan.',
    'likuid': 'Nilai transaksi rata-rata 20 hari >= Rp200 juta.',
}

# Berapa bar pertama tiap emiten yang dilewati, PER SEMESTA.
#
# Versi pertama modul ini memakai 20 untuk keduanya, dan itu diam-diam
# salah: 20 bar itu cuma dibutuhkan sel "likuid" (ADV-nya rata-rata 20
# hari, jadi 19 bar pertama NaN). Sel "semua" tidak butuh apa-apa, tapi
# ikut kena -- sehingga "semua" sebenarnya berarti "semua kecuali bulan
# pertama tiap emiten".
#
# Bukan detail kecil. Dua puluh bar pertama itu jendela debut IPO, dan
# di periode ini isinya 17.562 pengamatan dengan rata-rata -5,05%
# (median -6,19%). Membuangnya menggeser baseline "semua" dari -1,03%
# jadi -0,34% -- 0,7 poin persen, cukup untuk membuat pemeriksaan di
# bawah menuduh scanner.py salah menyebut populasinya, padahal
# komentarnya benar dan modul inilah yang salah.
WARMUP = {'semua': 0, 'likuid': ADV_LOOK}

# Konstanta beku yang sedang dipakai app, beserta sel mana yang sebanding.
# semesta=None berarti definisinya tidak bisa direkonstruksi -- ditampilkan
# tapi tidak dibandingkan (lihat catatan panjang di atas).
TERDAFTAR = [
    # Asal-usulnya sudah dilacak: tidak ada script di repo yang
    # menghitungnya, jadi populasinya dicari dengan membalik -- varian
    # filter mana yang menghasilkan (n=116.522, mean=-1,33). Cocok PERSIS
    # pada: semua emiten, semua bar, tanpa saringan likuiditas, horizon
    # 20 hari, data sampai 4 September 2026. Komentar "SELURUH pasar" di
    # scanner.py benar apa adanya.
    dict(modul='scanner', nama='MARKET_BASELINE_20D', ukuran='mean',
         semesta='semua', horizon=20,
         asal=dict(n=116522, tanggal='2026-09-04'),
         catatan='Rata-rata return 20 hari seluruh pasar, data s.d. 4 Sep 2026.'),
    dict(modul='screen_eval', nama='MARKET_BASELINE_20D', ukuran='mean',
         semesta='semua', horizon=20,
         asal=dict(n=116522, tanggal='2026-09-04'),
         catatan='Nilai yang sama dengan scanner.py, asal yang sama.'),
    dict(modul='crowding', nama='MARKET_BASELINE_20D', ukuran='mean',
         semesta=None, horizon=20,
         catatan='Populasi matriks keramaian sendiri -- sengaja tidak dibandingkan.'),
    dict(modul='portfolio_xray', nama='BASELINE_PASAR', ukuran='win',
         semesta='semua', horizon=40,
         catatan='Win rate 40 hari, sumber sama dengan fake_accumulation.'),
]

# Selisih yang dianggap wajar. Bukan uji statistik -- ini ambang praktis:
# di bawah ini perbedaannya tidak akan mengubah kesimpulan halaman mana
# pun, di atas ini iya. Untuk win rate satuannya poin persen.
AMBANG = {'mean': 1.5, 'win': 5.0}


def _sumber_terbaru():
    from .kesegaran import summary_terbaru
    return summary_terbaru()


def hitung(force=False):
    """
    Ukur ulang seluruh sel (semesta x horizon) dari berkas Summary.

    Satu pengamatan per (emiten, hari bursa) -- tidak memakai langkah
    lompat seperti pattern_miner, karena ini populasi pembanding, bukan
    pencarian pola: tumpang tindih antar pengamatan tidak masalah untuk
    rata-rata, yang masalah cuma untuk p-value.
    """
    if not force:
        try:
            with open(CACHE_FILE, 'rb') as fh:
                isi = pickle.load(fh)
            if isi.get('ts', 0) >= _sumber_terbaru():
                hasil = dict(isi['result'])
                hasil['from_cache'] = True
                return hasil
        except Exception:
            pass

    t0 = time.time()
    kumpul = {(s, h): [] for s in SEMESTA for h in HORIZON}
    tanggal_min, tanggal_maks = None, None
    n_emiten = 0

    for path in glob.glob(os.path.join(SUMMARY_DIR, '*_Summary.csv')):
        try:
            df = pd.read_csv(path, usecols=['Date', 'Close', 'Volume'])
            df['Date'] = pd.to_datetime(df['Date'], format='%d-%b-%y', errors='coerce')
            df = df.dropna(subset=['Date']).sort_values('Date').reset_index(drop=True)
        except Exception:
            continue
        n = len(df)
        # Ambang per HORIZON, bukan satu ambang untuk semuanya: gerbang
        # tunggal max(HORIZON)+ADV_LOOK+2 membuang emiten yang sebenarnya
        # punya cukup bar untuk horizon 20, cuma kurang untuk horizon 40.
        if n < min(HORIZON) + 2:
            continue
        n_emiten += 1

        close = pd.to_numeric(df['Close'], errors='coerce').to_numpy(dtype=float)
        vol = pd.to_numeric(df['Volume'], errors='coerce').fillna(0.0).to_numpy(dtype=float)

        d0, d1 = df['Date'].iloc[0], df['Date'].iloc[-1]
        tanggal_min = d0 if tanggal_min is None or d0 < tanggal_min else tanggal_min
        tanggal_maks = d1 if tanggal_maks is None or d1 > tanggal_maks else tanggal_maks

        # Nilai transaksi rata-rata 20 hari, sejajar dengan tiap bar.
        adv = pd.Series(vol).rolling(ADV_LOOK).mean().to_numpy() * close
        sah = np.isfinite(close) & (close > 0)

        for h in HORIZON:
            akhir = n - h
            for semesta in SEMESTA:
                mulai = WARMUP[semesta]
                if akhir <= mulai:
                    continue
                i = np.arange(mulai, akhir)
                ok = sah[i] & np.isfinite(close[i + h])
                if semesta == 'likuid':
                    ok &= np.isfinite(adv[i]) & (adv[i] >= LIKUID_ADV)
                i = i[ok]
                if not len(i):
                    continue
                kumpul[(semesta, h)].append(
                    (close[i + h] - close[i]) / close[i] * 100.0)

    sel = {}
    for (s, h), potongan in kumpul.items():
        if not potongan:
            continue
        v = np.concatenate(potongan)
        sel['%s|%d' % (s, h)] = {
            'semesta': s, 'horizon': h,
            'n': int(len(v)),
            'mean': round(float(v.mean()), 2),
            'median': round(float(np.median(v)), 2),
            'win': round(float((v > 0).mean()) * 100, 1),
        }

    hasil = {
        'available': True,
        'sel': sel,
        'semesta': dict(SEMESTA),
        'horizon': list(HORIZON),
        'n_emiten': n_emiten,
        'periode': [str(tanggal_min.date()) if tanggal_min is not None else None,
                    str(tanggal_maks.date()) if tanggal_maks is not None else None],
        'as_of': time.strftime('%Y-%m-%d %H:%M'),
        'durasi_detik': round(time.time() - t0, 1),
        'from_cache': False,
    }

    try:
        with open(CACHE_FILE, 'wb') as fh:
            pickle.dump({'ts': time.time(), 'result': hasil}, fh)
    except Exception:
        pass

    return hasil


def _nilai_beku(modul, nama):
    """Baca konstanta dari modul asalnya. None kalau tidak ada lagi."""
    try:
        m = __import__('website.%s' % modul, fromlist=['x'])
    except Exception:
        return None
    return getattr(m, nama, None)


def bandingkan(force=False):
    """Tiap konstanta beku vs sel yang sebanding, plus selisihnya."""
    ukur = hitung(force=force)
    baris = []
    for t in TERDAFTAR:
        beku = _nilai_beku(t['modul'], t['nama'])
        entri = dict(t)
        entri['beku'] = beku
        entri['sekarang'] = None
        entri['selisih'] = None
        entri['melenceng'] = False
        entri['n'] = None

        if beku is None:
            entri['pesan'] = ('%s.%s sudah tidak ada -- daftar di baseline.py '
                              'perlu diperbarui.' % (t['modul'], t['nama']))
            baris.append(entri)
            continue
        if t['semesta'] is None:
            entri['pesan'] = t['catatan']
            baris.append(entri)
            continue

        s = ukur['sel'].get('%s|%d' % (t['semesta'], t['horizon']))
        if not s:
            entri['pesan'] = 'Sel pembandingnya tidak bisa dihitung.'
            baris.append(entri)
            continue

        entri['sekarang'] = s[t['ukuran']]
        entri['n'] = s['n']
        asal = t.get('asal')
        if asal:
            entri['n_asal'] = asal['n']
            entri['tanggal_asal'] = asal['tanggal']
            entri['pengamatan_baru'] = s['n'] - asal['n']
        entri['selisih'] = round(entri['sekarang'] - beku, 2)
        entri['melenceng'] = abs(entri['selisih']) > AMBANG[t['ukuran']]

        # Sel mana yang PALING dekat ke nilai bekunya. Kalau itu bukan sel
        # yang terdaftar, komentar di modul asalnya kemungkinan salah
        # menyebut populasinya -- dan pemeriksaan ini jadi membandingkan
        # dua definisi yang berbeda. Dilaporkan, tidak diperbaiki diam-diam:
        # menebak ulang populasi asal justru bikin angkanya makin susah
        # dilacak.
        kandidat = [(abs(c[t['ukuran']] - beku), k, c)
                    for k, c in ukur['sel'].items() if c['horizon'] == t['horizon']]
        if kandidat:
            jarak, kunci, c = min(kandidat)
            entri['cocok_terbaik'] = {'sel': kunci, 'nilai': c[t['ukuran']],
                                      'n': c['n'], 'jarak': round(jarak, 2)}
            entri['salah_semesta'] = (c['semesta'] != t['semesta']
                                      and jarak < abs(entri['selisih']) / 2)
        baris.append(entri)

    return {'available': True, 'ukur': ukur, 'baris': baris, 'ambang': dict(AMBANG)}


def periksa():
    """
    Dipanggil kesehatan.py. Daftar masalah; kosong berarti aman.

    Tidak pernah memaksa hitung ulang: dipanggil setiap pemeriksaan
    kesehatan, dan cache-nya sudah pakai aturan mtime sumber -- kalau
    Summary tidak berubah, angkanya memang tidak mungkin berubah.
    """
    try:
        h = bandingkan()
    except Exception as exc:
        return ['baseline tidak bisa dihitung: %s' % exc]

    masalah = []
    for b in h['baris']:
        if b.get('beku') is None:
            masalah.append(b.get('pesan'))
        elif b.get('salah_semesta'):
            ct = b['cocok_terbaik']
            masalah.append(
                '%s.%s = %s terdaftar sebagai semesta "%s" (sekarang %s), tapi jauh '
                'lebih cocok ke semesta "%s" (%s). Komentar di modul asalnya '
                'kemungkinan salah menyebut populasinya -- selama itu belum '
                'dipastikan, kolom "vs baseline" di halaman yang memakainya '
                'membandingkan dua populasi yang berbeda.'
                % (b['modul'], b['nama'], b['beku'], b['semesta'], b['sekarang'],
                   ct['sel'].split('|')[0], ct['nilai']))
        elif b['melenceng']:
            masalah.append(
                '%s.%s = %s, padahal diukur ulang dari data sekarang hasilnya %s '
                '(selisih %+.2f dari %s pengamatan). Setiap kolom "vs baseline" '
                'yang memakainya bergeser sebanyak itu tanpa ada yang terlihat rusak.'
                % (b['modul'], b['nama'], b['beku'], b['sekarang'], b['selisih'],
                   '{:,}'.format(b['n'])))
    return masalah


if __name__ == '__main__':
    h = bandingkan(force=True)
    u = h['ukur']
    print('periode %s .. %s | %d emiten | %.1f detik'
          % (u['periode'][0], u['periode'][1], u['n_emiten'], u['durasi_detik']))
    print()
    print('%-8s %-4s %10s %8s %8s %8s' % ('semesta', 'H', 'n', 'mean', 'median', 'win'))
    for k in sorted(u['sel']):
        s = u['sel'][k]
        print('%-8s %-4d %10s %8.2f %8.2f %8.1f'
              % (s['semesta'], s['horizon'], '{:,}'.format(s['n']),
                 s['mean'], s['median'], s['win']))
    print()
    for b in h['baris']:
        if b['sekarang'] is None:
            print('  %-16s %-20s beku=%-8s  (%s)'
                  % (b['modul'], b['nama'], b['beku'], b.get('pesan')))
        else:
            print('  %-16s %-20s beku=%-8s sekarang=%-8s selisih=%+.2f  %s'
                  % (b['modul'], b['nama'], b['beku'], b['sekarang'], b['selisih'],
                     'MELENCENG' if b['melenceng'] else 'wajar'))
    print()
    for m in periksa() or ['(tidak ada masalah)']:
        print('*', m)
