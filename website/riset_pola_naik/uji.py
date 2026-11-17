"""
Uji pola di panel Yahoo -- pencarian vs validasi, ketahanan, penajaman.

  Pencarian = separuh emiten A x sinyal 2013-2019
  Validasi  = separuh emiten B x sinyal 2020-2026   (periode DAN semesta terpisah)

Tiap angka dibandingkan dengan pembanding HARI YANG SAMA: untuk tiap
kejadian, pembandingnya apa yang dilakukan semua emiten layak dari hari itu.
Pola yang cuma muncul di pasar naik tidak mendapat kredit dari pasarnya.
Return diringkas sebagai selisih MAJEMUK (rata-rata log), bukan aritmetik.

PEMAKAIAN: python -m website.riset_pola_naik.uji {pola|ketahanan|penajaman|validasi|cek-setara}
"""
import hashlib
import os
import sys
import warnings

import numpy as np
import pandas as pd

from . import panel as PN

warnings.filterwarnings('ignore', category=FutureWarning)

JEDA = 20
MIN_NILAI = float(os.environ.get('MIN_NILAI', 1e9))     # median nilai harian (Rp)
MIN_HARGA = float(os.environ.get('MIN_HARGA', 100))


def muat():
    p = PN.bangun()
    p = p[p['date'] >= '2012-06-01'].reset_index(drop=True)
    g = p.groupby('ticker', sort=False)
    p['ret1'] = g['close'].pct_change()
    p['prevrange60'] = g['range60'].shift(1)
    p['up_low20_prev'] = g['up_low20'].shift(1)
    p['dd20h'] = p['close'] / g['close'].transform(lambda s: s.rolling(20, min_periods=20).max()) - 1
    p['dd20h_prev'] = p.groupby('ticker', sort=False)['dd20h'].shift(1)
    p['elig'] = ((p['hist'] >= 260) & (p['close'] >= MIN_HARGA) & (p['medval20'] >= MIN_NILAI)
                 & (p['traded30'] >= 0.9) & (p['bad_back60'] == 0) & (p['date'] >= '2013-01-01'))
    p['half'] = p['ticker'].map(lambda t: int(hashlib.md5(t.encode()).hexdigest(), 16) % 2)
    p['period'] = np.where(p['date'] < '2020-01-01', 1, 2)
    p['month'] = p['date'].dt.to_period('M')

    # peringkat antar-emiten layak, per tanggal
    e = p['elig']
    for col in ('ret120', 'vol20'):
        p[col + '_cs'] = np.nan
        p.loc[e, col + '_cs'] = p.loc[e].groupby('date')[col].rank(pct=True)

    # pembanding hari yang sama: semua emiten layak di tanggal itu
    q = p.loc[e, ['date', 'fwd20', 'fwd60', 'fp60']].copy()
    q['lr20'] = np.log1p(q['fwd20']); q['lr60'] = np.log1p(q['fwd60'])
    q['p10'] = (q['fwd20'] >= 0.10).where(q['fwd20'].notna())
    q['win'] = (q['fwd20'] > 0).where(q['fwd20'].notna())
    q['p20_60'] = (q['fwd60'] >= 0.20).where(q['fwd60'].notna())
    q['fpup'] = (q['fp60'] == 1).where(q['fp60'].notna())
    q['fpdn'] = (q['fp60'] == -1).where(q['fp60'].notna())
    b = q.groupby('date')[['lr20', 'lr60', 'p10', 'win', 'p20_60', 'fpup', 'fpdn']].mean()
    b.columns = ['b_' + c for c in b.columns]
    p = p.merge(b, left_on='date', right_index=True, how='left')
    # harus 0: tanggal tanpa satu pun emiten layak = bendera elig bolong se-pasar
    # (dulu 41/87/91 tanggal di 2017/2018/2019, lihat panel.tanpa_libur)
    nol = int((p[p['date'] >= '2013-01-01'].groupby('date')['elig'].sum() == 0).sum())
    print('emiten-hari layak: %d | emiten: %d | tanggal tanpa emiten layak: %d'
          % (int(p['elig'].sum()), p.loc[p['elig'], 'ticker'].nunique(), nol), flush=True)
    return p


def jeda(rows, gap=JEDA):
    """Paling banyak satu kejadian per emiten per `gap` bar (yang pertama menang)."""
    rows = rows.sort_values(['ticker', 'hist'])
    t = rows['ticker'].to_numpy(); h = rows['hist'].to_numpy()
    keep = np.zeros(len(rows), bool)
    last_t, last_h = None, -10 ** 9
    for i in range(len(rows)):
        if t[i] != last_t:
            last_t, last_h = t[i], -10 ** 9
        if h[i] - last_h >= gap:
            keep[i] = True
            last_h = h[i]
    return rows[keep]


