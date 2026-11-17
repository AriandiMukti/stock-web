"""
Menu PER SAHAM -- tiap menu diperdagangkan sendiri-sendiri di tiap emiten,
hasilnya dilabel NAIK (untung) / TURUN (rugi), lalu emiten NAIK
dikelompokkan menurut kemiripan cirinya. (29 Okt 2026)

KENAPA
Semua bukti menu selama ini GABUNGAN semua emiten. Pertanyaannya: apakah
emiten yang cocok dengan sebuah menu punya ciri bersama -- dan kalau iya,
apakah ciri itu bisa dikenali SEBELUM transaksi, di emiten dan periode lain?

DESAIN (didaftar SEBELUM hasil dilihat)
Menu yang bisa diuji mundur 2013-2026 dari harga (menu lain datanya baru 2026):
    TB    Tembus Basis gabungan (basis <20% + vol >2x ATAU puncak 52mg + vol >2x),
          keluar trailing 10% maks 120 hari (TS10, aturan halaman)
    KD10  Skor Kecondongan desil 10, tahan 60 hari
    KD1   Skor Kecondongan desil 1 (menu bilang HINDARI), tahan 60 hari
    JD    Jatuh Dalam (dd60 <= -40% & rentang 20h >= 25%; status gagal), tahan 60 hari
Per emiten: transaksi BERURUTAN (tidak tumpang tindih, sinyal saat pegang
dilewati), masuk close hari setelah sinyal, ongkos pulang-pergi 0,9%,
jalur dengan loncatan >45% dibuang. Periode menurut tanggal masuk:
2013-19 dan 2020-26.
Label per emiten-periode (minimal 3 transaksi):
    NAIK  = jumlah log-return bersih transaksinya > 0 (untung kalau cuma main
            emiten itu); TURUN = sebaliknya
    juga  "lebih" = jumlah selisih vs pasar (indeks rata-rata-sama emiten layak,
            jendela yang sama persis) > 0
Ciri emiten (dihitung dari data harian periode itu, BUKAN dari hasil menu):
likuiditas, harga, volatilitas, beta & R2 terhadap pasar, volatilitas sisa,
skew, porsi hari harga diam, autokorelasi harian, rasio varians 10 hari,
umur pencatatan, frekuensi sinyal, sektor, kepemilikan KSEI. Return
beli-tahan periode itu ikut dicatat tapi TIDAK dipakai sebagai ciri (itu
hasil, bukan ciri -- emiten yang naik jelas membuat menu beli untung).
Sel sama dengan uji.py: CARI = emiten separuh A 2013-19; UJI = separuh B
2020-26 (emiten DAN periode terpisah), dua sel silang sebagai pemeriksaan.

HASIL (29 Okt 2026; indeks pasar = pasar_lengkap, lihat fungsinya)
1. NAIK/TURUN per emiten TIDAK berulang. Tembus Basis+TS10: 50% emiten
   NAIK di 2013-19, 55% di 2020-26; NAIK dulu -> NAIK lagi 61% vs TURUN
   dulu -> NAIK 59%, rho 0,09. Desil 10: rho -0,10. Sama dengan
   donchian_saham.py: label per emiten = lempar koin. NAIK-nya menu beli
   sebagian besar karena emitennya memang naik (beli-tahan naik di 64-81%
   emiten NAIK vs 41-57% emiten TURUN); menu > beli-tahan cuma 31-48%.
2. KLASTER emiten NAIK (k-means, ciri z-skor per periode): di tiap menu
   muncul dua tipe yang sama -- "liar" (kecil, volatil, skew +, R2 rendah,
   vr10 tinggi) dan "ikut pasar" (besar, likuid, R2/beta tinggi, tenang).
   - TB: tipe yang menang BERGANTI -- 2013-19 liar 59% NAIK vs ikut pasar
     44%; 2020-26 liar 49-51% vs ikut pasar 58-60%. Tidak ada profil
     emiten yang stabil untuk Tembus Basis.
   - KD1 & JD (menu "hindari"/beli jatuh): tipe ikut pasar NAIK lebih
     sering di DUA periode (KD1 39-44% vs 8-29%). Ini yang diuji lanjut.
3. CIRI SEBELUM SINYAL (exante, kuintil per sel, vs pasar per transaksi):
   - TB: tidak ada ciri yang konsisten di 4 sel. Likuiditas rendah sedikit
     lebih baik (Q5-Q1 -2,8 s.d. -4,7, t -1,4 s.d. -2,1); vr10 positif di
     3 sel tapi ~0 di silang A 2020-26; R2 Q5-Q1 -0,4 s.d. -3,6 (n.s.) --
     R2 BUKAN saringan Tembus Basis.
   - KD1 & JD: R2 terhadap pasar memisahkan dengan tajam di keempat sel
     -> jatuh_sendiri.py.

PEMAKAIAN (dari <project>/)
    python -m website.riset_pola_naik.menu_per_saham bangun     # transaksi + ciri -> cache
    python -m website.riset_pola_naik.menu_per_saham ringkas    # naik/turun per menu, persistensi
    python -m website.riset_pola_naik.menu_per_saham ciri       # ciri NAIK vs TURUN per sel (AUC)
    python -m website.riset_pola_naik.menu_per_saham klaster    # kelompok emiten NAIK + uji di periode lain
    python -m website.riset_pola_naik.menu_per_saham exante     # ciri 250h SEBELUM sinyal, kuintil per sel
"""
import os
import pickle
import sys
import time
import warnings

