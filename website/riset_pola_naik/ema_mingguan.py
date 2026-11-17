"""
Golden cross / dead cross EMA 10 & EMA 20 MINGGUAN -- 29 Okt 2026.

ATURAN (dari pengguna, tanpa parameter yang disetel)
    Beli  : minggu ini EMA10 > EMA20, minggu lalu EMA10 <= EMA20 (golden cross)
    Jual  : minggu ini EMA10 < EMA20, minggu lalu EMA10 >= EMA20 (dead cross)
Candle mingguan = close hari bursa terakhir tiap minggu (Jumat). Sinyal baru
diketahui setelah minggu tutup, jadi eksekusi di close hari bursa BERIKUTNYA
(Open Yahoo untuk BEI tidak bisa dipercaya). Golden cross hanya diambil
kalau emiten layak (uji.muat) di hari sinyal. EMA dihitung dari seluruh
riwayat panel (mulai Jun 2012), perdagangan mulai 2013.

DUA SUDUT
1. PER SAHAM: tiap emiten satu akun (masuk penuh / kas), dibandingkan dengan
   beli-tahan emiten itu sendiri; 2013-19 dan 2020-26 dihitung terpisah.
   -> ema_mingguan_per_saham.csv
2. PORTOFOLIO: semua golden cross di semua emiten, 10 slot sama besar,
   median 10 urutan pengisian slot acak; pembanding Tembus Basis + vol
   dengan TS10, beli-semua-emiten-layak, dan IHSG.
Ongkos 0,15% beli + 0,25% jual + slippage 0,25%/sisi. Karena aturannya
datang utuh dari luar (tidak dipilih dari data), dua periode dilaporkan
berdampingan; yang dinilai: konsisten di keduanya atau tidak.

HASIL (29 Okt 2026), 2013-19 / 2020-26
- Untung? Per saham cuma 35% / 34% emiten yang untung, median CAGR -1,6 /
  -2,6 (beli-tahan -0,7 / +0,4). Portofolio 10 slot: -4,2% / +2,0% per
  tahun, DD -45 / -57. Win per transaksi 28%, median transaksi -6%.
- Lebih baik dari yang ada? Tidak: Tembus Basis+vol TS10 di semesta yang
  sama 3,6% / 9,2%, DD -28. Beli-semua 0,0% / 2,8%, IHSG 5,5% / -2,8%.
- Konsisten per saham? Tidak: "bagus" (untung & > beli-tahan) di dua
  periode 2 emiten (SMBR, SIDO) vs ~3,3 kalau kebetulan.
- Satu-satunya kelebihan: drawdown per saham lebih dangkal (93-95% emiten)
  -- emiten kecil yang dipegang terus bisa -80..-99%.
- Kenapa lemah: silang EMA mingguan telat dua kali -- masuk setelah harga
  sudah lari, keluar setelah turun jauh; banyak silang palsu (whipsaw).

PEMAKAIAN (dari <project>/)
    python -m website.riset_pola_naik.ema_mingguan
"""
try:
    from ..runtime_paths import runtime_file as _runtime_file, market_file as _market_file, WEBSITE_DIR as _WEBSITE_DIR, PROJECT_DIR as _PROJECT_DIR, RUNTIME_DIR as _RUNTIME_DIR
except ImportError:
    from website.runtime_paths import runtime_file as _runtime_file, market_file as _market_file, WEBSITE_DIR as _WEBSITE_DIR, PROJECT_DIR as _PROJECT_DIR, RUNTIME_DIR as _RUNTIME_DIR
import os

import numpy as np
import pandas as pd

from . import donchian_saham as DS
from . import keluar as KL
from . import uji
from .panel import sumber_ihsg

PERIODE = DS.PERIODE
N_SEED = 10
KELUAR_CSV = str(_runtime_file('riset_pola_naik', 'ema_mingguan_per_saham.csv'))


def sinyal(d):
    """Array harian: golden / dead cross mingguan menyala di hari bursa terakhir minggunya."""
    c = d['close'].astype(float)
    minggu = d['date'].dt.to_period('W-FRI')
    akhir = ~minggu.duplicated(keep='last')            # baris terakhir tiap minggu
    wk = c[akhir.to_numpy()]
    e10 = wk.ewm(span=10, adjust=False, min_periods=10).mean()
    e20 = wk.ewm(span=20, adjust=False, min_periods=20).mean()
    atas = (e10 > e20) & e20.notna()
    bawah = (e10 < e20) & e20.notna()
    gold = atas & ~atas.shift(1, fill_value=True) & e20.shift(1).notna()
    dead = bawah & ~bawah.shift(1, fill_value=True) & e20.shift(1).notna()
    g = np.zeros(len(d), bool); x = np.zeros(len(d), bool)
    pos = np.flatnonzero(akhir.to_numpy())
    g[pos] = gold.to_numpy(); x[pos] = dead.to_numpy()
    return g, x


