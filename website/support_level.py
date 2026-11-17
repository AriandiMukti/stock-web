"""
Penentu support/resistance untuk chart saham (15 Okt 2026).

Menggantikan utilities.compute_levels() HANYA di chart (/stock-chart-data).
compute_levels() sengaja dibiarkan untuk rapat_agen.py (jurnal maju sejak
9 Okt 2026 memakai rumus itu) dan compute_stock_targets() -- mengganti
rumusnya di sana akan diam-diam mengubah aturan yang sedang dinilai maju.

Riset & bukti: riset_pola_naik/support_maksimal.py.

HARGA MENTAH
Berkas Summary punya dua jenis harga. Baris awal (Januari s.d. Maret-Juni
2026, tergantung emiten) adalah isian Yahoo yang SUDAH DISETEL DIVIDEN --
4-11% di bawah harga yang benar-benar diperdagangkan saat itu (TLKM 8%,
BMRI 9-11%, maks 24%); sesudahnya harga mentah dari data broker. 349 dari
881 berkas begitu. Level yang lahir dari baris isian itu ikut melenceng
sebesar dividennya, dan lilinnya tidak cocok dengan harga di aplikasi
broker. koreksi_mentah() mengembalikannya ke harga mentah.
"""
try:
    from .runtime_paths import runtime_file as _runtime_file, market_file as _market_file, WEBSITE_DIR as _WEBSITE_DIR, PROJECT_DIR as _PROJECT_DIR, RUNTIME_DIR as _RUNTIME_DIR
except ImportError:
    from website.runtime_paths import runtime_file as _runtime_file, market_file as _market_file, WEBSITE_DIR as _WEBSITE_DIR, PROJECT_DIR as _PROJECT_DIR, RUNTIME_DIR as _RUNTIME_DIR
import logging
import os
import pickle
import threading

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

HERE = os.path.dirname(os.path.abspath(__file__))
MENTAH_FILE = str(_runtime_file('', 'research_cache', 'harga_mentah_close.pkl'))

_mentah = None
_mentah_kunci = threading.Lock()


def _tick(p):
    """Fraksi harga BEI (aturan yang berlaku 2026)."""
    return np.select([p < 200, p < 500, p < 2000, p < 5000], [1, 2, 5, 10], 25)


def _snap(x):
    t = _tick(x)
    return np.round(x / t) * t


def _pecahan(x):
    return np.abs(x - np.round(x)) > 1e-6


def _harga_mentah():
    """Close mentah (belum disetel dividen, sudah disetel split) per emiten,
    dari research_cache (sumber_baru.py mentah). {} kalau tidak ada."""
    global _mentah
    if _mentah is None:
        with _mentah_kunci:
            if _mentah is None:
                try:
                    with open(MENTAH_FILE, 'rb') as fh:
                        _mentah = pickle.load(fh)
                except Exception:
                    logger.warning('harga_mentah_close.pkl tidak terbaca -- koreksi pakai Avg Price')
                    _mentah = {}
    return _mentah


