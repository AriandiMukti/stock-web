"""
Sepi dibahas vs ramai dibahas -- arsip Telegram 2018-2026. (27 Okt 2026)

KENAPA
Menu /ramai-dibahas cuma melihat yang ramai. Bacaan pertamanya: ramai ~
ukuran + gerak harga (R2 0,53), jadi "sepi vs ramai" mentah cuma mengulang
efek ukuran. Yang ditanya di sini SEPI RELATIF: saham yang dari ukuran &
geraknya mestinya diobrolkan, tapi tidak. Literatur atensi: yang ramai
diborong ritel lalu kalah; yang terabaikan bereaksi telat (drift lebih
panjang). Petunjuk lokal: Top-30 ramai nol irisan dengan Tembus Basis.

DATA
Dua grup Telegram (riset_sentimen_obrolan/tg_hist): kelompok riset A
Feb 2018 - Okt 2026, kelompok riset B Sep 2021 - Okt 2026, ~625 ribu pesan.
Sebutan = pesan yang memuat ticker (pencocok ramai_dibahas: $/# atau kata
4 huruf, minus AMBIGU); pesan yang menyebut > 5 emiten dibuang (rekap).
Ticker yang huruf kecilnya >2,5x huruf besarnya (AMIN, ARTI, EURO, ...)
cuma dihitung kalau ditulis besar / ber-tag. Hari = hari bursa pesan
(>=16:00 / libur -> hari bursa berikutnya), sama dengan sentimen.py.

DESAIN (didaftar SEBELUM hasil dilihat)
- men20 = jumlah sebutan 20 hari bursa terakhir (sampai & termasuk t).
- Sepi relatif: tiap hari, di antara emiten layak (uji.py), regresi lintas
  emiten log1p(men20) ~ log medval20 + |r5| + |r20| + r20 + log vspike +
  vol20. sisa = residual; sisa rendah = lebih sepi dari yang diharapkan.
- Uji 1 (Fama-MacBeth): tiap 20 hari bursa (tak tumpang-tindih), regresi
  lintas emiten selisih log fwd20 (vs pembanding hari yang sama) ~ zsisa +
  kontrol yang sama. Koefisien zsisa dirata-rata, t dari deret waktu.
  Juga kuintil sisa (Q1 paling sepi) sebagai deskripsi.
- Uji 2 (sepi tapi likuid): emiten layak di 30% teratas medval20 dengan
  men20 = 0 vs men20 >= 1 di kelompok likuid yang sama.
- Uji 3 (Tembus Basis): sinyal menu (tembus basis + vol ATAU puncak 52 mgg
  + vol, persis gabungan.py), satu per emiten per 20 bar. Dibelah sisa <= 0
  (sepi) vs > 0 (ramai), juga men20 = 0 vs >= 1. Hasil: fwd20/fwd60 vs
  pembanding hari yang sama, dan transaksi TS10 (keluar.py).
- Sel: PILIH = separuh emiten A x Mar 2018 - Des 2021; UJI = separuh B x
  Jan 2022 - Jul 2026. PILIH praktis cuma kelompok riset A (cakupan kelompok lain berbeda).

KRITERIA (ditulis sebelum hasil)
- Sepi relatif BERGUNA kalau koefisien zsisa NEGATIF (lebih sepi -> lebih
  untung) dengan t <= -2 di UJI dan bertanda sama di PILIH.
- Untuk Tembus Basis, sepi MEMBANTU kalau subset sepi mengalahkan subset
  ramai di fwd60 vs pasar DAN di TS10 vs pasar/tx, di PILIH dan UJI, dengan
  t selisih >= 2 di UJI. Kalau cuma satu sel: "belum jelas".

BATAS
- Dua grup bukan seluruh pasar; nol sebutan di dua grup != nol di Stockbit.
- Survivorship Yahoo seperti riset lain.

PEMAKAIAN: python -m website.riset_pola_naik.sepi_dibahas   (dari <project>/)
Cache sebutan: research_cache/sepi_dibahas_sebutan.pkl (hapus untuk hitung ulang).

HASIL (27 Okt 2026) -- GAGAL di semua uji
=========================================
Data: 400 ribu pesan unik (pkl berisi duplikat id), 59 ribu memuat ticker,
64 ribu sebutan. 57% emiten-hari layak nol sebutan 20 hari; di 30% teratas
likuiditas pun 34% nol. R2 harian atensi ~ kontrol cuma 0,31 (Stockbit
jepretan 15 Okt: 0,53).

1. Sepi relatif (Fama-MacBeth, fwd20): koef zsisa +0,05 (t 0,2) PILIH,
   -0,05 (t -0,2) UJI; silang -0,19 / +0,14. Kuintil tak monoton, Q1-Q5
   -0,1 s.d. -0,6% (t <= 0,9). fwd60 sama: nihil. GAGAL.
2. Sepi tapi likuid (men20=0 di 30% teratas): +1,83% (t 1,6) PILIH,
   -0,22% (t -0,3) UJI. GAGAL.
3. Tembus Basis (TS10 vs pasar/tx):
     sisa<=0 vs >0 : PILIH 2,62 vs 2,45 | UJI 2,59 vs 4,77 (t -1,4)
                     silang 1,79 vs 5,88 (t -2,1) / 1,98 vs 3,10
     men20=0 vs >=1: PILIH 2,94 vs 2,01 | UJI 4,28 vs 3,03 (t 0,7)
   Sepi relatif TIDAK membantu -- kalau ada arah, yang ramai relatif
   sedikit lebih baik (3 dari 4 sel). Nol sebutan mentah condong lebih
   baik tapi t <= 1,1. Tembus Basis sendiri tetap untung di kedua belahan
   (t 2-4): edge-nya tidak bergantung atensi.

Pemeriksaan proksi: sebutan Telegram 18 Sep-16 Okt vs total Stockbit
15-16 Okt, Spearman cuma 0,35; 165 dari 253 emiten dgn >=10 post Stockbit
nol di dua grup ini. Jadi "sepi" versi arsip ini kasar -- hasil nihil bisa
sebagian karena ukurannya berisik. Uji yang lebih tajam butuh jurnal
Stockbit harian (ramai_dibahas_harian.csv) yang juga mencatat yang nol.
"""
try:
    from ..runtime_paths import runtime_file as _runtime_file, market_file as _market_file, WEBSITE_DIR as _WEBSITE_DIR, PROJECT_DIR as _PROJECT_DIR, RUNTIME_DIR as _RUNTIME_DIR
