"""
Buku besar broker: menarik data broker harian per saham dari berkas mentah
JSON, jadi satu tabel yang bisa dianalisis.

KENAPA INI ADA
Berkas mentah di Daily\\All menyimpan, untuk SETIAP saham SETIAP hari, rincian
per broker: kode broker, lot, nilai, dan yang paling menarik --
`netbs_buy_avg_price`, harga rata-rata beli broker itu hari itu. App ini
selama ini meremas semuanya jadi satu angka "Net Top5 lot" dan membuang
identitas maupun harganya.

Padahal di situ ada 962 saham x 158 hari x ~24 baris broker = sekitar 3,6 juta
baris yang tidak pernah disentuh. Modul ini membacanya sekali (~10-15 menit,
diparalelkan) lalu menyimpannya sebagai satu berkas cache, supaya modul
analisis di atasnya bisa bekerja dalam hitungan detik.

BENTUK TABELNYA
    date, stock, broker, side ('buy'/'sell'), lot, value, avg_price

CATATAN SUMBER
- Satu broker bisa muncul di sisi beli DAN jual pada hari yang sama (dia
  memang memperdagangkan dua arah). Keduanya disimpan apa adanya; modul di
  atasnya yang memutuskan mau memakai netto atau bruto.
- `netbs_buy_avg_price` ada pada baris beli maupun jual (di sisi jual itu
  harga rata-rata jualnya). Nilai 0/kosong dibuang, bukan diisi tebakan.
- Nama field mengikuti sumbernya (netbs_*), tidak diubah, supaya kalau
  sumbernya berubah bentuk ketahuan langsung.

DUA FORMAT BERKAS -- SEJAK 16 SEP 2026
Sampai 15 Sep 2026 berkasnya JSON Stockbit (<KODE>_ALL_<tanggal>.json,
RUN_SUMMARY_ALL). Sejak 16 Sep unduhannya pindah ke ekspor .xls IPOT
(<KODE>.xls, RUN_BROKER_ACTIVITY_XLS) -- dan modul ini, yang cuma membaca
JSON, diam-diam BERHENTI di 15 Sep: folder tanggal baru tidak berisi satu
pun JSON, jadi mode bertambah menyimpulkan "tidak ada yang berubah" dan
mengembalikan tabel lama. Sidik Jari Broker dan Modal Bandar ikut membeku
seminggu tanpa satu pun galat; yang menangkapnya cuma umur berkas di
pemeriksaan kesehatan.

Isi keduanya SETARA. Dicek pada BBCA 15 Sep (hari satu-satunya yang punya
keduanya): 37 broker beli + 26 jual, lot dan nilai identik, harga rata-rata
sama sampai dua desimal (.xls membulatkan). baca_xls() mengubah .xls ke
bentuk data.broker_summary JSON, jadi SEMUA pembaca di atasnya -- termasuk
Broker Footprint & Broker Trend di utilities.py -- memakai jalur yang sama.
Kalau satu emiten punya keduanya di hari yang sama (rantai lama dijalankan
lagi), JSON yang dipakai dan .xls-nya dilewati: angkanya sama, dan dibaca
dua kali berarti terhitung ganda.
"""
try:
    from .runtime_paths import runtime_file as _runtime_file, market_file as _market_file, WEBSITE_DIR as _WEBSITE_DIR, PROJECT_DIR as _PROJECT_DIR, RUNTIME_DIR as _RUNTIME_DIR
except ImportError:
    from website.runtime_paths import runtime_file as _runtime_file, market_file as _market_file, WEBSITE_DIR as _WEBSITE_DIR, PROJECT_DIR as _PROJECT_DIR, RUNTIME_DIR as _RUNTIME_DIR
import os
import re
import glob
import json
import pickle
import time
from concurrent.futures import ThreadPoolExecutor

import pandas as pd

from .config import DAILY_PATH

ALL_DIR = os.path.join(DAILY_PATH, 'All')
CACHE_FILE = str(_runtime_file('', 'broker_ledger.pkl'))


