"""
Sinyal scanner yang MASIH BERJALAN -- yang belum diketahui hasilnya.

KENAPA MODUL INI ADA
Delapan script riset di folder ini (big_jump_scan.py, divergence_scan.py,
dst.) sengaja membuang sinyal terbaru. Semuanya memakai pola:

    while i < n - max_fwd:      # berhenti `max_fwd` hari sebelum data habis

karena tugas mereka menghitung HASIL 20/40/60 hari ke depan, dan hasil itu
belum ada untuk sinyal yang baru muncul. Konsekuensinya CSV mereka
berhenti 1-3 bulan di belakang: per 30 Agustus 2026, slope_turn berhenti
di 29 Juli dan divergence di 29 Juni. Bagus untuk backtest, tidak bisa
dipakai memantau kandidat hari ini.

Modul ini menjalankan logika DETEKSI yang sama tanpa syarat forward,
sehingga sinyal sampai hari terakhir data ikut keluar -- kolom hasilnya
saja yang kosong. Skor pola tetap bisa dihitung karena skor tidak butuh
data masa depan, cuma volume dan kepemilikan pada saat sinyal muncul.

KENAPA BUKAN MENGUBAH SCRIPT ASLINYA
Script-script itu artefak riset yang hasilnya sudah divalidasi dan jadi
dasar skor di Scanner Lab. Menyisipkan mode live ke dalamnya berisiko
menggeser angka backtest yang justru jadi acuan. Jadi logikanya
direplikasi di sini, dan replikasi itu DIUJI kecocokannya terhadap CSV
asli pada periode yang beririsan (lihat verify_against_csv()) -- kalau
meleset, sinyal live tidak akan sebanding dengan backtest yang
mendasarinya.

Konstanta di bawah disalin dari script aslinya. Sumber kebenarannya tetap
di sana; kalau di sana diubah, di sini harus ikut diubah, dan
verify_against_csv() akan langsung ketahuan gagal kalau lupa.
"""
try:
    from .runtime_paths import runtime_file as _runtime_file, market_file as _market_file, WEBSITE_DIR as _WEBSITE_DIR, PROJECT_DIR as _PROJECT_DIR, RUNTIME_DIR as _RUNTIME_DIR
except ImportError:
    from website.runtime_paths import runtime_file as _runtime_file, market_file as _market_file, WEBSITE_DIR as _WEBSITE_DIR, PROJECT_DIR as _PROJECT_DIR, RUNTIME_DIR as _RUNTIME_DIR
import os
import threading
from datetime import datetime, timedelta

import pandas as pd
import numpy as np

from .config import DAILY_PATH

SUMMARY_DIR = os.path.join(DAILY_PATH, 'Summary')

# --- backtest_signal.py (slope_turn / sinyal 3 bintang) ---
SLOPE_DAYS = 5          # backtest_signal.py:37
PRICE_LOOKBACK = 10     # backtest_signal.py:38
MIN_HISTORY = PRICE_LOOKBACK + 1

# --- big_jump_scan.py ---
JUMP_LOOKBACK = 20
JUMP_PCT = 15
JUMP_VOL_MULT = 3
JUMP_COOLDOWN = 20

# --- divergence_scan.py ---
DIV_LOOKBACK = 20
DIV_Z = 2.0
DIV_COOLDOWN = 20

# --- slow_accum_scan.py ---
ACC_LOOKBACK = 60
ACC_COOLDOWN = 40
ACC_MAX_DRIFT_PCT = 20
ACC_MAX_SINGLE_DAY_SHARE = 0.3

# --- breakout_scan.py ---
BRK_SIDEWAYS_DAYS = 20
BRK_MAX_RANGE_PCT = 4
BRK_VOL_MULT = 3


def load_stock(stock):
    """
    Satu file Summary jadi DataFrame terurut.

    fillna(0) di sini WAJIB dan bukan pilihan gaya: loader di
    backtest_signal.py (yang dipakai semua script riset) melakukan
    `pd.read_csv(path).fillna(0)`. Membiarkan NaN akan mengubah rata-rata
    volume dan jumlah bergulir, sehingga sinyal yang dihasilkan di sini
    tidak lagi identik dengan CSV backtest yang jadi dasar skor. Terbukti:
    tanpa fillna(0), replikasi breakout memunculkan 8 sinyal yang tidak
    ada di CSV asli pada rentang tanggal yang sama.
    """
    path = os.path.join(SUMMARY_DIR, '%s_Summary.csv' % stock)
    if not os.path.exists(path):
        return None
    try:
        df = pd.read_csv(path).fillna(0)
    except Exception:
        return None
    if df.empty or 'Date' not in df.columns:
        return None
    df['Date'] = pd.to_datetime(df['Date'], format='%d-%b-%y', errors='coerce')
    df = df.dropna(subset=['Date']).sort_values('Date').reset_index(drop=True)
    for col in ['Open', 'High', 'Low', 'Close', 'Volume',
                'Net Top5 All Lot', 'Net Top5 Foreign Lot', 'Retail']:
        if col not in df.columns:
            df[col] = 0.0
        df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
    return df


