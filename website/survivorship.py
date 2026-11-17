"""
Emiten Hilang: siapa yang berhenti mengirim data, dan dalam keadaan apa
mereka berhenti.

KENAPA MODUL INI ADA
Setiap angka "luar sampel" di app ini dihitung dari emiten yang MASIH
ADA. Folder Test berisi 21 emiten besar yang semuanya masih
diperdagangkan hari ini. Untuk sebagian besar temuan itu bias kecil.
Untuk satu temuan, itu bias yang bisa membalik kesimpulannya:

    jatuh_dalam.py bilang "beli yang baru jatuh >40% dari puncak 60 hari".
    Emiten yang jatuh 40% LALU TERUS JATUH sampai disuspend permanen
    adalah persis kelompok yang hilang dari data.

Selisih yang mencurigakan sudah terlihat tanpa modul ini:

    setup yang sama, return majemuk 20 hari
      21 emiten penyintas, 2016-2025 : +13,2%
      788 emiten penuh, 2026         :  -2,5%

Lima belas poin. Itu bukan bukti survivorship -- rezimnya juga beda --
tapi bentuknya persis seperti yang diharapkan kalau survivorship yang
mengangkatnya. Modul ini mengukur bagian yang BISA diukur dari data yang
ada: berapa banyak emiten berhenti mengirim data, dan apakah mereka
terkonsentrasi di zona jatuh dalam.

BEDA DENGAN data_confidence.py
Modul itu menilai kesegaran data PER EMITEN untuk menjawab "boleh
percaya angka emiten ini?" -- satu skor, satu emiten, dipakai sebagai
peringatan. Modul ini menjawab pertanyaan yang berbeda: "dari seluruh
bursa, siapa saja yang hilang, DALAM KEADAAN APA mereka hilang, dan
seberapa besar itu merusak backtest?" Yang pertama soal kepercayaan
tampilan; yang kedua soal kepercayaan kesimpulan.

APA YANG TIDAK BISA DIUKUR DARI SINI -- INI HARUS JUJUR
Emiten yang sudah delisting SEBELUM 2 Januari 2026 tidak punya berkas
Summary sama sekali, jadi tidak muncul di sini dan tidak bisa dihitung.
Yang terukur cuma yang hilang DI DALAM jendela data. Artinya angka di
halaman ini batas BAWAH dari bias yang sebenarnya, bukan ukuran penuhnya.

Juga: "berhenti mengirim data" bukan berarti delisting. Bisa suspensi
sementara, bisa masalah unduhan. Karena itu yang dilaporkan lamanya
menghilang, bukan vonis.
"""
try:
    from .runtime_paths import runtime_file as _runtime_file, market_file as _market_file, WEBSITE_DIR as _WEBSITE_DIR, PROJECT_DIR as _PROJECT_DIR, RUNTIME_DIR as _RUNTIME_DIR
except ImportError:
    from website.runtime_paths import runtime_file as _runtime_file, market_file as _market_file, WEBSITE_DIR as _WEBSITE_DIR, PROJECT_DIR as _PROJECT_DIR, RUNTIME_DIR as _RUNTIME_DIR
import glob
import logging
import os
import pickle

import numpy as np
import pandas as pd

from .config import DAILY_PATH

logger = logging.getLogger(__name__)

SUMMARY_DIR = os.path.join(DAILY_PATH, 'Summary')
CACHE_FILE = str(_runtime_file('', 'survivorship_cache.pkl'))

C = {
    'HILANG_MIN': 5,      # tertinggal >= sekian hari bursa = dianggap hilang
    'HILANG_LAMA': 20,    # >= sekian hari = hilang lama, kemungkinan besar suspensi
    'PUNCAK_W': 60,       # sama dengan jatuh_dalam.py, supaya zonanya sebanding
    'DALAM': -40.0,       # ambang zona jatuh dalam, sama dengan jatuh_dalam.py
    'VOL_W': 20,
}


def _muat(path):
    KOL = ['Date', 'High', 'Low', 'Close', 'Volume', 'Avg Price']
    try:
        d = pd.read_csv(path, usecols=KOL)[KOL]
    except Exception:
        return None
    d.columns = ['date', 'high', 'low', 'close', 'volume', 'avgp']
    d['date'] = pd.to_datetime(d['date'], format='%d-%b-%y', errors='coerce')
    d = d.dropna(subset=['date']).sort_values('date')
    for c in ['high', 'low', 'close', 'volume', 'avgp']:
        d[c] = pd.to_numeric(d[c], errors='coerce')
    d = d[d['close'] > 0]
    return d if len(d) >= 25 else None


