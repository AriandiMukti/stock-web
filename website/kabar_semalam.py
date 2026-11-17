"""
Kabar Semalam: layar pagi sebelum IDX buka. Apa yang sudah FINAL di luar
negeri sejak IDX tutup, dan saham mana yang kena lampu merah pagi ini.

DASAR (riset_pola_naik/lintas_pasar.py, 9 Okt 2026, data 2013-2026)
  - S&P 500 / Dow / Nasdaq / EIDO semalam menebak GAP pembukaan IHSG
    (korelasi 0,4-0,6), tapi open->close ~0: sudah dibayar di harga buka.
    Jadi TIDAK ADA lampu hijau di layar ini.
  - S&P jatuh dalam (20% malam terburuk) -> saham lapis tipis & sedang
    rata-rata MASIH turun 0,3-0,5% dari open ke close (t -2,7..-4,0 di
    2020-2026). Lapis tebal tidak konsisten -> tidak diberi lampu.
  - Komoditas jatuh dalam semalam -> saham komoditasnya lanjut turun
    open->close, −0,3..−0,4% vs rata-rata, negatif 13 dari 14 tahun.
  Lampu = "tunda beli pagi; kalau pegang, jual di open lebih baik dari
  menunggu". Bukan sinyal jual-kosong, bukan ramalan harian per saham.

ATURAN DIKUNCI 9 OKT 2026. Karena bacaan tiap pagi bisa dihitung ulang
dari riwayat harga (sesi luar negeri yang sudah final + Open/Close
Summary), penilaian maju TIDAK butuh halaman ini dibuka tiap pagi:
evaluasi() menghitung ulang semua hari bursa sejak MULAI_MAJU.

ATURAN WAKTU sama dengan riset: untuk hari bursa IDX T dengan tutup
sebelumnya Tp, kabar = return sesi bertanggal D, Tp <= D < T, yang sudah
final (bar sesi yang masih berjalan dibuang).
"""
try:
    from .runtime_paths import runtime_file as _runtime_file, market_file as _market_file, WEBSITE_DIR as _WEBSITE_DIR, PROJECT_DIR as _PROJECT_DIR, RUNTIME_DIR as _RUNTIME_DIR
except ImportError:
    from website.runtime_paths import runtime_file as _runtime_file, market_file as _market_file, WEBSITE_DIR as _WEBSITE_DIR, PROJECT_DIR as _PROJECT_DIR, RUNTIME_DIR as _RUNTIME_DIR
import glob
import logging
import os
import pickle
import time

import numpy as np
import pandas as pd

from .config import DAILY_PATH

logger = logging.getLogger(__name__)

HERE = os.path.dirname(os.path.abspath(__file__))
RIWAYAT_FILE = str(_runtime_file('', 'kabar_semalam_riwayat.pkl'))
SUMMARY_DIR = os.path.join(DAILY_PATH, 'Summary')
MULAI_MAJU = pd.Timestamp('2026-10-12')     # hari bursa pertama sesudah aturan dikunci
TTL = 1800

LAMPU = {     # seri yang lampunya diuji
    '^GSPC': 'S&P 500', 'BZ=F': 'Minyak Brent', 'GC=F': 'Emas', 'HG=F': 'Tembaga',
}
INFO = {     # ditampilkan saja -- arah ke GAP, bukan ke open->close
    '^IXIC': 'Nasdaq', '^DJI': 'Dow', '^VIX': 'VIX', 'EIDO': 'EIDO (ETF Indonesia di NY)',
    'TLK': 'TLK (ADR Telkom)', 'IDR=X': 'USD/IDR', 'CL=F': 'Minyak WTI', 'BTC-USD': 'Bitcoin',
}
LIKUID_MIN = 1e9


def _ambang():
    from .rapat_agen import _ambang_q1
    return _ambang_q1()


def _kembar():
    from .rapat_agen import KEMBAR_KOMODITAS
    return KEMBAR_KOMODITAS


# ------------------------------------------------------------ data luar negeri
def _riwayat(force=False):
    """Close harian semua seri, ~1 tahun, bar sesi berjalan dibuang. Cache TTL."""
    if not force and os.path.exists(RIWAYAT_FILE):
        try:
            with open(RIWAYAT_FILE, 'rb') as fh:
                s = pickle.load(fh)
            if time.time() - s['ts'] < TTL:
                return s['close']
        except Exception:
            pass
    import yfinance as yf
    tick = list(LAMPU) + list(INFO)
    d = yf.download(tick, period='1y', auto_adjust=False, progress=False, group_by='ticker')
    kini_et = pd.Timestamp.now(tz='America/New_York')
    final = pd.Timestamp(kini_et.date()) - pd.Timedelta(days=0 if kini_et.hour >= 17 else 1)
    close = {}
    for t in tick:
        try:
            c = d[t]['Close'].dropna()
        except KeyError:
            continue
        c = c[~c.index.duplicated(keep='last')]
        close[t] = c[c.index <= final]
    try:
        with open(RIWAYAT_FILE, 'wb') as fh:
            pickle.dump({'ts': time.time(), 'close': close, 'final': final}, fh)
    except Exception:
        pass
    return close