def _all_stocks():
    if not os.path.isdir(SUMMARY_DIR):
        return []
    return sorted(name[:-len('_Summary.csv')]
                  for name in os.listdir(SUMMARY_DIR)
                  if name.endswith('_Summary.csv'))


# ------------------------------------------------------------- detektor
# Tiap detektor menerima `stop` -- indeks terakhir yang boleh diperiksa.
# Mode live memakai stop=n (sampai hari terakhir); verifikasi terhadap CSV
# asli memakai stop=n-forward supaya adil dibandingkan.

def detect_slope_turn(df, stock, stop):
    """
    Sinyal 3 bintang (backtest_signal.find_three_star_signals):
      1. Net Top5 5 hari terakhir > 0
      2. Retail 5 hari terakhir < 0
      3. Harga bergerak < 5% selama 10 hari terakhir
    Hanya AWAL rangkaian yang dihitung -- saham yang bertahan 3 bintang
    seminggu tidak dihitung sebagai 5-7 sinyal terpisah.
    """
    n = len(df)
    net_top5, retail, close = df['Net Top5 All Lot'], df['Retail'], df['Close']

    confidence = [None] * n
    for i in range(MIN_HISTORY - 1, n):
        lo = max(0, i - SLOPE_DAYS + 1)
        price_then = close.iloc[i - PRICE_LOOKBACK]
        flat = price_then != 0 and abs(
            (close.iloc[i] - price_then) / price_then * 100) < 5
        confidence[i] = sum([net_top5.iloc[lo:i + 1].sum() > 0,
                             retail.iloc[lo:i + 1].sum() < 0,
                             bool(flat)])

    rows = []
    for i in range(MIN_HISTORY - 1, stop):
        if confidence[i] != 3:
            continue
        prev = confidence[i - 1] if i - 1 >= MIN_HISTORY - 1 else None
        if prev == 3:
            continue
        entry = close.iloc[i]
        if entry == 0 or pd.isna(entry):
            continue
        rows.append({'stock': stock, 'signal_date': df['Date'].iloc[i],
                     'entry_close': float(entry), 'scanner': 'slope_turn'})
    return rows


def detect_big_jump(df, stock, stop):
    """Lompatan harga >=15% dalam sehari disertai volume >=3x rata-rata 20 hari."""
    n = len(df)
    close, open_, volume = df['Close'], df['Open'], df['Volume']
    rows, i, last = [], JUMP_LOOKBACK, -10**9
    while i < stop:
        prev_close, entry = close.iloc[i - 1], close.iloc[i]
        if prev_close <= 0 or entry <= 0 or pd.isna(prev_close) or pd.isna(entry):
            i += 1
            continue
        jump = (entry - prev_close) / prev_close * 100
        avg_vol = volume.iloc[i - JUMP_LOOKBACK:i].mean()
        vol_mult = volume.iloc[i] / avg_vol if avg_vol and avg_vol > 0 else 0
        if jump >= JUMP_PCT and vol_mult >= JUMP_VOL_MULT and i - last >= JUMP_COOLDOWN:
            combined = pd.concat([open_.iloc[i - JUMP_LOOKBACK:i],
                                  close.iloc[i - JUMP_LOOKBACK:i]])
            cmin = combined.min()
            rows.append({
                'stock': stock, 'signal_date': df['Date'].iloc[i],
                'entry_close': float(entry), 'scanner': 'big_jump',
                'day_jump_pct': round(jump, 2),
                'scanner_vol_mult': round(float(vol_mult), 2),
                'sideways_range_pct': round((combined.max() - cmin) / cmin * 100, 2)
                                      if cmin and cmin > 0 else None,
            })
            last = i
        i += 1
    return rows


