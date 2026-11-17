"""
Aktivitas Insider -- transaksi direksi/komisaris/pengendali yang selama
ini sudah ditarik rutin (InsiderActivityAll.py di <external-tools>/BDM\\,
dari Stockbit) ke <market-data>/Monthly\\All\\<Bulan>\\<KODE>_INSIDER.json,
tapi belum pernah disentuh satu baris kode pun di app ini.

DUA MASALAH KUALITAS DATA YANG DITEMUKAN SAAT SURVEI, DAN KEPUTUSANNYA
Disurvei dulu seluruh 1.014 file (6.386 baris) sebelum menulis parser --
dua hal yang kalau diabaikan akan diam-diam menghasilkan angka salah:

1. Field `percentage` (previous/current/changes) TIDAK KONSISTEN
   satuannya antar baris -- kadang pecahan (0,0074 = 0,74%), kadang
   sudah dalam bentuk persen (86,76 berarti 86,76%, bukan 8676%).
   Sumbernya (KSEI vs IDX) TIDAK bisa dipakai sebagai pembeda bersih
   (KSEI 99% "sudah persen", tapi bukan 100%). Bahkan ada baris dengan
   percentage 156,64% -- mustahil secara definisi, muncul khusus pada
   baris ACTION_TYPE_TRANSFER (transfer/stock split yang mengubah basis
   saham, bukan transaksi pasar). KEPUTUSAN: field ini TIDAK dipakai
   untuk perhitungan atau pengurutan apa pun -- cuma ditampilkan apa
   adanya sebagai teks dari sumber, diberi label jelas bahwa satuannya
   tidak terjamin konsisten.

2. `price_formatted` KOSONG (=0) pada 68% dari SELURUH baris -- termasuk
   67% dari transaksi BUY dan 63% dari SELL. Nilai transaksi (Rupiah)
   tidak bisa dihitung langsung dari harga yang dilaporkan untuk
   sebagian besar baris. KEPUTUSAN: kalau harga dilaporkan (>0), dipakai
   apa adanya (paling akurat, itu harga eksekusi sungguhan). Kalau tidak,
   dicari harga penutupan saham itu dari Daily/Summary pada tanggal
   terdekat (app ini sudah punya data itu untuk 875 emiten) sebagai
   ESTIMASI -- dan sumbernya (`price_source`: 'reported' atau
   'estimated_close') selalu ikut dikirim, tidak pernah disamarkan
   seolah-olah harga eksekusi sungguhan.

ACTION_TYPE BUKAN CUMA BELI/JUAL
15 jenis action_type muncul di data; hanya BUY dan SELL yang merupakan
transaksi pasar diskresioner sungguhan. Sisanya (TRANSFER, CROSS,
MESOP_OPTION, WARRANT_EXERCISE, MERGER, RIGHT_ISSUE, BOND_CONVERSION,
CAPITAL_REDUCTION, PRIVATE_PLACEMENT, STOCK_SPLIT, STOCK_DIVIDEND,
STOCK_BONUS, MSOP_OPTION) adalah aksi korporasi/mekanis -- mengeksekusi
opsi saham karyawan (MESOP) bukan sinyal yang sama dengan membeli di
pasar terbuka. Ditandai `is_market_trade` dan disaring terpisah, bukan
disamakan begitu saja dengan BUY/SELL.

DUPLIKAT
217 dari 6.386 baris adalah duplikat PERSIS (id+tanggal+action+perubahan
sama, dalam bulan yang sama) -- ciri baris yang kebetulan tertarik dua
kali oleh scraper, bukan dua transaksi sungguhan. Dibuang lewat kunci
komposit sebelum dipakai di mana pun.
"""
try:
    from .runtime_paths import runtime_file as _runtime_file, market_file as _market_file, WEBSITE_DIR as _WEBSITE_DIR, PROJECT_DIR as _PROJECT_DIR, RUNTIME_DIR as _RUNTIME_DIR
