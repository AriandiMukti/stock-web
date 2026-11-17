"""
Analog chart: "kalau bentuk chart-nya seperti ini, sesudahnya biasanya apa?"
-- dijawab dari data Yahoo bertahun-tahun, bukan dari buku analisis teknikal.
(23 Sep 2026)

PERTANYAANNYA
Bisakah pola chart dibaca tanpa teori: cari di data kapan saja bentuk chart
yang MIRIP pernah muncul, lalu lihat apa yang terjadi sesudahnya?

DUA CARA, SATU HIPOTESIS
  1. ANALOG (tetangga terdekat). Untuk tiap emiten-hari, cari 100 jendela
     harga paling mirip di PUSTAKA; ramalannya = rata-rata hasil 100 tetangga
     itu.
  2. KLASTER. Kelompokkan semua bentuk di pustaka jadi 24 "pola" (k-means),
     catat hasil tiap pola, lalu lihat apakah urutan pola terbaik-terburuk
     bertahan di data lain. Ini bentuk "jika pola A maka C" yang paling
     harfiah.
Dua-duanya menguji SATU pertanyaan -- apakah bentuk chart memuat informasi
arah -- bukan ribuan aturan "jika A maka C" yang diuji sendiri-sendiri. Yang
terakhir itu jalan Penemu Pola: 450 pola lolos koreksi FDR, di luar sampel
setara lempar koin (lihat pattern_miner.py).

EMPAT BENTUK YANG DICOBA (semua dilaporkan)
  z30   bentuk harga 30 hari, dinormalkan (skala & volatilitas dibuang)
  r30   lintasan harga 30 hari relatif ke hari ini (besar gerak ikut)
  z60   bentuk harga 60 hari (30 titik, tiap 2 bar)
  z30v  bentuk harga + bentuk volume 30 hari

PROTOKOL (sama dengan uji.py)
  Pustaka          = separuh emiten A (md5) x 2013-2019
  Validasi penuh   = separuh emiten B x 2020-2026 (periode DAN emiten beda)
  Silang emiten    = separuh B x 2013-2019 (periode sama, emiten beda)
  Silang periode   = separuh A x 2020-2026 (emiten sama, periode beda)
  Emiten likuid saja (kolom elig), jendela diambil tiap 5 bar per emiten.
  Hasil = return majemuk 20 hari dari close t+1 dikurangi emiten layak lain
  PADA HARI YANG SAMA, plus "+10% dulu sebelum -10%" dalam 60 bar.
  Ukuran utama: IC = korelasi peringkat ramalan vs hasil antar-emiten per
  tanggal, t dari rata-rata bulanan. Pembanding: fitur polos (momentum,
  jarak dari puncak 52 minggu, volatilitas) -- kalau analog tidak lebih baik
  dari satu angka momentum, "pola"-nya cuma momentum yang menyamar.

HASIL (23 Sep 2026; sampel 94.650 emiten-hari, uji penuh n=31.486 di 743 tanggal)
=================================================================================
1. ANALOG GAGAL DI UJI PENUH. IC arah +0,009 s.d. +0,017 (t 0,3-1,1) di keempat
   bentuk; kuintil terbaik minus terburuk +0,1 s.d. +0,6% per 20 hari (t <= 1,5).
   Setelah dikurangi ret20/ret120/jarak puncak/volatilitas, IC sisanya ~0.
   Di sel SILANG (periode sama, emiten beda) sempat t 2,6-5,1: pola yang
   "benar" di eranya sendiri tidak terbawa ke era lain -- jebakan yang sama
   dengan Penemu Pola. IC "+10% dulu" memang positif (t 2,7-5,1), tapi
   sebagian besar dari besar gerak: dicek terpisah (r30, uji penuh), peluang
   MENYENTUH +/-10% dalam 60 hari IC +0,267 (t 21,8), sedangkan ASIMETRI
   naik-dulu minus turun-dulu cuma +0,030 (t 2,6) dan hilang setelah
   dinetralkan dari momentum/puncak/volatilitas (+0,010, t 0,7).
2. BESAR GERAK TERTEBAK (r30: IC 0,275), tapi volatilitas 20 hari polos lebih
   baik (0,316). Tidak perlu pola untuk itu.
3. KLASTER: urutan pola BERTAHAN -- rho +0,70 (19/24 tanda sama); dengan
   12/24/48 pola dan arah pustaka dibalik, rho selalu positif (+0,34 s.d.
   +0,78). TAPI kecil: 3 pola terbaik +0,7 s.d. +1,2% per 20 hari terhadap
   pasar di uji penuh (rata-rata ~+0,9%, setara ongkos pulang-pergi 0,9%),
   3 terburuk -0,4 s.d. -1,2%. Isinya sebagian besar POSISI HARGA DALAM
   RENTANG 30 HARI (rho +0,67 antar-pola): tutup di bagian atas rentang
   cenderung lanjut, di bagian bawah cenderung lanjut turun. Sisa setelah
   dinetralkan dari posisi/momentum/puncak/volatilitas: IC +0,016 (t 2,3).
   Klaster lebih stabil daripada 100 tetangga karena rata-ratanya dari
   ratusan jendela, bukan seratus -- tetangga terdekat didominasi noise.
4. Fitur polos yang mengalahkan semua analog: jarak dari puncak 52 minggu
   (IC +0,090, t 3,6) dan volatilitas 20 hari (IC -0,105, t -5,3: yang liar
   kalah setelah dimajemukkan) -- sejalan dengan tembus_basis.py.

KESIMPULAN: bentuk chart hampir tidak memuat informasi arah di luar yang
sudah ditangkap "dekat puncak / tembus basis" dan "volatilitas rendah". Tidak
ada "jika pola A maka C": pola terbaik menggeser rata-rata ~1% per 20 hari,
sementara sebaran hasil per emiten jauh lebih lebar dari itu. Ini cara ketiga
yang sampai ke kesimpulan yang sama (Penemu Pola, ~40 pola di uji.py).

PEMAKAIAN (dari <project>/)
    python -m website.riset_pola_naik.analog
"""
import sys
import time

