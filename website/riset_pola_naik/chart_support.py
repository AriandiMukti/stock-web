"""
Uji support/resistance PERSIS seperti yang digambar chart Halaman Saham
(utilities.compute_levels pada 100 bar terakhir, lalu stock_chart.js:
support terdekat = level tertinggi <= close terakhir).

Direplikasi per hari tanpa melihat ke depan: fraktal di bar i cuma butuh
bar i-2..i+2, jadi dihitung sekali untuk seluruh riwayat, lalu level pada
hari t = fraktal i di t-97..t-2 (persis indeks 2..97 dari jendela 100 bar
yang berakhir di t) -> hitung >=2 -> buang yang terlalu rapat (aturan 2%/5%
yang sama).

Harga Yahoo lama disesuaikan dividen (pecahan), sedangkan aturan "muncul
>=2x" butuh harga yang PERSIS sama -- jadi High/Low dibulatkan ke fraksi
harga BEI dulu, seperti data mentah yang dilihat chart.

PEMAKAIAN: python -m website.riset_pola_naik.chart_support
"""
import os
import pickle
import sys
from multiprocessing import Pool

import numpy as np
import pandas as pd

from . import panel as PN
from . import uji as U
from . import support_volume as SV

CACHE = os.path.join(PN.RESEARCH_CACHE, 'chart_support_levels.pkl')


def tick(p):
    return np.select([p < 200, p < 500, p < 2000, p < 5000], [1, 2, 5, 10], 25)


def snap(x):
    t = tick(x)
    return np.round(x / t) * t


def fraktal(Lo, Hi):
    """Salinan vektor utilities.is_support / is_resistance (elif: support menang)."""
    n = len(Lo)
    val = np.full(n, np.nan)

    def s(a, k):
        out = np.full(n, np.nan)
        if k > 0:
            out[k:] = a[:-k]
        else:
            out[:k] = a[-k:]
        return out

    for arr, sign, kind in ((Lo, 1, 'sup'), (Hi, -1, 'res')):
        m1, m2, p1, p2 = s(arr, 1), s(arr, 2), s(arr, -1), s(arr, -2)
        frac = np.where(arr <= 200, 0.02, 0.01)
        if kind == 'sup':
            c = (arr < m1) & (arr < p1) & (p1 < p2) & (m1 < m2)
        else:
            c = (arr > m1) & (arr > p1) & (p1 > p2) & (m1 > m2)
        near = lambda o: np.abs(arr - o) / arr <= frac
        c5 = (near(m1) | near(m2)) & (near(p1) | near(p2))
        hit = (c | c5)
        hit[:2] = False; hit[-2:] = False
        if kind == 'sup':
            val[hit] = arr[hit]
            sup_hit = hit
        else:
            val[hit & ~sup_hit] = arr[hit & ~sup_hit]
    return val


def levels_dari(vals):
    v = vals[~np.isnan(vals)]
    if len(v) == 0:
        return v
    u, c = np.unique(v, return_counts=True)
    lv = u[c >= 2]
    keep, low = [], None
    for x in lv:
        if low is None:
            keep.append(x); low = x; continue
        if x <= low * 1.05:          # (x < low*1.02) or (low*1.02 < x <= low*1.05) -> dibuang
            if x == low * 1.02:      # celah aturan asli: tepat 1.02 tidak dibuang
                keep.append(x); low = x
            continue
        keep.append(x); low = x
    return np.array(keep)


def per_emiten(args):
    t, df = args
    df = df[['High', 'Low', 'Close']].copy()
    df = df[df['Close'] > 0].sort_index()
    df = df[~df.index.duplicated(keep='last')]
    n = len(df)
    if n < 300:
        return None
    C = df['Close'].to_numpy(float)
    Lo = snap(np.minimum(df['Low'].to_numpy(float), C))
    Hi = snap(np.maximum(df['High'].to_numpy(float), C))
    vals = fraktal(Lo, Hi)
    sup = np.full(n, np.nan); res = np.full(n, np.nan); nlev = np.zeros(n)
    for k in range(99, n):
        lv = levels_dari(vals[k - 97:k - 1])
        nlev[k] = len(lv)
        if len(lv) == 0:
            continue
        b = lv[lv <= C[k]]
        a = lv[lv >= C[k]]
        if len(b):
            sup[k] = b[-1]
        if len(a):
            res[k] = a[0]
    return pd.DataFrame({'ticker': t, 'sup': sup, 'res': res, 'nlev': nlev,
                         'lo_s': Lo, 'c_raw': C}, index=df.index)