def jalan(c, gold, dead, elig):
    """Satu emiten satu akun. Kembalikan kurva ekuitas, daftar (i_masuk, i_keluar, ret), porsi hari pegang."""
    n = len(c)
    eq = np.ones(n)
    kas, lembar, modal, beli, jual, i_in = 1.0, 0.0, 1.0, False, False, -1
    tx, pegang = [], 0
    for k in range(n):
        if jual:
            kas = lembar * c[k] * (1 - DS.JUAL)
            tx.append((i_in, k, kas / modal - 1))
            lembar, jual = 0.0, False
        elif beli:
            modal, lembar, kas, i_in, beli = kas, kas * (1 - DS.BELI) / c[k], 0.0, k, False
        eq[k] = kas + lembar * c[k]
        if lembar > 0:
            pegang += 1
            if k > i_in and dead[k]:
                jual = True
        elif gold[k] and elig[k]:
            beli = True
    if lembar > 0:
        kas = lembar * c[-1] * (1 - DS.JUAL)
        tx.append((i_in, n - 1, kas / modal - 1))
        eq[-1] = kas
    return eq, tx, pegang / n


def per_saham(p):
    rows = []
    for t, d in p.groupby('ticker', sort=False):
        d = d.sort_values('hist').reset_index(drop=True)
        g, x = sinyal(d)
        for np_, (a, b) in PERIODE.items():
            m = ((d['date'] >= a) & (d['date'] <= b)).to_numpy()
            s = d[m]
            if len(s) < 250 or not s['elig'].any() or (s['ret1'].abs().iloc[1:] > 0.45).any():
                continue
            c = s['close'].to_numpy(float)
            hari = (s['date'].iloc[-1] - s['date'].iloc[0]).days
            eq, tx, pg = jalan(c, g[m], x[m], s['elig'].to_numpy(bool))
            r = np.array([z[2] for z in tx])
            bh = c / c[0]
            rows.append({'ticker': t, 'periode': np_, 'transaksi': len(r),
                         'win%': round((r > 0).mean() * 100, 0) if len(r) else np.nan,
                         'CAGR strategi%': round(DS.cagr(eq[-1], hari), 1),
                         'CAGR beli-tahan%': round(DS.cagr(bh[-1] * (1 - DS.BELI) * (1 - DS.JUAL), hari), 1),
                         'DD strategi%': round(DS.dd(eq), 1), 'DD beli-tahan%': round(DS.dd(bh), 1),
                         'hari pegang%': round(pg * 100, 0)})
    df = pd.DataFrame(rows)
    df['selisih%'] = (df['CAGR strategi%'] - df['CAGR beli-tahan%']).round(1)
    return df


def transaksi_porto(p, pasar):
    """Semua golden cross di seluruh riwayat (tanpa potong periode) sebagai transaksi portofolio."""
    rows = []
    for t, d in p.groupby('ticker', sort=False):
        d = d.sort_values('hist').reset_index(drop=True)
        g, x = sinyal(d)                                # EMA dari seluruh riwayat, baru dipotong
        m = (d['date'] >= '2013-01-01').to_numpy()
        if m.sum() < 30:
            continue
        d, g, x = d[m].reset_index(drop=True), g[m], x[m]
        c = d['close'].to_numpy(float)
        bad = (d['ret1'].abs() > 0.45).to_numpy()
        _, tx, _ = jalan(c, g, x, d['elig'].to_numpy(bool))
        dates = d['date'].to_numpy()
        for i, j, _ in tx:
            if bad[i + 1:j + 1].any():
                continue
            d_in, d_out = pd.Timestamp(dates[i]), pd.Timestamp(dates[j])
            try:
                m = pasar.loc[d_out] - pasar.loc[d_in]
            except KeyError:
                continue
            r = np.log(c[j] / c[i])
            rows.append({'ticker': t, 'masuk': d_in, 'keluar': d_out, 'tahan': j - i, 'r': r, 'lebih': r - m,
                         'bulan': d_in.to_period('M')})
    return pd.DataFrame(rows)


def beli_semua(p, a, b):
    """CAGR portofolio rata-rata-sama semua emiten layak (rebalance harian, tanpa ongkos) dan IHSG."""
    q = p[['ticker', 'date', 'elig', 'ret1']].sort_values(['ticker', 'date'])
    q['layak_kmrn'] = q.groupby('ticker')['elig'].shift(1).fillna(False).astype(bool)
    q = q[q['layak_kmrn'] & (q['ret1'].abs() <= 0.45) & (q['date'] >= a) & (q['date'] <= b)]
    ew = (1 + q.groupby('date')['ret1'].mean().sort_index()).cumprod()
    th = (ew.index[-1] - ew.index[0]).days / 365.25
    out = {'beli semua': round((ew.iloc[-1] ** (1 / th) - 1) * 100, 1)}
    ih = sumber_ihsg()
    if ih is not None:
        s = ih[(ih.index >= a) & (ih.index <= b)]
        out['IHSG'] = round(((s.iloc[-1] / s.iloc[0]) ** (1 / th) - 1) * 100, 1)
    return out