except ImportError:
    from website.runtime_paths import runtime_file as _runtime_file, market_file as _market_file, WEBSITE_DIR as _WEBSITE_DIR, PROJECT_DIR as _PROJECT_DIR, RUNTIME_DIR as _RUNTIME_DIR
import glob
import hashlib
import pickle
import tempfile
import threading
import json
import math
import os
import re
import time

import pandas as pd

from .config import DAILY_PATH

INSIDER_DIR = _market_file('Monthly/All')
SUMMARY_DIR = os.path.join(DAILY_PATH, 'Summary')

ACTION_LABELS = {
    'ACTION_TYPE_BUY': 'Beli', 'ACTION_TYPE_SELL': 'Jual',
    'ACTION_TYPE_TRANSFER': 'Transfer', 'ACTION_TYPE_CROSS': 'Cross',
    'ACTION_TYPE_MESOP_OPTION': 'Eksekusi MESOP', 'ACTION_TYPE_MSOP_OPTION': 'Eksekusi MSOP',
    'ACTION_TYPE_WARRANT_EXERCISE': 'Eksekusi Waran', 'ACTION_TYPE_MERGER': 'Merger',
    'ACTION_TYPE_RIGHT_ISSUE': 'Rights Issue', 'ACTION_TYPE_BOND_CONVERSION': 'Konversi Obligasi',
    'ACTION_TYPE_CAPITAL_REDUCTION': 'Penurunan Modal', 'ACTION_TYPE_PRIVATE_PLACEMENT': 'Private Placement',
    'ACTION_TYPE_STOCK_SPLIT': 'Stock Split', 'ACTION_TYPE_STOCK_DIVIDEND': 'Dividen Saham',
    'ACTION_TYPE_STOCK_BONUS': 'Saham Bonus',
}
MARKET_TRADE_ACTIONS = {'ACTION_TYPE_BUY', 'ACTION_TYPE_SELL'}

BADGE_LABELS = {
    'SHAREHOLDER_BADGE_DIREKTUR': 'Direktur',
    'SHAREHOLDER_BADGE_KOMISARIS': 'Komisaris',
    'SHAREHOLDER_BADGE_PENGENDALI': 'Pengendali',
}


def _num(raw):
    """'3,500,000' / '+1,000' / '-150,000' -> float. Kosong/None -> 0.0."""
    if raw is None:
        return 0.0
    cleaned = str(raw).replace(',', '').replace('+', '').strip()
    if not cleaned:
        return 0.0
    try:
        return float(cleaned)
    except ValueError:
        return 0.0


_summary_cache = {}


def _closing_price(ticker, date):
    """
    Harga penutupan saham itu pada tanggal terdekat (<=) dari Daily/
    Summary -- cadangan saat insider tidak melaporkan harga eksekusi.
    Satu file per ticker dibaca sekali saja lewat _summary_cache, bukan
    sekali per baris insider (satu emiten bisa punya belasan baris).
    """
    if ticker not in _summary_cache:
        path = os.path.join(SUMMARY_DIR, '%s_Summary.csv' % ticker)
        if not os.path.exists(path):
            _summary_cache[ticker] = None
        else:
            try:
                df = pd.read_csv(path, usecols=['Date', 'Close'])
                df['Date'] = pd.to_datetime(df['Date'], format='%d-%b-%y', errors='coerce')
                df = df.dropna(subset=['Date']).sort_values('Date')
                _summary_cache[ticker] = df
            except Exception:
                _summary_cache[ticker] = None

    df = _summary_cache[ticker]
    if df is None or df.empty:
        return None
    pos = df['Date'].searchsorted(date, side='right') - 1
    if pos < 0:
        return None
    return float(df['Close'].iloc[pos])


