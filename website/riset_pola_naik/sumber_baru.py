"""
Pengunduh sumber data BARU untuk riset event (23 Sep 2026) -- disimpan di
research_cache, TIDAK di folder data app.

KENAPA DI SINI, BUKAN DI Monthly\\Ownership\\ksei
Halaman Kepemilikan Saham memuat SEMUA bulan yang ada di folder KSEI-nya
(ownership.load_ksei_months). Menaruh 160 bulan arsip di sana akan mengubah
halaman itu. Arsip riset disimpan terpisah sebagai ZIP mentah (~80 KB per
bulan) dan diparse dengan ownership.parse_ksei_zip() yang sama -- satu
pembaca, dua tempat simpan.

1. KSEI "Kepemilikan Efek" bulanan, Des 2012 - sekarang
   Tiap file memuat SEMUA saham yang tercatat bulan itu, termasuk yang
   sekarang sudah delisting. Dua kegunaan:
     - arus kepemilikan per jenis investor (asing, individu, reksa dana,
       asuransi, dana pensiun, ...) per bulan, 13+ tahun;
     - daftar emiten yang PERNAH tercatat -> sumber daftar emiten delisting
       yang tidak ada di cache Yahoo (lubang survivorship).
   Nama file = hari bursa terakhir bulan itu, tapi tidak selalu: dicoba 12
   hari terakhir bulan itu, lalu 5 hari pertama bulan berikutnya. File yang
   isinya < 100 saham dianggap rusak/kosong (Des 2021 misalnya ~2 KB) dan
   tanggal lain dicoba.

2. Aksi korporasi dari Yahoo (dividen & pemecahan saham) per emiten.

3. Close MENTAH (tanpa penyesuaian dividen) dari Yahoo, untuk imbal hasil
   dividen -- cache harga riset sudah auto-adjusted.

HASIL UNDUHAN 23 Sep 2026: arsip KSEI ketemu Des 2012-Mei 2013 dan Des
2017-Sep 2026 (112 bulan). Juni 2013-Nov 2017 tidak ada di server KSEI,
juga setelah dicoba setiap hari kerja (isi-bolong). Yahoo: 5.834 dividen,
365 split dari 888 emiten; 0 dari 101 emiten KSEI 2013 yang tidak ada di
cache punya harga di Yahoo.

PEMAKAIAN (dari <project>/)
    python -m website.riset_pola_naik.sumber_baru ksei        # ~160 bulan, sekali
    python -m website.riset_pola_naik.sumber_baru isi-bolong  # bulan bolong dicoba tiap hari kerja
    python -m website.riset_pola_naik.sumber_baru aksi        # dividen & split Yahoo
    python -m website.riset_pola_naik.sumber_baru mentah      # close tanpa penyesuaian dividen
"""
import glob
import json
import os
import pickle
import sys
import time
import zipfile
from calendar import monthrange
from datetime import date, timedelta
from io import BytesIO

from . import panel as PN

KSEI_DIR = os.path.join(PN.RESEARCH_CACHE, 'ksei_riwayat')
KSEI_LOG = os.path.join(KSEI_DIR, '_log.json')
AKSI_FILE = os.path.join(PN.RESEARCH_CACHE, 'aksi_korporasi.pkl')
MULAI = (2012, 12)
MIN_SAHAM = 100


def _kandidat(tahun, bulan):
    akhir = monthrange(tahun, bulan)[1]
    mundur = [date(tahun, bulan, d) for d in range(akhir, max(akhir - 12, 0), -1)]
    awal_berikut = date(tahun, bulan, akhir) + timedelta(days=1)
    maju = [awal_berikut + timedelta(days=i) for i in range(5)]
    return mundur + maju


def _jumlah_saham(blob):
    try:
        arsip = zipfile.ZipFile(BytesIO(blob))
        teks = arsip.read(arsip.namelist()[0]).decode('utf-8', errors='replace')
    except Exception:
        return 0
    return sum(1 for baris in teks.splitlines()[1:] if '|EQUITY|' in baris.upper())


def bulan_tersimpan():
    """{'YYYY-MM': path_zip} dari arsip riset."""
    out = {}
    for path in glob.glob(os.path.join(KSEI_DIR, '*.zip')):
        out[os.path.basename(path)[:7]] = path
    return dict(sorted(out.items()))