def detect_divergence(df, stock, stop):
    """Top5 domestik memborong ekstrem (z>=2) saat asing melepas ekstrem (z<=-2)."""
    n = len(df)
    close = df['Close']
    domestic = df['Net Top5 All Lot'] - df['Net Top5 Foreign Lot']
    foreign = df['Net Top5 Foreign Lot']

    def z(series, i):
        w = series.iloc[i - DIV_LOOKBACK:i]
        mean, std = w.mean(), w.std()
        if std == 0 or pd.isna(std):
            return None
        return (series.iloc[i] - mean) / std

    rows, i, last = [], DIV_LOOKBACK, -10**9
    while i < stop:
        dz, fz = z(domestic, i), z(foreign, i)
        entry = close.iloc[i]
        if (dz is not None and fz is not None and not pd.isna(dz) and not pd.isna(fz)
                and dz >= DIV_Z and fz <= -DIV_Z and entry > 0
                and i - last >= DIV_COOLDOWN):
            rows.append({'stock': stock, 'signal_date': df['Date'].iloc[i],
                         'entry_close': float(entry), 'scanner': 'divergence',
                         'domestic_z': round(float(dz), 2),
                         'foreign_z': round(float(fz), 2)})
            last = i
        i += 1
    return rows


def detect_slow_accum(df, stock, stop):
    """
    Akumulasi bertahap 60 hari: Net Top5 positif, tidak didominasi satu
    hari lonjakan (<=30% dari total), dan harganya belum lari (<=20%).
    """
    close, net_top5, retail = df['Close'], df['Net Top5 All Lot'], df['Retail']
    rows, i, last = [], ACC_LOOKBACK, -10**9
    while i < stop:
        w_net = net_top5.iloc[i - ACC_LOOKBACK:i]
        net_sum = w_net.sum()
        if net_sum <= 0 or pd.isna(net_sum):
            i += 1
            continue
        share = w_net.abs().max() / net_sum
        if share > ACC_MAX_SINGLE_DAY_SHARE:
            i += 1
            continue
        price_then, price_now = close.iloc[i - ACC_LOOKBACK], close.iloc[i]
        if price_then <= 0 or price_now <= 0 or pd.isna(price_then) or pd.isna(price_now):
            i += 1
            continue
        drift = (price_now - price_then) / price_then * 100
        if abs(drift) > ACC_MAX_DRIFT_PCT or i - last < ACC_COOLDOWN:
            i += 1
            continue
        rows.append({
            'stock': stock, 'signal_date': df['Date'].iloc[i],
            'entry_close': float(price_now), 'scanner': 'slow_accum',
            'net_top5_60d_sum': round(float(net_sum), 1),
            'retail_60d_sum': round(float(retail.iloc[i - ACC_LOOKBACK:i].sum()), 1),
            'price_drift_60d_pct': round(float(drift), 2),
        })
        last = i
        i += 1
    return rows


def detect_breakout(df, stock, stop):
    """Keluar dari rentang sempit (<=4% selama 20 hari) dengan volume >=3x dan harga naik."""
    close, open_, volume = df['Close'], df['Open'], df['Volume']
    rows, i = [], BRK_SIDEWAYS_DAYS
    while i < stop:
        combined = pd.concat([open_.iloc[i - BRK_SIDEWAYS_DAYS:i],
                              close.iloc[i - BRK_SIDEWAYS_DAYS:i]])
        cmin = combined.min()
        if cmin is None or pd.isna(cmin) or cmin <= 0:
            i += 1
            continue
        range_pct = (combined.max() - cmin) / cmin * 100
        avg_vol = volume.iloc[i - BRK_SIDEWAYS_DAYS:i].mean()
        entry = close.iloc[i]
        if (range_pct <= BRK_MAX_RANGE_PCT and avg_vol and avg_vol > 0
                and volume.iloc[i] >= BRK_VOL_MULT * avg_vol
                and entry > close.iloc[i - 1] and entry != 0 and not pd.isna(entry)):
            rows.append({
                'stock': stock, 'signal_date': df['Date'].iloc[i],
                'entry_close': float(entry), 'scanner': 'breakout',
                'scanner_vol_mult': round(float(volume.iloc[i] / avg_vol), 2),
                'sideways_range_pct': round(float(range_pct), 2),
            })
        i += 1
    return rows


DETECTORS = {
    'slope_turn': detect_slope_turn,
    'big_jump': detect_big_jump,
    'divergence': detect_divergence,
    'slow_accum': detect_slow_accum,
    'breakout': detect_breakout,
}

