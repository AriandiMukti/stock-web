"""
Jurnal maju rebalancing indeks MSCI Indonesia.

KENAPA INI ADA
==============
riset_pola_naik/indeks_msci.py (18 Okt 2026) menemukan efek indeks klasik
yang LOLOS di keempat kelompok: setelah pengumuman MSCI, arah ke tanggal
efektif masih bisa diambil, lalu berbalik sesudah dana pasif selesai
berdagang. Tapi itu kalibrasi: 50 review 2012-2026, ST cuma 34/50 kejadian.
Belum ada satu pun review yang dilihat SESUDAH aturannya ditulis. Jurnal ini
mencatat tiap review baru dengan aturan yang sama persis, lalu menilainya
setelah jendelanya lewat.

ATURAN -- DIKUNCI 18 Okt 2026, JANGAN DIUBAH
============================================
(sama dengan DESAIN di indeks_msci.py; diubah = jurnal baru, bukan jurnal ini)
  Sumber   MSCI_<Bln><yy>_STPublicList.pdf & _SCPublicList.pdf dari
           app2.msci.com/eqb/gimi/{stdindex,smallcap}/ (Python bisa langsung,
           bukan IDX). Dibaca baca_satu_pdf() milik riset -- parser yang sama.
  Nama     MSCI -> kode lewat indeks_msci.PETA + PETA_TAMBAHAN di bawah.
           Nama yang tak dikenal dicatat 'belum_dipetakan' dan dilaporkan
           kesehatan; begitu ditambahkan ke PETA_TAMBAHAN, kejadiannya terisi
           dengan tanggal_catat yang asli.
  Kelompok per emiten-review (urutan prioritas sama dengan riset):
           ST_naik   masuk Standard (baru / naik dari Small Cap)
           ST_turun  keluar Standard (termasuk turun ke Small Cap)
           SC_masuk  masuk Small Cap, bukan turunan dari Standard
           SC_keluar keluar Small Cap, bukan naik ke Standard
  Tanggal  D1 = hari bursa BEI pertama SETELAH tanggal pengumuman ("Geneva,
           <tgl>"); E = tanggal efektif ("as of the close of <tgl>").
  Hasil    selisih log vs rata-rata semua emiten tanggal yang sama:
           x_D1      gerak hari D1 (reaksi, tak bisa diambil)
           x_jalan   close D1 -> close E   (yang bisa diambil)
           x_balik5  close E -> close E+5
           x_balik20 close E -> close E+20 (pembalikan)
           Dibuang (status dibuang_*) persis seperti ukur() di riset:
           gerak harian > 35% di D1-1..E+20 (aksi korporasi tak disesuaikan),
           harga kosong di D1-1/D1/E, atau E > 5 hari kalender dari hari
           bursa terdekat.
  Hipotesis (dari kalibrasi, lihat KALIBRASI):
           ST_naik  jalan > 0 lalu balik20 < 0     ST_turun jalan < 0 lalu balik20 > 0
           SC_masuk jalan > 0 lalu balik20 < 0     SC_keluar jalan < 0 lalu balik20 > 0

APA YANG DICATAT
- Satu baris per emiten-review. Kolom hasil diisi bertahap saat jendelanya
  lewat (D1, lalu E, E+5, E+20) dan BEKU setelah status 'matang' / dibuang_*.
- Review yang sudah dikenal saat aturan dikunci (s.d. Aug26) TIDAK dinilai:
  Aug26 dicatat sebagai awal=1 supaya jurnal tahu titik mulainya.
- Review tanpa perubahan Indonesia tetap dapat satu baris penanda
  (status 'tanpa_perubahan') supaya jurnal tidak mencarinya lagi.

PEMAKAIAN
    python -m website.msci_jurnal            # cari review baru, catat, nilai, ringkas
    (harian lewat kesehatan.py, tugas 'msci_jurnal')
"""
try:
    from .runtime_paths import runtime_file as _runtime_file, market_file as _market_file, WEBSITE_DIR as _WEBSITE_DIR, PROJECT_DIR as _PROJECT_DIR, RUNTIME_DIR as _RUNTIME_DIR
except ImportError:
    from website.runtime_paths import runtime_file as _runtime_file, market_file as _market_file, WEBSITE_DIR as _WEBSITE_DIR, PROJECT_DIR as _PROJECT_DIR, RUNTIME_DIR as _RUNTIME_DIR
