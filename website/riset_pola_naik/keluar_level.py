"""
Aturan keluar TAMBAHAN untuk Tembus Basis / Puncak 52 minggu (24 Sep 2026).

keluar.py (23 Sep) sudah membandingkan H60/H120/TS10/TS15/TS20/SL8/X20:
TS10 dan X20 unggul. Yang BELUM diuji -- dan didaftar di sini SEBELUM hasil
dilihat:

    SUP      keluar kalau close < 97% support chart KEMARIN (support
             diperbarui tiap hari, compute_levels 100 bar), maks 120 hari
    SUPIN    stop tetap: 97% support chart terdekat SAAT MASUK, maks 120
    SUP+TS10 mana yang lebih dulu: SUP atau TS10
    ATR3     trailing chandelier: close <= puncak close sejak masuk
             - 3 x ATR10 (ATR diukur di hari masuk), maks 120
    T20      time stop: di hari ke-20 kalau close <= harga masuk -> keluar;
             kalau tidak, lanjut TS10 sampai 120
    GAGAL5   keluar kalau dalam 5 hari close < 99% level yang ditembus
             (high 30 hari sebelum sinyal); kalau lolos, lanjut TS10

Pembanding: H60, TS10, X20 dari keluar.py (logika dipakai ulang).
Konvensi sama: keluar di close HARI BERIKUTNYA setelah pemicu.
Portofolio 10 slot, median dari 5 urutan pengisian slot acak.

HASIL (24 Sep 2026) -- CAGR% / drawdown% portofolio, median 5 urutan:

                  tembus basis + vol              puncak 52mg + vol
                PILIH A   UJI B    SEMUA        PILIH A   UJI B    SEMUA
    TS10        2,6/-32  25,4/-21  8,5/-27     12,6/-18  27,6/-27  26,5/-25
    X20         1,2/-31  19,9/-21  8,3/-28     10,5/-17  29,6/-23  28,5/-22
    SUP         4,0/-41  12,2/-29  6,3/-43     12,8/-24  17,6/-30  15,5/-35
    SUPIN       1,1/-35  18,5/-33  1,0/-56     15,7/-26  17,4/-57  17,3/-47
    SUP+TS10    3,4/-29  24,5/-27  8,3/-29     12,2/-18  31,6/-24  28,3/-23
    ATR3        8,1/-29  23,7/-26  9,0/-30      9,6/-21  33,2/-39  22,0/-35
    T20         3,0/-33  14,8/-27  4,0/-37      5,7/-19  13,4/-56  10,7/-38
    GAGAL5      2,5/-23  18,9/-21  6,3/-34      8,6/-16  31,4/-26  22,4/-38

- Tidak ada yang mengalahkan TS10/X20 secara konsisten. SUP+TS10 ~ TS10
  (support chart jarang kena sebelum trailing 10%, jadi nyaris tak mengubah
  apa pun). ATR3 menang di dua sel, kalah drawdown di sel lain.
- Stop tetap di bawah support saat masuk (SUPIN) dan keluar HANYA saat
  jebol support (SUP) lebih buruk: menahan terlalu lama (68-82 hari).
- Time stop (T20) paling buruk -- memotong pemenang yang naiknya pelan.
  Konsisten dengan "untung dari ekor kanan yang menumpuk pelan".
- GAGAL5 paling efisien per hari ditahan (vs pasar per 20h tertinggi) tapi
  transaksinya banyak & pendek; CAGR tidak lebih baik dari TS10.
Kesimpulan: tetap TS10/X20. Level chart tidak menambah apa-apa sebagai
aturan keluar di atas trailing 10%.

PEMAKAIAN: python -m website.riset_pola_naik.keluar_level
"""
import sys
import warnings

import numpy as np
import pandas as pd

from . import uji
from . import keluar as K
from . import chart_support as CS
from . import panel as PN

warnings.filterwarnings('ignore')

ATURAN = ['H60', 'TS10', 'X20', 'SUP', 'SUPIN', 'SUP+TS10', 'ATR3', 'T20', 'GAGAL5']
MAKS = K.MAKS
N_SEED = 5