def t_klaster(x, groups):
    """Nilai t dengan galat baku dikelompokkan (per bulan): kejadian di bulan
    yang sama saling berkorelasi, jadi t biasa terlalu optimistis."""
    x = np.asarray(x, float); ok = np.isfinite(x)
    x, groups = x[ok], np.asarray(groups)[ok]
    n = len(x)
    if n < 30:
        return np.nan
    m = x.mean(); e = x - m
    s = pd.Series(e).groupby(groups).sum().to_numpy()
    se = np.sqrt((s ** 2).sum()) / n
    return m / se if se > 0 else np.nan


def statistik(ev):
    out = {'n': len(ev), 'stocks': ev['ticker'].nunique(), 'months': ev['month'].nunique()}
    f = ev[ev['fwd20'].notna()]
    if len(f) >= 30:
        lr = np.log1p(f['fwd20'])
        out['p10'] = (f['fwd20'] >= 0.10).mean() * 100
        out['p10_base'] = f['b_p10'].mean() * 100
        out['win'] = (f['fwd20'] > 0).mean() * 100
        out['win_base'] = f['b_win'].mean() * 100
        out['exc20'] = (np.exp((lr - f['b_lr20']).mean()) - 1) * 100
        out['t20'] = t_klaster(lr - f['b_lr20'], f['month'].astype(str))
        out['comp20'] = (np.exp(lr.mean()) - 1) * 100
        out['med20'] = f['fwd20'].median() * 100
    f = ev[ev['fwd60'].notna()]
    if len(f) >= 30:
        lr = np.log1p(f['fwd60'])
        out['p20_60'] = (f['fwd60'] >= 0.20).mean() * 100
        out['p20_60_base'] = f['b_p20_60'].mean() * 100
        out['exc60'] = (np.exp((lr - f['b_lr60']).mean()) - 1) * 100
        out['t60'] = t_klaster(lr - f['b_lr60'], f['month'].astype(str))
    f = ev[ev['fp60'].notna()]
    if len(f) >= 30:
        out['fpup'] = (f['fp60'] == 1).mean() * 100
        out['fpup_base'] = f['b_fpup'].mean() * 100
        out['fpdn'] = (f['fp60'] == -1).mean() * 100
        out['fpdn_base'] = f['b_fpdn'].mean() * 100
    return out


