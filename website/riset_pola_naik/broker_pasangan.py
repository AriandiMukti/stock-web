"""
Kalau broker X membeli saham Y secara konsisten berminggu-minggu, apakah
harga Y cenderung naik? Dan apakah ada PASANGAN broker-saham tertentu yang
"jitu" -- misalnya AZ di BBCA -- yang kejituannya berulang?

DEFINISI -- DIKUNCI SEBELUM HASIL DILIHAT
  Hari t, pasangan (broker B, saham S), 20 hari bursa terakhir S dipecah
  jadi 4 blok x 5 hari.
    AKUM  : net beli B > 0 di KEEMPAT blok, DAN net 20h B >= 10% dari total
            net beli semua broker di S selama 20h itu.
    DIST  : cerminnya (net jual di keempat blok, >= 10% total net jual).
    longgar (pembanding): 3 dari 4 blok, ambang 5%.
  Kejadian = hari pertama kondisi terpenuhi (awal episode), lalu paling
  banyak satu per pasangan per 20 hari bursa. Masuk di close t+1 (konvensi
  panel.py), hasil = selisih majemuk 20h/60h terhadap semua emiten layak di
  hari yang sama.

  Penyebut "total net beli" sengaja dipilih yang bisa dihitung SAMA di dua
  sumber: Test (Stockbit, netto per broker) dan Daily 2026 (buku besar).

TIGA UJI
  1. Umum     : kejadian AKUM/DIST vs semua hari layak emiten yang sama.
                Diulang per tahun -- tiap tahun satu replikasi.
  2. Pasangan : catatan jejak pasangan (rata-rata selisih kejadian AKUM
                sebelumnya, yang jendela 20h-nya SUDAH SELESAI sebelum
                kejadian sekarang; min 3) -> apakah pasangan "jitu" di masa
                lalu tetap jitu? Jitu (>0) vs meleset (<=0), per tahun.
  3. Broker   : sama, tapi catatan jejak broker lintas semua saham (min 10).

SEMESTA
  Test21  : 21 emiten, 2016-2026 -- dipilih dengan hindsight (emiten besar
            hari ini), jadi selisih ABSOLUT terangkat. Yang dibaca: selisih
            AKUM vs semua-hari di emiten yang sama, dan konsistensi per tahun.
  2026    : ~880 emiten, Jan-Sep 2026 -- satu rezim, cuma kalibrasi.

PEMAKAIAN
    python -m website.riset_pola_naik.broker_pasangan urai   # urai JSON Test (sekali, beberapa menit)
    python -m website.riset_pola_naik.broker_pasangan uji
"""
try:
    from ..runtime_paths import runtime_file as _runtime_file, market_file as _market_file, WEBSITE_DIR as _WEBSITE_DIR, PROJECT_DIR as _PROJECT_DIR, RUNTIME_DIR as _RUNTIME_DIR
except ImportError:
    from website.runtime_paths import runtime_file as _runtime_file, market_file as _market_file, WEBSITE_DIR as _WEBSITE_DIR, PROJECT_DIR as _PROJECT_DIR, RUNTIME_DIR as _RUNTIME_DIR
import glob
import json
import os
import pickle
import re
import sys
import time
from concurrent.futures import ProcessPoolExecutor

import numpy as np
import pandas as pd

from ..config import BASE_PATH
from . import uji
from .panel import RESEARCH_CACHE

TEST_DIR = os.path.join(BASE_PATH, 'Test')
NET_FILE = os.path.join(RESEARCH_CACHE, 'broker_pasangan_test21.pkl')
LEDGER_FILE = str(_runtime_file('', 'broker_ledger.pkl'))

BLOK, NBLOK = 5, 4
W = BLOK * NBLOK
JEDA = 20
DEF = {'ketat': (4, 0.10), 'longgar': (3, 0.05)}   # (blok minimal, porsi minimal)
MIN_PASANGAN, MIN_BROKER = 3, 10


# ------------------------------------------------------------------ urai
def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0