except ImportError:
    from website.runtime_paths import runtime_file as _runtime_file, market_file as _market_file, WEBSITE_DIR as _WEBSITE_DIR, PROJECT_DIR as _PROJECT_DIR, RUNTIME_DIR as _RUNTIME_DIR
import os
import re
import sys
import time
import warnings

import numpy as np
import pandas as pd

from . import uji
from .keluar import siapkan, transaksi, ringkas_tx
from ..ramai_dibahas import AMBIGU, POLA_TAG

warnings.filterwarnings('ignore')
HERE = os.path.dirname(os.path.abspath(__file__))
TG = str(_runtime_file('', 'riset_sentimen_obrolan', 'tg_hist'))
from ..runtime_paths import research_groups
GRUP = [row['archive'] for row in research_groups()]
CACHE = str(_runtime_file('', 'research_cache', 'sepi_dibahas_sebutan.pkl'))
POLA_POLOS = re.compile(r'(?<![A-Za-z0-9$#])([A-Za-z]{4})(?![A-Za-z0-9])')
MAKS_TAG = 5
RASIO_KECIL = 2.5
MULAI = '2018-03-01'
KONTROL = ['lmv', 'ar5', 'ar20', 'r20', 'lvs', 'vol20']


def _ticker(teks, semesta, cuma_besar):
    hasil = []
    for m in POLA_TAG.finditer(teks):
        t = m.group(1).upper()
        if t in semesta:
            hasil.append(t)
    for m in POLA_POLOS.finditer(teks):
        w = m.group(1); t = w.upper()
        if t in semesta and t not in AMBIGU and (w.isupper() or t not in cuma_besar):
            hasil.append(t)
    return list(dict.fromkeys(hasil))