import glob
import logging
import os
import time

import numpy as np
import pandas as pd

from .config import DAILY_PATH
from .riset_pola_naik import indeks_msci as M

logger = logging.getLogger(__name__)

HERE = os.path.dirname(__file__)
SUMMARY_DIR = os.path.join(DAILY_PATH, 'Summary')
JURNAL_FILE = str(_runtime_file('', 'msci_jurnal.csv'))
DIR_MAJU = os.path.join(M.DIR, 'maju')        # PDF review baru, terpisah dari set kalibrasi

URL = 'https://app2.msci.com/eqb/gimi/%s/MSCI_%s_%sPublicList.pdf'
FOLDER = {'ST': 'stdindex', 'SC': 'smallcap'}
BULAN = {2: 'Feb', 5: 'May', 8: 'Aug', 11: 'Nov'}
REVIEW_AWAL = 'Aug26'          # review terakhir yang sudah dikenal saat aturan dikunci
VERSI = 'msci-v1'
JENDELA = 20                   # E+20
LONCAT = 0.35

HIPOTESIS = {
    'ST_naik': 'jalan D1->E > 0, lalu balik E->E+20 < 0',
    'ST_turun': 'jalan D1->E < 0, lalu balik E->E+20 > 0',
    'SC_masuk': 'jalan D1->E > 0, lalu balik E->E+20 < 0',
    'SC_keluar': 'jalan D1->E < 0, lalu balik E->E+20 > 0',
}
# Angka kalibrasi 18 Okt 2026 (docstring indeks_msci.py), % vs pasar.
KALIBRASI = {
    'ST_naik': {'n': 34, 'jalan': 4.2, 'balik20': -6.2},
    'ST_turun': {'n': 50, 'jalan': -7.8, 'balik20': 6.7},
    'SC_masuk': {'n': 121, 'jalan': 3.6, 'balik20': -4.2},
    'SC_keluar': {'n': 156, 'jalan': -10.6, 'balik20': 3.1},
}

# Nama MSCI baru -> kode BEI. Tambah di sini (bukan di riset) kalau
# kesehatan melaporkan 'belum_dipetakan'. Contoh: 'CONTOH NAMA TBK': 'XXXX'.
PETA_TAMBAHAN = {
}
# Nama yang di riset sengaja dibuang karena ambigu (BJBR/BJTM).
AMBIGU_AWALAN = ('BANK PEMBANGUNAN DA', 'NUSANTARA PROPERTI INTL')

KOLOM = ['tanggal_catat', 'kejadian', 'aturan', 'awal', 'review', 'stock', 'nama', 'grup',
         'umum', 'efektif', 'D1', 'tE', 'status', 'x_D1', 'x_jalan', 'hari_jalan',
         'x_balik5', 'x_balik20', 'dinilai']
SELESAI = ('matang', 'dibuang_loncat', 'dibuang_harga', 'dibuang_tanggal',
           'tanpa_perubahan', 'ambigu', 'dipetakan_ulang')


# ---------------------------------------------------------------------------
# BERSAMA (dipakai juga oleh pk_jurnal.py)
# ---------------------------------------------------------------------------
def hari_bursa():
    """Hari bursa dari berkas Summary terbesar (emiten paling likuid praktis
    tidak pernah bolong -- sama dengan pola_jurnal/insider_jurnal)."""
    berkas = glob.glob(os.path.join(SUMMARY_DIR, '*_Summary.csv'))
    if not berkas:
        return pd.DatetimeIndex([])
    df = pd.read_csv(max(berkas, key=os.path.getsize), usecols=['Date'])
    d = pd.to_datetime(df['Date'], format='%d-%b-%y', errors='coerce').dropna()
    return pd.DatetimeIndex(sorted(d.unique()))


def panel_close():
    """Close semua emiten dari panel sambungan tembus_basis (~15 detik) --
    sumber yang sama dengan kalender_bursa._panel_close() riset untuk semua
    tanggal sejak Juni 2024, tanpa riwayat Yahoo yang tidak dibutuhkan jurnal."""
    from .tembus_basis import _panel
    p = _panel()
    return pd.DataFrame({s: f['close'] for s, f in p['fit'].items()}).sort_index()


