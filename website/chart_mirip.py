"""
Chart Termirip: 100 jendela harga 30 hari yang paling mirip dengan chart
sebuah emiten hari ini, diambil dari ~750 emiten likuid 2013-2026, dan apa
yang terjadi 20 hari bursa sesudahnya.

KENAPA SEBARAN, BUKAN RAMALAN
=============================
riset_pola_naik/analog.py menguji persis ini dengan protokol penuh (pustaka
emiten A 2013-2019, uji emiten B 2020-2026):
  - ARAH rata-rata tetangga TIDAK memprediksi apa pun di luar sampel
    (IC +0,017, t 1,1; ~0 setelah dikurangi momentum/puncak/volatilitas).
  - LEBAR sebaran hasilnya iya: IC besar gerak +0,275 (t 23), dan peluang
    menyentuh +/-10% dalam 60 hari IC +0,267 (t 21,8).
  - Asimetri "naik 10% dulu" minus "turun 10% dulu" ada tapi kecil (IC
    +0,030, t 2,6) dan hilang setelah dikurangi momentum/puncak/volatilitas
    (sisa +0,010, t 0,7) -- sudah tercakup Skor Kecondongan.
Jadi kartu ini menampilkan RENTANG hasil tetangga dan peluang kena +/-10%,
nilai tengahnya ditandai "arah tidak terbukti", dan asimetrinya ditandai
"sudah tercakup skor". Gunanya mengukur seberapa jauh harga biasanya
bergerak dari chart seperti ini -- bukan menebak naik atau turun.

PUSTAKA
=======
Emiten layak (saringan riset_pola_naik/uji.muat), satu jendela tiap 5 bar
per emiten, hasil 20 hari sudah diketahui. Vektornya r30 = log close 30 hari
relatif close hari itu: besar gerak ikut terbawa, bukan cuma bentuk -- r30
yang punya IC besar gerak tertinggi di pengujian. Disimpan di
chart_mirip_cache.pkl bersama lintasan 30 hari sebelum + 20 hari sesudah
tiap jendela (untuk gambar contoh).

Pustaka cuma bergantung pada pickle harga Yahoo di research_cache, yang
jarang berubah. bangun() membandingkan jejak pickle itu dengan yang tercatat
di cache; kalau sama, cache cuma disentuh (mtime = terakhir DIPERIKSA) supaya
pemeriksa kesehatan tidak menandainya basi, tanpa menghitung ulang ~30 detik.

KUERI
=====
30 close terakhir emiten dari berkas Summary-nya -- harga yang sama dengan
halaman lain di app. Summary sendiri harganya dari Yahoo, jadi skalanya
setara dengan pustaka; yang dibandingkan bentuk relatif, bukan level harga.
"""
try:
    from .runtime_paths import runtime_file as _runtime_file, market_file as _market_file, WEBSITE_DIR as _WEBSITE_DIR, PROJECT_DIR as _PROJECT_DIR, RUNTIME_DIR as _RUNTIME_DIR
except ImportError:
    from website.runtime_paths import runtime_file as _runtime_file, market_file as _market_file, WEBSITE_DIR as _WEBSITE_DIR, PROJECT_DIR as _PROJECT_DIR, RUNTIME_DIR as _RUNTIME_DIR
import logging
import os
import pickle
import time

import numpy as np

logger = logging.getLogger(__name__)

HERE = os.path.dirname(__file__)
CACHE_FILE = str(_runtime_file('', 'chart_mirip_cache.pkl'))
W = 30            # jendela yang dicocokkan
MAJU = 20         # hari sesudah yang digambar & diukur
LANGKAH = 5
K = 100
N_CONTOH = 5

_MEMO = {'mtime': None, 'isi': None}


def _jejak_sumber():
    from .riset_pola_naik.panel import RESEARCH_CACHE
    import glob
    kandidat = glob.glob(os.path.join(RESEARCH_CACHE, 'harga_*.pkl'))
    if not kandidat:
        return None
    path = max(kandidat, key=os.path.getsize)
    return os.path.basename(path), round(os.path.getmtime(path))


