"""
Jatuh SENDIRI vs jatuh BARENG PASAR -- dari uji menu per saham (29 Okt 2026).

ASAL
menu_per_saham.py exante: di transaksi per emiten Skor Kecondongan desil 1
dan Jatuh Dalam, ciri yang paling memisahkan emiten yang lanjut kalah dari
yang tidak adalah R2 terhadap pasar (seberapa besar gerak harian emiten itu
dijelaskan pasar, 250 hari sebelum sinyal) -- di keempat sel, bukan
likuiditas. Tapi "vs pasar" polos memihak beta tinggi kalau sinyalnya
berkumpul sebelum pasar memantul (crash 2020), jadi diuji ulang di sini.

DESAIN (didaftar SEBELUM hasil dilihat)
Kerangka uji.py: hari layak, satu kejadian per emiten per 20 bar, masuk
close t+1, hasil 60 hari.
    vs pasar     = log(1+fwd60) - rata-rata log semua emiten layak hari itu (b_lr60)
    alfa beta    = log(1+fwd60) - beta_250h x log return pasar di jendela yang sama
                   (pasar = indeks rata-rata-sama emiten layak, beta dari 250 hari
                   SEBELUM sinyal) -- yang tersisa setelah beta dihitung
Kelompok: desil 1 Kecondongan, Jatuh Dalam, dan SEMUA hari layak (apakah R2
rendah buruk di mana saja, atau khusus emiten yang sedang jatuh?).
Uji: kuintil R2 di tiap sel; regresi alfa ~ R2 + likuiditas + porsi hari
diam + volatilitas (peringkat per bulan), galat dikelompokkan per bulan.
Sel sama dengan uji.py.

HASIL (29 Okt 2026) -- R2 250h terhadap indeks rata-rata-sama emiten likuid.
Sebaran semua emiten-hari layak: p20 0,037, median 0,122, p80 0,252.
1. Desil 1, ambang tetap, 60 hari (CARI / UJI / silang B13-19 / silang A20-26):
     R2 < 0,05  abs -16,7 / -12,5 / -19,6 / -16,2%; alfa -13,7 / -10,6 / -17,0 / -14,5
                (t -4,9 / -5,4 / -3,4 / -8,0); naik 27-32%; jatuh lagi >=20%: 36-43%
     R2 >= 0,15 abs -1,1 / +0,7 / +2,7 / +6,2%; alfa +1,8 / +0,2 / +2,7 / +1,3 (n.s.);
                naik 46-50%; jatuh lagi >=20%: 15-21%
   Alfa per tahun R2<0,05 negatif 13/14 tahun. Portofolio 10 slot 60h:
   desil 1 + R2<0,05 CAGR -26,4% (DD -98,7%); desil 1 + R2>=0,15 +3,2%.
   => "Desil 1 = hindari" sebenarnya "desil 1 yang JALAN SENDIRI = hindari";
      desil 1 yang ikut pasar ~ pasar.
2. Jatuh Dalam, sama: R2<0,05 alfa -13 s.d. -28% (t -3,3 s.d. -8,2), R2>=0,15
   alfa +6,5 / +4,1 / +4,3 / +6,8 (t 3,5 / 2,1 / 0,8 / 4,3), abs +4,7 s.d. +11,5%,
   naik 58-67%, positif 10/12 tahun. Portofolio: JD+R2>=0,15 CAGR +7,6% (2013-19),
   +6,8% (2020-26), +7,3% semua, DD -45,5%, 158 transaksi; JD semua -18,3%;
   beli-semua likuid +4,8%, IHSG +2,6%. Jauh di bawah Tembus Basis+TS10.
3. Pemeriksaan (cmd_kokoh, OLS gabungan per sel, galat per bulan, desil 1):
   R2 tetap +13 s.d. +30 (t 2,6-5,2) dengan likuiditas+diam+vol20; MENANG
   lawan volatilitas sisa (idio n.s., jadi bukan puzzle IVOL); tanpa emiten
   sering diam +15 s.d. +27 (t 2,1-5,0); R2 120h +11 s.d. +25 (t 2,3-5,1).
   Semua hari layak: R2 rendah juga kalah (alfa negatif 13/14 tahun) tapi
   kira-kira sepertiganya (Q1 alfa -4,7 s.d. -7,3% vs -13 s.d. -25% di
   desil 1) -- efeknya terkumpul di emiten yang SEDANG jatuh.
4. Tembus Basis TIDAK terbantu R2 (menu_per_saham exante): R2 rendah bukan
   berarti emiten jelek -- tembusnya tetap jalan. Yang bahaya jatuhnya.
BATAS: arah R2 terlihat di menu_per_saham exante (keempat sel) SEBELUM
ambang 0,05/0,15 dipilih (dari sebaran, bukan dari hasil), jadi ini bukan
uji buta -- perlu jurnal maju. Survivorship: emiten delisting tidak ada di
Yahoo; mereka lebih mungkin di kelompok R2 rendah, jadi bias ini MENGECILKAN
temuan sisi hindari.

PEMAKAIAN: python -m website.riset_pola_naik.jatuh_sendiri [kokoh|ambang|portofolio]
"""
import os
import warnings

