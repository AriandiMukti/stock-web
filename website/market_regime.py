"""
Kondisi Pasar: "bagaimana pasar secara umum sedang bergerak", ditampilkan
sebagai KONTEKS di samping (BUKAN menggantikan) baseline historis tetap
yang sudah dipakai di scanner.py/screen_eval.py/kering_screener.py.

KENAPA INI ADA
Ketemu sendiri waktu menguji ide "Tekanan Order Book" (lihat riwayat
percakapan): baseline yang dipakai untuk menilai sebuah sinyal bisa
sangat menyesatkan tergantung rezim pasar saat itu -- window pengujian
itu ternyata pasar rally +2%/3 hari, bikin semua pembanding kelihatan
lebih buruk dari yang sebenarnya. Baseline historis TETAP (mis. -1,33%
di screen_eval.py) tidak pernah tahu bahwa MINGGU INI pasar sedang naik
kencang atau turun kencang.

KENAPA TIDAK MENGGANTI BASELINE YANG SUDAH ADA
Baseline historis tetap itu untuk menjawab pertanyaan "screen/scanner
ini secara historis menang atau kalah dari pasar" -- itu memang harus
dihitung dari seluruh periode historis, bukan rolling, supaya sampelnya
cukup besar. Kondisi Pasar menjawab pertanyaan BERBEDA: "pasar HARI INI
sedang bagaimana" -- keduanya dipakai BERSAMA (mis. "screen ini menang
tipis dari baseline lama, TAPI pasar sedang rally kencang minggu ini,
jadi kemenangan tipis itu mungkin cuma ikut arus"), bukan salah satu
menggantikan yang lain. Mengganti seluruh baseline tetap di modul lain
jadi rolling adalah pekerjaan jauh lebih besar (butuh re-backtest tiap
modul) dan di luar cakupan ini.

CACHE
Satu file, mtime-keyed sama seperti kering_screener.py/screen_eval.py --
tidak bergantung parameter jadi tidak ada risiko tabrakan cache seperti
yang pernah terjadi di live_scan.py.
"""
try:
    from .runtime_paths import runtime_file as _runtime_file, market_file as _market_file, WEBSITE_DIR as _WEBSITE_DIR, PROJECT_DIR as _PROJECT_DIR, RUNTIME_DIR as _RUNTIME_DIR
except ImportError:
    from website.runtime_paths import runtime_file as _runtime_file, market_file as _market_file, WEBSITE_DIR as _WEBSITE_DIR, PROJECT_DIR as _PROJECT_DIR, RUNTIME_DIR as _RUNTIME_DIR
import glob
import os
import pickle

import numpy as np
import pandas as pd

from .config import DAILY_PATH

SUMMARY_DIR = os.path.join(DAILY_PATH, 'Summary')
CACHE_FILE = str(_runtime_file('', 'market_regime_cache.pkl'))

WINDOW_DAYS = 20


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


def _compute(window_days=WINDOW_DAYS):
    files = glob.glob(os.path.join(SUMMARY_DIR, '*_Summary.csv'))
    returns = []
    as_of = None
    for fp in files:
        try:
            df = pd.read_csv(fp, usecols=['Date', 'Close']).fillna(0)
        except Exception:
            continue
        if df.empty:
            continue
        df['Date'] = pd.to_datetime(df['Date'], format='%d-%b-%y', errors='coerce')
        df = df.dropna(subset=['Date']).sort_values('Date')
        if len(df) < window_days + 1:
            continue
        last_date = df['Date'].iloc[-1]
        if as_of is None or last_date > as_of:
            as_of = last_date
        c_now = float(df['Close'].iloc[-1])
        c_then = float(df['Close'].iloc[-(window_days + 1)])
        if c_then > 0:
            returns.append((c_now - c_then) / c_then * 100)

    if not returns:
        return {'available': False, 'message': 'Tidak cukup data untuk menghitung kondisi pasar.'}

    arr = np.array(returns)
    mean = float(arr.mean())
    if mean >= 5:
        label, key = 'Rally kencang', 'rally'
    elif mean >= 1.5:
        label, key = 'Naik', 'naik'
    elif mean > -1.5:
        label, key = 'Datar', 'datar'
    elif mean > -5:
        label, key = 'Turun', 'turun'
    else:
        label, key = 'Anjlok', 'anjlok'

    return {
        'available': True,
        'window_days': window_days,
        'n': len(returns),
        'mean_pct': round(mean, 2),
        'median_pct': round(float(np.median(arr)), 2),
        'pct_up': round(float((arr > 0).mean() * 100), 1),
        'as_of': as_of.strftime('%Y-%m-%d') if as_of is not None else None,
        'label': label,
        'key': key,
    }


def get_regime_if_ready():
    """Sama seperti get_regime(), TAPI tidak pernah menghitung kalau cache
    belum ada/basi - balikin None saja. Dipakai pemanggil yang harus tidak
    pernah blocking (dashboard "/", lihat _ringkasan_dashboard() di
    views.py - docstring-nya sudah janji "tidak ada yang dihitung di sini",
    tapi get_regime() biasa melanggar itu lewat fallback _compute() yang
    membaca ~900 berkas *_Summary.csv satu per satu)."""
    if not os.path.exists(CACHE_FILE):
        return None
    try:
        with open(CACHE_FILE, 'rb') as fh:
            cached = pickle.load(fh)
        if cached.get('built_at', 0) >= _newest_summary_mtime():
            return cached['payload']
    except Exception:
        pass
    return None


def get_regime_tersimpan():
    """
    (payload, segar) dari cache APA ADANYA, tanpa pernah menghitung.

    Untuk dashboard: begitu ada Summary yang lebih baru dari cache,
    get_regime_if_ready() mengembalikan None dan kartu regime dulu HILANG
    sampai pemeriksaan kesehatan malam itu jalan. Angka kemarin berlabel
    "basi" lebih berguna daripada kartu kosong.
    """
    if not os.path.exists(CACHE_FILE):
        return None, False
    try:
        with open(CACHE_FILE, 'rb') as fh:
            cached = pickle.load(fh)
        return cached.get('payload'), cached.get('built_at', 0) >= _newest_summary_mtime()
    except Exception:
        return None, False


def get_regime(force=False):
    """Kondisi pasar dari cache; dihitung ulang kalau basi atau dipaksa."""
    if not force:
        ready = get_regime_if_ready()
        if ready is not None:
            return ready

    payload = _compute()
    try:
        with open(CACHE_FILE, 'wb') as fh:
            pickle.dump({'built_at': _newest_summary_mtime(), 'payload': payload}, fh)
    except Exception:
        pass
    return payload