def bangun(force=False):
    """Bangun pustaka dari cache Yahoo riset. Mengembalikan ringkasan."""
    jejak = _jejak_sumber()
    if jejak is None:
        return {'available': False, 'message': 'Tidak ada harga_*.pkl di research_cache.'}
    if not force and os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, 'rb') as fh:
                lama = pickle.load(fh)
            if tuple(lama.get('sumber') or ()) == tuple(jejak):
                os.utime(CACHE_FILE, None)      # diperiksa: masih cocok dengan sumbernya
                return {'available': True, 'n': int(lama['n']), 'dibangun': lama['dibangun'], 'ulang': False}
        except Exception:
            logger.exception('Cache Chart Termirip tidak terbaca, dibangun ulang')

    from numpy.lib.stride_tricks import sliding_window_view as swv
    from .riset_pola_naik import panel as PN
    from .riset_pola_naik import uji as U
    t0 = time.time()
    p = U.muat()
    p = p.sort_values(['ticker', 'date']).reset_index(drop=True)
    s = p[p['elig'] & (p['hist'] % LANGKAH == 0) & p['fwd20'].notna()].reset_index(drop=True)
    _path, data = PN.sumber_harga()

    X = np.full((len(s), W), np.nan, dtype='float32')
    jalur = np.full((len(s), W + MAJU), np.nan, dtype='float32')
    hist = s['hist'].to_numpy().astype(int)
    for t, idx in s.groupby('ticker', sort=False).indices.items():
        df = data.get(t)
        if df is None:
            continue
        df = df[['Close']].copy()
        df = df[df['Close'] > 0].sort_index()
        df = df[~df.index.duplicated(keep='last')]
        lc = np.log(df['Close'].to_numpy(float))
        h = hist[idx]
        ok = h + MAJU < len(lc)
        idx, h = idx[ok], h[ok]
        w = swv(lc, W + MAJU)[h - W + 1]           # t-29 .. t+20
        rel = w - w[:, W - 1:W]                   # relatif close hari t
        X[idx] = rel[:, :W]
        jalur[idx] = rel
    ok = np.isfinite(X).all(1) & np.isfinite(jalur).all(1)
    s = s[ok].reset_index(drop=True)
    X, jalur = X[ok], jalur[ok]

    lr20 = np.log1p(s['fwd20'].to_numpy(float))
    exc20 = lr20 - s['b_lr20'].to_numpy(float)
    fp60 = s['fp60'].to_numpy(float)
    isi = {
        'sumber': jejak,
        'dibangun': time.strftime('%Y-%m-%d %H:%M'),
        'n': int(len(s)),
        'n_emiten': int(s['ticker'].nunique()),
        'rentang': (str(s['date'].min().date()), str(s['date'].max().date())),
        'X': X, 'jalur': jalur.astype('float16'),
        'ticker': s['ticker'].to_numpy(), 'tanggal': s['date'].dt.strftime('%Y-%m-%d').to_numpy(),
        'lr20': lr20.astype('float32'), 'exc20': exc20.astype('float32'), 'fp60': fp60.astype('float32'),
        'populasi': _ringkas(lr20, exc20, fp60),
    }
    with open(CACHE_FILE, 'wb') as fh:
        pickle.dump(isi, fh, protocol=pickle.HIGHEST_PROTOCOL)
    _MEMO.update(mtime=None, isi=None)
    return {'available': True, 'n': isi['n'], 'dibangun': isi['dibangun'], 'ulang': True,
            'detik': round(time.time() - t0, 1)}


def _ringkas(lr, exc, fp):
    q = np.percentile(lr, [10, 25, 50, 75, 90])
    ok = np.isfinite(fp)
    return {
        'p10': float((np.exp(q[0]) - 1) * 100), 'p25': float((np.exp(q[1]) - 1) * 100),
        'p50': float((np.exp(q[2]) - 1) * 100), 'p75': float((np.exp(q[3]) - 1) * 100),
        'p90': float((np.exp(q[4]) - 1) * 100),
        'naik': float((lr > 0).mean() * 100),
        'naik10_dulu': float((fp[ok] == 1).mean() * 100) if ok.any() else None,
        'turun10_dulu': float((fp[ok] == -1).mean() * 100) if ok.any() else None,
        'vs_pasar': float((np.exp(np.nanmean(exc)) - 1) * 100),
    }


def _pustaka():
    try:
        m = os.path.getmtime(CACHE_FILE)
    except OSError:
        return None
    if _MEMO['isi'] is None or _MEMO['mtime'] != m:
        with open(CACHE_FILE, 'rb') as fh:
            _MEMO.update(isi=pickle.load(fh), mtime=m)
    return _MEMO['isi']


