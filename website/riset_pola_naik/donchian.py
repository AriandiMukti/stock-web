"""
Donchian channel (gaya Turtle) vs Tembus Basis + TS10 -- 29 Okt 2026.

KENAPA
Puncak 52 minggu sudah lolos dan itu pada dasarnya Donchian ~250 hari pada
close. Yang belum pernah diuji: Donchian ASLI (kanal dari High/Low, bukan
close) dengan N pendek gaya Turtle (20/55), dan keluar lewat kanal bawah
alih-alih trailing 10%.

DESAIN (didaftar SEBELUM hasil dilihat)
Masuk (sinyal di close t, beli di close t+1, satu sinyal per emiten per 20 bar):
    D20 / D55 / D120 / D250   close t > High tertinggi N hari SEBELUM t
    ... + vol                 idem dan volume t > 2x rata-rata 20 hari sebelumnya
    ref TB+vol                tembus basis + vol (yang dipakai /tembus-basis)
    ref P52+vol               puncak 52 minggu (close) + vol
Keluar (pemicu di close k, jual di close k+1):
    TS10   close <= 90% close tertinggi sejak masuk, maks 120 hari (aturan produksi)
    DL10   close < Low terendah 10 hari sebelum k, maks 250 hari (Turtle S1)
    DL20   close < Low terendah 20 hari sebelum k, maks 250 hari (Turtle S2)
Transaksi yang belum kena pemicu saat data habis ditutup di bar terakhir
(bukan dibuang -- aturan yang menahan lama justru kehilangan pemenangnya
kalau dibuang). Berlaku sama untuk semua aturan, termasuk referensi.

Sel: PILIH = separuh emiten A 2013-2019, UJI = separuh B 2020-2026 (uji.py).
Portofolio 10 slot, ongkos 0,15% beli + 0,25% jual + slippage 0,25%/sisi,
CAGR & drawdown = MEDIAN dari 10 urutan pengisian slot acak.

ATURAN KEPUTUSAN
Dari 24 kombinasi Donchian (8 masuk x 3 keluar), yang dipilih = CAGR median
tertinggi di PILIH. Ia LOLOS kalau di UJI: CAGR median > TB+vol TS10, maxDD
median tidak lebih buruk >5 poin, dan t per transaksi vs pasar > 2.
Kombinasi lain di UJI cuma konteks, bukan untuk dipilih ulang.

HASIL (29 Okt 2026) -- GAGAL menurut aturan keputusan
Yang dipilih di PILIH: D250+vol / DL20 (CAGR 19,1, DD -16,9). Di UJI
anjlok ke CAGR 17,5 / DD -53,2, vs TB+vol TS10 23,2 / -21,0.

CAGR median / DD median (10 urutan slot acak):
                   PILIH (A 2013-19)          UJI (B 2020-26)
                  TS10    DL10    DL20       TS10    DL10    DL20
    D20         4/-43   3/-50   3/-44     26/-30  42/-44  27/-51
    D55         7/-30  10/-37  10/-24     26/-36  43/-44  32/-43
    D120       10/-23  11/-29  11/-23     23/-39  41/-48  28/-40
    D250       13/-19  10/-25  16/-18     37/-26  34/-39  21/-50
    D250+vol   11/-15  10/-19  19/-17     29/-31  32/-39  18/-53
    ref TB+vol  3/-33   7/-35   9/-34     23/-21  22/-30  14/-32
    ref P52+vol 14/-18 11/-26  21/-20     27/-27  31/-42  26/-53

- Per transaksi SEMUA varian tembus atas mengalahkan pasar (t 2,4..7,0):
  breakout memang bekerja, Donchian tidak menambah hal baru di situ.
- Keluar kanal bawah tidak stabil: DL20 terbaik di PILIH untuk N panjang,
  terburuk di UJI; DL10 CAGR tinggi di UJI tapi DD -40..-51. TS10 satu-
  satunya keluar yang drawdown-nya terkendali di kedua sel -> tetap TS10.
- N pendek (20/55): transaksi 2-3x lebih banyak, PILIH cuma 3-10%/thn
  dengan DD -30..-50. Periode UJI (2020-26) murah hati ke SEMUA breakout,
  jadi CAGR tinggi di sana sendirian tidak berarti banyak.
- Yang konsisten di dua sel cuma D250 + TS10 (13/-19 -> 37/-26) -- itu
  pada dasarnya puncak 52 minggu yang sudah ada (pakai High, bukan close).
  Terlihat SESUDAH semua sel dibuka, jadi bukan bukti baru.

PEMAKAIAN (dari <project>/)
    python -m website.riset_pola_naik.donchian
"""
import time
import warnings