import numpy as np
import pandas as pd
from numpy.lib.stride_tricks import sliding_window_view as swv

from . import panel as PN
from . import uji as U

W = 30            # panjang jendela bentuk (hari bursa)
W_PANJANG = 60    # varian z60: 60 hari diambil tiap 2 bar -> 30 titik
LANGKAH = 5       # jendela diambil tiap 5 bar per emiten
K = 100           # jumlah tetangga
N_KLASTER = 24

VARIAN = {
    'z30': 'bentuk harga 30h (dinormalkan)',
    'r30': 'lintasan harga 30h relatif hari ini',
    'z60': 'bentuk harga 60h (30 titik)',
    'z30v': 'bentuk harga + volume 30h',
}
SEL = {
    'validasi': (1, 2, 'emiten B x 2020-2026'),
    'silang_emiten': (1, 1, 'emiten B x 2013-2019'),
    'silang_periode': (0, 2, 'emiten A x 2020-2026'),
}
FITUR_POLOS = {
    'pos30': 'posisi dalam rentang 30 hari',
    'ret5': 'return 5 hari',
    'ret20': 'return 20 hari',
    'ret120': 'return 120 hari',
    'dd250': 'jarak dari puncak 52 mgg',
    'vol20': 'volatilitas 20 hari',
}


# ---------------------------------------------------------------------------
# DATA
# ---------------------------------------------------------------------------
def _z(x):
    m = x.mean(1, keepdims=True)
    s = x.std(1, keepdims=True)
    with np.errstate(invalid='ignore', divide='ignore'):
        out = (x - m) / s
    out[~np.isfinite(out).all(1)] = np.nan
    return out