def _kueri(ticker):
    """(tanggal, r30, harga terakhir, alasan di luar semesta) dari Summary.

    Pustaka cuma berisi emiten LAYAK (harga >= Rp100, median nilai 20 hari
    >= Rp1 M). Emiten di luar itu tetap dicarikan tetangga, tapi diberi
    tanda: saham gocap atau yang jarang ditransaksikan punya harga yang
    "nyangkut" di satu fraksi, dan tetangganya ikut jadi jendela datar --
    rentangnya terlihat sempit padahal itu artefak fraksi harga."""
    from .tembus_basis import SUMMARY_DIR, _baca_summary
    df = _baca_summary(os.path.join(SUMMARY_DIR, '%s_Summary.csv' % ticker))
    if df is None or len(df) < W:
        return None
    c = df['Close'].astype(float).iloc[-W:]
    lc = np.log(c.to_numpy())
    alasan = []
    if float(c.iloc[-1]) < 100:
        alasan.append('harga di bawah Rp100')
    nilai = (df['Close'].astype(float) * df['Volume'].astype(float)).iloc[-20:].median()
    if not np.isfinite(nilai) or nilai < 1e9:
        alasan.append('median nilai transaksi 20 hari di bawah Rp1 M')
    return c.index[-1].strftime('%Y-%m-%d'), (lc - lc[-1]).astype('float32'), float(c.iloc[-1]), alasan


def cari(ticker):
    ticker = (ticker or '').strip().upper()
    pus = _pustaka()
    if pus is None:
        return {'available': False, 'message': 'Pustaka chart belum dibangun (tugas kesehatan chart_mirip).'}
    q = _kueri(ticker)
    if q is None:
        return {'available': False, 'message': 'Riwayat harga %s kurang dari %d hari bursa.' % (ticker, W)}
    tanggal, vek, harga, di_luar = q
    d = ((pus['X'] - vek) ** 2).sum(1)
    idx = np.argpartition(d, K)[:K]
    idx = idx[np.argsort(d[idx])]

    lr, exc, fp = pus['lr20'][idx].astype(float), pus['exc20'][idx].astype(float), pus['fp60'][idx].astype(float)
    tetangga = _ringkas(lr, exc, fp)
    pop = pus['populasi']
    lebar = (tetangga['p90'] - tetangga['p10']) / max(pop['p90'] - pop['p10'], 1e-9)

    # Contoh yang digambar: yang paling mirip, tapi tidak dari emiten yang
    # sama berdekatan waktu -- jendela tiap 5 bar dari satu kejadian yang
    # sama akan memenuhi kelima contoh kalau tidak disaring.
    contoh, dipakai = [], []
    for i in idx:
        t, tg = pus['ticker'][i], pus['tanggal'][i]
        if any(t == t2 and abs((np.datetime64(tg) - np.datetime64(tg2)).astype(int)) < 90 for t2, tg2 in dipakai):
            continue
        dipakai.append((t, tg))
        contoh.append({'stock': str(t), 'tanggal': str(tg),
                       'hasil20': round(float((np.exp(pus['lr20'][i]) - 1) * 100), 1),
                       'jalur': [round(float(v), 4) for v in pus['jalur'][i]]})
        if len(contoh) >= N_CONTOH:
            break

    try:
        from .kecondongan import untuk as skor_untuk
        skor = skor_untuk(ticker)
    except Exception:
        skor = None
    return {
        'available': True, 'ticker': ticker, 'tanggal': tanggal, 'harga': harga,
        'kueri': [round(float(v), 4) for v in vek],
        'k': K, 'tetangga': tetangga, 'populasi': pop, 'lebar_rasio': round(float(lebar), 2),
        'contoh': contoh, 'skor': skor, 'di_luar_semesta': di_luar,
        'pustaka': {'n': pus['n'], 'n_emiten': pus['n_emiten'], 'rentang': list(pus['rentang']),
                    'dibangun': pus['dibangun']},
        'uji': {'ic_arah': 0.017, 't_arah': 1.1, 'ic_gerak': 0.275, 't_gerak': 23.0,
                'ic_kena': 0.267, 't_kena': 21.8, 'ic_asim': 0.030, 't_asim': 2.6, 'ic_asim_sisa': 0.010},
    }


if __name__ == '__main__':
    import sys
    print(bangun(force='--paksa' in sys.argv))
    for t in [a for a in sys.argv[1:] if not a.startswith('--')]:
        h = cari(t)
        if not h.get('available'):
            print(t, h.get('message'))
            continue
        tt = h['tetangga']
        print('%s %s: 10-90%% %+.1f..%+.1f (populasi %+.1f..%+.1f, rasio %.2f) naik %.0f%% | contoh: %s'
              % (t, h['tanggal'], tt['p10'], tt['p90'], h['populasi']['p10'], h['populasi']['p90'],
                 h['lebar_rasio'], tt['naik'], ', '.join('%s %s %+.0f%%' % (c['stock'], c['tanggal'], c['hasil20'])
                                                       for c in h['contoh'])))