import numpy as np
import pandas as pd

from . import keluar as KL
from . import uji
from .panel import RESEARCH_CACHE

warnings.filterwarnings('ignore')

CACHE = os.path.join(RESEARCH_CACHE, 'menu_per_saham.pkl')
KSEI_CACHE = os.path.join(RESEARCH_CACHE, 'ksei_porsi_bulanan.pkl')
BIAYA_LOG = np.log(1 - 0.005) - np.log(1 + 0.004)   # 0,15%+0,25% slip beli, 0,25%+0,25% slip jual
MIN_TX = 3
PERIODE = {'2013-19': ('2013-01-01', '2019-12-31'), '2020-26': ('2020-01-01', '2026-12-31')}
SEL = {'CARI (A 2013-19)': (0, '2013-19'), 'UJI (B 2020-26)': (1, '2020-26'),
       'silang (B 2013-19)': (1, '2013-19'), 'silang (A 2020-26)': (0, '2020-26')}
MENU = {'TB': 'TS10', 'KD10': 'H60', 'KD1': 'H60', 'JD': 'H60'}
CIRI = ['log_nilai', 'log_harga', 'vol', 'beta', 'r2', 'idio', 'skew', 'diam', 'ac1', 'vr10',
        'umur', 'frek', 'asing', 'individu', 'reksa_dana']


def pasar_lengkap(p):
    """Indeks rata-rata-sama (log, kumulatif) emiten likuid KEMARIN, tanpa syarat traded30.

    KL.siapkan memakai `elig`, dan di 2017-2019 `elig` kosong untuk SEMUA emiten
    di sekitar libur panjang (Lebaran, Natal-Tahun Baru): Yahoo memuat baris libur
    dengan volume 0, jadi traded30 < 0,9 di semua emiten sekaligus. Indeksnya
    bolong ~30% hari di 2018-2019, dan beta/R2 250 hari ikut kosong.
    """
    q = p[['ticker', 'date', 'close', 'medval20', 'hist', 'bad_back60', 'ret1']].sort_values(['ticker', 'date'])
    q['lr'] = np.log(q['close']).groupby(q['ticker']).diff()
    ok = (q['medval20'] >= uji.MIN_NILAI) & (q['close'] >= uji.MIN_HARGA) & (q['hist'] >= 260) & (q['bad_back60'] == 0)
    q['ok_kmrn'] = ok.groupby(q['ticker']).shift(1).fillna(False).astype(bool)
    q = q[q['ok_kmrn'] & (q['ret1'].abs() <= 0.45) & (q['date'] >= '2012-06-01')]
    return q.groupby('date')['lr'].mean().sort_index().cumsum()


def sinyal(p):
    e = p['elig']
    basis = (p['brk30'] == 1) & (p['prevrange30'] < 0.20) & (p['vspike'] > 2)
    puncak = (p['hi250'] == 1) & (p['vspike'] > 2)
    g = p.loc[e].groupby('date')
    r_puncak = g['dd250'].rank(pct=True)
    r_tenang = g['vol20'].rank(pct=True, ascending=False)
    skor = ((r_puncak + r_tenang) / 2).rename('skor')
    desil = np.ceil(skor.groupby(p.loc[e, 'date']).rank(pct=True) * 10).clip(1, 10)
    p['desil'] = np.nan
    p.loc[e, 'desil'] = desil
    return {'TB': e & (basis | puncak),
            'KD10': e & (p['desil'] == 10),
            'KD1': e & (p['desil'] == 1),
            'JD': e & (p['dd60'] <= -0.40) & (p['range20'] >= 0.25)}