def _angka(v):
    """'172,660' / '-235,232' / 6430.25 / '' -> float. Kosong -> 0.0."""
    s = str(v).strip().replace(',', '')
    if not s:
        return 0.0
    try:
        return float(s)
    except ValueError:
        return 0.0


def baca_xls(path):
    """
    Satu berkas .xls IPOT (Broker Activity Summary, mode Net) -> dict berbentuk
    SAMA dengan data.broker_summary di JSON Stockbit:
        {'symbol', 'brokers_buy': [{netbs_broker_code, netbs_stock_code,
         netbs_date, blot, bval, netbs_buy_avg_price}], 'brokers_sell': [...]}
    Sisi jual tetap NEGATIF seperti di JSON (-235,232), supaya pembaca yang
    sudah memakai abs() tidak perlu tahu sumbernya apa.

    Tata letak (dikonfirmasi pada berkas sungguhan, sama dengan
    utilities.broker()): baris 0 'Code <KODE> Start <tgl> End <tgl> Mode Net',
    baris 1 investor & board, baris 2 judul kolom NBY NBLot NBVal BAvg # NSL
    NSLot NSVal SAvg, data mulai baris 3. Kalau judul kolomnya bukan itu atau
    modenya bukan Net, berkasnya DITOLAK (melempar), bukan ditebak: angka
    bruto yang terbaca sebagai netto adalah angka yang diam-diam salah.

    KODE EMITEN DARI NAMA BERKAS, BUKAN SEL `Code`. Daily\All6-09-28    IFII.xls berisi broker IFII (harga ~211, cocok Summary IFII 212) tapi sel
    Code-nya tertulis EAST -- ekspor IPOT menyisakan kode emiten sebelumnya.
    Dulu sel itu yang dipakai: transaksi IFII masuk ke EAST (EAST hari itu
    88-90) dan IFII 28 Sep kosong. Pemeriksaan baris kembar cuma menangkap 7
    broker yang kebetulan ada di dua berkas; sisanya masuk diam-diam. Sel
    yang beda dikembalikan sebagai `kode_sel` supaya build() mencatatnya ke
    meta dan pemeriksaan kesehatan melaporkannya. Nama berkas yang bukan
    kode emiten 4 huruf (mis. salinan "BBCA (1).xls") tetap memakai sel.
    """
    import xlrd
    sh = xlrd.open_workbook(path).sheet_by_index(0)
    if sh.nrows < 3:
        return {'symbol': None, 'brokers_buy': [], 'brokers_sell': []}
    kepala = [str(x).strip() for x in sh.row_values(0)]
    judul = [str(x).strip() for x in sh.row_values(2)]
    if judul[:9] != ['NBY', 'NBLot', 'NBVal', 'BAvg', '#', 'NSL', 'NSLot', 'NSVal', 'SAvg']:
        raise ValueError('tata letak .xls tidak dikenal: %s' % judul[:9])
    if 'Mode' in kepala:
        mode = kepala[kepala.index('Mode') + 1] if kepala.index('Mode') + 1 < len(kepala) else ''
        if mode and mode != 'Net':
            raise ValueError('.xls mode %s, bukan Net' % mode)

    sel = (kepala[1] if len(kepala) > 1 else '').upper()
    nama = os.path.splitext(os.path.basename(path))[0].upper()
    kode = nama if re.fullmatch(r'[A-Z]{4}', nama) else (sel or nama)
    tanggal = kepala[3] if len(kepala) > 3 else ''
    if not RE_FOLDER_TANGGAL.match(tanggal):
        tanggal = os.path.basename(os.path.dirname(path))
    nd = tanggal.replace('-', '')

    beli, jual = [], []
    for r in range(3, sh.nrows):
        row = sh.row_values(r)
        if len(row) < 9:
            continue
        b = str(row[0]).strip()
        if b:
            beli.append({'netbs_broker_code': b, 'netbs_stock_code': kode, 'netbs_date': nd,
                         'blot': _angka(row[1]), 'bval': _angka(row[2]),
                         'netbs_buy_avg_price': _angka(row[3])})
        s = str(row[5]).strip()
        if s:
            jual.append({'netbs_broker_code': s, 'netbs_stock_code': kode, 'netbs_date': nd,
                         'slot': _angka(row[6]), 'sval': _angka(row[7]),
                         'netbs_sell_avg_price': _angka(row[8])})
    hasil = {'symbol': kode, 'brokers_buy': beli, 'brokers_sell': jual}
    if sel and sel != kode:
        hasil['kode_sel'] = sel
    return hasil


