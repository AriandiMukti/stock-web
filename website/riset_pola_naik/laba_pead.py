"""
Post-earnings announcement drift (PEAD): apakah harga terus bergerak ke arah
kejutan laba SETELAH laporan keuangan terbit?

DATA (ditarik 18 Okt 2026 lewat tab browser idx.co.id -- Python kena 403)
  Angka : API "Financial Data & Ratio" BEI (/primary/DigitalStatistic/
          GetApiDataPaginated?urlName=LINK_FINANCIAL_DATA_RATIO), semua emiten
          per terbitan kuartalan; laporan Sep 2020 - Jun 2026 terisi (terbitan
          2018-2019 kosong/503). Laba = laba ke pemilik entitas induk, KUMULATIF
          sejak awal tahun buku (YTD), miliar rupiah. Hanya tahun buku Desember.
  Tanggal terbit: /primary/ListedCompany/GetFinancialReport (TW1/TW2/TW3/Audit),
          File_Modified lampiran paling awal. Median 32 hari setelah tanggal
          laporan; dibuang kalau > 120 hari (unggah ulang/terlambat).
  Kejutan = (laba YTD - laba YTD periode sama tahun lalu) / ekuitas tahun lalu,
          x1000. Semesta: 273 emiten layak uji.muat() >= 30% hari sejak 2021.
  Berkas: research_cache/idx_bursa/laba_kuartalan_2020-2026.txt
          "KODE:dddFsss,...;"  ddd = hari sejak 1 Jan 2020 (base36),
          F = a (terbit < 16:00 WIB) / b (>= 16:00), sss = kejutan x1000.

DESAIN (didaftar SEBELUM hasil dilihat, 18 Okt 2026)
  Hari reaksi R = hari terbit kalau 'a', hari bursa berikutnya kalau 'b'.
  Masuk di close R. Diukur selisih log vs rata-rata semua emiten tanggal yang
  sama: reaksi (close R-1 -> R) dan drift R -> R+5/20/60.
  Kuintil kejutan = peringkat persentil di dalam KOHORT kuartal kalender
  terbit (laporan Q1 dan tahunan skalanya beda; peringkat menyamakannya).
  Dua periode: terbit s.d. 2023 vs 2024+; t klaster per bulan terbit.
  LOLOS kalau drift Q5 - Q1 (H+20 atau H+60) positif di DUA periode dan
  |t| gabungan >= 2. Strategi beli Q5 hanya kalau Q5 sendiri > +0,4%.

HASIL (18 Okt 2026, 3.476 kejadian terukur, terbit Agu 2021 - Okt 2026): GAGAL.
  Reaksi hari terbit nyata: Q5-Q1 +2,0% (t 3,3), Q1 -1,0% / Q5 +1,4% -- tanda
  tanggal terbitnya benar. Tapi SESUDAH hari reaksi tak ada drift yang
  konsisten: H+20 Q5-Q1 +3,1 (2021-23) lalu -0,5 (2024+), t gabungan 0,8;
  H+60 +5,8 lalu +0,6, t 1,2. Q5 sendiri H+20 -0,3%. Kalau dulu sempat ada
  drift, di 2024+ sudah habis dicerna di hari terbit.
  Batas: cuma ~5 tahun (angka XBRL IDX baru lengkap sejak laporan Sep 2020),
  kejutan diukur vs tahun lalu (bukan vs konsensus analis), 273 emiten likuid.

PEMAKAIAN: python -m website.riset_pola_naik.laba_pead
"""
import os

import numpy as np
import pandas as pd

from . import kalender_bursa as KB
from . import uji as U

BERKAS = os.path.join(KB.DIR, 'laba_kuartalan_2020-2026.txt')
BELAH = pd.Timestamp('2024-01-01')
H = (5, 20, 60)


