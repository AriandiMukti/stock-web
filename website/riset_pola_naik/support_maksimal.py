"""
Penentu support "maksimal" (15 Okt 2026).

PERTANYAAN (pengguna): apakah garis support di chart Halaman Saham sudah
berfungsi maksimal? Kalau belum, buat penentu support yang maksimal.

"Berfungsi" di sini diukur, bukan dirasa. Riset lama (chart_support.py)
menguji support sebagai SINYAL BELI -- hasilnya ~netral. Yang belum pernah
diuji adalah fungsi dasarnya: kalau harga turun ke garis itu, apakah ia
memang lebih sering TERTAHAN di sana daripada di harga sembarang? Dan
kalau garisnya jebol, apakah itu memang kabar buruk (bahan cut-loss)?

UKURAN -- didaftar SEBELUM hasil apa pun dilihat
  S_t      support pada close t = level tertinggi <= close t (sama dengan
           cara stock_chart.js memilih "support terdekat").
  SENTUH   hari u: low_u <= S x 1,01 dan close_{u-1} > S x 1,01, dengan
           S = S_{u-1} (garis yang terlihat di chart pagi itu). Satu
           sentuhan per emiten per 10 hari bursa.
  TAHAN    tidak ada close < S x 0,97 di hari u..u+10.      <- UKURAN UTAMA
  PANTUL   close >= S x 1,05 tercapai sebelum close < S x 0,97, dalam 20 hari.
  PLASEBO  garis sembarang: kisi harga tetap berjarak 8%, 4 fase acak per
           emiten, diperiksa dengan aturan sentuh/tahan yang PERSIS sama.
           lift = TAHAN(garis) - TAHAN(plasebo) pada EMITEN yang sama
           (seluruh riwayatnya), jarak kemarin dalam satuan ATR14 (9 ember)
           dan tertil ATR14 emiten itu. Strata awal (jarak % x ATR, global)
           ternyata bias di random walk -- riwayat perbaikannya di catatan
           B_JARAK_ATR; diperbaiki sebelum data asli dibuka.
           Nilai t dikelompokkan per bulan (uji.t_klaster).
  JEBOL    close_t < S_{t-1} x 0,97, hari pertama, satu per emiten per 20
           hari: selisih majemuk 20 hari vs semua emiten layak di hari yang
           sama (masuk close t+1). Dibanding jebol garis plasebo pada strata
           turun-1-hari yang sama.
  CAKUPAN  % hari layak yang punya support 0-15% di bawah close; median jarak.
  Resistance diuji cerminnya: sentuh dari bawah (high >= R x 0,99),
  TOLAK = tidak ada close > R x 1,03 di u..u+10.

  Semesta, sel, dan pembanding sama dengan uji.py: emiten likuid, cari di
  separuh emiten A 2013-2019, validasi separuh B 2020-2026, dua sel silang.

ATURAN PILIH (juga didaftar sebelum hasil dilihat)
  Di sel PENCARIAN saja: lift TAHAN tertinggi, di antara kandidat yang
  cakupannya >= cakupan chart lama - 10 poin dan sentuhannya >= 2 per
  emiten-tahun (garis yang tak pernah didatangi harga tak berguna).
  Syarat tambahan: jebolnya tidak lebih lemah dari chart lama.
  Kalau kandidat teratas cuma unggul < 1 poin lift dari kandidat sekeluarga
  yang jendelanya lebih pendek, pilih yang pendek (Summary cuma ~190 bar;
  jendela 250 butuh riwayat Yahoo disambung).
  Baru sesudah itu sel validasi & silang dibuka.

PEMAKAIAN (dari <project>/)
    python -m website.riset_pola_naik.support_maksimal hitung    # ~ beberapa menit, simpan cache
    python -m website.riset_pola_naik.support_maksimal cari      # sel pencarian saja
    python -m website.riset_pola_naik.support_maksimal validasi  # semua sel, kandidat terpilih
"""
import hashlib
import os
import pickle
import sys
import time
import warnings
from multiprocessing import Pool

import numpy as np
import pandas as pd

from . import panel as PN
from . import uji as U
from . import chart_support as CS

warnings.filterwarnings('ignore', category=RuntimeWarning)

# Level & sentuhan dihitung di harga MENTAH (belum disetel dividen, sudah
# disetel split -- yang dilihat trader di chart). Harga Yahoo yang disetel
# dividen menggeser level lama 2-3% per tahun relatif terhadap harga yang
# dulu benar-benar dilihat orang (BBCA: rasio mentah/setel 1,33 di 2012,
# 1,09 di 2024) -- itu mengaburkan level berumur panjang dan merugikan
# penentu berjendela panjang. Return ke depan tetap dari harga setel
# (dividen bagian dari hasil). SUPPORT_HARGA=adj untuk versi setel.
HARGA = os.environ.get('SUPPORT_HARGA', 'mentah')
CACHE = os.path.join(PN.RESEARCH_CACHE, 'support_maksimal_kejadian_%s.pkl' % HARGA)
MENTAH_FILE = os.path.join(PN.RESEARCH_CACHE, 'harga_mentah_close.pkl')

TOL = 0.01          # zona sentuh: low <= S x 1,01
BATAS = 0.97        # jebol / tidak tahan: close < S x 0,97
H_TAHAN = 10
H_PANTUL = 20
PANTUL = 1.05
JEDA_SENTUH = 10
JEDA_JEBOL = 20
JARAK_MAKS = 0.15
KISI = 0.08
N_FASE = 4
LONCAT = PN.LONCAT

CELL_NAMA = {0: 'PENCARIAN (A, 2013-19)', 1: 'VALIDASI (B, 2020-26)',
             2: 'silang B 2013-19', 3: 'silang A 2020-26'}


