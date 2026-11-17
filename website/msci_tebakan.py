"""
Jurnal maju tebakan "dihapus dari MSCI Standard" -- dicatat SEBELUM pengumuman.

KENAPA INI ADA
==============
riset_pola_naik/msci_tebak.py (28 Okt 2026): anggota MSCI Indonesia Standard
TERKECIL menjelang review ternyata dihapus 49% kali (17/35 review), dan
masuk close D0-5 -> D1 rata-rata -2,2% vs pasar (t -1,9, tipis di bawah
ambang); sampai tanggal efektif -6,0% (t -3,1). Tebakan yang salah netral
(+0,5%), jadi efeknya MSCI, bukan momentum. Hampir lolos -> diuji maju di
sini. Pemakaian praktis kalau bertahan: pemegang anggota ST terkecil keluar
sebelum pengumuman.

Jurnal terpisah dari msci_jurnal.py karena aturan di sana dikunci 18 Okt
(menambah aturan = jurnal baru).

ATURAN -- DIKUNCI 28 Okt 2026, JANGAN DIUBAH
============================================
(sama dengan DESAIN ST_turun di msci_tebak.py; diubah = jurnal baru)
  Review    berikutnya sesudah review terakhir di jurnal ini (mulai Nov26).
  Arsip     KSEI bulan SEBELUM bulan review (Okt untuk Nov), diunduh sendiri
            lewat ownership.fetch_ksei_month. Kalau sampai tanggal 3 bulan
            review arsip itu belum terbit, pakai arsip terbaru yang ada
            (ditandai di kolom arsip_ksei).
  Anggota   rekonstruksi msci_tebak: kode perubahan PDF kalibrasi 2012-Agu26
            diputar berurutan, lalu PDF review maju (research_cache/msci/maju/)
            dengan peta nama msci_jurnal. Anggota yang masuk di luar review
            (IPO dll.) tidak terlihat -- batas yang sama dengan kalibrasi.
  Tebakan   anggota ST dengan full (jumlah saham x harga KSEI) TERKECIL =
            peringkat 1. Peringkat 2-3 ikut dicatat sebagai info, tidak dinilai.
  Bocor     tebakan hanya sah kalau PDF review BELUM terbit saat dicatat
            (dicek dengan mencoba mengunduhnya). Kalau sudah terbit: baris
            'terlambat', tidak dinilai.
  Hasil     (rumus = msci_tebak.hasil) log vs rata-rata semua emiten tanggal sama:
            x_keD1 close D0-5 -> close D1, x_keE close D0-5 -> close tanggal
            efektif. D0 = hari bursa terakhir <= tanggal pengumuman.
            terjadi = 1 kalau emiten itu dihapus dari ST di review itu.
  Kalibrasi presisi 49%, keD1 -2,2%, keE -6,0% (35 review 2018-2026).

PEMAKAIAN
    python -m website.msci_tebakan             # catat / nilai / ringkas
    python -m website.msci_tebakan pratinjau   # urutan sekarang, TIDAK dicatat
    (harian lewat kesehatan.py, tugas 'msci_tebakan', sebelum 'msci_jurnal')
"""
try:
    from .runtime_paths import runtime_file as _runtime_file, market_file as _market_file, WEBSITE_DIR as _WEBSITE_DIR, PROJECT_DIR as _PROJECT_DIR, RUNTIME_DIR as _RUNTIME_DIR
except ImportError:
    from website.runtime_paths import runtime_file as _runtime_file, market_file as _market_file, WEBSITE_DIR as _WEBSITE_DIR, PROJECT_DIR as _PROJECT_DIR, RUNTIME_DIR as _RUNTIME_DIR
import glob
import json
import logging
import os
import sys

import numpy as np
import pandas as pd

from . import msci_jurnal as J
from .riset_pola_naik import indeks_msci as M
from .riset_pola_naik import msci_tebak as T

logger = logging.getLogger(__name__)

HERE = os.path.dirname(__file__)
JURNAL_FILE = str(_runtime_file('', 'msci_tebakan.csv'))
VERSI = 'msci-hapus-v1'
REVIEW_AWAL = 'Aug26'
INFO = 3
KALIBRASI = {'review': 35, 'presisi': 49, 'keD1': -2.2, 'keE': -6.0}

