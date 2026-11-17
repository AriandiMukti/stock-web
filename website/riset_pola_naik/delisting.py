"""
Lubang survivorship: seberapa besar emiten yang DELISTING mengubah angka
riset di app ini? (23 Sep 2026)

MASALAHNYA
Cache harga Yahoo (888 emiten) cuma berisi emiten yang MASIH tercatat. Dari
499 saham di arsip KSEI Januari 2013, 101 tidak ada di cache itu -- dan
Yahoo tidak menyimpan harga harian satu pun dari ke-101 itu (dicoba
langsung, 0 dari 101). Emiten yang mati hilang beserta kerugiannya, jadi
semua backtest agak terlalu optimistis -- paling parah untuk kelompok
"jatuh dan liar".

JALAN KELUAR YANG ADA: HARGA AKHIR BULAN KSEI
Arsip bulanan KSEI (sumber_baru.py) memuat SEMUA saham yang tercatat bulan
itu, termasuk yang kemudian delisting, lengkap dengan harga dan jumlah saham.
Harian tidak bisa, bulanan bisa. Modul ini:
  1. mengukur besar lubangnya per tahun: berapa emiten hilang, dan return
     12 bulan terakhir mereka sebelum hilang;
  2. membandingkan return rata-rata SEMUA saham vs saham yang ada di cache
     Yahoo -- selisihnya = bias survivorship "beli semua";
  3. menguji ulang Skor Kecondongan versi BULANAN (dekat puncak 12 bulan +
     volatilitas 12 bulan) dengan dan tanpa emiten delisting, dengan dua
     perlakuan untuk emiten yang hilang di tengah jalan: dibuang (seperti
     Yahoo) atau dianggap -100% (batas terburuk).

BATAS
- Harga KSEI = harga penutupan pada tanggal arsip, BELUM disesuaikan aksi
  korporasi. Pemecahan saham dikenali dari lompatan jumlah saham (rasio
  >= 1,9x atau <= 0,55x) dan return bulan itu disesuaikan; penerbitan
  saham baru (rights) tidak disesuaikan. Dividen tidak ikut -- sama untuk
  yang hidup dan yang mati.
- Delisting bisa karena bangkrut (nol), merger atau go-private (sering
  dengan premi). Tanpa alasan per emiten, "-100%" adalah batas terburuk,
  bukan perkiraan.
- Arsip 2013-06 s.d. ~2017 banyak bolong (lihat ksei_riwayat/_log.json);
  bulan yang bolong membuat return antar-arsip mencakup lebih dari sebulan
  -- dinormalkan tidak, jadi analisis bulanan cuma memakai pasangan arsip
  berjarak 20-45 hari.

HASIL (23 Sep 2026; arsip Des 2012-Mei 2013 + Des 2017-Sep 2026)
=================================================================
1. Lubangnya lebih kecil dari yang dikira, untuk saham yang layak dibeli.
   "Tidak ada di cache Yahoo" TIDAK sama dengan delisting: sebagian besar
   dari 101 saham KSEI 2013 yang tidak ada di cache masih muncul di arsip
   sesudahnya. Yang benar-benar hilang dari arsip: 56 emiten, kebanyakan
   saham yang sudah lama disuspensi (harga beku; 20-50% di Rp50).
2. Bias "beli semua" (kapitalisasi >= Rp500 M): -1 s.d. +3 poin persen per
   tahun, kebanyakan < 1,5 -- yang terlihat saja; bulan sesudah emiten
   hilang tidak terhitung.
3. Skor Kecondongan versi bulanan (2018-05 .. 2026-09, tanpa harga beku),
   vs rata-rata semua emiten, 3 bulan ke depan:
                                         desil 1    desil 10
       hanya emiten di cache Yahoo        -4,2%      +2,9%
       semua emiten KSEI, yang mati dibuang -4,7%    +3,0%
       semua emiten KSEI, yang mati -100%   -4,9%    +3,0%
   Memasukkan emiten delisting membuat desil 1 SEDIKIT LEBIH BURUK dan
   desil 10 tidak berubah -- arah bias yang diduga, besarnya kecil.
   Temuan skor bertahan.
   Tanpa saringan harga beku, desil 10 versi bulanan sempat jatuh ke -0,6%
   dengan perlakuan -100%: saham yang disuspensi terlihat "tenang dan dekat
   puncak" lalu delisting. Skor harian di app tidak kena (syarat
   bertransaksi >= 90% hari), tapi ini alasan saringan itu wajib.

PEMAKAIAN (dari <project>/)
    python -m website.riset_pola_naik.delisting
"""
import sys
import warnings

import numpy as np
import pandas as pd

from . import panel as PN
from .sumber_baru import muat_ksei

warnings.filterwarnings('ignore')

MIN_MCAP = 500e9          # Rp500 M kapitalisasi -- pengganti kasar saringan likuiditas


