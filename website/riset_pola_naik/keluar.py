"""
Cara KELUAR dari sinyal Tembus Basis -- dan apakah filter rezim pasar membantu.

KENAPA
Tembus basis / puncak 52 minggu untung dari ekor kanan: win per transaksi
~47%, tanpa 10 transaksi terbaik portofolionya balik ke kisaran beli-semua,
drawdown -45%. Jadi pertanyaan berikutnya bukan "masuk di mana" lagi, tapi
"keluar kapan" -- aturan yang memotong yang rugi tanpa memotong pemenang
besar sebelum waktunya.

DESAIN (didaftar SEBELUM hasil dilihat)
Aturan keluar, semuanya pakai close; yang dipicu kondisi keluar di close
HARI BERIKUTNYA (sama dengan konvensi masuk -- sinyal baru diketahui
setelah tutup):
    H60     tahan 60 hari bursa (pembanding = yang dipakai BUKTI sekarang)
    H120    tahan 120 hari
    TS10    trailing: keluar kalau close <= 90% close tertinggi sejak masuk, maks 120 hari
    TS15    idem 85%
    TS20    idem 80%
    SL8     cut loss: keluar kalau close <= 92% harga masuk, selain itu 60 hari
    X20     keluar kalau close <= 90% tertinggi 20 hari (pemicu turun_dari_puncak di
            chart app -- negatif terhadap pasar 13/14 tahun), maks 120 hari
Filter rezim: masuk hanya kalau IHSG di atas MA200-nya pada hari sinyal.

Sel sama dengan uji.py: pilih di separuh A 2013-2019, uji di separuh B
2020-2026. Pembanding transaksi = indeks rata-rata-sama emiten layak di
JENDELA YANG SAMA PERSIS (masuk s.d. keluar), jadi aturan yang menahan lebih
lama tidak dapat kredit dari pasar yang kebetulan naik.

HASIL (23 Sep 2026)
Portofolio 10 slot, ongkos pulang-pergi 0,9%, MEDIAN dari 10 urutan
pengisian slot acak (`keluar stres`), CAGR% / drawdown terdalam%:

                     puncak 52mg + vol              tembus basis + vol
                   PILIH A   UJI B     SEMUA       PILIH A   UJI B     SEMUA
    H60 (skrg)    10,0/-38  25,6/-50  22,9/-44    -0,6/-59  16,3/-38   4,3/-58
    TS10          12,4/-18  27,6/-24  26,4/-25     2,5/-32  25,5/-21   8,3/-27
    X20           10,2/-17  30,9/-22  28,6/-22     1,1/-31  19,8/-22   7,5/-28
    TS20          21,5/-22  36,2/-35  20,9/-43     8,6/-34   8,8/-22  11,9/-42
    SL8           11,8/-17  26,1/-33  23,5/-40    -0,2/-37  19,3/-26   9,9/-37

- TS10 dan X20 lebih baik dari H60 di KEENAM kombinasi, CAGR maupun
  drawdown -- drawdown kira-kira separuhnya. Trailing 15-20% tidak
  konsisten (kadang CAGR lebih tinggi, kadang lebih rendah).
- Per transaksi, sel UJI, vs pasar per 20 hari yang ditahan: puncak
  +0,85% (t 1,6) -> TS10 +3,16% (t 4,7), X20 +3,18% (t 4,8); tembus basis
  +1,43% (t 4,3) -> +2,06% (t 5,9) / +1,94% (t 6,3).
- Harganya: win per transaksi turun ke ~41-44%, rata-rata ditahan 24-44
  hari, transaksi ~2x lebih banyak (ongkosnya sudah dihitung).
- Kenapa masuk akal: X20 = pemicu turun_dari_puncak di chart, yang
  negatif terhadap pasar 13/14 tahun. Keluar saat ia menyala menghindari
  lanjutannya; pemenang yang sedang tren jarang turun 10% dari puncaknya,
  jadi mereka tetap ditahan sampai 120 hari.
- Filter IHSG > MA200 (satu urutan): CAGR turun di hampir semua kombinasi
  (puncak SEMUA H60 25,8 -> 14,1), drawdown nyaris tidak membaik; ditumpuk
  di atas trailing malah lebih buruk. Tidak dipakai.
- Lintasan vs pasar tanpa aturan keluar (semua emiten): puncak +1,5% di
  H+20, +3,4% di H+60, +4,4% di H+120 -- menumpuk pelan, bukan sekali lonjak.

BATAS: TS10/X20 terlihat unggul SETELAH semua sel dilihat (enam varian
diuji). Karena itu masih perlu bukti ke depan -- jurnal Tembus Basis
merekam harga masuk, jadi aturan keluar ini bisa diukur di jurnal yang
sama tanpa mengubah apa pun.

PEMAKAIAN: python -m website.riset_pola_naik.keluar [stres]
"""
import sys
import warnings

