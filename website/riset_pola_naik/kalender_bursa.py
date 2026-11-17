"""
Kejadian bursa yang tanggalnya diketahui: UMA, suspensi/unsuspensi, dan
berakhirnya lock-up IPO. Apa yang terjadi pada harga sesudahnya?

DATA
  UMA & suspensi : API pengumuman IDX (GetUma, GetSuspension), ditarik lewat
                   browser 9 Okt 2026 -- API-nya cuma menyimpan 3 tahun
                   (10 Okt 2023 - 9 Okt 2026). Berkas ringkas di
                   research_cache/idx_bursa/:
                     uma_*.txt       "YYMMDDKODE"
                     suspensi_*.txt  "YYMMDDhhXKODE"  X = S suspend / U unsuspend
                   (hh = jam UTC pengumuman; ">1Kode" = pengumuman banyak emiten, dibuang)
  Harga          : panel sambungan Summary + Yahoo (tembus_basis._panel), close saja.
                   Masuk di CLOSE hari kejadian (UMA diumumkan saat/ setelah sesi;
                   unsuspensi = close hari pertama diperdagangkan lagi).
  Lock-up IPO    : tanggal listing = bar pertama di pickle Yahoo (research_cache), hanya
                   emiten yang bar pertamanya >= Feb 2013 (sebelum itu = awal data, bukan
                   IPO). Lock-up pemegang pra-IPO 8 bulan sejak pernyataan efektif
                   (~1-2 minggu sebelum listing) -> tanggal bebas ~ listing + 8 bulan - 7 hari.

PEMBANDING: rata-rata return log semua emiten di panel pada tanggal yang sama
(equal-weight), jadi pasar naik/turun tidak memberi kredit.
UJI LUAR SAMPEL: dipecah dua periode (UMA/suspensi: s.d. Mar 2025 vs sesudahnya;
lock-up: listing s.d. 2019 vs 2020+).

    python -m website.riset_pola_naik.kalender_bursa uma
    python -m website.riset_pola_naik.kalender_bursa lockup
"""
import os
import sys

import numpy as np
import pandas as pd

from .panel import RESEARCH_CACHE
from . import uji as U

DIR = os.path.join(RESEARCH_CACHE, 'idx_bursa')
H = (1, 3, 5, 10, 20)
BELAH = pd.Timestamp('2025-04-01')


def _baca_uma():
    with open(os.path.join(DIR, 'uma_2023-10_2026-10.txt')) as fh:
        tok = fh.read().split()
    rows = [(pd.Timestamp('20' + t[:6]), t[6:]) for t in tok if len(t) == 10 and t[6:].isalpha()]
    return pd.DataFrame(rows, columns=['date', 'stock']).drop_duplicates()


def _baca_suspensi():
    with open(os.path.join(DIR, 'suspensi_2023-10_2026-10.txt')) as fh:
        tok = fh.read().split()
    rows = [(pd.Timestamp('20' + t[:6]), int(t[6:8]), t[8], t[9:]) for t in tok
            if len(t) == 13 and t[9:].isalpha()]
    return pd.DataFrame(rows, columns=['date', 'jam', 'jenis', 'stock']).drop_duplicates()


def _panel_close():
    """Panel sambungan (Juni 2024 s.d. kini) di atas riwayat Yahoo untuk tanggal sebelumnya."""
    from ..tembus_basis import _panel
    from .panel import sumber_harga
    p = _panel()
    c = pd.DataFrame({s: f['close'] for s, f in p['fit'].items()}).sort_index()
    _, data = sumber_harga()
    y = pd.DataFrame({t: df['Close'] for t, df in data.items() if t in c.columns}).sort_index()
    y = y[y.index < c.index[0]].where(lambda v: v > 0)
    return pd.concat([y, c]).sort_index()


