"""
Musim PER SAHAM -- apakah tiap emiten punya bulan "langganan" yang
berulang tiap tahun, dan apakah musim dividennya sendiri bisa dipakai?
(29 Okt 2026)

KENAPA
Uji kalender sebelumnya (ta_lanjutan.py kalender) di TINGKAT PASAR: Senin,
pergantian bulan, Lebaran -- tidak ada yang lolos. Yang belum pernah diuji:
musim milik tiap emiten sendiri. Literatur: Heston & Sadka (2008) -- saham
yang relatif kuat di bulan kalender tertentu cenderung kuat lagi di bulan
yang sama tahun-tahun berikutnya (lag 12, 24, 36 ... bulan); Keloharju,
Linnainmaa & Nyberg (2016) menemukan pola serupa di banyak kelas aset;
Hartzmark & Solomon (2013) -- saham naik di bulan ia DIPERKIRAKAN membagi
dividen (perkiraan = bulan dividen tahun lalu), padahal informasinya
sudah publik. Di BEI pemburu cum date banyak, jadi ini kandidat wajar.

DESAIN (didaftar SEBELUM hasil dilihat)
Data: harga Yahoo (disesuaikan dividen & split -- return = return total)
2010-2026, return bulanan per emiten dikurangi rata-rata-sama emiten likuid
bulan itu (= selisih vs pasar). Bulan dengan loncatan >45% dibuang.
Likuid di awal bulan = saringan uji.py (tanpa traded30, lihat cmd_bangun)
pada hari bursa terakhir bulan sebelumnya.

1. PER EMITEN: profil 12 bulan (rata-rata selisih per bulan kalender)
   2010-2019 vs 2020-2026 -> korelasi per emiten. Nol = korelasi dengan
   bulan diacak (1.000 kali). Emiten minimal 5 tahun / 4 tahun per bulan.
2. ANTAR EMITEN (yang bisa dipakai): skor musim = rata-rata selisih emiten
   di bulan kalender yang SAMA, 1-5 tahun lalu (min. 3 tahun). IC peringkat
   per bulan dan selisih desil 10 - desil 1. Pembanding: rata-rata 11 bulan
   LAIN di tahun-tahun yang sama (kalau itu sama kuatnya, yang tertangkap
   bukan musim tapi momentum/ciri emiten). Sel: emiten A 2015-19 (cari),
   emiten B 2020-26 (uji), dua sel silang.
3. BULAN DIVIDEN: event = perkiraan ex-date tahun ini = ex-date tahun lalu
   + 1 tahun (tidak mengintip pengumuman tahun ini). Masuk close ~25 hari
   bursa sebelum perkiraan ex-date, keluar close sehari sebelumnya; juga
   jendela 20 hari SESUDAH perkiraan ex-date. Selisih vs indeks rata-rata-
   sama emiten layak di jendela yang sama persis.

HASIL (29 Okt 2026)
1. MUSIM PER EMITEN: GAGAL. Korelasi profil 12 bulan 2010-19 vs 2020-26
   rata-rata -0,07 (nol +0,00, sd 0,06; 57 emiten cukup data); bulan terbaik
   sama di dua periode 3,5% (kebetulan 8,3%). Antar emiten: IC skor musim
   -0,03 / +0,01 / +0,01 / +0,02, tak ada sel yang t > 1,5.
2. BULAN DIVIDEN: LOLOS relatif terhadap pasar, TIDAK untung absolut.
   25 hari bursa sebelum perkiraan ex-date, vs pasar: CARI +1,20% (t 1,8),
   UJI +1,49% (t 2,3), silang +1,32% (t 2,6) / +1,98% (t 2,3); positif 13/14
   tahun (2020 -0,8%). Plasebo setengah tahun dari musim dividen: +0,07% /
   +0,52% -- jadi bukan "pembagi dividen selalu menang". Makin tinggi imbal
   hasil tahun lalu makin kuat (>= 2,5%: +2,0 s.d. +3,6%; < 1%: ~0).
   Kuncinya dividen memang dibagi dekat perkiraan (+-15 hari: +2,7%, t 6,6);
   perkiraan meleset / tidak dibagi: ~0 (tak bisa diketahui saat masuk).
   Per emiten tidak ada "langganan": porsi emiten yang run-up >= 80% tahun
   9% vs 10% kalau semua emiten sama (p=0,56); rho run-up tahun lalu vs
   tahun ini -0,02 / +0,00.
   SETELAH ONGKOS 0,9%: vs pasar +0,4% (2013-19) / +0,8% (2020-26), imbal
   hasil >= 2,5%: +1,0% / +1,8%. ABSOLUT bersih NEGATIF -1,4% / -0,8% (untung
   45-49%): jendela pra-dividen (umumnya Apr-Jun) pasarnya sendiri lemah.
   Gunanya waktu, bukan strategi sendiri: jangan menjual pembagi dividen
   imbal hasil tinggi di ~5 minggu sebelum perkiraan ex-date-nya, dan kalau
   memang mau membeli, lebih baik sebelum jendela itu daripada sesudahnya.

PEMAKAIAN (dari <project>/)
    python -m website.riset_pola_naik.musiman_saham bangun
    python -m website.riset_pola_naik.musiman_saham profil
    python -m website.riset_pola_naik.musiman_saham silang
    python -m website.riset_pola_naik.musiman_saham dividen
    python -m website.riset_pola_naik.musiman_saham dividen-kokoh
"""
import hashlib
import os
import pickle
import sys
import time
import warnings