KOLOM = ['tanggal_catat', 'aturan', 'review', 'arsip_ksei', 'peringkat', 'stock', 'full_T',
         'skor', 'anggota_st', 'status', 'umum', 'efektif', 'D1', 'tE', 'terjadi',
         'x_keD1', 'x_keE', 'dinilai']
SELESAI = ('matang', 'terlambat', 'info', 'dibuang_harga', 'dibuang_loncat')


# ---------------------------------------------------------------------------
# KEANGGOTAAN & UKURAN
# ---------------------------------------------------------------------------
def _ksei_bulan(th, bl):
    """dict arsip KSEI (format parse_ksei_zip) dari Monthly/Ownership/ksei."""
    from .ownership import KSEI_DIR
    path = os.path.join(KSEI_DIR, '%04d-%02d.json' % (th, bl))
    if not os.path.exists(path):
        return None
    with open(path, encoding='utf-8') as fh:
        return json.load(fh)


def _ksei_2017_12():
    from .ownership import parse_ksei_zip
    from .riset_pola_naik.sumber_baru import bulan_tersimpan
    from datetime import date
    path = bulan_tersimpan()['2017-12']
    tgl = os.path.basename(path)[8:16]
    with open(path, 'rb') as fh:
        return parse_ksei_zip(fh.read(), date(int(tgl[:4]), int(tgl[4:6]), int(tgl[6:])))


def _kode_maju(rv):
    """(kode per stock, daftar stock) review maju, peta nama = msci_jurnal."""
    peta = J._peta()
    kode = {}
    for jenis in ('ST', 'SC'):
        for r in M.baca_satu_pdf(J._berkas(rv, jenis)):
            s = peta.get(r['nama'])
            if s:
                kode.setdefault((rv, s), set()).add(r['indeks'] + r['sisi'])
    return kode, sorted({s for _, s in kode})


def anggota_st(sebelum=None):
    """Himpunan ST hasil rekonstruksi, sesudah semua review yang PDF-nya ada
    (kalibrasi + maju), kecuali `sebelum` dan sesudahnya."""
    ev = M.kejadian()
    kode = T.kode_perubahan()
    st, sc = T.status_awal(ev, kode, {'2017-12': _ksei_2017_12()})
    for r in T.tanggal_review().itertuples():
        T.terapkan(st, sc, r.review, ev.loc[ev['review'] == r.review, 'stock'], kode)
    for rv in J._review_maju():
        if sebelum and J._kunci_review(rv) >= J._kunci_review(sebelum):
            break
        k, stocks = _kode_maju(rv)
        T.terapkan(st, sc, rv, stocks, k)
    return st


def urutan(isi, st):
    """Anggota ST yang ada di arsip, urut full terkecil dulu."""
    f = T.fitur(isi)
    a = f.loc[[s for s in st if s in f.index]].copy()
    a['skor'] = a['full'] / a['full'].median()
    return a.sort_values('full')


# ---------------------------------------------------------------------------
# MENCATAT
# ---------------------------------------------------------------------------
def muat():
    if not os.path.exists(JURNAL_FILE):
        return pd.DataFrame(columns=KOLOM)
    teks = ('tanggal_catat', 'aturan', 'review', 'arsip_ksei', 'stock', 'status', 'umum',
            'efektif', 'D1', 'tE', 'dinilai')
    j = pd.read_csv(JURNAL_FILE, dtype={k: object for k in teks}, keep_default_na=False, na_values=[''])
    return j[KOLOM]


def review_dinanti(j):
    terakhir = j['review'].iloc[-1] if len(j) else REVIEW_AWAL
    rv = J._review_berikut(terakhir)
    th, bl = J._kunci_review(rv)
    return rv, th, bl


