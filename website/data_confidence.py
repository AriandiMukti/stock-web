"""
Skor kepercayaan data per emiten.

KENAPA INI ADA
Di seluruh app ini, saham dengan riwayat 28 hari ditampilkan PERSIS SAMA
meyakinkannya dengan saham yang punya 158 hari. Angka "skor 0,72" atau
"retail 99,5%" terlihat sama tegaknya, padahal yang satu dihitung dari data
lengkap dan yang lain dari potongan data yang bolong.

Sesi pembangunan app ini sendiri sudah menemukan beberapa masalah nyata:
tabel pemegang saham sempat dobel hitung, satuan persen insider tidak
konsisten antar baris, 68% harga transaksi insider kosong, free float resmi
cuma tersedia untuk 43 dari 1.010 emiten, dan panjang riwayat harga
bervariasi 28-158 baris. Semua itu tidak pernah terlihat di UI.

Modul ini menghitung SATU angka 0-100 per emiten dari kelengkapan datanya,
plus daftar apa yang kurang -- supaya angka rapuh bisa dibedakan dari angka
tegak sebelum dipakai mengambil keputusan.

YANG DIUKUR (bobot)
    Riwayat harga        30  -- jumlah baris Summary; penuh di >=120 baris
    Kelengkapan kolom    25  -- % sel terisi pada 20 baris terakhir untuk
                               kolom yang benar-benar dipakai app ini
    Kesegaran            15  -- selisih hari data terakhir vs bursa
    Bulan KSEI           15  -- jumlah bulan kepemilikan; penuh di >=6 bulan
    Registri IDX          8  -- ada tabel pemegang >=5% atau tidak
    Free float resmi      7  -- ada angka LBRPE/registri atau tidak

YANG TIDAK DIUKUR
Ini mengukur KELENGKAPAN, bukan KEBENARAN. Data bisa lengkap tapi salah
(kasus dobel hitung tabel pemegang dulu lolos 100% kelengkapan). Skor tinggi
berarti "tidak ada yang kosong", bukan "sudah diverifikasi benar".
"""
try:
    from .runtime_paths import runtime_file as _runtime_file, market_file as _market_file, WEBSITE_DIR as _WEBSITE_DIR, PROJECT_DIR as _PROJECT_DIR, RUNTIME_DIR as _RUNTIME_DIR
except ImportError:
    from website.runtime_paths import runtime_file as _runtime_file, market_file as _market_file, WEBSITE_DIR as _WEBSITE_DIR, PROJECT_DIR as _PROJECT_DIR, RUNTIME_DIR as _RUNTIME_DIR
import os
import glob
import pickle
import time
from datetime import datetime

import pandas as pd

from .config import DAILY_PATH

SUMMARY_DIR = os.path.join(DAILY_PATH, 'Summary')
CACHE_FILE = str(_runtime_file('', 'data_confidence_cache.pkl'))


def _sumber_terbaru():
    """
    mtime paling baru dari SEMUA yang dibaca scan(): berkas Summary dan
    seluruh pohon kepemilikan (KSEI, registri IDX, LBRPE, overrides).

    KENAPA BUKAN TTL
    Dulu di sini ada CACHE_TTL = 6 jam. Umur bukan ukuran yang benar:
    datanya berubah SEKALI sehari, saat unduhan pagi selesai, dan tidak
    berubah lagi sampai besok. TTL 6 jam berarti cache yang dibangun
    RUN_KESEHATAN.bat pukul 20.24 kedaluwarsa sekitar 02.24 -- di tengah
    hari kerja, di luar jendela batch -- lalu pengguna pertama sesudah
    itu membayar pembangunan ulangnya sendiri. Terukur 70 detik, karena
    scan() memanggil build_ownership() untuk tiap emiten dan sejak
    registri IDX lengkap carve-out benar-benar bekerja untuk 881 emiten,
    bukan 46.

    Aturan yang benar sama dengan live_scan.cached_scan(): basi begitu
    ada berkas SUMBER yang lebih baru daripada cache-nya. Kalau sumbernya
    tidak berubah, cache tetap sah berapa pun umurnya -- dan begitu
    unduhan pagi menyentuh Summary, ia basi seketika tanpa perlu
    menunggu jam dinding.

    Ongkosnya dua pemindaian direktori, ~0,05 detik untuk 1.820 berkas.
    """
    terbaru = 0.0
    try:
        for nama in os.listdir(SUMMARY_DIR):
            if not nama.endswith('_Summary.csv'):
                continue
            m = os.path.getmtime(os.path.join(SUMMARY_DIR, nama))
            if m > terbaru:
                terbaru = m
    except OSError:
        pass

    try:
        from .config import OWNERSHIP_PATH
        for akar, _dirs, berkas in os.walk(OWNERSHIP_PATH):
            for nama in berkas:
                try:
                    m = os.path.getmtime(os.path.join(akar, nama))
                except OSError:
                    continue
                if m > terbaru:
                    terbaru = m
    except Exception:
        pass

    return terbaru

