"""
Simulasi portofolio: modal dibagi K slot sama besar, beli di close hari
SETELAH sinyal, tahan H hari bursa, jual di close. Ongkos 0,15% beli +
0,25% jual (termasuk PPh final 0,1%) + slippage per sisi.

Angka per transaksi saja tidak cukup untuk strategi yang diputar -- rata-
rata per transaksi bisa positif sementara portofolionya menyusut (lihat
catatan rata-rata majemuk). Karena itu yang dilaporkan di sini pertumbuhan
modal sungguhan, dibandingkan dengan beli-semua-emiten-layak dan IHSG.

HASIL 23 Sep 2026 (10 slot, tahan 60 hari, ongkos pulang-pergi 0,9%):
    puncak 52 minggu + vol   18,6%/thn 2013-2026, 18,3% 2020-2026, DD -44,9%
    keduanya sekaligus       19,0% / 35,1%, DD -35,8%
    tenang <15%              -0,5% / -1,3%
    Jatuh Dalam             -19,1% / -27,3%, DD -95,6%
    beli semua (tanpa ongkos) 3,7% / 8,3%;  IHSG 3,0% / 0,5%
Uji stres: urutan pengisian slot diacak, ongkos x2, 5/20 slot, tahan 20
hari -- semuanya tetap jauh di atas pembanding. TAPI tanpa 10 transaksi
terbaik hasilnya kembali ke kisaran beli-semua: untungnya dari ekor kanan.

PEMAKAIAN
    python -m website.riset_pola_naik.simulasi dasar
    python -m website.riset_pola_naik.simulasi stres
    SLOTS=5 HOLD=20 SLIP=0.005 python -m website.riset_pola_naik.simulasi dasar
"""
import os
import sys
import warnings

import numpy as np
import pandas as pd

from . import uji
from .panel import sumber_ihsg

warnings.filterwarnings('ignore')

K = int(os.environ.get('SLOTS', 10))
H = int(os.environ.get('HOLD', 60))
SLIP = float(os.environ.get('SLIP', 0.0025))


class Pasar:
    """Harga tertutup (dates x emiten) + pembanding beli-semua + IHSG."""

    def __init__(self, p):
        self.p = p
        self.close = p.pivot(index='date', columns='ticker', values='close').sort_index().ffill(limit=15)
        self.kal = self.close.index
        self.pos = {d: i for i, d in enumerate(self.kal)}
        self.akhir = len(self.kal) - 1
        self.arr = self.close.to_numpy()
        self.kol = {t: j for j, t in enumerate(self.close.columns)}
        layak = p.pivot(index='date', columns='ticker', values='elig').reindex(self.kal)
        layak = layak.astype('boolean').fillna(False).astype(bool)
        dret = self.close.pct_change(fill_method=None)
        self.ew = dret.where(layak.shift(1, fill_value=False) & ~(dret.abs() > 0.45)).mean(axis=1).fillna(0)
        ih = sumber_ihsg()
        self.ihsg = ih.reindex(self.kal).ffill() if ih is not None else None


def simulasi(ps, ev, mulai, akhir, k=K, h=H, slip=SLIP, urutan='likuid', seed=0):
    beli, jual = 0.0015 + slip, 0.0025 + slip
    ev = ev[(ev['date'] >= mulai) & (ev['date'] <= akhir)]
    ev = ev[ev['fwd60'].notna()] if h == 60 else ev[ev['fwd20'].notna()]
    if urutan == 'likuid':
        ev = ev.sort_values(['date', 'medval20'], ascending=[True, False])
    else:
        ev = ev.sample(frac=1, random_state=seed).sort_values('date', kind='stable')
    masuk = {}
    for t, d in zip(ev['ticker'], ev['date']):
        i = ps.pos[d] + 1
        if i + h <= ps.akhir:
            masuk.setdefault(i, []).append(t)
    i0 = ps.pos[ps.kal[ps.kal >= pd.Timestamp(mulai)][0]]
    i1 = min(ps.pos[ps.kal[ps.kal <= pd.Timestamp(akhir)][-1]] + h + 1, ps.akhir)
    kas, pegang, kurva, transaksi = 1.0, {}, [], []
    for i in range(i0, i1 + 1):
        for t in [t for t, x in pegang.items() if x['keluar'] == i]:
            x = pegang.pop(t)
            nilai = x['lembar'] * ps.arr[i, ps.kol[t]] * (1 - jual)
            kas += nilai
            transaksi.append((nilai / x['modal'] - 1, t, ps.kal[i]))
        ekuitas = kas + sum(x['lembar'] * ps.arr[i, ps.kol[t]] for t, x in pegang.items())
        for t in masuk.get(i, []):
            if len(pegang) >= k or t in pegang:
                continue
            harga = ps.arr[i, ps.kol[t]]
            alokasi = min(ekuitas / k, kas)
            if not np.isfinite(harga) or harga <= 0 or alokasi <= ekuitas * 0.01:
                continue
            kas -= alokasi
            pegang[t] = {'lembar': alokasi * (1 - beli) / harga, 'modal': alokasi, 'keluar': i + h}
        kurva.append((ps.kal[i], kas + sum(x['lembar'] * ps.arr[i, ps.kol[t]] for t, x in pegang.items())))
    return pd.Series(dict(kurva)), transaksi