def ringkasan_broker(path):
    """data.broker_summary dari berkas JSON ATAU .xls -- satu pintu untuk
    semua pembaca berkas broker harian. None kalau tidak terbaca."""
    try:
        if path.lower().endswith('.xls'):
            return baca_xls(path)
        with open(path, encoding='utf-8') as fh:
            data = json.load(fh)
        return (data.get('data') or {}).get('broker_summary') or {}
    except Exception:
        return None


def berkas_tanggal(folder):
    """
    Berkas broker satu folder tanggal: JSON Stockbit kalau ada, .xls IPOT
    kalau tidak -- ditentukan per EMITEN, bukan per folder, supaya hari yang
    kebetulan punya keduanya tidak terbaca ganda.
    """
    js = glob.glob(os.path.join(folder, '*_ALL_*.json')) + glob.glob(os.path.join(folder, '*_FOREIGN_*.json'))
    punya = {os.path.basename(p).split('_')[0].upper() for p in js}
    xs = [p for p in glob.glob(os.path.join(folder, '*.xls'))
          if os.path.splitext(os.path.basename(p))[0].upper() not in punya]
    return js + xs


def _parse_file(path):
    """Satu berkas -> daftar baris. Berkas rusak dilewati, bukan menggagalkan."""
    return _parse_dgn_beda(path)[0]


def _parse_dgn_beda(path):
    """-> (baris, beda). `beda` = (tanggal folder, nama berkas, isi sel Code)
    kalau sel Code .xls tidak sama dengan nama berkasnya (lihat baca_xls), else None."""
    bs = ringkasan_broker(path)
    if bs is None:
        return [], None
    beda = None
    if bs.get('kode_sel'):
        beda = (os.path.basename(os.path.dirname(path)), os.path.basename(path), bs['kode_sel'])

    stock = bs.get('symbol')
    out = []
    # Sisi beli dan jual memakai NAMA FIELD YANG BERBEDA, dan nilai sisi jual
    # NEGATIF di sumbernya:
    #   beli : blot / bval / netbs_buy_avg_price     (positif)
    #   jual : slot / sval / netbs_sell_avg_price    (negatif, mis. "-195135")
    #
    # Versi pertama memakai `r.get('blot') or r.get('slot')` lalu membuang
    # baris dengan lot <= 0 -- akibatnya 99,4% baris JUAL terbuang diam-diam
    # (11.918 tersisa dari ~900 ribu), dan seluruh perhitungan "net" di modul
    # di atasnya sebenarnya cuma menghitung sisi beli. Ketahuan waktu net dan
    # bruto menghasilkan angka yang persis identik.
    for side, lot_key, val_key, price_key, src in (
            ('buy', 'blot', 'bval', 'netbs_buy_avg_price', 'brokers_buy'),
            ('sell', 'slot', 'sval', 'netbs_sell_avg_price', 'brokers_sell')):
        for r in (bs.get(src) or []):
            try:
                lot = abs(float(r.get(lot_key) or 0))
                val = abs(float(r.get(val_key) or 0))
                price = float(r.get(price_key) or 0)
            except (TypeError, ValueError):
                continue
            if lot <= 0:
                continue
            out.append((
                r.get('netbs_date'),
                (r.get('netbs_stock_code') or stock or '').upper(),
                (r.get('netbs_broker_code') or '').upper(),
                side, lot, val, price if price > 0 else None,
            ))
    return out, beda


# Nama folder tanggal di Daily\\All berformat YYYY-MM-DD.
RE_FOLDER_TANGGAL = re.compile(r'^\d{4}-\d{2}-\d{2}$')