def baca():
    rows = []
    awal = pd.Timestamp('2020-01-01')
    for blok in open(BERKAS).read().strip().split(';'):
        kode, isi = blok.split(':')
        for e in isi.split(','):
            rows.append({'stock': kode, 'tgl': awal + pd.Timedelta(days=int(e[:3], 36)),
                         'sore': e[3] == 'b', 'kejutan': int(e[4:]) / 1000.0})
    d = pd.DataFrame(rows)
    d['kohort'] = d['tgl'].dt.to_period('Q')
    d['pct'] = d.groupby('kohort')['kejutan'].rank(pct=True)
    d['q'] = np.minimum(5, (d['pct'] * 5).apply(np.ceil)).astype(int)
    return d


def ukur(close, ev):
    lr = np.log(close)
    idx = close.index
    mk = lr.diff().mean(axis=1).fillna(0).cumsum().to_numpy()
    r = close.pct_change().abs()
    out = []
    for e in ev.itertuples():
        if e.stock not in close.columns:
            continue
        i = idx.searchsorted(e.tgl, side='right' if e.sore else 'left')
        if i < 1 or i >= len(idx) or (idx[i] - e.tgl).days > 7:
            continue
        s = lr[e.stock].to_numpy()
        if not (np.isfinite(s[i]) and np.isfinite(s[i - 1])):
            continue
        if (r[e.stock].iloc[i - 1:i + 61] > 0.35).any():
            continue                                     # aksi korporasi tak disesuaikan
        d = {'stock': e.stock, 'tR': idx[i], 'q': e.q, 'kejutan': e.kejutan,
             'reaksi': (s[i] - s[i - 1]) - (mk[i] - mk[i - 1])}
        for h in H:
            j = i + h
            d['x%d' % h] = (s[j] - s[i]) - (mk[j] - mk[i]) if j < len(idx) and np.isfinite(s[j]) else np.nan
        out.append(d)
    return pd.DataFrame(out)


def _beda(sub, k):
    m = sub.groupby([sub['tR'].dt.to_period('M'), 'q'])[k].mean().unstack()
    if 1 not in m or 5 not in m:
        return np.nan, np.nan
    d = (m[5] - m[1]).dropna()
    return d.mean(), d.mean() / (d.std(ddof=1) / np.sqrt(len(d))) if len(d) > 3 else np.nan


def main():
    ev = baca()
    print('kejadian: %d, %d emiten, terbit %s s.d. %s'
          % (len(ev), ev['stock'].nunique(), ev['tgl'].min().date(), ev['tgl'].max().date()))
    close = KB._panel_close()
    d = ukur(close, ev)
    print('terukur: %d' % len(d))
    pd.set_option('display.width', 200)
    for nama, m in (('SEMUA', slice(None)), ('s.d. 2023', d['tR'] < BELAH), ('2024+', d['tR'] >= BELAH)):
        sub = d.loc[m] if not isinstance(m, slice) else d
        t = sub.groupby('q')[['reaksi'] + ['x%d' % h for h in H]].mean().apply(lambda c: (np.exp(c) - 1) * 100)
        t['n'] = sub.groupby('q').size()
        print('\n--- %s (selisih vs pasar, %%; masuk close hari reaksi)' % nama)
        print(t.round(2).to_string())
        print('Q5-Q1: ' + ' | '.join('%s %+.2f (t %.1f)' % ((k,) + tuple(
            (v * 100 if i == 0 else v) for i, v in enumerate(_beda(sub, k)))) for k in ['reaksi'] + ['x%d' % h for h in H]))

    print('\nKRITERIA (drift Q5-Q1 positif dua periode, |t| gabungan >= 2):')
    for k in ('x20', 'x60'):
        a, _ = _beda(d[d['tR'] < BELAH], k)
        b, _ = _beda(d[d['tR'] >= BELAH], k)
        g, t = _beda(d, k)
        ok = a > 0 and b > 0 and abs(t) >= 2
        q5 = d.loc[d['q'] == 5, k].mean()
        print('  %s: P1 %+.2f, P2 %+.2f, gabung %+.2f (t %.1f) -> %s | Q5 sendiri %+.2f%%'
              % (k, a * 100, b * 100, g * 100, t, 'LOLOS' if ok else 'gagal', (np.exp(q5) - 1) * 100))


if __name__ == '__main__':
    main()