def sebutan(semesta, kal):
    """DataFrame (ticker, D, n) -- jumlah pesan yang menyebut emiten per hari bursa."""
    if os.path.exists(CACHE):
        return pd.read_pickle(CACHE)
    sys.path.insert(0, str(_runtime_file('', 'riset_sentimen_obrolan')))
    from sentimen import hari_bursa
    pesan = []
    for g in GRUP:
        d = pd.read_pickle(str(_runtime_file('riset_sentimen_obrolan/tg_hist', g + '.pkl'))).drop_duplicates('id')
        d['waktu'] = pd.to_datetime(d.waktu, utc=True).dt.tz_convert('Asia/Jakarta').dt.tz_localize(None)
        d['grup'] = g
        pesan.append(d[['grup', 'waktu', 'teks']])
    d = pd.concat(pesan, ignore_index=True)
    d['teks'] = d['teks'].astype(str)

    # ticker yang huruf kecilnya lebih sering dari wajar = kata biasa (amin, arti, euro, ...)
    besar, kecil = {}, {}
    for teks in d['teks']:
        for m in POLA_POLOS.finditer(teks):
            w = m.group(1); t = w.upper()
            if t in semesta and t not in AMBIGU:
                if w.isupper():
                    besar[t] = besar.get(t, 0) + 1
                else:
                    kecil[t] = kecil.get(t, 0) + 1
    cuma_besar = {t for t, k in kecil.items() if k > RASIO_KECIL * (besar.get(t, 0) + 1)}
    print('ticker dihitung huruf besar saja: %s' % ' '.join(sorted(cuma_besar)), flush=True)

    d['tk'] = [_ticker(x, semesta, cuma_besar) for x in d['teks']]
    d = d[d['tk'].map(len).between(1, MAKS_TAG)]
    d['D'] = hari_bursa(d['waktu'], pd.Series(kal))
    e = d[['D', 'tk']].explode('tk').dropna()
    out = e.groupby(['tk', 'D']).size().rename('n').reset_index().rename(columns={'tk': 'ticker'})
    out.to_pickle(CACHE)
    return out


def siapkan_panel():
    p = uji.muat()
    g = p.groupby('ticker', sort=False)['close']
    p['r5'] = g.pct_change(5)
    p['r20'] = g.pct_change(20)
    kal = pd.DatetimeIndex(sorted(p['date'].unique()))
    s = sebutan(set(p['ticker'].unique()), kal)
    p = p.merge(s.rename(columns={'D': 'date'}), on=['ticker', 'date'], how='left')
    p['n'] = p['n'].fillna(0)
    p = p.sort_values(['ticker', 'date']).reset_index(drop=True)
    p['men20'] = p.groupby('ticker', sort=False)['n'].transform(lambda x: x.rolling(20, min_periods=20).sum())
    p['lmv'] = np.log(p['medval20'].clip(lower=1))
    p['ar5'] = p['r5'].abs(); p['ar20'] = p['r20'].abs()
    p['lvs'] = np.log(p['vspike'].clip(lower=0.05))
    p['y'] = np.log1p(p['men20'])
    p['ex20'] = np.log1p(p['fwd20']) - p['b_lr20']
    p['ex60'] = np.log1p(p['fwd60']) - p['b_lr60']
    p = p[(p['date'] >= MULAI)].reset_index(drop=True)
    return p, s


def _ols(y, X):
    X = np.column_stack([np.ones(len(X)), X])
    b, *_ = np.linalg.lstsq(X, y, rcond=None)
    return b, y - X @ b