BOBOT = {
    'riwayat': 30,
    'kolom': 25,
    'segar': 15,
    'ksei': 15,
    'registri': 8,
    'free_float': 7,
}

# Kolom yang benar-benar dipakai modul-modul app ini. Tidak semua kolom
# Summary dinilai -- yang tidak dipakai tidak menurunkan kepercayaan.
KOLOM_PENTING = ['Close', 'Volume', 'Net Top5 All Lot', 'Retail', 'Total Buyer', 'Total Seller']

RIWAYAT_PENUH = 120   # baris
KSEI_PENUH = 6        # bulan
SEGAR_TOLERANSI = 3   # hari bursa; lebih dari ini mulai dipotong

LABELS = [
    (85, 'tinggi', 'hijau'),
    (65, 'sedang', 'kuning'),
    (0, 'rendah', 'merah'),
]


def _label(score):
    for ambang, label, verdict in LABELS:
        if score >= ambang:
            return label, verdict
    return 'rendah', 'merah'


def _read(stock):
    path = os.path.join(SUMMARY_DIR, '%s_Summary.csv' % stock)
    if not os.path.exists(path):
        return None
    try:
        df = pd.read_csv(path)
    except Exception:
        return None
    if 'Date' not in df.columns or df.empty:
        return None
    df['Date'] = pd.to_datetime(df['Date'], format='%d-%b-%y', errors='coerce')
    df = df.dropna(subset=['Date']).sort_values('Date').reset_index(drop=True)
    return df if len(df) else None


def _ksei_info():
    """{ticker: {'bulan': n, 'terakhir': '2026-08'}} dari seluruh berkas KSEI."""
    from .ownership import load_ksei_months
    out = {}
    for payload in load_ksei_months():
        month = payload.get('month')
        for ticker in (payload.get('securities') or {}):
            info = out.setdefault(ticker, {'bulan': 0, 'terakhir': None})
            info['bulan'] += 1
            info['terakhir'] = month
    return out


def measure(stock, df=None, ksei=None, market_last=None, own=None):
    """
    Skor kepercayaan satu emiten. `own` = hasil build_ownership() kalau sudah
    ada (dipakai untuk registri & free float); kalau None, dua komponen itu
    dinilai dari ketiadaan datanya saja.
    """
    if df is None:
        df = _read(stock)
    if df is None:
        return None

    kurang = []
    rincian = {}

    # --- Riwayat harga ---
    n_baris = len(df)
    r_riwayat = min(1.0, n_baris / float(RIWAYAT_PENUH))
    rincian['riwayat'] = {'nilai': n_baris, 'satuan': 'baris', 'rasio': round(r_riwayat, 3)}
    if n_baris < 60:
        kurang.append('Riwayat harga cuma %d baris (ideal >=%d)' % (n_baris, RIWAYAT_PENUH))

    # --- Kelengkapan kolom pada 20 baris terakhir ---
    win = df.tail(20)
    terisi, total, kolom_hilang = 0, 0, []
    for col in KOLOM_PENTING:
        if col not in win.columns:
            kolom_hilang.append(col)
            total += len(win)
            continue
        s = pd.to_numeric(win[col], errors='coerce')
        terisi += int(s.notna().sum())
        total += len(s)
    r_kolom = (terisi / total) if total else 0.0
    rincian['kolom'] = {'nilai': round(r_kolom * 100, 1), 'satuan': '% terisi', 'rasio': round(r_kolom, 3)}
    if kolom_hilang:
        kurang.append('Kolom tidak ada: ' + ', '.join(kolom_hilang))
    elif r_kolom < 0.95:
        kurang.append('Ada sel kosong di 20 baris terakhir (%.0f%% terisi)' % (r_kolom * 100))

    # --- Kesegaran ---
    last = df['Date'].max()
    if market_last is not None and pd.notna(last):
        selisih = int((market_last - last).days)
    else:
        selisih = 0
    r_segar = 1.0 if selisih <= SEGAR_TOLERANSI else max(0.0, 1.0 - (selisih - SEGAR_TOLERANSI) / 20.0)
    rincian['segar'] = {'nilai': selisih, 'satuan': 'hari tertinggal', 'rasio': round(r_segar, 3)}
    if selisih > SEGAR_TOLERANSI:
        kurang.append('Data terakhir tertinggal %d hari dari bursa' % selisih)

    # --- Bulan KSEI ---
    kinfo = (ksei or {}).get(stock) or {}
    bulan = kinfo.get('bulan', 0)
    r_ksei = min(1.0, bulan / float(KSEI_PENUH))
    rincian['ksei'] = {'nilai': bulan, 'satuan': 'bulan', 'rasio': round(r_ksei, 3)}
    if bulan == 0:
        kurang.append('Tidak ada data kepemilikan KSEI')
    elif bulan < 3:
        kurang.append('Data KSEI cuma %d bulan' % bulan)

    # --- Registri IDX & free float ---
    punya_registri = bool(own and own.get('holders'))
    punya_ff = bool(own and own.get('free_float') is not None)
    rincian['registri'] = {'nilai': 'ada' if punya_registri else 'tidak', 'satuan': '', 'rasio': 1.0 if punya_registri else 0.0}
    rincian['free_float'] = {'nilai': 'ada' if punya_ff else 'tidak', 'satuan': '', 'rasio': 1.0 if punya_ff else 0.0}
    if not punya_registri:
        kurang.append('Tidak ada registri pemegang >=5% (persentase besar jadi perkiraan)')
    if not punya_ff:
        kurang.append('Tidak ada free float resmi (dipakai scripless sebagai gantinya)')

    skor = sum(BOBOT[k] * rincian[k]['rasio'] for k in BOBOT)
    skor = round(skor, 1)
    label, verdict = _label(skor)

    return {
        'stock': stock,
        'skor': skor,
        'label': label,
        'verdict': verdict,
        'rincian': rincian,
        'kurang': kurang,
        'n_baris': n_baris,
        'bulan_ksei': bulan,
        'tanggal_terakhir': last.strftime('%Y-%m-%d') if pd.notna(last) else None,
        'tertinggal_hari': selisih,
    }


