try:
    from ..runtime_paths import runtime_file as _runtime_file, market_file as _market_file, WEBSITE_DIR as _WEBSITE_DIR, PROJECT_DIR as _PROJECT_DIR, RUNTIME_DIR as _RUNTIME_DIR
except ImportError:
    from website.runtime_paths import runtime_file as _runtime_file, market_file as _market_file, WEBSITE_DIR as _WEBSITE_DIR, PROJECT_DIR as _PROJECT_DIR, RUNTIME_DIR as _RUNTIME_DIR
import os, sys
import numpy as np, pandas as pd
from sentimen import *

HERE = os.path.dirname(os.path.abspath(__file__))
pd.set_option('display.width', 220); pd.set_option('display.max_columns', 30)
ih = muat_ihsg(); kal = pd.Series(ih.index)
from website.runtime_paths import research_groups
BELAH = {row['archive']:row['split'] for row in research_groups(required=True)}


def muat_grup(nama):
    d = pd.read_pickle(str(_runtime_file('riset_sentimen_obrolan', 'tg_hist', nama + '.pkl')))
    d['waktu'] = pd.to_datetime(d.waktu, utc=True).dt.tz_convert('Asia/Jakarta').dt.tz_localize(None)
    d = d.drop_duplicates('id')
    d['Dw'] = hari_bursa(d.waktu, kal)
    d = d[d.Dw == d.D]                      # buang pesan yg sebenarnya milik hari bursa sebelumnya
    return d


def ringkas(x, label):
    """x: tabel harian berisi z (negativitas), r0, r5lalu, f*."""
    print('\n==== %s | %d hari | %s s/d %s' % (label, len(x), x.index.min().date(), x.index.max().date()))
    x = x.dropna(subset=['z'])
    x['kel'] = pd.qcut(x.z, 5, labels=['Q1 paling positif', 'Q2', 'Q3', 'Q4', 'Q5 paling negatif'])
    t = x.groupby('kel', observed=True)[['z', 'r0'] + ['f%d' % h for h in H]].mean().round(2)
    t['win_f1'] = x.groupby('kel', observed=True).f1.apply(lambda s: (s > 0).mean() * 100).round(0)
    t['n'] = x.groupby('kel', observed=True).size()
    print(t)
    # regresi: kendalikan return hari itu & 5 hari lalu (komen negatif biasanya MENGIKUTI harga turun)
    out = {}
    for h in H:
        if x['f%d' % h].notna().sum() < 40:
            continue
        r = nw(x['f%d' % h], x[['z', 'r0', 'r5lalu']], lag=max(h, 1))
        out['H+%d' % h] = '%+.3f (t %+.1f)' % (r.params['z'], r.tvalues['z'])
    print('koef z (per 1 sd negativitas), kendali r0 & r5lalu:', out)
    return t


def ekstrem(x, label, q=0.95):
    """Hari paling negatif (top 5%) vs hari dengan return hari-itu yang mirip."""
    x = x.dropna(subset=['z', 'f20']).copy()
    ambang = x.z.quantile(q)
    x['ek'] = x.z >= ambang
    x['bin_r0'] = pd.qcut(x.r0, 10, labels=False, duplicates='drop')
    baris = []
    for h in H:
        sel = x[x.ek]
        pemb = x[~x.ek].groupby('bin_r0')['f%d' % h].mean()
        harap = sel.bin_r0.map(pemb)
        baris.append((h, sel['f%d' % h].mean(), harap.mean(), (sel['f%d' % h] - harap).mean(),
                      (sel['f%d' % h] > 0).mean() * 100, x['f%d' % h].mean()))
    print('\n-- %s: hari top %.0f%% negatif (n=%d) vs pembanding r0 setara' % (label, (1 - q) * 100, x.ek.sum()))
    print(pd.DataFrame(baris, columns=['H', 'ekstrem', 'pembanding_r0', 'selisih', 'win%', 'semua_hari']).round(2).to_string(index=False))


if __name__ == '__main__':
    semua = []
    for nama, belah in BELAH.items():
        f = str(_runtime_file('riset_sentimen_obrolan', 'tg_hist', nama + '.pkl'))
        if not os.path.exists(f):
            continue
        d = muat_grup(nama)
        g, dd = harian(d.drop(columns=['D']).rename(columns={}), kal)
        g = g[g.pesan >= 30]
        x = gabung_ihsg(g, ih)
        x['z'] = zskor(x.porsi_neg)
        x.to_pickle(str(_runtime_file('riset_sentimen_obrolan', 'harian_%s.pkl' % nama)))
        print('\n######## %s: %d pesan, rata2 %.0f/hari, porsi negatif %.1f%%, corr(neg, r0) %.2f' % (
            nama, len(dd), g.pesan.mean(), dd.neg.mean() * 100, x[['porsi_neg', 'r0']].corr().iloc[0, 1]))
        ringkas(x, nama + ' SEMUA')
        ringkas(x[x.index < belah], nama + ' PERIODE A')
        ringkas(x[x.index >= belah], nama + ' PERIODE B')
        ekstrem(x, nama)
        semua.append(x[['z', 'porsi_neg', 'pesan']].add_suffix('_' + nama[:6]))
