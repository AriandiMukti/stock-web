"""
Masuk / keluar Papan Pemantauan Khusus (full call auction): apa yang terjadi
pada harga sesudahnya?

DATA
  Pengumuman BEI "Efek Bersifat Ekuitas Dalam Pemantauan Khusus" (Peng-PK),
  "Pencabutan ... Dari Pemantauan Khusus" (Peng-CK) via API GetAnnouncement,
  PDF dibaca pdf.js di tab browser idx.co.id 18 Okt 2026 (API cuma 3 tahun:
  29 Nov 2023 - 16 Okt 2026; Python kena 403 Cloudflare). 732 pengumuman, 724
  terbaca; yang gagal 7 "Perubahan" (ganti kriteria, tak dipakai) + 1 pencabutan
  ber-PDF rusak (Peng-CK-00034/03-2026). Berkas ringkas:
    research_cache/idx_bursa/pemantauan_khusus_2023-11_2026-10.txt
    token "EEEEEEAAAAAAJKODE-k1.k2"  E = tanggal efektif (yymmdd),
    A = tanggal pengumuman, J = M masuk / K keluar, k = nomor kriteria
  Kriteria (versi 2024-26): 1 harga < Rp51 (+ likuiditas rendah sejak 2025),
  2 opini disclaimer, 3 tanpa pendapatan, 5 ekuitas negatif, 6 free float,
  7 likuiditas rendah, 8/9 PKPU/pailit, 10 disuspensi > 1 hari karena aktivitas
  perdagangan, 11 lain-lain (OJK).

DESAIN (didaftar SEBELUM hasil dilihat, 18 Okt 2026)
  Hari kejadian = tanggal EFEKTIF (hari pertama di / keluar papan). Masuk di
  close hari itu (kerangka kalender_bursa: _maju, pembanding rata-rata semua
  emiten tanggal yang sama). "hari-H" = gerak hari efektif itu sendiri
  (umumnya diumumkan sore sebelumnya -> pemegang tidak sempat keluar).
  Kelompok:  M10 / K10  = karena suspensi aktivitas perdagangan
             Mfund / Kfund = kriteria 2,3,5,6,8,9,11
             Mharga / Kharga = kriteria 1,7 (harga gocap / tidak likuid)
  Dua periode: s.d. Mar 2025 vs Apr 2025+ (sama dengan kalender_bursa).
  LOLOS kalau H+5 atau H+20: tanda sama di dua periode (n >= 30 tiap
  periode) DAN |t| gabungan >= 2 (klaster bulanan). Sinyal beli harus
  > +0,4% (biaya); sinyal hindari tak punya ambang biaya.

HASIL (18 Okt 2026, 976 kejadian terpetakan, 12 dibuang karena loncatan data):
  Mfund (masuk karena disclaimer/tanpa pendapatan/ekuitas negatif/free float/
  PKPU) LOLOS sebagai sinyal HINDARI: hari-H -3,3%, lalu H+5 -4,2% (t -3,1),
  H+20 -8,7% (t -4,0) vs pasar; P1 -5,7% / P2 -12,2% di H+20; 72% negatif,
  median -5,2%; tetap di harga >= 100 (-9,7%), tanpa 10 terburuk -3,3%.
  Mayoritas kriteria 6 (free float, n 62). n 84 dalam 3 tahun -> kalibrasi.
  Batas: ~30% hari sesudahnya harganya tak bergerak (call auction tipis),
  jadi "jual di close hari efektif" belum tentu bisa terisi penuh.
  M10 (suspensi trading) gagal: H+1 -1,5% (t -3,4, sama dgn temuan
  unsuspensi) lalu pulih, H+20 ~+2,5. Keluar papan (K*) gagal semua; lonjakan
  keluar papan fundamental terjadi DI hari-H (+10,9%), tak bisa diambil.
  Mharga/Kharga: n periode 2 kurang (kriteria 1 diubah 2025).

JURNAL MAJU: website/pk_jurnal.py (Peng-PK sesudah 16 Okt 2026, aturan
sama; data lewat skrip browser di /perbarui-kepemilikan). Diuji setara
dengan _maju + saringan loncatan di sini: 467/467 kejadian masuk.

PEMAKAIAN: python -m website.riset_pola_naik.pemantauan_khusus
"""
import os