def lengkapi(per, p):
    """Tambah array support chart, ATR10, dan high-30-hari ke `per`."""
    lv = CS.hitung_level()[['ticker', 'date', 'sup']]
    q = p[['ticker', 'date', 'hist', 'atr10']].merge(lv, on=['ticker', 'date'], how='left')
    _, data = PN.sumber_harga()
    for t, d in q.groupby('ticker', sort=False):
        a = per.get(t)
        if a is None:
            continue
        d = d.sort_values('hist')
        a['sup'] = d['sup'].to_numpy(float)
        a['atr'] = d['atr10'].to_numpy(float)
        hi = data[t]['High']
        hi = hi[~hi.index.duplicated(keep='last')].reindex(pd.DatetimeIndex(a['date']))
        a['ph30'] = hi.rolling(30, min_periods=30).max().shift(1).to_numpy(float)


def _trail(c, i, akhir, batas=0.90):
    jalan = c[i:akhir + 1]
    puncak = np.maximum.accumulate(jalan)
    kena = np.flatnonzero((jalan <= batas * puncak)[1:]) + 1
    return i + (kena[0] + 1 if len(kena) else akhir - i + 1)


def keluar_di(a, i, aturan, sinyal):
    if aturan in ('H60', 'TS10', 'X20'):
        return K.keluar_di(a, i, aturan)
    c = a['close']; n = len(c)
    akhir = min(i + MAKS, n - 1)
    j = None
    if aturan in ('SUP', 'SUP+TS10'):
        s = a['sup']
        j_sup = i + MAKS
        for k in range(i + 1, akhir + 1):
            if np.isfinite(s[k - 1]) and c[k] < 0.97 * s[k - 1]:
                j_sup = k + 1
                break
        j = j_sup
        if aturan == 'SUP+TS10':
            j = min(j_sup, _trail(c, i, akhir))
    elif aturan == 'SUPIN':
        s0 = a['sup'][i]
        j = i + MAKS
        if np.isfinite(s0):
            kena = np.flatnonzero(c[i + 1:akhir + 1] < 0.97 * s0)
            if len(kena):
                j = i + 1 + kena[0] + 1
    elif aturan == 'ATR3':
        atr = a['atr'][i]
        if not np.isfinite(atr):
            return None
        j = _trail(c, i, akhir, batas=max(0.0, 1 - 3 * atr))
    elif aturan == 'T20':
        if i + 20 <= akhir and c[i + 20] <= c[i]:
            j = i + 21
        else:
            j = _trail(c, i, akhir)
    elif aturan == 'GAGAL5':
        lvl = a['ph30'][sinyal]
        j = None
        if np.isfinite(lvl):
            kena = np.flatnonzero(c[i + 1:min(i + 5, akhir) + 1] < 0.99 * lvl)
            if len(kena):
                j = i + 1 + kena[0] + 1
        if j is None:
            j = _trail(c, i, akhir)
    else:
        raise ValueError(aturan)
    if j >= n:
        return None
    if a['bad'][i + 1:j + 1].any():
        return None
    return j


def transaksi(ev, per, pasar, aturan):
    rows = []
    for t, h, tgl in zip(ev['ticker'], ev['hist'], ev['date']):
        a = per[t]
        s = int(h) - a['h0']
        i = s + 1
        if i >= len(a['close']):
            continue
        j = keluar_di(a, i, aturan, s)
        if j is None:
            continue
        r = np.log(a['close'][j] / a['close'][i])
        d_in, d_out = a['date'][i], a['date'][j]
        try:
            m = pasar.loc[d_out] - pasar.loc[d_in]
        except KeyError:
            continue
        rows.append({'ticker': t, 'masuk': d_in, 'keluar': d_out, 'tahan': j - i, 'r': r,
                     'lebih': r - m, 'bulan': pd.Timestamp(tgl).to_period('M')})
    return pd.DataFrame(rows)