import numpy as np
import pandas as pd

from . import keluar as KL
from . import panel as PN
from . import uji

warnings.filterwarnings('ignore')

NS = (20, 55, 120, 250)
KELUAR = {'TS10': ('ts', 0.10, 120), 'DL10': ('dl', 10, 250), 'DL20': ('dl', 20, 250)}
N_SEED = 10


def kanal(p):
    """Tambah brkN (tembus High N hari sebelumnya) ke panel; kembalikan juga
    Low terendah M hari sebelumnya per emiten untuk pemicu keluar."""
    _, data = PN.sumber_harga()
    cols, low = [], {}
    for t, df in data.items():
        df = df[['High', 'Low', 'Close']].copy()
        df = df[df['Close'] > 0].sort_index()
        df = df[~df.index.duplicated(keep='last')]     # sama dengan panel.fitur -> hist cocok
        if len(df) < 300:
            continue
        C = df['Close']
        H = np.maximum(df['High'], C); L = np.minimum(df['Low'], C)
        f = pd.DataFrame({'ticker': t, 'hist': np.arange(len(df), dtype='float32')})
        for n in NS:
            f['brk%d' % n] = (C > H.rolling(n, min_periods=n).max().shift(1)).to_numpy()
        cols.append(f)
        low[t] = {m: L.rolling(m, min_periods=m).min().shift(1).to_numpy(float) for m in (10, 20)}
    k = pd.concat(cols)
    p = p.merge(k, on=['ticker', 'hist'], how='left')
    for n in NS:
        p['brk%d' % n] = p['brk%d' % n].fillna(False).astype(bool)
    return p, low


def keluar_di(a, lo, i, aturan):
    """Indeks baris keluar dan apakah ditutup paksa di akhir data."""
    jenis, x, maks = KELUAR[aturan]
    c = a['close']
    n = len(c)
    akhir = min(i + maks, n - 1)
    jalan = c[i:akhir + 1]
    if jenis == 'ts':
        kena = np.flatnonzero((jalan <= (1 - x) * np.maximum.accumulate(jalan))[1:]) + 1
    else:
        kena = np.flatnonzero((jalan < lo[x][i:akhir + 1])[1:]) + 1
    j = i + kena[0] + 1 if len(kena) else i + maks
    paksa = j > n - 1
    j = min(j, n - 1)
    if j <= i or a['bad'][i + 1:j + 1].any():
        return None, False
    return j, paksa


def transaksi(ev, per, low, pasar, aturan):
    rows = []
    for t, h, tgl in zip(ev['ticker'], ev['hist'], ev['date']):
        a = per[t]
        i = int(h) - a['h0'] + 1
        if i >= len(a['close']) - 1:
            continue
        # per[t] mulai dari baris panel (>= Jun 2012), low[t] dari baris 0 riwayat
        lo = {m: v[a['h0']:a['h0'] + len(a['close'])] for m, v in low[t].items()}
        j, paksa = keluar_di(a, lo, i, aturan)
        if j is None:
            continue
        d_in, d_out = a['date'][i], a['date'][j]
        try:
            m = pasar.loc[d_out] - pasar.loc[d_in]
        except KeyError:
            continue
        r = np.log(a['close'][j] / a['close'][i])
        rows.append({'ticker': t, 'masuk': d_in, 'keluar': d_out, 'tahan': j - i, 'r': r, 'lebih': r - m,
                     'paksa': paksa, 'bulan': pd.Timestamp(tgl).to_period('M')})
    return pd.DataFrame(rows)