def _jendela(s):
    """Vektor bentuk untuk tiap baris sampel. Posisi bar diambil dari kolom
    `hist` panel -- indeks baris di data harga yang sudah dibersihkan dengan
    cara yang SAMA seperti panel.fitur() (Close > 0, urut, tanpa duplikat)."""
    _path, data = PN.sumber_harga()
    X = {k: np.full((len(s), 2 * W if k == 'z30v' else W), np.nan, dtype='float32') for k in VARIAN}
    beda_tanggal = 0
    hist = s['hist'].to_numpy().astype(int)
    tgl = s['date'].to_numpy()
    for t, idx in s.groupby('ticker', sort=False).indices.items():
        df = data.get(t)
        if df is None:
            continue
        df = df[['Close', 'Volume']].copy()
        df = df[df['Close'] > 0].sort_index()
        df = df[~df.index.duplicated(keep='last')]
        h = hist[idx]
        beda_tanggal += int((df.index.to_numpy()[h] != tgl[idx]).sum())
        lc = np.log(df['Close'].to_numpy(float))
        lv = np.log1p(df['Volume'].fillna(0).to_numpy(float))
        w30 = swv(lc, W)[h - W + 1]
        w60 = swv(lc, W_PANJANG)[h - W_PANJANG + 1][:, 1::2]
        v30 = swv(lv, W)[h - W + 1]
        X['z30'][idx] = _z(w30)
        X['r30'][idx] = w30 - w30[:, -1:]
        X['z60'][idx] = _z(w60)
        X['z30v'][idx] = np.hstack([_z(w30), _z(v30)])
    if beda_tanggal:
        raise RuntimeError('%d jendela tidak jatuh di tanggal panelnya -- posisi `hist` '
                           'tidak cocok dengan data harga.' % beda_tanggal)
    return X


def siapkan():
    p = U.muat()
    p = p.sort_values(['ticker', 'date']).reset_index(drop=True)
    s = p[p['elig'] & (p['hist'] % LANGKAH == 0) & p['fwd20'].notna()
          & (p['hist'] >= W_PANJANG)].copy()
    s['lr20'] = np.log1p(s['fwd20'].astype(float))
    s['exc20'] = s['lr20'] - s['b_lr20']
    s['abs20'] = s['lr20'].abs()
    s['fpup'] = (s['fp60'] == 1).astype(float).where(s['fp60'].notna())
    s['fp_edge'] = s['fpup'] - s['b_fpup']
    s['year'] = s['date'].dt.year
    kol = ['ticker', 'date', 'hist', 'half', 'period', 'month', 'year', 'lr20', 'exc20', 'abs20',
           'fpup', 'b_fpup', 'fp_edge'] + list(FITUR_POLOS)
    s = s[kol].reset_index(drop=True)
    t0 = time.time()
    X = _jendela(s)
    print('sampel: %d emiten-hari (tiap %d bar) | jendela %.0f detik'
          % (len(s), LANGKAH, time.time() - t0), flush=True)
    return s, X


# ---------------------------------------------------------------------------
# UKURAN
# ---------------------------------------------------------------------------
def ic(df, kol, hasil='exc20', min_n=15):
    """(IC rata-rata, t dari rata-rata bulanan, jumlah tanggal)."""
    d = df[['date', kol, hasil]].dropna()
    d = d[d.groupby('date')[kol].transform('size') >= min_n]
    if d.empty:
        return np.nan, np.nan, 0
    r1 = d.groupby('date')[kol].rank()
    r2 = d.groupby('date')[hasil].rank()
    per = pd.DataFrame({'date': d['date'], 'a': r1, 'b': r2}).groupby('date').apply(
        lambda g: np.corrcoef(g['a'], g['b'])[0, 1] if g['a'].std() > 0 and g['b'].std() > 0 else np.nan)
    per = per.dropna()
    bulanan = per.groupby(per.index.to_period('M')).mean()
    t = bulanan.mean() / (bulanan.std(ddof=1) / np.sqrt(len(bulanan))) if len(bulanan) > 2 else np.nan
    return per.mean(), t, len(per)


def kuintil(df, kol):
    """Kuintil ramalan per tanggal -> hasil majemuk vs pasar & peluang +10% dulu."""
    d = df.dropna(subset=[kol, 'exc20']).copy()
    d['q'] = np.ceil(d.groupby('date')[kol].rank(pct=True) * 5).clip(1, 5).astype(int)
    rows = []
    for q, g in d.groupby('q'):
        f = g.dropna(subset=['fp_edge'])
        rows.append({'kuintil': q, 'n': len(g),
                     'vs_pasar20': (np.exp(g['exc20'].mean()) - 1) * 100,
                     'naik10_dulu': f['fpup'].mean() * 100,
                     'pembanding': f['b_fpup'].mean() * 100})
    tab = pd.DataFrame(rows).set_index('kuintil')
    # Q5 - Q1 per bulan (t) dan per tahun (berapa tahun positif)
    q15 = d[d['q'].isin([1, 5])]
    per_bulan = q15.groupby(['month', 'q'])['exc20'].mean().unstack()
    sp = (per_bulan[5] - per_bulan[1]).dropna()
    t = sp.mean() / (sp.std(ddof=1) / np.sqrt(len(sp))) if len(sp) > 2 else np.nan
    per_tahun = q15.groupby(['year', 'q'])['exc20'].mean().unstack()
    spt = (per_tahun[5] - per_tahun[1]).dropna()
    return tab, (np.exp(sp.mean()) - 1) * 100, t, '%d/%d' % ((spt > 0).sum(), len(spt))