def main():
    p = uji.muat()
    per, pasar = K.siapkan(p)
    lengkapi(per, p)
    kal = pd.DatetimeIndex(sorted(p['date'].unique()))
    harga = {t: dict(zip(pd.DatetimeIndex(a['date']), a['close'])) for t, a in per.items()}
    MASUK = {'tembus basis + vol': (p['brk30'] == 1) & (p['prevrange30'] < 0.20) & (p['vspike'] > 2),
             'puncak 52mg + vol': (p['hi250'] == 1) & (p['vspike'] > 2)}
    SEL = {'PILIH (A, 2013-19)': (p['half'] == 0) & (p['period'] == 1),
           'UJI (B, 2020-26)': (p['half'] == 1) & (p['period'] == 2),
           'SEMUA (2013-26)': p['date'] <= '2026-06-01'}
    for nm, m in MASUK.items():
        for ns, s in SEL.items():
            ev = uji.jeda(p[m.fillna(False) & p['elig'] & s])
            rows = []
            for ak in ATURAN:
                tx = transaksi(ev, per, pasar, ak)
                r = {'keluar': ak}
                r.update(K.ringkas_tx(tx))
                hs = [K.portofolio(tx, kal, harga, seed=sd) for sd in range(N_SEED)]
                r['CAGR med'] = round(float(np.median([h['CAGR%'] for h in hs])), 1)
                r['DD med'] = round(float(np.median([h['maxDD%'] for h in hs])), 1)
                rows.append(r)
            print('\n' + '=' * 130 + '\n%s | %s\n' % (nm, ns) + '=' * 130, flush=True)
            print(pd.DataFrame(rows).set_index('keluar').to_string(), flush=True)


def main_rezim():
    """Filter rezim di tingkat PORTOFOLIO (keluar TS10). ta_lanjutan rezim
    menunjukkan: saat <50% emiten di atas MA50, sinyal tetap unggul vs pasar
    tapi return absolutnya negatif. keluar.py cuma menguji IHSG>MA200."""
    p = uji.muat()
    e = p['elig']
    lebar = p.loc[e].groupby('date')['ma50'].apply(lambda s: (s > 0).mean()).rename('lebar')
    p = p.merge(lebar, left_on='date', right_index=True, how='left')
    per, pasar = K.siapkan(p)
    kal = pd.DatetimeIndex(sorted(p['date'].unique()))
    harga = {t: dict(zip(pd.DatetimeIndex(a['date']), a['close'])) for t, a in per.items()}
    MASUK = {'tembus basis + vol': (p['brk30'] == 1) & (p['prevrange30'] < 0.20) & (p['vspike'] > 2),
             'puncak 52mg + vol': (p['hi250'] == 1) & (p['vspike'] > 2)}
    SEL = {'PILIH (A, 2013-19)': (p['half'] == 0) & (p['period'] == 1),
           'UJI (B, 2020-26)': (p['half'] == 1) & (p['period'] == 2),
           'SEMUA (2013-26)': p['date'] <= '2026-06-01'}
    FILTER = {'-': pd.Series(True, index=p.index),
              'lebar >50%': p['lebar'] > 0.5,
              'lebar >40%': p['lebar'] > 0.4,
              'IHSG naik 20h': p['ihsg_ret20'] > 0,
              'IHSG>MA200': p['ihsg_ma200'] > 0}
    rows = []
    for nm, m in MASUK.items():
        for ns, s in SEL.items():
            for fn, f in FILTER.items():
                ev = uji.jeda(p[m.fillna(False) & p['elig'] & s & f.fillna(False)])
                tx = transaksi(ev, per, pasar, 'TS10')
                hs = [K.portofolio(tx, kal, harga, seed=sd) for sd in range(N_SEED)]
                rows.append({'masuk': nm, 'sel': ns, 'filter': fn, 'n': len(tx),
                             'CAGR med': round(float(np.median([h['CAGR%'] for h in hs])), 1),
                             'DD med': round(float(np.median([h['maxDD%'] for h in hs])), 1)})
            print(pd.DataFrame(rows[-len(FILTER):]).set_index(['masuk', 'sel', 'filter']).to_string(), flush=True)


if __name__ == '__main__':
    sys.exit(main_rezim() if len(sys.argv) > 1 and sys.argv[1] == 'rezim' else main())