# ---------------------------------------------------------------------------
# PENENTU LEVEL -- tiap fungsi mengembalikan (S, R): support & resistance pada
# close t, hanya memakai data sampai t. NaN = tidak ada.
# ---------------------------------------------------------------------------
def _terdekat(levels, c):
    """Level tertinggi <= c dan terendah >= c dari array terurut."""
    if len(levels) == 0:
        return np.nan, np.nan
    j = np.searchsorted(levels, c, side='right')
    s = levels[j - 1] if j > 0 else np.nan
    j2 = np.searchsorted(levels, c, side='left')
    r = levels[j2] if j2 < len(levels) else np.nan
    return s, r


def lv_lama(d, w=100):
    """utilities.compute_levels pada w bar terakhir (replika chart_support.py)."""
    C = d['C']; n = len(C)
    vals = d['fraktal']
    S = np.full(n, np.nan); R = np.full(n, np.nan)
    for k in range(w - 1, n):
        lv = CS.levels_dari(vals[k - (w - 3):k - 1])
        S[k], R[k] = _terdekat(lv, C[k])
    return S, R


def pivot(arr, k, low=True):
    """Indeks titik balik orde k: ekstrem di [i-k, i+k], lebih ekstrem
    (tegas) dari k bar sebelumnya. Baru DIKETAHUI di bar i+k."""
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
    """lp: log harga terurut. Rantai tunggal dengan celah g, lebar maks 2g.
    -> (log level = rata-rata anggota, jumlah anggota)."""
    if len(lp) == 0:
        return np.empty(0), np.empty(0, int)
    pecah = np.flatnonzero(np.diff(lp) > g) + 1
    lv, cnt = [], []
    for seg in np.split(lp, pecah):
        # potong segmen yang terlalu lebar (rantai panjang) per 2g dari awal
        a = 0
        while a < len(seg):
            b = a + int(np.searchsorted(seg[a:], seg[a] + 2 * g, side='right'))
            lv.append(seg[a:b].mean()); cnt.append(b - a)
            a = b
    return np.array(lv), np.array(cnt)


def lv_pivot(d, k, W, sumber, tau, m_list):
    """
    Klaster titik balik. sumber 'L': support dari pivot low, resistance dari
    pivot high. 'LH': keduanya dipakai untuk dua sisi (polaritas: resistance
    yang tembus jadi support). Level = rata-rata (log) anggota klaster;
    syarat >= m anggota. Kembalikan {m: (S, R)}.
    """
    C, H, L = d['C'], d['H'], d['L']; n = len(C)
    g = np.log1p(tau)
    pl = pivot(L, k, True); ph = pivot(H, k, False)
    ev = []   # (hari diketahui, +1/-1, sisi, harga)
    for idx, arr, sisi in ((pl, L, 'l'), (ph, H, 'h')):
        for i in idx:
            ev.append((i + k, 1, sisi, arr[i], i))
            ev.append((i + W, -1, sisi, arr[i], i))
    out = {m: (np.full(n, np.nan), np.full(n, np.nan)) for m in m_list}
    if not ev:
        return out
    ev.sort(key=lambda e: (e[0], e[1]))
    aktif = {'l': {}, 'h': {}}
    hari = sorted(set(e[0] for e in ev if e[0] < n))
    batas = hari + [n]
    p = 0
    for si, t0 in enumerate(hari):
        while p < len(ev) and ev[p][0] <= t0:
            _, tipe, sisi, harga, i = ev[p]
            if tipe == 1:
                aktif[sisi][i] = harga
            else:
                aktif[sisi].pop(i, None)
            p += 1
        t1 = batas[si + 1]
        c = C[t0:t1]
        lo = np.log(np.fromiter(aktif['l'].values(), float)) if aktif['l'] else np.empty(0)
        hi = np.log(np.fromiter(aktif['h'].values(), float)) if aktif['h'] else np.empty(0)
        if sumber == 'LH':
            both = np.sort(np.concatenate([lo, hi]))
            ks, cs = klaster(both, g)
            kr, cr = ks, cs
        else:
            ks, cs = klaster(np.sort(lo), g)
            kr, cr = klaster(np.sort(hi), g)
        for m in m_list:
            S, R = out[m]
            ls = np.exp(ks[cs >= m]); lr = np.exp(kr[cr >= m])
            if len(ls):
                j = np.searchsorted(ls, c, side='right')
                S[t0:t1] = np.where(j > 0, ls[np.maximum(j - 1, 0)], np.nan)
            if len(lr):
                j2 = np.searchsorted(lr, c, side='left')
                R[t0:t1] = np.where(j2 < len(lr), lr[np.minimum(j2, len(lr) - 1)], np.nan)
    return out


def lv_vp(d, W, thetas, bw=0.01):
    """Profil volume (volume per harga) W bar terakhir; level = puncak lokal
    (node volume tinggi) setinggi >= theta x rata-rata profil."""
    C, H, L, V = d['C'], d['H'], d['L'], d['V']; n = len(C)
    lo = np.log(np.nanmin(L)) - bw
    G = int(np.ceil((np.log(np.nanmax(H)) - lo) / bw)) + 2
    gl = np.floor((np.log(L) - lo) / bw).astype(int)
    gh = np.floor((np.log(H) - lo) / bw).astype(int)
    nb = gh - gl + 1
    D = np.zeros((n, G + 1), np.float64)
    r = np.arange(n)
    np.add.at(D, (r, gl), V / nb)
    np.add.at(D, (r, gh + 1), -V / nb)
    prof = np.cumsum(D, axis=1)[:, :G]
    del D
    cum = np.cumsum(prof, axis=0)
    prof = cum.copy()
    prof[W:] -= cum[:-W]
    del cum
    sm = prof.copy()
    sm[:, 1:-1] = (prof[:, :-2] + prof[:, 1:-1] + prof[:, 2:]) / 3
    del prof
    isp = np.zeros_like(sm, bool)
    isp[:, 1:-1] = (sm[:, 1:-1] >= sm[:, :-2]) & (sm[:, 1:-1] > sm[:, 2:]) & (sm[:, 1:-1] > 0)
    nz = (sm > 0).sum(1)
    rata = np.where(nz > 0, sm.sum(1) / np.maximum(nz, 1), np.inf)
    pusat = np.exp(lo + (np.arange(G) + 0.5) * bw)
    gc = np.floor((np.log(C) - lo) / bw).astype(int)
    gc = np.clip(gc, 0, G - 1)
    # bin yang pusatnya > close tidak boleh jadi support
    gs = np.where(pusat[gc] <= C, gc, gc - 1)
    gr = np.where(pusat[gc] >= C, gc, gc + 1)
    out = {}
    idx = np.arange(G)
    for th in thetas:
        ok = isp & (sm >= th * rata[:, None])
        a = np.where(ok, idx[None, :], -1)
        pre = np.maximum.accumulate(a, axis=1)
        b = np.where(ok, idx[None, :], G)
        suf = np.minimum.accumulate(b[:, ::-1], axis=1)[:, ::-1]
        js = pre[r, np.clip(gs, 0, G - 1)]
        js = np.where(gs >= 0, js, -1)
        jr = suf[r, np.clip(gr, 0, G - 1)]
        jr = np.where(gr <= G - 1, jr, G)
        S = np.where(js >= 0, pusat[np.clip(js, 0, G - 1)], np.nan)
        R = np.where(jr < G, pusat[np.clip(jr, 0, G - 1)], np.nan)
        S[:W - 1] = np.nan; R[:W - 1] = np.nan
        out[th] = (S, R)
    return out