def pola(r):
    """Semua pola yang diuji putaran pertama -- didaftar SEBELUM validasi dilihat."""
    P = {}
    P['ALL eligible days'] = pd.Series(True, index=r.index)
    # --- A. tenang (contoh di pertanyaan aslinya) ---
    P['A1 steady: 30d range <10%'] = r['range30'] < 0.10
    P['A2 steady: 30d range <15%'] = r['range30'] < 0.15
    P['A3 steady: 30d range <20%'] = r['range30'] < 0.20
    P['A4 vol squeeze: vol20 in own lowest 10% (1y)'] = r['vol20pct'] <= 0.10
    P['A5 ATR contraction: ATR10/ATR60 <0.6'] = r['atrratio'] < 0.6
    P['A6 low vol vs market: vol20 bottom decile'] = r['vol20_cs'] <= 0.10
    # --- B. tenang + konteks ---
    s20 = r['range30'] < 0.20
    P['B1 steady20 after +30% run-up (flag)'] = s20 & (r['into_base'] > 0.30)
    P['B2 steady20 after -25% decline (basing)'] = s20 & (r['into_base'] < -0.25)
    P['B3 steady20 near 52w high (dd250>-10%)'] = s20 & (r['dd250'] > -0.10)
    P['B4 steady20 near 52w low (dd250<-40%)'] = s20 & (r['dd250'] < -0.40)
    P['B5 steady20 + volume dry-up (vdry<0.5)'] = s20 & (r['vdry'] < 0.5)
    P['B6 steady20 + above MA200'] = s20 & (r['ma200'] > 0)
    # --- C. tembus DARI basis tenang ---
    P['C1 break 30d high after base<20%'] = (r['brk30'] == 1) & (r['prevrange30'] < 0.20)
    P['C2 C1 + volume >2x'] = (r['brk30'] == 1) & (r['prevrange30'] < 0.20) & (r['vspike'] > 2)
    P['C3 C2 + close near day high'] = (r['brk30'] == 1) & (r['prevrange30'] < 0.20) & (r['vspike'] > 2) & (r['day_pos'] > 0.7)
    P['C4 break 60d high after 60d base<30%'] = (r['brk60'] == 1) & (r['prevrange60'] < 0.30)
    P['C5 break 30d high + volume >2x (any base)'] = (r['brk30'] == 1) & (r['vspike'] > 2)
    # --- D. momentum ---
    P['D1 new 52w closing high'] = r['hi250'] == 1
    P['D2 new 52w high + volume >2x'] = (r['hi250'] == 1) & (r['vspike'] > 2)
    P['D3 6m return top decile'] = r['ret120_cs'] >= 0.90
    P['D4 MA stack C>MA20>MA50>MA200'] = (r['ma20'] > 0) & (r['ma50'] > r['ma20']) & (r['ma200'] > r['ma50'])
    P['D5 +10% off 20d low (first day)'] = (r['up_low20'] >= 0.10) & (r['up_low20_prev'] < 0.10)
    P['D6 already +20% in 20d'] = r['ret20'] > 0.20
    # --- E. berbalik dari jatuh ---
    P['E1 down >40% from 60d peak'] = r['dd60'] <= -0.40
    P['E2 E1 + still volatile (20d range>=25%)'] = (r['dd60'] <= -0.40) & (r['range20'] >= 0.25)
    P['E3 down 60-70% from 60d peak'] = (r['dd60'] <= -0.60) & (r['dd60'] > -0.70)
    P['E4 5-day drop >15%'] = r['ret5'] <= -0.15
    P['E5 RSI14 <25'] = r['rsi14'] < 25
    P['E6 -10% off 20d high (first day)'] = (r['dd20h'] <= -0.10) & (r['dd20h_prev'] > -0.10)
    # --- F. volume / aksi harga ---
    P['F1 volume >3x on strong up-day'] = (r['vspike'] > 3) & (r['ret1'] > 0.03) & (r['day_pos'] > 0.7)
    P['F2 volume >3x, price flat (|1d|<2%)'] = (r['vspike'] > 3) & (r['ret1'].abs() < 0.02)
    P['F3 volume dry-up alone (vdry<0.4)'] = r['vdry'] < 0.4
    P['F4 high vol: vol20 top decile'] = r['vol20_cs'] >= 0.90
    return P


def sel(p):
    return {
        'PENCARIAN (separuh A, 2013-2019)': (p['half'] == 0) & (p['period'] == 1),
        'VALIDASI (separuh B, 2020-2026)': (p['half'] == 1) & (p['period'] == 2),
        'silang: separuh B, 2013-2019': (p['half'] == 1) & (p['period'] == 1),
        'silang: separuh A, 2020-2026': (p['half'] == 0) & (p['period'] == 2),
    }


def jalankan(p, masks, label):
    rows = []
    for name, m in masks.items():
        s = statistik(jeda(p[m.fillna(False) & p['elig'] & label]))
        s['pattern'] = name
        rows.append(s)
    return pd.DataFrame(rows).set_index('pattern')


def tampil(df, title):
    d = pd.DataFrame(index=df.index)
    d['n'] = df['n']
    d['P(+10%/20d)'] = df['p10'].round(1)
    d['base'] = df['p10_base'].round(1)
    d['lift'] = (df['p10'] - df['p10_base']).round(1)
    d['up-first'] = df['fpup'].round(1)
    d['base '] = df['fpup_base'].round(1)
    d['lift '] = (df['fpup'] - df['fpup_base']).round(1)
    d['exc20%'] = df['exc20'].round(2)
    d['t20'] = df['t20'].round(1)
    d['exc60%'] = df['exc60'].round(2)
    d['t60'] = df['t60'].round(1)
    d['P(+20%/60d)'] = df['p20_60'].round(1)
    d['base  '] = df['p20_60_base'].round(1)
    print('\n' + '=' * 150 + '\n' + title + '\n' + '=' * 150)
    print(d.to_string())


# ---------------------------------------------------------------------------
def cmd_pola(p):
    masks = pola(p)
    for title, lab in sel(p).items():
        tampil(jalankan(p, masks, lab), title)


KUNCI = ['ALL eligible days', 'A2 steady: 30d range <15%', 'B3 steady20 near 52w high (dd250>-10%)',
         'C1 break 30d high after base<20%', 'C2 C1 + volume >2x', 'C3 C2 + close near day high',
         'C5 break 30d high + volume >2x (any base)', 'D1 new 52w closing high', 'D2 new 52w high + volume >2x',
         'D4 MA stack C>MA20>MA50>MA200', 'E1 down >40% from 60d peak', 'E2 E1 + still volatile (20d range>=25%)',
         'E6 -10% off 20d high (first day)', 'F4 high vol: vol20 top decile']