import numpy as np
import pandas as pd

from . import panel as PN
from . import uji

warnings.filterwarnings('ignore')

CACHE = os.path.join(PN.RESEARCH_CACHE, 'musiman_saham.pkl')


def separuh(t):
    return int(hashlib.md5(t.encode()).hexdigest(), 16) % 2


def cmd_bangun():
    t0 = time.time()
    p = PN.bangun()
    p = p.sort_values(['ticker', 'date'])
    # tanpa traded30: di 2017-2019 Yahoo memuat baris libur bervolume 0, jadi traded30 < 0,9
    # di SEMUA emiten sekitar Lebaran/Natal (lihat menu_per_saham.pasar_lengkap). Median
    # nilai 20 hari sudah menyaring emiten yang jarang bertransaksi.
    p['likuid'] = ((p['hist'] >= 260) & (p['close'] >= uji.MIN_HARGA) & (p['medval20'] >= uji.MIN_NILAI)
                   & (p['bad_back60'] == 0))
    p['ret1'] = p.groupby('ticker', sort=False)['close'].pct_change()
    p['ym'] = p['date'].dt.year * 12 + p['date'].dt.month - 1
    g = p.groupby(['ticker', 'ym'], sort=False)
    m = pd.DataFrame({'close': g['close'].last(), 'bad': g['ret1'].apply(lambda s: (s.abs() > 0.45).any()),
                      'likuid_akhir': g['likuid'].last()}).reset_index()
    m = m.sort_values(['ticker', 'ym'])
    gm = m.groupby('ticker', sort=False)
    m['lr'] = np.log(m['close']).diff()
    m.loc[gm['ym'].diff() != 1, 'lr'] = np.nan            # hanya bulan berurutan
    m.loc[m['bad'], 'lr'] = np.nan
    m['likuid'] = gm['likuid_akhir'].shift(1).fillna(False).astype(bool)   # likuid di AWAL bulan
    m.loc[gm['ym'].diff() != 1, 'likuid'] = False
    pasar = m[m['likuid'] & m['lr'].notna()].groupby('ym')['lr'].mean()
    m['ex'] = m['lr'] - m['ym'].map(pasar)
    m['tahun'] = m['ym'] // 12
    m['bulan'] = m['ym'] % 12 + 1
    m['half'] = m['ticker'].map(separuh)

    # pasar harian (indeks rata-rata-sama emiten layak kemarin) untuk event dividen
    q = p[['ticker', 'date', 'close', 'likuid', 'ret1']].copy()
    q['lr'] = np.log(q['close']).groupby(q['ticker']).diff()
    q['lk'] = q.groupby('ticker')['likuid'].shift(1).fillna(False).astype(bool)
    q = q[q['lk'] & (q['ret1'].abs() <= 0.45)]
    harian = q.groupby('date')['lr'].mean().sort_index().cumsum()
    per = {t: {'date': d['date'].to_numpy(), 'close': d['close'].to_numpy(float),
               'bad': (d['ret1'].abs() > 0.45).to_numpy(), 'likuid': d['likuid'].to_numpy(bool)}
           for t, d in p.groupby('ticker', sort=False)}
    pickle.dump({'bulanan': m.drop(columns=['likuid_akhir']), 'harian': harian, 'per': per}, open(CACHE, 'wb'))
    print('tersimpan %s: %d emiten-bulan, %d emiten (%.0f dtk)' % (CACHE, len(m), m['ticker'].nunique(), time.time() - t0))


