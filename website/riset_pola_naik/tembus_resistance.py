"""
Tembus resistance CHART (level utilities.compute_levels, replika di
chart_support.py). Kerangka uji sama dengan uji.py.

Tembus = close hari t >= 1% di atas resistance terdekat KEMARIN (R).
Varian yang butuh hari-hari sesudah tembus (retest, gagal, bertahan)
dicatat di hari syaratnya terpenuhi, bukan di hari tembus -- jadi tidak
ada yang melihat ke depan.

PEMAKAIAN: python -m website.riset_pola_naik.tembus_resistance
"""
import sys

import numpy as np
import pandas as pd

from . import uji as U
from . import support_volume as SV
from . import chart_support as CS

RETEST_WIN = 10
GAGAL_WIN = 5


def tambah(p):
    p = p.sort_values(['ticker', 'date']).reset_index(drop=True)
    g = p.groupby('ticker', sort=False)
    p['R'] = g['res'].shift(1)
    tembus = p['close'] >= p['R'] * 1.01
    p['t_tembus'] = tembus.astype(float)
    p['t_margin'] = p['close'] / p['R'] - 1

    n = len(p)
    retest = np.zeros(n); gagal = np.zeros(n); tahan = np.zeros(n)
    c = p['close'].to_numpy(float); lo = p['lo_s'].to_numpy(float)
    tk = p['ticker'].to_numpy()
    for b in np.flatnonzero(tembus.to_numpy()):
        R = p.at[b, 'R']
        end = min(n, b + 1 + max(RETEST_WIN, GAGAL_WIN) + 1)
        same = tk[b + 1:end] == tk[b]
        idx = np.arange(b + 1, end)[same]
        # gagal: close balik di bawah R dalam 5 bar
        for j in idx[:GAGAL_WIN]:
            if c[j] < R * 0.99:
                gagal[j] = 1
                break
        else:
            if len(idx) >= GAGAL_WIN:
                tahan[idx[GAGAL_WIN - 1]] = 1
        # retest: turun menyentuh R (+2%), close tak jebol, lalu naik lagi +3%
        disentuh = False
        for j in idx[:RETEST_WIN]:
            if c[j] < R * 0.97:
                break
            if lo[j] <= R * 1.02:
                disentuh = True
            elif disentuh and c[j] >= R * 1.03:
                retest[j] = 1
                break
    p['t_retest'] = retest; p['t_gagal'] = gagal; p['t_tahan5'] = tahan
    return p


def pola(r):
    P = {'ALL eligible days': pd.Series(True, index=r.index)}
    t = r['t_tembus'] == 1
    P['R1 tembus resistance chart (close >=1% di atas)'] = t
    P['R2 R1 + volume >2x'] = t & (r['vspike'] > 2)
    P['R3 R1 + volume >2x + close dekat high'] = t & (r['vspike'] > 2) & (r['day_pos'] > 0.7)
    P['R4 R1 + tak ada resistance lagi di atas'] = t & r['res'].isna()
    P['R5 R1 + resistance berikutnya >=10% di atas'] = t & (r['jarak_res'] >= 0.10)
    P['R6 R1 + di atas MA200'] = t & (r['ma200'] > 0)
    P['R7 R1 + basis tenang 30h (<20%)'] = t & (r['prevrange30'] < 0.20)
    P['R8 R1 tembus tebal (>=3%)'] = t & (r['t_margin'] >= 0.03)
    P['R9 retest: balik sentuh R, tahan, naik lagi'] = r['t_retest'] == 1
    P['R10 gagal tembus: close balik di bawah R <=5 hari'] = r['t_gagal'] == 1
    P['R11 bertahan 5 hari di atas R'] = r['t_tahan5'] == 1
    P['ref: tembus basis 30h + volume >2x (C2 lama)'] = (r['brk30'] == 1) & (r['prevrange30'] < 0.20) & (r['vspike'] > 2)
    return P


def main():
    p = tambah(CS.tambah_kolom(SV.muat()))
    P = pola(p)
    for label, m in U.sel(p).items():
        U.tampil(U.jalankan(p, P, m), label)


if __name__ == '__main__':
    sys.exit(main())
