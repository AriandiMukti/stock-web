"""
Panel fitur per emiten-hari dari cache harga Yahoo.

Semua kolom fitur hanya memakai data sampai dan termasuk hari t. Hasil ke
depan memakai masuk di CLOSE hari t+1: sinyal baru diketahui setelah t
tutup, dan Open Yahoo untuk BEI tidak bisa dipakai (sama dengan close
kemarin di ~40% baris).

Tanggal tanpa data se-pasar (hari libur yang tetap ditulis Yahoo, hari
datanya bolong) dibuang dulu di semua emiten -- lihat tanpa_libur().
"""
try:
    from ..runtime_paths import runtime_file as _runtime_file, market_file as _market_file, WEBSITE_DIR as _WEBSITE_DIR, PROJECT_DIR as _PROJECT_DIR, RUNTIME_DIR as _RUNTIME_DIR
except ImportError:
    from website.runtime_paths import runtime_file as _runtime_file, market_file as _market_file, WEBSITE_DIR as _WEBSITE_DIR, PROJECT_DIR as _PROJECT_DIR, RUNTIME_DIR as _RUNTIME_DIR
import glob
import os
import pickle
import time

import numpy as np
import pandas as pd
from numpy.lib.stride_tricks import sliding_window_view as swv

RESEARCH_CACHE = str(_runtime_file('', 'research_cache'))

LONCAT = 0.45    # |gerak 1 hari| di atas ini mustahil dengan batas harga BEI -> data rusak / aksi korporasi
FP_BAR = 0.10    # batas lintasan pertama (+/-10%)
FP_WIN = 60
LIBUR_V0 = 0.6   # volume 0 di >= 60% emiten pada satu tanggal = tanggal tanpa data se-pasar


def sumber_harga():
    """
    (path, dict) pickle harga Yahoo dengan baris TERBANYAK di research_cache.

    Baris, bukan jumlah emiten: ada dua pickle berisi 888 emiten, satu mulai
    2012 dan satu mulai 2017. Memilih menurut jumlah emiten membuat urutan
    glob yang menentukan -- dan yang 2017 membuat sel pencarian 2013-2019
    kehilangan hampir semua datanya tanpa ada yang error.
    """
    terbaik, kunci_terbaik, path_terbaik = None, (0, 0), None
    for path in glob.glob(str(_runtime_file('research_cache', 'harga_*.pkl'))):
        with open(path, 'rb') as fh:
            data = pickle.load(fh)
        if not isinstance(data, dict):
            continue
        kunci = (sum(len(v) for v in data.values()), len(data))
        if kunci > kunci_terbaik:
            terbaik, kunci_terbaik, path_terbaik = data, kunci, path
    if terbaik is None:
        raise FileNotFoundError('Tidak ada harga_*.pkl di %s -- jalankan riset RL Trading '
                                '(universe penuh) sekali untuk mengunduhnya.' % RESEARCH_CACHE)
    return path_terbaik, terbaik


def hari_libur(data):
    """
    Tanggal yang bervolume 0 di hampir semua emiten: hari libur bursa yang
    tetap ditulis Yahoo sebagai baris (sebagian besar 2017-2019: Lebaran,
    Natal-Tahun Baru, pilkada; OHLC = close kemarin) dan hari data Yahoo
    bolong (Mar-Apr 2016, 16-27 Apr 2018, ...). Pickle 18 Okt 2026: 75
    tanggal, 2011-2019.

    Ambang LIBUR_V0: di tanggal biasa porsi volume 0 paling tinggi 51%
    (2010-09-15, hari pertama sesudah Lebaran 2010), di tanggal-tanggal ini
    paling rendah 75% -- ambang mana pun di antaranya memberi daftar yang sama.
    """
    v0 = []
    for df in data.values():
        d = df[df['Close'] > 0]
        d = d[~d.index.duplicated(keep='last')]
        v0.append(d['Volume'].fillna(0) == 0)
    porsi = pd.concat(v0).groupby(level=0).mean()
    return porsi.index[porsi >= LIBUR_V0]