def cagr_pasar(pasar, mulai, akhir):
    s = pasar[(pasar.index >= mulai) & (pasar.index <= akhir)]
    th = (s.index[-1] - s.index[0]).days / 365.25
    return round((np.exp((s.iloc[-1] - s.iloc[0]) / th) - 1) * 100, 1)


def main():
    t0 = time.time()
    p = uji.muat()
    p, low = kanal(p)
    per, pasar = KL.siapkan(p)
    kal = pd.DatetimeIndex(sorted(p['date'].unique()))
    harga = {t: dict(zip(pd.DatetimeIndex(a['date']), a['close'])) for t, a in per.items()}
    vol = p['vspike'] > 2
    MASUK = {}
    for n in NS:
        MASUK['D%d' % n] = p['brk%d' % n]
    for n in NS:
        MASUK['D%d+vol' % n] = p['brk%d' % n] & vol
    MASUK['ref TB+vol'] = (p['brk30'] == 1) & (p['prevrange30'] < 0.20) & vol
    MASUK['ref P52+vol'] = (p['hi250'] == 1) & vol
    SEL = {'PILIH': (p['half'] == 0) & (p['period'] == 1),
           'UJI': (p['half'] == 1) & (p['period'] == 2)}
    print('kanal siap, %.0f detik' % (time.time() - t0), flush=True)
    print('pasar rata-rata-sama CAGR%%: 2013-19 %.1f | 2020-26 %.1f'
          % (cagr_pasar(pasar, '2013-01-01', '2019-12-31'), cagr_pasar(pasar, '2020-01-01', '2026-12-31')))

    rows = []
    for ns, s in SEL.items():
        for nm, m in MASUK.items():
            ev = uji.jeda(p[m.fillna(False) & p['elig'] & s])
            for ak in KELUAR:
                tx = transaksi(ev, per, low, pasar, ak)
                r = {'sel': ns, 'masuk': nm, 'keluar': ak}
                r.update(KL.ringkas_tx(tx))
                r['paksa'] = int(tx['paksa'].sum()) if len(tx) else 0
                hasil = [KL.portofolio(tx, kal, harga, seed=sd) for sd in range(N_SEED)]
                cagr = np.array([h['CAGR%'] for h in hasil]); dd = np.array([h['maxDD%'] for h in hasil])
                r['CAGR med'] = round(float(np.median(cagr)), 1)
                r['CAGR min..max'] = '%.1f..%.1f' % (cagr.min(), cagr.max())
                r['DD med'] = round(float(np.median(dd)), 1)
                rows.append(r)
                print('  %-5s %-12s %-5s n=%-5s CAGR %5.1f DD %6.1f  (%.0f dtk)'
                      % (ns, nm, ak, r['n'], r['CAGR med'], r['DD med'], time.time() - t0), flush=True)
    df = pd.DataFrame(rows).set_index(['sel', 'masuk', 'keluar'])
    with pd.option_context('display.width', 250, 'display.max_columns', 30):
        for ns in SEL:
            print('\n' + '=' * 130 + '\n' + ns + '\n' + '=' * 130)
            print(df.loc[ns].to_string())

    # aturan keputusan
    don = df.loc['PILIH'].drop(index=['ref TB+vol', 'ref P52+vol'], level='masuk')
    pilih = don['CAGR med'].idxmax()
    u = df.loc['UJI']
    ref = u.loc[('ref TB+vol', 'TS10')]
    hu = u.loc[pilih]
    lolos = (hu['CAGR med'] > ref['CAGR med']) and (hu['DD med'] >= ref['DD med'] - 5) and (hu['t'] > 2)
    print('\nDIPILIH di PILIH: %s / %s (CAGR %.1f)' % (pilih[0], pilih[1], don.loc[pilih, 'CAGR med']))
    print('di UJI: CAGR %.1f DD %.1f t %.1f  vs  TB+vol TS10: CAGR %.1f DD %.1f t %.1f  ->  %s'
          % (hu['CAGR med'], hu['DD med'], hu['t'], ref['CAGR med'], ref['DD med'], ref['t'],
             'LOLOS' if lolos else 'GAGAL'))


if __name__ == '__main__':
    main()
