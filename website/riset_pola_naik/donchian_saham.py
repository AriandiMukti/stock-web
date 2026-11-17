"""
Donchian PER SAHAM -- tiap emiten diperdagangkan sendiri, dibandingkan
dengan beli-tahan emiten itu sendiri (29 Okt 2026).

Beda dengan donchian.py (portofolio 10 slot gabungan): di sini satu emiten =
satu akun. Masuk penuh saat sinyal, kas saat tidak pegang, masuk lagi hanya
di sinyal baru sesudah keluar. Dua periode dihitung TERPISAH (mulai kosong,
posisi ditutup paksa di akhir periode): 2013-2019 dan 2020-2026.

Aturan sama dengan donchian.py: sinyal di close t -> beli close t+1; pemicu
keluar di close k -> jual close k+1; sinyal hanya dihitung kalau emiten
layak (uji.muat) hari itu. Ongkos 0,15% beli + 0,25% jual + slippage
0,25%/sisi. Beli-tahan bayar ongkos sekali masuk sekali keluar.
Emiten-periode dengan loncatan >45% sehari dibuang (data rusak / aksi
korporasi), juga yang riwayatnya < 1 tahun di periode itu.

HASIL (29 Okt 2026), emiten dengan >=1 transaksi:
                 untung    >beli-tahan  DD lebih dangkal  hari pegang (median)
    D20/DL10    35%/43%     48%/50%        92%/95%            7%
    D55/DL20    42%/41%     48%/47%        96%/95%            7%
    D55/TS10    41%/47%     50%/51%        96%/98%          3-5%
    D250/TS10   47%/46%     44%/46%       100%/99%          1-2%
    (2013-19 / 2020-26; ~210-260 emiten di periode 1, 500-600 di periode 2)
- Per saham, untung vs beli-tahan = lempar koin; median CAGR strategi ~-1%
  karena 93-99% hari duduk di kas -- satu emiten jarang memberi sinyal.
  Yang hampir pasti: drawdown jauh lebih dangkal.
- "Bagus" (untung DAN > beli-tahan) di 2013-19 -> bagus lagi di 2020-26:
  D20/DL10 40% vs 27% (dulu jelek), 17 emiten vs 12,9 kalau kebetulan;
  D250/TS10 34% vs 20%, 12 vs 8,1; D55/DL20 dan D55/TS10 ~ kebetulan.
  Dua dari empat aturan ada tanda lemah, jumlahnya kecil (35-48 emiten).
- MLPL muncul di keempat aturan (untung & > beli-tahan dua periode).

KELUARAN: donchian_per_saham.csv di folder ini, satu baris per emiten x
periode x aturan.

PEMAKAIAN (dari <project>/)
    python -m website.riset_pola_naik.donchian_saham
"""
try:
    from ..runtime_paths import runtime_file as _runtime_file, market_file as _market_file, WEBSITE_DIR as _WEBSITE_DIR, PROJECT_DIR as _PROJECT_DIR, RUNTIME_DIR as _RUNTIME_DIR
except ImportError:
    from website.runtime_paths import runtime_file as _runtime_file, market_file as _market_file, WEBSITE_DIR as _WEBSITE_DIR, PROJECT_DIR as _PROJECT_DIR, RUNTIME_DIR as _RUNTIME_DIR
import os

import numpy as np
import pandas as pd

from . import donchian as DN
from . import uji

ATURAN = {'D20/DL10': (20, 'dl', 10, 250), 'D55/DL20': (55, 'dl', 20, 250),
          'D55/TS10': (55, 'ts', 0.10, 120), 'D250/TS10': (250, 'ts', 0.10, 120)}
PERIODE = {'2013-19': ('2013-01-01', '2019-12-31'), '2020-26': ('2020-01-01', '2026-12-31')}
BELI, JUAL = 0.0015 + 0.0025, 0.0025 + 0.0025
KELUAR_CSV = str(_runtime_file('riset_pola_naik', 'donchian_per_saham.csv'))


def jalan(c, brk, elig, lo, jenis, x, maks):
    """Kurva ekuitas harian (mulai 1), return per transaksi, porsi hari pegang."""
    n = len(c)
    eq = np.ones(n)
    kas, lembar, masuk_i, puncak, tunggu_beli, tunggu_jual = 1.0, 0.0, -1, 0.0, False, False
    tx = []
    pegang = 0
    for k in range(n):
        if tunggu_jual:
            kas = lembar * c[k] * (1 - JUAL)
            tx.append(kas / modal - 1)
            lembar, masuk_i, tunggu_jual = 0.0, -1, False
        elif tunggu_beli:
            modal = kas
            lembar = kas * (1 - BELI) / c[k]
            kas, masuk_i, puncak, tunggu_beli = 0.0, k, c[k], False
        eq[k] = kas + lembar * c[k]
        if lembar > 0:
            pegang += 1
            puncak = max(puncak, c[k])
            if k > masuk_i:
                if jenis == 'ts':
                    kena = c[k] <= (1 - x) * puncak
                else:
                    kena = np.isfinite(lo[k]) and c[k] < lo[k]
                if kena or k - masuk_i >= maks:
                    tunggu_jual = True
        elif brk[k] and elig[k]:
            tunggu_beli = True
    if lembar > 0:                         # tutup paksa di akhir periode
        kas = lembar * c[-1] * (1 - JUAL)
        tx.append(kas / modal - 1)
        eq[-1] = kas
    return eq, np.array(tx), pegang / n


def cagr(nilai_akhir, hari):
    th = hari / 365.25
    return (nilai_akhir ** (1 / th) - 1) * 100 if nilai_akhir > 0 else -100.0