def lv_donchian(d, N):
    S = pd.Series(d['L']).rolling(N, min_periods=N).min().to_numpy()
    R = pd.Series(d['H']).rolling(N, min_periods=N).max().to_numpy()
    return S, R


def lv_ma(d, N):
    C = d['C']
    m = pd.Series(C).rolling(N, min_periods=N).mean().to_numpy()
    return np.where(m <= C, m, np.nan), np.where(m >= C, m, np.nan)


def lv_swing(d, k, Wmax=250):
    """Pivot low terakhir yang masih di bawah close (dan cerminnya)."""
    C, H, L = d['C'], d['H'], d['L']; n = len(C)
    out = []
    for arr, low in ((L, True), (H, False)):
        piv = pivot(arr, k, low)
        X = np.full(n, np.nan)
        ptr, akt = 0, []
        for t in range(n):
            while ptr < len(piv) and piv[ptr] + k <= t:
                akt.append(piv[ptr]); ptr += 1
            for j in reversed(akt):
                if j < t - Wmax:
                    break
                if (arr[j] <= C[t]) if low else (arr[j] >= C[t]):
                    X[t] = arr[j]
                    break
        out.append(X)
    return out[0], out[1]


def lv_kisi(d, fase):
    """Plasebo: garis harga tetap berjarak KISI, digeser fase (0..1)."""
    C = d['C']
    g = np.log1p(KISI)
    x = np.log(C) / g - fase
    S = np.exp((np.floor(x) + fase) * g)
    R = np.exp((np.ceil(x) + fase) * g)
    return S, R


# daftar kandidat ------------------------------------------------------------
def daftar_algo():
    A = [('A0 chart lama 100 bar', 'lama', {'w': 100}),
         ('A1 chart lama 200 bar', 'lama', {'w': 200}),
         ('A2 chart lama 250 bar', 'lama', {'w': 250})]
    for k in (3, 5, 10):
        for W in (120, 250):
            for src in ('L', 'LH'):
                for tau in (0.015, 0.03):
                    for m in (1, 2, 3):
                        A.append(('P k%d W%d %s tau%.1f m%d' % (k, W, src, tau * 100, m), 'pivot',
                                  {'k': k, 'W': W, 'sumber': src, 'tau': tau, 'm': m}))
    for W in (60, 120, 250):
        for th in (0.0, 1.0, 1.5):
            A.append(('VP W%d th%.1f' % (W, th), 'vp', {'W': W, 'th': th}))
    for N in (10, 20, 60, 120):
        A.append(('D donchian %d' % N, 'donchian', {'N': N}))
    for N in (20, 50, 100, 200):
        A.append(('MA %d' % N, 'ma', {'N': N}))
    for k in (3, 5, 10):
        A.append(('SW swing terakhir k%d' % k, 'swing', {'k': k}))
    for f in range(N_FASE):
        A.append(('PLASEBO fase %d' % f, 'kisi', {'fase': (f + 0.5) / N_FASE}))
    return A


ALGO = daftar_algo()
ALGO_ID = {a[0]: i for i, a in enumerate(ALGO)}

# UJI SUSULAN -- didaftar SESUDAH sel validasi dibuka (bukti lebih lemah).
# Validasi menunjukkan rumus chart lama justru yang paling konsisten
# menahan harga; kelemahannya praktis: tak ada support sama sekali saat
# harga di bawah semua level 100 hari (26% emiten likuid pada 15 Okt 2026).
# Pertanyaannya: kalau celah itu diisi cara lain yang JUGA konsisten di
# 4 sel (swing low terakhir k3, Donchian 10), apakah fungsinya tetap?
SUSULAN = ['H1 lama, kosong->swing k3', 'H2 lama(<=15%), lain->swing k3',
           'H3 lama, kosong->donchian 10', 'H1b swing k3 HANYA saat lama kosong',
           'H2b swing k3 HANYA saat lama kosong/>15%']


def hitung_susulan_satu(d):
    C = d['C']
    S0, R0 = lv_lama(d, 100)
    Ssw, _ = lv_swing(d, 3)
    Sd, _ = lv_donchian(d, 10)
    kosong = ~np.isfinite(S0)
    jauh = kosong | (C / S0 - 1 > JARAK_MAKS)
    nan = np.full(len(C), np.nan)
    return {SUSULAN[0]: (np.where(kosong, Ssw, S0), R0),
            SUSULAN[1]: (np.where(jauh, Ssw, S0), R0),
            SUSULAN[2]: (np.where(kosong, Sd, S0), R0),
            SUSULAN[3]: (np.where(kosong, Ssw, np.nan), nan),
            SUSULAN[4]: (np.where(jauh, Ssw, np.nan), nan)}