# Berapa hari bursa ke depan yang dibutuhkan tiap scanner untuk tahu
# hasilnya. Dipakai untuk menandai sinyal mana yang masih "berjalan".
FORWARD_NEEDED = {
    'slope_turn': 20, 'big_jump': 20, 'breakout': 20,
    'divergence': 60, 'slow_accum': 60,
}


def scan_live(days_back=60, scanners=None, stocks=None, days_list=None):
    """
    Jalankan semua detektor sampai hari terakhir data, kembalikan sinyal
    dalam `days_back` hari kalender terakhir.

    Tiap sinyal ditandai `pending` -- True kalau umurnya belum cukup untuk
    tahu hasilnya, yang berarti sinyal itu memang tidak akan pernah muncul
    di CSV backtest.

    `days_list` mengembalikan {days_back: DataFrame} dari SATU lintasan.
    Boleh begitu karena `days_back` cuma dipakai untuk satu hal di bawah:
    menyaring `signal_date < cutoff`. Memuat 881 CSV dan menjalankan tiap
    detektor sama persis untuk 14, 60, maupun 90 -- hasil 90 hari adalah
    superset tepat dari 60 dan 14, dan kolom `pending` tidak bergantung
    pada `days_back` sama sekali (ia dihitung dari `last_data_date`).
    Jadi memindai tiga kali cuma membuang ~100 detik untuk jawaban yang
    identik. Dipakai oleh warm().
    """
    stocks = stocks or _all_stocks()
    wanted = scanners or list(DETECTORS)
    daftar = sorted(set(days_list or [days_back]), reverse=True)
    terluas = daftar[0]
    jangkar = None
    cutoff = None
    rows = []
    last_data_date = None

    for stock in stocks:
        df = load_stock(stock)
        if df is None or len(df) < ACC_LOOKBACK + 2:
            continue
        n = len(df)
        if last_data_date is None or df['Date'].iloc[-1] > last_data_date:
            last_data_date = df['Date'].iloc[-1]
        if cutoff is None:
            # Jangkarnya emiten pertama yang lolos, bukan tanggal terbaru
            # global -- perilaku asli, dipertahankan apa adanya supaya
            # hasil warm() identik dengan pindaian terpisah.
            jangkar = df['Date'].iloc[-1]
            cutoff = jangkar - timedelta(days=terluas)

        for key in wanted:
            detector = DETECTORS.get(key)
            if detector is None:
                continue
            try:
                found = detector(df, stock, n)
            except Exception:
                continue
            for row in found:
                if cutoff is not None and row['signal_date'] < cutoff:
                    continue
                rows.append(row)

    if not rows:
        if days_list is None:
            return pd.DataFrame(), last_data_date
        return {d: pd.DataFrame() for d in daftar}, last_data_date

    out = pd.DataFrame(rows)
    # Umur sinyal dalam hari BURSA, bukan kalender -- itu yang menentukan
    # apakah hasilnya sudah bisa dihitung.
    trading_days = sorted(set(out['signal_date']))
    out['pending'] = out.apply(
        lambda r: _bars_since(r['signal_date'], last_data_date) < FORWARD_NEEDED.get(r['scanner'], 20),
        axis=1)
    # kind='mergesort' (stabil) BUKAN gaya-gayaan: quicksort default
    # mengurutkan baris yang signal_date-nya SAMA secara sembarang, jadi
    # dua pindaian atas data yang sama bisa menghasilkan urutan berbeda.
    # Itu juga yang membuat hasil turunan days_list tidak bisa dibuktikan
    # sama dengan pindaian terpisah. Urutan stabil = penyaringan superset
    # menghasilkan urutan yang persis sama dengan memindai subsetnya.
    out = out.sort_values('signal_date', ascending=False,
                          kind='mergesort').reset_index(drop=True)
    if days_list is None:
        return out, last_data_date
    hasil = {}
    for d in daftar:
        batas = jangkar - timedelta(days=d) if jangkar is not None else None
        hasil[d] = (out if batas is None
                    else out[out['signal_date'] >= batas].reset_index(drop=True))
    return hasil, last_data_date


_CALENDAR = None