_ALL_CACHE = {'ts': 0.0, 'df': None, 'sig': None}
_ALL_CACHE_TTL = 30  # detik -- jeda antar-PEMERIKSAAN berkas, bukan umur data
_ALL_CACHE_LOCK = threading.RLock()
_ALL_DISK_CACHE = str(_runtime_file('', 'insider_activity_cache.pkl'))
# Invalidate normalized data whenever this parser changes, including dedup rules.
with open(__file__, 'rb') as _parser_file:
    _ALL_DISK_VERSION = hashlib.sha256(_parser_file.read()).hexdigest()


def _load_disk_cache(sig):
    try:
        with open(_ALL_DISK_CACHE, 'rb') as fh:
            cached = pickle.load(fh)
        if (cached.get('version') == _ALL_DISK_VERSION
                and cached.get('sig') == sig
                and isinstance(cached.get('df'), pd.DataFrame)):
            return cached['df']
    except Exception:
        pass
    return None


def _save_disk_cache(df, sig):
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
                dir=os.path.dirname(_ALL_DISK_CACHE),
                prefix='insider_activity_', suffix='.tmp', delete=False) as fh:
            temporary = fh.name
            pickle.dump({'version': _ALL_DISK_VERSION, 'sig': sig, 'df': df},
                        fh, protocol=pickle.HIGHEST_PROTOCOL)
        os.replace(temporary, _ALL_DISK_CACHE)
    except Exception:
        # Cache storage is optional; the freshly parsed result remains usable.
        if temporary:
            try:
                os.unlink(temporary)
            except OSError:
                pass



def _insider_signature():
    """(path, mtime) tiap berkas insider; ~0,04 detik untuk ~1.300 berkas."""
    return tuple(sorted((p, os.stat(p).st_mtime_ns) for p in
                        glob.glob(os.path.join(INSIDER_DIR, '*', '*_INSIDER.json'))))


def load_all():
    """Reuse normalized insider data across requests and process restarts."""
    with _ALL_CACHE_LOCK:
        return _load_all_locked()