import numpy as np
import pandas as pd

from . import uji

warnings.filterwarnings('ignore')

ATURAN_KELUAR = ['H60', 'H120', 'TS10', 'TS15', 'TS20', 'SL8', 'X20']
MAKS = 120
BIAYA = 0.004 + 2 * 0.0025      # 0,15% beli + 0,25% jual + slippage 0,25%/sisi


def siapkan(p):
    """Array per emiten + indeks pasar kumulatif (log) untuk pembanding jendela."""
    per = {}
    for t, d in p.groupby('ticker', sort=False):
        d = d.sort_values('hist')
        per[t] = {'h0': int(d['hist'].iloc[0]),
                  'date': d['date'].to_numpy(),
                  'close': d['close'].to_numpy(float),
                  'bad': (d['ret1'].abs() > 0.45).to_numpy()}
    # indeks pasar: rata-rata log-return harian emiten yang layak KEMARIN
    q = p[['ticker', 'date', 'close', 'elig', 'ret1']].sort_values(['ticker', 'date'])
    q['lr'] = np.log(q['close']).groupby(q['ticker']).diff()
    q['layak_kmrn'] = q.groupby('ticker')['elig'].shift(1).fillna(False).astype(bool)
    q = q[q['layak_kmrn'] & (q['ret1'].abs() <= 0.45)]
    pasar = q.groupby('date')['lr'].mean().sort_index().cumsum()
    return per, pasar


def keluar_di(a, i, aturan):
    """Indeks baris keluar untuk masuk di baris i (close i), atau None."""
    c = a['close']
    n = len(c)
    if aturan == 'H60':
        j = i + 60
    elif aturan == 'H120':
        j = i + MAKS
    else:
        akhir = min(i + MAKS, n - 1)
        jalan = c[i:akhir + 1]
        if aturan.startswith('TS'):
            batas = 1 - int(aturan[2:]) / 100.0
            puncak = np.maximum.accumulate(jalan)
            kena = np.flatnonzero((jalan <= batas * puncak)[1:]) + 1
            j = i + (kena[0] + 1 if len(kena) else MAKS)
        elif aturan == 'SL8':
            kena = np.flatnonzero((jalan[:61] <= 0.92 * c[i])[1:]) + 1
            j = i + (kena[0] + 1 if len(kena) else 60)
        elif aturan == 'X20':
            j = i + MAKS
            for k in range(1, len(jalan)):
                lo = max(0, i + k - 19)
                if c[i + k] <= 0.90 * c[lo:i + k + 1].max():
                    j = i + k + 1
                    break
        else:
            raise ValueError(aturan)
    if j >= n:
        return None
    if a['bad'][i + 1:j + 1].any():     # loncatan data/aksi korporasi di jalur -> buang
        return None
    return j


def transaksi(ev, per, pasar, aturan):
    rows = []
    for t, h, tgl in zip(ev['ticker'], ev['hist'], ev['date']):
        a = per[t]
        i = int(h) - a['h0'] + 1            # masuk di close hari setelah sinyal
        if i >= len(a['close']):
            continue
        j = keluar_di(a, i, aturan)
        if j is None:
            continue
        r = np.log(a['close'][j] / a['close'][i])
        d_in, d_out = a['date'][i], a['date'][j]
        try:
            m = pasar.loc[d_out] - pasar.loc[d_in]
        except KeyError:
            continue
        rows.append({'ticker': t, 'masuk': d_in, 'keluar': d_out, 'tahan': j - i, 'r': r, 'lebih': r - m,
                     'bulan': pd.Timestamp(tgl).to_period('M')})
    return pd.DataFrame(rows)


