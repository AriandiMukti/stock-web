"""
Studi event: informasi BARU di luar bentuk harga (23 Sep 2026).

KENAPA
Tiga cara menambang pola harga sampai ke kesimpulan yang sama (lihat
analog.py): arah dari harga itu kecil. Event bertanggal jelas membawa
informasi yang tidak ada di chart -- dan tanggalnya diketahui, jadi tidak
ada "sinyal yang baru kelihatan sesudah terjadi".

YANG DIUJI (semua dilaporkan, termasuk yang gagal)
  1. DIVIDEN (tanggal ex, Yahoo): hasil sesudah ex-date, dan run-up 20 hari
     sebelumnya; per besar imbal hasil.
  2. PEMECAHAN SAHAM (Yahoo "Stock Splits"): split >= 2x, reverse split, dan
     rasio ganjil 1-2x (Yahoo memakai kolom yang sama untuk saham bonus dan
     rights issue).
  3. ARUS KEPEMILIKAN KSEI bulanan (arsip Des 2012 - sekarang, lihat
     sumber_baru.py): perubahan porsi asing, institusi lokal, dan individu
     sebulan, serta levelnya.
Yang TIDAK bisa diuji dari sini: masuk/keluar indeks LQ45/IDX30 (tidak ada
riwayat konstituen yang bisa diunduh) dan rights issue secara langsung.

PROTOKOL (sama dengan uji.py)
  Pencarian = emiten A (md5) x 2013-2019, validasi = emiten B x 2020-2026.
  Hari event = hari bursa pertama >= tanggal event; masuk di close hari
  bursa SESUDAHNYA; hasil 20/60 hari dimajemukkan, dikurangi emiten layak
  lain pada hari yang sama; nilai t dikelompokkan per bulan. Hanya emiten
  layak (elig) di hari event.

HASIL (23 Sep 2026)
===================
1. DIVIDEN (1.432 ex-date emiten layak 2013-2026)
   Sesudah ex-date: +1,1% vs pasar per 60 hari (t 1,8) -- tidak kokoh:
   pencarian +1,0% (t 0,7), validasi +2,1% (t 2,1), silang A 2020-26 0,0%.
   Positif 11/14 tahun tapi kecil. TIDAK ADA drift sesudah ex-date yang
   bisa dipegang, di imbal hasil mana pun.
   Yang menarik justru SEBELUM ex-date dividen besar: imbal hasil >= 7%
   naik +4,5% vs pasar dalam 20 hari sebelum ex (t 4,5, n=129); 4-7%
   +1,4% (t 2,1). TAPI: (a) cuma ada cukup event di 2020-2026 (dua sel,
   +5,9% dan +3,4%), sel 2013-2019 terlalu kecil; (b) besar dividen baru
   diketahui saat diumumkan, biasanya < 20 hari sebelum ex -- sebagian
   kenaikan itu terjadi sebelum ada yang bisa tahu imbal hasilnya. Belum
   bisa dijadikan aturan.
2. PEMECAHAN SAHAM (86 event layak): split >= 2x naik +4,3% vs pasar 20
   hari SEBELUM (t 2,6) lalu -4,7% dalam 60 hari SESUDAH (t -1,4, n=65).
   Arahnya "naik menjelang, turun sesudah", tapi sampelnya terlalu kecil
   untuk dipecah per sel -- belum bukti.
3. ARUS KEPEMILIKAN KSEI (18.436 emiten-bulan, arsip Des 2012-Mei 2013 dan
   Des 2017-Sep 2026)
   - PERUBAHAN sebulan (asing masuk/keluar, individu, institusi lokal,
     reksa dana): IC ~0 di semua sel. "Ikuti asing" bulanan tidak ada isinya.
   - LEVEL: porsi asing (+0,060 validasi) dan reksa dana (+0,058) memang
     condong positif, porsi individu negatif -- tapi setelah dinetralkan
     dari likuiditas, volatilitas, jarak puncak, dan ret120, sisanya NOL di
     validasi 2020-2026 (asing +0,019 t 1,3; reksa dana 0,000; individu
     0,000). Levelnya cuma wakil ukuran & ketenangan yang sudah ditangkap
     Skor Kecondongan. Di 2013-2019 sempat kuat (asing +0,112, individu
     -0,117) -- periode itu cuma ~30 bulan arsip.
Kesimpulan: dari tiga sumber baru, tidak ada yang menambah informasi arah
yang lolos luar sampel. Yang tersisa: run-up dividen besar (belum bisa
dipakai) dan split (sampel kecil).

PEMAKAIAN (dari <project>/)
    python -m website.riset_pola_naik.event dividen
    python -m website.riset_pola_naik.event split
    python -m website.riset_pola_naik.event kepemilikan
"""
import os
import pickle
import sys
import warnings

