"""
Skor Kecondongan: satu angka dari dua temuan yang SUDAH lolos sendiri-sendiri.
(23 Sep 2026)

KENAPA
Tiga cara mencari pola chart (Penemu Pola, ~40 pola di uji.py, analog &
klaster di analog.py) sampai ke kesimpulan yang sama: informasi arah dari
harga itu kecil, dan yang tersisa tertangkap dua hal --
  1. DEKAT PUNCAK 52 MINGGU (puncak 52 mgg + volume lolos luar sampel,
     13/14 tahun; lihat tembus_basis.py),
  2. TENANG, BUKAN LIAR ("volatilitas tinggi" gagal: menaikkan peluang
     +10% tapi kalah dari pasar setelah dimajemukkan; uji.py gagal_lain).
Daripada menambang pola keempat, dua hal itu digabung jadi satu peringkat
harian dan diuji SEKALI.

RUMUS -- DIKUNCI SEBELUM SEL VALIDASI DIBUKA, TIDAK ADA YANG DISETEL
  skor = rata-rata dua peringkat persentil di antara emiten layak hari itu
         (a) dd250 = close / close tertinggi 250 hari - 1   (makin dekat 0 makin tinggi)
         (b) vol20 = simpangan baku return log 20 hari        (makin kecil makin tinggi)
  Bobot sama, tanpa ambang. Desil 10 = 10% emiten dengan skor tertinggi.

KEJUJURAN SOAL SEL VALIDASI
IC kedua komponen di sel validasi (emiten B x 2020-2026) SUDAH terlihat di
pilot analog.py sebelum skor ini dirumuskan -- jadi angka validasi di sini
bukan uji buta. Yang membuat rumusnya tidak disetel ke validasi: kedua
komponen dipilih dari temuan sel pencarian yang lebih tua, bobotnya sama,
tanpa ambang. Uji yang benar-benar buta: jurnal maju di kecondongan.py.

PROTOKOL: sama dengan uji.py (pencarian emiten A x 2013-2019, validasi emiten
B x 2020-2026, dua sel silang). Tabel desil memakai satu pengamatan per
emiten per 20 bar supaya hasil 20 hari tidak tumpang tindih. Portofolio:
simulasi.py (10 slot, tahan 60 hari, ongkos pulang-pergi 0,9%), slot diisi
skor tertinggi dulu; varian ukuran posisi ~ 1/vol20 ("takaran risiko").

HASIL (23 Sep 2026)
===================
IC (korelasi peringkat skor vs return 60 hari terhadap pasar hari yang sama):
                                 dekat puncak      tenang         SKOR
    pencarian  A 2013-19        +0,101 (t 4,2)  +0,043 (t 2,0)  +0,094 (t 3,9)
    validasi   B 2020-26        +0,115 (t 5,3)  +0,129 (t 6,7)  +0,155 (t 6,9)
    silang     B 2013-19        +0,062 (t 3,4)  +0,066 (t 3,5)  +0,080 (t 4,2)
    silang     A 2020-26        +0,105 (t 5,2)  +0,120 (t 6,3)  +0,146 (t 6,6)
Positif di keempat sel. Gabungannya lebih baik dari tiap komponen di tiga
sel; di pencarian setara "dekat puncak" saja -- "tenang" jauh lebih berguna
sejak 2020 daripada 2013-2019.

Desil, vs pasar 60 hari (satu pengamatan per emiten per 20 bar):
                                 desil 1     desil 10
    pencarian  A 2013-19          -4,1%      +0,5% (t 0,3)
    validasi   B 2020-26          -8,2%      +5,0% (t 4,2)
    silang     B 2013-19          -5,8%      +2,9% (t 3,0)
    silang     A 2020-26          -8,6%      +4,2% (t 4,4)
Per tahun 2013-2026: desil 10 positif 12/14, desil 1 negatif 12/14.
Per lapis likuiditas (Rp1-5 M, 5-20 M, >20 M per hari): desil 1 negatif di
SEMUA sel dan SEMUA lapis (-2,6% s.d. -13,5%); desil 10 positif di
kebanyakan tapi ~0 di sel pencarian untuk dua lapis, dan paling lemah di
emiten paling likuid (+2,2% gabungan).

YANG PALING KOKOH ADALAH SISI BAWAHNYA: "jauh dari puncak dan liar"
konsisten kalah. Sisi atasnya ada, tapi lebih lemah dan tidak stabil di
2013-2019. Emiten yang delisting hilang dari data Yahoo; diperiksa dengan
arsip bulanan KSEI 2018-2026 yang memuatnya (delisting.py), versi bulanan
skor ini: desil 1 -4,2% -> -4,9% per 3 bulan kalau emiten delisting ikut
(yang mati dihitung -100%), desil 10 +2,9% -> +3,0%. Biasnya searah dugaan,
besarnya kecil.

Sebagai portofolio (10 slot, tahan 60 hari, ongkos 0,9%), CAGR / maxDD:
                                          2013-2026        2020-2026
    skor desil 10                        6,9% / -38%      8,5% / -29%
    skor desil 10, ukuran ~1/vol         5,8% / -43%     12,1% / -27%
    puncak 52 mgg + vol (sudah lolos)   18,6% / -45%     18,3% / -45%
    puncak 52 mgg + vol DAN desil 10     8,6% / -26%     12,5% / -23%
    beli semua emiten layak              3,7% / -65%      8,3% / -48%
    IHSG                                 3,0% / -42%      0,5% / -42%
Sebagai DAFTAR BELI skor ini biasa saja -- 2020-2026 setara beli-semua,
cuma kejatuhannya lebih dangkal. Ukuran posisi ~1/vol tidak konsisten
(turun di 2013-2026, naik di 2020-2026). Kegunaannya yang terbukti:
PERINGKAT dan SARINGAN -- hindari desil bawah, dan sebagai penyaring
sinyal puncak 52 minggu ia memangkas kejatuhan terdalam dari -45% ke -23%
dengan ongkos CAGR (18% -> 12,5%).

PEMAKAIAN (dari <project>/)
    python -m website.riset_pola_naik.skor
"""
import sys
import time
import warnings