def urut(a, sig_hist, aturan):
    """Transaksi berurutan satu emiten: (i_masuk, j_keluar)."""
    out, bebas = [], -1
    n = len(a['close'])
    for h in sig_hist:
        i = int(h) - a['h0'] + 1
        if i <= bebas:
            continue
        if i >= n:
            break
        j = KL.keluar_di(a, i, aturan)
        if j is None:
            continue
        out.append((i, j))
        bebas = j
    return out


def kepemilikan():
    """Porsi kepemilikan bulanan per emiten dari arsip KSEI (cache sendiri)."""
    if os.path.exists(KSEI_CACHE):
        return pd.read_pickle(KSEI_CACHE)
    from .sumber_baru import muat_ksei
    rows = []
    for _k, isi in muat_ksei().items():
        tgl = pd.Timestamp(isi['as_of'])
        for t, s in isi['securities'].items():
            lok, asg = s['local'], s['foreign']
            total = s['local_total'] + s['foreign_total']
            if total <= 0:
                continue
            rows.append({'ticker': t, 'as_of': tgl,
                         'asing': s['foreign_total'] / total * 100,
                         'individu': (lok['ID'] + asg['ID']) / total * 100,
                         'reksa_dana': (lok['MF'] + asg['MF']) / total * 100})
    k = pd.DataFrame(rows)
    k.to_pickle(KSEI_CACHE)
    return k


def ciri_periode(d, mkt, a, b):
    """Ciri satu emiten di satu periode dari data harian (bukan dari hasil menu)."""
    s = d[(d['date'] >= a) & (d['date'] <= b)]
    if len(s) < 120:
        return None
    lr = np.log(s['close']).diff()
    lr[s['ret1'].abs() > 0.45] = np.nan
    lr.index = s['date'].to_numpy()
    m = mkt.reindex(lr.index)
    ok = lr.notna() & m.notna()
    x, y = m[ok].to_numpy(), lr[ok].to_numpy()
    if len(y) < 100:
        return None
    beta = np.cov(x, y)[0, 1] / np.var(x, ddof=1)
    sisa = y - beta * x - (y.mean() - beta * x.mean())
    v1 = np.var(y, ddof=1)
    s10 = pd.Series(y).rolling(10).sum().dropna().to_numpy()
    return {'log_nilai': np.log(max(float(s['medval20'].median()), 1.0)),
            'log_harga': np.log(float(s['close'].median())),
            'vol': np.sqrt(v1 * 250),
            'beta': beta,
            'r2': 1 - np.var(sisa, ddof=1) / v1 if v1 > 0 else np.nan,
            'idio': np.std(sisa, ddof=1) * np.sqrt(250),
            'skew': pd.Series(y).skew(),
            'diam': float((y == 0).mean()),
            'ac1': pd.Series(y).autocorr(1),
            'vr10': np.var(s10, ddof=1) / (10 * v1) if v1 > 0 else np.nan,
            'umur': float(s['hist'].iloc[0]) / 250,
            'bh': float(np.log(s['close'].iloc[-1] / s['close'].iloc[0])),
            'hari_layak': int(s['elig'].sum())}