def _load_all_locked():
    """
    Semua baris movement dari seluruh file, dinormalisasi, duplikat
    dibuang.

    Di-cache in-memory selama _ALL_CACHE_TTL detik -- dulu didokumentasikan
    "~0,14 detik, tidak perlu cache", tapi itu sudah basi: sekarang makan
    ~1,1 detik (jumlah file sudah jauh lebih banyak), dan sejak kartu
    keputusan Watchlist/Screens ikut memuat detail insider (bukan cuma
    ?light=1), fungsi ini dipanggil 2x per kartu (recent_insider() dan
    buy_cluster_count() dua-duanya lewat sini) -- kelipatan itu yang bikin
    halaman Watchlist/Screens terasa lambat begitu Screen & Aktivitas
    Insider ditambahkan.

    Dulu TTL 5 menit, artinya tiap 5 menit SATU permintaan membayar
    pemuatan ulang penuh (~4-6 detik, sebagian besar _merge_cross_source)
    untuk berkas yang sebenarnya tidak berubah -- sumbernya cuma ditarik
    sebulan sekali. Sekarang dimuat ulang HANYA kalau tanda tangan berkas
    (path + mtime) berubah; tanda tangannya sendiri dicek paling sering
    sekali per _ALL_CACHE_TTL detik.
    """
    now = time.time()
    if _ALL_CACHE['df'] is not None and now - _ALL_CACHE['ts'] < _ALL_CACHE_TTL:
        return _ALL_CACHE['df']
    sig = _insider_signature()
    if _ALL_CACHE['df'] is not None and sig == _ALL_CACHE['sig']:
        _ALL_CACHE['ts'] = now
        return _ALL_CACHE['df']

    disk = _load_disk_cache(sig)
    if disk is not None:
        _ALL_CACHE.update(df=disk, ts=now, sig=sig)
        return disk

    rows = []
    seen = {}

    for month_dir in sorted(glob.glob(os.path.join(INSIDER_DIR, '*'))):
        for path in glob.glob(os.path.join(month_dir, '*_INSIDER.json')):
            ticker = os.path.basename(path).split('_')[0].upper()
            try:
                with open(path, encoding='utf-8') as fh:
                    payload = json.load(fh)
            except Exception:
                continue

            for m in payload.get('data', {}).get('movement', []):
                key = (ticker, m.get('id'), m.get('date'), m.get('action_type'),
                      m.get('changes', {}).get('value'))
                purpose = (m.get('purpose') or '').strip()
                if key in seen:
                    # Later downloads can add a purpose to an existing event.
                    if purpose and not seen[key]['purpose']:
                        seen[key]['purpose'] = purpose
                    continue

                action = m.get('action_type')
                badges = [BADGE_LABELS.get(b, b) for b in (m.get('badges') or [])]
                shares_changed = _num(m.get('changes', {}).get('value'))
                price_reported = _num(m.get('price_formatted'))

                rows.append({
                    'ticker': ticker,
                    'date_raw': m.get('date'),
                    'name': (m.get('name') or '').strip(),
                    'action_type': action,
                    'purpose': purpose,
                    'action_label': ACTION_LABELS.get(action, action or '-'),
                    'is_market_trade': action in MARKET_TRADE_ACTIONS,
                    'shares_prev': _num(m.get('previous', {}).get('value')),
                    'shares_curr': _num(m.get('current', {}).get('value')),
                    'shares_changed': shares_changed,
                    # Persentase dari sumber APA ADANYA -- satuannya tidak
                    # konsisten (lihat catatan modul), tidak dipakai untuk
                    # sortir/skor apa pun, cuma teks tampilan.
                    'pct_changed_raw': m.get('changes', {}).get('percentage'),
                    'price_reported': price_reported,
                    'nationality': 'Asing' if m.get('nationality') == 'NATIONALITY_TYPE_FOREIGN' else 'Lokal',
                    'is_controller': 'SHAREHOLDER_BADGE_PENGENDALI' in (m.get('badges') or []),
                    'badges': badges,
                    'source': (m.get('data_source') or {}).get('label', ''),
                })
                seen[key] = rows[-1]

    df = pd.DataFrame(rows)
    if not df.empty:
        df['date'] = pd.to_datetime(df['date_raw'], format='%d %b %y', errors='coerce')
        df = df.dropna(subset=['date']).sort_values('date', ascending=False).reset_index(drop=True)
        df = _merge_cross_source(df)

    _save_disk_cache(df, sig)
    _ALL_CACHE.update(df=df, ts=time.time(), sig=sig)
    return df