def muat():
    return pickle.load(open(CACHE, 'rb'))


# ---------------------------------------------------------------------------
def profil(m, a, b, min_th):
    x = m[(m['tahun'] >= a) & (m['tahun'] <= b) & m['likuid'] & m['ex'].notna()]
    g = x.groupby(['ticker', 'bulan'])['ex']
    pr = g.mean().unstack()
    n = g.size().unstack()
    return pr[(n >= min_th).all(axis=1) & (pr.notna().all(axis=1))]


def cmd_profil():
    m = muat()['bulanan']
    p1 = profil(m, 2010, 2019, 5)
    p2 = profil(m, 2020, 2026, 4)
    t = p1.index.intersection(p2.index)
    A, B = p1.loc[t].to_numpy(), p2.loc[t].to_numpy()

    def rkor(A, B):
        a = A - A.mean(1, keepdims=True); b = B - B.mean(1, keepdims=True)
        return (a * b).sum(1) / np.sqrt((a * a).sum(1) * (b * b).sum(1))
    r = rkor(A, B)
    rng = np.random.default_rng(0)
    nol = np.array([rkor(A, B[:, rng.permutation(12)]).mean() for _ in range(1000)])
    print('PROFIL 12 BULAN PER EMITEN: %d emiten punya >=5 thn/bulan 2010-19 dan >=4 thn/bulan 2020-26' % len(t))
    print('  korelasi profil 2010-19 vs 2020-26: rata-rata %+.3f, median %+.3f, positif %.0f%%'
          % (r.mean(), np.median(r), (r > 0).mean() * 100))
    print('  nol (bulan diacak 1.000x): rata-rata %+.3f, sd %.3f -> z %.1f, p %.3f'
          % (nol.mean(), nol.std(), (r.mean() - nol.mean()) / nol.std(), (nol >= r.mean()).mean()))
    # bulan terkuat/terlemah tiap emiten berulang?
    top1, top2 = A.argmax(1), B.argmax(1)
    bot1, bot2 = A.argmin(1), B.argmin(1)
    print('  bulan TERBAIK sama di dua periode: %.1f%% (kebetulan 8,3%%) | bulan TERBURUK sama: %.1f%%'
          % ((top1 == top2).mean() * 100, (bot1 == bot2).mean() * 100))
    rk1 = pd.DataFrame(A).rank(axis=1).to_numpy(); rk2 = pd.DataFrame(B).rank(axis=1).to_numpy()
    for lbl, sel in (('3 bulan terbaik 2010-19', rk1 >= 10), ('3 bulan terburuk 2010-19', rk1 <= 3)):
        print('  %s -> rata-rata selisih bulan itu di 2020-26: %+.2f%%/bln (bulan lain %+.2f%%)'
              % (lbl, B[sel].mean() * 100, B[~sel].mean() * 100))
    # bulan kalender mana yang paling "berulang"?
    rows = []
    for k in range(12):
        rows.append({'bulan': k + 1, 'korelasi antar emiten (2010-19 vs 2020-26)':
                     round(pd.Series(A[:, k]).corr(pd.Series(B[:, k]), method='spearman'), 3)})
    print(pd.DataFrame(rows).set_index('bulan').T.to_string())
    pickle.dump({'r': pd.Series(r, index=t), 'p1': p1.loc[t], 'p2': p2.loc[t]},
                open(os.path.join(PN.RESEARCH_CACHE, 'musiman_profil.pkl'), 'wb'))