import numpy as np
import pandas as pd

from . import panel as PN
from . import uji as U

warnings.filterwarnings('ignore')

SEL = {'pencarian A 2013-19': (0, 1), 'validasi B 2020-26': (1, 2),
       'silang B 2013-19': (1, 1), 'silang A 2020-26': (0, 2)}


def muat():
    p = U.muat()
    p = p.sort_values(['ticker', 'date']).reset_index(drop=True)
    # Pembanding untuk run-up SEBELUM event: rata-rata log return 20 hari
    # emiten layak pada hari yang sama.
    p['lret20'] = np.log1p(p['ret20'])
    b = p[p['elig']].groupby('date')['lret20'].mean().rename('b_lret20')
    p = p.merge(b, left_on='date', right_index=True, how='left')
    p['pre_exc20'] = p['lret20'] - p['b_lret20']
    p['year'] = p['date'].dt.year
    return p


def petakan(p, ev):
    """ev: DataFrame(ticker, tanggal, ...) -> baris panel di hari event
    (hari bursa pertama >= tanggal), plus run-up 20 hari sampai sehari
    sebelum event."""
    idx = {t: g.index.to_numpy() for t, g in p.groupby('ticker', sort=False)}
    tgl = {t: p.loc[i, 'date'].to_numpy() for t, i in idx.items()}
    baris, pre = [], []
    for r in ev.itertuples():
        if r.ticker not in idx:
            baris.append(-1); pre.append(np.nan)
            continue
        j = np.searchsorted(tgl[r.ticker], np.datetime64(r.tanggal))
        if j >= len(idx[r.ticker]) or j == 0:
            baris.append(-1); pre.append(np.nan)
            continue
        baris.append(idx[r.ticker][j])
        pre.append(p.at[idx[r.ticker][j - 1], 'pre_exc20'])
    ev = ev.copy()
    ev['baris'] = baris
    ev['pre20'] = pre
    ev = ev[ev['baris'] >= 0]
    kol = ['ticker', 'date', 'elig', 'half', 'period', 'month', 'year', 'fwd20', 'fwd60', 'fp60',
           'b_lr20', 'b_lr60', 'b_p10', 'b_win', 'b_p20_60', 'b_fpup', 'b_fpdn', 'medval20',
           'dd250', 'vol20', 'ret120']
    out = p.loc[ev['baris'], kol].reset_index(drop=True)
    for k in ev.columns:
        if k not in ('ticker', 'baris'):
            out[k] = ev[k].to_numpy()
    return out[out['elig']]


def ringkas(ev):
    s = U.statistik(ev) if len(ev) else {'n': 0}
    pre = ev['pre20'].dropna()
    return {
        'n': s.get('n', 0),
        'sebelum 20h %': (np.exp(pre.mean()) - 1) * 100 if len(pre) >= 30 else np.nan,
        't sebelum': U.t_klaster(pre, ev.loc[pre.index, 'month'].astype(str)) if len(pre) >= 30 else np.nan,
        'sesudah 20h %': s.get('exc20', np.nan), 't20': s.get('t20', np.nan),
        'sesudah 60h %': s.get('exc60', np.nan), 't60': s.get('t60', np.nan),
        '+10% dulu': s.get('fpup', np.nan), 'pemb +10%': s.get('fpup_base', np.nan),
    }