def olah_susulan(args):
    tid, t, df, mentah = args
    d = siapkan(t, df, mentah)
    if d is None:
        return None
    rs, rj = [], []
    cov = np.zeros((len(SUSULAN), 4, 52), np.int64)
    for i, (nama, (S, R)) in enumerate(hitung_susulan_satu(d).items()):
        a, b = kejadian(d, S, R, len(ALGO) + i, tid)
        rs += a; rj += b
        cov[i] = cakupan(d, S)
    return (np.array(rs, dtype=S_DT), np.array(rj, dtype=J_DT), cov)


def hitung_satu(d, nama):
    """(S, R) satu kandidat saja -- untuk cek-setara dan pemeriksaan cepat."""
    _, jenis, p = ALGO[ALGO_ID[nama]]
    if jenis == 'lama':
        return lv_lama(d, p['w'])
    if jenis == 'pivot':
        return lv_pivot(d, p['k'], p['W'], p['sumber'], p['tau'], (p['m'],))[p['m']]
    if jenis == 'vp':
        return lv_vp(d, p['W'], (p['th'],))[p['th']]
    if jenis == 'donchian':
        return lv_donchian(d, p['N'])
    if jenis == 'ma':
        return lv_ma(d, p['N'])
    if jenis == 'swing':
        return lv_swing(d, p['k'])
    return lv_kisi(d, p['fase'])


def hitung_semua(d):
    """{nama: (S, R)} untuk semua kandidat -- kelompok berparameter sama
    dihitung sekali."""
    out = {}
    for w in (100, 200, 250):
        out['A%d chart lama %d bar' % ({100: 0, 200: 1, 250: 2}[w], w)] = lv_lama(d, w)
    for k in (3, 5, 10):
        for W in (120, 250):
            for src in ('L', 'LH'):
                for tau in (0.015, 0.03):
                    res = lv_pivot(d, k, W, src, tau, (1, 2, 3))
                    for m, sr in res.items():
                        out['P k%d W%d %s tau%.1f m%d' % (k, W, src, tau * 100, m)] = sr
    for W in (60, 120, 250):
        res = lv_vp(d, W, (0.0, 1.0, 1.5))
        for th, sr in res.items():
            out['VP W%d th%.1f' % (W, th)] = sr
    for N in (10, 20, 60, 120):
        out['D donchian %d' % N] = lv_donchian(d, N)
    for N in (20, 50, 100, 200):
        out['MA %d' % N] = lv_ma(d, N)
    for k in (3, 5, 10):
        out['SW swing terakhir k%d' % k] = lv_swing(d, k)
    for f in range(N_FASE):
        out['PLASEBO fase %d' % f] = lv_kisi(d, (f + 0.5) / N_FASE)
    return out


# ---------------------------------------------------------------------------
# DATA PER EMITEN
# ---------------------------------------------------------------------------
def siapkan(t, df, mentah=None):
    df = df[['Open', 'High', 'Low', 'Close', 'Volume']].copy()
    df = df[df['Close'] > 0].sort_index()
    df = df[~df.index.duplicated(keep='last')]
    n = len(df)
    if n < 300:
        return None
    C = df['Close'].to_numpy(float)
    H = np.fmax(df['High'].to_numpy(float), C)
    L = np.fmin(df['Low'].to_numpy(float), C)
    L = np.where(L > 0, L, C)
    V = df['Volume'].fillna(0).to_numpy(float)
    dates = df.index
    Cadj = C
    if mentah is not None:
        # faktor mentah/setel per hari; sebelum data mentah mulai (Jun 2012)
        # memakai faktor hari pertamanya
        m = mentah[~mentah.index.duplicated(keep='last')].reindex(dates)
        f = (m / df['Close']).where(lambda x: np.isfinite(x) & (x > 0))
        f = f.ffill().bfill().to_numpy(float)
        if np.isfinite(f).all():
            C, H, L = C * f, H * f, L * f
    # kelayakan = persis uji.muat() (harga setel, semesta sama dengan riset lain)
    value = pd.Series(Cadj * V)
    traded30 = pd.Series((V > 0).astype(float)).rolling(30, min_periods=30).mean().to_numpy()
    medval20 = value.rolling(20, min_periods=20).median().to_numpy()
    ret1a = np.r_[np.nan, Cadj[1:] / Cadj[:-1] - 1]
    ret1 = np.r_[np.nan, C[1:] / C[:-1] - 1]          # yang dilihat di chart (strata jebol)
    bad = (np.abs(np.nan_to_num(ret1a)) > LONCAT).astype(float)
    bad60 = pd.Series(bad).rolling(60, min_periods=1).max().to_numpy()
    hist = np.arange(n)
    elig = ((hist >= 260) & (Cadj >= U.MIN_HARGA) & (medval20 >= U.MIN_NILAI) & (traded30 >= 0.9)
            & (bad60 == 0) & (dates >= '2013-01-01'))
    tr = np.fmax.reduce([H - L, np.abs(H - np.r_[C[0], C[:-1]]), np.abs(L - np.r_[C[0], C[:-1]])])
    atr = pd.Series(tr).rolling(14, min_periods=14).mean().to_numpy() / C
    # hasil ke depan, sama dengan panel.fitur: masuk close t+1, harga setel
    badc = np.concatenate([[0], np.cumsum(bad)])
    lr20 = np.full(n, np.nan)
    i = np.arange(n); j = i + 21; ok = j < n
    lr20[ok] = np.log(Cadj[j[ok]] / Cadj[i[ok] + 1])
    nb = np.full(n, 1.0); nb[ok] = badc[j[ok] + 1] - badc[i[ok] + 1]
    lr20[nb > 0] = np.nan
    half = int(hashlib.md5(t.encode()).hexdigest(), 16) % 2
    period = np.where(dates < '2020-01-01', 1, 2)
    # 0 cari (A,1), 1 validasi (B,2), 2 silang (B,1), 3 silang (A,2)
    cell = np.where(half == 0, np.where(period == 1, 0, 3), np.where(period == 2, 1, 2)).astype(np.int8)
    month = (dates.year * 12 + dates.month - 1).to_numpy().astype(np.int32)
    Lo_s = CS.snap(L); Hi_s = CS.snap(H)
    return {'t': t, 'C': C, 'H': H, 'L': L, 'V': V, 'elig': elig, 'atr': atr, 'lr20': lr20,
            'badc': badc, 'cell': cell, 'month': month, 'ret1': ret1,
            'dayno': ((dates - pd.Timestamp('1970-01-01')).days).to_numpy().astype(np.int32),
            'fraktal': CS.fraktal(Lo_s, Hi_s)}