def netralkan(df, kol, terhadap=('ret20', 'ret120', 'dd250', 'vol20')):
    """Sisa ramalan setelah dikurangi yang sudah dijelaskan fitur polos
    (regresi peringkat per tanggal). IC sisa ~0 = analog tidak menambah apa-apa."""
    d = df.dropna(subset=[kol] + list(terhadap)).copy()
    kolom = [kol] + list(terhadap)
    R = d.groupby('date')[kolom].rank(pct=True)
    R['date'] = d['date']

    def _sisa(g):
        A = np.column_stack([np.ones(len(g))] + [g[c].to_numpy() for c in terhadap])
        y = g[kol].to_numpy()
        if len(g) < len(terhadap) + 5:
            return pd.Series(np.nan, index=g.index)
        b = np.linalg.lstsq(A, y, rcond=None)[0]
        return pd.Series(y - A @ b, index=g.index)

    d[kol + '_sisa'] = R.groupby('date', group_keys=False).apply(_sisa)
    return d


# ---------------------------------------------------------------------------
# ANALOG
# ---------------------------------------------------------------------------
def tetangga(Xp, Xq):
    from sklearn.neighbors import NearestNeighbors
    nn = NearestNeighbors(n_neighbors=K, algorithm='brute', n_jobs=-1).fit(Xp)
    return nn.kneighbors(Xq, return_distance=False)


def ramal(pustaka, ind):
    """Rata-rata hasil tetangga: return vs pasar, peluang +10% dulu (selisih
    dengan pembanding tetangga), dan besar gerak."""
    exc = pustaka['exc20'].to_numpy()[ind]
    fp = pustaka['fp_edge'].to_numpy()[ind]
    ab = pustaka['abs20'].to_numpy()[ind]
    return np.nanmean(exc, 1), np.nanmean(fp, 1), np.nanmean(ab, 1)


def _mask(s, half, period):
    return ((s['half'] == half) & (s['period'] == period)).to_numpy()


def bagian_analog(s, X):
    print('\n' + '=' * 78)
    print('1. ANALOG: 100 chart paling mirip di pustaka (emiten A x 2013-2019)')
    print('=' * 78)
    mp = _mask(s, 0, 1)
    rows, simpan = [], {}
    for v in VARIAN:
        Xv = X[v]
        okp = mp & np.isfinite(Xv).all(1)
        pustaka = s[okp].reset_index(drop=True)
        for sel, (half, period, _lbl) in SEL.items():
            mq = _mask(s, half, period) & np.isfinite(Xv).all(1)
            q = s[mq].reset_index(drop=True)
            t0 = time.time()
            ind = tetangga(Xv[okp], Xv[mq])
            q['pred'], q['pred_fp'], q['pred_abs'] = ramal(pustaka, ind)
            a, ta, nd = ic(q, 'pred')
            b, tb, _ = ic(q, 'pred_fp', hasil='fp_edge')
            c, tc, _ = ic(q, 'pred_abs', hasil='abs20')
            rows.append({'bentuk': v, 'sel': sel, 'n': len(q), 'tanggal': nd,
                         'IC arah': a, 't': ta, 'IC +10% dulu': b, 't ': tb,
                         'IC besar gerak': c, 't  ': tc, 'detik': round(time.time() - t0)})
            simpan[(v, sel)] = q
            print('  %-5s %-15s n=%6d  IC arah %+.3f (t %+.1f)  IC besar gerak %+.3f   %.0f dtk'
                  % (v, sel, len(q), a, ta, c, time.time() - t0), flush=True)
    return pd.DataFrame(rows), simpan