def tabel(ev, kelompok, judul):
    print('\n  ' + judul)
    rows = []
    for nama, g in kelompok(ev):
        for sel, (h, per) in [('semua', (None, None))] + list(SEL.items()):
            d = g if h is None else g[(g['half'] == h) & (g['period'] == per)]
            if len(d) < 30:
                continue
            r = ringkas(d)
            r.update({'kelompok': nama, 'sel': sel})
            rows.append(r)
    if not rows:
        print('    (sampel terlalu kecil)')
        return
    t = pd.DataFrame(rows).set_index(['kelompok', 'sel'])
    print(t.round(2).to_string())


def per_tahun(ev, judul):
    ok = ev[ev['fwd60'].notna()]
    th = ok.groupby('year').apply(lambda g: (np.exp((np.log1p(g['fwd60']) - g['b_lr60']).mean()) - 1) * 100
                                  if len(g) >= 15 else np.nan).dropna()
    print('  %s -- vs pasar 60h per tahun: %s | positif %d/%d'
          % (judul, ' '.join('%d:%+.1f' % (y, v) for y, v in th.items()), (th > 0).sum(), len(th)))


# ---------------------------------------------------------------------------
def cmd_dividen(p):
    d = pickle.load(open(os.path.join(PN.RESEARCH_CACHE, 'aksi_korporasi.pkl'), 'rb'))['aksi']
    rows = []
    for t, a in d.items():
        if 'Dividends' not in a:
            continue
        for tgl, v in a['Dividends'].items():
            if v and v > 0:
                rows.append((t, pd.Timestamp(tgl).normalize(), float(v)))
    ev = pd.DataFrame(rows, columns=['ticker', 'tanggal', 'dividen'])
    ev = ev[(ev['tanggal'] >= '2013-01-01')]

    # Imbal hasil = dividen / close MENTAH sehari sebelum ex (sumber_baru mentah).
    mentah_path = os.path.join(PN.RESEARCH_CACHE, 'harga_mentah_close.pkl')
    if os.path.exists(mentah_path):
        mentah = pickle.load(open(mentah_path, 'rb'))
        yl = []
        for r in ev.itertuples():
            c = mentah.get(r.ticker)
            if c is None:
                yl.append(np.nan)
                continue
            sebelum = c[c.index < r.tanggal]
            yl.append(r.dividen / float(sebelum.iloc[-1]) * 100 if len(sebelum) and sebelum.iloc[-1] > 0 else np.nan)
        ev['yield'] = yl
    else:
        ev['yield'] = np.nan
        print('  (harga_mentah_close.pkl belum ada -- imbal hasil tidak dihitung)')
    ev = petakan(p, ev)
    print('\n' + '=' * 78)
    print('DIVIDEN: %d ex-date emiten layak 2013-2026' % len(ev))
    print('=' * 78)
    tabel(ev, lambda e: [('semua dividen', e)], 'Semua ex-date (masuk close hari bursa sesudah ex-date)')
    per_tahun(ev, 'semua dividen')
    if ev['yield'].notna().any():
        bins = [(0, 2, '< 2%'), (2, 4, '2-4%'), (4, 7, '4-7%'), (7, 1e9, '>= 7%')]
        tabel(ev, lambda e: [(lbl, e[(e['yield'] >= lo) & (e['yield'] < hi)]) for lo, hi, lbl in bins],
              'Per imbal hasil dividen (dividen / close mentah sehari sebelum ex)')
        tinggi = ev[ev['yield'] >= 4]
        per_tahun(tinggi, 'imbal hasil >= 4%')


