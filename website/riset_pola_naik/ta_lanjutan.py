"""
Teknikal lanjutan (24 Sep 2026) -- semua kejadian didaftar di sini SEBELUM
hasil dilihat. Kerangka sama dengan uji.py: pencarian separuh A 2013-19,
validasi separuh B 2020-26, dua sel silang, pembanding = semua emiten layak
hari yang sama, selisih majemuk.

  ara       ARA/ARB, fraksi harga, gocap (BEI-spesifik)
  rezim     apakah edge Tembus Basis / Puncak 52mg bergantung kondisi pasar
  indikator golden/death cross, MACD, divergensi RSI, Stochastic, Bollinger
  sektor    kekuatan relatif terhadap sektor, rotasi sektor
  kalender  hari, pergantian bulan, bulan, Lebaran (tingkat pasar)

HARGA MENTAH: pita ARA/ARB dan fraksi bergantung harga yang dilihat bursa,
bukan harga Yahoo yang disesuaikan. harga_mentah_close.pkl belum
disesuaikan dividen tapi SUDAH disesuaikan split, jadi dikali balik dengan
rasio split dari aksi_korporasi.pkl. Terverifikasi: kenaikan maksimum
harian yang tutup di high mengumpul tepat di 35/25/20% per pita, 2013-2026.

JADWAL ARB (dikalibrasi dari data: persentil 5% penurunan yang tutup di
low, per kuartal -- cocok dengan kebijakan BEI yang diketahui):
  -2015-08-24 simetris | -2017 10% | -2020-03-10 simetris | -2023-06-05 7%
  | -2023-09-04 15% | -2025-04-08 simetris | sesudahnya 15%

SEKTOR: klasifikasi IDX-IC SAAT INI (snapshot idx/2026-09), dipakai mundur
ke 2013 -- emiten yang pindah sektor tidak tertangkap. Bias kecil.

HASIL (24 Sep 2026) -- excess 20h vs pasar di sel A13-19 / B20-26 / B13-19 / A20-26
  ARA/ARB
    ARA hari pertama          -6,2 / -2,7 / -4,8 / -2,9  (60h -5..-11)   jangan dikejar
    ARA lalu besoknya turun        -3,2 / -6,4 (t -3,2)   [sel 2013-19 n<30]
    ARB hari pertama          -1,7 / -3,7 (t -5,9) / -9,9 / -3,0 (t -4,9)
    ARB 2 / >=3 hari beruntun  -6,3/-4,8  |  -7,9/-8,6 (60h -13)  [2020-26]
    naik pertama sesudah >=2 ARB   -3,8 / -2,3 (60h -9/-8)  -> menangkap pisau jatuh rugi
    fraksi harga: tidak ada efek khusus (turun lewat batas = cuma "harga turun")
    gocap: kelihatan positif (+1,7..+3,8) TAPI TIDAK BISA DIPERCAYA -- emiten
      yang delisting kebanyakan saham suspensi di Rp50 dan tidak ada di cache
      (lihat delisting.py). Survivorship paling parah persis di kelompok ini.
  REZIM: edge tembus basis/puncak vs pasar bertahan di SEMUA rezim. Return
    absolut negatif saat lebar pasar <50% di atas MA50, tapi di portofolio
    (keluar_level rezim, TS10) semua filter MENURUNKAN CAGR (UJI tembus 25,4
    -> 12,8..23,3), drawdown cuma sedikit membaik. Tidak dipakai.
  INDIKATOR: yang "kuat makin kuat" positif di 4 sel -- MACD cross naik di
    atas nol (+0,4..+1,1), RSI tembus 70 (+0,1..+1,6), close di atas Bollinger
    atas (+0,6..+1,1; t 1,9-3,1). Yang "beli murah" negatif di 4 sel --
    Stochastic cross naik <20 (-0,7..-0,9; t -2,6..-4,1), close di bawah
    Bollinger bawah, divergensi RSI bullish, MACD cross naik di bawah nol.
    Golden/death cross, lewat MA50/MA200: nihil. Squeeze Bollinger: gagal
    di sel pencarian. Tak ada yang lebih kuat dari tembus basis + volume.
  SEKTOR: lemah relatif thd sektornya (desil bawah) negatif di 4 sel
    (-0,7..-1,6); kuat relatif tidak konsisten; momentum sektor nyaris nihil.
    Tembus basis di sektor kuat sedikit lebih baik (+1,7..+2,5) daripada di
    sektor lemah (+0,6..+1,7) -- beda kecil, n sektor lemah kecil.
  KALENDER: tidak ada yang lolos. Senin negatif & Rabu positif di 2013-19
    (t ~3) hilang di 2020-26; Januari berbalik tanda; Desember, pergantian
    bulan, sekitar Lebaran tidak signifikan / berbalik.

PEMAKAIAN: python -m website.riset_pola_naik.ta_lanjutan {ara|rezim|indikator|sektor|kalender|semua}
"""
import glob
import json
import os
import pickle
import sys
import warnings