def tulis_atomik(df, path):
    tmp = path + '.tmp'
    df.to_csv(tmp, index=False)
    os.replace(tmp, path)


def num(v, d=6):
    try:
        v = float(v)
    except (TypeError, ValueError):
        return np.nan
    return round(v, d) if np.isfinite(v) else np.nan


def hari_ini():
    return pd.Timestamp.now().normalize()


# ---------------------------------------------------------------------------
# REVIEW
# ---------------------------------------------------------------------------
def _kunci_review(rv):
    """'Nov26' -> (2026, 11)."""
    bln = {v: k for k, v in BULAN.items()}[rv[:3]]
    return 2000 + int(rv[3:]), bln


def _review_berikut(rv):
    th, bl = _kunci_review(rv)
    bl += 3
    if bl > 12:
        th, bl = th + 1, bl - 12
    return '%s%02d' % (BULAN[bl], th % 100)


def _berkas(rv, jenis, folder=None):
    return os.path.join(folder or DIR_MAJU, 'MSCI_%s_%sPublicList.pdf' % (rv, jenis))


def _lengkap(rv, folder=None):
    return all(os.path.exists(_berkas(rv, j, folder)) for j in ('ST', 'SC'))


def _review_maju():
    """Review baru yang kedua PDF-nya sudah ada di DIR_MAJU, urut waktu."""
    rv = set()
    for f in glob.glob(os.path.join(DIR_MAJU, 'MSCI_*PublicList.pdf')):
        r = os.path.basename(f)[5:10]
        if r[:3] in BULAN.values() and _lengkap(r):
            rv.add(r)
    return sorted(rv, key=_kunci_review)


def review_dinanti():
    """(review berikut yang belum ada, tanggal mulai dicari)."""
    maju = _review_maju()
    rv = _review_berikut(maju[-1] if maju else REVIEW_AWAL)
    th, bl = _kunci_review(rv)
    return rv, pd.Timestamp(th, bl, 1)


def _unduh(rv):
    """Coba unduh dua PDF review `rv`. True kalau keduanya ada sesudahnya.
    404 = belum terbit (wajar); galat jaringan dicatat, tidak dilempar."""
    import requests
    os.makedirs(DIR_MAJU, exist_ok=True)
    for jenis in ('ST', 'SC'):
        path = _berkas(rv, jenis)
        if os.path.exists(path):
            continue
        try:
            r = requests.get(URL % (FOLDER[jenis], rv, jenis), timeout=30,
                             headers={'User-Agent': 'Mozilla/5.0'})
        except Exception as exc:
            logger.warning('MSCI %s %s: %s', rv, jenis, exc)
            return False
        if r.status_code != 200 or not r.content.startswith(b'%PDF'):
            return False
        with open(path + '.tmp', 'wb') as fh:
            fh.write(r.content)
        os.replace(path + '.tmp', path)
    return _lengkap(rv)


def _peta():
    return dict(M.PETA, **PETA_TAMBAHAN)


def _nama_emiten(n):
    """Kolom Additions/Deletions juga memuat 'None' (tak ada perubahan) dan
    kaki halaman ('Page 1 MSCI', 'Global Standard Indexes - ... All rights
    reserved'). Di riset semuanya hilang sendiri karena tak ada di PETA;
    di sini disaring supaya tidak dilaporkan sebagai nama baru. Nama emiten
    di daftar MSCI selalu huruf besar."""
    return (isinstance(n, str) and n != 'None' and n == n.upper()
            and 'MSCI' not in n and any(c.isalpha() for c in n))