import numpy as np
import pandas as pd

from . import keluar as KL
from . import menu_per_saham as MP
from . import uji

warnings.filterwarnings('ignore')


def siapkan():
    p = uji.muat()
    MP.sinyal(p)                         # kolom desil
    cb = pd.read_pickle(MP.CIRI_CACHE)   # ciri 250h s.d. hari t (dibuat menu_per_saham exante)
    p = p.merge(cb[['ticker', 'date', 'beta', 'r2', 'idio', 'diam', 'vr10']], on=['ticker', 'date'], how='left')
    pasar = MP.pasar_lengkap(p)
    # log return pasar dari close t+1 s.d. close t+61 (jendela fwd60)
    kal = pasar.index
    pos = pd.Series(np.arange(len(kal)), index=kal)
    i = p['date'].map(pos).to_numpy()
    ok = np.isfinite(i)
    m60 = np.full(len(p), np.nan)
    ii = i[ok].astype(int)
    a, b = ii + 1, ii + 61
    v = (a < len(kal)) & (b < len(kal))
    tmp = np.full(len(ii), np.nan)
    tmp[v] = pasar.to_numpy()[b[v]] - pasar.to_numpy()[a[v]]
    m60[ok] = tmp
    p['m60'] = m60
    p['lr60'] = np.log1p(p['fwd60'])
    p['vs_pasar'] = p['lr60'] - p['b_lr60']
    p['alfa'] = p['lr60'] - p['beta'] * p['m60']
    p['log_nilai'] = np.log(p['medval20'].clip(lower=1))
    return p


def kuintil_tabel(ev, kol_hasil):
    rows = []
    for sn, (h, per) in {'CARI (A 13-19)': (0, 1), 'UJI (B 20-26)': (1, 2),
                         'silang (B 13-19)': (1, 1), 'silang (A 20-26)': (0, 2)}.items():
        x = ev[(ev['half'] == h) & (ev['period'] == per)].dropna(subset=['r2', kol_hasil])
        if len(x) < 100:
            rows.append({'sel': sn})
            continue
        x['q'] = pd.qcut(x['r2'].rank(method='first'), 5, labels=False) + 1
        r = {'sel': sn, 'n': len(x)}
        for q, g in x.groupby('q'):
            r['Q%d' % q] = round((np.exp(g[kol_hasil].mean()) - 1) * 100, 1)
        a, b = x[x['q'] == 5], x[x['q'] == 1]
        r['Q5-Q1'] = round(r['Q5'] - r['Q1'], 1)
        r['t'] = round(MP.t_beda(a[kol_hasil].to_numpy(), a['month'].astype(str).to_numpy(),
                                 b[kol_hasil].to_numpy(), b['month'].astype(str).to_numpy()), 1)
        rows.append(r)
    return pd.DataFrame(rows).set_index('sel')