import numpy as np
import pandas as pd

from . import kalender_bursa as KB

BERKAS = os.path.join(KB.DIR, 'pemantauan_khusus_2023-11_2026-10.txt')
FUND = {2, 3, 5, 6, 8, 9, 11}
HARGA = {1, 7}


def baca():
    rows = []
    for t in open(BERKAS).read().split():
        if t[:6] == '------':
            continue
        kr = {int(x) for x in t[18:].split('.') if x} if '-' in t else set()
        rows.append({'date': pd.Timestamp('20' + t[:6]), 'umum': pd.Timestamp('20' + t[6:12]),
                     'jenis': t[12], 'stock': t[13:17], 'kr': kr})
    d = pd.DataFrame(rows)
    d['grup'] = np.where(d['kr'].map(lambda k: 10 in k), '10',
                np.where(d['kr'].map(lambda k: bool(k & FUND)), 'fund',
                np.where(d['kr'].map(lambda k: bool(k & HARGA)), 'harga', 'lain')))
    return d


def _lolos(d):
    hasil = {}
    a, b = d[d['t0'] < KB.BELAH], d[d['t0'] >= KB.BELAH]
    for h in (5, 20):
        xa, xb, x = a['x%d' % h].dropna(), b['x%d' % h].dropna(), d['x%d' % h].dropna()
        if len(xa) < 30 or len(xb) < 30:
            hasil[h] = 'n kurang (%d/%d)' % (len(xa), len(xb))
            continue
        t = KB.U.t_klaster(x, d.loc[x.index, 't0'].dt.to_period('M').astype(str))
        sama = np.sign(xa.mean()) == np.sign(xb.mean())
        hasil[h] = '%s (P1 %+.2f%%, P2 %+.2f%%, t %.1f)' % (
            'LOLOS' if (sama and abs(t) >= 2) else 'gagal',
            (np.exp(xa.mean()) - 1) * 100, (np.exp(xb.mean()) - 1) * 100, t)
    return hasil


def main():
    ev = baca()
    print('kejadian: %d (masuk %d, keluar %d), %s s.d. %s'
          % (len(ev), (ev['jenis'] == 'M').sum(), (ev['jenis'] == 'K').sum(),
             ev['date'].min().date(), ev['date'].max().date()))
    print(ev.groupby(['jenis', 'grup']).size().unstack(fill_value=0).to_string())
    close = KB._panel_close()
    d = KB._maju(close, ev)
    # gerak harian > 35% mustahil di bawah batas ARB/ARA -> aksi korporasi yang
    # tak disesuaikan (mis. SCCO split 1:4, 1 Feb 2024) -- kejadiannya dibuang
    r = close.pct_change().abs()
    loncat = [bool((r[s].iloc[max(0, i - 1):i + 21] > 0.35).any())
              for s, i in zip(d['stock'], close.index.get_indexer(d['t0']))]
    d = d[~np.array(loncat)].reset_index(drop=True)
    print('terpetakan ke harga: %d (dibuang %d karena loncatan data)' % (len(d), sum(loncat)))

    for j, nama in (('M', 'MASUK papan'), ('K', 'KELUAR papan')):
        rows = []
        dj = d[d['jenis'] == j]
        rows.append(KB._ringkas(dj, '%s semua' % j))
        for g in ('10', 'fund', 'harga'):
            dg = dj[dj['grup'] == g]
            rows.append(KB._ringkas(dg, '%s%s' % (j, g)))
            rows.append(KB._ringkas(dg[dg['t0'] < KB.BELAH], '  %s%s s.d. Mar 2025' % (j, g)))
            rows.append(KB._ringkas(dg[dg['t0'] >= KB.BELAH], '  %s%s Apr 2025+' % (j, g)))
        KB._tabel(rows, '%s -> masuk close hari efektif' % nama)

    print('\nKRITERIA (H+5 / H+20: tanda sama dua periode, n>=30, |t|>=2):')
    for j in ('M', 'K'):
        for g in ('10', 'fund', 'harga'):
            dg = d[(d['jenis'] == j) & (d['grup'] == g)]
            print('  %s%-6s %s' % (j, g, ' | '.join('H+%d %s' % (h, v) for h, v in _lolos(dg).items())))


if __name__ == '__main__':
    main()