def _keadaan(d):
    """Keadaan emiten pada bar TERAKHIR yang dia kirim."""
    close = float(d['close'].iloc[-1])
    puncak = float(d['close'].tail(C['PUNCAK_W']).max())
    dari = (close / puncak - 1) * 100 if puncak > 0 else None
    r = d['close'].pct_change()
    vol = float(r.tail(C['VOL_W']).std() * 100) if r.tail(C['VOL_W']).notna().sum() >= 12 else None
    chg20 = None
    if len(d) > 20:
        c0 = float(d['close'].iloc[-21])
        if c0 > 0:
            chg20 = (close / c0 - 1) * 100
    nilai = d['avgp'] * d['volume']
    adv = float(nilai.tail(20).mean()) if nilai.tail(20).notna().sum() >= 10 else None
    return {'close': close, 'dari_puncak': round(dari, 1) if dari is not None else None,
            'volat': round(vol, 2) if vol is not None else None,
            'chg20': round(chg20, 1) if chg20 is not None else None,
            'adv': adv}


def _sumber_terbaru():
    from .kesegaran import summary_terbaru
    return summary_terbaru()


def scan(force=False):
    if not force:
        try:
            with open(CACHE_FILE, 'rb') as fh:
                cached = pickle.load(fh)
            if cached.get('ts', 0) >= _sumber_terbaru():
                return cached['hasil']
        except Exception:
            pass

    semua = {}
    for path in glob.glob(os.path.join(SUMMARY_DIR, '*_Summary.csv')):
        stock = os.path.basename(path).split('_')[0].upper()
        d = _muat(path)
        if d is not None:
            semua[stock] = d
    if not semua:
        return {'available': False, 'message': 'Tidak ada berkas Summary terbaca.'}

    # Hari bursa terakhir = tanggal paling baru di SELURUH bursa, bukan per
    # emiten. Emiten yang berhenti mengirim tidak boleh mendefinisikan
    # sendiri apa itu "hari ini".
    kalender = sorted({t for d in semua.values() for t in d['date']})
    terakhir_bursa = kalender[-1]
    urutan = {t: i for i, t in enumerate(kalender)}

    hilang, hidup_dalam, hilang_dalam = [], 0, 0
    for stock, d in semua.items():
        akhir = d['date'].iloc[-1]
        tertinggal = urutan[terakhir_bursa] - urutan.get(akhir, 0)
        k = _keadaan(d)
        di_zona = k['dari_puncak'] is not None and k['dari_puncak'] <= C['DALAM']
        if tertinggal >= C['HILANG_MIN']:
            if di_zona:
                hilang_dalam += 1
            hilang.append(dict(stock=stock, tertinggal=int(tertinggal),
                               tanggal_akhir=akhir.strftime('%Y-%m-%d'),
                               lama=bool(tertinggal >= C['HILANG_LAMA']),
                               di_zona_dalam=bool(di_zona), **k))
        elif di_zona:
            hidup_dalam += 1

    hilang.sort(key=lambda x: (-x['tertinggal'], x['dari_puncak'] or 0))
    n_zona = hidup_dalam + hilang_dalam
    porsi_zona = (hilang_dalam / n_zona * 100) if n_zona else None
    n_all = len(semua)
    porsi_semua = (len(hilang) / n_all * 100) if n_all else None

    hasil = {
        'available': True,
        'terakhir_bursa': terakhir_bursa.strftime('%Y-%m-%d'),
        'total_emiten': n_all,
        'hilang': hilang,
        'jumlah_hilang': len(hilang),
        'jumlah_hilang_lama': sum(1 for h in hilang if h['lama']),
        'porsi_hilang': round(porsi_semua, 1) if porsi_semua is not None else None,
        # Ini angka intinya: apakah yang hilang MENUMPUK di zona jatuh dalam?
        'zona': {
            'n': n_zona, 'hilang': hilang_dalam, 'hidup': hidup_dalam,
            'porsi': round(porsi_zona, 1) if porsi_zona is not None else None,
            'porsi_semua': round(porsi_semua, 1) if porsi_semua is not None else None,
            'kelipatan': (round(porsi_zona / porsi_semua, 2)
                          if porsi_zona and porsi_semua else None),
        },
        'config': C,
        'catatan': (
            'Emiten yang delisting SEBELUM 2 Januari 2026 tidak punya berkas Summary '
            'sama sekali, jadi tidak terhitung di sini. Angka ini batas BAWAH dari bias '
            'yang sebenarnya. "Berhenti mengirim data" juga bukan vonis delisting -- '
            'bisa suspensi sementara atau masalah unduhan, karena itu yang dilaporkan '
            'lamanya menghilang, bukan statusnya.'),
    }
    try:
        with open(CACHE_FILE, 'wb') as fh:
            pickle.dump({'ts': _sumber_terbaru(), 'hasil': hasil}, fh)
    except Exception:
        logger.exception('Gagal menulis cache Emiten Hilang')
    return hasil