def hitung_sisa(p):
    """Residual atensi lintas emiten per hari (emiten layak saja)."""
    p['sisa'] = np.nan
    m = p['elig'] & p[['y'] + KONTROL].notna().all(axis=1) & np.isfinite(p[KONTROL]).all(axis=1)
    q = p[m]
    out = pd.Series(np.nan, index=q.index)
    for _, d in q.groupby('date'):
        if len(d) < 50:
            continue
        _, e = _ols(d['y'].to_numpy(float), d[KONTROL].to_numpy(float))
        out[d.index] = (e - e.mean()) / (e.std() or 1)
    p.loc[out.index, 'sisa'] = out
    return p


def sel(p):
    return {
        'PILIH A 18-21': (p['half'] == 0) & (p['date'] < '2022-01-01'),
        'UJI B 22-26': (p['half'] == 1) & (p['date'] >= '2022-01-01'),
        'silang B 18-21': (p['half'] == 1) & (p['date'] < '2022-01-01'),
        'silang A 22-26': (p['half'] == 0) & (p['date'] >= '2022-01-01'),
    }


def deskripsi(p):
    """Seberapa jauh atensi dijelaskan ukuran & gerak (R2 lintas emiten)."""
    q = p[p['elig'] & p['sisa'].notna()]
    r2 = []
    for _, d in q.groupby('date'):
        y = d['y'].to_numpy(float)
        _, e = _ols(y, d[KONTROL].to_numpy(float))
        r2.append(1 - e.var() / y.var() if y.var() > 0 else np.nan)
    print('\nemiten-hari layak dgn sisa: %d | median R2 harian atensi~kontrol: %.2f | porsi men20=0: %.0f%%'
          % (len(q), np.nanmedian(r2), (q['men20'] == 0).mean() * 100))
    lik = q[q.groupby('date')['medval20'].rank(pct=True) >= 0.7]
    print('di 30%% teratas likuiditas, porsi men20=0: %.0f%%' % ((lik['men20'] == 0).mean() * 100))


def fama_macbeth(p, mask, kol='ex20', langkah=20):
    q = p[mask & p['elig'] & p['sisa'].notna() & p[kol].notna()]
    tanggal = sorted(q['date'].unique())[::langkah]
    kf, kuin = [], []
    for t in tanggal:
        d = q[q['date'] == t]
        if len(d) < 30:
            continue
        b, _ = _ols(d[kol].to_numpy(float), d[['sisa'] + KONTROL].to_numpy(float))
        kf.append(b[1])
        k = pd.qcut(d['sisa'].rank(method='first'), 5, labels=False)
        kuin.append(d.groupby(k)[kol].mean().to_numpy())
    kf = np.array(kf); kuin = np.array(kuin)
    t = kf.mean() / (kf.std(ddof=1) / np.sqrt(len(kf)))
    sp = kuin[:, 0] - kuin[:, 4]
    return {'tanggal': len(kf),
            'koef zsisa (%/sd)': round((np.exp(kf.mean()) - 1) * 100, 2), 't': round(t, 1),
            **{'Q%d' % (i + 1): round((np.exp(kuin[:, i].mean()) - 1) * 100, 2) for i in range(5)},
            'Q1-Q5': round((np.exp(sp.mean()) - 1) * 100, 2),
            't Q1-Q5': round(sp.mean() / (sp.std(ddof=1) / np.sqrt(len(sp))), 1)}


def likuid_nol(p, mask, langkah=20):
    q = p[mask & p['elig'] & p['men20'].notna() & p['ex20'].notna()].copy()
    q = q[q.groupby('date')['medval20'].rank(pct=True) >= 0.7]
    tanggal = set(sorted(q['date'].unique())[::langkah])
    q = q[q['date'].isin(tanggal)]
    q['nol'] = q['men20'] == 0
    per = q.groupby(['date', 'nol'])['ex20'].mean().unstack().dropna()
    sp = per[True] - per[False]
    return {'tanggal': len(per), 'n nol/hari': round(q[q.nol].groupby('date').size().mean(), 0),
            'nol': round((np.exp(per[True].mean()) - 1) * 100, 2),
            'disebut': round((np.exp(per[False].mean()) - 1) * 100, 2),
            'selisih': round((np.exp(sp.mean()) - 1) * 100, 2),
            't': round(sp.mean() / (sp.std(ddof=1) / np.sqrt(len(sp))), 1)}