def bagian_pembanding(simpan):
    print('\n' + '=' * 78)
    print('2. PEMBANDING: fitur polos di sel validasi yang sama (emiten B x 2020-2026)')
    print('=' * 78)
    q = simpan[('z30', 'validasi')]
    rows = []
    for f, lbl in FITUR_POLOS.items():
        a, ta, _ = ic(q, f)
        c, tc, _ = ic(q, f, hasil='abs20')
        rows.append({'fitur': lbl, 'IC arah': round(a, 3), 't': round(ta, 1),
                     'IC besar gerak': round(c, 3), 't ': round(tc, 1)})
    print(pd.DataFrame(rows).to_string(index=False))

    print('\n   Analog setelah dinetralkan dari ret20/ret120/jarak puncak/volatilitas:')
    for v in VARIAN:
        d = netralkan(simpan[(v, 'validasi')], 'pred')
        a, ta, _ = ic(d, 'pred_sisa')
        print('   %-5s IC sisa %+.3f (t %+.1f)' % (v, a, ta))


def bagian_kuintil(simpan):
    print('\n' + '=' * 78)
    print('3. KUINTIL RAMALAN ANALOG di validasi penuh (emiten B x 2020-2026)')
    print('   Q5 = 20%% emiten yang tetangganya paling bagus, Q1 = paling jelek')
    print('=' * 78)
    for v in VARIAN:
        tab, sp, t, thn = kuintil(simpan[(v, 'validasi')], 'pred')
        print('\n  [%s] %s -- Q5-Q1: %+.2f%% per 20 hari (t %+.1f), positif %s tahun'
              % (v, VARIAN[v], sp, t, thn))
        print(tab.round(1).to_string())