def unduh_ksei(sampai=None):
    from ..ownership import KSEI_URL, _scraper
    os.makedirs(KSEI_DIR, exist_ok=True)
    try:
        log = json.load(open(KSEI_LOG, encoding='utf-8'))
    except (OSError, ValueError):
        log = {}
    ada = bulan_tersimpan()
    hari_ini = date.today()
    sampai = sampai or (hari_ini.year, hari_ini.month)
    sesi = _scraper()
    t, b = MULAI
    baru = hilang = 0
    while (t, b) <= sampai:
        kunci = '%04d-%02d' % (t, b)
        if kunci not in ada:
            dapat = None
            for tgl in _kandidat(t, b):
                if tgl > hari_ini:
                    continue
                url = KSEI_URL.format(yyyymmdd=tgl.strftime('%Y%m%d'))
                try:
                    r = sesi.get(url, timeout=90, headers={'User-Agent': 'Mozilla/5.0'})
                except Exception:
                    time.sleep(1.0)
                    continue
                time.sleep(0.15)
                if r.status_code != 200 or r.content[:2] != b'PK':
                    continue
                n = _jumlah_saham(r.content)
                if n < MIN_SAHAM:
                    continue
                path = os.path.join(KSEI_DIR, '%s_%s.zip' % (kunci, tgl.strftime('%Y%m%d')))
                with open(path, 'wb') as fh:
                    fh.write(r.content)
                dapat = (tgl.isoformat(), n)
                break
            log[kunci] = dapat
            if dapat:
                baru += 1
                print('%s  %s  %d saham' % (kunci, dapat[0], dapat[1]), flush=True)
            else:
                hilang += 1
                print('%s  TIDAK ADA' % kunci, flush=True)
            with open(KSEI_LOG, 'w', encoding='utf-8') as fh:
                json.dump(log, fh, indent=1)
        b += 1
        if b == 13:
            t, b = t + 1, 1
    print('selesai: %d bulan baru, %d tidak ditemukan, %d tersimpan total'
          % (baru, hilang, len(bulan_tersimpan())), flush=True)


def isi_bolong():
    """Bulan yang tidak ketemu di pencarian biasa dicoba SEMUA harinya.
    Arsip lama tidak selalu bertanggal akhir bulan (Mei 2013 misalnya
    bertanggal 21 Mei)."""
    from ..ownership import KSEI_URL, _scraper
    try:
        log = json.load(open(KSEI_LOG, encoding='utf-8'))
    except (OSError, ValueError):
        print('log belum ada -- jalankan `ksei` dulu')
        return
    ada = bulan_tersimpan()
    sesi = _scraper()
    for kunci in sorted(k for k, v in log.items() if not v and k not in ada):
        t, b = int(kunci[:4]), int(kunci[5:])
        sudah = set(_kandidat(t, b))
        dapat = None
        for hari in range(1, monthrange(t, b)[1] + 1):
            tgl = date(t, b, hari)
            if tgl in sudah or tgl.weekday() >= 5:
                continue
            try:
                r = sesi.get(KSEI_URL.format(yyyymmdd=tgl.strftime('%Y%m%d')), timeout=60,
                             headers={'User-Agent': 'Mozilla/5.0'})
            except Exception:
                continue
            time.sleep(0.1)
            if r.status_code == 200 and r.content[:2] == b'PK' and _jumlah_saham(r.content) >= MIN_SAHAM:
                path = os.path.join(KSEI_DIR, '%s_%s.zip' % (kunci, tgl.strftime('%Y%m%d')))
                with open(path, 'wb') as fh:
                    fh.write(r.content)
                dapat = (tgl.isoformat(), _jumlah_saham(r.content))
                break
        log[kunci] = dapat
        print('%s  %s' % (kunci, dapat if dapat else 'tetap tidak ada'), flush=True)
        with open(KSEI_LOG, 'w', encoding='utf-8') as fh:
            json.dump(log, fh, indent=1)
    print('selesai: %d bulan tersimpan' % len(bulan_tersimpan()), flush=True)


def muat_ksei():
    """{'YYYY-MM': {'as_of': ..., 'securities': {...}}} -- diparse dengan
    pembaca yang sama dengan halaman Kepemilikan Saham."""
    from ..ownership import parse_ksei_zip
    out = {}
    for kunci, path in bulan_tersimpan().items():
        tgl = os.path.basename(path)[8:16]
        with open(path, 'rb') as fh:
            out[kunci] = parse_ksei_zip(fh.read(), date(int(tgl[:4]), int(tgl[4:6]), int(tgl[6:])))
    return out


