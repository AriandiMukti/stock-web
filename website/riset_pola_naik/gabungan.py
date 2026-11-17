"""
Gabungan tiga menu teruji: masuk dari Tembus Basis, alarm keluar dari Skor
Kecondongan, ukuran posisi dari Takaran Risiko. (18 Okt 2026)

KENAPA
Tiga menu ini masing-masing lolos luar sampel, tapi untuk pertanyaan yang
berbeda -- dan tiga bagian yang teruji belum tentu jadi gabungan yang
teruji. Sebelum ada halaman yang menyatukannya, dua pertanyaan diuji:
  1. Apakah "saham yang dipegang merosot ke desil 1 Kecondongan" berguna
     sebagai alarm KELUAR? (Sebagai saringan MASUK ia tidak berguna: dari 43
     sinyal jurnal maju 22 Sep - 17 Okt 2026, tidak ada satu pun di desil 1;
     paling rendah desil 5. Sinyal tembus/puncak memang selalu dekat puncak.)
  2. Apakah ukuran posisi "setara risiko" Takaran Risiko (100 / x_rugi %
     dari slot normal) lebih baik dari slot sama rata yang dipakai BUKTI?

DESAIN (didaftar SEBELUM hasil dilihat)
Masuk : sinyal menu Tembus Basis = tembus basis + vol ATAU puncak 52 mgg +
        vol (gabungan, seperti halaman), satu per emiten per 20 bar,
        masuk di close hari setelah sinyal. Dua aturan masuk itu juga
        dilaporkan terpisah sebagai pemeriksaan.
Keluar: H60       tahan 60 hari (dasar BUKTI)
        H60+D1    idem, tapi keluar di close BESOKNYA kalau desil hari ini = 1
        TS10      trailing 10%, maks 120 hari (pemenang keluar.py)
        TS10+D1   idem + alarm desil 1
        Desil = rumus kecondongan.py persis: rata-rata persentil dd250 dan
        persentil terbalik vol20 di antara emiten layak hari itu.
Ukuran: sama      ekuitas / 10 per slot (dasar BUKTI)
        setara    slot x (1 / x_rugi), dibatasi kas -- angka "ukuran_setara"
                  yang ditampilkan Takaran Risiko apa adanya
        kecilkan  slot x min(1, 1 / x_rugi) -- cuma mengecilkan yang liar,
                  tidak pernah membesarkan (versi di mockup halaman)
        x_rugi dari risiko.GRID memakai definisi risiko._ukur: simpangan
        baku pct_change 20 hari (%) dan close / close tertinggi 60 hari.
Sel   : PILIH (emiten A 2013-19), UJI (emiten B 2020-26), SEMUA -- sama
        dengan uji.py / keluar.py. Portofolio 10 slot, ongkos pulang-pergi
        0,9%, MEDIAN dari 10 urutan pengisian slot acak.

KRITERIA (juga ditulis sebelum hasil)
Sebuah varian dianggap MEMBANTU hanya kalau, dibanding pasangannya
(D1 vs tanpa D1 dengan keluar & ukuran sama; setara/kecilkan vs sama),
CAGR median tidak turun DAN drawdown terdalam median tidak memburuk, di
sel UJI, dengan arah yang sama di sel PILIH. Kalau cuma salah satu sel,
statusnya "belum jelas", bukan "membantu".

BATAS YANG SUDAH DIKETAHUI
- GRID Takaran Risiko dikalibrasi di 2026 + 21 emiten 2016-2025, jadi
  untuk sel UJI ia bukan buta. Yang dikalibrasi BESARAN risiko, bukan
  return, jadi kebocorannya ke CAGR tidak langsung -- tapi tetap dicatat.
- Data Yahoo tanpa emiten delisting (survivorship), sama seperti riset lain.

PEMAKAIAN: python -m website.riset_pola_naik.gabungan   (~1 menit)

HASIL (18 Okt 2026)
===================
Pemeriksaan mesin: angka dasar sama persis dengan keluar.py (puncak H60
10,0 / 25,6 / 23,0; TS10 12,3 / 27,6 / 26,5; basis H60 -0,6 / 16,3).

Portofolio sinyal MENU (basis ATAU puncak), slot sama rata, CAGR% / maxDD%:
                       PILIH A 13-19   UJI B 20-26    SEMUA 13-26
    H60                 11,4 / -51      26,8 / -38     17,5 / -46
    H60 + D1            12,7 / -39      28,9 / -33     16,6 / -43
    TS10                10,9 / -27      27,5 / -26     19,2 / -32
    TS10 + D1            9,5 / -28      23,1 / -25     15,7 / -32

1. ALARM DESIL 1 -- MEMBANTU H60, MERUSAK TS10.
   - Di atas H60 lolos kriteria (CAGR naik & DD membaik di PILIH dan UJI).
     Transaksi yang kena alarm: +11,7%/tx vs pasar (t 5,5) di UJI, dipotong
     ~38 hari lebih awal. Menyala dulu di ~17% transaksi.
   - Di atas TS10 gagal di semua sel dan semua aturan masuk: alarm cuma
     menyala lebih dulu di 3-10% transaksi, dan yang kena justru RUGI
     -2,5 s.d. -3,3%/tx (t -1,2 s.d. -1,9). Untuk puncak 52 mgg nyaris
     tidak pernah menyala (0,1-0,3%) -- hasilnya identik dengan TS10.
   - Artinya desil 1 cuma trailing stop yang lebih lambat dan kasar. Kalau
     TS10 sudah dipakai, ia tidak menambah apa-apa; H60+D1 juga kalah dari
     TS10 di drawdown (-39/-33 vs -27/-26) dengan CAGR setara.

2. UKURAN SETARA RISIKO -- TIDAK MEMBANTU.
   - Menu + TS10: setara 10,1/-34 (PILIH), 27,0/-25 (UJI); kecilkan
     10,0/-29, 27,0/-24 -- CAGR turun di kedua sel, DD membaik cuma di UJI.
   - Puncak 52 mgg paling rusak: setara 10,0 -> 2,6 (PILIH H60), 25,6 ->
     19,4 (UJI H60). Sesuai dugaan: pemenang ekor kanan ada di saham liar,
     dan ukuran setara risiko justru mengecilkan mereka.
   - Sejalan dengan skor.py (ukuran ~1/vol tidak konsisten).

KESIMPULAN
Gabungan terbaik tetap yang sudah ada: sinyal Tembus Basis + TS10 + slot
sama rata. Kecondongan dan Takaran Risiko tidak menambah apa pun pada
strategi ini -- Takaran Risiko tetap berguna sebagai INFORMASI seberapa
keras saham berayun, bukan sebagai pengatur ukuran; desil 1 hanya berguna
untuk posisi yang TIDAK memakai trailing stop. TS10 sendiri dipilih
setelah semua sel keluar.py dilihat, jadi masih menunggu bukti jurnal maju.
"""
import sys
import time
import warnings