def skor_musim(m, lags=5, min_n=3):
    """Skor musim & pembanding 11-bulan-lain dari 1..lags tahun lalu (tanpa bulan ini)."""
    w = m.pivot(index='ym', columns='ticker', values='ex').sort_index()
    w = w.reindex(range(w.index.min(), w.index.max() + 1))
    sama = sum(w.shift(12 * k).fillna(0) for k in range(1, lags + 1))
    n_sama = sum(w.shift(12 * k).notna().astype(int) for k in range(1, lags + 1))
    musim = (sama / n_sama).where(n_sama >= min_n)
    # semua bulan di jendela 12..12*lags lag, dikurangi bulan yang sama
    tot = w.fillna(0).rolling(12 * lags, min_periods=1).sum().shift(1)
    ntot = w.notna().astype(int).rolling(12 * lags, min_periods=1).sum().shift(1)
    # bulan t-1..t-11 dibuang supaya pembanding tidak memuat momentum jangka pendek
    pendek = w.fillna(0).rolling(11, min_periods=1).sum().shift(1)
    npendek = w.notna().astype(int).rolling(11, min_periods=1).sum().shift(1)
    lain = ((tot - pendek - sama) / (ntot - npendek - n_sama)).where(n_sama >= min_n)
    mom = w.fillna(0).rolling(11, min_periods=8).sum().shift(2)       # momentum 12-2 klasik
    out = pd.DataFrame({'musim': musim.stack(), 'lain': lain.stack(), 'mom': mom.stack()})
    out.index.names = ['ym', 'ticker']
    return out.reset_index()