def cmd_split(p):
    d = pickle.load(open(os.path.join(PN.RESEARCH_CACHE, 'aksi_korporasi.pkl'), 'rb'))['aksi']
    rows = []
    for t, a in d.items():
        if 'Stock Splits' not in a:
            continue
        for tgl, v in a['Stock Splits'].items():
            if v and v > 0 and v != 1:
                rows.append((t, pd.Timestamp(tgl).normalize(), float(v)))
    ev = pd.DataFrame(rows, columns=['ticker', 'tanggal', 'rasio'])
    ev = petakan(p, ev[ev['tanggal'] >= '2013-01-01'])
    print('\n' + '=' * 78)
    print('PEMECAHAN SAHAM: %d event emiten layak 2013-2026' % len(ev))
    print('=' * 78)
    kel = lambda e: [('split >= 2x', e[e['rasio'] >= 2]),
                     ('rasio ganjil 1-2x (bonus / rights)', e[(e['rasio'] > 1) & (e['rasio'] < 2)]),
                     ('reverse split < 1x', e[e['rasio'] < 1])]
    tabel(ev, kel, 'Per jenis (sampel kecil -- sel dengan < 30 event tidak ditampilkan)')
    per_tahun(ev[ev['rasio'] >= 2], 'split >= 2x')


