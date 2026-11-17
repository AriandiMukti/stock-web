"""
Apakah arus broker menambah sesuatu di atas pola harga?

  Bagian 1: 21 emiten dengan 10 tahun data broker (New BDM\\Test), 2016-2026.
  Bagian 2: ~850 emiten dengan data broker 2026 (Daily\\Summary) -- satu
            periode, satu rezim, jadi cuma kalibrasi.

Return ke depan dan pembanding pasar hari yang sama diambil dari panel Yahoo.

HASIL 23 Sep 2026: tidak ada yang memisahkan secara konsisten -- Top5
akumulasi vs distribusi, asing beli vs jual, ritel beli vs jual, jumlah
pembeli vs penjual, sendirian maupun ditumpuk di atas pola tenang, tembus
basis, dan puncak 52 minggu.

TEST21 dipilih dengan hindsight (emiten besar hari ini), jadi selisih
ABSOLUT-nya terhadap pasar terangkat semua. Yang dibaca SELISIH antar
kelompok arus di dalamnya.

Bagian 2 memakai volume bursa (Summary 'Volume', lembar/100) sebagai
penyebut, bukan 'volume' bandar_detector Stockbit seperti bagian 1 -- yang
terakhir cuma ~30-50% volume bursa. Keduanya penyebut yang sah; pembagian
tersilnya dihitung terpisah per bagian.

PEMAKAIAN
    python -m website.riset_pola_naik.arus urai   # urai 47 ribu JSON (~4,5 menit, sekali)
    python -m website.riset_pola_naik.arus uji
"""
import glob
import json
import os
import pickle
import re
import sys
import time

import numpy as np
import pandas as pd

from ..config import BASE_PATH, DAILY_PATH
from . import uji
from .panel import RESEARCH_CACHE

TEST_DIR = os.path.join(BASE_PATH, 'Test')
ARUS_FILE = os.path.join(RESEARCH_CACHE, 'pola_naik_arus_test21.pkl')
RITEL = {'YP', 'PD', 'XL', 'XC'}   # sama dengan kolom 'Retail' di Summary


def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return np.nan


def _urai_satu(path):
    with open(path, encoding='utf-8') as fh:
        d = json.load(fh).get('data') or {}
    bd = d.get('bandar_detector') or {}
    bs = d.get('broker_summary') or {}
    row = {'volume': _f(bd.get('volume')), 'value': _f(bd.get('value')),
           'total_buyer': _f(bd.get('total_buyer')), 'total_seller': _f(bd.get('total_seller'))}
    for k in ('top1', 'top3', 'top5', 'top10', 'avg'):
        row[k + '_vol'] = _f((bd.get(k) or {}).get('vol'))
        row[k + '_acc'] = (bd.get(k) or {}).get('accdist')
    asing = ritel = 0.0
    for b in bs.get('brokers_buy') or []:
        lot = _f(b.get('blot')) or 0.0
        if b.get('type') == 'Asing':
            asing += lot
        if b.get('netbs_broker_code') in RITEL:
            ritel += lot
    for s in bs.get('brokers_sell') or []:
        lot = abs(_f(s.get('slot')) or 0.0)
        if s.get('type') == 'Asing':
            asing -= lot
        if s.get('netbs_broker_code') in RITEL:
            ritel -= lot
    row['foreign_net'] = asing
    row['retail_net'] = ritel
    return row


def urai():
    t0 = time.time()
    berkas = glob.glob(os.path.join(TEST_DIR, '*', '*_ALL_*.json'))
    print(len(berkas), 'berkas', flush=True)
    rows = []
    for i, path in enumerate(berkas):
        m = re.search(r'([A-Z]+)_ALL_(\d{4}-\d{2}-\d{2})\.json$', path)
        if not m:
            continue
        try:
            r = _urai_satu(path)
        except Exception:
            continue
        r['ticker'], r['date'] = m.group(1), m.group(2)
        rows.append(r)
        if i % 10000 == 0:
            print(i, '%.0fs' % (time.time() - t0), flush=True)
    df = pd.DataFrame(rows)
    df['date'] = pd.to_datetime(df['date'])
    df = df.sort_values(['ticker', 'date']).reset_index(drop=True)
    with open(ARUS_FILE, 'wb') as fh:
        pickle.dump(df, fh)
    print('%d baris, %d emiten, %s s.d. %s, %.0f detik'
          % (len(df), df['ticker'].nunique(), df['date'].min().date(), df['date'].max().date(), time.time() - t0))


def _porsi(df, pembilang, penyebut, w):
    g = df.groupby('ticker', sort=False)
    return (g[pembilang].transform(lambda s: s.rolling(w, min_periods=w).sum())
            / g[penyebut].transform(lambda s: s.rolling(w, min_periods=w).sum()).replace(0, np.nan))