def cmd_silang():
    m = muat()['bulanan']
    s = skor_musim(m)
    d = m.merge(s, on=['ym', 'ticker'], how='left')
    d = d[d['likuid'] & d['ex'].notna() & d['musim'].notna()]
    d['periode'] = np.where(d['tahun'] < 2020, 1, 2)
    d = d[d['tahun'] >= 2015]
    sel = {'CARI (A 2015-19)': (0, 1), 'UJI (B 2020-26)': (1, 2), 'silang (B 2015-19)': (1, 1),
           'silang (A 2020-26)': (0, 2)}

    def ic_seri(x, kol):
        r = x.groupby('ym').apply(lambda g: g[kol].corr(g['ex'], method='spearman') if len(g) >= 30 else np.nan)
        return r.dropna()

    rows = []
    for sn, (h, per) in sel.items():
        x = d[(d['half'] == h) & (d['periode'] == per)].copy()
        r = {'sel': sn, 'emiten-bulan': len(x), 'bulan': x['ym'].nunique()}
        for kol in ('musim', 'lain', 'mom'):
            ic = ic_seri(x, kol)
            r['IC ' + kol] = '%+.3f (t %+.1f)' % (ic.mean(), ic.mean() / ic.std() * np.sqrt(len(ic)))
        x['dec'] = x.groupby('ym')['musim'].transform(lambda v: np.ceil(v.rank(pct=True) * 10))
        sp = x.groupby('ym').apply(lambda g: g.loc[g['dec'] == 10, 'ex'].mean() - g.loc[g['dec'] == 1, 'ex'].mean()).dropna()
        hi = x.groupby('ym').apply(lambda g: g.loc[g['dec'] == 10, 'ex'].mean()).dropna()
        r['D10-D1 %/bln'] = '%+.2f (t %+.1f)' % (sp.mean() * 100, sp.mean() / sp.std() * np.sqrt(len(sp)))
        r['D10 vs pasar %/bln'] = '%+.2f (t %+.1f)' % (hi.mean() * 100, hi.mean() / hi.std() * np.sqrt(len(hi)))
        # musim setelah dikendalikan lain + mom (regresi per bulan, rata-rata koefisien ala Fama-MacBeth)
        def fm(g):
            g = g.dropna(subset=['musim', 'lain', 'mom'])
            if len(g) < 40:
                return np.nan
            z = lambda v: (v.rank(pct=True) - 0.5)
            A = np.column_stack([np.ones(len(g)), z(g['musim']), z(g['lain']), z(g['mom'])])
            return np.linalg.lstsq(A, g['ex'].to_numpy(), rcond=None)[0][1]
        b = x.groupby('ym').apply(fm).dropna()
        r['FM musim | lain,mom'] = '%+.2f (t %+.1f)' % (b.mean() * 100, b.mean() / b.std() * np.sqrt(len(b)))
        rows.append(r)
    print('SKOR MUSIM antar emiten (selisih bulanan vs pasar; musim = bulan kalender sama 1-5 thn lalu)')
    print(pd.DataFrame(rows).set_index('sel').T.to_string())
    x = d.copy()
    x['dec'] = x.groupby('ym')['musim'].transform(lambda v: np.ceil(v.rank(pct=True) * 10))
    th = x.groupby(['tahun', 'ym']).apply(lambda g: g.loc[g['dec'] == 10, 'ex'].mean() - g.loc[g['dec'] == 1, 'ex'].mean())
    print('\nD10-D1 per tahun (%/bln, semua emiten):')
    print((th.groupby('tahun').mean() * 100).round(2).to_frame('D10-D1').T.to_string())
    th = x.groupby(['bulan', 'ym']).apply(lambda g: g.loc[g['dec'] == 10, 'ex'].mean() - g.loc[g['dec'] == 1, 'ex'].mean())
    print('D10-D1 per bulan kalender (%/bln, semua emiten 2015-26):')
    print((th.groupby('bulan').mean() * 100).round(2).to_frame('D10-D1').T.to_string())