def cmd_bangun():
    t0 = time.time()
    p = uji.muat()
    S = sinyal(p)
    per, _ = KL.siapkan(p)
    pasar = pasar_lengkap(p)
    mkt = pasar.diff()
    from .lead_lag import peta
    sektor = peta('sector')
    rows_tx = []
    for nama, aturan in MENU.items():
        sig = p.loc[S[nama].fillna(False), ['ticker', 'hist']]
        for t, g in sig.groupby('ticker', sort=False):
            a = per[t]
            for i, j in urut(a, np.sort(g['hist'].to_numpy()), aturan):
                r = float(np.log(a['close'][j] / a['close'][i]))
                d_in, d_out = a['date'][i], a['date'][j]
                if d_in not in pasar.index or d_out not in pasar.index:
                    continue
                rows_tx.append({'menu': nama, 'ticker': t, 'masuk': d_in, 'keluar': d_out, 'tahan': j - i,
                                'r': r + BIAYA_LOG, 'lebih': r - (pasar.loc[d_out] - pasar.loc[d_in])})
        print('  %s: %d transaksi (%.0f dtk)' % (nama, sum(1 for x in rows_tx if x['menu'] == nama), time.time() - t0),
              flush=True)
    tx = pd.DataFrame(rows_tx)
    tx['periode'] = np.where(tx['masuk'] < pd.Timestamp('2020-01-01'), '2013-19', '2020-26')

    # ciri per emiten-periode
    for nama in MENU:
        p['s_' + nama] = S[nama].fillna(False).astype(bool)
    half = p.groupby('ticker')['half'].first()
    rows_c = []
    for t, d in p.groupby('ticker', sort=False):
        d = d.sort_values('date')
        for np_, (a, b) in PERIODE.items():
            c = ciri_periode(d, mkt, a, b)
            if c is None:
                continue
            c.update({'ticker': t, 'periode': np_, 'half': int(half[t]), 'sektor': sektor.get(t)})
            dd = d[(d['date'] >= a) & (d['date'] <= b)]
            for nama in MENU:
                c['sinyal_' + nama] = int(dd['s_' + nama].sum())
            rows_c.append(c)
    ci = pd.DataFrame(rows_c)

    k = kepemilikan()
    for np_, (a, b) in PERIODE.items():
        kk = k[(k['as_of'] >= a) & (k['as_of'] <= b)].groupby('ticker')[['asing', 'individu', 'reksa_dana']].mean()
        mk = ci['periode'] == np_
        for kol in kk.columns:
            ci.loc[mk, kol] = ci.loc[mk, 'ticker'].map(kk[kol])
    pickle.dump({'tx': tx, 'ciri': ci}, open(CACHE, 'wb'))
    print('tersimpan %s: %d transaksi, %d emiten-periode (%.0f dtk)' % (CACHE, len(tx), len(ci), time.time() - t0))


def muat_cache():
    return pickle.load(open(CACHE, 'rb'))


def label(tx, ci, menu):
    """Satu baris per emiten-periode: hasil menu + ciri."""
    x = tx[tx['menu'] == menu]
    g = x.groupby(['ticker', 'periode'])
    L = pd.DataFrame({'n_tx': g.size(), 'lr': g['r'].sum(), 'lebih': g['lebih'].sum(),
                      'win': g['r'].apply(lambda s: (s > 0).mean()), 'tahan': g['tahan'].sum()}).reset_index()
    L = L.merge(ci, on=['ticker', 'periode'], how='left')
    L = L[L['n_tx'] >= MIN_TX].copy()
    L['naik'] = L['lr'] > 0
    L['ngalahin'] = L['lebih'] > 0
    yrs = np.where(L['periode'] == '2013-19', 7.0, 6.8)
    L['frek'] = L['sinyal_' + menu] / yrs
    return L