def _jeda(idx, gap):
    keep, last = [], -10 ** 9
    for i in idx:
        if i - last >= gap:
            keep.append(i); last = i
    return np.array(keep, int)


# Pembanding plasebo -- diperbaiki dua kali SEBELUM hasil data asli dibuka,
# memakai random walk (cek_acak: di harga acak tak ada support, jadi lift
# semua penentu harus ~0). Sentuhan Donchian 20/60/120 jadi alat ukurnya:
#   v1  strata global jarak (1-3/3-6/>6%) x ATR (3 ember):  Donchian +2..+2,5
#   v2  global jarak/ATR (9) x ATR (8):                      Donchian +1,0 (z~3)
#       -> ATR14 itu pengukur gejolak yang berisik; sentuhan Donchian lebih
#          sering datang dari seri yang gejolak ASLINYA rendah.
#   v3  emiten x tahun x jarak/ATR:                          Donchian +2,5 (!)
#       -> blok waktu yang memuat jendela hasil ikut "tahu" jalan harga
#          sesudah sentuhan; makin pendek bloknya makin bias.
#   v4  EMITEN (seluruh riwayat) x jarak/ATR (9) x tertil ATR emiten itu:
#       |lift| rata-rata 0,27 poin, |z|>2 di 2 dari 94 kandidat, Donchian
#       +0,2 -- DIPAKAI. Sisa bias ~0,2-0,4 poin: lift di bawah ~0,5 poin
#       anggap nol.
B_JARAK_ATR = [0, 0.25, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0, 5.0, np.inf]
B_ATR = [0, 0.015, 0.02, 0.025, 0.03, 0.035, 0.045, 0.06, np.inf]
B_TURUN_ATR = [-np.inf, -3.0, -2.0, -1.5, -1.0, -0.5, 0.0, np.inf]


def _ember(x, edges):
    return np.clip(np.searchsorted(edges, np.nan_to_num(x, nan=0.0), side='right') - 1,
                   0, len(edges) - 2).astype(np.int16)


def kejadian(d, S, R, aid, tid):
    """Sentuhan support & resistance + jebol support untuk satu kandidat."""
    C, H, L, n = d['C'], d['H'], d['L'], len(d['C'])
    badc, elig = d['badc'], d['elig']
    rows_s, rows_j = [], []
    for sisi, X in ((0, S), (1, R)):
        Xp = np.r_[np.nan, X[:-1]]
        Cp = np.r_[np.nan, C[:-1]]
        eligp = np.r_[False, elig[:-1]]
        with np.errstate(invalid='ignore'):
            if sisi == 0:
                cand = eligp & np.isfinite(Xp) & (Cp > Xp * (1 + TOL)) & (L <= Xp * (1 + TOL))
            else:
                cand = eligp & np.isfinite(Xp) & (Cp < Xp * (1 - TOL)) & (H >= Xp * (1 - TOL))
        for u in _jeda(np.flatnonzero(cand), JEDA_SENTUH):
            if u + H_TAHAN >= n or badc[u + H_TAHAN + 1] - badc[u + 1] > 0:
                continue
            x = Xp[u]
            w = C[u:u + H_TAHAN + 1]
            tahan = not (w < x * BATAS).any() if sisi == 0 else not (w > x * (2 - BATAS)).any()
            w2 = C[u:min(u + H_PANTUL + 1, n)]
            if sisi == 0:
                kb = np.flatnonzero(w2 < x * BATAS); ka = np.flatnonzero(w2 >= x * PANTUL)
            else:
                kb = np.flatnonzero(w2 > x * (2 - BATAS)); ka = np.flatnonzero(w2 <= x * (2 - PANTUL))
            b = kb[0] if len(kb) else 10 ** 6
            a = ka[0] if len(ka) else 10 ** 6
            if a < b:
                pantul = 1
            elif b < a or len(w2) == H_PANTUL + 1:
                pantul = 0
            else:
                pantul = -1
            jarak = (Cp[u] / x - 1) if sisi == 0 else (1 - Cp[u] / x)
            rows_s.append((aid, tid, sisi, u, d['dayno'][u], d['month'][u], d['cell'][u],
                           int(tahan), pantul, d['lr20'][u], jarak, d['atr'][u - 1]))
    # jebol support
    Sp = np.r_[np.nan, S[:-1]]
    with np.errstate(invalid='ignore'):
        jb = np.isfinite(Sp) & (C < Sp * BATAS)
    first = jb & ~np.r_[False, jb[:-1]] & elig
    for t in _jeda(np.flatnonzero(first), JEDA_JEBOL):
        rows_j.append((aid, tid, t, d['dayno'][t], d['month'][t], d['cell'][t],
                       d['lr20'][t], d['ret1'][t], d['atr'][t - 1]))
    return rows_s, rows_j


def cakupan(d, S):
    """Histogram jarak support per sel (hanya hari layak): 0..50% per 1%, +1 ember 'tak ada'."""
    C, e, cell = d['C'], d['elig'], d['cell']
    out = np.zeros((4, 52), np.int64)
    with np.errstate(invalid='ignore', divide='ignore'):
        dist = C / S - 1
    b = np.where(np.isfinite(dist), np.clip((dist * 100).astype(int), 0, 50), 51)
    for c in range(4):
        m = e & (cell == c)
        out[c] = np.bincount(b[m], minlength=52)
    return out


