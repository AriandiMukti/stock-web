"""
Menebak perubahan MSCI SEBELUM pengumuman (kandidat A1, ARUS_PAKSA_KANDIDAT.md).

KENAPA
  indeks_msci.py: lompatan hari reaksi D1 (+3,0% ST_naik, -4,5% ST_turun)
  tidak bisa diambil karena itu informasi baru. Kalau perubahannya bisa
  ditebak dari ukuran sebelum pengumuman, D1 ikut terambil.

DATA
  Perubahan per review: indeks_msci.kejadian() (PDF MSCI Feb 2012 - Agu 2026).
  Tanggal tiap review (termasuk review TANPA perubahan Indonesia): halaman 1
  tiap PDF. Ukuran: arsip KSEI bulanan (sumber_baru.muat_ksei), jumlah saham x
  harga KSEI (tak disesuaikan, cocok dengan jumlah saham saat itu).
  Likuiditas: medval20 panel uji.muat(). Harga untuk hasil: KB._panel_close()
  (sama dengan indeks_msci.ukur).

DESAIN (didaftar SEBELUM hasil dilihat, 28 Okt 2026)
  Review yang diuji: pengumuman Feb 2018 - Agu 2026 (arsip KSEI ada).
  Arsip dipakai = tanggal arsip terakhir <= pengumuman - 5 hari (akhir bulan
  sebelum bulan review = sekitar tanggal potong harga MSCI).

  KEANGGOTAAN direkonstruksi dari urutan perubahan:
    - kode mentah kejadian pertama sebuah emiten menentukan status awalnya
      (hapus dari ST -> tadinya ST; hapus dari SC -> tadinya SC; selain itu
      bukan anggota), lalu semua review diputar ulang berurutan sejak 2012
    - emiten TANPA kejadian sama sekali sejak 2012 dianggap anggota ST kalau
      kapitalisasinya >= Rp100 T di arsip Des 2017 (BBRI, TLKM, BMRI, ASII,
      BBCA, BBNI, UNTR), selain itu bukan anggota
    - perubahan di luar review kuartalan (IPO, delisting, merger) tak terlihat:
      kejadian yang bertentangan dengan status rekonstruksi dihitung & dilaporkan
  FITUR per emiten (arsip KSEI):
    full = jumlah saham x harga; buang full > Rp2.500 T (harga KSEI rusak)
    ff   = (lembar terkategori - CP lokal - CP asing) / jumlah saham (proksi kasar:
           pemegang pengendali di luar rekening efek tak tercatat, pengendali
           perorangan tetap terhitung float)
    likuid = medval20 x 250 / (full x ff) >= 0,15 (ATVR MSCI)
  SKOR = full / median full anggota ST (untuk ST) atau anggota SC (untuk SC).
  TEBAKAN tiap review (k tetap, apa pun kondisinya):
    ST_naik   : bukan ST, ff >= 0,15, likuid -> 1 skor ST tertinggi
    ST_turun  : anggota ST -> 1 skor ST terendah
    SC_masuk  : bukan anggota mana pun, ff >= 0,15, likuid -> 3 skor SC tertinggi
    SC_keluar : anggota SC -> 3 skor SC terendah
  HASIL (log, dikurangi rata-rata semua emiten tanggal sama):
    masuk = close D0-5 (D0 = hari bursa terakhir <= tanggal pengumuman)
    keD1  = masuk -> close D1 (hari bursa pertama SESUDAH pengumuman)
    keE   = masuk -> close tanggal efektif
  Juga: presisi (tebakan yang benar terjadi) dan AUC skor terhadap kejadian
  sebenarnya di tiap kelompok calon.
  Dua periode: review 2018-2021 vs 2022-2026; t klaster per review.
  LOLOS kalau keD1 atau keE: tanda sama dua periode, |t| gabungan >= 2;
  ST_naik/SC_masuk dipakai beli hanya kalau > +0,4% (biaya).

HASIL (28 Okt 2026, 35 review Feb 2018 - Agu 2026, 0 kejadian bertentangan
dengan rekonstruksi; ST akhir 9 emiten -- yang masuk lewat jalur di luar
review, mis. IPO, tak terlihat):
               presisi  ketangkap   keD1 (t)      keE (t)      benar/salah keD1
  ST_naik  top1  26%      9/16     -0,6 (-0,4)   +1,4 (+0,6)    +2,0 / -1,4
  ST_turun bot1  49%     17/40     -2,2 (-1,9)   -6,0 (-3,1)    -4,9 / +0,5
  SC_masuk top3   3%      3/52     -0,9 (-1,3)   -0,4 (-0,3)
  SC_keluar bot3  3%      3/100    -4,2 (-2,6)   -3,7 (-1,1)    -8,9 / -3,9
  (AUC ~0,9-1,0 tak berarti: calon didominasi ratusan emiten kecil.)
  GAGAL sebagai sinyal BELI: tebakan masuk ST benar cuma 1 dari 4; untung
  yang benar (+2,0%) habis oleh yang salah (-1,4%). SC hampir tak tertebak.
  ST_turun keE "lolos" (dua periode -4,5 / -7,3) TAPI sebagian besar terjadi
  SESUDAH pengumuman -- sudah ditangkap jurnal MSCI (ST_turun jalan D1->E).
  Bagian baru yang cuma bisa diambil dengan menebak (masuk D0-5 -> D1)
  = -2,2% t -1,9: di bawah ambang. Tebakan salahnya netral (+0,5%), jadi
  bukan efek momentum -- efeknya memang MSCI, cuma belum cukup kuat.
  SC_keluar keD1 "lolos" BUKAN karena MSCI: presisi 3%, tebakan salah pun
  -3,9% -- itu saham kecil yang sedang jatuh (sudah diketahui: desil 1).
  Pakai praktis (bukan bukti): anggota ST terkecil menjelang review = risiko
  dihapus ~50%; pemegang bisa keluar lebih awal.

JURNAL MAJU: website/msci_tebakan.py (sejak 28 Okt 2026, aturan ST_turun di
atas, mulai review Nov26; dicatat otomatis begitu arsip KSEI Okt terbit).

PEMAKAIAN (dari <project>/)
    python -m website.riset_pola_naik.msci_tebak
"""
import glob
import os
import re
import warnings