def koreksi_mentah(df, stock):
    """
    Baris isian Yahoo yang disetel dividen -> harga mentah.

    df: Summary, terurut tanggal, kolom Date (datetime) / Open / High / Low /
    Close / Volume / Avg Price. Mengembalikan (df baru, keterangan).

    Bloknya = semua baris sampai baris TERAKHIR yang punya harga pecahan
    (harga BEI selalu bulat; hasil penyetelan hampir tak pernah). Seluruh
    blok dikalikan faktornya, bukan cuma sel yang pecahan: nilai setel bisa
    kebetulan bulat (BBCA 27 Mar 2026: Low = Close = 6419,000 padahal
    mentahnya 6700).

    Faktor per baris = close mentah / close Summary, dari research_cache --
    tepat sampai fraksi harga, dan menangkap dua dividen dalam satu blok
    (BMRI). Kalau emitennya tidak ada di sana (emiten baru), satu faktor
    dari median Avg Price / harga tipikal di blok itu: Avg Price di Summary
    selalu mentah (data broker). Dicek pada 881 berkas (15 Okt 2026): close
    terkoreksi selisih < 0,5% dari close mentah di 332 dari 338 emiten (median
    0,00%); terbesar KINO 4% di satu baris. Baris High/Low terbalik: 0.
    """
    O, H, L, C = (df[c].to_numpy(float) for c in ('Open', 'High', 'Low', 'Close'))
    ada = _pecahan(O) | _pecahan(H) | _pecahan(L) | _pecahan(C)
    if not ada.any():
        return df, None
    akhir = int(np.flatnonzero(ada)[-1]) + 1
    f = np.full(akhir, np.nan)
    asal = 'mentah'
    raw = _harga_mentah().get(stock)
    if raw is not None and len(raw):
        r = raw[~raw.index.duplicated(keep='last')].reindex(df['Date'].iloc[:akhir]).to_numpy(float)
        ok = np.isfinite(r) & (r > 0) & (C[:akhir] > 0)
        f[ok] = r[ok] / C[:akhir][ok]
    if not np.isfinite(f).any():
        ap = pd.to_numeric(df['Avg Price'], errors='coerce').to_numpy(float)[:akhir]
        tipikal = (H[:akhir] + L[:akhir] + C[:akhir]) / 3
        ok = (ap > 0) & (df['Volume'].to_numpy(float)[:akhir] > 0) & (tipikal > 0)
        est = float(np.nanmedian(ap[ok] / tipikal[ok])) if ok.any() else np.nan
        if not (np.isfinite(est) and 1.0 <= est <= 1.35):
            return df, None
        f[:] = est
        asal = 'avg price'
    f = pd.Series(f).ffill().bfill().to_numpy()
    out = df.copy()
    for c in ('Open', 'High', 'Low', 'Close'):
        v = out[c].to_numpy(float).copy()
        v[:akhir] = _snap(v[:akhir] * f)
        out[c] = v
    return out, {'baris': akhir, 'asal': asal,
                 'faktor': round(float(np.median(f)), 4)}


# ---------------------------------------------------------------------------
# PENENTU LEVEL -- satu hari (bar terakhir df). Rumusnya HARUS sama dengan
# versi per-hari di riset_pola_naik/support_maksimal.py; dicek oleh
# `python -m website.riset_pola_naik.support_maksimal cek-setara`.
# ---------------------------------------------------------------------------
def pivot(arr, k, low=True):
    """Indeks titik balik orde k: ekstrem di [i-k, i+k] dan lebih ekstrem
    (tegas) dari k bar sebelumnya. Baru diketahui di bar i+k."""
    s = pd.Series(arr)
    if low:
        m = s.rolling(2 * k + 1, center=True).min().to_numpy()
        prev = s.shift(1).rolling(k).min().to_numpy()
        ok = (arr == m) & (arr < prev)
    else:
        m = s.rolling(2 * k + 1, center=True).max().to_numpy()
        prev = s.shift(1).rolling(k).max().to_numpy()
        ok = (arr == m) & (arr > prev)
    return np.flatnonzero(ok)


def klaster(lp, g):
    """lp: log harga terurut. Rantai tunggal bercelah g, lebar maks 2g.
    -> (log level = rata-rata anggota, jumlah anggota, indeks awal, indeks akhir)."""
    if len(lp) == 0:
        return np.empty(0), np.empty(0, int), [], []
    pecah = np.flatnonzero(np.diff(lp) > g) + 1
    lv, cnt, awal, akhir = [], [], [], []
    mulai = 0
    for seg in np.split(lp, pecah):
        a = 0
        while a < len(seg):
            b = a + int(np.searchsorted(seg[a:], seg[a] + 2 * g, side='right'))
            lv.append(seg[a:b].mean()); cnt.append(b - a)
            awal.append(mulai + a); akhir.append(mulai + b - 1)
            a = b
        mulai += len(seg)
    return np.array(lv), np.array(cnt), awal, akhir