def kejadian_dividen(c, sebelum=25, sesudah=20, geser_plasebo=0):
    """Event perkiraan ex-date = ex-date tahun lalu + 365 hari, per emiten.
    geser_plasebo: hari kalender tambahan (mis. 182 = setengah tahun dari musim
    dividennya) -- emiten dan jumlah event sama, hanya jendelanya bukan musim dividen."""
    d = pickle.load(open(os.path.join(PN.RESEARCH_CACHE, 'aksi_korporasi.pkl'), 'rb'))['aksi']
    mentah = pickle.load(open(os.path.join(PN.RESEARCH_CACHE, 'harga_mentah_close.pkl'), 'rb'))
    per, harian = c['per'], c['harian']
    rows = []
    for t, a in d.items():
        if 'Dividends' not in a or t not in per:
            continue
        s = a['Dividends']
        s = s[s > 0]
        if s.empty:
            continue
        ex = pd.DatetimeIndex(pd.to_datetime(s.index)).tz_localize(None).normalize()
        nilai = s.to_numpy(float)
        x = per[t]
        tgl = pd.DatetimeIndex(x['date'])
        terakhir = None
        for e_lalu, dv in sorted(zip(ex, nilai)):
            P = e_lalu + pd.Timedelta(days=365 + geser_plasebo)
            if terakhir is not None and (P - terakhir).days < 45:
                continue                   # dua dividen berdekatan tahun lalu -> satu event
            terakhir = P
            k = tgl.searchsorted(P)        # hari bursa pertama >= perkiraan ex-date
            i, j, j2 = k - sebelum, k - 1, k + sesudah - 1
            if i < 1 or j2 >= len(tgl) or tgl[i] < pd.Timestamp('2013-01-01'):
                continue
            if not x['likuid'][i - 1]:
                continue
            ok_pra = not x['bad'][i + 1:j + 1].any()
            ok_pasca = not x['bad'][j + 1:j2 + 1].any()
            try:
                m_pra = harian.loc[tgl[j]] - harian.loc[tgl[i]]
                m_pasca = harian.loc[tgl[j2]] - harian.loc[tgl[j]]
            except KeyError:
                continue
            # dividen benar-benar dibagi tahun ini di sekitar perkiraan? (hanya untuk penjelasan, BUKAN syarat)
            nyata = ex[(ex > e_lalu + pd.Timedelta(days=200)) & (ex < e_lalu + pd.Timedelta(days=530))]
            geser = (nyata[np.argmin(np.abs((nyata - P).days))] - P).days if len(nyata) else np.nan
            raw = mentah.get(t)
            yl = np.nan
            if raw is not None:
                sb = raw[raw.index <= tgl[i - 1]]
                if len(sb) and sb.iloc[-1] > 0:
                    yl = dv / float(sb.iloc[-1]) * 100     # dividen tahun lalu / harga mentah saat masuk
            rows.append({'ticker': t, 'masuk': tgl[i], 'perkiraan_ex': tgl[k] if k < len(tgl) else P,
                         'pra': np.log(x['close'][j] / x['close'][i]) - m_pra if ok_pra else np.nan,
                         'pasca': np.log(x['close'][j2] / x['close'][j]) - m_pasca if ok_pasca else np.nan,
                         'yield': yl, 'geser_hari': geser})
    ev = pd.DataFrame(rows)
    ev['half'] = ev['ticker'].map(separuh)
    ev['tahun'] = ev['masuk'].dt.year
    ev['periode'] = np.where(ev['tahun'] < 2020, 1, 2)
    ev['bulan'] = ev['masuk'].dt.to_period('M').astype(str)
    return ev


def ringkas_ev(x, kol):
    v = x[kol].dropna()
    if len(v) < 30:
        return '-'
    g = x.loc[v.index, 'bulan']
    t = v.mean() / (np.sqrt((pd.Series(v - v.mean()).groupby(g.to_numpy()).sum() ** 2).sum()) / len(v))
    return '%+.2f%% (t %+.1f, n %d, positif %.0f%%)' % ((np.exp(v.mean()) - 1) * 100, t, len(v), (v > 0).mean() * 100)