S_DT = np.dtype([('aid', 'i2'), ('tid', 'i2'), ('sisi', 'i1'), ('u', 'i4'), ('day', 'i4'), ('month', 'i4'),
                 ('cell', 'i1'), ('tahan', 'i1'), ('pantul', 'i1'),
                 ('lr20', 'f4'), ('jarak', 'f4'), ('atr', 'f4')])
J_DT = np.dtype([('aid', 'i2'), ('tid', 'i2'), ('t', 'i4'), ('day', 'i4'), ('month', 'i4'), ('cell', 'i1'),
                 ('lr20', 'f4'), ('ret1', 'f4'), ('atr', 'f4')])


def olah(args):
    tid, t, df, mentah = args
    d = siapkan(t, df, mentah)
    if d is None:
        return None
    lv = hitung_semua(d)
    rs, rj = [], []
    cov = np.zeros((len(ALGO), 4, 52), np.int64)
    for nama, (S, R) in lv.items():
        aid = ALGO_ID[nama]
        a, b = kejadian(d, S, R, aid, tid)
        rs += a; rj += b
        cov[aid] = cakupan(d, S)
    harian = np.zeros(int(d['elig'].sum()), dtype=[('day', 'i4'), ('lr20', 'f4')])
    harian['day'] = d['dayno'][d['elig']]
    harian['lr20'] = d['lr20'][d['elig']]
    return (np.array(rs, dtype=S_DT), np.array(rj, dtype=J_DT), cov, harian)


def hitung():
    t0 = time.time()
    path, data = PN.sumber_harga()
    print('harga: %s (%d emiten), level di harga %s' % (os.path.basename(path), len(data), HARGA), flush=True)
    mentah = {}
    if HARGA == 'mentah':
        with open(MENTAH_FILE, 'rb') as fh:
            mentah = pickle.load(fh)
    tick = sorted(data)
    tugas = [(i, t, data[t], mentah.get(t)) for i, t in enumerate(tick)]
    del data, mentah
    with Pool(max(1, os.cpu_count() - 2)) as pool:
        parts = [p for p in pool.imap_unordered(olah, tugas, chunksize=4) if p is not None]
    s = np.concatenate([p[0] for p in parts])
    j = np.concatenate([p[1] for p in parts])
    cov = sum(p[2] for p in parts)
    h = np.concatenate([p[3] for p in parts])
    # pembanding pasar per hari: rata-rata log return 20h semua emiten layak
    hb = pd.DataFrame(h).dropna().groupby('day')['lr20'].mean()
    out = {'sentuh': s, 'jebol': j, 'cakupan': cov, 'pasar': hb, 'tickers': tick,
           'algo': [a[0] for a in ALGO], 'dibuat': time.strftime('%Y-%m-%d %H:%M')}
    with open(CACHE, 'wb') as fh:
        pickle.dump(out, fh)
    print('selesai %.0f detik: %d sentuhan, %d jebol' % (time.time() - t0, len(s), len(j)), flush=True)
    return out


def muat():
    if not os.path.exists(CACHE):
        return hitung()
    with open(CACHE, 'rb') as fh:
        Z = pickle.load(fh)
    if os.path.exists(CACHE_SUSULAN):
        with open(CACHE_SUSULAN, 'rb') as fh:
            T = pickle.load(fh)
        Z['sentuh'] = np.concatenate([Z['sentuh'], T['sentuh']])
        Z['jebol'] = np.concatenate([Z['jebol'], T['jebol']])
        Z['cakupan'] = np.concatenate([Z['cakupan'], T['cakupan']])
        Z['algo'] = Z['algo'] + T['algo']
    return Z


CACHE_SUSULAN = CACHE.replace('_kejadian_', '_susulan_')


def hitung_susulan():
    t0 = time.time()
    _, data = PN.sumber_harga()
    mentah = {}
    if HARGA == 'mentah':
        with open(MENTAH_FILE, 'rb') as fh:
            mentah = pickle.load(fh)
    tick = sorted(data)
    tugas = [(i, t, data[t], mentah.get(t)) for i, t in enumerate(tick)]
    del data, mentah
    with Pool(max(1, os.cpu_count() - 2)) as pool:
        parts = [p for p in pool.imap_unordered(olah_susulan, tugas, chunksize=4) if p is not None]
    out = {'sentuh': np.concatenate([p[0] for p in parts]), 'jebol': np.concatenate([p[1] for p in parts]),
           'cakupan': sum(p[2] for p in parts), 'algo': list(SUSULAN)}
    with open(CACHE_SUSULAN, 'wb') as fh:
        pickle.dump(out, fh)
    print('susulan selesai %.0f detik' % (time.time() - t0), flush=True)


# ---------------------------------------------------------------------------
# RINGKASAN
# ---------------------------------------------------------------------------
def _t_grup(df, kol, kunci='aid'):
    """Rata-rata & nilai t (galat baku dikelompokkan per bulan, = uji.t_klaster)
    per `kunci`, tanpa loop per kandidat."""
    d = df[[kunci, 'month', kol]].dropna()
    g = d.groupby(kunci)[kol]
    mu = g.mean(); n = g.size()
    bm = d.groupby([kunci, 'month'])[kol].agg(['sum', 'size'])
    bm['mu'] = bm.index.get_level_values(0).map(mu)
    bm['e'] = bm['sum'] - bm['size'] * bm['mu']
    se = np.sqrt((bm['e'] ** 2).groupby(level=0).sum()) / n
    t = (mu / se).where(n >= 30)
    return pd.DataFrame({'mu': mu, 't': t, 'n': n})