import numpy as np
import pandas as pd

from . import panel as PN
from . import uji as U

warnings.filterwarnings('ignore')

ARB_JADWAL = [('2015-08-24', None), ('2017-01-01', 0.10), ('2020-03-10', None),
              ('2023-06-05', 0.07), ('2023-09-04', 0.15), ('2025-04-08', None),
              ('2100-01-01', 0.15)]          # (berlaku SEBELUM tanggal ini, batas); None = simetris
BATAS_FRAKSI = (200, 500, 2000, 5000)
LEBARAN = ['2013-08-08', '2014-07-28', '2015-07-17', '2016-07-06', '2017-06-25', '2018-06-15',
           '2019-06-05', '2020-05-24', '2021-05-13', '2022-05-02', '2023-04-22', '2024-04-10',
           '2025-03-31', '2026-03-20']


# --------------------------------------------------------------- data dasar
def harga_mentah():
    m = pickle.load(open(os.path.join(PN.RESEARCH_CACHE, 'harga_mentah_close.pkl'), 'rb'))
    ak = pickle.load(open(os.path.join(PN.RESEARCH_CACHE, 'aksi_korporasi.pkl'), 'rb'))['aksi']
    out = {}
    for t, s in m.items():
        s = s[~s.index.duplicated(keep='last')].sort_index()
        f = np.ones(len(s))
        a = ak.get(t)
        if a is not None and 'Stock Splits' in a:
            sp = a['Stock Splits']
            sp = sp[sp > 0]
            for d, r in sp.items():
                d = pd.Timestamp(d)
                d = d.tz_localize(None) if d.tzinfo else d
                f[s.index < d] *= r
        out[t] = s * f
    return out


def peta_sektor():
    from ..ownership import IDX_DIR
    sek = {}
    for f in glob.glob(os.path.join(IDX_DIR, '*', '*.json')):
        try:
            j = json.load(open(f, encoding='utf-8'))
        except Exception:
            continue
        if j.get('sector'):
            sek[j['ticker']] = j['sector']
    return sek


def _tick(p):
    return np.select([p < 200, p < 500, p < 2000, p < 5000], [1, 2, 5, 10], 25)


def _batas_arb(tgl, band):
    lim = np.full(len(tgl), np.nan)
    mulai = pd.Timestamp('1900-01-01')
    for akhir, v in ARB_JADWAL:
        akhir = pd.Timestamp(akhir)
        m = (tgl >= mulai) & (tgl < akhir)
        lim[m] = band[m] if v is None else v
        mulai = akhir
    return lim


def _pertama(x, jeda=1):
    """True hanya di hari pertama rangkaian True."""
    return x & ~x.shift(jeda, fill_value=False)