def _urai_satu(path):
    m = re.search(r'([A-Z]+)_ALL_(\d{4}-\d{2}-\d{2})\.json$', path)
    if not m:
        return []
    try:
        with open(path, encoding='utf-8') as fh:
            bs = (json.load(fh).get('data') or {}).get('broker_summary') or {}
    except Exception:
        return []
    out = []
    for b in bs.get('brokers_buy') or []:
        out.append((m.group(2), m.group(1), b.get('netbs_broker_code'), _f(b.get('blot'))))
    for s in bs.get('brokers_sell') or []:
        out.append((m.group(2), m.group(1), s.get('netbs_broker_code'), -abs(_f(s.get('slot')))))
    return out


def urai():
    t0 = time.time()
    berkas = glob.glob(os.path.join(TEST_DIR, '*', '*_ALL_*.json'))
    print(len(berkas), 'berkas', flush=True)
    rows = []
    with ProcessPoolExecutor() as ex:
        for i, r in enumerate(ex.map(_urai_satu, berkas, chunksize=200)):
            rows.extend(r)
            if i % 10000 == 0:
                print(i, '%.0fs' % (time.time() - t0), flush=True)
    df = pd.DataFrame(rows, columns=['date', 'stock', 'broker', 'net'])
    df['date'] = pd.to_datetime(df['date'])
    df = df.dropna(subset=['broker']).groupby(['date', 'stock', 'broker'], as_index=False)['net'].sum()
    with open(NET_FILE, 'wb') as fh:
        pickle.dump(df, fh)
    print('%d baris, %d emiten, %d broker, %s s.d. %s, %.0f detik'
          % (len(df), df['stock'].nunique(), df['broker'].nunique(),
             df['date'].min().date(), df['date'].max().date(), time.time() - t0))


def net_2026():
    with open(LEDGER_FILE, 'rb') as fh:
        d = pickle.load(fh)['df']
    d = d.copy()
    d['net'] = np.where(d['side'].astype(str) == 'buy', d['lot'], -d['lot'])
    for c in ('stock', 'broker'):
        d[c] = d[c].astype(str)
    return d.groupby(['date', 'stock', 'broker'], as_index=False)['net'].sum()


# ------------------------------------------------------------- kejadian
def kejadian(net):
    """Satu baris per awal episode AKUM/DIST per pasangan, untuk tiap definisi."""
    out = []
    for stock, g in net.groupby('stock', sort=False):
        m = g.pivot_table(index='date', columns='broker', values='net', aggfunc='sum').sort_index().fillna(0.0)
        if len(m) < W + 5:
            continue
        a = m.to_numpy()
        cs = np.vstack([np.zeros((1, a.shape[1])), np.cumsum(a, axis=0)])
        T = len(a)
        idx = np.arange(W - 1, T)
        # jumlah blok ke-k (k=0 paling baru) berakhir di t-5k
        blok = np.stack([cs[idx + 1 - BLOK * k] - cs[idx + 1 - BLOK * (k + 1)] for k in range(NBLOK)])
        net20 = cs[idx + 1] - cs[idx + 1 - W]
        pos = np.clip(a, 0, None).sum(axis=1); neg = np.clip(-a, 0, None).sum(axis=1)
        cp, cn = np.concatenate([[0], np.cumsum(pos)]), np.concatenate([[0], np.cumsum(neg)])
        tb = (cp[idx + 1] - cp[idx + 1 - W])[:, None]
        tj = (cn[idx + 1] - cn[idx + 1 - W])[:, None]
        dates = m.index[idx]
        for nama, (kmin, porsi) in DEF.items():
            for arah, nblok, share in (
                    ('AKUM', (blok > 0).sum(axis=0), net20 / np.where(tb > 0, tb, np.nan)),
                    ('DIST', (blok < 0).sum(axis=0), -net20 / np.where(tj > 0, tj, np.nan))):
                cond = (nblok >= kmin) & (share >= porsi)
                awal = cond & ~np.vstack([np.zeros((1, cond.shape[1]), bool), cond[:-1]])
                ti, bi = np.nonzero(awal)
                if not len(ti):
                    continue
                order = np.lexsort((ti, bi))
                ti, bi = ti[order], bi[order]
                keep = np.ones(len(ti), bool)
                last_b, last_t = -1, -10 ** 9
                for k in range(len(ti)):
                    if bi[k] != last_b:
                        last_b, last_t = bi[k], -10 ** 9
                    if ti[k] - last_t >= JEDA:
                        last_t = ti[k]
                    else:
                        keep[k] = False
                ti, bi = ti[keep], bi[keep]
                out.append(pd.DataFrame({'date': dates[ti], 'stock': stock,
                                         'broker': m.columns[bi].astype(str),
                                         'arah': arah, 'definisi': nama,
                                         'share': share[ti, bi]}))
    return pd.concat(out, ignore_index=True)