def tanpa_libur(data):
    """
    (data, libur): baris di tanggal hari_libur() dibuang, di SEMUA emiten.

    Dibiarkan, baris itu terhitung hari bursa tanpa transaksi: traded30 < 0,9
    di semua emiten sekitar Lebaran/Natal, sampai 91 hari setahun (2017-2019)
    tanpa satu pun emiten layak, dan pembanding beli-semua kehilangan return
    hari-hari itu. Mengeluarkannya dari traded30 saja tidak cukup: volume 0
    yang sama menekan rata-rata volume 20 hari, sehingga "volume > 2x" 33-47%
    lebih sering dalam 20 hari bursa sesudah libur. Dibuang juga di emiten
    yang masih bertransaksi pada hari bolong, supaya tanggalnya hilang dari
    kalender -- bukan tersisa segelintir emiten yang tak satu pun layak.
    """
    libur = hari_libur(data)
    return {t: df[~df.index.isin(libur)] for t, df in data.items()}, libur


def sumber_ihsg():
    """Seri IHSG terpanjang di research_cache (ihsg_<mulai>_<akhir>.pkl)."""
    kandidat = sorted(glob.glob(str(_runtime_file('research_cache', 'ihsg_*.pkl'))))
    if not kandidat:
        return None
    with open(kandidat[0], 'rb') as fh:     # nama diurut -> tanggal mulai paling awal dulu
        s = pickle.load(fh)
    return s[~s.index.duplicated()]


def rmax(s, w): return s.rolling(w, min_periods=w).max()
def rmin(s, w): return s.rolling(w, min_periods=w).min()
def rmean(s, w): return s.rolling(w, min_periods=w).mean()


