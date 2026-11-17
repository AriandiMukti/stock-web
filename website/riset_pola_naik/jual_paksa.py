"""
Jual paksa reksa dana: bulan redemption industri menekan saham yang banyak
dipegang reksa dana, lalu pulih? (Coval & Stafford 2007, versi BEI.)
Kandidat A2 (reksa dana lokal) + A4 (reksa dana asing) di ARUS_PAKSA_KANDIDAT.md.

BEDA DARI event.py "kepemilikan"
  Di sana yang diuji keputusan PER SAHAM (porsi reksa dana di BBRI naik/turun)
  -> IC ~0. Di sini pemicunya arus INDUSTRI: kalau semua reksa dana kena
  redemption sekaligus, mereka menjual yang sudah dipegang tanpa menilai
  sahamnya. Saham kena karena siapa pemiliknya.

DATA
  Arsip KSEI bulanan (sumber_baru.muat_ksei): lembar per tipe investor, lokal
  & asing, Des 2012 - Mei 2013 dan Des 2017 - kini. Harga: panel uji.muat().

DESAIN (didaftar SEBELUM hasil dilihat, 28 Okt 2026)
  Arus industri bulan t, per seri (lokal MF / asing MF):
      F_t = sum((lembar_t - lembar_t-1) x harga_t-1) / sum(lembar_t-1 x harga_t-1)
  hanya emiten yang jumlah sahamnya berubah <= 2% (bukan rights/split), hanya
  bulan berurutan. Bulan |F_t| > 20% dibuang (reklasifikasi tipe investor,
  contoh PF Apr 2020 -71%).
  Bulan KELUAR = F_t di kuartil terbawah seri itu; MASUK = kuartil teratas
  (cermin). Ambang dihitung dari arus saja, tidak melihat return.

  Kelompok (antara emiten layak di hari pengukuran):
    V1 terpapar : kuintil teratas porsi MF di akhir bulan t-1
    V2 terjual  : di antara porsi MF t-1 >= 1%, kuintil dengan penurunan
                  porsi MF bulan t paling besar (yang benar-benar dijual)
  Jendela (log excess vs rata-rata emiten layak tanggal yang sama):
    tekanan   : 20 hari bursa sampai akhir bulan t (~bulan t) -- cek
                mekanisme, TIDAK bisa diambil (arsip baru terbit sesudahnya)
    pulih20/60: masuk di close sesudah hari bursa ke-7 setelah tanggal arsip
                bulan t (sama dengan event.py), 20 / 60 hari
  Statistik utama = selisih rata-rata BULANAN kelompok di bulan KELUAR dikurangi
  kelompok yang sama di bulan lain (selisih-dari-selisih: efek ukuran / big
  cap yang menempel pada porsi MF tinggi saling meniadakan). t Welch antar
  bulan (= klaster per bulan).
  Dua periode: arsip s.d. Des 2021 vs Jan 2022+.
  LOLOS kalau pulih20 atau pulih60 V1/V2: tanda sama dua periode, |t| gabungan
  >= 2, dan rata-rata kelompok di bulan KELUAR > +0,4% (biaya) untuk dipakai beli.

HASIL (28 Okt 2026, 18.954 emiten-bulan layak, 103 bulan 2013-01..2026-09,
27 bulan KELUAR lokal / 26 asing): GAGAL, keempat kombinasi.
  selisih bulan KELUAR vs bulan lain, % (t):
                       tekanan        pulih20        pulih60
  lokal V1 terpapar  -0,4 (-0,6)    -0,2 (-0,4)    +0,9 (+0,8)  P1 +3,0 / P2 -0,8
  lokal V2 terjual   -0,6 (-0,7)    +0,2 (+0,2)    +0,9 (+0,7)  P1 +1,9 / P2 -0,2
  asing V1 terpapar  -0,8 (-1,0)    +0,6 (+0,8)    -1,0 (-0,6)
  asing V2 terjual   -0,8 (-1,0)    +1,4 (+1,9)    +0,0 (+0,0)
  Bacaan: tekanan di bulan redemption hampir tak beda dari bulan biasa --
  mekanismenya sendiri tidak kelihatan di data bulanan. Saham yang porsi MF-nya
  turun banyak memang jatuh di bulan itu (V2 tekanan -3,5% lokal / -2,9% asing)
  TAPI sama saja di bulan biasa: itu efek "dijual = turun", bukan redemption.
  Paling dekat: asing V2 pulih20 +1,4% (P1 +0,5 t 0,5, P2 +2,3 t 2,2) -- tanda
  sama, |t| gabungan 1,9 < 2, satu periode yang membawa. Jangan diselamatkan
  dengan ganti ambang/jendela (itu memancing). Ambang KELUAR asing cuma
  -0,63%/bln -- redemption asing jarang besar; KSEI bulanan terlalu kasar untuk
  menangkap jual paksa yang biasanya selesai dalam hitungan hari.

PEMAKAIAN (dari <project>/)
    python -m website.riset_pola_naik.jual_paksa
"""
import warnings