def _bars_since(signal_date, last_date):
    """
    Perkiraan jumlah hari bursa antara dua tanggal, memakai kalender hari
    bursa nyata dari salah satu file Summary -- bukan hari kalender,
    karena akhir pekan dan libur bursa akan membuat hitungannya meleset.
    """
    global _CALENDAR
    if _CALENDAR is None:
        for stock in _all_stocks()[:20]:
            df = load_stock(stock)
            if df is not None and len(df) > 100:
                _CALENDAR = list(df['Date'])
                break
        if _CALENDAR is None:
            _CALENDAR = []
    if not _CALENDAR:
        return (last_date - signal_date).days
    return sum(1 for d in _CALENDAR if signal_date < d <= last_date)


def verify_against_csv(scanner, csv_name, sample_stocks=60):
    """
    Uji bahwa detektor di sini menghasilkan sinyal yang SAMA dengan script
    riset aslinya pada rentang tanggal yang beririsan.

    Ini bukan formalitas: skor di Scanner Lab berasal dari backtest CSV
    itu. Kalau detektor di sini meleset walau sedikit, sinyal live tidak
    lagi sebanding dengan statistik yang mendasarinya, dan skornya jadi
    menyesatkan.

    HASIL SAAT DITULIS (sampel 40 emiten per scanner):
    kelimanya `hanya_di_asli = 0` -- tidak satu pun sinyal asli terlewat,
    491 sinyal cocok seluruhnya. Yang muncul cuma segelintir sinyal
    TAMBAHAN, dan itu sudah terjelaskan: 838 dari 881 file Summary (95%)
    dimodifikasi setelah CSV scanner dibuat, jadi data historisnya memang
    sudah berubah/diisi ulang sejak saat itu. Kesalahan logika hampir
    pasti juga akan membuat sinyal HILANG, bukan cuma bertambah -- nol
    sinyal hilang di lima detektor berbeda adalah bukti kuat replikasinya
    setia.
    """
    path = str(_runtime_file('', csv_name))
    if not os.path.exists(path):
        return {'ok': False, 'message': 'CSV asli tidak ada: %s' % csv_name}

    original = pd.read_csv(path, usecols=['stock', 'signal_date'])
    original['signal_date'] = pd.to_datetime(original['signal_date'], errors='coerce')
    original = original.dropna().drop_duplicates()
    original['stock'] = original['stock'].astype(str).str.upper()

    stocks = sorted(original['stock'].unique())[:sample_stocks]
    orig_set = set(map(tuple, original[original['stock'].isin(stocks)]
                       [['stock', 'signal_date']].values))

    forward = FORWARD_NEEDED.get(scanner, 20)
    mine = set()
    for stock in stocks:
        df = load_stock(stock)
        if df is None:
            continue
        # stop = n - forward, meniru batas script asli supaya adil.
        for row in DETECTORS[scanner](df, stock, max(0, len(df) - forward)):
            mine.add((stock, row['signal_date']))

    only_orig = orig_set - mine
    only_mine = mine - orig_set
    return {
        'ok': not only_orig and not only_mine,
        'scanner': scanner,
        'stocks_diuji': len(stocks),
        'sinyal_asli': len(orig_set),
        'sinyal_replikasi': len(mine),
        'cocok': len(orig_set & mine),
        'hanya_di_asli': len(only_orig),
        'hanya_di_replikasi': len(only_mine),
        'contoh_beda': [(s, str(d.date())) for s, d in list(only_orig)[:3]],
    }


# ------------------------------------------------------------------ cache
# scan_live() memakan ~48 detik untuk 881 emiten -- terlalu lama untuk satu
# request web. Hasilnya disimpan, dan dianggap basi begitu ada file Summary
# yang lebih baru daripada waktu cache dibuat (artinya data hariannya sudah
# diperbarui, jadi sinyalnya bisa berubah).
#
# SATU FILE PER days_back, bukan satu file bersama -- pemanggil yang beda
# pakai days_back beda (Ringkasan Watchlist=14, Halaman Saham/Watchlist/
# Screens=90, Scanner Lab=60). Dulu ketiganya berebut SATU file cache: buka
# Ringkasan Watchlist lalu buka Watchlist biasa akan langsung memicu
# pemindaian ulang penuh (~48-60 detik) karena "days_back beda" dianggap
# basi -- dan karena dev server Flask default satu-thread, pemindaian itu
# memblokir SELURUH app buat semua orang, bukan cuma halaman yang diklik.
# Nyata terjadi & dilaporkan sebagai "aplikasi jadi tidak responsif".
def _cache_file(days_back):
    return str(_runtime_file('', 'live_scan_cache_%d.pkl' % days_back))