def _beda(a, b, kol, bulan_kol):
    """Selisih rata-rata a-b dengan galat baku klaster per bulan (gabungan)."""
    import statsmodels.api as sm
    x = pd.concat([a.assign(g=1), b.assign(g=0)])
    x = x[x[kol].notna()]
    if x['g'].sum() < 20 or (1 - x['g']).sum() < 20:
        return np.nan, np.nan
    r = sm.OLS(x[kol].to_numpy(float), sm.add_constant(x['g'].to_numpy(float))).fit(
        cov_type='cluster', cov_kwds={'groups': pd.factorize(x[bulan_kol].astype(str))[0]})
    return r.params[1], r.tvalues[1]


def tembus_basis(p, per, pasar):
    basis = (p['brk30'] == 1) & (p['prevrange30'] < 0.20) & (p['vspike'] > 2)
    puncak = (p['hi250'] == 1) & (p['vspike'] > 2)
    m = (basis | puncak).fillna(False) & p['elig'] & p['sisa'].notna()
    rows, ts = [], []
    for ns, s in sel(p).items():
        ev = uji.jeda(p[m & s])
        for nb, a_m in (('sisa<=0 vs >0', ev['sisa'] <= 0), ('men20=0 vs >=1', ev['men20'] == 0)):
            a, b = ev[a_m], ev[~a_m]
            r = {'sel': ns, 'belah': nb, 'n sepi': len(a), 'n ramai': len(b)}
            for kol in ('ex20', 'ex60'):
                _, t = _beda(a, b, kol, 'month')
                r[kol + ' sepi%'] = round((np.exp(a[kol].mean()) - 1) * 100, 2)
                r[kol + ' ramai%'] = round((np.exp(b[kol].mean()) - 1) * 100, 2)
                r['t ' + kol] = round(t, 1)
            ta, tb = transaksi(a, per, pasar, 'TS10'), transaksi(b, per, pasar, 'TS10')
            _, t = _beda(ta, tb, 'lebih', 'bulan')
            r['TS10 sepi%/tx'] = ringkas_tx(ta).get('vs pasar/tx%')
            r['TS10 ramai%/tx'] = ringkas_tx(tb).get('vs pasar/tx%')
            r['t TS10'] = round(t, 1)
            rows.append(r)
            for nama, tx in (('sepi', ta), ('ramai', tb)):
                ts.append({'sel': ns, 'belah': nb, 'grup': nama, **ringkas_tx(tx)})
    return pd.DataFrame(rows), pd.DataFrame(ts)


def main():
    t0 = time.time()
    p, s = siapkan_panel()
    print('sebutan: %d emiten-hari, %d sebutan | %.0f detik' % (len(s), int(s['n'].sum()), time.time() - t0), flush=True)
    p = hitung_sisa(p)
    deskripsi(p)
    pd.set_option('display.width', 250); pd.set_option('display.max_columns', 40)

    print('\n== UJI 1: Fama-MacBeth, selisih fwd20 vs pembanding hari yg sama ~ zsisa + kontrol')
    print(pd.DataFrame({ns: fama_macbeth(p, m) for ns, m in sel(p).items()}).T.to_string())
    print('\n   idem fwd60 (tiap 60 hari)')
    print(pd.DataFrame({ns: fama_macbeth(p, m, 'ex60', 60) for ns, m in sel(p).items()}).T.to_string())

    print('\n== UJI 2: 30% teratas likuiditas, men20=0 vs disebut (fwd20 vs pembanding)')
    print(pd.DataFrame({ns: likuid_nol(p, m) for ns, m in sel(p).items()}).T.to_string())

    print('\n== UJI 3: sinyal menu Tembus Basis dibelah atensi')
    per, pasar = siapkan(p)
    ringkas, ts = tembus_basis(p, per, pasar)
    print(ringkas.to_string(index=False))
    print(ts.to_string(index=False))
    print('\nselesai %.0f detik' % (time.time() - t0))


if __name__ == '__main__':
    main()