def unduh_aksi(tickers=None, keluaran=AKSI_FILE):
    """Dividen & split per emiten dari Yahoo: {ticker: DataFrame(Dividends,
    Stock Splits)} hanya baris yang ada aksinya. Emiten yang gagal diunduh
    dicatat, bukan diabaikan diam-diam."""
    import yfinance as yf
    from concurrent.futures import ThreadPoolExecutor
    if tickers is None:
        _path, data = PN.sumber_harga()
        tickers = sorted(data)
    try:
        lama = pickle.load(open(keluaran, 'rb'))
    except (OSError, EOFError, pickle.UnpicklingError):
        lama = {'aksi': {}, 'gagal': []}

    def ambil(t):
        try:
            a = yf.Ticker(t + '.JK').actions
            if a is None:
                return t, None
            a = a[(a.get('Dividends', 0) != 0) | (a.get('Stock Splits', 0) != 0)]
            if getattr(a.index, 'tz', None) is not None:
                a.index = a.index.tz_localize(None)
            return t, a
        except Exception as exc:
            return t, exc

    sisa = [t for t in tickers if t not in lama['aksi']]
    print('aksi korporasi: %d emiten diunduh (%d sudah ada)' % (len(sisa), len(tickers) - len(sisa)), flush=True)
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=6) as ex:
        for i, (t, a) in enumerate(ex.map(ambil, sisa), 1):
            if isinstance(a, Exception) or a is None:
                lama['gagal'].append(t)
            else:
                lama['aksi'][t] = a
            if i % 100 == 0:
                print('  %d/%d  %.0f dtk' % (i, len(sisa), time.time() - t0), flush=True)
    lama['gagal'] = sorted(set(lama['gagal']) - set(lama['aksi']))
    with open(keluaran, 'wb') as fh:
        pickle.dump(lama, fh)
    n_div = sum(int((a['Dividends'] != 0).sum()) for a in lama['aksi'].values() if 'Dividends' in a)
    n_split = sum(int((a['Stock Splits'] != 0).sum()) for a in lama['aksi'].values() if 'Stock Splits' in a)
    print('selesai: %d emiten, %d dividen, %d split, %d gagal, %.0f dtk'
          % (len(lama['aksi']), n_div, n_split, len(lama['gagal']), time.time() - t0), flush=True)


MENTAH_FILE = os.path.join(PN.RESEARCH_CACHE, 'harga_mentah_close.pkl')


def unduh_mentah(tickers=None, keluaran=MENTAH_FILE):
    """Close TANPA penyesuaian dividen (auto_adjust=False; split tetap
    disesuaikan Yahoo). Perlu untuk imbal hasil dividen: cache harga riset
    sudah auto-adjusted, jadi dividen / close-nya melebih-lebihkan imbal hasil
    lama (harga lamanya sudah dikurangi semua dividen sesudahnya).
    Nama filenya sengaja bukan harga_*.pkl supaya tidak ikut dipilih
    panel.sumber_harga()."""
    import yfinance as yf
    if tickers is None:
        _path, data = PN.sumber_harga()
        tickers = sorted(data)
    out = {}
    t0 = time.time()
    for i in range(0, len(tickers), 60):
        potong = tickers[i:i + 60]
        try:
            m = yf.download([t + '.JK' for t in potong], start='2012-06-01', interval='1d',
                            progress=False, auto_adjust=False, actions=False, group_by='ticker', threads=True)
        except Exception as exc:
            print('  gagal potongan %d: %s' % (i, exc), flush=True)
            continue
        for t in potong:
            try:
                c = m[t + '.JK']['Close'].dropna()
            except Exception:
                continue
            if len(c):
                c.index = c.index.tz_localize(None) if getattr(c.index, 'tz', None) is not None else c.index
                out[t] = c.astype('float64')
        print('  %d/%d  %.0f dtk' % (min(i + 60, len(tickers)), len(tickers), time.time() - t0), flush=True)
    with open(keluaran, 'wb') as fh:
        pickle.dump(out, fh)
    print('selesai: %d emiten, %.0f dtk' % (len(out), time.time() - t0), flush=True)


if __name__ == '__main__':
    perintah = sys.argv[1] if len(sys.argv) > 1 else ''
    if perintah == 'ksei':
        unduh_ksei()
    elif perintah == 'aksi':
        unduh_aksi()
    elif perintah == 'mentah':
        unduh_mentah()
    elif perintah == 'isi-bolong':
        isi_bolong()
    else:
        print(__doc__)