def ringkas_tx(tx):
    if len(tx) < 30:
        return {'n': len(tx)}
    return {
        'n': len(tx),
        'win%': round((tx['r'] > 0).mean() * 100, 1),
        'median%': round((np.exp(tx['r'].median()) - 1) * 100, 1),
        'majemuk/tx%': round((np.exp(tx['r'].mean()) - 1) * 100, 2),
        'tahan (hari)': round(tx['tahan'].mean(), 0),
        'vs pasar/tx%': round((np.exp(tx['lebih'].mean()) - 1) * 100, 2),
        'vs pasar per 20h%': round((np.exp(tx['lebih'].sum() / tx['tahan'].sum() * 20) - 1) * 100, 2),
        't': round(uji.t_klaster(tx['lebih'].to_numpy(), tx['bulan'].astype(str).to_numpy()), 1),
    }


def portofolio(tx, kal, harga, k=10, seed=None):
    """Simulasi slot sama besar dengan tanggal masuk/keluar per transaksi.
    `seed` mengacak urutan sinyal DI DALAM hari yang sama -- urutan itu yang
    menentukan siapa kebagian slot, dan hasilnya sensitif terhadapnya."""
    if tx.empty:
        return {}
    if seed is not None:
        tx = tx.sample(frac=1, random_state=seed)
    tx = tx.sort_values('masuk', kind='stable')
    per_masuk = {}
    for r in tx.itertuples():
        per_masuk.setdefault(r.masuk, []).append(r)
    kas, pegang, kurva, hasil = 1.0, {}, [], []
    mulai = tx['masuk'].min()
    akhir = tx['keluar'].max()
    for d in kal[(kal >= mulai) & (kal <= akhir)]:
        for key in [key for key, x in pegang.items() if x['keluar'] == d]:
            x = pegang.pop(key)
            nilai = x['lembar'] * harga[x['t']].get(d, x['px']) * (1 - 0.0025 - 0.0025)
            kas += nilai
            hasil.append(nilai / x['modal'] - 1)
        for x in pegang.values():
            x['px'] = harga[x['t']].get(d, x['px'])
        ekuitas = kas + sum(x['lembar'] * x['px'] for x in pegang.values())
        for r in per_masuk.get(d, []):
            if len(pegang) >= k or any(x['t'] == r.ticker for x in pegang.values()):
                continue
            px = harga[r.ticker].get(d)
            alokasi = min(ekuitas / k, kas)
            if px is None or not np.isfinite(px) or alokasi <= ekuitas * 0.01:
                continue
            kas -= alokasi
            pegang[(r.ticker, d)] = {'t': r.ticker, 'lembar': alokasi * (1 - 0.0015 - 0.0025) / px,
                                     'modal': alokasi, 'keluar': r.keluar, 'px': px}
        kurva.append((d, kas + sum(x['lembar'] * x['px'] for x in pegang.values())))
    c = pd.Series(dict(kurva))
    tahun = max((c.index[-1] - c.index[0]).days / 365.25, 0.5)
    h = np.array(hasil)
    return {'CAGR%': round(((c.iloc[-1] / c.iloc[0]) ** (1 / tahun) - 1) * 100, 1),
            'maxDD%': round((c / c.cummax() - 1).min() * 100, 1),
            'transaksi': len(h), 'win%': round((h > 0).mean() * 100, 1) if len(h) else None}


