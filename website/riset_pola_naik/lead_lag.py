"""
Lead-lag dalam sektor: saham BESAR bergerak duluan, saham KECIL sesektor
menyusul? (ide Hou 2007: perhatian investor terbatas, berita sektor dicerna
dulu di saham yang paling ramai diikuti.)

DESAIN (didaftar SEBELUM hasil dilihat, 18 Okt 2026)
Semesta: emiten layak uji.muat() (median nilai >= Rp1M, harga >= 100,
diperdagangkan >= 90%, tanpa loncatan data), sektor IDX-IC dari profil
registri (peta_sektor -- sektor HARI INI, emiten pindah sektor tak tertangkap).
Per (tanggal, sektor):
    besar = 3 emiten dengan median nilai transaksi 20h tertinggi
    kecil = emiten di bawah median nilai sektor itu (bukan besar)
    syarat >= 3 besar dan >= 3 kecil
Sinyal G_k = rata2 return k hari BESAR - rata2 return k hari KECIL (k = 1, 5):
"celah" yang belum disusul saham kecil. Utama: G5.
Target (per saham kecil, selisih log vs semua emiten layak hari yang sama):
    f1  close t -> close t+1    (teoretis: masuk di close hari sinyal)
    f5  close t+1 -> close t+6  (bisa diambil: masuk close besoknya, sama dgn uji.py)
Kuintil G memakai batas dari 2013-2019 untuk dua periode. Sel = belahan
emiten (md5, uji.py) x periode; t-stat dari rata2 bulanan Q5-Q1.

LOLOS hanya kalau G5 -> f5: Q5-Q1 positif di 4 sel, t > 2 di tiap periode
(dua belahan digabung), DAN tetap positif di ketiga tertil momentum 5 hari
saham kecil itu sendiri (bukan sekadar "saham kecil yang tertinggal mantul").
Layak jadi strategi beli cuma kalau Q5 sendiri > +0,4% (biaya pulang-pergi).

HASIL (18 Okt 2026, 760 emiten layak, 224 rb saham-kecil-hari, 11 sektor): GAGAL.
  G5 -> f5 Q5-Q1: +0,17/+0,07 (2013-19), +0,03/-0,12 (2020-26), t 1,0 / -0,5;
  Q5 absolut -0,11% (P1) -- jauh dari ambang +0,4%. Kontrol momentum bolak-balik
  tanda (P2 tertil 1 -0,36, t -2,3). Teoretis H+1 (G1 -> f1) malah sedikit
  TERBALIK di 2020-26 (-0,05, t -2,1): celah kemarin tidak disusul, kalau ada
  justru mantul. Subsektor (22 grup, sekunder): sama-sama gagal, Q5 -0,18%.
  Bacaan: di BEI saham kecil sesektor tidak "menyusul" saham besar dalam
  hitungan hari -- arus informasi antar-saham sudah cepat, atau saham kecil
  digerakkan hal lain (bandar/ritel) daripada berita sektor.

PEMAKAIAN: python -m website.riset_pola_naik.lead_lag [sektor|subsektor]
"""
import glob
import json
import os
import sys

import numpy as np
import pandas as pd

from . import uji as U

BATAS_DISCOVERY = '2020-01-01'


def peta(kolom):
    from ..ownership import IDX_DIR
    out = {}
    for f in glob.glob(os.path.join(IDX_DIR, '*', '*.json')):
        try:
            j = json.load(open(f, encoding='utf-8'))
        except Exception:
            continue
        if j.get(kolom):
            out[j['ticker']] = j[kolom]
    return out


def siapkan(kolom='sector'):
    p = U.muat()
    p = p.sort_values(['ticker', 'date'])
    g = p.groupby('ticker', sort=False)['close']
    p['r1'] = g.pct_change()
    p['r5'] = g.pct_change(5)
    p['f1'] = g.shift(-1) / p['close'] - 1
    p['f5'] = g.shift(-6) / g.shift(-1) - 1
    # loncatan data (|gerak 1 hari| > 45%) di jendela mana pun -> buang
    loncat = (p['r1'].abs() > 0.45).astype(float)
    lg = loncat.groupby(p['ticker'])
    p.loc[lg.shift(-1).fillna(1) > 0, 'f1'] = np.nan
    ke_depan = sum(lg.shift(-k).fillna(1) for k in range(1, 7))
    p.loc[ke_depan > 0, 'f5'] = np.nan
    p.loc[lg.transform(lambda s: s.rolling(5, min_periods=1).max()) > 0, ['r1', 'r5']] = np.nan

    p = p[p['elig']].copy()
    for f in ('f1', 'f5'):
        lr = np.log1p(p[f])
        p['x' + f] = lr - lr.groupby(p['date']).transform('mean')

    p['grup'] = p['ticker'].map(peta(kolom))
    p = p[p['grup'].notna()].copy()
    rk = p.groupby(['date', 'grup'])['medval20'].rank(ascending=False, method='first')
    med = p.groupby(['date', 'grup'])['medval20'].transform('median')
    p['besar'] = rk <= 3
    p['kecil'] = (p['medval20'] < med) & ~p['besar']

    agg = {}
    for nama, m in (('B', p['besar']), ('K', p['kecil'])):
        a = p[m].groupby(['date', 'grup']).agg(r1=('r1', 'mean'), r5=('r5', 'mean'), n=('r1', 'size'))
        agg[nama] = a.add_prefix(nama + '_')
    sg = agg['B'].join(agg['K'], how='inner')
    sg = sg[(sg['B_n'] >= 3) & (sg['K_n'] >= 3)]
    sg['G1'] = sg['B_r1'] - sg['K_r1']
    sg['G5'] = sg['B_r5'] - sg['K_r5']

    k = p[p['kecil']].merge(sg[['G1', 'G5']], left_on=['date', 'grup'], right_index=True)
    print('saham kecil-hari: %d | sektor-hari: %d | grup: %d'
          % (len(k), len(sg), k['grup'].nunique()), flush=True)
    return k


