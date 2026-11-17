"""
Mencuri start: data luar negeri yang sudah FINAL sebelum IDX buka (09:00 WIB)
-- apakah menebak IHSG / saham hari itu? Dan yang lebih penting: apakah
tebakannya masih bisa DIAMBIL, atau sudah habis di harga pembukaan?

ATURAN WAKTU (inti seluruh uji)
  Untuk hari bursa IDX T (tutup sebelumnya Tp), fitur luar negeri =
  return kumulatif semua sesi bertanggal D dengan Tp <= D < T.
    - Sesi AS bertanggal D tutup 03:00-04:00 WIB tanggal D+1 -> sudah final
      sebelum IDX buka di T. Akhir pekan/libur otomatis terakumulasi.
    - Komoditas berjangka: settlement sore ET -> sama.
    - BTC (bar UTC) berakhir 07:00 WIB -> sama.
    - Bursa Asia bertanggal D berjalan BERSAMAAN dengan IDX D, jadi di sini
      yang terpakai cuma sesi Tp (kemarin) -- itu "kabar basi" yang sengaja
      ikut sebagai pembanding, bukan fitur pencuri start.
  Target di hari T:
    gap = ln(Open_T / Close_Tp)    -- TIDAK bisa diambil (sudah terjadi saat buka)
    oc  = ln(Close_T / Open_T)     -- BISA diambil: beli di pembukaan/pra-pembukaan
    cc  = ln(Close_T / Close_Tp)   -- = gap + oc, ukuran "selaras" biasa

UJI
  1. Korelasi tiap fitur vs gap / oc / cc, dipisah 2013-2019 vs 2020-2026.
  2. Kuintil fitur -> rata-rata oc & P(oc>0) di dua periode (lolos = searah
     dan monoton di keduanya).
  3. Saham dengan "kembaran" luar negeri (ADR, komoditas sektornya).

PEMAKAIAN
    python -m website.riset_pola_naik.lintas_pasar unduh
    python -m website.riset_pola_naik.lintas_pasar uji
"""
import os
import pickle
import sys

import numpy as np
import pandas as pd

from .panel import RESEARCH_CACHE

DIR = os.path.join(RESEARCH_CACHE, 'lintas_pasar')
GLOBAL_FILE = os.path.join(DIR, 'global_2012.pkl')
SAHAM_FILE = os.path.join(DIR, 'saham_2012.pkl')

ASIA = {'^N225', '^HSI', '^KS11', '^AXJO', '^STI', '000001.SS'}

# saham IDX -> fitur luar negeri yang secara bisnis "kembarannya"
KEMBAR = {
    'TLKM.JK': ['TLK', 'EIDO'],
    'BBCA.JK': ['EIDO'], 'BBRI.JK': ['EIDO'], 'BMRI.JK': ['EIDO'], 'ASII.JK': ['EIDO'],
    'ADRO.JK': ['MTF=F', 'NG=F', 'BZ=F'], 'PTBA.JK': ['MTF=F', 'NG=F', 'BZ=F'],
    'ITMG.JK': ['MTF=F', 'NG=F', 'BZ=F'], 'BUMI.JK': ['MTF=F', 'NG=F'],
    'ANTM.JK': ['GC=F', 'HG=F'], 'MDKA.JK': ['GC=F', 'HG=F'], 'INCO.JK': ['HG=F'],
    'MEDC.JK': ['BZ=F', 'CL=F'], 'ELSA.JK': ['BZ=F', 'CL=F'], 'AKRA.JK': ['BZ=F'],
    'AALI.JK': ['ZS=F', 'BZ=F'], 'LSIP.JK': ['ZS=F', 'BZ=F'],
}
SAHAM_UMUM = ['^GSPC', 'EIDO', '^VIX', 'IDR=X']


def unduh():
    import yfinance as yf
    os.makedirs(DIR, exist_ok=True)
    tick = list(KEMBAR)
    d = yf.download(tick, start='2012-01-01', auto_adjust=False, progress=False, group_by='ticker')
    out = {}
    for t in tick:
        x = d[t][['Open', 'High', 'Low', 'Close', 'Volume']].dropna(subset=['Close'])
        out[t] = x
        print(t, len(x))
    with open(SAHAM_FILE, 'wb') as fh:
        pickle.dump(out, fh)


def _muat():
    with open(GLOBAL_FILE, 'rb') as fh:
        g = pickle.load(fh)
    with open(SAHAM_FILE, 'rb') as fh:
        s = pickle.load(fh)
    return g['nama'], g['data'], s


def _bersih(x):
    """Buang bar hari ini yang belum selesai (volume 0 di hari terakhir) dan open rusak."""
    x = x[~x.index.duplicated(keep='last')].sort_index()
    x = x[(x['Close'] > 0) & (x['Open'] > 0)]
    if len(x) and x['Volume'].iloc[-1] == 0:
        x = x.iloc[:-1]
    return x


def target(x):
    x = _bersih(x)
    c, o = x['Close'], x['Open']
    t = pd.DataFrame(index=x.index)
    t['gap'] = np.log(o / c.shift(1))
    t['oc'] = np.log(c / o)
    t['cc'] = np.log(c / c.shift(1))
    t['tp'] = pd.Series(x.index, index=x.index).shift(1)
    # open = close kemarin persis -> open tidak informatif; hari itu dibuang dari uji oc/gap
    basi = (o - c.shift(1)).abs() < 1e-9 * c.shift(1)
    t.loc[basi, ['gap', 'oc']] = np.nan
    # loncatan mustahil (aksi korporasi / data rusak)
    t[(t['cc'].abs() > 0.35)] = np.nan
    return t.dropna(subset=['tp'])