def _exc(ev, col, base):
    f = ev[ev[col].notna()]
    if len(f) < 20:
        return np.nan
    return (np.exp((np.log1p(f[col]) - f[base]).mean()) - 1) * 100


def cmd_ketahanan(p):
    M = pola(p)
    p['year'] = p['date'].dt.year
    print('\n### 1. vs pasar hari yang sama, 60 hari, per tahun sinyal (semua emiten)')
    rows = {}
    for k in KUNCI:
        ev = jeda(p[M[k].fillna(False) & p['elig']])
        rows[k] = {y: _exc(g, 'fwd60', 'b_lr60') for y, g in ev.groupby('year')}
    yy = pd.DataFrame(rows).T.round(1)
    yy['tahun+'] = (yy > 0).sum(1).astype(str) + '/' + yy.notna().sum(1).astype(str)
    print(yy.to_string())

    print('\n### 2. per lapis likuiditas: exc20 / exc60 / lift P(+10%/20h) / n')
    lapis = {'Rp1-5M': (1e9, 5e9), 'Rp5-20M': (5e9, 20e9), '>Rp20M': (20e9, 1e15)}
    out = {}
    for k in KUNCI:
        r = {}
        for tn, (lo, hi) in lapis.items():
            s = statistik(jeda(p[M[k].fillna(False) & p['elig'] & (p['medval20'] >= lo) & (p['medval20'] < hi)]))
            r[tn] = '%+.1f / %+.1f / %+.1f / %d' % (s.get('exc20', np.nan), s.get('exc60', np.nan),
                                                   s.get('p10', np.nan) - s.get('p10_base', np.nan), s['n'])
        out[k] = r
    print(pd.DataFrame(out).T.to_string())

    print('\n### 3. per rezim (IHSG vs MA200 saat sinyal): exc60 / lift P(+10%/20h) / n')
    out = {}
    for k in KUNCI:
        r = {}
        for tn, cond in {'IHSG > MA200': p['ihsg_ma200'] > 0, 'IHSG < MA200': p['ihsg_ma200'] <= 0}.items():
            s = statistik(jeda(p[M[k].fillna(False) & p['elig'] & cond]))
            r[tn] = '%+.1f / %+.1f / %d' % (s.get('exc60', np.nan), s.get('p10', np.nan) - s.get('p10_base', np.nan), s['n'])
        out[k] = r
    print(pd.DataFrame(out).T.to_string())


def cmd_penajaman(p):
    g = p.groupby('ticker', sort=False)
    p['dd250_prev'] = g['dd250'].shift(1)
    base = (p['brk30'] == 1) & (p['prevrange30'] < 0.20)
    brk_vol = base & (p['vspike'] > 2)
    R = {
        'ref: ALL eligible days': pd.Series(True, index=p.index),
        'C2 base<20% breakout + vol>2x (round 1)': brk_vol,
        'D2 new 52w high + vol>2x (round 1)': (p['hi250'] == 1) & (p['vspike'] > 2),
        'R1 C2 AND new 52w high': brk_vol & (p['hi250'] == 1),
        'R2 C2 AND base sat within 10% of 52w high': brk_vol & (p['dd250_prev'] > -0.10),
        'R3 C2 AND above MA200': brk_vol & (p['ma200'] > 0),
        'R4 base<20% breakout + vol>3x': base & (p['vspike'] > 3),
        'R5 base<15% breakout + vol>2x': (p['brk30'] == 1) & (p['prevrange30'] < 0.15) & (p['vspike'] > 2),
        'R6 C2 but NOT new 52w high': brk_vol & (p['hi250'] == 0),
    }
    print('\nCATATAN: varian ini didaftar SESUDAH validasi putaran pertama dilihat -- bukti lebih lemah.')
    for title, lab in sel(p).items():
        tampil(jalankan(p, R, lab), title)