def hitung_level():
    if os.path.exists(CACHE):
        with open(CACHE, 'rb') as fh:
            return pickle.load(fh)
    _, data = PN.sumber_harga()
    with Pool(max(1, os.cpu_count() - 1)) as pool:
        parts = pool.map(per_emiten, list(data.items()), chunksize=8)
    out = pd.concat([x for x in parts if x is not None])
    out.index.name = 'date'
    out = out.reset_index()
    with open(CACHE, 'wb') as fh:
        pickle.dump(out, fh)
    return out


def tambah_kolom(p):
    lv = hitung_level()
    p = p.merge(lv, on=['ticker', 'date'], how='left')
    g = p.groupby('ticker', sort=False)
    p['jarak_sup'] = p['close'] / p['sup'] - 1
    p['jarak_res'] = p['res'] / p['close'] - 1
    sup_prev = g['sup'].shift(1)
    # sentuh: low salah satu dari 5 hari terakhir <= support+1% (dan tidak tembus jauh)
    lo5 = g['lo_s'].transform(lambda s: s.rolling(5).min())
    cmin5 = g['close'].transform(lambda s: s.rolling(5).min())
    sentuh = (lo5 <= p['sup'] * 1.01) & (cmin5 >= p['sup'] * 0.98)
    pantul = sentuh & (p['close'] >= p['sup'] * 1.04)
    p['c_pantul'] = (pantul & ~pantul.groupby(p['ticker']).shift(1, fill_value=False)).astype(float)
    p['c_tahan'] = (sentuh & (p['jarak_sup'] < 0.02)).astype(float)
    jebol = p['close'] < sup_prev * 0.97
    p['c_jebol'] = (jebol & ~jebol.groupby(p['ticker']).shift(1, fill_value=False)).astype(float)
    return p


def pola(r):
    P = {'ALL eligible days': pd.Series(True, index=r.index)}
    js = r['jarak_sup']
    P['J1 jarak ke support chart 0-2%'] = (js >= 0) & (js < 0.02)
    P['J2 jarak ke support chart 2-5%'] = (js >= 0.02) & (js < 0.05)
    P['J3 jarak ke support chart 5-10%'] = (js >= 0.05) & (js < 0.10)
    P['J4 jarak ke support chart >10%'] = js >= 0.10
    P['J5 tidak ada support di bawah (di bawah semua level)'] = r['sup'].isna() & (r['nlev'] > 0)
    P['J6 resistance chart >15% di atas (ruang naik lebar)'] = r['jarak_res'] >= 0.15
    P['J7 tidak ada resistance di atas (di atas semua level)'] = r['res'].isna() & (r['nlev'] > 0)
    cp = r['c_pantul'] == 1
    P['C1 memantul dari support chart (sentuh, lalu +4%)'] = cp
    P['C2 C1 + volume hari pantul >1.5x'] = cp & (r['vspike'] > 1.5)
    P['C3 C1 + di atas MA200'] = cp & (r['ma200'] > 0)
    P['C4 C1 + resistance >=10% di atas'] = cp & (r['jarak_res'] >= 0.10)
    P['C5 tertahan di support chart (sentuh, close <2% di atasnya)'] = r['c_tahan'] == 1
    P['C6 jebol support chart (close <-3% di bawahnya)'] = r['c_jebol'] == 1
    return P


def main():
    p = tambah_kolom(SV.muat())
    print('baris dengan support chart: %.0f%%' % (p.loc[p['elig'], 'sup'].notna().mean() * 100))
    P = pola(p)
    for label, m in U.sel(p).items():
        U.tampil(U.jalankan(p, P, m), label)


if __name__ == '__main__':
    sys.exit(main())