def cmd_dividen():
    c = muat()
    ev = kejadian_dividen(c)
    sel = {'CARI (A 2013-19)': (0, 1), 'UJI (B 2020-26)': (1, 2), 'silang (B 2013-19)': (1, 1),
           'silang (A 2020-26)': (0, 2), 'SEMUA': (None, None)}
    print('BULAN DIVIDEN: %d event (perkiraan ex-date = ex-date tahun lalu + 1 thn), emiten likuid saat masuk'
          % len(ev))
    print('  dividen nyata tahun ini dalam +-30 hari dari perkiraan: %.0f%% | tidak ada dividen dlm 200-530 hr: %.0f%%'
          % ((ev['geser_hari'].abs() <= 30).mean() * 100, ev['geser_hari'].isna().mean() * 100))
    rows = []
    for sn, (h, per) in sel.items():
        x = ev if h is None else ev[(ev['half'] == h) & (ev['periode'] == per)]
        rows.append({'sel': sn, 'PRA: 25 hr bursa sebelum perkiraan ex (vs pasar)': ringkas_ev(x, 'pra'),
                     'PASCA: 20 hr sesudahnya': ringkas_ev(x, 'pasca')})
    print(pd.DataFrame(rows).set_index('sel').to_string())
    print('\nPer imbal hasil (dividen tahun lalu / harga mentah saat masuk), semua sel:')
    rows = []
    for lo, hi, lbl in ((0, 1, '< 1%'), (1, 2.5, '1-2,5%'), (2.5, 5, '2,5-5%'), (5, 1e9, '>= 5%')):
        for per in (1, 2):
            x = ev[(ev['yield'] >= lo) & (ev['yield'] < hi) & (ev['periode'] == per)]
            rows.append({'imbal hasil': lbl, 'periode': '2013-19' if per == 1 else '2020-26',
                         'PRA': ringkas_ev(x, 'pra'), 'PASCA': ringkas_ev(x, 'pasca')})
    print(pd.DataFrame(rows).set_index(['imbal hasil', 'periode']).to_string())
    th = ev.groupby('tahun').apply(lambda g: (np.exp(g['pra'].mean()) - 1) * 100).round(2)
    print('\nPRA per tahun (%):')
    print(th.to_frame('pra').T.to_string())
    # per emiten: run-up tahun lalu meramal run-up tahun ini?
    e2 = ev.dropna(subset=['pra']).sort_values(['ticker', 'masuk'])
    e2['pra_lalu'] = e2.groupby('ticker')['pra'].shift(1)
    e2 = e2.dropna(subset=['pra_lalu'])
    for per in (1, 2):
        z = e2[e2['periode'] == per]
        print('PER EMITEN periode %d: korelasi peringkat run-up tahun lalu vs tahun ini %.3f (n %d); '
              'run-up tahun lalu >0 -> tahun ini %+.2f%%, <=0 -> %+.2f%%'
              % (per, z['pra'].corr(z['pra_lalu'], method='spearman'), len(z),
                 (np.exp(z.loc[z['pra_lalu'] > 0, 'pra'].mean()) - 1) * 100,
                 (np.exp(z.loc[z['pra_lalu'] <= 0, 'pra'].mean()) - 1) * 100))
    ev.to_pickle(os.path.join(PN.RESEARCH_CACHE, 'musiman_dividen_ev.pkl'))