def dd(kurva):
    return (kurva / np.maximum.accumulate(kurva) - 1).min() * 100


def main():
    p = uji.muat()
    p, low = DN.kanal(p)
    rows = []
    for t, d in p.groupby('ticker', sort=False):
        d = d.sort_values('hist')
        for np_, (a, b) in PERIODE.items():
            s = d[(d['date'] >= a) & (d['date'] <= b)]
            if len(s) < 250 or not s['elig'].any():
                continue
            if (s['ret1'].abs().iloc[1:] > 0.45).any():
                continue
            c = s['close'].to_numpy(float)
            hist = s['hist'].to_numpy(int)
            elig = s['elig'].to_numpy(bool)
            hari = (s['date'].iloc[-1] - s['date'].iloc[0]).days
            bh = c / c[0]
            bh_akhir = bh[-1] * (1 - BELI) * (1 - JUAL)
            for na, (N, jenis, x, maks) in ATURAN.items():
                brk = s['brk%d' % N].to_numpy(bool)
                lo = low[t][x][hist] if jenis == 'dl' else None
                eq, tx, pg = jalan(c, brk, elig, lo, jenis, x, maks)
                rows.append({'ticker': t, 'periode': np_, 'aturan': na, 'transaksi': len(tx),
                             'win%': round((tx > 0).mean() * 100, 0) if len(tx) else np.nan,
                             'CAGR strategi%': round(cagr(eq[-1], hari), 1),
                             'CAGR beli-tahan%': round(cagr(bh_akhir, hari), 1),
                             'DD strategi%': round(dd(eq), 1), 'DD beli-tahan%': round(dd(bh), 1),
                             'hari pegang%': round(pg * 100, 0)})
    df = pd.DataFrame(rows)
    df['selisih%'] = (df['CAGR strategi%'] - df['CAGR beli-tahan%']).round(1)
    df.to_csv(KELUAR_CSV, index=False)
    print('tersimpan: %s (%d baris, %d emiten)' % (KELUAR_CSV, len(df), df['ticker'].nunique()))

    pd.set_option('display.width', 220)
    for na in ATURAN:
        x = df[df['aturan'] == na]
        print('\n' + '=' * 100 + '\n' + na + '\n' + '=' * 100)
        for np_ in PERIODE:
            y = x[(x['periode'] == np_) & (x['transaksi'] > 0)]
            print('%s: %d emiten | strategi untung %d (%.0f%%) | ngalahin beli-tahan %d (%.0f%%) | '
                  'DD lebih dangkal %d (%.0f%%) | median CAGR strategi %.1f vs beli-tahan %.1f'
                  % (np_, len(y), (y['CAGR strategi%'] > 0).sum(), (y['CAGR strategi%'] > 0).mean() * 100,
                     (y['selisih%'] > 0).sum(), (y['selisih%'] > 0).mean() * 100,
                     (y['DD strategi%'] > y['DD beli-tahan%']).sum(),
                     (y['DD strategi%'] > y['DD beli-tahan%']).mean() * 100,
                     y['CAGR strategi%'].median(), y['CAGR beli-tahan%'].median()))
        w = x.pivot(index='ticker', columns='periode', values=['CAGR strategi%', 'selisih%', 'transaksi']).dropna()
        w = w[(w[('transaksi', '2013-19')] > 0) & (w[('transaksi', '2020-26')] > 0)]
        a, b = w[('CAGR strategi%', '2013-19')], w[('CAGR strategi%', '2020-26')]
        sa, sb = w[('selisih%', '2013-19')], w[('selisih%', '2020-26')]
        print('emiten ada di dua periode: %d' % len(w))
        print('  untung di 2013-19 -> untung juga di 2020-26: %d dari %d (%.0f%%) | yang rugi di 2013-19 -> untung di 2020-26: %.0f%%'
              % (((a > 0) & (b > 0)).sum(), (a > 0).sum(), ((b > 0) & (a > 0)).sum() / max((a > 0).sum(), 1) * 100,
                 ((b > 0) & (a <= 0)).sum() / max((a <= 0).sum(), 1) * 100))
        print('  ngalahin beli-tahan 2013-19 -> ngalahin lagi 2020-26: %d dari %d (%.0f%%) | yang kalah dulu -> ngalahin: %.0f%%'
              % (((sa > 0) & (sb > 0)).sum(), (sa > 0).sum(), ((sb > 0) & (sa > 0)).sum() / max((sa > 0).sum(), 1) * 100,
                 ((sb > 0) & (sa <= 0)).sum() / max((sa <= 0).sum(), 1) * 100))
        print('  rho Spearman CAGR strategi antar periode %.2f | selisih vs beli-tahan %.2f'
              % (a.rank().corr(b.rank()), sa.rank().corr(sb.rank())))
        dua = w[(a > 0) & (b > 0) & (sa > 0) & (sb > 0)]
        print('  untung DAN ngalahin beli-tahan di DUA periode: %d emiten' % len(dua))
        top = dua.assign(min_cagr=np.minimum(dua[('CAGR strategi%', '2013-19')], dua[('CAGR strategi%', '2020-26')]))
        top = top.sort_values('min_cagr', ascending=False).head(15)
        print(pd.DataFrame({'CAGR 13-19': top[('CAGR strategi%', '2013-19')], 'CAGR 20-26': top[('CAGR strategi%', '2020-26')],
                            'vs B&H 13-19': top[('selisih%', '2013-19')], 'vs B&H 20-26': top[('selisih%', '2020-26')],
                            'tx 13-19': top[('transaksi', '2013-19')], 'tx 20-26': top[('transaksi', '2020-26')]}).T.to_string())


if __name__ == '__main__':
    main()