def fitur_ta(t, df, raw):
    df = df[['Open', 'High', 'Low', 'Close', 'Volume']].copy()
    df = df[df['Close'] > 0].sort_index()
    df = df[~df.index.duplicated(keep='last')]
    if len(df) < 300:
        return None
    C = df['Close']
    H = np.maximum(df['High'], C); L = np.minimum(df['Low'], C)
    r = C.pct_change()
    o = pd.DataFrame(index=df.index)
    o['ticker'] = t

    # --- ARA / ARB ---
    rw = raw.reindex(C.index) if raw is not None else pd.Series(np.nan, index=C.index)
    rprev = rw.shift(1)
    band = np.where(rprev <= 200, 0.35, np.where(rprev <= 5000, 0.25, 0.20))
    tol = np.maximum(0.01, 1.5 * _tick(rprev.fillna(1e9).to_numpy()) / rprev.to_numpy())
    di_hi = C >= H * 0.9999
    di_lo = C <= L * 1.0001
    ara = di_hi & (r >= band - tol) & (r > 0.15)
    arb_lim = _batas_arb(C.index, band)
    arb = di_lo & (r <= -arb_lim + tol) & (r < -0.05) & (rprev > 51)
    o['ara'] = ara.astype(float); o['arb'] = arb.astype(float)
    o['hampir_ara'] = ((r >= band - 0.05) & ~di_hi & (r > 0.10)).astype(float)
    g = (~arb).cumsum(); o['arb_run'] = arb.groupby(g).cumsum().astype(float)
    g = (~ara).cumsum(); o['ara_run'] = ara.groupby(g).cumsum().astype(float)
    o['arb_era_asim'] = (arb_lim < band).astype(float)

    # --- fraksi & gocap (harga mentah) ---
    up = pd.Series(False, index=C.index); dn = pd.Series(False, index=C.index)
    atas = pd.Series(False, index=C.index); bawah = pd.Series(False, index=C.index)
    for b in BATAS_FRAKSI:
        up |= (rw >= b) & (rprev < b)
        dn |= (rw < b) & (rprev >= b)
        atas |= (rw >= b) & (rw < b * 1.03)
        bawah |= (rw < b) & (rw >= b * 0.97)
    o['fr_naik'] = up.astype(float); o['fr_turun'] = dn.astype(float)
    o['fr_atas'] = atas.astype(float); o['fr_bawah'] = bawah.astype(float)
    lantai = rw <= 50.5
    n20 = lantai.astype(float).rolling(20).sum()
    o['gc_lepas'] = _pertama((n20.shift(1) >= 10) & (rw >= 55)).astype(float)
    o['gc_sentuh'] = (lantai & (lantai.astype(float).rolling(60).sum().shift(1) == 0)).astype(float)
    o['gc_di'] = lantai.astype(float)
    o['raw'] = rw

    # --- indikator klasik ---
    ma50, ma200 = C.rolling(50).mean(), C.rolling(200).mean()
    gold = ma50 > ma200
    o['golden'] = _pertama(gold).astype(float) * gold.shift(1).notna()
    o['death'] = _pertama(~gold & ma200.notna()).astype(float)
    ema12, ema26 = C.ewm(span=12, adjust=False).mean(), C.ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    sig = macd.ewm(span=9, adjust=False).mean()
    xup = _pertama(macd > sig); xdn = _pertama(macd < sig)
    o['macd_up_bawah'] = (xup & (macd < 0)).astype(float)
    o['macd_up_atas'] = (xup & (macd > 0)).astype(float)
    o['macd_dn_atas'] = (xdn & (macd > 0)).astype(float)
    lr = np.log(C).diff()
    au = lr.clip(lower=0).ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    ad = (-lr).clip(lower=0).ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    rsi = 100 - 100 / (1 + au / ad.replace(0, np.nan))
    # divergensi: close vs ekstrem close di t-40..t-10, RSI dibandingkan di titik ekstrem itu
    c = C.to_numpy(float); rs = rsi.to_numpy(float); n = len(c)
    bull = np.zeros(n); bear = np.zeros(n)
    for k in range(40, n):
        w = c[k - 40:k - 9]
        jlo = int(np.argmin(w)); jhi = int(np.argmax(w))
        if c[k] < w[jlo] and rs[k] < 40 and rs[k] > rs[k - 40 + jlo] + 5:
            bull[k] = 1
        if c[k] > w[jhi] and rs[k] > 60 and rs[k] < rs[k - 40 + jhi] - 5:
            bear[k] = 1
    o['rsi_div_bull'] = _pertama(pd.Series(bull, index=C.index) == 1, 1).astype(float)
    o['rsi_div_bear'] = _pertama(pd.Series(bear, index=C.index) == 1, 1).astype(float)
    o['rsi70'] = _pertama(rsi > 70).astype(float)
    hh, ll = H.rolling(14).max(), L.rolling(14).min()
    k_ = (C - ll) / (hh - ll).replace(0, np.nan) * 100
    d_ = k_.rolling(3).mean()
    o['stoch_up20'] = (_pertama(k_ > d_) & (d_ < 20)).astype(float)
    m20, s20 = C.rolling(20).mean(), C.rolling(20).std()
    o['bb_bawah'] = _pertama(C < m20 - 2 * s20).astype(float)
    o['bb_atas'] = _pertama(C > m20 + 2 * s20).astype(float)
    bw = (4 * s20 / m20)
    bwp = bw.rolling(250, min_periods=250).rank(pct=True)
    o['bb_squeeze_atas'] = (o['bb_atas'].astype(bool) & (bwp.shift(1) <= 0.10)).astype(float)
    o['x_ma50'] = _pertama((C > ma50) & ma50.notna()).astype(float)
    o['x_ma200'] = _pertama((C > ma200) & ma200.notna()).astype(float)
    return o