def _baris_review(rv, folder=None):
    """Baris jurnal (tanpa tanggal_catat/awal) untuk satu review. Pengelompokan
    SAMA dengan indeks_msci.kejadian(); bedanya nama yang tak dikenal tidak
    dibuang diam-diam tapi ikut tercatat."""
    rows = M.baca_satu_pdf(_berkas(rv, 'ST', folder)) + M.baca_satu_pdf(_berkas(rv, 'SC', folder))
    if not rows:
        return [{'review': rv, 'stock': '', 'nama': '', 'grup': '', 'status': 'tanpa_perubahan',
                 'kejadian': 'MSCI %s: tidak ada perubahan MSCI Indonesia' % rv}]
    df = pd.DataFrame(rows)
    peta = _peta()
    df['stock'] = df['nama'].map(peta)
    df = df[df['stock'].notna() | df['nama'].map(_nama_emiten)]
    if not len(df):
        return [{'review': rv, 'stock': '', 'nama': '', 'grup': '', 'status': 'tanpa_perubahan',
                 'kejadian': 'MSCI %s: tidak ada perubahan MSCI Indonesia' % rv}]
    out = []
    for r in df[df['stock'].isna()].drop_duplicates(['indeks', 'sisi', 'nama']).itertuples():
        ambigu = r.nama.startswith(AMBIGU_AWALAN)
        out.append({'review': rv, 'stock': '', 'nama': r.nama, 'grup': '',
                    'umum': r.umum, 'efektif': r.efektif,
                    'status': 'ambigu' if ambigu else 'belum_dipetakan',
                    'kejadian': '%s%s %s (MSCI %s, %s)' % (
                        r.indeks, r.sisi, r.nama, rv,
                        'nama ambigu, dibuang seperti riset' if ambigu else 'nama belum di PETA')})
    d = df[df['stock'].notna()].drop_duplicates(['review', 'indeks', 'sisi', 'stock'])
    for (_, s), g in d.groupby(['review', 'stock']):
        kode = set(g['indeks'] + g['sisi'])
        if 'STA' in kode:
            grup = 'ST_naik'
        elif 'STD' in kode:
            grup = 'ST_turun'
        elif 'SCA' in kode:
            grup = 'SC_masuk'
        else:
            grup = 'SC_keluar'
        out.append({'review': rv, 'stock': s, 'nama': ' / '.join(sorted(set(g['nama']))), 'grup': grup,
                    'umum': g['umum'].iloc[0], 'efektif': g['efektif'].iloc[0], 'status': 'menunggu',
                    'kejadian': '%s %s (MSCI %s)' % (grup, s, rv)})
    return out


# ---------------------------------------------------------------------------
# MENCATAT
# ---------------------------------------------------------------------------
def muat():
    """Berkas ada tapi tak terbaca -> melempar (jangan sampai jurnal dikira
    kosong lalu dicatat ulang sebagai baris baru)."""
    if not os.path.exists(JURNAL_FILE):
        return pd.DataFrame(columns=KOLOM)
    teks = ('tanggal_catat', 'kejadian', 'aturan', 'review', 'stock', 'nama', 'grup', 'umum',
            'efektif', 'D1', 'tE', 'status', 'dinilai')
    j = pd.read_csv(JURNAL_FILE, dtype={k: object for k in teks}, keep_default_na=False, na_values=[''])
    for k in ('stock', 'nama', 'grup'):
        j[k] = j[k].fillna('')
    return j[KOLOM]


def _tambah(j, rows, awal):
    hari = hari_ini().strftime('%Y-%m-%d')
    ada = set(zip(j['review'], j['stock'], j['nama'])) if len(j) else set()
    peta = _peta()
    baru = []
    for r in rows:
        if r['status'] == 'menunggu':
            if (r['review'], r['stock']) in set(zip(j['review'], j['stock'])):
                continue
        elif (r['review'], r['stock'], r['nama']) in ada:
            continue
        r = dict(r)
        r['tanggal_catat'] = hari
        r['awal'] = int(awal)
        if r['status'] == 'menunggu':
            # Nama yang dulu 'belum_dipetakan' dan kini dikenal: pakai
            # tanggal_catat aslinya, barisnya ditandai dipetakan_ulang.
            lama = j[(j['review'] == r['review']) & (j['status'] == 'belum_dipetakan')
                     & (j['nama'].map(peta) == r['stock'])] if len(j) else j
            if len(lama):
                r['tanggal_catat'] = lama['tanggal_catat'].iloc[0]
                j.loc[lama.index, 'status'] = 'dipetakan_ulang'
        r['aturan'] = '%s | %s' % (VERSI, HIPOTESIS.get(r.get('grup'), 'tidak dinilai'))
        if awal and r['status'] in ('menunggu', 'belum_dipetakan'):
            r['status'] = 'awal'
        for k in ('umum', 'efektif'):
            if isinstance(r.get(k), pd.Timestamp):
                r[k] = r[k].strftime('%Y-%m-%d')
        baru.append(r)
    if baru:
        j = pd.concat([j, pd.DataFrame(baru)], ignore_index=True)[KOLOM]
    return j, len(baru)