def _folder_tanggal():
    """
    Folder tanggal di ALL_DIR, terurut, beserta mtime-nya.

    HANYA yang namanya benar-benar tanggal. Ini bukan kehati-hatian
    berlebihan: di ALL_DIR ada folder bernama `backup` berisi 831 berkas
    yang SEMUANYA bertanggal 20260907 -- salinan satu hari bursa. Versi
    lama modul ini menyapu semua subfolder tanpa memeriksa namanya, jadi
    7 September masuk dua kali dan setiap angka broker untuk hari itu
    terhitung ganda: net lot, nilai, harga rata-rata, semuanya.

    Tidak ada yang menangkapnya karena tidak ada yang rusak dan tidak ada
    yang lambat -- angkanya cuma salah.
    """
    hasil = []
    for d in sorted(os.listdir(ALL_DIR)):
        if not RE_FOLDER_TANGGAL.match(d):
            continue
        jalur = os.path.join(ALL_DIR, d)
        if os.path.isdir(jalur):
            hasil.append((d, os.path.getmtime(jalur)))
    return hasil


def build(force=False, max_workers=16, days=None, progress=None):
    """
    Baca berkas broker harian (JSON Stockbit atau .xls IPOT, lihat
    berkas_tanggal) jadi satu DataFrame, lalu cache.

    MODE BERTAMBAH (bawaan)
    Membaca ULANG hanya folder tanggal yang BARU atau yang mtime-nya
    berubah sejak cache dibuat, lalu menempelkannya ke tabel lama.

    Kenapa: satu hari bursa menambah ~962 berkas, tapi arsipnya sudah
    ~152 ribu berkas. Membaca semuanya tiap pagi memakan 142 detik --
    sepertiga dari seluruh pembangunan ulang harian, dan satu-satunya
    tugas yang menahan modal_bandar serta sidik_jari di belakangnya.
    Mode bertambah memangkasnya jadi hitungan detik, sebagian besar
    untuk menulis ulang pickle 128 MB.

    Penjaganya mtime FOLDER, bukan sekadar nama tanggal yang belum
    pernah dilihat. Kalau berkas hari lama diperbaiki belakangan --
    dan itu bukan hipotesis, pemeriksaan kesehatan melaporkan 154 dari
    962 berkas "kosong/kecil" tiap hari -- folder induknya ikut
    berubah mtime, jadi tanggal itu dibaca ulang dan barisnya
    ditimpa. Tanpa penjaga ini, perbaikan diam-diam tidak akan pernah
    masuk.

    force=True tetap membaca ulang SELURUH arsip. Itu jaring pengaman
    kalau mtime tidak bisa dipercaya (arsip disalin ulang, jam sistem
    mundur, cache dicurigai rusak) -- pantas dijalankan berkala, bukan
    tiap hari.

    days: batasi ke N hari terakhir (untuk uji cepat). None = semua.
    progress: callback(sudah, total) opsional.
    """
    if not os.path.isdir(ALL_DIR):
        raise RuntimeError('Folder broker tidak ditemukan: %s' % ALL_DIR)

    semua_tanggal = _folder_tanggal()
    if days:
        semua_tanggal = semua_tanggal[-days:]

    df_lama = None
    mtime_lama = {}
    beda_lama = []
    if not force and os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, 'rb') as fh:
                cached = pickle.load(fh)
            df_lama = cached.get('df')
            mtime_lama = cached.get('mtime_tanggal') or {}
            beda_lama = (cached.get('meta') or {}).get('kode_beda') or []
        except Exception:
            df_lama = None
            mtime_lama = {}

    # Cache lama tanpa peta mtime (dibangun sebelum mode bertambah ada)
    # tidak bisa dipercaya sebagian -- baca ulang semuanya sekali.
    if df_lama is not None and not mtime_lama:
        df_lama = None

    if df_lama is None:
        perlu = semua_tanggal
    else:
        perlu = [(d, m) for d, m in semua_tanggal
                 if abs(mtime_lama.get(d, -1) - m) > 1e-6]

    files = []
    for d, _m in perlu:
        files.extend(berkas_tanggal(os.path.join(ALL_DIR, d)))

    if df_lama is not None and not files:
        # Tidak ada yang berubah. Kembalikan apa adanya tanpa menulis ulang
        # pickle 128 MB.
        try:
            with open(CACHE_FILE, 'rb') as fh:
                cached = pickle.load(fh)
            return cached['df'], cached['meta']
        except Exception:
            pass

    t0 = time.time()
    rows, beda = [], []
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        for i, (hasil, b) in enumerate(ex.map(_parse_dgn_beda, files, chunksize=64)):
            if hasil:
                rows.extend(hasil)
            if b:
                beda.append(b)
            if progress and i % 5000 == 0:
                progress(i, len(files))

    df = pd.DataFrame(rows, columns=['date', 'stock', 'broker', 'side', 'lot', 'value', 'avg_price'])
    df = df[(df['stock'] != '') & (df['broker'] != '')]
    df['date'] = pd.to_datetime(df['date'], format='%Y%m%d', errors='coerce')
    df = df.dropna(subset=['date'])

    if df_lama is not None:
        # Buang tanggal yang baru saja dibaca ulang dari tabel lama, lalu
        # sambung. Dibuang per TANGGAL, bukan per baris, supaya hari yang
        # berkasnya diperbaiki benar-benar tergantikan dan tidak
        # meninggalkan baris kembar.
        dibaca = pd.to_datetime([d for d, _m in perlu], format='%Y-%m-%d', errors='coerce')
        dibaca = dibaca.dropna()
        sisa = df_lama[~df_lama['date'].isin(dibaca)]
        # Kategori dari dua sumber tidak bisa disambung langsung -- kembalikan
        # ke object dulu, lalu jadikan kategori sekali di akhir.
        for c in ('stock', 'broker', 'side'):
            if str(sisa[c].dtype) == 'category':
                sisa = sisa.copy()
                sisa[c] = sisa[c].astype('object')
        df = pd.concat([sisa, df], ignore_index=True)
        df = df.sort_values(['date', 'stock', 'broker']).reset_index(drop=True)

    for c in ('stock', 'broker', 'side'):
        df[c] = df[c].astype('category')

    meta = {
        'n_baris': int(len(df)),
        'n_broker': int(df['broker'].nunique()),
        'n_saham': int(df['stock'].nunique()),
        'n_hari': int(df['date'].nunique()),
        'dari': str(df['date'].min().date()) if len(df) else None,
        'sampai': str(df['date'].max().date()) if len(df) else None,
        'n_file': len(files),
        'durasi_detik': round(time.time() - t0, 1),
        'dibangun': time.strftime('%Y-%m-%d %H:%M'),
        'mode': 'penuh' if df_lama is None else 'bertambah',
        'tanggal_dibaca': len(perlu),
        # Berkas .xls yang sel Code-nya bukan nama berkasnya. Tanggal yang
        # tidak dibaca ulang membawa catatan lamanya.
        'kode_beda': sorted([b for b in beda_lama if df_lama is not None and b[0] not in {d for d, _m in perlu}]
                            + [list(b) for b in beda]),
    }

    try:
        with open(CACHE_FILE, 'wb') as fh:
            pickle.dump({'df': df, 'meta': meta,
                         'mtime_tanggal': {d: m for d, m in semua_tanggal}},
                        fh, protocol=4)
    except Exception:
        pass

    return df, meta


def load():
    """Ambil dari cache saja; None kalau belum pernah dibangun."""
    if not os.path.exists(CACHE_FILE):
        return None, None
    try:
        with open(CACHE_FILE, 'rb') as fh:
            cached = pickle.load(fh)
        return cached['df'], cached['meta']
    except Exception:
        return None, None


if __name__ == '__main__':
    def lapor(sudah, total):
        print('  %d / %d berkas...' % (sudah, total), flush=True)

    df, meta = build(force=True, progress=lapor)
    print(meta)