def regresi(ev, kol_hasil, cols=('r2', 'log_nilai', 'diam', 'vol20')):
    """Koefisien per bulan (Fama-MacBeth sederhana) dari peringkat -0,5..0,5; t dari deret bulanan."""
    x = ev.dropna(subset=list(cols) + [kol_hasil])
    hasil = []
    for _m, g in x.groupby('month'):
        if len(g) < 15:
            continue
        A = np.column_stack([np.ones(len(g))] + [g[c].rank(pct=True).to_numpy() - 0.5 for c in cols])
        hasil.append(np.linalg.lstsq(A, g[kol_hasil].to_numpy(), rcond=None)[0][1:])
    h = np.array(hasil)
    if len(h) < 12:
        return {}
    return {c: '%+.1f (t %+.1f)' % (h[:, k].mean() * 100, h[:, k].mean() / h[:, k].std() * np.sqrt(len(h)))
            for k, c in enumerate(cols)}


def main():
    p = siapkan()
    e = p['elig']
    grup = {'desil 1 Kecondongan': e & (p['desil'] == 1),
            'Jatuh Dalam (dd60<=-40%, rentang20>=25%)': e & (p['dd60'] <= -0.40) & (p['range20'] >= 0.25),
            'SEMUA hari layak': e}
    pd.set_option('display.width', 220)
    for nama, m in grup.items():
        ev = uji.jeda(p[m.fillna(False)])
        print('\n' + '=' * 110 + '\n%s: %d kejadian\n' % (nama, len(ev)) + '=' * 110)
        for kol, judul in (('vs_pasar', 'vs pasar hari yang sama (60h, %)'),
                           ('alfa', 'ALFA setelah beta (60h, %)')):
            print('-- kuintil R2 (Q1 = paling "jalan sendiri"), %s' % judul)
            print(kuintil_tabel(ev, kol).to_string())
        print('-- regresi ALFA per bulan (selisih peringkat atas - bawah, %%/60h): ')
        rows = []
        for sn, (h, per) in {'CARI (A 13-19)': (0, 1), 'UJI (B 20-26)': (1, 2), 'silang (B 13-19)': (1, 1),
                             'silang (A 20-26)': (0, 2)}.items():
            r = regresi(ev[(ev['half'] == h) & (ev['period'] == per)], 'alfa')
            r['sel'] = sn
            rows.append(r)
        print(pd.DataFrame(rows).set_index('sel').to_string())
    # hasil absolut desil 1 per kuintil R2 (untung/rugi, bukan cuma relatif)
    ev = uji.jeda(p[grup['desil 1 Kecondongan'].fillna(False)]).dropna(subset=['r2', 'lr60'])
    ev['q'] = ev.groupby('period')['r2'].transform(lambda s: pd.qcut(s.rank(method='first'), 5, labels=False) + 1)
    print('\nDesil 1, hasil ABSOLUT 60h (majemuk %) dan porsi naik, per kuintil R2 x periode:')
    t = ev.groupby(['period', 'q']).apply(lambda g: '%+.1f%% / naik %.0f%% / -20%% atau lebih %.0f%%'
                                          % ((np.exp(g['lr60'].mean()) - 1) * 100, (g['lr60'] > 0).mean() * 100,
                                             (g['fwd60'] <= -0.20).mean() * 100)).unstack()
    print(t.to_string())
    tahunan(p, grup)


def gabung_ols(ev, kol_hasil, cols):
    """OLS gabungan, peringkat persentil per bulan (-0,5..0,5), galat dikelompokkan per bulan."""
    x = ev.dropna(subset=list(cols) + [kol_hasil]).copy()
    if len(x) < 150:
        return {}
    Xs = [np.ones(len(x))] + [x.groupby('month')[c].rank(pct=True).to_numpy() - 0.5 for c in cols]
    X = np.column_stack(Xs)
    y = x[kol_hasil].to_numpy()
    XtX_inv = np.linalg.inv(X.T @ X)
    b = XtX_inv @ X.T @ y
    e = y - X @ b
    g = x['month'].astype(str).to_numpy()
    meat = np.zeros((X.shape[1], X.shape[1]))
    for _k, idx in pd.Series(np.arange(len(x))).groupby(g):
        s = X[idx.to_numpy()].T @ e[idx.to_numpy()]
        meat += np.outer(s, s)
    se = np.sqrt(np.diag(XtX_inv @ meat @ XtX_inv))
    return {c: '%+.1f (t %+.1f)' % (b[k + 1] * 100, b[k + 1] / se[k + 1]) for k, c in enumerate(cols)}