def level_pivot(H, L, k, W, sumber, tau, m):
    """
    Level dari klaster titik balik pada bar terakhir.
    -> (levels_support, levels_resistance, detail) ; level terurut naik.
    sumber 'L': support dari pivot low, resistance dari pivot high;
           'LH': keduanya untuk dua sisi (polaritas).
    """
    n = len(H)
    t = n - 1
    g = np.log1p(tau)
    pl = pivot(L, k, True); ph = pivot(H, k, False)
    pl = pl[(pl + k <= t) & (pl >= t - W + 1)]
    ph = ph[(ph + k <= t) & (ph >= t - W + 1)]
    lo = np.log(L[pl]); hi = np.log(H[ph])

    def susun(lp, idx):
        urut = np.argsort(lp, kind='stable')
        lp, idx = lp[urut], idx[urut]
        lv, cnt, aw, ak = klaster(lp, g)
        det = []
        for j in range(len(lv)):
            anggota = idx[aw[j]:ak[j] + 1]
            det.append({'harga': float(np.exp(lv[j])), 'sentuh': int(cnt[j]),
                        'bawah': float(np.exp(lp[aw[j]])), 'atas': float(np.exp(lp[ak[j]])),
                        'terakhir': int(anggota.max())})
        return [d for d in det if d['sentuh'] >= m]

    if sumber == 'LH':
        both = susun(np.concatenate([lo, hi]), np.concatenate([pl, ph]))
        return both, both
    return susun(lo, pl), susun(hi, ph)


def level_swing(H, L, C, k, Wmax=250):
    """Pivot low terakhir yang masih di bawah close (dan cerminnya)."""
    n = len(C)
    t = n - 1
    out = []
    for arr, low in ((L, True), (H, False)):
        piv = pivot(arr, k, low)
        piv = piv[(piv + k <= t) & (piv >= t - Wmax)]
        x = None
        for j in piv[::-1]:
            if (arr[j] <= C[t]) if low else (arr[j] >= C[t]):
                x = {'harga': float(arr[j]), 'sentuh': 1, 'bawah': float(arr[j]),
                     'atas': float(arr[j]), 'terakhir': int(j)}
                break
        out.append([x] if x else [])
    return out[0], out[1]


def hitung_level(H, L, C, V, jenis, p):
    """(daftar support, daftar resistance) pada bar terakhir untuk penentu
    `jenis` berparameter `p` (nama & parameter = support_maksimal.ALGO)."""
    H = np.asarray(H, float); L = np.asarray(L, float); C = np.asarray(C, float)
    n = len(C)
    if jenis == 'pivot':
        return level_pivot(H, L, p['k'], p['W'], p['sumber'], p['tau'], p['m'])
    if jenis == 'swing':
        return level_swing(H, L, C, p['k'])
    if jenis == 'donchian':
        if n < p['N']:
            return [], []
        s, r = float(L[-p['N']:].min()), float(H[-p['N']:].max())
        return ([{'harga': s, 'sentuh': 1, 'bawah': s, 'atas': s, 'terakhir': n - 1}],
                [{'harga': r, 'sentuh': 1, 'bawah': r, 'atas': r, 'terakhir': n - 1}])
    if jenis == 'ma':
        if n < p['N']:
            return [], []
        m = float(C[-p['N']:].mean())
        d = [{'harga': m, 'sentuh': 0, 'bawah': m, 'atas': m, 'terakhir': n - 1}]
        return d, d
    raise ValueError(jenis)


def terdekat(det, c):
    """(support, resistance): level tertinggi <= c dan terendah >= c."""
    bawah = [d for d in det[0] if d['harga'] <= c]
    atas = [d for d in det[1] if d['harga'] >= c]
    return (max(bawah, key=lambda d: d['harga']) if bawah else None,
            min(atas, key=lambda d: d['harga']) if atas else None)