def cmd_dividen_kokoh():
    """Pemeriksaan sesudah hasil PRA dilihat: plasebo setengah tahun, panjang jendela,
    dibagi/tidaknya dividen tahun ini (penjelasan saja), sebaran per emiten, ongkos."""
    c = muat()
    biaya = -np.log(1 - 0.005) + np.log(1 + 0.004)        # pulang-pergi ~0,9%
    print('1. PLASEBO: jendela yang sama tapi digeser setengah tahun dari musim dividen emiten itu')
    rows = []
    for nama, kw in (('musim dividen (asli)', {}), ('plasebo +182 hari', {'geser_plasebo': 182}),
                     ('plasebo -182 hari', {'geser_plasebo': -182})):
        ev = kejadian_dividen(c, **kw)
        r = {'jendela': nama}
        for sn, per in (('2013-19', 1), ('2020-26', 2), ('semua', None)):
            x = ev if per is None else ev[ev['periode'] == per]
            r[sn] = ringkas_ev(x, 'pra')
        rows.append(r)
    print(pd.DataFrame(rows).set_index('jendela').to_string())

    print('\n2. PANJANG JENDELA sebelum perkiraan ex-date (hari bursa), semua emiten:')
    rows = []
    for k in (10, 15, 25, 40):
        ev = kejadian_dividen(c, sebelum=k)
        rows.append({'hari': k, '2013-19': ringkas_ev(ev[ev['periode'] == 1], 'pra'),
                     '2020-26': ringkas_ev(ev[ev['periode'] == 2], 'pra')})
    print(pd.DataFrame(rows).set_index('hari').to_string())

    ev = kejadian_dividen(c)
    print('\n3. Dibagi tahun ini dekat perkiraan? (TIDAK bisa diketahui saat masuk -- penjelasan saja)')
    kel = np.where(ev['geser_hari'].isna(), 'tidak ada dividen',
                   np.where(ev['geser_hari'].abs() <= 15, 'ex nyata +-15 hari',
                            np.where(ev['geser_hari'] < -15, 'ex nyata LEBIH AWAL >15 hari', 'ex nyata lebih LAMBAT >15 hari')))
    for k in pd.unique(kel):
        print('  %-32s %s' % (k, ringkas_ev(ev[kel == k], 'pra')))

    print('\n4. PER EMITEN (>= 5 event): porsi run-up positif per emiten vs binomial p=0,5')
    g = ev.dropna(subset=['pra']).groupby('ticker')['pra']
    n, pos = g.size(), g.apply(lambda s: (s > 0).sum())
    n, pos = n[n >= 5], pos[n >= 5]
    rng = np.random.default_rng(0)
    sim = np.array([(rng.binomial(n.to_numpy(), 0.5) / n.to_numpy() >= 0.8).mean() for _ in range(2000)])
    print('  %d emiten | median porsi positif %.0f%% | emiten dgn >= 80%% positif: %.0f%% (kalau acak p=0,5: %.0f%%)'
          % (len(n), (pos / n).median() * 100, ((pos / n) >= 0.8).mean() * 100, sim.mean() * 100))
    print('  porsi positif keseluruhan %.1f%% -> kalau semua emiten p=%.2f, emiten >=80%% positif diharapkan: %.0f%%'
          % ((ev['pra'] > 0).mean() * 100, (ev['pra'] > 0).mean(),
             np.mean([(rng.binomial(n.to_numpy(), (ev['pra'] > 0).mean()) / n.to_numpy() >= 0.8).mean() for _ in range(2000)]) * 100))

    print('\n5. SETELAH ONGKOS (pulang-pergi 0,9%%) dan ABSOLUT, per imbal hasil, 2013-19 / 2020-26:')
    ev['abs'] = ev['pra']        # selisih vs pasar; absolut dihitung terpisah di bawah
    per = c['per']
    absr = []
    for r in ev.itertuples():
        x = per[r.ticker]
        i = np.searchsorted(x['date'], np.datetime64(r.masuk))
        j = np.searchsorted(x['date'], np.datetime64(r.perkiraan_ex)) - 1
        absr.append(np.log(x['close'][j] / x['close'][i]) if 0 <= i < j < len(x['close']) and np.isfinite(r.pra) else np.nan)
    ev['abs'] = absr
    rows = []
    for lo, hi, lbl in ((0, 1e9, 'semua'), (0, 2.5, '< 2,5%'), (2.5, 1e9, '>= 2,5%')):
        r = {'imbal hasil': lbl}
        for per_, nm in ((1, '2013-19'), (2, '2020-26')):
            x = ev[(ev['yield'] >= lo) & (ev['yield'] < hi) & (ev['periode'] == per_)].dropna(subset=['pra', 'abs'])
            r[nm] = 'vs pasar bersih %+.2f%% | absolut bersih %+.2f%%, untung %.0f%% (n %d)' % (
                (np.exp((x['pra'] - biaya).mean()) - 1) * 100, (np.exp((x['abs'] - biaya).mean()) - 1) * 100,
                ((x['abs'] - biaya) > 0).mean() * 100, len(x))
        rows.append(r)
    print(pd.DataFrame(rows).set_index('imbal hasil').to_string())


if __name__ == '__main__':
    perintah = sys.argv[1] if len(sys.argv) > 1 else 'profil'
    f = {'bangun': cmd_bangun, 'profil': cmd_profil, 'silang': cmd_silang, 'dividen': cmd_dividen,
         'dividen-kokoh': cmd_dividen_kokoh}.get(perintah)
    if f is None:
        print(__doc__)
        sys.exit(2)
    f()