def r2_pendek(p, pasar, w=120):
    mkt = pasar.diff()
    out = []
    for t, d in p.groupby('ticker', sort=False):
        lr = np.log(d['close']).diff()
        lr[d['ret1'].abs() > 0.45] = np.nan
        lr.index = d['date'].to_numpy()
        m = mkt.reindex(lr.index)
        cv = lr.rolling(w, min_periods=100).cov(m)
        r2 = cv * cv / (lr.rolling(w, min_periods=100).var() * m.rolling(w, min_periods=100).var())
        out.append(pd.Series(r2.to_numpy(), index=d.index))
    return pd.concat(out)


def cmd_kokoh():
    """Pemeriksaan sesudah hasil utama dilihat: R2 vs volatilitas sisa (puzzle IVOL),
    tanpa emiten yang sering diam, dan R2 120 hari."""
    p = siapkan()
    p['r2_120'] = r2_pendek(p, MP.pasar_lengkap(p))
    e = p['elig']
    grup = {'desil 1': e & (p['desil'] == 1),
            'Jatuh Dalam': e & (p['dd60'] <= -0.40) & (p['range20'] >= 0.25),
            'semua hari layak': e}
    sel = {'CARI (A 13-19)': (0, 1), 'UJI (B 20-26)': (1, 2), 'silang (B 13-19)': (1, 1), 'silang (A 20-26)': (0, 2)}
    pd.set_option('display.width', 250)
    for nama, m in grup.items():
        ev = uji.jeda(p[m.fillna(False)])
        print('\n' + '=' * 120 + '\n%s (%d kejadian): OLS gabungan ALFA 60h, koefisien = selisih peringkat atas-bawah (%%)\n'
              % (nama, len(ev)) + '=' * 120)
        for judul, cols, filt in (
                ('R2 + likuiditas + diam + vol20', ('r2', 'log_nilai', 'diam', 'vol20'), None),
                ('R2 vs volatilitas SISA (idio)', ('r2', 'idio', 'log_nilai'), None),
                ('tanpa emiten sering diam (diam 250h > 20%)', ('r2', 'log_nilai', 'vol20'), ev['diam'] <= 0.20),
                ('R2 120 hari (bukan 250)', ('r2_120', 'log_nilai', 'diam', 'vol20'), None)):
            rows = []
            for sn, (h, per) in sel.items():
                d = ev[(ev['half'] == h) & (ev['period'] == per)]
                if filt is not None:
                    d = d[filt.reindex(d.index).fillna(False)]
                r = gabung_ols(d, 'alfa', cols)
                r['sel'] = sn
                r['n'] = len(d)
                rows.append(r)
            print('-- ' + judul)
            print(pd.DataFrame(rows).set_index('sel').to_string())


AMBANG = (0.05, 0.15)     # R2 250h; dipilih dari sebaran SEMUA hari layak, bukan dari hasil


def tahunan(p, grup):
    """Per tahun sinyal, ambang R2 tetap (bukan kuintil per sel) supaya bisa dipakai di halaman."""
    x = p.loc[p['elig'] & p['r2'].notna(), 'r2']
    print('\nSebaran R2 250h semua emiten-hari layak: p20 %.3f, median %.3f, p80 %.3f'
          % (x.quantile(0.2), x.median(), x.quantile(0.8)))
    for nama in ('desil 1 Kecondongan', 'Jatuh Dalam (dd60<=-40%, rentang20>=25%)', 'SEMUA hari layak'):
        ev = uji.jeda(p[grup[nama].fillna(False)]).dropna(subset=['r2', 'alfa'])
        ev['year'] = ev['date'].dt.year
        ev['kel'] = np.where(ev['r2'] < AMBANG[0], 'R2<%.2f' % AMBANG[0],
                             np.where(ev['r2'] < AMBANG[1], 'tengah', 'R2>=%.2f' % AMBANG[1]))
        f = lambda g: (np.exp(g['alfa'].mean()) - 1) * 100
        t = ev.groupby(['kel', 'year']).apply(f).unstack().round(1)
        n = ev.groupby('kel').size()
        t['n'] = n
        t['tahun negatif'] = (ev.groupby(['kel', 'year']).apply(f).unstack() < 0).sum(1).astype(str) + '/' + \
            ev.groupby(['kel', 'year']).apply(f).unstack().notna().sum(1).astype(str)
        print('\n%s -- ALFA 60h per tahun sinyal (%%), ambang R2 tetap:' % nama)
        print(t.to_string())
        a = ev.groupby('kel').apply(lambda g: '%+.1f%% abs, naik %.0f%%, jatuh >=20%% %.0f%%'
                                    % ((np.exp(g['lr60'].mean()) - 1) * 100, (g['lr60'] > 0).mean() * 100,
                                       (g['fwd60'] <= -0.2).mean() * 100))
        print(a.to_string())