def siapkan_ringkas(Z, cells, sisi=0):
    """Kejadian + pembanding plasebo, untuk sel `cells`. Pembanding sentuhan
    dihitung per EMITEN dari seluruh riwayatnya (semua sel) -- lihat catatan
    v4 di atas B_JARAK_ATR; baru sesudah itu dipotong ke `cells`."""
    a = Z['sentuh']
    s = pd.DataFrame(a[a['sisi'] == sisi])
    a = Z['jebol']
    j = pd.DataFrame(a[np.isin(a['cell'], cells)])
    pasar = Z['pasar']
    j['exc'] = j['lr20'] - j['day'].map(pasar)
    s['exc'] = s['lr20'] - s['day'].map(pasar)
    s['jbin'] = _ember(s['jarak'] / s['atr'], B_JARAK_ATR)
    s['vbin'] = s.groupby('tid')['atr'].transform(
        lambda x: pd.qcut(x.rank(method='first'), 3, labels=False) if len(x) >= 3 else 0)
    j['rbin'] = _ember(j['ret1'] / j['atr'], B_TURUN_ATR)
    j['vbin'] = _ember(j['atr'], B_ATR)
    plas = [i for i, nm in enumerate(Z['algo']) if nm.startswith('PLASEBO')]
    ps = s[s['aid'].isin(plas)]
    kunci = ['tid', 'jbin', 'vbin']
    p_tahan = ps.groupby(kunci)['tahan'].mean().rename('p_tahan')
    pp = ps[ps['pantul'] >= 0].groupby(kunci)['pantul'].mean().rename('p_pantul')
    pj = (j[j['aid'].isin(plas)].dropna(subset=['exc'])
          .groupby(['cell', 'rbin', 'vbin'])['exc'].mean().rename('p_exc'))
    s = s[np.isin(s['cell'], cells)]
    s = s.merge(p_tahan, left_on=kunci, right_index=True, how='left')
    s = s.merge(pp, left_on=kunci, right_index=True, how='left')
    j = j.merge(pj, left_on=['cell', 'rbin', 'vbin'], right_index=True, how='left')
    # strata tanpa pembanding plasebo (jarang) dibuang
    s = s[s['p_tahan'].notna()]
    s['res'] = s['tahan'] - s['p_tahan']
    s['resP'] = np.where(s['pantul'] >= 0, s['pantul'] - s['p_pantul'], np.nan)
    s['pantul_ok'] = np.where(s['pantul'] >= 0, s['pantul'], np.nan)
    j['resJ'] = j['exc'] - j['p_exc']
    return s, j


def ringkas(Z, cells, sisi=0, sj=None):
    s, j = sj if sj is not None else siapkan_ringkas(Z, cells, sisi)
    nama = Z['algo']
    cov = Z['cakupan'][:, cells, :].sum(1)       # (algo, 52)
    gs = s.groupby('aid')
    lift = _t_grup(s, 'res')
    liftp = _t_grup(s, 'resP')
    jb = _t_grup(j, 'exc')
    jbp = _t_grup(j, 'resJ')
    tahan = gs['tahan'].mean(); plas = gs['p_tahan'].mean()
    pant = gs['pantul_ok'].mean(); sexc = gs['exc'].mean()
    rows = []
    for aid, a in enumerate(nama):
        c = cov[aid]
        tot = c.sum()
        cum = np.cumsum(c[:51])
        n = int(lift['n'].get(aid, 0))
        r = {'algo': a, 'cakupan%': 100 * c[:15].sum() / tot if tot else np.nan,
             'jarak_med%': float(np.searchsorted(cum, cum[-1] / 2)) if cum[-1] else np.nan,
             'sentuh/thn': n / (tot / 250) if tot else np.nan, 'n': n}
        if n >= 30:
            r['TAHAN%'] = tahan[aid] * 100
            r['plasebo%'] = plas[aid] * 100
            r['lift'] = lift.loc[aid, 'mu'] * 100
            r['t'] = lift.loc[aid, 't']
            r['PANTUL%'] = pant[aid] * 100
            r['liftP'] = liftp.loc[aid, 'mu'] * 100 if aid in liftp.index else np.nan
            r['sentuh_exc20%'] = (np.exp(sexc[aid]) - 1) * 100
        if aid in jb.index and jb.loc[aid, 'n'] >= 30:
            r['n_jebol'] = int(jb.loc[aid, 'n'])
            r['jebol_exc20%'] = (np.exp(jb.loc[aid, 'mu']) - 1) * 100
            r['tj'] = jb.loc[aid, 't']
            r['jebol_vs_plas'] = jbp.loc[aid, 'mu'] * 100 if aid in jbp.index else np.nan
        rows.append(r)
    return pd.DataFrame(rows).set_index('algo')


def tampil(df, judul, urut='lift', n=None):
    pd.set_option('display.width', 250)
    d = df.sort_values(urut, ascending=False)
    if n:
        d = d.head(n)
    print('\n' + '=' * 160 + '\n' + judul + '\n' + '=' * 160)
    print(d.round(2).to_string())


def pilih(df):
    """ATURAN PILIH di docstring, sebagai kode -- dijalankan di sel pencarian.
    'Jebol tidak lebih lemah' = selisih 20h sesudah jebol tidak lebih dari
    0,5 poin di atas milik chart lama (toleransi derau)."""
    a0 = df.loc['A0 chart lama 100 bar']
    d = df[~df.index.str.startswith('PLASEBO') & ~df.index.str.startswith('A')]
    lolos = d[(d['cakupan%'] >= a0['cakupan%'] - 10) & (d['sentuh/thn'] >= 2)
              & (d['jebol_exc20%'] <= a0['jebol_exc20%'] + 0.5)]
    if lolos.empty:
        return None, lolos
    top = lolos['lift'].idxmax()
    jenis, p = ALGO[ALGO_ID[top]][1], ALGO[ALGO_ID[top]][2]
    if 'W' in p:
        for nm in lolos.index:
            j2, p2 = ALGO[ALGO_ID[nm]][1], ALGO[ALGO_ID[nm]][2]
            sama = {k: v for k, v in p2.items() if k != 'W'} == {k: v for k, v in p.items() if k != 'W'}
            if j2 == jenis and sama and p2['W'] < p['W'] and lolos.loc[top, 'lift'] - lolos.loc[nm, 'lift'] < 1:
                return nm, lolos
    return top, lolos