def muat():
    p = U.muat()
    _, data = PN.sumber_harga()
    raw = harga_mentah()
    ext = pd.concat([f for f in (fitur_ta(t, d, raw.get(t)) for t, d in data.items()) if f is not None])
    ext.index.name = 'date'
    ext = ext.reset_index()
    fc = [c for c in ext.columns if c not in ('ticker', 'date')]
    ext[fc] = ext[fc].astype('float32')
    p = p.merge(ext, on=['ticker', 'date'], how='left')
    # layak tanpa syarat harga -- khusus kejadian gocap
    p['elig_gc'] = ((p['hist'] >= 260) & (p['medval20'] >= U.MIN_NILAI) & (p['traded30'] >= 0.9)
                    & (p['bad_back60'] == 0) & (p['date'] >= '2013-01-01'))
    sek = peta_sektor()
    p['sektor'] = p['ticker'].map(sek)
    return p


# --------------------------------------------------------------- laporan
SEL_NAMA = ['A 13-19', 'B 20-26', 'B 13-19', 'A 20-26']


def _sel(p):
    return dict(zip(SEL_NAMA, U.sel(p).values()))


def ringkas(p, P, elig='elig', judul=''):
    """Satu baris per pola: excess 20h & 60h di 4 sel (t dalam kurung), lift P(+10%) di validasi."""
    sel = _sel(p)
    rows = []
    for nama, m in P.items():
        r = {'pola': nama}
        for sn, s in sel.items():
            ev = U.jeda(p[m.fillna(False) & p[elig] & s])
            st = U.statistik(ev)
            r['n ' + sn] = st['n']
            e20, t20, e60 = st.get('exc20'), st.get('t20'), st.get('exc60')
            r['20h ' + sn] = '' if e20 is None else '%+.2f (%+.1f)' % (e20, t20)
            r['60h ' + sn] = '' if e60 is None else '%+.2f' % e60
            if sn == 'B 20-26' and 'p10' in st:
                r['P10 lift B'] = round(st['p10'] - st['p10_base'], 1)
        rows.append(r)
    d = pd.DataFrame(rows).set_index('pola')
    kol = ['n B 20-26'] + ['20h ' + s for s in SEL_NAMA] + ['60h ' + s for s in SEL_NAMA] + ['P10 lift B']
    print('\n' + '=' * 170 + '\n' + judul + '\n' + '=' * 170)
    print(d[[k for k in kol if k in d]].to_string(), flush=True)