def ringkas(kurva):
    tahun = (kurva.index[-1] - kurva.index[0]).days / 365.25
    cagr = ((kurva.iloc[-1] / kurva.iloc[0]) ** (1 / tahun) - 1) * 100
    dd = (kurva / kurva.cummax() - 1).min() * 100
    return cagr, dd, tahun


def strategi(p):
    base = (p['brk30'] == 1) & (p['prevrange30'] < 0.20) & (p['vspike'] > 2)
    return {
        'puncak 52 minggu + vol>2x': (p['hi250'] == 1) & (p['vspike'] > 2),
        'tembus basis + vol>2x + tutup kuat': base & (p['day_pos'] > 0.7),
        'keduanya sekaligus *': base & (p['hi250'] == 1),
        'tenang: rentang 30h <15%': p['range30'] < 0.15,
        'Jatuh Dalam': (p['dd60'] <= -0.40) & (p['range20'] >= 0.25),
    }


def main_dasar():
    p = uji.muat()
    ps = Pasar(p)
    for mulai, akhir in (('2013-01-01', '2026-06-01'), ('2020-01-01', '2026-06-01')):
        print('\n=== %s -> %s | %d slot, tahan %d hari, ongkos pulang-pergi %.2f%% ==='
              % (mulai, akhir, K, H, (0.004 + 2 * SLIP) * 100))
        jendela = (p['date'] >= mulai) & (p['date'] <= akhir)
        rows, span = [], None
        for nama, m in strategi(p).items():
            # Jeda dihitung DI DALAM jendela (angka tembus_basis.BUKTI dari
            # sini); uji stres menghitungnya di seluruh periode -- bedanya
            # cuma di sinyal awal jendela 2020.
            ev = uji.jeda(p[m.fillna(False) & p['elig'] & jendela])
            kurva, tr = simulasi(ps, ev, mulai, akhir)
            span = (kurva.index[0], kurva.index[-1])
            cagr, dd, _ = ringkas(kurva)
            r = np.array([x[0] for x in tr])
            rows.append({'strategi': nama, 'CAGR%': round(cagr, 1), 'maxDD%': round(dd, 1), 'transaksi': len(r),
                         'win%': round((r > 0).mean() * 100, 1), 'median transaksi%': round(np.median(r) * 100, 1)})
        ew = (1 + ps.ew.loc[span[0]:span[1]]).cumprod()
        cagr, dd, _ = ringkas(ew)
        rows.append({'strategi': 'PEMBANDING beli semua emiten layak (tanpa ongkos)', 'CAGR%': round(cagr, 1), 'maxDD%': round(dd, 1)})
        if ps.ihsg is not None:
            cagr, dd, _ = ringkas(ps.ihsg.loc[span[0]:span[1]].dropna())
            rows.append({'strategi': 'PEMBANDING IHSG', 'CAGR%': round(cagr, 1), 'maxDD%': round(dd, 1)})
        print(pd.DataFrame(rows).set_index('strategi').to_string())


def main_stres():
    p = uji.muat()
    ps = Pasar(p)
    EV = {k: uji.jeda(p[m.fillna(False) & p['elig']]) for k, m in strategi(p).items()}
    for mulai, akhir in (('2013-01-01', '2026-06-01'), ('2020-01-01', '2026-06-01')):
        print('\n#### %s -> %s' % (mulai, akhir))
        rows = []
        for nama, ev in EV.items():
            if nama == 'Jatuh Dalam':
                continue
            kurva, tr = simulasi(ps, ev, mulai, akhir)
            cagr, _, tahun = ringkas(kurva)
            r = np.array([x[0] for x in tr])
            acak = [ringkas(simulasi(ps, ev, mulai, akhir, urutan='acak', seed=s)[0])[0] for s in range(10)]

            def tanpa_teratas(n):
                # Hampiran: tiap transaksi 1/K modal, tanpa urutan waktu. Dengan
                # semua transaksi hampiran ini ~3 poin di atas CAGR sebenarnya,
                # jadi angka "tanpa teratas" di bawah juga sedikit terlalu baik.
                sisa = np.sort(r)[:-n] if n < len(r) else r
                return (np.prod(1 + sisa / K) ** (1 / tahun) - 1) * 100

            terbaik = sorted(tr, key=lambda x: -x[0])[:3]
            rows.append({'strategi': nama, 'dasar': round(cagr, 1),
                         'acak min/med/max': '%.1f / %.1f / %.1f' % (min(acak), np.median(acak), max(acak)),
                         'ongkos x2': round(ringkas(simulasi(ps, ev, mulai, akhir, slip=0.005)[0])[0], 1),
                         'tahan 20h': round(ringkas(simulasi(ps, ev, mulai, akhir, h=20)[0])[0], 1),
                         '5 slot': round(ringkas(simulasi(ps, ev, mulai, akhir, k=5)[0])[0], 1),
                         '20 slot': round(ringkas(simulasi(ps, ev, mulai, akhir, k=20)[0])[0], 1),
                         'tanpa 10 teratas (hampiran)': round(tanpa_teratas(10), 1),
                         '3 terbaik': ', '.join('%s %+.0f%%' % (t, v * 100) for v, t, _ in terbaik)})
        print(pd.DataFrame(rows).set_index('strategi').to_string())


if __name__ == '__main__':
    perintah = sys.argv[1] if len(sys.argv) > 1 else 'dasar'
    if perintah == 'dasar':
        main_dasar()
    elif perintah == 'stres':
        main_stres()
    else:
        print(__doc__)
        sys.exit(2)