# ---------------------------------------------------------------------------
# KLASTER: "jika pola A maka C"
# ---------------------------------------------------------------------------
def _ciri(c):
    """Nama kasar sebuah bentuk dari kemiringan tiap sepertiganya."""
    n = len(c)
    kata = []
    for a, b in ((0, n // 3), (n // 3, 2 * n // 3), (2 * n // 3, n - 1)):
        d = c[b] - c[a]
        kata.append('naik' if d > 0.35 else ('turun' if d < -0.35 else 'datar'))
    return ' > '.join(kata)


def bagian_klaster(s, X):
    from sklearn.cluster import KMeans
    print('\n' + '=' * 78)
    print('4. KLASTER: %d "pola" bentuk harga 30 hari (z30) dari pustaka' % N_KLASTER)
    print('=' * 78)
    Xv = X['z30']
    ok = np.isfinite(Xv).all(1)
    mp = _mask(s, 0, 1) & ok
    km = KMeans(n_clusters=N_KLASTER, n_init=4, random_state=0).fit(Xv[mp])
    pustaka = s[mp].copy()
    pustaka['k'] = km.labels_

    def ringkas(df):
        g = df.groupby('k')
        return pd.DataFrame({'n': g.size(),
                             'vs_pasar20': (np.exp(g['exc20'].mean()) - 1) * 100,
                             'naik10_dulu_lift': g['fp_edge'].mean() * 100})

    tabel = {'pustaka': ringkas(pustaka)}
    for sel, (half, period, _lbl) in SEL.items():
        m = _mask(s, half, period) & ok
        d = s[m].copy()
        d['k'] = km.predict(Xv[m])
        tabel[sel] = ringkas(d)

    gab = pd.concat({k: v['vs_pasar20'] for k, v in tabel.items()}, axis=1)
    gab.insert(0, 'n_pustaka', tabel['pustaka']['n'])
    gab.insert(0, 'bentuk', [_ciri(km.cluster_centers_[k]) for k in gab.index])
    gab['lift_pustaka'] = tabel['pustaka']['naik10_dulu_lift']
    gab['lift_validasi'] = tabel['validasi']['naik10_dulu_lift']
    gab = gab.sort_values('pustaka', ascending=False)
    print('  vs pasar 20 hari (%, majemuk) per pola; diurut dari yang terbaik di pustaka')
    print(gab.round(2).to_string())

    print('\n  Apakah urutan pola bertahan? (korelasi peringkat antar-%d pola)' % N_KLASTER)
    for sel in SEL:
        r = gab['pustaka'].corr(gab[sel], method='spearman')
        sama = int((np.sign(gab['pustaka']) == np.sign(gab[sel])).sum())
        print('  pustaka -> %-15s rho %+.2f | tanda sama %d/%d' % (sel, r, sama, len(gab)))
    r = gab['lift_pustaka'].corr(gab['lift_validasi'], method='spearman')
    print('  peluang +10%% dulu, pustaka -> validasi: rho %+.2f' % r)
    atas, bawah = gab.index[:3], gab.index[-3:]
    print('\n  3 pola TERBAIK di pustaka -> validasi: %s'
          % ', '.join('%+.2f' % x for x in gab.loc[atas, 'validasi']))
    print('  3 pola TERBURUK di pustaka -> validasi: %s'
          % ', '.join('%+.2f' % x for x in gab.loc[bawah, 'validasi']))
    bagian_klaster_uji(s, X, km, pustaka)
    return gab


def bagian_klaster_uji(s, X, km, pustaka):
    """Dua pertanyaan lanjutan untuk klaster:
    (a) urutannya bertahan juga kalau jumlah pola / arah pustaka diganti?
    (b) kalau iya, apakah itu cuma posisi harga dalam rentang 30 hari --
        yang sudah tercakup temuan tembus basis?"""
    from sklearn.cluster import KMeans
    Xv = X['z30']
    ok = np.isfinite(Xv).all(1)

    print('\n  (a) Ketahanan: rho urutan pola pustaka -> uji penuh (periode & emiten beda)')
    for n_k in (12, 24, 48):
        for (hp, pp), (hq, pq), lbl in (((0, 1), (1, 2), 'pustaka A 2013-19 -> uji B 2020-26'),
                                        ((1, 1), (0, 2), 'pustaka B 2013-19 -> uji A 2020-26')):
            mp = _mask(s, hp, pp) & ok
            mq = _mask(s, hq, pq) & ok
            k2 = KMeans(n_clusters=n_k, n_init=4, random_state=0).fit(Xv[mp])
            a = s[mp].assign(k=k2.labels_).groupby('k')['exc20'].mean()
            b = s[mq].assign(k=k2.predict(Xv[mq])).groupby('k')['exc20'].mean()
            j = pd.concat([a, b], axis=1, keys=['p', 'u']).dropna()
            print('      %2d pola | %s: rho %+.2f, tanda sama %d/%d'
                  % (n_k, lbl, j['p'].corr(j['u'], method='spearman'),
                     int((np.sign(j['p']) == np.sign(j['u'])).sum()), len(j)))

    print('\n  (b) Apakah pola = posisi dalam rentang 30 hari? (uji penuh, emiten B x 2020-2026)')
    m = _mask(s, 1, 2) & ok
    d = s[m].copy()
    d['k'] = km.predict(Xv[m])
    d['pred_k'] = d['k'].map(pustaka.groupby('k')['exc20'].mean())
    a, ta, _ = ic(d, 'pred_k')
    b, tb, _ = ic(d, 'pos30')
    print('      IC ramalan pola (rata-rata pustaka klasternya): %+.3f (t %+.1f)' % (a, ta))
    print('      IC posisi dalam rentang 30 hari saja:           %+.3f (t %+.1f)' % (b, tb))
    n = netralkan(d, 'pred_k', terhadap=('pos30', 'ret20', 'ret120', 'dd250', 'vol20'))
    c, tc, _ = ic(n, 'pred_k_sisa')
    print('      IC pola setelah dinetralkan (pos30, ret20, ret120, puncak, vol): %+.3f (t %+.1f)' % (c, tc))
    kel = pd.DataFrame({'pos30_pustaka': pustaka.groupby('k')['pos30'].mean(),
                        'uji': d.groupby('k')['exc20'].mean()})
    print('      antar-%d pola: rho(posisi rata-rata pola, hasil uji) %+.2f'
          % (len(kel), kel['pos30_pustaka'].corr(kel['uji'], method='spearman')))


def main():
    t0 = time.time()
    s, X = siapkan()
    tab, simpan = bagian_analog(s, X)
    print('\n' + tab.round(3).to_string(index=False))
    bagian_pembanding(simpan)
    bagian_kuintil(simpan)
    bagian_klaster(s, X)
    print('\nselesai %.0f detik' % (time.time() - t0))


if __name__ == '__main__':
    sys.exit(main())