import numpy as np
import pandas as pd

from . import indeks_msci as M
from . import kalender_bursa as KB
from . import uji as U
from .sumber_baru import muat_ksei

warnings.filterwarnings('ignore')

MULAI = pd.Timestamp('2018-01-01')
BELAH = pd.Timestamp('2022-01-01')
K = {'ST_naik': 1, 'ST_turun': 1, 'SC_masuk': 3, 'SC_keluar': 3}
MAKS_FULL = 2500e12
PRESUMSI_ST = 100e12


def tanggal_review():
    """review -> (umum, efektif) dari halaman 1 SEMUA PDF, termasuk yang tanpa
    perubahan Indonesia. Di-cache ke msci/_tanggal.pkl."""
    cache = os.path.join(M.DIR, '_tanggal.pkl')
    if os.path.exists(cache):
        return pd.read_pickle(cache)
    import pdfplumber
    rows = []
    for f in sorted(glob.glob(os.path.join(M.DIR, 'MSCI_*PublicList.pdf'))):
        with pdfplumber.open(f) as d:
            teks = (d.pages[0].extract_text() or '').replace('\n', ' ')
        u = re.search(r'Geneva,\s+([A-Za-z]+\s+\d{1,2},\s+\d{4})', teks)
        e = re.search(r'as of the close of\s+([A-Za-z]+\s+\d{1,2},\s+\d{4})', teks)
        if u and e:
            rows.append({'review': os.path.basename(f)[5:10], 'umum': M._tgl(u.group(1)), 'efektif': M._tgl(e.group(1))})
    df = pd.DataFrame(rows).drop_duplicates('review').sort_values('umum').reset_index(drop=True)
    df.to_pickle(cache)
    return df


def fitur(isi):
    rows = []
    for t, s in isi['securities'].items():
        n, h = s.get('sec_num'), s.get('price')
        if not n or not h:
            continue
        full = n * h
        if full > MAKS_FULL:
            continue
        kat = s['local_total'] + s['foreign_total'] - s['local']['CP'] - s['foreign']['CP']
        rows.append({'stock': t, 'full': full, 'ff': min(max(kat / n, 0.0), 1.0)})
    return pd.DataFrame(rows).set_index('stock')


def kode_perubahan():
    """(review, stock) -> set kode 'STA','STD','SCA','SCD' dari baris mentah PDF.
    kejadian() meringkas jadi satu grup per emiten; untuk merekonstruksi
    keanggotaan butuh kodenya (ST_turun bisa turun ke SC atau keluar total)."""
    df = M.baca_pdf()
    df = df[df['nama'].isin(M.PETA)].copy()
    df['stock'] = df['nama'].map(M.PETA)
    df['kode'] = df['indeks'] + df['sisi']
    out = {}
    for r in df.itertuples():
        out.setdefault((r.review, r.stock), set()).add(r.kode)
    return out