def _merge_cross_source(df):
    """
    Duplikat kunci `seen` di atas cuma menangkap penarikan dobel dari
    SUMBER YANG SAMA (kuncinya termasuk `id`, dan KSEI/IDX punya sistem id
    sendiri-sendiri) -- transaksi yang SAMA tapi dilaporkan KSEI *dan* IDX
    lolos dari situ, jadi muncul dua kali seolah dua transaksi berbeda.

    Ditemukan nyata: 17 pasang (34 baris) dengan ticker+tanggal+action+
    lembar berubah IDENTIK tapi source beda -- semua tanpa kecuali baris
    IDX-nya punya harga eksekusi terlapor, baris KSEI-nya 0 (KSEI tidak
    melaporkan harga). Nama pelapor juga sering beda ejaan/urutan antar
    dua sumber untuk ORANG YANG SAMA (mis. "RUDI R SUTANTRA" vs "RUDI R.
    SUTANTRA", atau entitas vs perorangan) -- empat kolom itu (bukan nama)
    yang dipakai sebagai kunci gabung, karena nama sendiri terlalu tidak
    stabil buat kunci.

    Baris hasil gabung: field lain (nama, harga, badge) diambil dari baris
    yang PALING INFORMATIF (harga terlapor > 0, bukan asal salah satu),
    field `source` jadi gabungan kedua sumber ("IDX + KSEI") supaya tetap
    terlihat dikonfirmasi dua sumber, bukan disembunyikan begitu saja.
    """
    df = df.copy()
    df['source'] = df['source'].str.replace('Sumber: ', '', regex=False)
    df['cross_source_confirmed'] = False

    # PENTING: baris dgn kunci sama TAPI SUMBER SAMA juga bukan dupe --
    # itu kebetulan dua insider beda jual/beli jumlah lembar bulat yang
    # sama persis di hari yang sama (lumrah utk angka bulat spt 10 juta),
    # transaksi sungguhan yang beda, HARUS tetap dua baris. Cek nyata:
    # dari 92 grup berkunci sama, cuma 17 yang sumbernya beneran >1 unik
    # -- 75 sisanya salah gabung kalau tidak disaring lewat cek ini
    # (sempat kejadian, 121 baris asli hilang sebelum ini ditemukan).
    group_cols = ['ticker', 'date', 'action_type', 'shares_changed']
    kept_rows = []
    for _, g in df.groupby(group_cols, dropna=False):
        sources = [s for s in g['source'] if s]
        if len(g) == 1 or len(set(sources)) <= 1:
            kept_rows.extend(row for _, row in g.iterrows())
            continue
        best = g.loc[g['price_reported'].idxmax()].copy()
        best['source'] = ' + '.join(dict.fromkeys(sources))  # urut kemunculan, tanpa duplikat
        # Preserve reported purposes even when the selected price row has none.
        best['purpose'] = '; '.join(dict.fromkeys(
            p.strip() for p in g.get('purpose', []) if isinstance(p, str) and p.strip()))
        best['cross_source_confirmed'] = True
        kept_rows.append(best)

    result = pd.DataFrame(kept_rows).sort_values('date', ascending=False).reset_index(drop=True)
    return result


def enrich_prices(df):
    """
    Isi harga yang tidak dilaporkan dengan harga penutupan Summary pada
    tanggal itu, ditandai jelas sumbernya. Dipisah dari load_all() supaya
    pemanggil yang cuma butuh daftar transaksi (tanpa nilai Rupiah) tidak
    perlu menanggung biaya baca puluhan file Summary.
    """
    if df.empty:
        return df
    df = df.copy()
    price_used, price_source = [], []
    for _, r in df.iterrows():
        if r['price_reported'] > 0:
            price_used.append(r['price_reported'])
            price_source.append('reported')
        else:
            est = _closing_price(r['ticker'], r['date'])
            price_used.append(est)
            price_source.append('estimated_close' if est is not None else 'unavailable')
    df['price_used'] = price_used
    df['price_source'] = price_source
    df['value_idr'] = df['price_used'] * df['shares_changed'].abs()
    return df


def recent_for_ticker(ticker, days_back=180, market_trades_only=False):
    """Transaksi insider satu emiten -- untuk Halaman Saham."""
    df = load_all()
    if df.empty:
        return []
    sub = df[df['ticker'] == ticker.upper()]
    if sub.empty:
        return []
    cutoff = df['date'].max() - pd.Timedelta(days=days_back)
    sub = sub[sub['date'] >= cutoff]
    if market_trades_only:
        sub = sub[sub['is_market_trade']]
    if sub.empty:
        return []
    sub = enrich_prices(sub)
    return _to_rows(sub)