def _arsip(th, bl):
    """(isi, 'YYYY-MM') arsip untuk review bulan (th, bl), atau (None, alasan)."""
    from .ownership import fetch_ksei_month, KSEI_DIR
    ta, ba = (th, bl - 1) if bl > 1 else (th - 1, 12)
    if J.hari_ini() < pd.Timestamp(th, bl, 1):
        # arsip bulan sebelumnya baru terbit setelah bulan itu habis
        if J.hari_ini() < pd.Timestamp(ta, ba, 1) + pd.offsets.MonthEnd(0):
            return None, 'arsip %04d-%02d belum terbit' % (ta, ba)
    try:
        fetch_ksei_month(ta, ba)
    except Exception as exc:
        logger.warning('KSEI %04d-%02d: %s', ta, ba, exc)
    isi = _ksei_bulan(ta, ba)
    if isi:
        return isi, '%04d-%02d' % (ta, ba)
    if J.hari_ini() >= pd.Timestamp(th, bl, 3):
        ada = sorted(os.path.basename(p)[:7] for p in glob.glob(os.path.join(KSEI_DIR, '*.json')))
        if ada:
            th2, bl2 = map(int, ada[-1].split('-'))
            return _ksei_bulan(th2, bl2), ada[-1] + ' (cadangan)'
    return None, 'menunggu arsip %04d-%02d' % (ta, ba)


def catat():
    """Catat tebakan review berikutnya kalau arsipnya siap. Idempoten."""
    j = muat()
    rv, th, bl = review_dinanti(j)
    isi, arsip = _arsip(th, bl)
    if isi is None:
        return j, ['MSCI %s: %s' % (rv, arsip)]
    hari = J.hari_ini().strftime('%Y-%m-%d')
    terbit = J._lengkap(rv) or (J.hari_ini() >= pd.Timestamp(th, bl, 1) and J._unduh(rv))
    a = urutan(isi, anggota_st(sebelum=rv))
    rows = []
    for i, (s, r) in enumerate(a.head(INFO).iterrows(), 1):
        status = 'terlambat' if terbit else ('menunggu' if i == 1 else 'info')
        rows.append({'tanggal_catat': hari, 'aturan': VERSI, 'review': rv, 'arsip_ksei': arsip,
                     'peringkat': i, 'stock': s, 'full_T': round(r['full'] / 1e12, 2),
                     'skor': round(r['skor'], 4), 'anggota_st': len(a), 'status': status})
    j = pd.concat([j, pd.DataFrame(rows, columns=KOLOM)], ignore_index=True)[KOLOM]
    tebak = rows[0]['stock'] if rows else '-'
    return j, ['MSCI %s: tebakan hapus ST = %s (arsip %s, %d anggota)%s'
               % (rv, tebak, arsip, len(a), ' -- TERLAMBAT, PDF sudah terbit' if terbit else '')]


# ---------------------------------------------------------------------------
# MENILAI
# ---------------------------------------------------------------------------
def _tanggal_maju(rv):
    """(umum, efektif) dari halaman 1 PDF ST review maju."""
    import re
    import pdfplumber
    with pdfplumber.open(J._berkas(rv, 'ST')) as d:
        teks = (d.pages[0].extract_text() or '').replace('\n', ' ')
    u = re.search(r'Geneva,\s+([A-Za-z]+\s+\d{1,2},\s+\d{4})', teks)
    e = re.search(r'as of the close of\s+([A-Za-z]+\s+\d{1,2},\s+\d{4})', teks)
    return M._tgl(u.group(1)), M._tgl(e.group(1))