def fitur(seri, t_index, tp):
    """Return kumulatif sesi bertanggal D, Tp <= D < T (lihat docstring)."""
    c = _bersih(seri)['Close']
    lc = np.log(c)
    # close terakhir dengan tanggal < T, dan < Tp
    pos_t = lc.index.searchsorted(t_index, side='left') - 1
    pos_p = lc.index.searchsorted(pd.DatetimeIndex(tp), side='left') - 1
    v = lc.to_numpy()
    ok = (pos_t >= 0) & (pos_p >= 0)
    f = np.full(len(t_index), np.nan)
    f[ok] = v[pos_t[ok]] - v[pos_p[ok]]
    # tak ada sesi baru sejak Tp -> 0, bukan NaN (mis. libur AS)
    return pd.Series(f, index=t_index)


def _periode(idx):
    return np.where(idx < pd.Timestamp('2020-01-01'), '2013-19', '2020-26')


def _korelasi(t, F, nama, judul):
    rows = []
    for k, f in F.items():
        r = {'fitur': nama.get(k, k) + (' (kemarin, basi)' if k in ASIA else '')}
        for per in ('2013-19', '2020-26'):
            m = (_periode(t.index) == per) & (t.index >= pd.Timestamp('2013-01-01'))
            for tg in ('gap', 'oc', 'cc'):
                s = pd.concat([f[m], t.loc[m, tg]], axis=1).dropna()
                r['%s %s' % (tg, per[2:])] = round(s.iloc[:, 0].corr(s.iloc[:, 1]), 3) if len(s) > 200 else None
        rows.append(r)
    df = pd.DataFrame(rows).set_index('fitur')
    df = df[['gap 13-19', 'gap 20-26', 'oc 13-19', 'oc 20-26', 'cc 13-19', 'cc 20-26']]
    print('\n--- ' + judul + ' -- korelasi (gap = sudah dibayar di pembukaan, oc = bisa diambil)')
    print(df.sort_values('cc 20-26', ascending=False, key=lambda s: s.abs()).to_string())
    return df


def _kuintil(t, f, label):
    rows = []
    for per in ('2013-19', '2020-26'):
        m = (_periode(t.index) == per) & (t.index >= pd.Timestamp('2013-01-01'))
        s = pd.concat([f[m].rename('f'), t.loc[m, ['gap', 'oc', 'cc']]], axis=1).dropna()
        if len(s) < 300:
            continue
        s['q'] = pd.qcut(s['f'].rank(method='first'), 5, labels=[1, 2, 3, 4, 5])
        for q, g in s.groupby('q', observed=True):
            rows.append({'periode': per, 'kuintil': int(q),
                         'fitur rata2 %': round(g['f'].mean() * 100, 2),
                         'gap %': round(g['gap'].mean() * 100, 3),
                         'oc %': round(g['oc'].mean() * 100, 3),
                         'P(oc>0) %': round((g['oc'] > 0).mean() * 100, 1),
                         'P(oc>0,4%) %': round((g['oc'] > 0.004).mean() * 100, 1),
                         'n': len(g)})
    print('\n--- kuintil ' + label)
    print(pd.DataFrame(rows).to_string(index=False))


def main_uji():
    nama, G, S = _muat()
    ih = target(G['^JKSE'])
    feats = {k: fitur(v, ih.index, ih['tp']) for k, v in G.items() if k != '^JKSE'}
    print('IHSG: %d hari, %s s.d. %s; gap/oc valid %d hari'
          % (len(ih), ih.index.min().date(), ih.index.max().date(), ih['oc'].notna().sum()))
    _korelasi(ih, feats, nama, 'IHSG')
    for k in ('^GSPC', 'EIDO', '^VIX', 'IDR=X'):
        _kuintil(ih, feats[k], 'IHSG <- %s semalam' % nama[k])

    print('\n' + '=' * 100 + '\nSAHAM DENGAN KEMBARAN LUAR NEGERI\n' + '=' * 100)
    rows = []
    for s, ks in KEMBAR.items():
        if s not in S:
            continue
        t = target(S[s])
        basi = 1 - t['oc'].notna().mean()
        for k in list(dict.fromkeys(ks + SAHAM_UMUM)):
            f = fitur(G[k], t.index, t['tp'])
            r = {'saham': s.replace('.JK', ''), 'fitur': nama[k], 'open basi %': round(basi * 100)}
            for per in ('2013-19', '2020-26'):
                m = (_periode(t.index) == per) & (t.index >= pd.Timestamp('2013-01-01'))
                for tg in ('gap', 'oc'):
                    x = pd.concat([f[m], t.loc[m, tg]], axis=1).dropna()
                    r['%s %s' % (tg, per[2:])] = round(x.iloc[:, 0].corr(x.iloc[:, 1]), 3) if len(x) > 200 else None
            rows.append(r)
    df = pd.DataFrame(rows)
    print(df.to_string(index=False))

    # yang paling menjanjikan dari tabel saham -> kuintil
    for s, k in (('TLKM.JK', 'TLK'), ('ADRO.JK', 'MTF=F'), ('ANTM.JK', 'GC=F'), ('MEDC.JK', 'BZ=F')):
        t = target(S[s])
        _kuintil(t, fitur(G[k], t.index, t['tp']), '%s <- %s' % (s, nama[k]))


if __name__ == '__main__':
    perintah = sys.argv[1] if len(sys.argv) > 1 else 'uji'
    if perintah == 'unduh':
        unduh()
    elif perintah == 'uji':
        main_uji()
    else:
        print(__doc__)
        sys.exit(2)
