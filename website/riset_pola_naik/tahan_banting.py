"""Saham tahan banting saat IHSG jatuh: episode historis + persistensi + episode sekarang."""
try:
    from ..runtime_paths import runtime_file as _runtime_file, market_file as _market_file, WEBSITE_DIR as _WEBSITE_DIR, PROJECT_DIR as _PROJECT_DIR, RUNTIME_DIR as _RUNTIME_DIR
except ImportError:
    from website.runtime_paths import runtime_file as _runtime_file, market_file as _market_file, WEBSITE_DIR as _WEBSITE_DIR, PROJECT_DIR as _PROJECT_DIR, RUNTIME_DIR as _RUNTIME_DIR
import os, sys, pickle, glob
import numpy as np, pandas as pd
from scipy.stats import spearmanr

WEB = str(_WEBSITE_DIR)
sys.path.insert(0, os.path.join(WEB, 'riset_pola_naik'))
import panel

SUMDIR = _market_file('Daily/Summary')
OUT = os.path.dirname(os.path.abspath(__file__))

_, harga = panel.sumber_harga()
ihsg = pickle.load(open(str(_runtime_file('', 'research_cache', 'ihsg_2010-01-01_2026-10-18.pkl')), 'rb'))
ihsg = ihsg[~ihsg.index.duplicated()]

C, V = {}, {}
for t, df in harga.items():
    df = df[df['Close'] > 0].sort_index()
    df = df[~df.index.duplicated(keep='last')]
    r = df['Close'].pct_change().abs()
    if (r > panel.LONCAT).any():          # loncatan mustahil -> potong pada titik rusak terakhir
        last_bad = r[r > panel.LONCAT].index[-1]
        df = df[df.index >= last_bad]
    C[t] = df['Close']; V[t] = df['Close'] * df['Volume'].fillna(0)
C = pd.DataFrame(C); V = pd.DataFrame(V)

# sambung 19 & 20 Okt dari Summary (rasio Summary sendiri dirantai ke close Yahoo 16 Okt)
ext = {}
for f in glob.glob(os.path.join(SUMDIR, '*_Summary.csv')):
    t = os.path.basename(f).split('_')[0]
    try:
        s = pd.read_csv(f, usecols=['Date', 'Close', 'Volume'])
    except Exception:
        continue
    s['Date'] = pd.to_datetime(s['Date'], format='%d-%b-%y', errors='coerce')
    s = s.dropna().set_index('Date').sort_index()
    s = s[~s.index.duplicated(keep='last')]
    if pd.Timestamp('2026-10-16') in s.index and s.index[-1] >= pd.Timestamp('2026-10-20'):
        ext[t] = s
for d in ['2026-10-19', '2026-10-20']:
    d = pd.Timestamp(d)
    C.loc[d] = np.nan; V.loc[d] = np.nan
    for t, s in ext.items():
        if t in C and d in s.index and not np.isnan(C.at[pd.Timestamp('2026-10-16'), t]):
            C.at[d, t] = C.at[pd.Timestamp('2026-10-16'), t] * s.at[d, 'Close'] / s.at[pd.Timestamp('2026-10-16'), 'Close']
            V.at[d, t] = s.at[d, 'Close'] * s.at[d, 'Volume']
ihsg.loc[pd.Timestamp('2026-10-19')] = 4996.608887
ihsg.loc[pd.Timestamp('2026-10-20')] = 5278.888184
C = C.sort_index(); V = V.sort_index()

def trough_after(a, b):
    x = ihsg[a:b]; p = x.idxmax(); return p, x[p:].idxmin()

EPS = [
    ('2011', '2011-07-01', '2011-12-31'),
    ('2013', '2013-05-01', '2013-12-31'),
    ('2015', '2015-03-01', '2015-12-31'),
    ('2018', '2018-01-01', '2018-12-31'),
    ('2020', '2019-12-01', '2020-06-30'),
    ('2024-25', '2024-09-01', '2025-06-30'),
    ('2026a', '2026-01-01', '2026-06-30'),
    ('2026b', '2026-08-15', '2026-10-20'),
]
eps = []
for nama, a, b in EPS:
    p, tr = trough_after(a, b)
    eps.append((nama, p, tr, ihsg[tr] / ihsg[p] - 1))