def _maju(close, ev, kol_tgl='date', sesudah=False):
    """Return log ke depan dari close tanggal kejadian (atau hari bursa berikutnya kalau libur),
    dikurangi rata-rata semua emiten tanggal yang sama. Juga gerak 1 & 20 hari SEBELUM."""
    lr = np.log(close)
    idx = close.index
    pasar = {}
    for h in H:
        pasar[h] = (lr.shift(-h) - lr).mean(axis=1)
    pasar_pre = (lr - lr.shift(20)).mean(axis=1)
    out = []
    for _, e in ev.iterrows():
        s = e['stock']
        if s not in close.columns:
            continue
        # sesudah=True: kejadian berlaku hari bursa BERIKUTNYA (unsuspensi diumumkan
        # tanggal d, perdagangan dibuka lagi d+1 -- dicek pada IFSH 8->9 Okt 2026)
        i = idx.searchsorted(e[kol_tgl], side='right' if sesudah else 'left')
        if i >= len(idx) or (idx[i] - e[kol_tgl]).days > 7:
            continue
        ser = lr[s].to_numpy()
        if not np.isfinite(ser[i]):
            continue
        r = dict(e)
        r['t0'] = idx[i]
        r['pre1'] = ser[i] - ser[i - 1] if i >= 1 else np.nan
        r['pre20'] = (ser[i] - ser[i - 20] - pasar_pre.iloc[i]) if i >= 20 else np.nan
        for h in H:
            if i + h < len(idx) and np.isfinite(ser[i + h]):
                r['x%d' % h] = ser[i + h] - ser[i] - pasar[h].iloc[i]
                r['a%d' % h] = ser[i + h] - ser[i]
            else:
                r['x%d' % h] = r['a%d' % h] = np.nan
        out.append(r)
    return pd.DataFrame(out)


def _ringkas(d, label):
    r = {'kelompok': label, 'n': len(d)}
    if len(d) < 15:
        return r
    r['pre20 vs pasar %'] = round((np.exp(d['pre20'].mean()) - 1) * 100, 1)
    r['hari-H %'] = round((np.exp(d['pre1'].mean()) - 1) * 100, 1)
    for h in H:
        x = d['x%d' % h].dropna()
        if len(x) >= 15:
            r['H+%d vs pasar %%' % h] = round((np.exp(x.mean()) - 1) * 100, 2)
            if h in (1, 5, 20):
                r['t%d' % h] = round(U.t_klaster(x, d.loc[x.index, 't0'].dt.to_period('M').astype(str)), 1)
    a = d['a5'].dropna()
    if len(a) >= 15:
        r['P(naik H+5) %'] = round((a > 0).mean() * 100, 1)
    return r


def _tabel(rows, judul):
    print('\n--- ' + judul)
    print(pd.DataFrame(rows).set_index('kelompok').to_string())


def cmd_uma():
    close = _panel_close()
    print('panel: %d emiten, %s s.d. %s' % (close.shape[1], close.index[0].date(), close.index[-1].date()))

    uma = _maju(close, _baca_uma())
    print('UMA: %d kejadian terpetakan' % len(uma))
    rows = [_ringkas(uma, 'UMA semua')]
    for nama, m in (('UMA s.d. Mar 2025', uma['t0'] < BELAH), ('UMA Apr 2025+', uma['t0'] >= BELAH)):
        rows.append(_ringkas(uma[m], nama))
    up = uma['pre20'] > 0
    rows.append(_ringkas(uma[up], 'UMA setelah naik (pre20 > pasar)'))
    rows.append(_ringkas(uma[~up], 'UMA setelah turun (pre20 <= pasar)'))
    rows.append(_ringkas(uma[uma['pre1'] > 0.05], 'UMA dan hari-H naik >5%'))
    rows.append(_ringkas(uma[uma['pre1'] < -0.05], 'UMA dan hari-H turun >5%'))
    _tabel(rows, 'UMA -> masuk close hari pengumuman')

    sus = _baca_suspensi().sort_values(['stock', 'date'])
    # pasangkan S dengan U berikutnya untuk emiten yang sama -> lama suspensi
    pas = []
    for s, g in sus.groupby('stock'):
        g = g.sort_values('date')
        terbuka = None
        for _, r in g.iterrows():
            if r['jenis'] == 'S':
                terbuka = r['date']
            elif terbuka is not None:
                pas.append({'stock': s, 'tgl_s': terbuka, 'date': r['date']})
                terbuka = None
    pas = pd.DataFrame(pas)
    hari = close.index
    pas['lama'] = [int(hari.searchsorted(u) - hari.searchsorted(s_)) for s_, u in zip(pas['tgl_s'], pas['date'])]
    uma_set = set(zip(uma['stock'], uma['t0']))
    # suspensi yang didahului UMA dalam 30 hari = hampir pasti karena lonjakan harga
    um = _baca_uma()
    pas['pasca_uma'] = [bool(((um['stock'] == s) & (um['date'] <= t) & (um['date'] >= t - pd.Timedelta(days=30))).any())
                        for s, t in zip(pas['stock'], pas['tgl_s'])]
    un = _maju(close, pas, sesudah=True)
    print('\nUnsuspensi berpasangan: %d (dari %d S dan %d U)'
          % (len(un), (sus['jenis'] == 'S').sum(), (sus['jenis'] == 'U').sum()))
    rows = [_ringkas(un, 'unsuspensi semua')]
    for nama, m in (('suspensi 1-2 hari bursa', un['lama'] <= 2),
                    ('suspensi 3-10 hari', (un['lama'] > 2) & (un['lama'] <= 10)),
                    ('suspensi >10 hari', un['lama'] > 10),
                    ('didahului UMA (30 hari)', un['pasca_uma']),
                    ('tanpa UMA', ~un['pasca_uma']),
                    ('s.d. Mar 2025', un['t0'] < BELAH), ('Apr 2025+', un['t0'] >= BELAH)):
        rows.append(_ringkas(un[m], nama))
    m = un['pasca_uma'] & (un['lama'] <= 2)
    rows.append(_ringkas(un[m & (un['t0'] < BELAH)], 'UMA + suspensi singkat, s.d. Mar 2025'))
    rows.append(_ringkas(un[m & (un['t0'] >= BELAH)], 'UMA + suspensi singkat, Apr 2025+'))
    _tabel(rows, 'UNSUSPENSI -> masuk close hari pertama dibuka lagi ("hari-H" = gerak hari itu)')

    # suspensi: gerak SEBELUM disuspensi (yang bisa dipegang trader saat UMA keluar)
    sp = _maju(close, pas.rename(columns={'date': 'tgl_u', 'tgl_s': 'date'}))
    _tabel([_ringkas(sp, 'hari suspensi diumumkan')], 'SUSPENSI (close hari terakhir sebelum suspensi efektif)')