def cmd_ambang():
    """Ambang R2 tetap per sel: hasil absolut, alfa, porsi naik, porsi jatuh >= 20%."""
    p = siapkan()
    e = p['elig']
    grup = {'desil 1': e & (p['desil'] == 1),
            'Jatuh Dalam': e & (p['dd60'] <= -0.40) & (p['range20'] >= 0.25)}
    sel = {'CARI (A 13-19)': (0, 1), 'UJI (B 20-26)': (1, 2), 'silang (B 13-19)': (1, 1), 'silang (A 20-26)': (0, 2)}
    pd.set_option('display.width', 250)
    for nama, m in grup.items():
        ev = uji.jeda(p[m.fillna(False)]).dropna(subset=['r2', 'alfa'])
        ev['kel'] = np.where(ev['r2'] < AMBANG[0], '1 R2<0,05 (jalan sendiri)',
                             np.where(ev['r2'] < AMBANG[1], '2 tengah', '3 R2>=0,15 (ikut pasar)'))
        rows = []
        for k, g0 in ev.groupby('kel'):
            r = {'kelompok': k}
            for sn, (h, per) in sel.items():
                g = g0[(g0['half'] == h) & (g0['period'] == per)]
                r[sn] = ('abs %+.1f%% | alfa %+.1f%% (t %+.1f) | naik %.0f%% | -20%% %.0f%% | n %d'
                         % ((np.exp(g['lr60'].mean()) - 1) * 100, (np.exp(g['alfa'].mean()) - 1) * 100,
                            uji.t_klaster(g['alfa'].to_numpy(), g['month'].astype(str).to_numpy()),
                            (g['lr60'] > 0).mean() * 100, (g['fwd60'] <= -0.2).mean() * 100, len(g))
                         if len(g) >= 30 else 'n %d' % len(g))
            rows.append(r)
        print('\n%s -- 60 hari sesudah sinyal, ambang R2 250h tetap' % nama)
        print(pd.DataFrame(rows).set_index('kelompok').T.to_string())