import numpy as np
import pandas as pd

from . import simulasi as SIM
from . import uji as U

warnings.filterwarnings('ignore')

SEL = {
    'pencarian (A 2013-19)': (0, 1),
    'validasi (B 2020-26)': (1, 2),
    'silang emiten (B 2013-19)': (1, 1),
    'silang periode (A 2020-26)': (0, 2),
}


def muat():
    p = U.muat()
    e = p['elig']
    for kol in ('r_puncak', 'r_tenang', 'skor', 'desil'):
        p[kol] = np.nan
    g = p.loc[e].groupby('date')
    p.loc[e, 'r_puncak'] = g['dd250'].rank(pct=True)
    p.loc[e, 'r_tenang'] = g['vol20'].rank(pct=True, ascending=False)
    p.loc[e, 'skor'] = (p.loc[e, 'r_puncak'] + p.loc[e, 'r_tenang']) / 2
    p.loc[e, 'desil'] = np.ceil(p.loc[e].groupby('date')['skor'].rank(pct=True) * 10).clip(1, 10)
    p['year'] = p['date'].dt.year
    p['lr20'] = np.log1p(p['fwd20'])
    p['lr60'] = np.log1p(p['fwd60'])
    return p


def _ic(d, x, y):
    """IC harian (korelasi peringkat antar emiten), t dari rata-rata bulanan."""
    d = d[['date', 'month', x, y]].dropna()
    rx = d.groupby('date')[x].rank()
    ry = d.groupby('date')[y].rank()
    t = pd.DataFrame({'date': d['date'], 'month': d['month'], 'a': rx, 'b': ry})
    t['ab'] = t['a'] * t['b']; t['aa'] = t['a'] ** 2; t['bb'] = t['b'] ** 2
    s = t.groupby('date').agg(n=('a', 'size'), a=('a', 'mean'), b=('b', 'mean'),
                              ab=('ab', 'mean'), aa=('aa', 'mean'), bb=('bb', 'mean'),
                              month=('month', 'first'))
    s = s[s['n'] >= 15]
    ic = (s['ab'] - s['a'] * s['b']) / np.sqrt((s['aa'] - s['a'] ** 2) * (s['bb'] - s['b'] ** 2))
    bul = ic.groupby(s['month']).mean()
    return ic.mean(), bul.mean() / (bul.std(ddof=1) / np.sqrt(len(bul)))


