"""
Rekam jejak keputusan sendiri: dari semua yang DIPUTUSKAN, mana yang benar.

KENAPA MODUL INI ADA
====================
App ini mengukur pasar dari banyak sudut -- Scanner Lab, Screen Eval,
Signal Recall, Penemu Pola, Kering Screener. Semuanya menjawab bentuk
pertanyaan yang sama: "apakah kriteria X memprediksi harga?"

Tidak satu pun menjawab pertanyaan yang berbeda jenisnya: **apakah
keputusan pengguna sendiri cenderung benar, dan sinyal mana di kartu
keputusan yang benar-benar membedakan hasilnya.** Itu pola orangnya,
bukan pola sahamnya, dan tidak ada backtest pasar yang bisa
menjawabnya -- datanya cuma ada di tabel DecisionSnapshot dan
WatchlistHistory milik app ini.

Jurnal Keputusan yang sudah ada menampilkan snapshot satu per satu
dengan perubahan harga sampai HARI INI. Itu tidak bisa dijumlahkan:
entry umur 3 hari dan entry umur 6 bulan bercampur di kolom yang sama,
jadi rata-ratanya mengukur "sudah berapa lama dicatat" sebagian besar,
bukan kualitas keputusannya. Modul ini memakai HORIZON TETAP dalam hari
bursa, persis seperti seluruh evaluasi lain di app ini.

BERAPA BANYAK DATANYA (per 11 Sep 2026)
=======================================
Sedikit, dan itu harus dikatakan di muka:

  DecisionSnapshot watchlist_add   67, tapi semuanya 6-11 Sep 2026
  WatchlistHistory                201 (124 masuk, 77 keluar), 29 Agu-11 Sep
  episode masuk->keluar sungguhan   49 (11 lagi selesai di hari yang sama)

Artinya horizon 20 dan 40 hari BELUM ADA SATU PUN yang matang, dan baru
akan ada mulai awal Oktober. Yang bisa dijawab hari ini cuma horizon
pendek (H+1 sampai H+5). Modul ini tetap menghitung semuanya dan
melaporkan berapa yang matang per horizon -- sama seperti pola_jurnal.py,
angka yang belum ada ditampilkan sebagai "belum matang", bukan sebagai
nol.

KENAPA KELUAR IKUT DIUKUR
=========================
Masuk dan keluar dua keputusan terpisah, dan yang kedua tidak pernah
diperiksa sama sekali. "Sesudah saya buang dari watchlist, harganya naik
atau turun?" Kalau sesudah dibuang harganya justru naik terus, keluarnya
yang mahal -- dan itu tidak akan pernah terlihat dari mengukur
penambahan saja.
"""
from .models import scoped_query

import json
import os
from collections import defaultdict

import numpy as np
import pandas as pd

from .config import DAILY_PATH
from .models import DecisionSnapshot, WatchlistHistory

SUMMARY_DIR = os.path.join(DAILY_PATH, 'Summary')

# Horizon pendek ikut dihitung BUKAN karena lebih informatif -- sebaliknya,
# semakin pendek semakin didominasi noise. Alasannya cuma satu: itu yang
# datanya sudah ada sekarang. Horizon 20 & 40 tetap dihitung supaya
# halaman ini langsung berfungsi begitu catatannya cukup tua, tanpa perlu
# disentuh lagi.
HORIZON = (1, 3, 5, 10, 20, 40)

MIN_N = 8            # di bawah ini barisnya tidak ditampilkan sama sekali

# Ambang KEDUA, dan yang lebih penting. MIN_N cuma menahan baris yang
# benar-benar kosong; MIN_N_BACA menandai mana yang boleh dibaca sebagai
# sesuatu. Dua ambang, bukan satu, karena kesalahan yang mau dicegah di
# sini bukan "tabelnya kosong" tapi "win 80% dari 10 keputusan dibaca
# sebagai temuan". Dengan 5 dimensi pembelah x beberapa kelompok x 6
# horizon, ada puluhan sel diuji sekaligus -- sebagian akan terlihat
# mencolok murni karena kebetulan, persis alasan pattern_miner.py memakai
# koreksi FDR. Di sini belum ada cukup data untuk dikoreksi, jadi yang
# dipakai cara yang lebih tumpul: di bawah ambang ini angkanya ditandai
# tidak layak baca.
MIN_N_BACA = 30


# ---------------------------------------------------------------------------
# HARGA
# ---------------------------------------------------------------------------
def _seri(stock, _cache={}):
    """(daftar tanggal 'YYYY-MM-DD', array Close) untuk satu emiten."""
    if stock in _cache:
        return _cache[stock]
    path = os.path.join(SUMMARY_DIR, '%s_Summary.csv' % stock)
    hasil = (None, None)
    if os.path.exists(path):
        try:
            df = pd.read_csv(path, usecols=['Date', 'Close'])
            df['Date'] = pd.to_datetime(df['Date'], format='%d-%b-%y', errors='coerce')
            df = df.dropna(subset=['Date']).sort_values('Date').reset_index(drop=True)
            hasil = ([str(d.date()) for d in df['Date']],
                     pd.to_numeric(df['Close'], errors='coerce').to_numpy())
        except Exception:
            pass
    _cache[stock] = hasil
    return hasil


