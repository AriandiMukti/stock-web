"""
Independensi dari IHSG: dimensi kartu keputusan yang BEDA ARAH dari
semua yang lain -- bukan deteksi sinyal, bukan komposisi kepemilikan,
tapi "apakah pergerakan saham ini distingtif, atau cuma numpang arus
pasar secara umum".

KENAPA INI BERGUNA
Kondisi Pasar (market_regime.py) sudah menjawab "pasar secara umum
lagi bagaimana" (mis. rally +9,09%). Tapi itu tidak menjawab pertanyaan
per-saham: kalau IHSG lagi rally kencang, HAMPIR SEMUA saham ikut naik
-- itu tidak berarti sinyal scanner-nya berarti apa-apa, cuma ikut
arus. Saham yang naik TAPI korelasinya ke IHSG rendah/negatif itu yang
pergerakannya lebih mungkin benar-benar spesifik ke saham itu sendiri,
bukan sekadar terbawa pasar.

DATA
IHSG (^JKSE) diambil live dari yfinance -- diverifikasi dulu sebelum
dibangun (bukan diasumsikan bekerja): dicoba langsung, datanya sampai
2026-09-04, real, bukan proxy. TIDAK bergantung file lokal yang bisa
basi (beda dengan corp_action.csv yang ternyata basi 1,5 tahun).
Cache berbasis WAKTU (bukan mtime Summary), karena sumbernya API
eksternal, bukan file lokal -- 1x per hari cukup, dipanggil ulang tiap
request akan memboroskan panggilan API untuk data yang jelas belum
berubah dalam hitungan jam.

Korelasi tiap SAHAM dihitung dari data lokal (Summary CSV) yang sudah
ada -- TIDAK perlu fetch yfinance per ticker (skrip lama
correlationWithIHSG.py melakukan itu untuk ~640 ticker, boros dan
lambat). Cuma IHSG-nya yang perlu diambil dari luar, sekali, di-cache.
"""
try:
    from .runtime_paths import runtime_file as _runtime_file, market_file as _market_file, WEBSITE_DIR as _WEBSITE_DIR, PROJECT_DIR as _PROJECT_DIR, RUNTIME_DIR as _RUNTIME_DIR
except ImportError:
    from website.runtime_paths import runtime_file as _runtime_file, market_file as _market_file, WEBSITE_DIR as _WEBSITE_DIR, PROJECT_DIR as _PROJECT_DIR, RUNTIME_DIR as _RUNTIME_DIR
import os
import pickle
import time

import numpy as np
import pandas as pd

from .config import DAILY_PATH

CACHE_FILE = str(_runtime_file('', 'ihsg_cache.pkl'))
# IHSG diambil dari luar (yfinance), jadi tidak ada berkas sumber lokal
# untuk dibandingkan. Yang dipakai sebagai penanda "hari bursa sudah maju"
# adalah berkas Summary: begitu unduhan pagi masuk, IHSG ikut ditarik ulang
# sekali, lalu diam sepanjang hari. Lebih tepat daripada TTL 12 jam, yang
# bisa menarik ulang dua kali di hari yang sama ATAU menyajikan IHSG
# kemarin di atas data hari ini.
SUMMARY_DIR = os.path.join(DAILY_PATH, 'Summary')

WINDOW_DAYS = 60


def _fetch_ihsg():
    """Return per hari IHSG dari yfinance, atau None kalau gagal (API down/offline)."""
    try:
        import yfinance as yf
        df = yf.download('^JKSE', period='6mo', interval='1d', progress=False)
        if df.empty:
            return None
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        close = df['Close'].dropna()
        returns = close.pct_change().dropna() * 100
        return {d.strftime('%Y-%m-%d'): float(v) for d, v in returns.items()}
    except Exception:
        return None


def _ihsg_returns_cached():
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, 'rb') as fh:
                cached = pickle.load(fh)
            from .kesegaran import summary_terbaru
            if cached.get('built_at', 0) >= summary_terbaru():
                return cached['returns']
        except Exception:
            pass

    returns = _fetch_ihsg()
    if returns is None:
        # yfinance gagal (offline, API berubah, dsb) -- pakai cache lama
        # kalau ada, walau basi, daripada tidak ada apa-apa sama sekali.
        if os.path.exists(CACHE_FILE):
            try:
                with open(CACHE_FILE, 'rb') as fh:
                    return pickle.load(fh)['returns']
            except Exception:
                pass
        return None

    try:
        with open(CACHE_FILE, 'wb') as fh:
            pickle.dump({'built_at': time.time(), 'returns': returns}, fh)
    except Exception:
        pass
    return returns


def _label(corr):
    if corr >= 0.6:
        return 'ikut_kuat', 'Sangat mengikuti IHSG'
    if corr >= 0.3:
        return 'ikut', 'Mengikuti IHSG'
    if corr > -0.1:
        return 'independen', 'Bergerak independen dari IHSG'
    return 'berlawanan', 'Bergerak berlawanan arah IHSG'


def compute_independence(ticker, window=WINDOW_DAYS):
    """
    Korelasi return harian ticker vs IHSG dalam `window` hari bursa
    terakhir yang datanya tersedia di KEDUANYA (irisan tanggal, bukan
    window kalender -- hari libur bursa beda-beda per sumber data).
    """
    ihsg = _ihsg_returns_cached()
    if not ihsg:
        return {'available': False, 'message': 'Data IHSG tidak tersedia (yfinance gagal/offline).'}

    path = os.path.join(SUMMARY_DIR, '%s_Summary.csv' % ticker)
    if not os.path.exists(path):
        return {'available': False, 'message': 'Tidak ada data harian untuk %s.' % ticker}
    try:
        df = pd.read_csv(path, usecols=['Date', 'Close']).fillna(0)
    except Exception:
        return {'available': False, 'message': 'Gagal membaca data harian.'}
    df['Date'] = pd.to_datetime(df['Date'], format='%d-%b-%y', errors='coerce')
    df = df.dropna(subset=['Date']).sort_values('Date')
    if len(df) < 10:
        return {'available': False, 'message': 'Data harian terlalu pendek.'}

    df['ret'] = df['Close'].pct_change() * 100
    df = df.dropna(subset=['ret'])
    df['date_str'] = df['Date'].dt.strftime('%Y-%m-%d')
    df['ihsg_ret'] = df['date_str'].map(ihsg)
    matched = df.dropna(subset=['ihsg_ret']).tail(window)

    if len(matched) < 15:
        return {'available': False, 'message': 'Irisan tanggal dengan IHSG terlalu sedikit (n=%d).' % len(matched)}

    corr = float(np.corrcoef(matched['ret'], matched['ihsg_ret'])[0, 1])
    if np.isnan(corr):
        return {'available': False, 'message': 'Korelasi tidak terdefinisi (salah satu sisi tidak bervariasi).'}

    key, label = _label(corr)
    return {'available': True, 'correlation': round(corr, 2), 'n': int(len(matched)),
            'key': key, 'label': label}