def lap_ara(p):
    P = {'ALL eligible days': pd.Series(True, index=p.index)}
    ara, arb = p['ara'] == 1, p['arb'] == 1
    P['A1 ARA (hari pertama)'] = ara & (p['ara_run'] == 1)
    P['A2 ARA 2 hari berturut'] = p['ara_run'] == 2
    P['A3 ARA + volume >5x'] = ara & (p['ara_run'] == 1) & (p['vspike'] > 5)
    g = p.groupby('ticker', sort=False)
    ara_kmrn = g['ara'].shift(1) == 1
    P['A4 ARA kemarin, hari ini turun'] = ara_kmrn & (p['ret1'] < 0)
    P['A5 ARA kemarin, hari ini naik >=5% (bukan ARA)'] = ara_kmrn & (p['ret1'] >= 0.05) & ~ara
    P['A6 hampir ARA tapi tidak tutup di high'] = p['hampir_ara'] == 1
    P['B1 ARB (hari pertama)'] = arb & (p['arb_run'] == 1)
    P['B1a ARB era batas sempit (7/10/15%)'] = arb & (p['arb_run'] == 1) & (p['arb_era_asim'] == 1)
    P['B1b ARB era simetris'] = arb & (p['arb_run'] == 1) & (p['arb_era_asim'] == 0)
    P['B2 ARB 2 hari berturut'] = p['arb_run'] == 2
    P['B3 ARB >=3 hari berturut'] = p['arb_run'] == 3
    run_kmrn = g['arb_run'].shift(1)
    P['B4 naik pertama setelah >=2 ARB'] = (run_kmrn >= 2) & (p['ret1'] > 0)
    P['F1 harga mentah naik lewat batas fraksi'] = p['fr_naik'] == 1
    P['F2 harga mentah turun lewat batas fraksi'] = p['fr_turun'] == 1
    P['F3 0-3% DI ATAS batas fraksi'] = p['fr_atas'] == 1
    P['F4 0-3% DI BAWAH batas fraksi'] = p['fr_bawah'] == 1
    ringkas(p, P, judul='ARA / ARB / FRAKSI  (layak: nilai >=1M, harga >=100)')
    G = {'ALL (tanpa syarat harga)': pd.Series(True, index=p.index),
         'G1 pertama kali menyentuh gocap (Rp50)': p['gc_sentuh'] == 1,
         'G2 sedang di gocap': p['gc_di'] == 1,
         'G3 lepas dari gocap (>=10/20 hari di 50, kini >=55)': p['gc_lepas'] == 1}
    ringkas(p, G, elig='elig_gc', judul='GOCAP  (layak TANPA syarat harga)')


def lap_indikator(p):
    P = {'ALL eligible days': pd.Series(True, index=p.index)}
    for k, lab in [('golden', 'I1 golden cross MA50>MA200'), ('death', 'I2 death cross'),
                   ('macd_up_bawah', 'I3 MACD cross naik di bawah nol'),
                   ('macd_up_atas', 'I4 MACD cross naik di atas nol'),
                   ('macd_dn_atas', 'I5 MACD cross turun di atas nol'),
                   ('rsi_div_bull', 'I6 divergensi RSI bullish'),
                   ('rsi_div_bear', 'I7 divergensi RSI bearish'),
                   ('rsi70', 'I8 RSI tembus 70 (overbought)'),
                   ('stoch_up20', 'I9 Stochastic cross naik <20'),
                   ('bb_bawah', 'I10 close di bawah Bollinger bawah'),
                   ('bb_atas', 'I11 close di atas Bollinger atas'),
                   ('bb_squeeze_atas', 'I12 squeeze Bollinger lalu tembus atas'),
                   ('x_ma50', 'I13 close naik lewat MA50'),
                   ('x_ma200', 'I14 close naik lewat MA200')]:
        P[lab] = p[k] == 1
    ringkas(p, P, judul='INDIKATOR KLASIK')