def cmd_validasi(p):
    """Tabel utama tembus_basis.BUKTI['validasi'] (sel validasi saja)."""
    base_brk = (p['brk30'] == 1) & (p['prevrange30'] < 0.20) & (p['vspike'] > 2)
    S = {
        'semua hari (pembanding)': pd.Series(True, index=p.index),
        'tenang: rentang 30h <15%': p['range30'] < 0.15,
        'tenang: rentang 30h <10%': p['range30'] < 0.10,
        'tembus basis <20% + vol>2x': base_brk,
        'puncak 52 minggu + vol>2x': (p['hi250'] == 1) & (p['vspike'] > 2),
        'keduanya sekaligus *': base_brk & (p['hi250'] == 1),
        'Jatuh Dalam (dd60<=-40%, bergejolak)': (p['dd60'] <= -0.40) & (p['range20'] >= 0.25),
    }
    val = (p['half'] == 1) & (p['period'] == 2)
    rows = []
    for k, m in S.items():
        ev = jeda(p[m.fillna(False) & p['elig'] & val])
        f20 = ev[ev['fwd20'].notna()]; f60 = ev[ev['fwd60'].notna()]; fp = ev[ev['fp60'].notna()]
        hit = fp[fp['fp60'] != 0]
        rows.append({
            'pola': k, 'n': len(f20),
            'naik 60h %': round((f60['fwd60'] > 0).mean() * 100, 1),
            'P(>=+10% @20h)': round((f20['fwd20'] >= .10).mean() * 100, 1),
            'P(<=-10% @20h)': round((f20['fwd20'] <= -.10).mean() * 100, 1),
            '+10% sblm -10%': round((hit['fp60'] == 1).mean() * 100, 1),
            'median 60h %': round(f60['fwd60'].median() * 100, 1),
            'vs pasar 60h %': round((np.exp((np.log1p(f60['fwd60']) - f60['b_lr60']).mean()) - 1) * 100, 1),
            't60': round(t_klaster(np.log1p(f60['fwd60']) - f60['b_lr60'], f60['month'].astype(str)), 1),
        })
    print(pd.DataFrame(rows).set_index('pola').to_string())
    print('* dipilih sesudah validasi dilihat')


def cmd_cek_setara():
    """
    tembus_basis.fitur() (dipakai halaman) HARUS memberi sinyal yang sama
    persis dengan rumus riset. Kalau suatu saat salah satunya diubah tanpa
    yang lain, halaman menampilkan aturan yang tidak pernah diuji -- cek ini
    yang menangkapnya. Dijalankan pada input Yahoo yang IDENTIK, tanpa tanggal
    libur (sama dengan yang dipakai riset; data halaman memang tidak punya
    baris libur -- kalendernya dari berkas Summary).
    """
    from .. import tembus_basis as TB
    data, _ = PN.tanpa_libur(PN.sumber_harga()[1])
    tickers = sorted(data)[::15]
    beda = total = n_sinyal = 0
    for t in tickers:
        r = PN.fitur(t, data[t])
        if r is None:
            continue
        df = data[t][['Open', 'High', 'Low', 'Close', 'Volume']]
        df = df[df['Close'] > 0].sort_index()
        df = df[~df.index.duplicated(keep='last')]
        f = TB.fitur(df)
        layak = ((r['hist'] >= TB.C['MIN_RIWAYAT']) & (r['close'] >= TB.C['MIN_HARGA'])
                 & (r['medval20'] >= TB.C['MIN_NILAI']) & (r['traded30'] >= TB.C['MIN_AKTIF'])
                 & (r['bad_back60'] == 0))
        rb = layak & (r['brk30'] == 1) & (r['prevrange30'] < TB.C['BASIS_MAX']) & (r['vspike'] > TB.C['VOL_X'])
        rp = layak & (r['hi250'] == 1) & (r['vspike'] > TB.C['VOL_X'])
        for a, b in ((layak, f['layak']), (rb, f['s_basis']), (rp, f['s_puncak'])):
            total += len(a)
            beda += int((a.fillna(False).astype(bool).to_numpy() != b.astype(bool).to_numpy()).sum())
        n_sinyal += int(rb.sum() + rp.sum())
    print('%d emiten diperiksa, %d hari sinyal: %d beda dari %d bendera -> %s'
          % (len(tickers), n_sinyal, beda, total, 'SETARA' if beda == 0 else 'TIDAK SETARA'))
    return beda == 0


if __name__ == '__main__':
    perintah = sys.argv[1] if len(sys.argv) > 1 else 'pola'
    if perintah == 'cek-setara':
        sys.exit(0 if cmd_cek_setara() else 1)
    fungsi = {'pola': cmd_pola, 'ketahanan': cmd_ketahanan,
              'penajaman': cmd_penajaman, 'validasi': cmd_validasi}.get(perintah)
    if fungsi is None:
        print(__doc__)
        sys.exit(2)
    fungsi(muat())