def _ret(c, tp, t=None):
    """Return log kumulatif sesi bertanggal D, tp <= D < t (t=None: sampai bar final terakhir)."""
    baru = c[c.index >= tp] if t is None else c[(c.index >= tp) & (c.index < t)]
    lama = c[c.index < tp]
    if not len(baru) or not len(lama):
        return None, None
    return float(np.log(baru.iloc[-1] / lama.iloc[-1])), baru.index[-1]


# ------------------------------------------------------------ data IDX
def _summary_oc():
    """Open/Close/Volume Summary semua emiten -> tiga DataFrame tanggal x emiten."""
    from .tembus_basis import _baca_summary
    o, c, v = {}, {}, {}
    for path in glob.glob(os.path.join(SUMMARY_DIR, '*_Summary.csv')):
        s = os.path.basename(path).replace('_Summary.csv', '')
        df = _baca_summary(path)
        if df is None or len(df) < 25:
            continue
        o[s], c[s], v[s] = df['Open'], df['Close'], df['Volume']
    return pd.DataFrame(o).sort_index(), pd.DataFrame(c).sort_index(), pd.DataFrame(v).sort_index()


def _lapis(close, vol, hari):
    """Lapis likuiditas per emiten pada hari `hari`: median nilai 20 hari, tersil di antara yang >= Rp1 M."""
    nilai = (close * vol).loc[:hari].tail(20).median()
    nilai = nilai[nilai >= LIKUID_MIN]
    if nilai.empty:
        return pd.Series(dtype=object)
    q1, q2 = nilai.quantile([1 / 3, 2 / 3])
    return pd.Series(np.where(nilai <= q1, 'tipis', np.where(nilai <= q2, 'sedang', 'tebal')), index=nilai.index)


def _lampu_hari(rets, ambang):
    merah = {k: (r is not None and r <= ambang[k]) for k, r in rets.items() if k in LAMPU}
    return merah


def _kena(merah, lapis):
    """Saham kena lampu: {stock: [alasan,...]}."""
    kena = {}
    if merah.get('^GSPC'):
        for s, l in lapis.items():
            if l in ('tipis', 'sedang'):
                kena.setdefault(s, []).append('spx')
    for s, k in _kembar().items():
        if merah.get(k) and s in lapis.index:
            kena.setdefault(s, []).append(k)
    return kena


# ------------------------------------------------------------ pagi ini
def bacaan(force=False):
    try:
        R = _riwayat(force)
    except Exception as exc:
        logger.exception('Kabar semalam: riwayat gagal')
        return {'available': False, 'message': 'Data luar negeri tidak terbaca: %s' % exc}
    from .tembus_basis import _baca_summary
    bb = _baca_summary(os.path.join(SUMMARY_DIR, 'BBCA_Summary.csv'))
    tp = bb.index[-1]
    ambang = _ambang()
    seri, rets = [], {}
    for k, nama in list(LAMPU.items()) + list(INFO.items()):
        c = R.get(k)
        r, sesi = _ret(c, tp) if c is not None else (None, None)
        rets[k] = r
        seri.append({'kode': k, 'nama': nama, 'lampu': k in LAMPU,
                     'ret': round(r * 100, 2) if r is not None else None,
                     'sesi': sesi.strftime('%Y-%m-%d') if sesi is not None else None,
                     'ambang': round(ambang[k] * 100, 2) if k in ambang else None,
                     'merah': bool(k in LAMPU and r is not None and r <= ambang[k])})
    merah = _lampu_hari(rets, ambang)
    o, c, v = _summary_oc()
    lapis = _lapis(c, v, tp)
    kena = _kena(merah, lapis)
    kembar = _kembar()
    daftar = [{'stock': s, 'lapis': lapis.get(s), 'alasan': a,
               'komoditas': LAMPU.get(kembar.get(s)) if kembar.get(s) else None,
               'close': float(c[s].dropna().iloc[-1]) if s in c else None}
              for s, a in sorted(kena.items())]
    return {
        'available': True, 'idx_terakhir': tp.strftime('%Y-%m-%d'),
        'ada_sesi': any(x['ret'] is not None for x in seri),
        'seri': seri, 'merah': [k for k, m in merah.items() if m],
        'kena': daftar, 'n_kena': len(daftar),
        'n_likuid': int(len(lapis)), 'n_lapis': lapis.value_counts().to_dict(),
        'kembar': [{'stock': s, 'komoditas': LAMPU[k]} for s, k in sorted(kembar.items())],
        'dibangun': time.strftime('%Y-%m-%d %H:%M'),
    }