def status_awal(ev, kode, ksei):
    """Status keanggotaan sebelum kejadian pertama tiap emiten (= awal 2012)."""
    st, sc = set(), set()
    for s, r in ev.sort_values('umum').groupby('stock')['review'].first().items():
        k = kode.get((r, s), set())
        if 'STD' in k:
            st.add(s)
        elif 'SCD' in k:
            sc.add(s)
    f = fitur(ksei['2017-12'])
    tanpa = f.index.difference(ev['stock'].unique())
    st |= set(f.loc[tanpa][f.loc[tanpa, 'full'] >= PRESUMSI_ST].index)
    return st, sc


def terapkan(st, sc, review, stocks, kode):
    """Ubah st/sc di tempat; kembalikan jumlah kode yang bertentangan dengan status."""
    salah = 0
    for s in stocks:
        k = kode.get((review, s), set())
        if 'STA' in k:
            salah += s in st; st.add(s)
        if 'STD' in k:
            salah += s not in st; st.discard(s)
        if 'SCA' in k:
            salah += s in sc; sc.add(s)
        if 'SCD' in k:
            salah += s not in sc and 'STA' not in k; sc.discard(s)
        if 'STA' in k:
            sc.discard(s)
    return salah


def auc(skor, label):
    skor, label = np.asarray(skor, float), np.asarray(label, bool)
    if label.sum() == 0 or (~label).sum() == 0:
        return np.nan
    r = pd.Series(skor).rank().to_numpy()
    return (r[label].sum() - label.sum() * (label.sum() + 1) / 2) / (label.sum() * (~label).sum())


def bangun(ev, rv, ksei, medval):
    """Satu baris per (review, kelompok, emiten calon): skor, ditebak, terjadi."""
    kunci = sorted(ksei)
    asof = pd.Series({k: pd.Timestamp(ksei[k]['as_of']) for k in kunci})
    kode = kode_perubahan()
    st, sc = status_awal(ev, kode, ksei)
    for r in rv[rv['umum'] < MULAI].itertuples():
        terapkan(st, sc, r.review, ev.loc[ev['review'] == r.review, 'stock'], kode)
    bertentangan = 0

    rows, info = [], []
    for r in rv[rv['umum'] >= MULAI].itertuples():
        cocok = asof[asof <= r.umum - pd.Timedelta(days=5)]
        if cocok.empty:
            continue
        f = fitur(ksei[cocok.index[-1]]).copy()
        tgl = cocok.iloc[-1]
        mv = medval.loc[:tgl].iloc[-5:].median() if len(medval.loc[:tgl]) else pd.Series(dtype=float)
        f['medval'] = mv.reindex(f.index)
        f['likuid'] = (f['medval'] * 250 / (f['full'] * f['ff']).replace(0, np.nan)) >= 0.15
        stn, scn = [s for s in st if s in f.index], [s for s in sc if s in f.index]
        if len(stn) < 5 or len(scn) < 5:
            continue
        f['skor_ST'] = f['full'] / f.loc[stn, 'full'].median()
        f['skor_SC'] = f['full'] / f.loc[scn, 'full'].median()
        g = ev[ev['review'] == r.review]
        terjadi = {k: set(g.loc[g['grup'] == k, 'stock']) for k in K}
        layak = (f['ff'] >= 0.15) & f['likuid']
        calon = {
            'ST_naik': (f.index.isin(list(st)) == False) & layak, 'ST_turun': f.index.isin(list(st)),
            'SC_masuk': (~f.index.isin(list(st | sc))) & layak, 'SC_keluar': f.index.isin(list(sc)),
        }
        for k, m in calon.items():
            c = f[m]
            kol = 'skor_ST' if k.startswith('ST') else 'skor_SC'
            naik = k in ('ST_naik', 'SC_masuk')
            urut = c[kol].sort_values(ascending=not naik)
            pilih = set(urut.index[:K[k]])
            for s in c.index:
                rows.append({'review': r.review, 'umum': r.umum, 'efektif': r.efektif, 'kelompok': k,
                             'stock': s, 'skor': c.at[s, kol] * (1 if naik else -1),
                             'ditebak': s in pilih, 'terjadi': s in terjadi[k]})
            info.append({'review': r.review, 'kelompok': k, 'calon': len(c), 'terjadi': len(terjadi[k]),
                         'terjadi_di_calon': len(terjadi[k] & set(c.index))})
        bertentangan += terapkan(st, sc, r.review, g['stock'], kode)
    return pd.DataFrame(rows), pd.DataFrame(info), bertentangan, (st, sc)