# ---------------------------------------------------------------------------
def cmd_ringkas():
    c = muat_cache()
    tx, ci = c['tx'], c['ciri']
    for menu in MENU:
        L = label(tx, ci, menu)
        print('\n' + '=' * 110 + '\n%s  (emiten-periode dengan >= %d transaksi)\n' % (menu, MIN_TX) + '=' * 110)
        for np_ in PERIODE:
            y = L[L['periode'] == np_]
            x = tx[(tx['menu'] == menu) & (tx['periode'] == np_)]
            print('%s: %4d emiten | NAIK %4d (%2.0f%%) | ngalahin pasar %2.0f%% | median transaksi/emiten %d | '
                  'median majemuk per emiten %+.1f%% | semua transaksi: n %d, majemuk/tx %+.2f%%, vs pasar/tx %+.2f%%'
                  % (np_, len(y), y['naik'].sum(), y['naik'].mean() * 100, y['ngalahin'].mean() * 100,
                     y['n_tx'].median(), (np.exp(y['lr'].median()) - 1) * 100, len(x),
                     (np.exp(x['r'].mean()) - 1) * 100, (np.exp(x['lebih'].mean()) - 1) * 100))
            # naik karena emitennya memang naik? (beli-tahan periode itu)
            print('        beli-tahan naik: di emiten NAIK %.0f%% | di emiten TURUN %.0f%% | '
                  'menu > beli-tahan %.0f%%'
                  % ((y.loc[y['naik'], 'bh'] > 0).mean() * 100, (y.loc[~y['naik'], 'bh'] > 0).mean() * 100,
                     (y['lr'] > y['bh']).mean() * 100))
        w = L.pivot(index='ticker', columns='periode', values=['naik', 'ngalahin', 'lr', 'lebih']).dropna()
        if len(w):
            n1, n2 = w[('naik', '2013-19')].astype(bool), w[('naik', '2020-26')].astype(bool)
            g1, g2 = w[('ngalahin', '2013-19')].astype(bool), w[('ngalahin', '2020-26')].astype(bool)
            print('PERSISTENSI (%d emiten di dua periode): NAIK 13-19 -> NAIK 20-26 %.0f%% (n %d) vs TURUN 13-19 -> NAIK %.0f%% (n %d)'
                  % (len(w), n2[n1].mean() * 100, n1.sum(), n2[~n1].mean() * 100, (~n1).sum()))
            print('                     ngalahin pasar -> ngalahin lagi %.0f%% vs kalah -> ngalahin %.0f%% | '
                  'rho lr %.2f, rho lebih %.2f'
                  % (g2[g1].mean() * 100, g2[~g1].mean() * 100,
                     w[('lr', '2013-19')].rank().corr(w[('lr', '2020-26')].rank()),
                     w[('lebih', '2013-19')].rank().corr(w[('lebih', '2020-26')].rank())))


def auc(x, y):
    """P(ciri emiten NAIK > ciri emiten TURUN), Mann-Whitney."""
    x, y = np.asarray(x, float), np.asarray(y, float)
    x, y = x[np.isfinite(x)], y[np.isfinite(y)]
    if len(x) < 10 or len(y) < 10:
        return np.nan
    r = pd.Series(np.concatenate([x, y])).rank().to_numpy()
    return (r[:len(x)].sum() - len(x) * (len(x) + 1) / 2) / (len(x) * len(y))


def cmd_ciri(target='naik'):
    c = muat_cache()
    tx, ci = c['tx'], c['ciri']
    for menu in MENU:
        L = label(tx, ci, menu)
        rows = {}
        for sn, (h, np_) in SEL.items():
            y = L[(L['half'] == h) & (L['periode'] == np_)]
            a, b = y[y[target]], y[~y[target]]
            rows[sn] = {k: auc(a[k], b[k]) for k in CIRI + ['bh']}
            rows[sn]['n NAIK/TURUN'] = '%d/%d' % (len(a), len(b))
        df = pd.DataFrame(rows)
        print('\n' + '=' * 100 + '\n%s: AUC ciri %s vs tidak (0,5 = tak beda; >0,5 = emiten %s cirinya lebih tinggi)\n'
              % (menu, target.upper(), target.upper()) + '=' * 100)
        print(df.to_string(float_format=lambda v: '%.2f' % v))


FITUR_KLASTER = ['log_nilai', 'log_harga', 'vol', 'beta', 'r2', 'idio', 'skew', 'diam', 'ac1', 'vr10', 'umur']