def panel_bulanan():
    bulan = muat_ksei()
    rows = []
    for kunci, isi in bulan.items():
        tgl = pd.Timestamp(isi['as_of'])
        for t, s in isi['securities'].items():
            if s['price'] > 0 and s['sec_num'] > 0:
                rows.append((t, kunci, tgl, s['price'], s['sec_num']))
    k = pd.DataFrame(rows, columns=['ticker', 'bulan', 'tanggal', 'harga', 'saham'])
    k = k.sort_values(['ticker', 'tanggal']).reset_index(drop=True)
    g = k.groupby('ticker')
    rasio = k['saham'] / g['saham'].shift(1)
    faktor = np.where((rasio >= 1.9) | (rasio <= 0.55), rasio, 1.0)     # pemecahan saham
    k['ret'] = k['harga'] * faktor / g['harga'].shift(1) - 1
    k['jarak'] = g['tanggal'].diff().dt.days
    k.loc[~k['jarak'].between(20, 45), 'ret'] = np.nan
    k['mcap'] = k['harga'] * k['saham']
    semua_bulan = sorted(k['bulan'].unique())
    terakhir = semua_bulan[-1]
    akhir = g['bulan'].transform('max')
    k['hilang_sesudah'] = akhir != terakhir          # baris milik emiten yang kemudian delisting
    k['bulan_terakhir'] = akhir
    return k, semua_bulan


def bagian_lubang(k, semua_bulan):
    _p, data = PN.sumber_harga()
    yahoo = set(data)
    print('\n' + '=' * 78)
    print('1. BESAR LUBANG: emiten yang hilang dari arsip KSEI, per tahun')
    print('=' * 78)
    akhir = k.groupby('ticker').agg(bulan_terakhir=('bulan', 'max'), harga=('harga', 'last'))
    akhir = akhir[akhir['bulan_terakhir'] != semua_bulan[-1]]
    # return 12 bulan terakhir sebelum hilang (dari harga arsip yang ada)
    r12 = {}
    for t in akhir.index:
        s = k[k['ticker'] == t].set_index('tanggal')['harga']
        if len(s) >= 2:
            awal = s[s.index >= s.index[-1] - pd.Timedelta(days=370)]
            r12[t] = s.iloc[-1] / awal.iloc[0] - 1 if len(awal) >= 2 else np.nan
    akhir['r12'] = pd.Series(r12)
    akhir['tahun'] = akhir['bulan_terakhir'].str[:4].astype(int)
    akhir['di_yahoo'] = akhir.index.isin(yahoo)
    per = akhir.groupby('tahun').agg(hilang=('harga', 'size'), di_yahoo=('di_yahoo', 'sum'),
                                     r12_median=('r12', 'median'),
                                     harga_gocap=('harga', lambda x: (x <= 50).mean() * 100))
    per['r12_median'] = (per['r12_median'] * 100).round(1)
    per['harga_gocap'] = per['harga_gocap'].round(0)
    print(per.to_string())
    print('  total hilang: %d emiten, %d di antaranya ada di cache Yahoo' % (len(akhir), int(akhir['di_yahoo'].sum())))
    print('  r12_median = return 12 bulan terakhir sebelum hilang; harga_gocap = %% yang harga terakhirnya <= Rp50')


def bagian_bias(k):
    _p, data = PN.sumber_harga()
    yahoo = set(data)
    print('\n' + '=' * 78)
    print('2. BIAS "BELI SEMUA": return rata-rata bulanan semua saham vs yang ada di Yahoo')
    print('=' * 78)
    k = k.copy()
    k['di_yahoo'] = k['ticker'].isin(yahoo)
    k['tahun'] = k['bulan'].str[:4].astype(int)
    # Return bulan t diatribusikan ke bulan t; saham kapitalisasi >= MIN_MCAP bulan sebelumnya.
    g = k.groupby('ticker')
    k['mcap_lalu'] = g['mcap'].shift(1)
    x = k[k['ret'].notna() & (k['mcap_lalu'] >= MIN_MCAP)]
    x = x[x['ret'].abs() < 3]
    rows = []
    for th, gg in x.groupby('tahun'):
        semua = gg.groupby('bulan')['ret'].mean()
        yh = gg[gg['di_yahoo']].groupby('bulan')['ret'].mean()
        rows.append({'tahun': th, 'bulan': len(semua),
                     'semua %/bln': semua.mean() * 100, 'yahoo saja %/bln': yh.mean() * 100,
                     'bias %/thn': ((1 + yh.mean()) ** 12 - (1 + semua.mean()) ** 12) * 100,
                     'n saham/bln': gg.groupby('bulan').size().mean(),
                     '% tak di yahoo': (1 - gg['di_yahoo'].mean()) * 100})
    print(pd.DataFrame(rows).set_index('tahun').round(2).to_string())
    print('  Hanya return yang TERLIHAT: bulan sesudah emiten hilang tidak dihitung, jadi bias sebenarnya lebih besar.')