def nilai(j, close=None):
    perlu = [i for i, r in j.iterrows() if r['status'] not in SELESAI and J._lengkap(r['review'])]
    if not perlu:
        return 0
    if close is None:
        close = J.panel_close()
    lr = np.log(close)
    idx = close.index
    n = len(idx)
    m = lr.diff().mean(axis=1).fillna(0).cumsum().to_numpy()
    r_abs = close.pct_change().abs()
    stamp = J.hari_ini().strftime('%Y-%m-%d')
    berubah = 0
    for i in perlu:
        e = j.loc[i]
        umum, efektif = _tanggal_maju(e['review'])
        k, _ = _kode_maju(e['review'])
        upd = {'umum': umum.strftime('%Y-%m-%d'), 'efektif': efektif.strftime('%Y-%m-%d'),
               'terjadi': int('STD' in k.get((e['review'], e['stock']), set()))}
        i0 = idx.searchsorted(umum, side='right') - 1
        i1, iE, im = i0 + 1, idx.searchsorted(efektif, side='left'), i0 - 5
        if e['stock'] in close.columns and im >= 0 and i1 < n:
            s = lr[e['stock']].to_numpy()
            upd['D1'] = idx[i1].strftime('%Y-%m-%d')
            if not (np.isfinite(s[im]) and np.isfinite(s[i1])):
                upd['status'] = 'dibuang_harga'
            else:
                upd['x_keD1'] = J.num((s[i1] - s[im]) - (m[i1] - m[im]))
                upd['status'] = 'sebagian'
                if iE < n and np.isfinite(s[iE]):
                    upd['tE'] = idx[iE].strftime('%Y-%m-%d')
                    upd['x_keE'] = J.num((s[iE] - s[im]) - (m[iE] - m[im]))
                    upd['status'] = 'matang'
                if (r_abs[e['stock']].iloc[im:min(n, iE + 1)] > J.LONCAT).any():
                    upd['status'] = 'dibuang_loncat'
        lama = {kk: j.at[i, kk] for kk in upd}
        if any(str(lama[kk]) != str(v) for kk, v in upd.items()):
            for kk, v in upd.items():
                j.at[i, kk] = v
            j.at[i, 'dinilai'] = stamp
            berubah += 1
    return berubah


def jalankan():
    """Tugas harian kesehatan: catat tebakan (sebelum msci_jurnal mengunduh
    PDF), nilai yang PDF-nya sudah ada, simpan."""
    j, log = catat()
    n = nilai(j)
    if len(j):
        J.tulis_atomik(j[KOLOM], JURNAL_FILE)
    return {'log': log, 'dinilai': n, 'baris': len(j)}


# ---------------------------------------------------------------------------
# MEMBACA HASIL
# ---------------------------------------------------------------------------
def ringkas(j=None):
    j = muat() if j is None else j
    t = j[(j['peringkat'].astype(int) == 1) & (j['status'] == 'matang')] if len(j) else j
    if not len(t):
        return {'matang': 0, **{'kalibrasi ' + k: v for k, v in KALIBRASI.items()}}
    pct = lambda x: round((np.exp(pd.to_numeric(x, errors='coerce').mean()) - 1) * 100, 2)
    return {'matang': len(t), 'presisi %': round(t['terjadi'].astype(int).mean() * 100, 1),
            'keD1 %': pct(t['x_keD1']), 'keE %': pct(t['x_keE']),
            **{'kalibrasi ' + k: v for k, v in KALIBRASI.items()}}


def periksa():
    try:
        j = muat()
    except Exception as exc:
        return ['msci_tebakan.csv tidak terbaca: %s' % exc]
    rv, th, bl = review_dinanti(j)
    # Pengumuman MSCI paling cepat sekitar tanggal 5 bulan review; lewat dari
    # itu tanpa tebakan berarti arsip KSEI gagal diunduh atau tugas tak jalan.
    if J.hari_ini() >= pd.Timestamp(th, bl, 5):
        return ['Tebakan MSCI %s belum tercatat padahal sudah tanggal 5 -- cek arsip KSEI '
                '(python -m website.ownership ksei) dan tugas msci_tebakan' % rv]
    return []


def pratinjau():
    """Urutan anggota ST terkecil dengan arsip KSEI terbaru. TIDAK dicatat."""
    from .ownership import KSEI_DIR
    ada = sorted(os.path.basename(p)[:7] for p in glob.glob(os.path.join(KSEI_DIR, '*.json')))
    th, bl = map(int, ada[-1].split('-'))
    j = muat()
    rv, _, _ = review_dinanti(j)
    a = urutan(_ksei_bulan(th, bl), anggota_st(sebelum=rv))
    print('pratinjau %s dengan arsip %s (TIDAK dicatat), %d anggota ST rekonstruksi:' % (rv, ada[-1], len(a)))
    print((a.assign(full_T=a['full'] / 1e12)[['full_T', 'ff', 'skor']]).round(3).to_string())


if __name__ == '__main__':
    if sys.argv[1:] == ['pratinjau']:
        pratinjau()
        sys.exit()
    hasil = jalankan()
    for baris in hasil['log']:
        print(baris)
    print('dinilai: %d baris berubah, total %d baris' % (hasil['dinilai'], hasil['baris']))
    print(ringkas())
    for m_ in periksa():
        print('MASALAH:', m_)