def _fitur_arus(fl):
    fl = fl.sort_values(['ticker', 'date']).copy()
    fl['t5s20'] = _porsi(fl, 'top5_vol', 'volume', 20)
    fl['fr20'] = _porsi(fl, 'foreign_net', 'volume', 20)
    fl['rt20'] = _porsi(fl, 'retail_net', 'volume', 20)
    fl['bs20'] = _porsi(fl, 'total_buyer', 'total_seller', 20)
    return fl[['ticker', 'date', 't5s20', 'fr20', 'rt20', 'bs20']]


FITUR = [('t5s20', 'Top5 DIST', 'Top5 ACC'),
         ('fr20', 'asing JUAL', 'asing BELI'),
         ('rt20', 'ritel JUAL', 'ritel BELI'),
         ('bs20', 'pembeli<penjual', 'pembeli>penjual')]


def _kelompok(q):
    return {'semua hari': pd.Series(True, index=q.index),
            'tenang: rentang 30h <15%': q['range30'] < 0.15,
            'tembus basis <20% + vol>2x': (q['brk30'] == 1) & (q['prevrange30'] < 0.20) & (q['vspike'] > 2),
            'puncak 52 minggu': q['hi250'] == 1}


def _laporan(q, judul):
    print('\n' + '=' * 130 + '\n' + judul + '\n' + '=' * 130)
    rows = []

    def tambah(nama, ember, sub):
        s = uji.statistik(uji.jeda(sub))
        rows.append({'pola harga': nama, 'ember arus': ember, 'n': s['n'],
                     'lift P(+10%/20h)': round(s.get('p10', np.nan) - s.get('p10_base', np.nan), 1),
                     'exc20%': round(s.get('exc20', np.nan), 2), 't20': round(s.get('t20', np.nan), 1),
                     'exc60%': round(s.get('exc60', np.nan), 2), 't60': round(s.get('t60', np.nan), 1)})

    for nama, m in _kelompok(q).items():
        sub = q[m.fillna(False) & q['elig']]
        for kol, rendah, tinggi in FITUR:
            lo, hi = q.loc[q['elig'], kol].quantile([1 / 3, 2 / 3])
            tambah(nama, '%s (%s)' % (rendah, kol), sub[sub[kol] <= lo])
            tambah(nama, '%s (%s)' % (tinggi, kol), sub[sub[kol] >= hi])
        tambah(nama, '(semua, tanpa saringan arus)', sub)
    print(pd.DataFrame(rows).set_index(['pola harga', 'ember arus']).to_string())


def main_uji():
    if not os.path.exists(ARUS_FILE):
        print('Belum ada %s -- jalankan dulu: python -m website.riset_pola_naik.arus urai' % ARUS_FILE)
        sys.exit(1)
    p = uji.muat()

    with open(ARUS_FILE, 'rb') as fh:
        fl = pickle.load(fh)
    ff = _fitur_arus(fl)
    q = p[p['ticker'].isin(ff['ticker'].unique()) & (p['date'] >= '2016-02-15')].merge(ff, on=['ticker', 'date'], how='inner')
    print('TEST21: %d emiten-hari, %d layak' % (len(q), int(q['elig'].sum())))
    _laporan(q, 'BAGIAN 1 -- 21 emiten, 2016-2026: tersil bawah vs atas tiap ukuran arus')

    rows = []
    for path in glob.glob(os.path.join(DAILY_PATH, 'Summary', '*_Summary.csv')):
        try:
            d = pd.read_csv(path, usecols=['Date', 'Volume', 'Net Top5 All Lot', 'Retail', 'Net Top5 Foreign Lot',
                                           'Total Buyer', 'Total Seller'])
        except Exception:
            continue
        d['ticker'] = os.path.basename(path).replace('_Summary.csv', '')
        rows.append(d)
    s = pd.concat(rows)
    s['date'] = pd.to_datetime(s['Date'], format='%d-%b-%y', errors='coerce')
    s = s.rename(columns={'Net Top5 All Lot': 'top5_vol', 'Retail': 'retail_net', 'Net Top5 Foreign Lot': 'foreign_net',
                          'Total Buyer': 'total_buyer', 'Total Seller': 'total_seller'})
    s['volume'] = s['Volume'] / 100.0          # Summary: lembar; arus: lot
    s = s.dropna(subset=['date']).drop_duplicates(['ticker', 'date'])
    q2 = p[p['date'] >= '2026-01-01'].merge(_fitur_arus(s), on=['ticker', 'date'], how='inner')
    print('\n2026: %d emiten-hari, %d layak, %d emiten' % (len(q2), int(q2['elig'].sum()), q2['ticker'].nunique()))
    _laporan(q2, 'BAGIAN 2 -- ~850 emiten, 2026 saja (kalibrasi, satu rezim pasar turun)')


if __name__ == '__main__':
    perintah = sys.argv[1] if len(sys.argv) > 1 else 'uji'
    if perintah == 'urai':
        urai()
    elif perintah == 'uji':
        main_uji()
    else:
        print(__doc__)
        sys.exit(2)