def cmd_cari():
    Z = muat()
    for sisi, nm in ((0, 'SUPPORT'), (1, 'RESISTANCE (cermin)')):
        df = ringkas(Z, [0], sisi)
        tampil(df, '%s -- %s' % (nm, CELL_NAMA[0]))
        if sisi == 0:
            top, lolos = pilih(df)
            print('\nlolos syarat: %d kandidat; TERPILIH: %s' % (len(lolos), top))


# Diisi SESUDAH sel pencarian dilihat, SEBELUM sel validasi dibuka (15 Okt
# 2026, harga mentah). Aturan pilih -> 'VP W250 th1.0': lift TAHAN +2,56
# (t 1,80) vs chart lama +1,94 (t 1,36); cakupan 63,3% (batas 63,2), jebol
# -1,26%/20h (t -2,71). Saudara berjendela pendek (W120/W60) gugur di
# syarat cakupan, jadi aturan seri tidak berlaku. Sisi resistance di sel
# yang sama: +2,85 (t 2,61) vs chart lama +1,65.
PILIHAN = ['VP W250 th1.0']
# pembanding yang ikut DITAMPILKAN di validasi (bukan untuk dipilih ulang)
KONTEKS = ['A1 chart lama 200 bar', 'VP W120 th1.0', 'VP W250 th1.5', 'VP W250 th0.0',
           'SW swing terakhir k3', 'MA 50', 'D donchian 10', 'P k3 W120 LH tau3.0 m2']


def _seri_acak(seed, n=3000):
    """Random walk dengan gejolak & rentang harian realistis, di fraksi BEI."""
    r = np.random.default_rng(seed)
    vol = r.uniform(0.015, 0.035)
    lr = r.normal(0, vol, n)
    C = 1500 * np.exp(np.cumsum(lr))
    O = np.r_[1500, C[:-1]] * (1 + r.normal(0, vol / 4, n))
    H = np.maximum(O, C) * (1 + np.abs(r.normal(0, vol / 2, n)))
    L = np.minimum(O, C) * (1 - np.abs(r.normal(0, vol / 2, n)))
    df = pd.DataFrame({'Open': CS.snap(O), 'High': CS.snap(H), 'Low': CS.snap(L), 'Close': CS.snap(C),
                       'Volume': np.full(n, 5e6)}, index=pd.bdate_range('2012-01-02', periods=n))
    return df[df['Close'] >= 120]


def _olah_acak(k):
    df = _seri_acak(k)
    return olah((k, 'X%03d' % k, df, None)) if len(df) >= 400 else None


def cek_acak(n_seri=120):
    """
    Uji metodenya sendiri: di random walk TIDAK ADA support, jadi lift
    setiap penentu harus ~0. Kalau ada yang tetap "menang" di sini, berarti
    pembanding plasebonya bias untuk penentu itu -- dan angkanya di data
    asli tidak bisa dipercaya.
    """
    with Pool(max(1, os.cpu_count() - 2)) as pool:
        parts = [p for p in pool.map(_olah_acak, range(n_seri)) if p is not None]
    Z = {'sentuh': np.concatenate([p[0] for p in parts]), 'jebol': np.concatenate([p[1] for p in parts]),
         'cakupan': sum(p[2] for p in parts), 'pasar': pd.Series(dtype=float), 'algo': [a[0] for a in ALGO]}
    Z['sentuh']['cell'] = 0; Z['jebol']['cell'] = 0
    for sisi in (0, 1):
        df = ringkas(Z, [0], sisi)
        df = df[~df.index.str.startswith('PLASEBO')]
        df['z'] = df['t']
        d = df[['n', 'TAHAN%', 'plasebo%', 'lift', 'z']].sort_values('lift')
        print('\n' + ('SUPPORT' if sisi == 0 else 'RESISTANCE'))
        print(d.round(2).to_string())
        print('lift mutlak rata-rata %.2f poin; |z|>2: %d dari %d (harapan acak ~%.0f)'
              % (d['lift'].abs().mean(), int((d['z'].abs() > 2).sum()), len(d), 0.05 * len(d)))


def cmd_validasi(semua=False):
    Z = muat()
    pilih = None if semua else ['A0 chart lama 100 bar'] + PILIHAN + KONTEKS
    for sisi, nm in ((0, 'SUPPORT'), (1, 'RESISTANCE (cermin)')):
        for c in (0, 1, 2, 3):
            df = ringkas(Z, [c], sisi)
            if pilih:
                df = df.loc[[p for p in pilih if p in df.index]]
            tampil(df, '%s -- %s' % (nm, CELL_NAMA[c]))


def cmd_tahun(nama):
    """lift TAHAN per tahun (semua emiten) untuk kandidat `nama` + chart lama."""
    Z = muat()
    s, _ = siapkan_ringkas(Z, [0, 1, 2, 3], 0)
    s['tahun'] = pd.to_datetime(s['day'], unit='D').dt.year
    rows = {}
    for nm in ['A0 chart lama 100 bar'] + list(nama):
        aid = Z['algo'].index(nm)
        e = s[s['aid'] == aid]
        rows[nm] = (e.groupby('tahun')['res'].mean() * 100).round(1)
    out = pd.DataFrame(rows).T
    out['tahun+'] = (out > 0).sum(1).astype(str) + '/' + out.notna().sum(1).astype(str)
    print(out.to_string())


if __name__ == '__main__':
    perintah = sys.argv[1] if len(sys.argv) > 1 else 'cari'
    if perintah == 'hitung':
        hitung()
    elif perintah == 'susulan':
        hitung_susulan()
    elif perintah == 'cari':
        cmd_cari()
    elif perintah == 'validasi':
        cmd_validasi(semua=len(sys.argv) > 2 and sys.argv[2] == 'semua')
    elif perintah == 'tahun':
        cmd_tahun(sys.argv[2:] or PILIHAN)
    elif perintah == 'cek-acak':
        cek_acak(int(sys.argv[2]) if len(sys.argv) > 2 else 120)
    else:
        print(__doc__)
        sys.exit(2)