def main():
    p = uji.muat()
    per, pasar = siapkan(p)
    kal = pd.DatetimeIndex(sorted(p['date'].unique()))
    harga = {t: dict(zip(pd.DatetimeIndex(a['date']), a['close'])) for t, a in per.items()}
    base = (p['brk30'] == 1) & (p['prevrange30'] < 0.20) & (p['vspike'] > 2)
    MASUK = {'puncak 52mg + vol': (p['hi250'] == 1) & (p['vspike'] > 2),
             'tembus basis + vol': base}
    SEL = {'PILIH (A, 2013-19)': (p['half'] == 0) & (p['period'] == 1),
           'UJI (B, 2020-26)': (p['half'] == 1) & (p['period'] == 2),
           'SEMUA (2013-26)': p['date'] <= '2026-06-01'}
    rezim = p['ihsg_ma200'] > 0

    for nama_masuk, m in MASUK.items():
        for nama_sel, s in SEL.items():
            print('\n' + '=' * 120 + '\n%s | %s\n' % (nama_masuk, nama_sel) + '=' * 120)
            rows = []
            for filt, cond in (('-', pd.Series(True, index=p.index)), ('IHSG>MA200', rezim)):
                ev = uji.jeda(p[m.fillna(False) & p['elig'] & s & cond])
                for ak in ATURAN_KELUAR:
                    tx = transaksi(ev, per, pasar, ak)
                    r = {'filter': filt, 'keluar': ak}
                    r.update(ringkas_tx(tx))
                    r.update({'porto ' + k: v for k, v in portofolio(tx, kal, harga).items()})
                    rows.append(r)
            print(pd.DataFrame(rows).set_index(['filter', 'keluar']).to_string())

    # Lintasan: di hari ke berapa keunggulan terhadap pasar terkumpul?
    print('\n' + '=' * 120 + '\nLINTASAN vs pasar (majemuk, %), semua emiten 2013-2026, tanpa aturan keluar\n' + '=' * 120)
    rows = []
    for nama_masuk, m in MASUK.items():
        ev = uji.jeda(p[m.fillna(False) & p['elig'] & (p['date'] <= '2026-02-01')])
        r = {'masuk': nama_masuk, 'n': len(ev)}
        for hari in (1, 5, 10, 20, 40, 60, 90, 120):
            v = []
            for t, h in zip(ev['ticker'], ev['hist']):
                a = per[t]
                i = int(h) - a['h0'] + 1
                j = i + hari
                if j >= len(a['close']) or a['bad'][i + 1:j + 1].any():
                    continue
                try:
                    v.append(np.log(a['close'][j] / a['close'][i]) - (pasar.loc[a['date'][j]] - pasar.loc[a['date'][i]]))
                except KeyError:
                    continue
            r['H+%d' % hari] = round((np.exp(np.mean(v)) - 1) * 100, 2) if v else None
        rows.append(r)
    print(pd.DataFrame(rows).set_index('masuk').to_string())


def main_stres(n_seed=10):
    """Portofolio tiap aturan keluar dengan 10 urutan pengisian slot acak --
    satu urutan saja bisa menggeser CAGR belasan poin (lihat simulasi stres)."""
    p = uji.muat()
    per, pasar = siapkan(p)
    kal = pd.DatetimeIndex(sorted(p['date'].unique()))
    harga = {t: dict(zip(pd.DatetimeIndex(a['date']), a['close'])) for t, a in per.items()}
    base = (p['brk30'] == 1) & (p['prevrange30'] < 0.20) & (p['vspike'] > 2)
    MASUK = {'puncak 52mg + vol': (p['hi250'] == 1) & (p['vspike'] > 2), 'tembus basis + vol': base}
    SEL = {'PILIH (A, 2013-19)': (p['half'] == 0) & (p['period'] == 1),
           'UJI (B, 2020-26)': (p['half'] == 1) & (p['period'] == 2),
           'SEMUA (2013-26)': p['date'] <= '2026-06-01'}
    rows = []
    for nm, m in MASUK.items():
        for ns, s in SEL.items():
            ev = uji.jeda(p[m.fillna(False) & p['elig'] & s])
            for ak in ['H60', 'TS10', 'TS15', 'TS20', 'X20', 'SL8']:
                tx = transaksi(ev, per, pasar, ak)
                hasil = [portofolio(tx, kal, harga, seed=sd) for sd in range(n_seed)]
                cagr = np.array([h['CAGR%'] for h in hasil])
                dd = np.array([h['maxDD%'] for h in hasil])
                rows.append({'masuk': nm, 'sel': ns, 'keluar': ak,
                             'CAGR median': round(float(np.median(cagr)), 1),
                             'CAGR min-max': '%.1f .. %.1f' % (cagr.min(), cagr.max()),
                             'maxDD median': round(float(np.median(dd)), 1),
                             'maxDD terburuk': round(float(dd.min()), 1)})
    print(pd.DataFrame(rows).set_index(['masuk', 'sel', 'keluar']).to_string())


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == 'stres':
        main_stres()
    else:
        main()