def cmd_klaster():
    """Kelompokkan emiten NAIK satu periode menurut ciri (z-skor relatif emiten
    lain di periode itu), lalu lihat porsi NAIK semua emiten yang jatuh ke tiap
    kelompok -- di periode itu sendiri dan di periode LAIN (dua arah).
    Sel CARI saja terlalu kecil untuk dikelompokkan (32 emiten NAIK di TB)."""
    from sklearn.cluster import KMeans
    from sklearn.metrics import silhouette_score
    c = muat_cache()
    tx, ci = c['tx'], c['ciri']
    fitur = FITUR_KLASTER
    for menu in ('TB', 'KD10', 'KD1', 'JD'):
        L = label(tx, ci, menu).dropna(subset=fitur)
        Z = {}
        for np_ in PERIODE:
            y = L[L['periode'] == np_]
            Z[np_] = ((y[fitur] - y[fitur].mean()) / y[fitur].std()).clip(-3, 3)
        for fit, lain in (('2013-19', '2020-26'), ('2020-26', '2013-19')):
            y = L[L['periode'] == fit]
            naik = Z[fit][y['naik'].to_numpy()]
            if len(naik) < 20:
                continue
            best = None
            for k in range(2, 6):
                km = KMeans(n_clusters=k, n_init=20, random_state=0).fit(naik.to_numpy())
                if min(np.bincount(km.labels_)) < 4:
                    continue
                s = silhouette_score(naik.to_numpy(), km.labels_)
                if best is None or s > best[0]:
                    best = (s, k, km)
            s, k, km = best
            print('\n' + '=' * 120 + '\n%s: %d emiten NAIK %s -> %d kelompok (silhouette %.2f)\n'
                  % (menu, len(naik), fit, k, s) + '=' * 120)
            prof = pd.DataFrame(km.cluster_centers_, columns=fitur).round(1)
            prof['n NAIK'] = np.bincount(km.labels_, minlength=k)
            yn = y[y['naik'].to_numpy()]
            for kol in ('asing', 'individu', 'bh'):
                prof[kol + ' med'] = [round(yn.loc[km.labels_ == q, kol].median() * (100 if kol == 'bh' else 1), 0)
                                      for q in range(k)]
            prof['sektor terbanyak'] = [', '.join('%s %d' % (s_[:12], n_) for s_, n_ in
                                                 yn.loc[km.labels_ == q, 'sektor'].value_counts().head(2).items())
                                        for q in range(k)]
            print('Profil (z-skor relatif semua emiten periode itu; bh = beli-tahan %, median):')
            print(prof.to_string())
            rows = []
            for np_ in (fit, lain):
                yy = L[L['periode'] == np_]
                lab = km.predict(Z[np_].to_numpy())
                r = {'periode': np_ + (' (tempat kelompok dibuat)' if np_ == fit else ' (periode LAIN)'),
                     'semua': '%.0f%% (n %d)' % (yy['naik'].mean() * 100, len(yy))}
                for q in range(k):
                    m = lab == q
                    r['kel %d' % q] = ('%.0f%% / %.0f%% (n %d)' % (yy.loc[m, 'naik'].mean() * 100,
                                                                  yy.loc[m, 'ngalahin'].mean() * 100, m.sum())
                                       if m.sum() else '-')
                rows.append(r)
            print('Porsi NAIK / ngalahin pasar di antara SEMUA emiten yang masuk tiap kelompok:')
            print(pd.DataFrame(rows).set_index('periode').to_string())


CIRI_CACHE = os.path.join(RESEARCH_CACHE, 'menu_per_saham_ciri_harian.pkl')
CIRI_ANTE = ['log_nilai', 'log_harga', 'vol', 'beta', 'r2', 'idio', 'diam', 'ac1', 'vr10', 'idio60', 'skew']


def ciri_berjalan(p, mkt, w=250):
    """Ciri emiten dari 250 hari bursa SAMPAI hari sinyal (tidak melihat ke depan)."""
    out = []
    for t, d in p.groupby('ticker', sort=False):
        d = d.sort_values('date')
        lr = np.log(d['close']).diff()
        lr[d['ret1'].abs() > 0.45] = np.nan
        lr.index = d['date'].to_numpy()
        m = mkt.reindex(lr.index)
        v1 = lr.rolling(w, min_periods=200).var()
        vm = m.rolling(w, min_periods=200).var()
        cv = lr.rolling(w, min_periods=200).cov(m)
        beta = cv / vm
        r2 = (cv * cv) / (v1 * vm)
        s10 = lr.rolling(10, min_periods=10).sum()
        lr60 = lr.rolling(60, min_periods=50).sum()
        m60 = m.rolling(60, min_periods=50).sum()
        out.append(pd.DataFrame({
            'ticker': t, 'date': lr.index,
            'log_nilai': np.log(d['medval20'].clip(lower=1)).to_numpy(),
            'log_harga': np.log(d['close']).to_numpy(),
            'vol': np.sqrt(v1 * 250).to_numpy(),
            'beta': beta.to_numpy(), 'r2': r2.to_numpy(),
            'idio': np.sqrt(v1 * (1 - r2) * 250).to_numpy(),
            'diam': (lr == 0).astype(float).rolling(w, min_periods=200).mean().to_numpy(),
            'ac1': lr.rolling(w, min_periods=200).corr(lr.shift(1)).to_numpy(),
            'vr10': (s10.rolling(w - 10, min_periods=180).var() / (10 * v1)).to_numpy(),
            'idio60': (lr60 - beta * m60).to_numpy(),         # bagian gerak 60h yang BUKAN karena pasar
            'skew': lr.rolling(w, min_periods=200).skew().to_numpy()}))
    c = pd.concat(out, ignore_index=True)
    fc = [k for k in c.columns if k not in ('ticker', 'date')]
    c[fc] = c[fc].astype('float32')
    return c