def scan(force=False, with_ownership=True):
    """
    Skor seluruh emiten yang punya berkas Summary.

    with_ownership=False melewati pemanggilan build_ownership() per emiten
    (jauh lebih cepat) dengan konsekuensi komponen registri & free float
    dinilai nol untuk semua -- dipakai kalau cuma butuh gambaran kasar.
    """
    if not force and os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, 'rb') as fh:
                cached = pickle.load(fh)
            if cached.get('ts', 0) >= _sumber_terbaru():
                result = dict(cached['result'])
                result['from_cache'] = True
                return result
        except Exception:
            pass

    files = glob.glob(os.path.join(SUMMARY_DIR, '*_Summary.csv'))
    ksei = _ksei_info()

    frames = {}
    market_last = None
    for path in files:
        stock = os.path.basename(path)[:4]
        df = _read(stock)
        if df is None:
            continue
        frames[stock] = df
        last = df['Date'].max()
        if pd.notna(last) and (market_last is None or last > market_last):
            market_last = last

    own_map = {}
    if with_ownership:
        from .ownership import build_ownership
        for stock in frames:
            try:
                o = build_ownership(stock)
                if o.get('available'):
                    own_map[stock] = o
            except Exception:
                pass

    rows = []
    for stock, df in frames.items():
        row = measure(stock, df=df, ksei=ksei, market_last=market_last,
                      own=own_map.get(stock))
        if row:
            rows.append(row)

    rows.sort(key=lambda r: r['skor'])

    counts = {'tinggi': 0, 'sedang': 0, 'rendah': 0}
    for r in rows:
        counts[r['label']] += 1

    result = {
        'available': True,
        'rows': rows,
        'total': len(rows),
        'counts': counts,
        'bobot': dict(BOBOT),
        'market_last': market_last.strftime('%Y-%m-%d') if market_last is not None else None,
        'rata2': round(sum(r['skor'] for r in rows) / len(rows), 1) if rows else 0.0,
        'as_of': time.strftime('%Y-%m-%d %H:%M'),
        'from_cache': False,
    }

    try:
        with open(CACHE_FILE, 'wb') as fh:
            pickle.dump({'ts': time.time(), 'result': result}, fh)
    except Exception:
        pass

    return result


def for_stock(stock):
    """Skor satu emiten -- dipakai lencana di Halaman Saham."""
    from .ownership import build_ownership
    df = _read(stock)
    if df is None:
        return None
    try:
        own = build_ownership(stock)
        own = own if own.get('available') else None
    except Exception:
        own = None

    # Tanggal bursa terakhir diambil dari cache scan kalau ada, supaya tidak
    # perlu membaca 881 berkas cuma untuk satu emiten.
    market_last = None
    try:
        if os.path.exists(CACHE_FILE):
            with open(CACHE_FILE, 'rb') as fh:
                cached = pickle.load(fh)
            ml = (cached.get('result') or {}).get('market_last')
            if ml:
                market_last = pd.Timestamp(datetime.strptime(ml, '%Y-%m-%d'))
    except Exception:
        pass

    return measure(stock, df=df, ksei=_ksei_info(), market_last=market_last, own=own)