def lap_rezim(p):
    ih = PN.sumber_ihsg()
    lr = np.log(ih).diff()
    v20 = lr.rolling(20).std()
    vpct = v20.rolling(750, min_periods=250).rank(pct=True).rename('ihsg_volpct')
    p = p.merge(vpct, left_on='date', right_index=True, how='left')
    e = p['elig']
    lebar = p.loc[e].groupby('date')['ma50'].apply(lambda s: (s > 0).mean()).rename('lebar')
    p = p.merge(lebar, left_on='date', right_index=True, how='left')
    REZIM = {'IHSG > MA200': p['ihsg_ma200'] > 0,
             'IHSG naik 20h': p['ihsg_ret20'] > 0,
             'lebar pasar >50% di atas MA50': p['lebar'] > 0.5,
             'volatilitas IHSG rendah (<median 3th)': p['ihsg_volpct'] < 0.5}
    MASUK = {'tembus basis + vol': (p['brk30'] == 1) & (p['prevrange30'] < 0.20) & (p['vspike'] > 2),
             'puncak 52mg + vol': (p['hi250'] == 1) & (p['vspike'] > 2),
             'semua hari layak': pd.Series(True, index=p.index)}
    for nm, m in MASUK.items():
        P = {}
        for rn, rc in REZIM.items():
            P[rn + ': YA'] = m & rc.fillna(False)
            P[rn + ': TIDAK'] = m & ~rc.fillna(True)
        ringkas(p, P, judul='REZIM -- %s (excess vs pasar hari itu)' % nm)
        # return ABSOLUT (majemuk) -- yang dipedulikan filter rezim
        rows = []
        for n2, m2 in P.items():
            r = {'pola': n2}
            for sn, s in _sel(p).items():
                st = U.statistik(U.jeda(p[m2.fillna(False) & p['elig'] & s]))
                r['abs20 ' + sn] = round(st.get('comp20', np.nan), 2)
            rows.append(r)
        print('-- return ABSOLUT majemuk 20h (%):')
        print(pd.DataFrame(rows).set_index('pola').to_string(), flush=True)


def lap_sektor(p):
    p = p[p['sektor'].notna()].copy()
    e = p['elig']
    q = p.loc[e, ['date', 'sektor', 'ret20', 'ret60']]
    sm = q.groupby(['date', 'sektor'])[['ret20', 'ret60']].median().rename(columns={'ret20': 'sek20', 'ret60': 'sek60'})
    sm['sek60_rank'] = sm.groupby(level='date')['sek60'].rank(pct=True)
    p = p.merge(sm, left_on=['date', 'sektor'], right_index=True, how='left')
    p['rel60'] = p['ret60'] - p['sek60']
    p['rel60_cs'] = np.nan
    p.loc[e, 'rel60_cs'] = p.loc[e].groupby('date')['rel60'].rank(pct=True)
    base = (p['brk30'] == 1) & (p['prevrange30'] < 0.20) & (p['vspike'] > 2)
    P = {'ALL eligible days': pd.Series(True, index=p.index),
         'S1 kuat relatif thd sektor (desil atas rel60)': p['rel60_cs'] >= 0.9,
         'S2 lemah relatif thd sektor (desil bawah rel60)': p['rel60_cs'] <= 0.1,
         'S3 sektor terkuat (sepertiga atas sek60)': p['sek60_rank'] > 2 / 3,
         'S4 sektor terlemah (sepertiga bawah sek60)': p['sek60_rank'] <= 1 / 3,
         'S5 naik sendirian: ret20>15%, sektor20<0': (p['ret20'] > 0.15) & (p['sek20'] < 0),
         'S6 naik bareng: ret20>15%, sektor20>5%': (p['ret20'] > 0.15) & (p['sek20'] > 0.05),
         'S7 tembus basis+vol, sektor kuat': base & (p['sek60_rank'] > 2 / 3),
         'S8 tembus basis+vol, sektor lemah': base & (p['sek60_rank'] <= 1 / 3)}
    ringkas(p, P, judul='SEKTOR (IDX-IC saat ini, %d emiten)' % p['ticker'].nunique())