# ----------------------------------------------------------------- uji
def _ringkas(ev):
    f = ev[ev['fwd20'].notna()]
    if len(f) < 20:
        return {'n': len(f)}
    x = np.log1p(f['fwd20']) - f['b_lr20']
    r = {'n': len(f), 'emiten': f['ticker'].nunique(),
         'exc20%': round((np.exp(x.mean()) - 1) * 100, 2),
         't20': round(uji.t_klaster(x, f['month'].astype(str)), 1),
         'win%': round((f['fwd20'] > 0).mean() * 100, 1),
         'win_base%': round(f['b_win'].mean() * 100, 1)}
    g = ev[ev['fwd60'].notna()]
    if len(g) >= 20:
        r['exc60%'] = round((np.exp((np.log1p(g['fwd60']) - g['b_lr60']).mean()) - 1) * 100, 2)
    return r


def _gabung(ev, p):
    cols = ['ticker', 'date', 'fwd20', 'fwd60', 'b_lr20', 'b_lr60', 'b_win', 'month', 'elig']
    e = ev.merge(p[cols], left_on=['stock', 'date'], right_on=['ticker', 'date'], how='inner')
    return e[e['elig']].copy()


def _jejak(e, kunci, min_n):
    """Catatan jejak per kunci dari kejadian yang jendelanya sudah selesai (>= 30 hari kalender)."""
    e = e[e['fwd20'].notna()].sort_values('date').copy()
    e['x'] = np.log1p(e['fwd20']) - e['b_lr20']
    rec = np.full(len(e), np.nan); cnt = np.zeros(len(e), int)
    for _, idx in e.groupby(kunci, sort=False).groups.items():
        sub = e.loc[idx]
        d = sub['date'].to_numpy(); x = sub['x'].to_numpy()
        pos = e.index.get_indexer(idx)
        for j in range(len(sub)):
            prior = d < d[j] - np.timedelta64(30, 'D')
            cnt[pos[j]] = prior.sum()
            if cnt[pos[j]] >= min_n:
                rec[pos[j]] = x[prior].mean()
    e['jejak'] = rec; e['n_jejak'] = cnt
    return e[e['jejak'].notna()]


def _tabel(rows, judul):
    print('\n--- ' + judul)
    print(pd.DataFrame(rows).to_string(index=False))