def bagian_ic(p):
    print('\n' + '=' * 78)
    print('1. IC per sel -- komponen dan skor (60 hari; 20 hari dalam kurung)')
    print('=' * 78)
    e = p[p['elig']].copy()
    e['exc60'] = e['lr60'] - e['b_lr60']
    e['exc20'] = e['lr20'] - e['b_lr20']
    e['neg_vol'] = -e['vol20']
    rows = []
    for nama, (h, per) in SEL.items():
        d = e[(e['half'] == h) & (e['period'] == per)]
        r = {'sel': nama}
        for kol, lbl in (('dd250', 'dekat puncak'), ('neg_vol', 'tenang'), ('skor', 'SKOR')):
            a, ta = _ic(d, kol, 'exc60')
            b, tb = _ic(d, kol, 'exc20')
            r[lbl] = '%+.3f (t %+.1f) [%+.3f]' % (a, ta, b)
        rows.append(r)
    print(pd.DataFrame(rows).set_index('sel').to_string())


def _desil(d):
    rows = []
    for q, g in d.groupby('desil'):
        f60 = g[g['fwd60'].notna()]
        f20 = g[g['fwd20'].notna()]
        fp = g[g['fp60'].notna()]
        rows.append({'desil': int(q), 'n': len(g),
                     'vs pasar 20h %': (np.exp((f20['lr20'] - f20['b_lr20']).mean()) - 1) * 100,
                     'vs pasar 60h %': (np.exp((f60['lr60'] - f60['b_lr60']).mean()) - 1) * 100,
                     '+10% dulu %': (fp['fp60'] == 1).mean() * 100,
                     '-10% dulu %': (fp['fp60'] == -1).mean() * 100,
                     'pembanding +10% %': fp['b_fpup'].mean() * 100})
    return pd.DataFrame(rows).set_index('desil')


def bagian_desil(p):
    print('\n' + '=' * 78)
    print('2. DESIL SKOR (satu pengamatan per emiten per 20 bar)')
    print('=' * 78)
    s = p[p['elig'] & (p['hist'] % 20 == 0)]
    for nama, (h, per) in SEL.items():
        d = s[(s['half'] == h) & (s['period'] == per)]
        tab = _desil(d)
        atas = d[(d['desil'] == 10) & d['fwd60'].notna()]
        bawah = d[(d['desil'] == 1) & d['fwd60'].notna()]
        ta = U.t_klaster(atas['lr60'] - atas['b_lr60'], atas['month'].astype(str))
        print('\n  [%s]  desil 10 vs pasar 60h: t %+.1f' % (nama, ta))
        print(tab.loc[[1, 2, 5, 8, 9, 10]].round(1).to_string())
        del bawah


def bagian_tahun(p):
    print('\n' + '=' * 78)
    print('3. PER TAHUN: desil 10 vs pasar hari yang sama, 60 hari (semua emiten)')
    print('=' * 78)
    s = p[p['elig'] & (p['hist'] % 20 == 0) & p['fwd60'].notna()]
    atas = s[s['desil'] == 10]
    th = atas.groupby('year').apply(lambda g: (np.exp((g['lr60'] - g['b_lr60']).mean()) - 1) * 100)
    th10 = s[s['desil'] == 1].groupby('year').apply(lambda g: (np.exp((g['lr60'] - g['b_lr60']).mean()) - 1) * 100)
    tab = pd.DataFrame({'desil 10': th, 'desil 1': th10}).round(1)
    print(tab.T.to_string())
    print('  desil 10 positif %d/%d tahun' % ((th > 0).sum(), len(th)))


def _sim_bobot(ps, ev, mulai, akhir, k=10, h=60, slip=SIM.SLIP, bobot=None):
    """simulasi.simulasi dengan alokasi per posisi = ekuitas/k x bobot."""
    beli, jual = 0.0015 + slip, 0.0025 + slip
    ev = ev[(ev['date'] >= mulai) & (ev['date'] <= akhir) & ev['fwd60'].notna()]
    ev = ev.sort_values(['date', 'skor'], ascending=[True, False])
    masuk = {}
    for t, d, w in zip(ev['ticker'], ev['date'], ev[bobot] if bobot else np.ones(len(ev))):
        i = ps.pos[d] + 1
        if i + h <= ps.akhir:
            masuk.setdefault(i, []).append((t, float(w)))
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
        for t, w in masuk.get(i, []):
            if len(pegang) >= k or t in pegang:
                continue
            harga = ps.arr[i, ps.kol[t]]
            alokasi = min(ekuitas / k * w, kas)
            if not np.isfinite(harga) or harga <= 0 or alokasi <= ekuitas * 0.01:
                continue
            kas -= alokasi
            pegang[t] = {'lembar': alokasi * (1 - beli) / harga, 'modal': alokasi, 'keluar': i + h}
        kurva.append((ps.kal[i], kas + sum(x['lembar'] * ps.arr[i, ps.kol[t]] for t, x in pegang.items())))
    return pd.Series(dict(kurva)), transaksi