# ---------------------------------------------------------------------------
def cmd_kepemilikan(p):
    from .sumber_baru import muat_ksei
    bulan = muat_ksei()
    print('\n' + '=' * 78)
    print('ARUS KEPEMILIKAN KSEI: %d bulan arsip (%s .. %s)' % (len(bulan), min(bulan), max(bulan)))
    print('=' * 78)
    rows = []
    for kunci, isi in bulan.items():
        tgl = pd.Timestamp(isi['as_of'])
        for t, s in isi['securities'].items():
            lok, asg = s['local'], s['foreign']
            total = s['local_total'] + s['foreign_total']
            if total <= 0:
                continue
            rows.append({'ticker': t, 'as_of': tgl,
                         'asing': s['foreign_total'] / total * 100,
                         'individu': (lok['ID'] + asg['ID']) / total * 100,
                         'institusi_lokal': (lok['IS'] + lok['PF'] + lok['MF'] + lok['IB']) / total * 100,
                         'reksa_dana': (lok['MF'] + asg['MF']) / total * 100})
    k = pd.DataFrame(rows).sort_values(['ticker', 'as_of'])
    g = k.groupby('ticker')
    for kol in ('asing', 'individu', 'institusi_lokal', 'reksa_dana'):
        k['d_' + kol] = g[kol].diff()
    k['jarak'] = g['as_of'].diff().dt.days
    k = k[k['jarak'].between(20, 45)]            # hanya perubahan antar bulan berurutan
    # Arsip KSEI terbit beberapa hari SESUDAH tanggalnya: event digeser ke
    # hari bursa ke-7 sesudah tanggal arsip supaya tidak memakai data yang
    # belum bisa diunduh.
    kal = np.sort(p['date'].unique())
    posisi = np.searchsorted(kal, k['as_of'].to_numpy()) + 6
    k = k[posisi < len(kal)]
    k['tanggal'] = kal[posisi[posisi < len(kal)]]
    ev = petakan(p, k.drop(columns=['as_of']))
    print('  %d emiten-bulan layak dengan perubahan bulanan' % len(ev))

    ev['exc60'] = np.log1p(ev['fwd60']) - ev['b_lr60']
    ev['exc20'] = np.log1p(ev['fwd20']) - ev['b_lr20']
    print('\n  IC antar emiten per bulan (korelasi peringkat vs hasil sesudahnya), t dari bulan:')
    rows = []
    for kol in ('d_asing', 'd_individu', 'd_institusi_lokal', 'd_reksa_dana',
                'asing', 'individu', 'institusi_lokal', 'reksa_dana'):
        r = {'ukuran': kol}
        for sel, (h, per) in [('semua', (None, None))] + list(SEL.items()):
            d = ev if h is None else ev[(ev['half'] == h) & (ev['period'] == per)]
            for hz in ('exc20', 'exc60'):
                x = d[['month', kol, hz]].dropna()
                ic = x.groupby('month').apply(lambda gg: gg[kol].corr(gg[hz], method='spearman')
                                              if len(gg) >= 20 else np.nan).dropna()
                t = ic.mean() / (ic.std(ddof=1) / np.sqrt(len(ic))) if len(ic) > 5 else np.nan
                r['%s %s' % (sel.split()[0], hz[-2:])] = '%+.3f (%+.1f)' % (ic.mean(), t) if len(ic) else '-'
        rows.append(r)
    print(pd.DataFrame(rows).set_index('ukuran').to_string())

    # Level kepemilikan berkorelasi dengan ukuran, likuiditas, dan
    # volatilitas. Sisa IC setelah dikurangi keempatnya = informasi baru.
    print('\n  IC LEVEL setelah dinetralkan dari likuiditas (medval20), volatilitas, dekat puncak, ret120:')
    ev['log_nilai'] = np.log(ev['medval20'])
    terhadap = ['log_nilai', 'vol20', 'dd250', 'ret120']

    def sisa(g, kol):
        if len(g) < 25:
            return pd.Series(np.nan, index=g.index)
        A = np.column_stack([np.ones(len(g))] + [g[c].to_numpy() for c in terhadap])
        b = np.linalg.lstsq(A, g[kol].to_numpy(), rcond=None)[0]
        return pd.Series(g[kol].to_numpy() - A @ b, index=g.index)

    rows = []
    for kol in ('asing', 'reksa_dana', 'individu', 'institusi_lokal'):
        r = {'ukuran': kol}
        for sel, (h, per) in [('semua', (None, None))] + list(SEL.items()):
            d = ev if h is None else ev[(ev['half'] == h) & (ev['period'] == per)]
            d = d.dropna(subset=[kol, 'exc60'] + terhadap)
            R = d.groupby('month')[[kol] + terhadap].rank(pct=True)
            R['month'] = d['month']
            d = d.assign(res=R.groupby('month', group_keys=False).apply(lambda g: sisa(g, kol)))
            ic = d.dropna(subset=['res']).groupby('month').apply(
                lambda gg: gg['res'].corr(gg['exc60'], method='spearman') if len(gg) >= 20 else np.nan).dropna()
            t = ic.mean() / (ic.std(ddof=1) / np.sqrt(len(ic))) if len(ic) > 5 else np.nan
            r[sel.split()[0] + ' ' + sel.split()[-1] if sel != 'semua' else 'semua'] = (
                '%+.3f (%+.1f)' % (ic.mean(), t) if len(ic) else '-')
        rows.append(r)
    print(pd.DataFrame(rows).set_index('ukuran').to_string())

    print('\n  Kuintil LEVEL (validasi B 2020-26) -- vs pasar 60h, n:')
    v = ev[(ev['half'] == 1) & (ev['period'] == 2)]
    for kol in ('asing', 'reksa_dana', 'individu'):
        x = v.dropna(subset=[kol, 'exc60']).copy()
        x['q'] = np.ceil(x.groupby('month')[kol].rank(pct=True) * 5).clip(1, 5)
        hs = x.groupby('q')['exc60'].agg(['mean', 'size'])
        print('   %-18s %s' % (kol, '  '.join('Q%d %+.1f%% (%d)' % (q, (np.exp(m) - 1) * 100, n)
                                            for q, (m, n) in hs.iterrows())))

    print('\n  Kuintil perubahan sebulan (validasi B 2020-26) -- vs pasar 60h, n:')
    v = ev[(ev['half'] == 1) & (ev['period'] == 2)]
    for kol in ('d_asing', 'd_individu', 'd_institusi_lokal'):
        x = v.dropna(subset=[kol, 'exc60']).copy()
        x['q'] = np.ceil(x.groupby('month')[kol].rank(pct=True) * 5).clip(1, 5)
        hs = x.groupby('q')['exc60'].agg(['mean', 'size'])
        print('   %-18s %s' % (kol, '  '.join('Q%d %+.1f%% (%d)' % (q, (np.exp(m) - 1) * 100, n)
                                            for q, (m, n) in hs.iterrows())))


def main():
    perintah = sys.argv[1] if len(sys.argv) > 1 else 'semua'
    p = muat()
    if perintah in ('dividen', 'semua'):
        cmd_dividen(p)
    if perintah in ('split', 'semua'):
        cmd_split(p)
    if perintah in ('kepemilikan', 'semua'):
        cmd_kepemilikan(p)


if __name__ == '__main__':
    main()