import numpy as np
import pandas as pd

from . import uji as U
from .event import petakan
from .sumber_baru import muat_ksei

warnings.filterwarnings('ignore')

SERI = {'lokal MF': ('local', 'MF'), 'asing MF': ('foreign', 'MF')}
BELAH = pd.Timestamp('2022-01-01')
MAKS_ARUS = 20.0
JEDA_ARSIP = 6          # posisi +6 = hari bursa ke-7 sesudah tanggal arsip


def _urut(a, b):
    ya, ma = map(int, a.split('-')); yb, mb = map(int, b.split('-'))
    return (yb * 12 + mb) - (ya * 12 + ma) == 1


def arus_industri(bulan):
    """DataFrame per bulan berurutan: as_of, as_of_lalu, dan arus % tiap seri."""
    kunci = sorted(bulan)
    rows = []
    for a, b in zip(kunci, kunci[1:]):
        if not _urut(a, b):
            continue
        A, B = bulan[a]['securities'], bulan[b]['securities']
        r = {'bulan': b, 'as_of': pd.Timestamp(bulan[b]['as_of']), 'as_of_lalu': pd.Timestamp(bulan[a]['as_of'])}
        for nama, (sisi, tipe) in SERI.items():
            num = den = 0.0
            for t, x in A.items():
                y = B.get(t)
                if not y or not x.get('price') or not x.get('sec_num') or not y.get('sec_num'):
                    continue
                if abs(y['sec_num'] / x['sec_num'] - 1) > 0.02:
                    continue
                num += (y[sisi][tipe] - x[sisi][tipe]) * x['price']
                den += x[sisi][tipe] * x['price']
            r[nama] = 100 * num / den if den else np.nan
        rows.append(r)
    return pd.DataFrame(rows)


def porsi(bulan):
    """Emiten-bulan: porsi MF lokal & asing (% dari total lembar)."""
    rows = []
    for kunci, isi in bulan.items():
        for t, s in isi['securities'].items():
            total = s['local_total'] + s['foreign_total']
            if total <= 0:
                continue
            r = {'ticker': t, 'bulan': kunci}
            for nama, (sisi, tipe) in SERI.items():
                r[nama] = s[sisi][tipe] / total * 100
            rows.append(r)
    return pd.DataFrame(rows)


def _geser(kal, tanggal, n):
    pos = np.searchsorted(kal, np.asarray(tanggal, dtype='datetime64[ns]')) + n
    return np.where(pos < len(kal), kal[np.minimum(pos, len(kal) - 1)], np.datetime64('NaT'))


def bangun_kejadian(p, bulan, arus):
    """Emiten-bulan dengan porsi t-1, perubahan porsi bulan t, tekanan & pulih."""
    pr = porsi(bulan)
    lalu = pr.rename(columns={k: k + ' lalu' for k in SERI}).copy()
    kunci = sorted(bulan)
    berikut = {a: b for a, b in zip(kunci, kunci[1:]) if _urut(a, b)}
    lalu['bulan'] = lalu['bulan'].map(berikut)
    k = pr.merge(lalu.dropna(subset=['bulan']), on=['ticker', 'bulan'])
    k = k.merge(arus[['bulan', 'as_of']], on='bulan')
    for nama in SERI:
        k['d ' + nama] = k[nama] - k[nama + ' lalu']

    kal = np.sort(p['date'].unique())
    # tekanan: run-up 20 hari sampai hari terakhir <= tanggal arsip
    # (petakan memberi pre_exc20 sampai sehari SEBELUM hari event, jadi
    # event = hari bursa pertama SESUDAH tanggal arsip)
    k['tanggal'] = _geser(kal, k['as_of'] + pd.Timedelta(days=1), 0)
    ev_tek = petakan(p, k[['ticker', 'tanggal', 'bulan']].dropna(subset=['tanggal']))
    tek = ev_tek[['ticker', 'bulan', 'pre20']].rename(columns={'pre20': 'tekanan'})

    k['tanggal'] = _geser(kal, k['as_of'], JEDA_ARSIP)
    ev = petakan(p, k.drop(columns=['as_of']).dropna(subset=['tanggal']))
    ev['pulih20'] = np.log1p(ev['fwd20']) - ev['b_lr20']
    ev['pulih60'] = np.log1p(ev['fwd60']) - ev['b_lr60']
    ev = ev.merge(tek, on=['ticker', 'bulan'], how='left')
    ev['periode'] = np.where(pd.to_datetime(ev['bulan']) < BELAH, 1, 2)
    return ev