def cmd_lockup():
    from .panel import sumber_harga
    _, data = sumber_harga()
    close = pd.DataFrame({t: df['Close'] for t, df in data.items()}).sort_index()
    close = close.where(close > 0)
    awal = close.apply(lambda s: s.first_valid_index())
    ipo = awal[awal >= pd.Timestamp('2013-02-01')]
    print('emiten dgn bar pertama >= Feb 2013 (anggap IPO): %d' % len(ipo))
    ev = pd.DataFrame({'stock': ipo.index, 'listing': ipo.values})
    ev['date'] = ev['listing'] + pd.DateOffset(months=8) - pd.Timedelta(days=7)
    ev = ev[ev['date'] < close.index[-1] - pd.Timedelta(days=40)]
    lr = np.log(close)
    idx = close.index
    pasar = lr.diff().mean(axis=1)
    rows = []
    for _, e in ev.iterrows():
        i = idx.searchsorted(e['date'])
        ser = lr[e['stock']].to_numpy()
        if i < 25 or i + 25 >= len(idx):
            continue
        ar = ser[1:] - ser[:-1] - pasar.to_numpy()[1:]
        ar = np.concatenate([[np.nan], ar])
        ar[np.abs(ar) > 0.45] = np.nan          # loncatan mustahil = data rusak / aksi korporasi
        w = ar[i - 20:i + 21]
        if np.isnan(w).mean() > 0.3:
            continue
        rows.append({'stock': e['stock'], 'listing': e['listing'], 't0': idx[i],
                     'car_pre20': np.nansum(ar[i - 20:i]), 'car_pre5': np.nansum(ar[i - 5:i]),
                     'car_post5': np.nansum(ar[i:i + 5]), 'car_post20': np.nansum(ar[i:i + 20]),
                     'ipo_run': ser[i - 1] - ser[idx.searchsorted(e['listing'])]})
    d = pd.DataFrame(rows)
    print('kejadian lock-up dengan harga cukup: %d' % len(d))
    out = []
    for nama, m in (('semua', d.index == d.index), ('listing 2013-2019', d['listing'] < '2020-01-01'),
                    ('listing 2020+', d['listing'] >= '2020-01-01'),
                    ('sudah naik >50% sejak IPO', d['ipo_run'] > np.log(1.5)),
                    ('sudah turun sejak IPO', d['ipo_run'] < 0)):
        g = d[m]
        r = {'kelompok': nama, 'n': len(g)}
        for k in ('car_pre20', 'car_pre5', 'car_post5', 'car_post20'):
            r[k + ' %'] = round((np.exp(g[k].mean()) - 1) * 100, 2)
        r['t post20'] = round(U.t_klaster(g['car_post20'], g['t0'].dt.to_period('M').astype(str)), 1)
        r['P(post20<0) %'] = round((g['car_post20'] < 0).mean() * 100, 1)
        out.append(r)
    print('\n--- Lock-up IPO berakhir (~listing + 8 bulan - 7 hari): return kumulatif vs pasar')
    print(pd.DataFrame(out).set_index('kelompok').to_string())


if __name__ == '__main__':
    k = sys.argv[1] if len(sys.argv) > 1 else 'uma'
    {'uma': cmd_uma, 'lockup': cmd_lockup}.get(k, lambda: print(__doc__))()