# ------------------------------------------------------------ penilaian maju
def evaluasi(force=False):
    """Hitung ulang lampu tiap hari bursa sejak MULAI_MAJU, lalu bandingkan open->close
    kelompok yang kena lampu dengan hari tanpa lampu (aturan dikunci 9 Okt 2026)."""
    try:
        R = _riwayat(force)
    except Exception as exc:
        return {'available': False, 'message': 'Data luar negeri tidak terbaca: %s' % exc}
    o, c, v = _summary_oc()
    hari = c.index[c.index >= MULAI_MAJU]
    if not len(hari):
        return {'available': False, 'mulai': MULAI_MAJU.strftime('%Y-%m-%d'),
                'message': 'Belum ada hari bursa sejak aturan dikunci (%s).' % MULAI_MAJU.strftime('%d %b %Y')}
    ambang = _ambang()
    semua = c.index
    baris = []
    for t in hari:
        tp = semua[semua.get_loc(t) - 1]
        rets = {k: _ret(R[k], tp, t)[0] for k in LAMPU if k in R}
        merah = _lampu_hari(rets, ambang)
        lapis = _lapis(c, v, tp)
        kena = _kena(merah, lapis)
        oc = np.log(c.loc[t] / o.loc[t])
        basi = (o.loc[t] - c.loc[tp]).abs() < 1e-9          # open = close kemarin -> dibuang (sama dgn riset)
        oc = oc[~basi & oc.notna() & np.isfinite(oc)]
        for s in lapis.index.intersection(oc.index):
            baris.append({'tanggal': t, 'stock': s, 'lapis': lapis[s], 'oc': float(oc[s]),
                          'spx_merah': bool(merah.get('^GSPC')),
                          'kena_spx': 'spx' in kena.get(s, []),
                          'komoditas': _kembar().get(s),
                          'kena_kom': any(a != 'spx' for a in kena.get(s, []))})
    d = pd.DataFrame(baris)
    if d.empty:
        return {'available': False, 'message': 'Belum ada Open/Close untuk dinilai.'}

    def _grp(g):
        return {'n': int(len(g)), 'hari': int(g['tanggal'].nunique()),
                'oc': round(float(g['oc'].mean() * 100), 3) if len(g) else None}

    kecil = d[d['lapis'].isin(['tipis', 'sedang'])]
    kom = d[d['komoditas'].notna()]
    return {
        'available': True, 'mulai': MULAI_MAJU.strftime('%Y-%m-%d'),
        'n_hari': int(d['tanggal'].nunique()),
        'spx': {'merah': _grp(kecil[kecil['spx_merah']]), 'biasa': _grp(kecil[~kecil['spx_merah']]),
                'harapan': 'merah lebih rendah 0,3-0,5 poin % dari biasa'},
        'komoditas': {'merah': _grp(kom[kom['kena_kom']]), 'biasa': _grp(kom[~kom['kena_kom']]),
                      'harapan': 'merah lebih rendah ~0,3-0,4 poin % dari biasa'},
        'cukup': bool(d[d['spx_merah']]['tanggal'].nunique() >= 20),
    }


def scan(force=False):
    from .berita_global import berita
    kabar_global = berita(force)
    try:
        h = bacaan(force)
    except Exception:
        logger.exception('Kabar semalam: bacaan gagal')
        h = {'available': False, 'message': 'Data pasar belum tersedia.'}
    h['berita_global'] = kabar_global
    if h.get('available'):
        try:
            h['jurnal'] = evaluasi(False)
        except Exception as exc:
            logger.exception('Kabar semalam: evaluasi gagal')
            h['jurnal'] = {'available': False, 'message': 'Gagal: %s' % exc}
    return h


if __name__ == '__main__':
    import json
    import sys
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass
    h = scan(force=True)
    h2 = dict(h); h2['kena'] = h2.get('kena', [])[:8]; h2.pop('kembar', None)
    print(json.dumps(h2, indent=1, ensure_ascii=False, default=str)[:4000])