import numpy as np
import pandas as pd

from . import uji
from .keluar import siapkan, keluar_di, ringkas_tx
from .. import risiko as R

warnings.filterwarnings('ignore')

K = 10
N_SEED = 10
KELUAR = ['H60', 'H60+D1', 'TS10', 'TS10+D1']
UKURAN = ['sama', 'setara', 'kecilkan']


def tambah_kolom(p):
    """desil Kecondongan (antar emiten layak per tanggal) + x_rugi Takaran Risiko."""
    e = p['elig']
    q = p.loc[e, ['date', 'dd250', 'vol20']]
    rp = q.groupby('date')['dd250'].rank(pct=True)
    rt = q.groupby('date')['vol20'].rank(pct=True, ascending=False)
    skor = (rp + rt) / 2
    desil = np.ceil(skor.groupby(q['date']).rank(pct=True) * 10).clip(1, 10)
    p['desil'] = np.nan
    p.loc[e, 'desil'] = desil

    g = p.groupby('ticker', sort=False)['ret1']
    volp = g.transform(lambda s: s.rolling(20, min_periods=12).std()) * 100
    vlab = pd.cut(volp, R.VOL_BIN, labels=R.VOL_LAB).astype(str)
    dlab = pd.cut(p['dd60'], R.DD_BIN, labels=R.DD_LAB).astype(str)
    peta = {(v, d): (R._cari_sel(v, d) or {}).get('x_rugi') for v in R.VOL_LAB for d in R.DD_LAB}
    p['x_rugi'] = [peta.get((v, d)) for v, d in zip(vlab, dlab)]
    p['x_rugi'] = p['x_rugi'].astype(float)
    return p