def bagian_skor(k):
    _p, data = PN.sumber_harga()
    yahoo = set(data)
    print('\n' + '=' * 78)
    print('3. SKOR KECONDONGAN VERSI BULANAN, dengan & tanpa emiten delisting')
    print('   (dekat puncak 12 bulan + volatilitas 12 bulan; hasil 3 bulan ke depan vs rata-rata semua)')
    print('=' * 78)
    k = k.copy().sort_values(['ticker', 'tanggal'])
    k['lr'] = np.log1p(k['ret'])
    g = k.groupby('ticker')
    k['n_ret12'] = g['lr'].transform(lambda s: s.rolling(12, min_periods=12).count())
    k['vol12'] = g['lr'].transform(lambda s: s.rolling(12, min_periods=10).std())
    idx_harga = g['harga'].transform(lambda s: s)       # harga mentah
    # jarak dari puncak 12 bulan memakai harga yang sudah disetel pemecahan saham
    k['faktor'] = np.exp(g['lr'].transform(lambda s: s.fillna(0).cumsum()))
    k['maks12'] = g['faktor'].transform(lambda s: s.rolling(12, min_periods=10).max())
    k['dd12'] = k['faktor'] / k['maks12'] - 1
    del idx_harga
    # hasil 3 bulan ke depan (butuh 3 pasangan arsip berurutan)
    k['maju3'] = g['lr'].transform(lambda s: s.shift(-1) + s.shift(-2) + s.shift(-3))
    # emiten yang hilang di tengah jendela: tidak punya maju3. Tandai.
    k['sisa_bulan'] = g['bulan'].transform(lambda s: np.arange(len(s))[::-1])
    k['mati3'] = k['hilang_sesudah'] & (k['sisa_bulan'] < 3)
    k['di_yahoo'] = k['ticker'].isin(yahoo)
    # Saham yang disuspensi harganya BEKU: volatilitasnya nol dan ia "dekat
    # puncak" -- persis profil desil 10 -- lalu delisting. Versi harian di
    # app tidak kena ini (syarat bertransaksi >= 90% hari); di sini
    # pengganti syarat itu: buang yang harganya tidak berubah 2 bulan
    # berturut-turut.
    k['beku'] = g['ret'].transform(lambda s: (s == 0).astype(float).rolling(2, min_periods=2).sum()) >= 2

    x = k[(k['mcap'] >= MIN_MCAP) & k['vol12'].notna() & k['dd12'].notna() & (k['harga'] > 50)
          & ~k['beku']].copy()
    x['r_puncak'] = x.groupby('bulan')['dd12'].rank(pct=True)
    x['r_tenang'] = x.groupby('bulan')['vol12'].rank(pct=True, ascending=False)
    x['skor'] = (x['r_puncak'] + x['r_tenang']) / 2
    x['desil'] = np.ceil(x.groupby('bulan')['skor'].rank(pct=True) * 10).clip(1, 10)

    def hasil(d, perlakuan):
        d = d.copy()
        if perlakuan == 'buang':
            d = d[d['maju3'].notna()]
            m = d['maju3']
        else:                                   # mati = -100% (batas terburuk)
            m = d['maju3'].where(~d['mati3'], np.log(1e-3))
            d = d[m.notna()]
            m = m[m.notna()]
        b = m.groupby(d['bulan']).transform('mean')
        exc = (m - b)
        return exc.groupby(d['desil']).mean().apply(lambda v: (np.exp(v) - 1) * 100), d.groupby('desil').size()

    for label, sub in (('HANYA emiten di cache Yahoo (seperti riset)', x[x['di_yahoo']]),
                       ('SEMUA emiten KSEI, yang hilang DIBUANG', x),
                       ('SEMUA emiten KSEI, yang hilang = -100%', x)):
        perl = 'mati' if '-100%' in label else 'buang'
        r, n = hasil(sub, perl)
        print('  %-44s desil 1 %+.1f%%  desil 10 %+.1f%%  (n desil 1 = %d; mati dlm 3 bln: desil 1 = %d, desil 10 = %d)'
              % (label, r.get(1, np.nan), r.get(10, np.nan), n.get(1, 0),
                 int(sub[(sub['desil'] == 1) & sub['mati3']].shape[0]),
                 int(sub[(sub['desil'] == 10) & sub['mati3']].shape[0])))
    print('  vs rata-rata semua emiten di kelompok yang sama, 3 bulan; bulan arsip: %s .. %s'
          % (x['bulan'].min(), x['bulan'].max()))


def main():
    k, semua_bulan = panel_bulanan()
    print('arsip KSEI: %d bulan (%s .. %s), %d emiten' % (len(semua_bulan), semua_bulan[0], semua_bulan[-1],
                                                       k['ticker'].nunique()))
    bagian_lubang(k, semua_bulan)
    bagian_bias(k)
    bagian_skor(k)


if __name__ == '__main__':
    sys.exit(main())