def hasil(close, d):
    lr = np.log(close)
    idx = close.index
    mk = lr.diff().mean(axis=1).fillna(0).cumsum().to_numpy()
    r = close.pct_change().abs()
    out = []
    for e in d.itertuples():
        if e.stock not in close.columns:
            continue
        i0 = idx.searchsorted(e.umum, side='right') - 1
        i1, iE, im = i0 + 1, idx.searchsorted(e.efektif, side='left'), i0 - 5
        if im < 0 or iE >= len(idx) or i1 >= len(idx):
            continue
        s = lr[e.stock].to_numpy()
        if not (np.isfinite(s[im]) and np.isfinite(s[i1]) and np.isfinite(s[iE])):
            continue
        if (r[e.stock].iloc[im:iE + 1] > 0.35).any():
            continue
        out.append({'i': e.Index, 'keD1': (s[i1] - s[im]) - (mk[i1] - mk[im]),
                    'keE': (s[iE] - s[im]) - (mk[iE] - mk[im])})
    h = pd.DataFrame(out).set_index('i')
    return d.join(h)


def laporan(d, info, bertentangan):
    print('\nkejadian bertentangan dengan rekonstruksi keanggotaan (perubahan di luar review): %d' % bertentangan)
    ii = info.groupby('kelompok')[['calon', 'terjadi', 'terjadi_di_calon']].agg(['mean', 'sum'])
    print('\ncakupan calon (rata-rata per review, total):')
    print(ii.round(1).to_string())

    rows = []
    for k in K:
        x = d[d['kelompok'] == k]
        a = x.groupby('review').apply(lambda g: auc(g['skor'], g['terjadi'])).dropna()
        tb = x[x['ditebak']]
        r = {'kelompok': k, 'AUC rata2': a.mean(), 'review ber-kejadian': len(a),
             'tebakan': len(tb), 'benar': int(tb['terjadi'].sum()),
             'presisi%': 100 * tb['terjadi'].mean(),
             'kejadian ketangkap%': 100 * tb['terjadi'].sum() / max(x['terjadi'].sum(), 1)}
        for j in ('keD1', 'keE'):
            v = tb[j].dropna()
            r[j + '%'] = (np.exp(v.mean()) - 1) * 100
            r[j + ' t'] = U.t_klaster(v, tb.loc[v.index, 'review'])
            for lab, m in (('P1', tb['umum'] < BELAH), ('P2', tb['umum'] >= BELAH)):
                w = tb.loc[m, j].dropna()
                r['%s %s%%' % (lab, j)] = (np.exp(w.mean()) - 1) * 100 if len(w) else np.nan
            benar = tb.loc[tb['terjadi'], j].dropna()
            salah = tb.loc[~tb['terjadi'], j].dropna()
            r[j + ' benar%'] = (np.exp(benar.mean()) - 1) * 100 if len(benar) else np.nan
            r[j + ' salah%'] = (np.exp(salah.mean()) - 1) * 100 if len(salah) else np.nan
        rows.append(r)
    t = pd.DataFrame(rows).set_index('kelompok')
    with pd.option_context('display.width', 250, 'display.float_format', '{:+.2f}'.format):
        print('\nTEBAKAN:')
        print(t[['AUC rata2', 'review ber-kejadian', 'tebakan', 'benar', 'presisi%', 'kejadian ketangkap%']].to_string())
        print('\nHASIL TEBAKAN (vs pasar, masuk close D0-5):')
        print(t[[c for c in t.columns if c.startswith(('keD1', 'keE', 'P1', 'P2'))]].to_string())

    print('\nKRITERIA (keD1 / keE: tanda sama dua periode, |t| klaster >= 2):')
    for k in K:
        teks = []
        for j in ('keD1', 'keE'):
            a, b, tt = t.at[k, 'P1 %s%%' % j], t.at[k, 'P2 %s%%' % j], t.at[k, j + ' t']
            ok = np.sign(a) == np.sign(b) and abs(tt) >= 2
            teks.append('%s %s (P1 %+.2f, P2 %+.2f, t %.1f)' % (j, 'LOLOS' if ok else 'gagal', a, b, tt))
        print('  %-10s %s' % (k, ' | '.join(teks)))


def main():
    ev = M.kejadian()
    rv = tanggal_review()
    ksei = muat_ksei()
    p = U.muat()
    medval = p.pivot_table(index='date', columns='ticker', values='medval20')
    d, info, bert, akhir = bangun(ev, rv, ksei, medval)
    print('review diuji: %d (%s .. %s) | baris calon: %d'
          % (d['review'].nunique(), d['umum'].min().date(), d['umum'].max().date(), len(d)))
    print('keanggotaan akhir (rekonstruksi): ST %d, SC %d' % (len(akhir[0]), len(akhir[1])))
    print('  ST: ' + ' '.join(sorted(akhir[0])))
    close = KB._panel_close()
    d = hasil(close, d)
    laporan(d, info, bert)
    return d


if __name__ == '__main__':
    main()