def bagian_portofolio(p):
    print('\n' + '=' * 78)
    print('4. PORTOFOLIO: 10 slot, tahan 60 hari, ongkos pulang-pergi 0,9%')
    print('=' * 78)
    ps = SIM.Pasar(p)
    e = p['elig']
    # Takaran risiko: alokasi ~ 1/vol20, dinormalkan ke median hari itu dan
    # dibatasi 0,5-1,5x supaya satu emiten super tenang tidak makan semua kas.
    p['bobot_risiko'] = (p.groupby('date')['vol20'].transform('median') / p['vol20']).clip(0.5, 1.5)
    top = U.jeda(p[e & (p['desil'] == 10)])
    puncak = U.jeda(p[e & (p['hi250'] == 1) & (p['vspike'] > 2)]).copy()
    puncak['skor'] = puncak['medval20']       # urutan pengisian slot: likuid dulu, seperti simulasi.py
    keduanya = U.jeda(p[e & (p['desil'] == 10) & (p['hi250'] == 1) & (p['vspike'] > 2)])
    for mulai, akhir in (('2013-01-01', '2026-06-01'), ('2020-01-01', '2026-06-01')):
        print('\n  %s -> %s' % (mulai, akhir))
        rows, span = [], None
        for nama, ev, bobot in (('SKOR desil 10', top, None),
                                ('SKOR desil 10, ukuran ~1/vol', top, 'bobot_risiko'),
                                ('puncak 52 mgg + vol (pembanding, sudah lolos)', puncak, None),
                                ('puncak 52 mgg + vol DAN skor desil 10', keduanya, None)):
            kurva, tr = _sim_bobot(ps, ev, mulai, akhir, bobot=bobot)
            span = (kurva.index[0], kurva.index[-1])
            cagr, dd, _ = SIM.ringkas(kurva)
            r = np.array([x[0] for x in tr])
            rows.append({'strategi': nama, 'CAGR%': round(cagr, 1), 'maxDD%': round(dd, 1),
                         'transaksi': len(r), 'win%': round((r > 0).mean() * 100, 1),
                         'median transaksi%': round(np.median(r) * 100, 1)})
        ew = (1 + ps.ew.loc[span[0]:span[1]]).cumprod()
        cagr, dd, _ = SIM.ringkas(ew)
        rows.append({'strategi': 'beli semua emiten layak (tanpa ongkos)', 'CAGR%': round(cagr, 1), 'maxDD%': round(dd, 1)})
        if ps.ihsg is not None:
            cagr, dd, _ = SIM.ringkas(ps.ihsg.loc[span[0]:span[1]].dropna())
            rows.append({'strategi': 'IHSG', 'CAGR%': round(cagr, 1), 'maxDD%': round(dd, 1)})
        print(pd.DataFrame(rows).set_index('strategi').to_string())


def bagian_likuiditas(p):
    print('\n' + '=' * 78)
    print('5. PER LAPIS LIKUIDITAS: vs pasar 60h (%%) desil 10 / desil 1, n dalam kurung')
    print('=' * 78)
    s = p[p['elig'] & (p['hist'] % 20 == 0) & p['fwd60'].notna()]
    lapis = {'Rp1-5 M/hari': (1e9, 5e9), 'Rp5-20 M/hari': (5e9, 20e9), '>Rp20 M/hari': (20e9, 1e15)}
    rows = []
    for nama, (h, per) in list(SEL.items()) + [('semua sel', (None, None))]:
        d = s if h is None else s[(s['half'] == h) & (s['period'] == per)]
        r = {'sel': nama}
        for ln, (lo, hi) in lapis.items():
            x = d[(d['medval20'] >= lo) & (d['medval20'] < hi)]
            a = x[x['desil'] == 10]
            b = x[x['desil'] == 1]
            r[ln] = '%+.1f (%d) / %+.1f (%d)' % ((np.exp((a['lr60'] - a['b_lr60']).mean()) - 1) * 100, len(a),
                                                 (np.exp((b['lr60'] - b['b_lr60']).mean()) - 1) * 100, len(b))
        rows.append(r)
    print(pd.DataFrame(rows).set_index('sel').to_string())


def main():
    t0 = time.time()
    p = muat()
    bagian_ic(p)
    bagian_desil(p)
    bagian_tahun(p)
    bagian_likuiditas(p)
    bagian_portofolio(p)
    print('\nselesai %.0f detik' % (time.time() - t0))


if __name__ == '__main__':
    sys.exit(main())