def keluar_gab(a, i, aturan):
    """(j, kena_d1). Sampel transaksi SAMA untuk varian dengan/tanpa D1:
    kalau keluar dasarnya tidak bisa dihitung, dua-duanya dibuang."""
    dasar, _, d1 = aturan.partition('+')
    j = keluar_di(a, i, dasar)
    if j is None or not d1:
        return j, False
    kena = np.flatnonzero(a['desil'][i:j] == 1)       # close i .. j-1
    if len(kena):
        j2 = i + int(kena[0]) + 1                      # keluar close besoknya
        if j2 < j:
            return j2, True
    return j, False


def transaksi(ev, per, pasar, aturan):
    rows = []
    for t, h, tgl, x in zip(ev['ticker'], ev['hist'], ev['date'], ev['x_rugi']):
        a = per[t]
        i = int(h) - a['h0'] + 1
        if i >= len(a['close']):
            continue
        j, d1 = keluar_gab(a, i, aturan)
        if j is None:
            continue
        r = np.log(a['close'][j] / a['close'][i])
        d_in, d_out = a['date'][i], a['date'][j]
        try:
            m = pasar.loc[d_out] - pasar.loc[d_in]
        except KeyError:
            continue
        rows.append({'ticker': t, 'masuk': d_in, 'keluar': d_out, 'tahan': j - i, 'r': r, 'lebih': r - m,
                     'bulan': pd.Timestamp(tgl).to_period('M'), 'x_rugi': x, 'd1': d1})
    return pd.DataFrame(rows)


def portofolio(tx, kal, harga, ukuran='sama', k=K, seed=None):
    """keluar.portofolio + ukuran posisi. Ongkos sama persis."""
    if tx.empty:
        return {}
    if seed is not None:
        tx = tx.sample(frac=1, random_state=seed)
    tx = tx.sort_values('masuk', kind='stable')
    per_masuk = {}
    for r in tx.itertuples():
        per_masuk.setdefault(r.masuk, []).append(r)
    kas, pegang, kurva = 1.0, {}, []
    for d in kal[(kal >= tx['masuk'].min()) & (kal <= tx['keluar'].max())]:
        for key in [key for key, x in pegang.items() if x['keluar'] == d]:
            x = pegang.pop(key)
            kas += x['lembar'] * harga[x['t']].get(d, x['px']) * (1 - 0.0025 - 0.0025)
        for x in pegang.values():
            x['px'] = harga[x['t']].get(d, x['px'])
        ekuitas = kas + sum(x['lembar'] * x['px'] for x in pegang.values())
        for r in per_masuk.get(d, []):
            if len(pegang) >= k or any(x['t'] == r.ticker for x in pegang.values()):
                continue
            px = harga[r.ticker].get(d)
            f = 1.0
            if ukuran != 'sama' and np.isfinite(r.x_rugi) and r.x_rugi > 0:
                f = 1.0 / r.x_rugi
                if ukuran == 'kecilkan':
                    f = min(1.0, f)
            alokasi = min(ekuitas / k * f, kas)
            if px is None or not np.isfinite(px) or alokasi <= ekuitas * 0.01:
                continue
            kas -= alokasi
            pegang[(r.ticker, d)] = {'t': r.ticker, 'lembar': alokasi * (1 - 0.0015 - 0.0025) / px,
                                     'keluar': r.keluar, 'px': px}
        kurva.append((d, kas + sum(x['lembar'] * x['px'] for x in pegang.values())))
    c = pd.Series(dict(kurva))
    tahun = max((c.index[-1] - c.index[0]).days / 365.25, 0.5)
    return {'cagr': ((c.iloc[-1] / c.iloc[0]) ** (1 / tahun) - 1) * 100,
            'dd': (c / c.cummax() - 1).min() * 100}