def _jangkar(tanggal, hari):
    """
    Indeks hari bursa TERAKHIR yang <= tanggal keputusan.

    Keputusan dicatat dengan jam dinding, jadi bisa jatuh di akhir pekan,
    hari libur, atau sesudah penutupan. Memakai "hari bursa terakhir yang
    sudah lewat" membuat jangkarnya selalu harga yang benar-benar sudah
    terlihat saat keputusan diambil -- bukan harga besok.
    """
    lo, hi, jawab = 0, len(hari) - 1, None
    while lo <= hi:
        tengah = (lo + hi) // 2
        if hari[tengah] <= tanggal:
            jawab = tengah
            lo = tengah + 1
        else:
            hi = tengah - 1
    return jawab


def _maju(stock, tanggal, n):
    """Return n hari bursa sesudah `tanggal`; None kalau belum matang."""
    hari, close = _seri(stock)
    if not hari:
        return None
    i = _jangkar(tanggal, hari)
    if i is None or i + n >= len(close):
        return None
    c0, c1 = close[i], close[i + n]
    if not np.isfinite(c0) or c0 <= 0 or not np.isfinite(c1):
        return None
    return (c1 - c0) / c0 * 100.0


# ---------------------------------------------------------------------------
# PENGELOMPOKAN
# ---------------------------------------------------------------------------
def _kelompok(row):
    """
    Label-label yang bisa dipakai membelah hasil satu keputusan.

    Dipilih dari apa yang MEMANG tersimpan di kartu saat keputusan
    diambil, bukan dari apa yang bisa dihitung sekarang. Menghitung ulang
    dari data hari ini akan memakai angka yang belum ada waktu itu, dan
    hasilnya bukan lagi ukuran keputusan.
    """
    out = {'Daftar': row.listType or '(tanpa daftar)'}

    scanner = json.loads(row.scannerJson) if row.scannerJson else None
    kering = json.loads(row.keringJson) if row.keringJson else None
    flow = json.loads(row.flowJson) if row.flowJson else None

    if scanner:
        out['Scanner'] = scanner.get('scanner_label') or '(tanpa label)'
        skor = scanner.get('score')
        if isinstance(skor, (int, float)):
            out['Skor scanner'] = ('>= 70' if skor >= 70 else
                                   '50 - 69' if skor >= 50 else '< 50')
    else:
        out['Scanner'] = 'tanpa sinyal scanner'

    if kering and isinstance(kering.get('skor'), (int, float)):
        out['Skor kering'] = '>= 0,7' if kering['skor'] >= 0.7 else '< 0,7'

    if flow and flow.get('label'):
        out['Kesehatan arus'] = flow['label']
    else:
        out['Kesehatan arus'] = 'tanpa checkpoint'

    return out


def _statistik(nilai):
    v = np.asarray([x for x in nilai if x is not None], dtype=float)
    if not len(v):
        return None
    return {
        'n': int(len(v)),
        'win': round(float((v > 0).mean()) * 100, 1),
        'mean': round(float(v.mean()), 2),
        'median': round(float(np.median(v)), 2),
    }


# ---------------------------------------------------------------------------
# MASUK
# ---------------------------------------------------------------------------
def penambahan():
    """
    Hasil tiap keputusan MENAMBAH ke watchlist, pada horizon tetap.

    Baseline-nya adalah seluruh penambahan pada horizon yang sama, jadi
    "Skor scanner >= 70 unggul +8" berarti unggul terhadap keputusan pengguna
    yang lain -- bukan terhadap pasar. Itu perbandingan yang tepat di
    sini: pertanyaannya bukan "apakah lebih baik dari beli acak", tapi
    "dari keputusan yang saya ambil, mana yang lebih baik".
    """
    rows = (scoped_query(DecisionSnapshot).filter_by(reason='watchlist_add')
            .order_by(DecisionSnapshot.timestamp).all())

    catatan = []
    for row in rows:
        if not row.timestamp:
            continue
        tanggal = str(row.timestamp.date())
        maju = {h: _maju(row.stock, tanggal, h) for h in HORIZON}
        catatan.append({'stock': row.stock, 'tanggal': tanggal,
                        'kelompok': _kelompok(row), 'maju': maju})

    hasil = {
        'n_keputusan': len(catatan),
        'min_n_baca': MIN_N_BACA,
        'mulai': catatan[0]['tanggal'] if catatan else None,
        'terakhir': catatan[-1]['tanggal'] if catatan else None,
        'horizon': list(HORIZON),
        'min_n': MIN_N,
        'matang': {h: sum(1 for c in catatan if c['maju'][h] is not None)
                   for h in HORIZON},
        'baseline': {h: _statistik([c['maju'][h] for c in catatan]) for h in HORIZON},
        'belah': {},
    }

    # Satu tabel per dimensi pembelah.
    dimensi = defaultdict(lambda: defaultdict(list))
    for c in catatan:
        for dim, nilai in c['kelompok'].items():
            dimensi[dim][nilai].append(c)

    for dim, kelompok in dimensi.items():
        baris = []
        for nilai, anggota in kelompok.items():
            entri = {'nilai': nilai, 'n_keputusan': len(anggota), 'per_horizon': {}}
            for h in HORIZON:
                st = _statistik([a['maju'][h] for a in anggota])
                if st and st['n'] >= MIN_N:
                    dasar = hasil['baseline'][h]
                    st['vs_baseline'] = (round(st['win'] - dasar['win'], 1)
                                         if dasar else None)
                    st['layak'] = st['n'] >= MIN_N_BACA
                    entri['per_horizon'][h] = st
            baris.append(entri)
        baris.sort(key=lambda b: -b['n_keputusan'])
        hasil['belah'][dim] = baris

    return hasil