def _laporan(ev, p, semesta, per_tahun):
    print('\n' + '=' * 110 + '\n' + semesta + '\n' + '=' * 110)
    tickers = ev['stock'].unique()
    dasar = p[p['ticker'].isin(tickers) & p['elig'] & (p['date'] >= ev['date'].min())]
    dasar = dasar[dasar['date'] <= ev['date'].max()]
    e = _gabung(ev, p)

    rows = [dict(kelompok='semua hari layak (emiten sama)', **_ringkas(dasar))]
    for (nama, arah), sub in e.groupby(['definisi', 'arah']):
        rows.append(dict(kelompok='%s %s' % (arah, nama), **_ringkas(sub)))
    _tabel(rows, 'UJI 1 -- umum')

    if per_tahun:
        rows = []
        for th in sorted(e['date'].dt.year.unique()):
            b = _ringkas(dasar[dasar['date'].dt.year == th])
            r = {'tahun': th, 'base exc20%': b.get('exc20%')}
            for arah in ('AKUM', 'DIST'):
                s = _ringkas(e[(e['definisi'] == 'ketat') & (e['arah'] == arah) & (e['date'].dt.year == th)])
                r['%s n' % arah] = s.get('n')
                r['%s exc20%%' % arah] = s.get('exc20%')
                r['%s - base' % arah] = (round(s['exc20%'] - b['exc20%'], 2)
                                         if 'exc20%' in s and 'exc20%' in b else None)
            rows.append(r)
        _tabel(rows, 'UJI 1 per tahun (ketat) -- tiap tahun satu replikasi')

    for kunci, min_n, label in ((['broker', 'stock'], MIN_PASANGAN, 'UJI 2 -- pasangan broker-saham'),
                                (['broker'], MIN_BROKER, 'UJI 3 -- broker lintas saham')):
        rows = []
        for (nama, arah), sub in e.groupby(['definisi', 'arah']):
            j = _jejak(sub, kunci, min_n)
            if arah == 'DIST':
                j['jejak'] = -j['jejak']          # DIST "jitu" = harga turun setelahnya
            jitu, meleset = j[j['jejak'] > 0], j[j['jejak'] <= 0]
            a, b = _ringkas(jitu), _ringkas(meleset)
            rows.append({'kelompok': '%s %s' % (arah, nama),
                         'jitu n': a.get('n'), 'jitu exc20%': a.get('exc20%'), 'jitu t': a.get('t20'),
                         'meleset n': b.get('n'), 'meleset exc20%': b.get('exc20%'), 'meleset t': b.get('t20'),
                         'rho jejak~hasil': round(j['jejak'].corr(np.log1p(j['fwd20']) - j['b_lr20'],
                                                                   method='spearman'), 3) if len(j) > 30 else None})
        _tabel(rows, label + ' (jitu = catatan jejak sebelumnya searah)')
        if per_tahun:
            j = _jejak(e[(e['definisi'] == 'ketat') & (e['arah'] == 'AKUM')], kunci, min_n)
            rows = []
            for th in sorted(j['date'].dt.year.unique()):
                s = j[j['date'].dt.year == th]
                a, b = _ringkas(s[s['jejak'] > 0]), _ringkas(s[s['jejak'] <= 0])
                rows.append({'tahun': th, 'jitu n': a.get('n'), 'jitu exc20%': a.get('exc20%'),
                             'meleset n': b.get('n'), 'meleset exc20%': b.get('exc20%'),
                             'selisih': (round(a['exc20%'] - b['exc20%'], 2)
                                         if 'exc20%' in a and 'exc20%' in b else None)})
            _tabel(rows, label + ' AKUM ketat per tahun')
    return e


def main_uji():
    if not os.path.exists(NET_FILE):
        print('Belum ada %s -- jalankan dulu: python -m website.riset_pola_naik.broker_pasangan urai' % NET_FILE)
        sys.exit(1)
    p = uji.muat()
    p['ticker'] = p['ticker'].astype(str)

    with open(NET_FILE, 'rb') as fh:
        n1 = pickle.load(fh)
    ev1 = kejadian(n1)
    print('Test21: %d kejadian' % len(ev1))
    e1 = _laporan(ev1, p, 'TEST21 -- 21 emiten, 2016-2026', per_tahun=True)

    n2 = net_2026()
    ev2 = kejadian(n2)
    print('\n2026: %d kejadian' % len(ev2))
    e2 = _laporan(ev2, p, '2026 -- ~880 emiten, Jan-Sep (satu rezim, kalibrasi)', per_tahun=False)

    with open(os.path.join(RESEARCH_CACHE, 'broker_pasangan_kejadian.pkl'), 'wb') as fh:
        pickle.dump({'test21': e1, '2026': e2}, fh)


if __name__ == '__main__':
    perintah = sys.argv[1] if len(sys.argv) > 1 else 'uji'
    if perintah == 'urai':
        urai()
    elif perintah == 'uji':
        main_uji()
    else:
        print(__doc__)
        sys.exit(2)