def _kuintil(k, sinyal):
    d = k[k['date'] < BATAS_DISCOVERY][sinyal].dropna()
    batas = np.quantile(d, [0.2, 0.4, 0.6, 0.8])
    return np.digitize(k[sinyal], batas) + 1


def _t_bulanan(sub, target):
    m = sub.groupby([sub['month'], sub['q']])[target].mean().unstack()
    if 1 not in m or 5 not in m:
        return np.nan, np.nan
    d = (m[5] - m[1]).dropna()
    if len(d) < 6:
        return np.nan, np.nan
    return d.mean(), d.mean() / (d.std(ddof=1) / np.sqrt(len(d)))


def laporan(k, sinyal, target):
    k = k[k[sinyal].notna() & k[target].notna()].copy()
    k['q'] = _kuintil(k, sinyal)
    print('\n%s -> %s (selisih log vs pasar, %%; Q5-Q1 dan t dari rata2 bulanan)' % (sinyal, target))
    print('sel              Q1      Q2      Q3      Q4      Q5    Q5-Q1     t      n')
    hasil = {}
    for per in (1, 2):
        for half in (0, 1, None):
            sub = k[(k['period'] == per) & ((k['half'] == half) if half is not None else True)]
            q = sub.groupby('q')[target].mean() * 100
            d, t = _t_bulanan(sub, target)
            nama = 'P%d %s' % (per, ('belahan %d' % half) if half is not None else 'gabung   ')
            print('%-14s %s  %+6.3f  %5.1f  %7d'
                  % (nama, ' '.join('%+7.3f' % q.get(i, np.nan) for i in range(1, 6)),
                     d * 100, t, len(sub)))
            hasil[(per, half)] = (d, t, q.get(5, np.nan))
    return hasil


def kontrol_momentum(k, sinyal, target):
    k = k[k[sinyal].notna() & k[target].notna() & k['r5'].notna()].copy()
    k['q'] = _kuintil(k, sinyal)
    k['ter'] = k.groupby('date')['r5'].transform(lambda s: pd.qcut(s.rank(method='first'), 3, labels=False))
    print('\nKontrol momentum 5h saham kecil sendiri (%s -> %s), Q5-Q1 %%:' % (sinyal, target))
    ok = True
    for per in (1, 2):
        baris = []
        for ter in (0, 1, 2):
            sub = k[(k['period'] == per) & (k['ter'] == ter)]
            d, t = _t_bulanan(sub, target)
            baris.append('tertil %d: %+6.3f (t %4.1f)' % (ter + 1, d * 100, t))
            ok &= bool(d > 0)
        print('  P%d  %s' % (per, ' | '.join(baris)))
    return ok


def main():
    kolom = 'sub_sector' if (len(sys.argv) > 1 and sys.argv[1] == 'subsektor') else 'sector'
    print('Grup: %s' % kolom)
    k = siapkan(kolom)
    for s, t in (('G1', 'xf1'), ('G5', 'xf1'), ('G1', 'xf5')):
        laporan(k, s, t)
    utama = laporan(k, 'G5', 'xf5')
    ok_mom = kontrol_momentum(k, 'G5', 'xf5')

    k4 = all(utama[(per, h)][0] > 0 for per in (1, 2) for h in (0, 1))
    kt = all(utama[(per, None)][1] > 2 for per in (1, 2))
    q5 = min(utama[(per, None)][2] for per in (1, 2))
    print('\nKriteria G5->f5: positif 4 sel: %s | t>2 dua periode: %s | tahan kontrol momentum: %s'
          % (k4, kt, ok_mom))
    print('VONIS: %s' % ('LOLOS' if (k4 and kt and ok_mom) else 'GAGAL'))
    print('Q5 terendah antar periode: %+.3f%% (ambang strategi beli +0,4%%)' % q5)


if __name__ == '__main__':
    main()