def lap_kalender(p):
    """Tingkat pasar: return harian indeks rata-rata-sama (emiten layak kemarin) dan IHSG."""
    q = p[['ticker', 'date', 'close', 'elig', 'ret1', 'half']].sort_values(['ticker', 'date'])
    q['lr'] = np.log(q['close']).groupby(q['ticker']).diff()
    q['lk'] = q.groupby('ticker')['elig'].shift(1).fillna(False).astype(bool)
    q = q[q['lk'] & (q['ret1'].abs() <= 0.45)]
    ew = q.groupby('date')['lr'].mean().rename('EW semua')
    ewa = q[q['half'] == 0].groupby('date')['lr'].mean().rename('EW separuh A')
    ewb = q[q['half'] == 1].groupby('date')['lr'].mean().rename('EW separuh B')
    ih = np.log(PN.sumber_ihsg()).diff().rename('IHSG')
    d = pd.concat([ew, ewa, ewb, ih], axis=1).dropna()
    d = d[d.index >= '2013-01-01']
    idx = d.index
    ym = idx.to_period('M')
    pos = pd.Series(np.arange(len(idx)), index=idx)
    first = pos.groupby(ym).transform('min'); last = pos.groupby(ym).transform('max')
    k_awal = (pos - first).to_numpy()
    k_akhir = (last - pos).to_numpy()
    tom = (k_akhir == 0) | (k_awal <= 2)
    pre = np.zeros(len(idx), bool); post = np.zeros(len(idx), bool)
    for L in LEBARAN:
        L = pd.Timestamp(L)
        before = np.flatnonzero(idx < L)[-5:]
        after = np.flatnonzero(idx > L + pd.Timedelta(days=3))[:5]
        pre[before] = True; post[after] = True
    GRUP = {'Senin': idx.dayofweek == 0, 'Selasa': idx.dayofweek == 1, 'Rabu': idx.dayofweek == 2,
            'Kamis': idx.dayofweek == 3, 'Jumat': idx.dayofweek == 4,
            'pergantian bulan (akhir 1 + awal 3)': tom,
            'Januari': idx.month == 1, 'Desember': idx.month == 12,
            'Desember paruh 2 (tgl>=15)': (idx.month == 12) & (idx.day >= 15),
            '5 hari bursa sebelum Lebaran': pre, '5 hari bursa sesudah Lebaran': post}
    per = {'2013-19': idx.year <= 2019, '2020-26': idx.year >= 2020}
    rows = []
    for gn, gm in GRUP.items():
        for pn, pm in per.items():
            r = {'grup': gn, 'periode': pn, 'hari': int((gm & pm).sum())}
            for col in d.columns:
                x = d[col].to_numpy()
                a, b = x[gm & pm], x[~gm & pm]
                dif = a.mean() - b.mean()
                se = np.sqrt(a.var(ddof=1) / len(a) + b.var(ddof=1) / len(b))
                r[col] = '%+.1f (%+.1f)' % (dif * 1e4, dif / se)
            rows.append(r)
    print('\n' + '=' * 130 + '\nKALENDER: selisih return harian grup vs hari lain, basis poin (t)\n' + '=' * 130)
    print(pd.DataFrame(rows).set_index(['grup', 'periode']).to_string(), flush=True)


def main(arg):
    p = muat()
    tugas = {'ara': lap_ara, 'rezim': lap_rezim, 'indikator': lap_indikator,
             'sektor': lap_sektor, 'kalender': lap_kalender}
    for k in (tugas if arg == 'semua' else [arg]):
        tugas[k](p)


if __name__ == '__main__':
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else 'semua'))