def kuintil(tx, kol, sel_mask):
    x = tx[sel_mask & tx[kol].notna()].copy()
    if len(x) < 100:
        return None
    x['q'] = pd.qcut(x[kol].rank(method='first'), 5, labels=False) + 1
    r = {}
    for q, g in x.groupby('q'):
        r['Q%d' % q] = (np.exp(g['lebih'].mean()) - 1) * 100
    a, b = x[x['q'] == 5], x[x['q'] == 1]
    r['Q5-Q1'] = r['Q5'] - r['Q1']
    r['t'] = t_beda(a['lebih'].to_numpy(), a['bulan'].to_numpy(), b['lebih'].to_numpy(), b['bulan'].to_numpy())
    r['n'] = len(x)
    return r


def se_klaster(x, g):
    """Galat baku rata-rata dengan galat dikelompokkan per bulan masuk."""
    e = x - x.mean()
    s = pd.Series(e).groupby(np.asarray(g)).sum().to_numpy()
    return np.sqrt((s ** 2).sum()) / len(x)


def t_beda(a, ga, b, gb):
    if len(a) < 20 or len(b) < 20:
        return np.nan
    return (a.mean() - b.mean()) / np.sqrt(se_klaster(a, ga) ** 2 + se_klaster(b, gb) ** 2)


def cmd_exante():
    """Ciri yang konsisten di tabel `ciri` (dihitung SEPANJANG periode) diuji ulang
    secara jujur: ciri 250 hari SEBELUM sinyal, per transaksi, kuintil di tiap sel.
    Angka = selisih vs pasar per transaksi (majemuk, %)."""
    c = muat_cache()
    tx, ci = c['tx'].copy(), c['ciri']
    if os.path.exists(CIRI_CACHE):
        cb = pd.read_pickle(CIRI_CACHE)
    else:
        p = uji.muat()
        cb = ciri_berjalan(p, pasar_lengkap(p).diff())
        cb.to_pickle(CIRI_CACHE)
    cb = cb.sort_values(['ticker', 'date'])
    cb[CIRI_ANTE] = cb.groupby('ticker', sort=False)[CIRI_ANTE].shift(1)   # nilai s.d. hari SINYAL (masuk - 1)
    tx = tx.merge(cb, left_on=['ticker', 'masuk'], right_on=['ticker', 'date'], how='left')
    half = ci.groupby('ticker')['half'].first()
    tx['half'] = tx['ticker'].map(half)
    tx['bulan'] = pd.to_datetime(tx['masuk']).dt.to_period('M').astype(str)
    pd.set_option('display.width', 250)
    for menu in MENU:
        x = tx[tx['menu'] == menu]
        print('\n' + '=' * 120 + '\n%s: kuintil ciri SEBELUM sinyal -> selisih vs pasar per transaksi (%%), Q5-Q1 (t)\n'
              % menu + '=' * 120)
        rows = []
        for kol in CIRI_ANTE:
            r = {'ciri': kol}
            for sn, (h, np_) in SEL.items():
                q = kuintil(x, kol, (x['half'] == h) & (x['periode'] == np_))
                r[sn] = ('%+5.1f %+5.1f %+5.1f %+5.1f %+5.1f | %+5.1f (%+.1f)'
                         % (q['Q1'], q['Q2'], q['Q3'], q['Q4'], q['Q5'], q['Q5-Q1'], q['t']) if q else '-')
            rows.append(r)
        print(pd.DataFrame(rows).set_index('ciri').to_string())


if __name__ == '__main__':
    perintah = sys.argv[1] if len(sys.argv) > 1 else 'ringkas'
    f = {'bangun': cmd_bangun, 'ringkas': cmd_ringkas, 'ciri': cmd_ciri, 'klaster': cmd_klaster,
         'exante': cmd_exante}.get(perintah)
    if f is None:
        print(__doc__)
        sys.exit(2)
    if perintah == 'ciri' and len(sys.argv) > 2:
        f(sys.argv[2])
    else:
        f()
