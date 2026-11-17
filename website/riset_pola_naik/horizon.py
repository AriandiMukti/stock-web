"""
Sapuan horizon: apakah pola yang lolos/gagal di 20h-60h berubah nasib di
horizon trader cepat (1, 3, 5, 10 hari)?

Event SAMA di semua horizon (jeda 20 seperti uji.py), jadi yang berubah
cuma panjang tahan. Masuk close t+1, selisih majemuk vs semua emiten layak
hari yang sama. Kolom 'bersih' = return majemuk ABSOLUT dikurangi biaya
pulang-pergi BIAYA (fee beli+jual, belum termasuk slippage).

    python -m website.riset_pola_naik.horizon
"""
import pickle
import os

import numpy as np
import pandas as pd

from . import uji
from .panel import RESEARCH_CACHE, LONCAT

H = (1, 3, 5, 10, 20, 60)
BIAYA = 0.004


def _fwd(p):
    p = p.sort_values(['ticker', 'date']).reset_index(drop=True)
    g = p.groupby('ticker', sort=False)['close']
    entry = g.shift(-1)
    bad = (p['ret1'].abs() > LONCAT).astype(float)
    badc = bad.groupby(p['ticker']).cumsum()
    for h in H:
        if h in (20, 60):
            continue
        f = g.shift(-(1 + h)) / entry - 1
        nb = badc.groupby(p['ticker']).shift(-(1 + h)) - badc.groupby(p['ticker']).shift(-1)
        p['fwd%d' % h] = f.where(nb == 0)
    for h in H:
        lr = np.log1p(p['fwd%d' % h])
        p['b%d' % h] = lr.where(p['elig']).groupby(p['date']).transform('mean')
    return p


def _baris(ev):
    r = {'n': len(ev)}
    for h in H:
        f = ev[ev['fwd%d' % h].notna()]
        if len(f) < 30:
            continue
        lr = np.log1p(f['fwd%d' % h])
        x = lr - f['b%d' % h]
        r['exc%d' % h] = round((np.exp(x.mean()) - 1) * 100, 2)
        r['t%d' % h] = round(uji.t_klaster(x, f['month'].astype(str)), 1)
        r['net%d' % h] = round((np.exp(lr.mean()) - 1 - BIAYA) * 100, 2)
        r['win%d' % h] = round((f['fwd%d' % h] > BIAYA).mean() * 100, 1)
    return r


def main():
    p = _fwd(uji.muat())
    P = uji.pola(p)
    pilih = ['ALL eligible days', 'A2 steady: 30d range <15%', 'C2 C1 + volume >2x',
             'C3 C2 + close near day high', 'D1 new 52w closing high', 'D2 new 52w high + volume >2x',
             'D3 6m return top decile', 'D5 +10% off 20d low (first day)', 'D6 already +20% in 20d',
             'E1 down >40% from 60d peak', 'E4 5-day drop >15%', 'E5 RSI14 <25',
             'E6 -10% off 20d high (first day)', 'F1 volume >3x on strong up-day',
             'F2 volume >3x, price flat (|1d|<2%)']
    sel = uji.sel(p)
    for cel in ('PENCARIAN (separuh A, 2013-2019)', 'VALIDASI (separuh B, 2020-2026)'):
        rows = []
        for k in pilih:
            ev = uji.jeda(p[P[k].fillna(False) & p['elig'] & sel[cel]])
            rows.append(dict(pola=k, **_baris(ev)))
        df = pd.DataFrame(rows).set_index('pola')
        print('\n' + '=' * 100 + '\n' + cel + '\n' + '=' * 100)
        print('selisih vs pasar (%) [t]:')
        print(df[['n'] + ['exc%d' % h for h in H]].to_string())
        print('t (galat baku per bulan):')
        print(df[['t%d' % h for h in H]].to_string())
        print('return majemuk absolut - biaya %.1f%% (%%), dan win%% setelah biaya:' % (BIAYA * 100))
        print(df[['net%d' % h for h in H] + ['win%d' % h for h in (1, 3, 5, 10)]].to_string())

    # kejadian broker dari broker_pasangan.py
    path = os.path.join(RESEARCH_CACHE, 'broker_pasangan_kejadian.pkl')
    if os.path.exists(path):
        with open(path, 'rb') as fh:
            d = pickle.load(fh)
        cols = ['ticker', 'date', 'month'] + ['fwd%d' % h for h in H] + ['b%d' % h for h in H]
        rows = []
        for sem, e in d.items():
            e = e[['ticker', 'date', 'arah', 'definisi']].merge(p[cols], on=['ticker', 'date'], how='inner')
            for (nama, arah), sub in e.groupby(['definisi', 'arah']):
                rows.append(dict(kelompok='%s %s %s' % (sem, arah, nama), **_baris(sub)))
        df = pd.DataFrame(rows).set_index('kelompok')
        print('\n' + '=' * 100 + '\nBROKER beli/jual konsisten 4 minggu\n' + '=' * 100)
        print(df[['n'] + ['exc%d' % h for h in H]].to_string())
        print(df[['t%d' % h for h in H]].to_string())


if __name__ == '__main__':
    main()