# ---------------------------------------------------------------------------
# KELUAR
# ---------------------------------------------------------------------------
def pembuangan():
    """
    Kualitas keputusan KELUAR: sesudah dibuang dari watchlist, harganya
    ke mana?

    Return positif sesudah keluar berarti keluarnya mahal -- saham itu
    masih naik tanpa pengguna. Ini satu-satunya sisi yang tidak pernah
    diperiksa; semua evaluasi lain di app ini berhenti di titik masuk.

    Episode yang masuk dan keluar di hari yang sama dibuang: itu koreksi
    input, bukan keputusan memegang.
    """
    ev = defaultdict(list)
    for x in (scoped_query(WatchlistHistory)
              .order_by(WatchlistHistory.timestamp).all()):
        if x.timestamp:
            ev[(x.stock, x.listType)].append(x)

    episode = []
    for (stock, listType), xs in ev.items():
        buka = None
        for x in xs:
            if x.action == 'added':
                buka = x
            elif x.action == 'removed' and buka is not None:
                hari = (x.timestamp.date() - buka.timestamp.date()).days
                if hari > 0:
                    episode.append({
                        'stock': stock, 'listType': listType,
                        'masuk': str(buka.timestamp.date()),
                        'keluar': str(x.timestamp.date()),
                        'hari_kalender': hari,
                        'harga_masuk': buka.avgPrice,
                        'harga_keluar': x.avgPrice,
                    })
                buka = None

    for e in episode:
        hm, hk = e['harga_masuk'], e['harga_keluar']
        e['saat_dipegang'] = (round((hk - hm) / hm * 100, 2)
                              if hm and hk and hm > 0 else None)
        e['setelah_keluar'] = {h: _maju(e['stock'], e['keluar'], h) for h in HORIZON}

    episode.sort(key=lambda e: e['keluar'], reverse=True)

    return {
        'n_episode': len(episode),
        'horizon': list(HORIZON),
        'min_n': MIN_N,
        'min_n_baca': MIN_N_BACA,
        'matang': {h: sum(1 for e in episode if e['setelah_keluar'][h] is not None)
                   for h in HORIZON},
        'saat_dipegang': _statistik([e['saat_dipegang'] for e in episode]),
        'setelah_keluar': {h: _statistik([e['setelah_keluar'][h] for e in episode])
                           for h in HORIZON},
        'hari_median': (round(float(np.median([e['hari_kalender'] for e in episode])), 1)
                        if episode else None),
        'episode': episode[:100],
    }


def rekam_jejak():
    """Kedua sisi sekaligus -- ini yang dipanggil endpoint."""
    return {'available': True, 'masuk': penambahan(), 'keluar': pembuangan()}


if __name__ == '__main__':
    from . import create_app
    with create_app(warm_cache=False).app_context():
        h = rekam_jejak()
        m, k = h['masuk'], h['keluar']
        print('PENAMBAHAN: %d keputusan (%s .. %s)'
              % (m['n_keputusan'], m['mulai'], m['terakhir']))
        print('  matang per horizon:', m['matang'])
        for hh in m['horizon']:
            if m['baseline'][hh]:
                print('  H+%-2d baseline: %s' % (hh, m['baseline'][hh]))
        for dim, baris in m['belah'].items():
            ada = [b for b in baris if b['per_horizon']]
            if ada:
                print('  [%s]' % dim)
                for b in ada:
                    for hh, st in sorted(b['per_horizon'].items()):
                        print('     H+%-2d %-28s n=%-3d win %5.1f  vs %s'
                              % (hh, b['nilai'][:28], st['n'], st['win'], st['vs_baseline']))
        print()
        print('PEMBUANGAN: %d episode, median %s hari' % (k['n_episode'], k['hari_median']))
        print('  saat dipegang :', k['saat_dipegang'])
        print('  matang        :', k['matang'])
        for hh in k['horizon']:
            if k['setelah_keluar'][hh]:
                print('  H+%-2d setelah keluar: %s' % (hh, k['setelah_keluar'][hh]))
