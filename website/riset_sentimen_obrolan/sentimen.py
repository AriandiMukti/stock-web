"""Komen negatif per hari (Telegram + Stockbit) vs IHSG H+1, H+5, H+20."""
try:
    from ..runtime_paths import runtime_file as _runtime_file, market_file as _market_file, WEBSITE_DIR as _WEBSITE_DIR, PROJECT_DIR as _PROJECT_DIR, RUNTIME_DIR as _RUNTIME_DIR
except ImportError:
    from website.runtime_paths import runtime_file as _runtime_file, market_file as _market_file, WEBSITE_DIR as _WEBSITE_DIR, PROJECT_DIR as _PROJECT_DIR, RUNTIME_DIR as _RUNTIME_DIR
import glob, os, re, sys, pickle
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
NEG = r'''turun|turunn+|anjlok|longsor|ambruk|ambrol|jeblok|nyungsep|rontok|crash|dump|dumping|merah|memerah|kebakaran|
berdarah|bloodbath|arb|nyangkut|nyangkut|boncos|rugi|loss|cutloss|cut loss|panik|panic|takut|hancur|bubar|rungkad|
nangis|terjun|koreksi|bearish|guyur|diguyur|distribusi|kabur|net ?sell|nyerah|stres|stress|sedih|ancur|anjir turun|
nyungsep|amblas|ambles|tenggelam|downtrend|breakdown|jebol|minus|nyangsang|mewek|kapok|trauma|kiamat|resesi|krisis|
collapse|halt|trading halt|hancurr|mati|nyesel|nyesal|apes|sial|zonk|tipu|scam|pom pom|pompom|gorengan buang|buang barang'''
POS = r'''naik|ijo|hijau|ara|cuan|profit|rebound|mantul|terbang|to the moon|bullish|akumulasi|borong|mantap|untung|
take profit|tp|hajar|meroket|melesat|breakout|uptrend|gacor|moon|pantul|mantab|menguat|rally|reli|hijau royo|ath|all time high'''
EMO_NEG = '😭😱💀🩸📉😢😰😩😫🥲🤬😡'
EMO_POS = '🚀📈🔥💰🤑😍🥳'
RNEG = re.compile(r'(?<![a-z])(' + NEG.replace('\n', '') + r')(?![a-z])')
RPOS = re.compile(r'(?<![a-z])(' + POS.replace('\n', '') + r')(?![a-z])')


def skor(teks):
    t = str(teks).lower()
    n = len(RNEG.findall(t)) + sum(t.count(e) for e in EMO_NEG)
    p = len(RPOS.findall(t)) + sum(t.count(e) for e in EMO_POS)
    return n, p


def hari_bursa(waktu, kal):
    """Pesan sebelum 16:00 WIB hari bursa D -> D; sesudahnya / akhir pekan -> hari bursa berikutnya."""
    w = pd.to_datetime(waktu)
    geser = (w - pd.Timedelta(hours=16)).dt.normalize() + pd.Timedelta(days=1)   # >=16:00 maju sehari
    idx = np.searchsorted(kal.values, geser.values)                                # hari bursa >= tanggal itu
    ok = idx < len(kal)
    out = pd.Series(pd.NaT, index=w.index)
    out[ok] = kal.values[idx[ok]]
    return out


def muat_ihsg():
    s = pd.read_pickle(str(_runtime_file("", 'research_cache/ihsg_2010-01-01_2026-10-18.pkl')))
    s.index = pd.to_datetime(s.index).tz_localize(None).normalize()
    return s.dropna()


def harian(df, kal):
    df = df[df.teks.astype(str).str.len() > 2].copy()
    sk = df.teks.map(skor)
    df['n'] = [a for a, b in sk]; df['p'] = [b for a, b in sk]
    df['neg'] = (df.n > df.p).astype(int); df['pos'] = (df.p > df.n).astype(int)
    df['D'] = hari_bursa(df.waktu, kal)
    g = df.dropna(subset=['D']).groupby('D').agg(pesan=('neg', 'size'), neg=('neg', 'sum'), pos=('pos', 'sum'))
    g['porsi_neg'] = g.neg / g.pesan
    g['bersih'] = (g.pos - g.neg) / (g.pos + g.neg).clip(lower=1)
    return g, df


H = [1, 2, 3, 5, 10, 20]


def gabung_ihsg(g, ihsg):
    df = pd.DataFrame({'c': ihsg})
    df['r0'] = df.c.pct_change() * 100
    df['r5lalu'] = (df.c / df.c.shift(5) - 1) * 100
    for h in H:
        df['f%d' % h] = (df.c.shift(-h) / df.c - 1) * 100
    return g.join(df, how='inner')


def zskor(s, jendela=60):
    """z terhadap 60 hari bursa SEBELUMNYA saja (tanpa intip masa depan)."""
    m = s.shift(1).rolling(jendela, min_periods=30).mean()
    sd = s.shift(1).rolling(jendela, min_periods=30).std()
    return (s - m) / sd


def nw(y, X, lag):
    import statsmodels.api as sm
    X = sm.add_constant(X)
    ok = y.notna() & X.notna().all(axis=1)
    r = sm.OLS(y[ok], X[ok]).fit(cov_type='HAC', cov_kwds={'maxlags': lag})
    return r