def catat(unduh=True):
    """Cari & catat review baru. Idempoten. Mengembalikan (jurnal, log)."""
    j = muat()
    log = []
    if not len(j):
        if _lengkap(REVIEW_AWAL, M.DIR):
            j, n = _tambah(j, _baris_review(REVIEW_AWAL, M.DIR), awal=True)
            log.append('jurnal dimulai: %d baris %s (awal=1, tidak dinilai)' % (n, REVIEW_AWAL))
    if unduh:
        rv, mulai = review_dinanti()
        if hari_ini() >= mulai:
            if _unduh(rv):
                log.append('MSCI %s terunduh ke %s' % (rv, DIR_MAJU))
            else:
                log.append('MSCI %s belum terbit' % rv)
    # Review maju yang belum tercatat, atau masih punya nama belum dipetakan
    # yang mungkin sekarang sudah ada di PETA_TAMBAHAN.
    peta = _peta()
    for rv in _review_maju():
        sudah = j[j['review'] == rv] if len(j) else j
        tunggu = sudah[sudah['status'] == 'belum_dipetakan'] if len(sudah) else sudah
        if len(sudah) and not (len(tunggu) and tunggu['nama'].isin(peta).any()):
            continue
        j, n = _tambah(j, _baris_review(rv), awal=False)
        if n:
            log.append('MSCI %s: %d baris baru' % (rv, n))
    return j, log


# ---------------------------------------------------------------------------
# MENILAI (rumus = indeks_msci.ukur, diisi bertahap)
# ---------------------------------------------------------------------------
def _perlu_dinilai(j, hari):
    if not len(j) or not len(hari):
        return []
    akhir = hari[-1]
    perlu = []
    for i, r in j.iterrows():
        if int(r['awal']) or r['status'] in SELESAI or r['status'] in ('belum_dipetakan', 'awal'):
            continue
        if not r['stock'] or pd.isna(r['umum']):
            continue
        if pd.Timestamp(r['umum']) < akhir:      # D1 sudah ada
            perlu.append(i)
    return perlu


def nilai(j, close=None):
    """Isi kolom hasil yang jendelanya sudah lewat. Mengubah j di tempat."""
    hari = hari_bursa()
    perlu = _perlu_dinilai(j, hari)
    if not perlu:
        return 0
    if close is None:
        close = panel_close()
    lr = np.log(close)
    idx = close.index
    n = len(idx)
    m = lr.diff().mean(axis=1).fillna(0).cumsum().to_numpy()
    r_abs = close.pct_change().abs()
    stamp = hari_ini().strftime('%Y-%m-%d')
    berubah = 0
    for i in perlu:
        e = j.loc[i]
        umum, efektif, s_ = pd.Timestamp(e['umum']), pd.Timestamp(e['efektif']), e['stock']
        i1 = idx.searchsorted(umum, side='right')
        iE = idx.searchsorted(efektif, side='left')
        if i1 >= n:
            continue
        upd = {'D1': idx[i1].strftime('%Y-%m-%d')}
        if s_ not in close.columns:
            # Emiten belum ada di Summary: tunggu sampai jendela penuh lewat.
            if iE + JENDELA < n:
                upd['status'] = 'dibuang_harga'
        else:
            s = lr[s_].to_numpy()
            if not (np.isfinite(s[i1 - 1]) and np.isfinite(s[i1])):
                upd['status'] = 'dibuang_harga'
            else:
                upd['x_D1'] = num((s[i1] - s[i1 - 1]) - (m[i1] - m[i1 - 1]))
                upd['status'] = 'sebagian'
                if iE < n:
                    upd['tE'] = idx[iE].strftime('%Y-%m-%d')
                    if iE < i1 or (idx[iE] - efektif).days > 5:
                        upd['status'] = 'dibuang_tanggal'
                    elif not np.isfinite(s[iE]):
                        upd['status'] = 'dibuang_harga'
                    else:
                        upd['hari_jalan'] = int(iE - i1)
                        if iE > i1:
                            upd['x_jalan'] = num((s[iE] - s[i1]) - (m[iE] - m[i1]))
                        for h in (5, 20):
                            jj = iE + h
                            if jj < n and np.isfinite(s[jj]):
                                upd['x_balik%d' % h] = num((s[jj] - s[iE]) - (m[jj] - m[iE]))
                        if iE + JENDELA < n:
                            upd['status'] = 'matang'
                if upd['status'] in ('sebagian', 'matang'):
                    if (r_abs[s_].iloc[i1 - 1:min(n, iE + 21)] > LONCAT).any():
                        upd['status'] = 'dibuang_loncat'
        lama = {k: j.at[i, k] for k in upd}
        if any(str(lama[k]) != str(v) for k, v in upd.items()):
            for k, v in upd.items():
                j.at[i, k] = v
            j.at[i, 'dinilai'] = stamp
            berubah += 1
    return berubah