def cmd_portofolio():
    """Portofolio 10 slot tahan 60 hari (simulasi.py), urutan likuid + median 10 urutan acak."""
    from . import simulasi as SM
    p = siapkan()
    ps = SM.Pasar(p)
    # pembanding beli-semua TANPA syarat traded30 (Pasar.ew bolong di libur panjang 2017-2019)
    ok = ((p['medval20'] >= uji.MIN_NILAI) & (p['close'] >= uji.MIN_HARGA) & (p['hist'] >= 260)
          & (p['bad_back60'] == 0))
    q = p[['ticker', 'date', 'ret1']].assign(ok=ok).sort_values(['ticker', 'date'])
    q['ok_k'] = q.groupby('ticker')['ok'].shift(1).fillna(False).astype(bool)
    ew = q[q['ok_k'] & (q['ret1'].abs() <= 0.45)].groupby('date')['ret1'].mean()
    e = p['elig']
    jd = e & (p['dd60'] <= -0.40) & (p['range20'] >= 0.25)
    d1 = e & (p['desil'] == 1)
    S = {'Jatuh Dalam (semua)': jd,
         'Jatuh Dalam + R2>=0,15': jd & (p['r2'] >= AMBANG[1]),
         'Jatuh Dalam + R2<0,05': jd & (p['r2'] < AMBANG[0]),
         'desil 1 + R2>=0,15': d1 & (p['r2'] >= AMBANG[1]),
         'desil 1 + R2<0,05': d1 & (p['r2'] < AMBANG[0])}
    for mulai, akhir in (('2013-01-01', '2019-12-31'), ('2020-01-01', '2026-06-01'), ('2013-01-01', '2026-06-01')):
        rows = []
        for nama, m in S.items():
            ev = uji.jeda(p[m.fillna(False)])
            kurva, tr = SM.simulasi(ps, ev, mulai, akhir)
            cagr, dd, _ = SM.ringkas(kurva)
            acak = [SM.ringkas(SM.simulasi(ps, ev, mulai, akhir, urutan='acak', seed=s)[0])[0] for s in range(10)]
            r = np.array([x[0] for x in tr])
            rows.append({'strategi': nama, 'CAGR%': round(cagr, 1), 'acak median': round(float(np.median(acak)), 1),
                         'maxDD%': round(dd, 1), 'transaksi': len(r), 'win%': round((r > 0).mean() * 100, 0)})
        b = (1 + ew.loc[mulai:akhir]).cumprod()
        cagr, dd, _ = SM.ringkas(b)
        rows.append({'strategi': 'PEMBANDING beli semua likuid (tanpa ongkos)', 'CAGR%': round(cagr, 1), 'maxDD%': round(dd, 1)})
        if ps.ihsg is not None:
            cagr, dd, _ = SM.ringkas(ps.ihsg.loc[mulai:akhir].dropna())
            rows.append({'strategi': 'PEMBANDING IHSG', 'CAGR%': round(cagr, 1), 'maxDD%': round(dd, 1)})
        print('\n=== %s -> %s | 10 slot, tahan 60 hari, ongkos pulang-pergi 0,9%% ===' % (mulai, akhir))
        print(pd.DataFrame(rows).set_index('strategi').to_string())


def cmd_cek_setara():
    """kecondongan.ukur_pasar (halaman: Summary 2026 + riwayat Yahoo) harus memberi
    R2 yang sama dengan riset (Yahoo penuh) di tanggal yang ada di dua-duanya.
    Tidak identik -- sumber harganya beda (Summary tidak disesuaikan dividen,
    riwayat halaman baru mulai Jun 2024) -- tapi kelompoknya harus hampir selalu sama."""
    from .. import kecondongan as KC
    from ..tembus_basis import _panel
    panel = _panel()
    live = {s: d['r2'] for s, d in KC.ukur_pasar(panel).items()}
    cb = pd.read_pickle(MP.CIRI_CACHE)
    akhir = cb['date'].max()
    rows = []
    for tgl in sorted(cb['date'].unique())[-60::20] + [akhir]:
        tgl = pd.Timestamp(tgl)
        r = cb[(cb['date'] == tgl) & cb['r2'].notna()].set_index('ticker')['r2']
        lv = pd.Series({s: float(x.get(tgl, np.nan)) for s, x in live.items()}).dropna()
        t = r.index.intersection(lv.index)
        a, b = r[t].astype(float), lv[t]
        ka = a.map(KC.kelompok_r2)
        kb = b.map(KC.kelompok_r2)
        rows.append({'tanggal': tgl.date(), 'emiten': len(t), 'rho': round(a.corr(b, method='spearman'), 3),
                     'median |beda|': round(float((a - b).abs().median()), 4),
                     'kelompok sama %': round(float((ka == kb).mean() * 100), 1),
                     'beda >1 kelompok': int(((ka == 'sendiri') & (kb == 'pasar') | (ka == 'pasar') & (kb == 'sendiri')).sum())})
    print(pd.DataFrame(rows).to_string(index=False))


if __name__ == '__main__':
    import sys
    perintah = sys.argv[1] if len(sys.argv) > 1 else 'utama'
    {'kokoh': cmd_kokoh, 'ambang': cmd_ambang, 'portofolio': cmd_portofolio,
     'cek-setara': cmd_cek_setara}.get(perintah, main)()