def _newest_summary_mtime():
    if not os.path.isdir(SUMMARY_DIR):
        return 0
    newest = 0
    for name in os.listdir(SUMMARY_DIR):
        if not name.endswith('_Summary.csv'):
            continue
        mtime = os.path.getmtime(os.path.join(SUMMARY_DIR, name))
        if mtime > newest:
            newest = mtime
    return newest


def cached_scan_if_ready(days_back=60):
    """Sama seperti cached_scan(), TAPI tidak pernah memindai kalau cache
    belum ada/basi - balikin None saja. Dipakai pemanggil yang harus tidak
    pernah blocking (mis. dashboard "/") supaya request pengunjung tidak
    ikut memicu cold-scan ~50 detik selagi thread warmup ( _start_cache_warmup
    di __init__.py) masih mengisi cache yang sama di background."""
    import pickle
    cache_file = _cache_file(days_back)
    if not os.path.exists(cache_file):
        return None
    try:
        with open(cache_file, 'rb') as fh:
            cached = pickle.load(fh)
        fresh = cached.get('built_at', 0) >= _newest_summary_mtime()
        if fresh and cached.get('days_back') == days_back:
            cached['from_cache'] = True
            return cached
    except Exception:
        pass
    return None


def cached_scan(days_back=60, force=False):
    """Sinyal live dari cache; dipindai ulang kalau basi atau dipaksa."""
    import pickle
    if not force:
        ready = cached_scan_if_ready(days_back)
        if ready is not None:
            return ready

    df, last_date = scan_live(days_back=days_back)
    payload = {'df': df, 'last_data_date': last_date, 'days_back': days_back,
               'built_at': datetime.now().timestamp(), 'from_cache': False}
    try:
        with open(_cache_file(days_back), 'wb') as fh:
            pickle.dump(payload, fh)
    except Exception:
        pass
    return payload


_bg_lock = threading.Lock()
_bg_running = False


def _rescan_in_background():
    """Jalankan warm() di thread terpisah, paling banyak satu sekaligus."""
    global _bg_running
    with _bg_lock:
        if _bg_running:
            return
        _bg_running = True

    def _jalan():
        global _bg_running
        try:
            warm()
        except Exception:
            pass
        finally:
            with _bg_lock:
                _bg_running = False

    threading.Thread(target=_jalan, daemon=True, name='live_scan_rescan').start()


def cached_scan_stale_ok(days_back=90):
    """
    Versi cached_scan() yang TIDAK PERNAH memindai di dalam request.

    Cache segar -> dipakai. Cache basi -> tetap dipakai (ditandai
    'stale': True) sementara pindaian ulang jalan di background. Tidak ada
    cache sama sekali -> None (juga memicu pindaian background).

    Kenapa perlu: 23 Sep 2026, 58 file Summary ditulis ulang jam 22:46,
    SETELAH pemeriksa kesehatan memanaskan cache jam ~22:30. Semua cache
    langsung basi dan kartu Ringkasan Sinyal membayar pindaian ~50 detik
    di dalam request. Sinyal yang telat beberapa menit jauh lebih baik
    daripada kartu yang menggantung semenit.
    """
    import pickle
    ready = cached_scan_if_ready(days_back)
    if ready is not None:
        return ready
    _rescan_in_background()
    try:
        with open(_cache_file(days_back), 'rb') as fh:
            cached = pickle.load(fh)
        if cached.get('days_back') == days_back:
            cached['from_cache'] = True
            cached['stale'] = True
            return cached
    except Exception:
        pass
    return None


def warm(days_list=(14, 60, 90)):
    """
    Hangatkan beberapa cache days_back dari SATU pindaian.

    Dipakai pemeriksa kesehatan harian. Sebelumnya ia memanggil
    cached_scan(force=True) tiga kali dan membayar pemuatan 881 CSV tiga
    kali (~150 detik) untuk sinyal yang sama persis; lihat catatan di
    scan_live tentang kenapa days_back cuma penyaring di akhir.

    Mengembalikan {days_back: jumlah_baris}.
    """
    import pickle
    daftar = sorted(set(days_list), reverse=True)
    per_hari, last_date = scan_live(days_list=daftar)
    built_at = datetime.now().timestamp()
    ringkas = {}
    for d in daftar:
        df = per_hari[d]
        payload = {'df': df, 'last_data_date': last_date, 'days_back': d,
                   'built_at': built_at, 'from_cache': False}
        with open(_cache_file(d), 'wb') as fh:
            pickle.dump(payload, fh)
        ringkas[d] = len(df)
    return ringkas