def main():
    p = uji.muat()

    # ---- 1. per saham ----
    df = per_saham(p)
    df.to_csv(KELUAR_CSV, index=False)
    print('tersimpan: %s (%d baris, %d emiten)' % (KELUAR_CSV, len(df), df['ticker'].nunique()))
    pd.set_option('display.width', 220)
    for np_ in PERIODE:
        y = df[(df['periode'] == np_) & (df['transaksi'] > 0)]
        print('%s: %d emiten | untung %d (%.0f%%) | > beli-tahan %d (%.0f%%) | DD lebih dangkal %.0f%% | '
              'median CAGR strategi %.1f vs beli-tahan %.1f | median transaksi %d, hari pegang %.0f%%'
              % (np_, len(y), (y['CAGR strategi%'] > 0).sum(), (y['CAGR strategi%'] > 0).mean() * 100,
                 (y['selisih%'] > 0).sum(), (y['selisih%'] > 0).mean() * 100,
                 (y['DD strategi%'] > y['DD beli-tahan%']).mean() * 100,
                 y['CAGR strategi%'].median(), y['CAGR beli-tahan%'].median(),
                 y['transaksi'].median(), y['hari pegang%'].median()))
    w = df.pivot(index='ticker', columns='periode', values=['CAGR strategi%', 'selisih%', 'transaksi']).dropna()
    w = w[(w[('transaksi', '2013-19')] > 0) & (w[('transaksi', '2020-26')] > 0)]
    g1 = (w[('CAGR strategi%', '2013-19')] > 0) & (w[('selisih%', '2013-19')] > 0)
    g2 = (w[('CAGR strategi%', '2020-26')] > 0) & (w[('selisih%', '2020-26')] > 0)
    print('emiten di dua periode: %d | "bagus" (untung & > beli-tahan) 2013-19: %d, 2020-26: %d, dua-duanya: %d '
          '(kebetulan ~%.1f) | bagus lagi kalau dulu bagus %.0f%% vs dulu jelek %.0f%%'
          % (len(w), g1.sum(), g2.sum(), (g1 & g2).sum(), g1.mean() * g2.mean() * len(w),
             g2[g1].mean() * 100, g2[~g1].mean() * 100))
    dua = w[g1 & g2]
    print(pd.DataFrame({'CAGR 13-19': dua[('CAGR strategi%', '2013-19')], 'CAGR 20-26': dua[('CAGR strategi%', '2020-26')],
                        'vs B&H 13-19': dua[('selisih%', '2013-19')], 'vs B&H 20-26': dua[('selisih%', '2020-26')]})
          .sort_values('CAGR 20-26', ascending=False).T.to_string())
    y = df[(df['periode'] == '2020-26') & (df['transaksi'] > 0)].sort_values('CAGR strategi%', ascending=False)
    print('\n25 teratas 2020-26:')
    print(y.head(25).drop(columns='periode').to_string(index=False))

    # ---- 2. portofolio ----
    per, pasar = KL.siapkan(p)
    kal = pd.DatetimeIndex(sorted(p['date'].unique()))
    harga = {t: dict(zip(pd.DatetimeIndex(a['date']), a['close'])) for t, a in per.items()}
    tx_ema = transaksi_porto(p, pasar)
    ev_tb = uji.jeda(p[((p['brk30'] == 1) & (p['prevrange30'] < 0.20) & (p['vspike'] > 2)).fillna(False) & p['elig']])
    tx_tb = KL.transaksi(ev_tb, per, pasar, 'TS10')
    rows = []
    for np_, (a, b) in PERIODE.items():
        for nama, tx in (('EMA10/20 mingguan', tx_ema), ('Tembus Basis+vol TS10', tx_tb)):
            s = tx[(tx['masuk'] >= a) & (tx['masuk'] <= b)]
            r = {'periode': np_, 'strategi': nama}
            r.update(KL.ringkas_tx(s))
            hasil = [KL.portofolio(s, kal, harga, seed=sd) for sd in range(N_SEED)]
            cg = np.array([h['CAGR%'] for h in hasil]); dd = np.array([h['maxDD%'] for h in hasil])
            r.update({'CAGR med': round(float(np.median(cg)), 1), 'CAGR min..max': '%.1f..%.1f' % (cg.min(), cg.max()),
                      'DD med': round(float(np.median(dd)), 1)})
            rows.append(r)
        bs = beli_semua(p, a, b)
        rows.append({'periode': np_, 'strategi': 'beli semua (tanpa ongkos)', 'CAGR med': bs['beli semua']})
        if 'IHSG' in bs:
            rows.append({'periode': np_, 'strategi': 'IHSG', 'CAGR med': bs['IHSG']})
    print('\nPORTOFOLIO 10 slot')
    print(pd.DataFrame(rows).set_index(['periode', 'strategi']).to_string())


if __name__ == '__main__':
    main()