def buy_cluster_count(df, ticker, window_days=5):
    """
    Jumlah transaksi ACTION_TYPE_BUY pasar untuk satu ticker dalam
    window_days hari kalender terakhir dari tanggal data terbaru.

    BUKAN sinyal yang tervalidasi -- backtest awal (Sep 2026, n=774
    episode independen) menunjukkan hitungan mentah TIDAK berkorelasi
    dengan hasil (mean +0,18%, win 47,7%, dekat kebetulan). Memecahnya
    per ukuran cluster menunjukkan episode dengan >=10 transaksi tampak
    lebih baik (+4,01% mean, win 59,7%), TAPI n=72 dan itu ditemukan
    lewat pemotongan post-hoc setelah agregat mentahnya nihil -- risiko
    tinggi cuma potongan data yang kebetulan bagus, bukan pola sungguhan.

    Sengaja hanya dicatat sebagai angka observasi pasif (bukan badge
    hijau/skor/sinyal beli) sampai terkumpul lebih banyak histori
    independen untuk diuji ulang.
    """
    if df is None or df.empty:
        return 0
    sub = df[(df['ticker'] == ticker.upper())
             & (df['action_type'] == 'ACTION_TYPE_BUY')
             & (df['is_market_trade'])]
    if sub.empty:
        return 0
    cutoff_end = df['date'].max()
    cutoff_start = cutoff_end - pd.Timedelta(days=window_days)
    return int(((sub['date'] > cutoff_start) & (sub['date'] <= cutoff_end)).sum())


def _num_or_none(v):
    """
    NaN lolos dari pandas ketika _closing_price() gagal menemukan harga
    (ticker delisting/data Summary hilang) -- json.dumps Python secara
    default menulis NaN sebagai literal `NaN`, yang BUKAN JSON valid dan
    membuat JSON.parse() di browser gagal total untuk seluruh response.
    """
    return None if v is None or (isinstance(v, float) and math.isnan(v)) else v


def _to_rows(df):
    rows = []
    for _, r in df.iterrows():
        rows.append({
            'ticker': r['ticker'], 'date': r['date'].strftime('%Y-%m-%d'),
            'name': r['name'], 'action_type': r['action_type'],
            'action_label': r['action_label'], 'is_market_trade': bool(r['is_market_trade']),
            'purpose': r.get('purpose') or None,
            'shares_changed': int(r['shares_changed']),
            'pct_changed_raw': r['pct_changed_raw'],
            'price_reported': r['price_reported'] if r['price_reported'] > 0 else None,
            'price_used': _num_or_none(r.get('price_used')),
            'price_source': r.get('price_source'),
            'value_idr': _num_or_none(r.get('value_idr')),
            'nationality': r['nationality'], 'is_controller': bool(r['is_controller']),
            'badges': r['badges'],
            'source': r.get('source'),
            'cross_source_confirmed': bool(r.get('cross_source_confirmed', False)),
        })
    return rows


def build_page(days_back=30, action_filter='trade', ticker_filter=None):
    """Ringkasan siap-tampil untuk halaman Aktivitas Insider."""
    df = load_all()
    if df.empty:
        return {'available': False, 'message': 'Tidak ada data insider ditemukan.'}

    cutoff = df['date'].max() - pd.Timedelta(days=days_back)
    sub = df[df['date'] >= cutoff]

    if action_filter == 'trade':
        sub = sub[sub['is_market_trade']]
    elif action_filter == 'buy':
        sub = sub[sub['action_type'] == 'ACTION_TYPE_BUY']
    elif action_filter == 'sell':
        sub = sub[sub['action_type'] == 'ACTION_TYPE_SELL']
    # 'all' -> tidak difilter

    if ticker_filter:
        sub = sub[sub['ticker'] == ticker_filter.upper()]

    sub = enrich_prices(sub)

    n_buy = int((df[df['date'] >= cutoff]['action_type'] == 'ACTION_TYPE_BUY').sum())
    n_sell = int((df[df['date'] >= cutoff]['action_type'] == 'ACTION_TYPE_SELL').sum())
    n_other = int(len(df[df['date'] >= cutoff]) - n_buy - n_sell)

    return {
        'available': True,
        'as_of': df['date'].max().strftime('%Y-%m-%d'),
        'total_emiten': df['ticker'].nunique(),
        'total_baris': len(df),
        'counts': {'buy': n_buy, 'sell': n_sell, 'other': n_other},
        'rows': _to_rows(sub),
    }