def fitur(t, df):
    df = df[['Open', 'High', 'Low', 'Close', 'Volume']].copy()
    df = df[df['Close'] > 0].sort_index()
    df = df[~df.index.duplicated(keep='last')]
    n = len(df)
    if n < 300:
        return None
    C, H, L, V = df['Close'], df['High'], df['Low'], df['Volume'].fillna(0)
    H = np.maximum(H, C); L = np.minimum(L, C)
    out = pd.DataFrame(index=df.index)
    out['ticker'] = t
    out['close'] = C
    value = C * V
    traded = (V > 0).astype(float)
    ret1 = C.pct_change()
    bad = (ret1.abs() > LONCAT).astype(float)
    out['hist'] = np.arange(n)
    out['traded30'] = rmean(traded, 30)
    out['medval20'] = value.rolling(20, min_periods=20).median()
    out['bad_back60'] = bad.rolling(60, min_periods=1).max()

    # --- ketenangan / rentang ---
    for w in (20, 30, 60):
        out['range%d' % w] = (rmax(H, w) - rmin(L, w)) / C
    out['ccrange30'] = (rmax(C, 30) - rmin(C, 30)) / C
    ph30, pl30 = rmax(H, 30).shift(1), rmin(L, 30).shift(1)
    out['prevrange30'] = (ph30 - pl30) / C.shift(1)
    out['brk30'] = (C > ph30).astype(float)
    ph60 = rmax(H, 60).shift(1)
    out['brk60'] = (C > ph60).astype(float)
    out['pos30'] = (C - rmin(L, 30)) / (rmax(H, 30) - rmin(L, 30)).replace(0, np.nan)

    lr = np.log(C).diff()
    out['vol20'] = lr.rolling(20, min_periods=20).std()
    out['vol120'] = lr.rolling(120, min_periods=120).std()
    out['volratio'] = out['vol20'] / out['vol120']
    out['vol20pct'] = out['vol20'].rolling(250, min_periods=250).rank(pct=True)
    tr = pd.concat([H - L, (H - C.shift(1)).abs(), (L - C.shift(1)).abs()], axis=1).max(axis=1)
    out['atr10'] = rmean(tr, 10) / C
    out['atr60'] = rmean(tr, 60) / C
    out['atrratio'] = out['atr10'] / out['atr60']

    # --- tren / posisi ---
    for k in (5, 20, 60, 120, 250):
        out['ret%d' % k] = C / C.shift(k) - 1
    out['into_base'] = C.shift(30) / C.shift(90) - 1        # gerak MASUK ke basis 30 hari terakhir
    out['dd60'] = C / rmax(C, 60) - 1
    out['dd250'] = C / rmax(C, 250) - 1
    out['up_low20'] = C / rmin(C, 20) - 1
    out['hi250'] = (C >= rmax(C, 250).shift(1)).astype(float)
    for m in (20, 50, 200):
        out['ma%d' % m] = C / rmean(C, m) - 1

    # --- volume ---
    vprev20 = rmean(V, 20).shift(1)
    out['vspike'] = V / vprev20.replace(0, np.nan)
    out['vdry'] = rmean(V, 10) / rmean(V, 60).replace(0, np.nan)

    # --- RSI14 (Wilder) ---
    up = lr.clip(lower=0); dn = (-lr).clip(lower=0)
    au = up.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    ad = dn.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    out['rsi14'] = 100 - 100 / (1 + au / ad.replace(0, np.nan))
    out['day_pos'] = (C - L) / (H - L).replace(0, np.nan)

    # --- hasil ke depan: masuk = close t+1 ---
    c = C.to_numpy(float)
    badc = np.concatenate([[0], np.cumsum(bad.to_numpy())])     # badc[i] = jumlah loncatan di baris < i
    entry = np.full(n, np.nan); entry[:-1] = c[1:]
    idx = np.arange(n)
    for h in (20, 60):
        f = np.full(n, np.nan)
        j = idx + 1 + h
        ok = j < n
        f[ok] = c[j[ok]] / entry[ok] - 1
        # jendela ke depan yang memuat loncatan dibuang
        nb = np.full(n, 1.0)
        nb[ok] = badc[j[ok] + 1] - badc[idx[ok] + 1]
        f[nb > 0] = np.nan
        out['fwd%d' % h] = f
    # lintasan pertama pada close, +/-10% dari harga masuk, dalam 60 bar sesudah masuk
    fp = np.full(n, np.nan); mfe20 = np.full(n, np.nan)
    if n > FP_WIN + 2:
        win = swv(c[2:], FP_WIN)                  # win[i] = c[i+2 : i+2+FP_WIN]
        m = len(win)
        rel = win / entry[:m, None]
        upi = np.where((rel >= 1 + FP_BAR).any(1), (rel >= 1 + FP_BAR).argmax(1), 10 ** 6)
        dni = np.where((rel <= 1 - FP_BAR).any(1), (rel <= 1 - FP_BAR).argmax(1), 10 ** 6)
        fp[:m] = np.where(upi < dni, 1.0, np.where(dni < upi, -1.0, 0.0))
        mfe20[:m] = rel[:, :20].max(1) - 1
        nb = badc[np.minimum(np.arange(m) + 2 + FP_WIN, n)] - badc[np.arange(m) + 1]
        fp[:m][nb > 0] = np.nan
        mfe20[:m][nb > 0] = np.nan
    out['fp60'] = fp
    out['mfe20'] = mfe20
    return out


def bangun(verbose=True):
    """Panel lengkap (DataFrame), dibangun di memori. ~20 detik untuk 888 emiten."""
    t0 = time.time()
    path, data = sumber_harga()
    data, libur = tanpa_libur(data)
    if verbose:
        print('harga: %s (%d emiten), %d tanggal libur/bolong dibuang'
              % (os.path.basename(path), len(data), len(libur)), flush=True)
    parts = [f for f in (fitur(t, df) for t, df in data.items()) if f is not None]
    p = pd.concat(parts)
    p.index.name = 'date'
    p = p.reset_index()
    ih = sumber_ihsg()
    if ih is not None:
        reg = (ih / ih.rolling(200, min_periods=200).mean() - 1).rename('ihsg_ma200')
        ihret20 = (ih / ih.shift(20) - 1).rename('ihsg_ret20')
        p = p.merge(pd.concat([reg, ihret20], axis=1), left_on='date', right_index=True, how='left')
    else:
        p['ihsg_ma200'] = np.nan
        p['ihsg_ret20'] = np.nan
    fcols = [c for c in p.columns if c not in ('ticker', 'date')]
    p[fcols] = p[fcols].astype('float32')
    p['ticker'] = p['ticker'].astype(str)
    if verbose:
        print('panel: %d baris, %d kolom, %.0f detik' % (len(p), len(p.columns), time.time() - t0), flush=True)
    return p