def jalankan():
    """Tugas harian kesehatan: catat review baru, nilai, simpan."""
    j, log = catat()
    n = nilai(j)
    if len(j):
        tulis_atomik(j[KOLOM], JURNAL_FILE)
    return {'log': log, 'dinilai': n, 'baris': len(j)}


# ---------------------------------------------------------------------------
# MEMBACA HASIL
# ---------------------------------------------------------------------------
def _pct(x):
    x = pd.to_numeric(x, errors='coerce').dropna()
    return round((np.exp(x.mean()) - 1) * 100, 2) if len(x) else None


def ringkas(j=None):
    """Per kelompok: kejadian maju (awal=0) yang matang vs kalibrasi."""
    j = muat() if j is None else j
    j = j[(j['awal'].astype(int) == 0) & (j['grup'] != '')] if len(j) else j
    rows = []
    for g in ('ST_naik', 'ST_turun', 'SC_masuk', 'SC_keluar'):
        x = j[j['grup'] == g] if len(j) else j
        mt = x[x['status'] == 'matang'] if len(x) else x
        jal = pd.to_numeric(mt['x_jalan'], errors='coerce').dropna() if len(mt) else pd.Series(dtype=float)
        rows.append({'kelompok': g, 'tercatat': len(x), 'matang': len(mt),
                     'jalan %': _pct(mt['x_jalan']) if len(mt) else None,
                     'searah jalan %': (round(((jal > 0) == (KALIBRASI[g]['jalan'] > 0)).mean() * 100, 1)
                                        if len(jal) else None),
                     'balik20 %': _pct(mt['x_balik20']) if len(mt) else None,
                     'kalibrasi jalan %': KALIBRASI[g]['jalan'],
                     'kalibrasi balik20 %': KALIBRASI[g]['balik20']})
    return pd.DataFrame(rows).set_index('kelompok')


def periksa():
    """Masalah untuk laporan kesehatan."""
    try:
        j = muat()
    except Exception as exc:
        return ['msci_jurnal.csv tidak terbaca: %s' % exc]
    masalah = []
    if len(j):
        b = j[j['status'] == 'belum_dipetakan']
        for rv, g in b.groupby('review'):
            masalah.append('Jurnal MSCI %s: %d nama belum dikenal (%s) -- tambahkan ke '
                           'msci_jurnal.PETA_TAMBAHAN' % (rv, len(g), ', '.join(g['nama'].head(5))))
    rv, mulai = review_dinanti()
    # Pengumuman MSCI jatuh di bulan review itu sendiri; lewat dari bulan
    # berikutnya tanggal 10 berarti unduhannya gagal, bukan belum terbit.
    batas = mulai + pd.DateOffset(months=1) + pd.Timedelta(days=9)
    if hari_ini() > batas:
        masalah.append('Jurnal MSCI: review %s belum terunduh padahal sudah lewat %s -- cek %s'
                       % (rv, batas.strftime('%d %b %Y'), URL % (FOLDER['ST'], rv, 'ST')))
    return masalah


if __name__ == '__main__':
    hasil = jalankan()
    for baris in hasil['log']:
        print(baris)
    print('dinilai: %d baris berubah, total %d baris' % (hasil['dinilai'], hasil['baris']))
    rv, mulai = review_dinanti()
    print('review berikut: %s (dicari mulai %s)' % (rv, mulai.date()))
    pd.set_option('display.width', 200)
    print(ringkas().to_string())
    for m in periksa():
        print('MASALAH:', m)