def at(df, d):
    i = df.index.searchsorted(d, side='right') - 1
    return df.iloc[i]

hasil = {}
for nama, p, tr, ri in eps:
    c0, c1 = at(C, p), at(C, tr)
    # likuid: median nilai 60 hari sebelum puncak >= Rp1 M, dan sudah punya >=250 hari data
    win = V.loc[:p].tail(60)
    liq = win.median()
    hist = C.loc[:p].notna().sum()
    ok = (liq >= 1e9) & (hist >= 250) & c0.notna() & c1.notna()
    # beta 1 thn sebelum puncak (return mingguan)
    w = C.loc[:p].tail(260).resample('W-FRI').last().pct_change()
    wi = ihsg.loc[:p].tail(260).resample('W-FRI').last().pct_change()
    beta = w.apply(lambda s: s.cov(wi) / wi.var() if s.notna().sum() >= 40 else np.nan)
    # pemulihan 60 hari bursa setelah dasar
    after = C.loc[tr:].iloc[:61]
    rec = after.iloc[-1] / after.iloc[0] - 1 if len(after) >= 61 else pd.Series(np.nan, index=C.columns)
    irec = ihsg.loc[tr:].iloc[:61]; irec = irec.iloc[-1] / irec.iloc[0] - 1 if len(irec) >= 61 else np.nan
    df = pd.DataFrame({'ret': c1 / c0 - 1, 'beta': beta, 'liq': liq, 'rec60': rec})[ok]
    df['rel'] = df['ret'] - ri
    hasil[nama] = (df, ri, irec)
    print(f'{nama:8s} puncak {p.date()} dasar {tr.date()} IHSG {ri*100:+.1f}%  n={len(df):3d}  '
          f'median saham {df.ret.median()*100:+.1f}%  naik/rata: {(df.ret>=0).mean()*100:.0f}%  '
          f'IHSG 60h stlh dasar {irec*100 if irec==irec else float("nan"):+.1f}%')

print('\n== Persistensi: rel episode k vs episode k+1 (Spearman), dan kuintil ==')
names = [e[0] for e in eps]
rows = []
for a, b in zip(names[:-1], names[1:]):
    A, B = hasil[a][0], hasil[b][0]
    j = A.index.intersection(B.index)
    rho = spearmanr(A.loc[j, 'rel'], B.loc[j, 'rel']).correlation
    rb = spearmanr(B.loc[j, 'beta'], B.loc[j, 'rel']).correlation
    q = pd.qcut(A.loc[j, 'rel'].rank(method='first'), 5, labels=False)
    top = B.loc[j][q == 4]['ret'].median(); bot = B.loc[j][q == 0]['ret'].median(); allm = B.loc[j, 'ret'].median()
    qb = pd.qcut(B.loc[j, 'beta'].rank(method='first'), 5, labels=False)
    lowb = B.loc[j][qb == 0]['ret'].median(); highb = B.loc[j][qb == 4]['ret'].median()
    print(f'{a:>8s} -> {b:8s} n={len(j):3d}  rho(tahan->tahan)={rho:+.2f}  rho(beta->rel)={rb:+.2f} | '
          f'episode {b}: Q5 tahan-lalu {top*100:+.1f}%  Q1 {bot*100:+.1f}%  semua {allm*100:+.1f}%  '
          f'| beta rendah {lowb*100:+.1f}%  beta tinggi {highb*100:+.1f}%')

print('\n== Setelah dasar: yg tahan vs yg hancur, 60 hari bursa ==')
for nama in names:
    df, ri, irec = hasil[nama]
    d = df.dropna(subset=['rec60'])
    if len(d) < 50: continue
    q = pd.qcut(d['rel'].rank(method='first'), 5, labels=False)
    print(f'{nama:8s} Q5 tahan {d[q==4].rec60.median()*100:+.1f}%  Q1 hancur {d[q==0].rec60.median()*100:+.1f}%  '
          f'semua {d.rec60.median()*100:+.1f}%  rho={spearmanr(d.rel, d.rec60).correlation:+.2f}')

pickle.dump((eps, hasil), open(str(_runtime_file('riset_pola_naik', 'tahan_banting.pkl')), 'wb'))