def kelompok(ev, nama):
    """Kolom bool V1/V2 per seri, dihitung per bulan."""
    g = ev.groupby('bulan')
    v1 = g[nama + ' lalu'].rank(pct=True) > 0.8
    pegang = ev[nama + ' lalu'] >= 1.0
    r = ev.loc[pegang].groupby('bulan')['d ' + nama].rank(pct=True)
    v2 = pd.Series(False, index=ev.index)
    v2.loc[r.index] = r <= 0.2
    return v1, v2


def welch(a, b):
    a, b = np.asarray(a, float), np.asarray(b, float)
    a, b = a[np.isfinite(a)], b[np.isfinite(b)]
    if len(a) < 4 or len(b) < 4:
        return np.nan
    se = np.sqrt(a.var(ddof=1) / len(a) + b.var(ddof=1) / len(b))
    return (a.mean() - b.mean()) / se if se > 0 else np.nan


def laporan(ev, arus, nama):
    a = arus.dropna(subset=[nama])
    a = a[a[nama].abs() <= MAKS_ARUS]
    q1, q3 = a[nama].quantile([0.25, 0.75])
    jenis = pd.Series('biasa', index=a['bulan'])
    jenis[a.set_index('bulan')[nama] <= q1] = 'KELUAR'
    jenis[a.set_index('bulan')[nama] >= q3] = 'MASUK'

    print('\n' + '=' * 100)
    print('%s: %d bulan sah (buang %d bulan |arus| > %.0f%%), ambang KELUAR <= %+.2f%%, MASUK >= %+.2f%%'
          % (nama.upper(), len(a), arus[nama].notna().sum() - len(a), MAKS_ARUS, q1, q3))
    print('  bulan KELUAR: ' + ', '.join('%s (%+.1f)' % (b, f) for b, f in
                                       a.loc[a[nama] <= q1, ['bulan', nama]].itertuples(index=False)))
    print('=' * 100)

    d = ev[ev['bulan'].isin(jenis.index)].copy()
    d['jenis'] = d['bulan'].map(jenis)
    v1, v2 = kelompok(d, nama)
    rows = []
    for vn, mask in [('V1 terpapar (porsi MF t-1 kuintil atas)', v1),
                     ('V2 terjual (porsi turun paling banyak)', v2)]:
        x = d[mask]
        for jendela in ('tekanan', 'pulih20', 'pulih60'):
            bul = x.groupby(['bulan', 'jenis', 'periode'])[jendela].mean().reset_index()
            r = {'kelompok': vn[:2], 'jendela': jendela}
            for per, lab in [((1, 2), 'gab'), ((1,), 'P1'), ((2,), 'P2')]:
                b = bul[bul['periode'].isin(per)]
                kel = b.loc[b['jenis'] == 'KELUAR', jendela]
                lain = b.loc[b['jenis'] != 'KELUAR', jendela]
                r[lab + ' keluar%'] = (np.exp(kel.mean()) - 1) * 100
                r[lab + ' selisih'] = (np.exp(kel.mean()) - np.exp(lain.mean())) * 100
                r[lab + ' t'] = welch(kel, lain)
            r['bln keluar'] = int((bul['jenis'] == 'KELUAR').sum())
            r['n emiten-bln'] = int((x['jenis'] == 'KELUAR').sum())
            if jendela != 'tekanan':
                masuk = bul.loc[bul['jenis'] == 'MASUK', jendela]
                r['cermin MASUK%'] = (np.exp(masuk.mean()) - 1) * 100
            rows.append(r)
    t = pd.DataFrame(rows).set_index(['kelompok', 'jendela'])
    with pd.option_context('display.width', 250, 'display.float_format', '{:+.2f}'.format):
        print(t.to_string())
    return t


def main():
    p = U.muat()
    p = p.sort_values(['ticker', 'date']).reset_index(drop=True)
    p['lret20'] = np.log1p(p['ret20'])
    b = p[p['elig']].groupby('date')['lret20'].mean().rename('b_lret20')
    p = p.merge(b, left_on='date', right_index=True, how='left')
    p['pre_exc20'] = p['lret20'] - p['b_lret20']
    p['year'] = p['date'].dt.year

    bulan = muat_ksei()
    arus = arus_industri(bulan)
    ev = bangun_kejadian(p, bulan, arus)
    print('\nemiten-bulan layak: %d | bulan: %d (%s .. %s)'
          % (len(ev), ev['bulan'].nunique(), ev['bulan'].min(), ev['bulan'].max()))
    for nama in SERI:
        laporan(ev, arus, nama)


if __name__ == '__main__':
    main()