def main():
    t0 = time.time()
    p = tambah_kolom(uji.muat())
    per, pasar = siapkan(p)
    for t, d in p.groupby('ticker', sort=False):
        per[t]['desil'] = d.sort_values('hist')['desil'].to_numpy()
    kal = pd.DatetimeIndex(sorted(p['date'].unique()))
    harga = {t: dict(zip(pd.DatetimeIndex(a['date']), a['close'])) for t, a in per.items()}
    print('siap %.0f detik' % (time.time() - t0), flush=True)

    basis = (p['brk30'] == 1) & (p['prevrange30'] < 0.20) & (p['vspike'] > 2)
    puncak = (p['hi250'] == 1) & (p['vspike'] > 2)
    MASUK = {'menu (basis ATAU puncak)': basis | puncak, 'puncak 52mg + vol': puncak, 'tembus basis + vol': basis}
    SEL = {'PILIH A 13-19': (p['half'] == 0) & (p['period'] == 1),
           'UJI B 20-26': (p['half'] == 1) & (p['period'] == 2),
           'SEMUA 13-26': p['date'] <= '2026-06-01'}

    porto, diag, pertx = [], [], []
    for nm, m in MASUK.items():
        for ns, s in SEL.items():
            ev = uji.jeda(p[m.fillna(False) & p['elig'] & s])
            # desil di hari sinyal -- memastikan ulang temuan jurnal maju di 13 tahun
            dsin = ev['desil'].value_counts(normalize=True)
            txs = {ak: transaksi(ev, per, pasar, ak) for ak in KELUAR}
            for ak, tx in txs.items():
                r = {'masuk': nm, 'sel': ns, 'keluar': ak}
                r.update(ringkas_tx(tx))
                pertx.append(r)
                for uk in UKURAN:
                    hs = [portofolio(tx, kal, harga, uk, seed=sd) for sd in range(N_SEED)]
                    porto.append({'masuk': nm, 'sel': ns, 'keluar': ak, 'ukuran': uk,
                                  'CAGR': round(float(np.median([h['cagr'] for h in hs])), 1),
                                  'CAGR min..max': '%.1f..%.1f' % (min(h['cagr'] for h in hs), max(h['cagr'] for h in hs)),
                                  'DD': round(float(np.median([h['dd'] for h in hs])), 1)})
            # Diagnosa D1: seberapa sering menyala lebih dulu, dan apa yang dihindarinya
            for dasar in ('H60', 'TS10'):
                a, b = txs[dasar], txs[dasar + '+D1']
                if a.empty:
                    continue
                g = a.merge(b, on=['ticker', 'masuk'], suffixes=('_a', '_b'))
                kena = g['d1_b'].to_numpy(bool)
                beda = (g['lebih_b'] - g['lebih_a']).to_numpy()
                row = {'masuk': nm, 'sel': ns, 'dasar': dasar, 'n': len(g),
                       'desil1 di hari sinyal %': round(dsin.get(1.0, 0) * 100, 2),
                       'D1 menyala dulu %': round(kena.mean() * 100, 1)}
                if kena.sum() >= 10:
                    row['selisih vs pasar, yg kena (%/tx)'] = round((np.exp(beda[kena].mean()) - 1) * 100, 2)
                    row['t'] = round(uji.t_klaster(beda[kena], g['bulan_b'].astype(str).to_numpy()[kena]), 1)
                    row['dipotong lebih awal (hari)'] = round(float((g['tahan_a'] - g['tahan_b'])[kena].mean()), 0)
                diag.append(row)
            print('.. %s | %s  %.0f detik' % (nm, ns, time.time() - t0), flush=True)

    pd.set_option('display.width', 250)
    print('\n' + '=' * 100 + '\nPORTOFOLIO (median 10 urutan acak): CAGR% / maxDD%\n' + '=' * 100)
    print(pd.DataFrame(porto).set_index(['masuk', 'sel', 'keluar', 'ukuran']).to_string())
    print('\n' + '=' * 100 + '\nDIAGNOSA ALARM DESIL 1\n' + '=' * 100)
    print(pd.DataFrame(diag).set_index(['masuk', 'sel', 'dasar']).to_string())
    print('\n' + '=' * 100 + '\nPER TRANSAKSI (ukuran tidak berpengaruh di sini)\n' + '=' * 100)
    print(pd.DataFrame(pertx).set_index(['masuk', 'sel', 'keluar']).to_string())


if __name__ == '__main__':
    main()
