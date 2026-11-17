"""
Dua pertanyaan (24 Sep 2026):

  1. Hubungan harga-volume seperti apa yang BENERAN diikuti kenaikan?
  2. Saham yang memantul / tertahan di area support -- punya peluang naik?

Kerangka uji sama dengan uji.py (pencarian separuh A 2013-19, validasi
separuh B 2020-26, pembanding = semua emiten layak di hari yang sama,
selisih majemuk). Pola didaftar di bawah SEBELUM hasil dilihat.

Support di sini didefinisikan mekanis, bukan digambar:
  S      = low terendah di jendela t-119 .. t-20 (lantai yang sudah
           berumur minimal 20 hari)
  syarat = sesudah lantai itu harga sempat naik >=15% di atasnya
           (max close t-60..t-10 >= 1,15 S) -- jadi ini KEMBALI ke lantai,
           bukan tren turun yang terus bikin low baru
  tes    = low 10 hari terakhir masuk 0,95S..1,03S
  tahan  = tidak ada CLOSE di bawah 0,97S selama 10 hari itu

PEMAKAIAN: python -m website.riset_pola_naik.support_volume
"""
import sys

import numpy as np
import pandas as pd
from numpy.lib.stride_tricks import sliding_window_view as swv

from . import panel as PN
from . import uji as U


def fitur_tambahan(t, df):
    df = df[['High', 'Low', 'Close', 'Volume']].copy()
    df = df[df['Close'] > 0].sort_index()
    df = df[~df.index.duplicated(keep='last')]
    if len(df) < 300:
        return None
    C, V = df['Close'], df['Volume'].fillna(0)
    L = np.minimum(df['Low'], C)
    r = C.pct_change()
    o = pd.DataFrame(index=df.index)
    o['ticker'] = t

    # --- harga vs volume ---
    upv = V.where(r > 0, 0).rolling(20).sum()
    dnv = V.where(r < 0, 0).rolling(20).sum()
    o['udr20'] = (upv - dnv) / V.rolling(20).sum().replace(0, np.nan)   # -1..1, mirip OBV ternormalisasi
    vrel = V / V.rolling(20).mean().replace(0, np.nan)
    o['pvcorr20'] = r.rolling(20).corr(vrel)

    # --- support ---
    S = L.shift(20).rolling(100, min_periods=100).min()
    low10 = L.rolling(10).min()
    cmin10 = C.rolling(10).min()
    kembali = C.shift(10).rolling(50).max() >= 1.15 * S
    tes = (low10 >= 0.95 * S) & (low10 <= 1.03 * S)
    tahan = cmin10 >= 0.97 * S
    base = kembali & tes & tahan
    pantul = base & (C >= 1.05 * low10)
    o['s_pantul'] = (pantul & ~pantul.shift(1, fill_value=False)).astype(float)
    o['s_tahan'] = (base & (C <= 1.04 * S)).astype(float)
    tembus = kembali & (C < 0.95 * S)
    o['s_tembus'] = (tembus & ~tembus.shift(1, fill_value=False)).astype(float)
    pernah_bawah = (C < 0.97 * S).astype(float).rolling(10).max() == 1
    spring = kembali & pernah_bawah & (C >= S)
    o['s_spring'] = (spring & ~spring.shift(1, fill_value=False)).astype(float)

    # berapa hari di jendela lantai yang low-nya ada di +/-3% S (zona teruji)
    l = L.to_numpy(float); s = S.to_numpy(float)
    n = len(l); cnt = np.full(n, np.nan)
    if n > 120:
        w = swv(l[:-20], 100)                   # w[k] = l[k : k+100] -> dipakai baris k+119
        sk = s[119:119 + len(w)]
        cnt[119:119 + len(w)] = ((w >= sk[:, None] * 0.97) & (w <= sk[:, None] * 1.03)).sum(1)
    o['zona_n'] = cnt
    return o


def muat():
    p = U.muat()
    _, data = PN.sumber_harga()
    ext = pd.concat([f for f in (fitur_tambahan(t, d) for t, d in data.items()) if f is not None])
    ext.index.name = 'date'
    ext = ext.reset_index()
    return p.merge(ext, on=['ticker', 'date'], how='left')


def pola(r):
    P = {}
    P['ALL eligible days'] = pd.Series(True, index=r.index)
    # --- 1. hubungan harga-volume ---
    P['V1 volume dominan di hari naik (udr20>=0.4)'] = r['udr20'] >= 0.4
    P['V2 volume dominan di hari turun (udr20<=-0.4)'] = r['udr20'] <= -0.4
    P['V3 harga turun/datar, volume di hari naik (divergensi +)'] = (r['udr20'] >= 0.3) & (r['ret20'] <= 0)
    P['V4 harga naik, volume di hari turun (divergensi -)'] = (r['udr20'] <= -0.3) & (r['ret20'] >= 0)
    P['V5 korelasi return-volume 20h >= 0.4'] = r['pvcorr20'] >= 0.4
    P['V6 korelasi return-volume 20h <= -0.2'] = r['pvcorr20'] <= -0.2
    P['V7 kapitulasi: -5% + volume >3x setelah -25%'] = (r['ret1'] <= -0.05) & (r['vspike'] >= 3) & (r['dd60'] <= -0.25)
    P['V8 tembus basis + volume >2x (=C2 lama)'] = (r['brk30'] == 1) & (r['prevrange30'] < 0.20) & (r['vspike'] > 2)
    # --- 2. support ---
    sp = r['s_pantul'] == 1
    P['S1 memantul +5% dari tes support'] = sp
    P['S2 S1 + volume hari pantul >1.5x'] = sp & (r['vspike'] > 1.5)
    P['S3 S1 + volume kering saat tes (vdry<0.7)'] = sp & (r['vdry'] < 0.7)
    P['S4 S1 + zona teruji >=5 hari'] = sp & (r['zona_n'] >= 5)
    P['S5 S1 + di atas MA200'] = sp & (r['ma200'] > 0)
    P['S6 tertahan di support (belum pantul)'] = r['s_tahan'] == 1
    P['S7 tembus support ke bawah (pembanding)'] = r['s_tembus'] == 1
    P['S8 jebol lalu balik ke atas support (spring)'] = r['s_spring'] == 1
    return P


def main():
    p = muat()
    P = pola(p)
    for label, m in U.sel(p).items():
        U.tampil(U.jalankan(p, P, m), label)


if __name__ == '__main__':
    sys.exit(main())
