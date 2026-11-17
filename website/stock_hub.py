"""
Halaman hub satu saham: semua yang app ini tahu tentang satu emiten,
dalam satu tempat.

KENAPA ADA
Sebelum ini, memeriksa satu saham berarti membuka enam halaman berbeda:
Kepemilikan Saham untuk struktur pemiliknya, Scanner Lab untuk sinyal,
All Charts untuk grafiknya, Broker Footprint dan Broker Trend untuk arus
brokernya, Portfolio P&L untuk posisi sendiri. Modul ini tidak menghitung
apa pun yang baru -- dia memanggil modul yang sudah ada dan menyusun
hasilnya jadi satu tampilan.

Semua bagian dibuat opsional: kalau data kepemilikan belum ditarik, atau
sahamnya tidak sedang punya sinyal, bagian itu kosong tapi halamannya
tetap berguna. Satu sumber yang gagal tidak boleh menjatuhkan seluruh
halaman -- itu sebabnya tiap bagian dibungkus try/except sendiri.
"""
import os

import pandas as pd

from .config import DAILY_PATH
from .ownership import build_ownership
from .live_scan import cached_scan_stale_ok, FORWARD_NEEDED
from .scanner import score_signal, enrich, SCANNERS, MARKET_BASELINE_20D
from .flow_health import check as flow_check, check_current as flow_check_current
from .flow_health import load_stock as load_flow_stock
from .insider_activity import recent_for_ticker as recent_insider
from .insider_activity import load_all as load_insider_all, buy_cluster_count
from .kering_screener import refresh as kering_refresh
from .screen_eval import (classify_history, _load as load_summary,
                          SCREEN_LABELS, build_report)
from .market_correlation import compute_independence

SUMMARY_DIR = os.path.join(DAILY_PATH, 'Summary')


def _price_snapshot(df):
    """Harga, perubahan, dan nilai transaksi hari terakhir."""
    if df is None or df.empty:
        return None
    last = df.iloc[-1]
    prev_close = df['Close'].iloc[-2] if len(df) > 1 else None
    change_pct = None
    if prev_close and prev_close > 0:
        change_pct = round((last['Close'] - prev_close) / prev_close * 100, 2)

    vol_avg20 = df['Volume'].iloc[-21:-1].mean() if len(df) > 21 else None
    return {
        'date': last['Date'].strftime('%Y-%m-%d'),
        'close': float(last['Close']),
        'change_pct': change_pct,
        'volume': float(last['Volume']),
        'vol_mult': round(float(last['Volume'] / vol_avg20), 2)
                    if vol_avg20 and vol_avg20 > 0 else None,
        'value_b': round(float((last['Open'] + last['Close']) / 2 * last['Volume'] / 1e9), 2),
        'net_top5_20d': float(df['Net Top5 All Lot'].iloc[-20:].sum()) if 'Net Top5 All Lot' in df else None,
        'retail_20d': float(df['Retail'].iloc[-20:].sum()) if 'Retail' in df else None,
        'net_top5_5d': float(df['Net Top5 All Lot'].iloc[-5:].sum()) if 'Net Top5 All Lot' in df else None,
        'retail_5d': float(df['Retail'].iloc[-5:].sum()) if 'Retail' in df else None,
    }


def _current_screen(df):
    """
    Screen apa yang sedang menampung saham ini hari ini, plus rekam jejak
    historis screen itu -- supaya rekomendasinya langsung datang bersama
    ukuran seberapa sering rekomendasi semacam itu benar.
    """
    if df is None or len(df) < 60:
        return None
    cats, value_b = classify_history(df)
    if not cats or not cats[-1]:
        return None

    key = cats[-1]
    label, model = SCREEN_LABELS.get(key, (key, None))
    record = None
    try:
        report = build_report()
        if report.get('available'):
            for row in report['screens']:
                if row['key'] == key:
                    record = row
                    break
    except Exception:
        record = None

    # Sudah berapa hari beruntun di screen yang sama.
    streak = 0
    for cat in reversed(cats):
        if cat != key:
            break
        streak += 1

    return {'key': key, 'label': label, 'type': model,
            'value_b': round(float(value_b.iloc[-1]), 2),
            'streak_days': streak, 'record': record}


def _live_signals(ticker, limit=8):
    """Sinyal scanner yang sedang berjalan untuk saham ini, sudah diberi skor."""
    try:
        payload = cached_scan_stale_ok(days_back=90)
    except Exception:
        return []
    if payload is None:
        return []
    df = payload.get('df')
    if df is None or df.empty:
        return []

    sub = df[df['stock'] == ticker]
    if sub.empty:
        return []

    sub = sub.copy()
    sub['scanner_label'] = sub['scanner'].map(lambda k: SCANNERS.get(k, {}).get('label', k))
    sub['retrospective'] = False
    sub['fwd20'] = None
    try:
        sub = enrich(sub)
    except Exception:
        pass

    # Satu CSV untuk semua sinyal -- dulu flow_check() membacanya ulang
    # per sinyal, sampai `limit` kali untuk berkas yang sama.
    try:
        flow_df = load_flow_stock(ticker)
    except Exception:
        flow_df = None

    rows = []
    for _, row in sub.head(limit).iterrows():
        score, reasons = score_signal(row, None)
        signal_date_str = row['signal_date'].strftime('%Y-%m-%d')
        try:
            fh = flow_check(ticker, signal_date_str, df=flow_df)
            flow = fh['checkpoints'] if fh.get('available') else []
        except Exception:
            flow = []

        rows.append({
            'signal_date': signal_date_str,
            'scanner': row['scanner'],
            'scanner_label': row['scanner_label'],
            'pending': bool(row.get('pending')),
            'forward_needed': FORWARD_NEEDED.get(row['scanner'], 20),
            'score': score,
            'reasons': [{'kind': k, 'text': t} for k, t in reasons],
            'flow': flow,
        })
    return rows


def _kering_status(ticker, days_back=14):
    """
    Apakah ticker ini sedang jadi kandidat Kering Screener dalam
    `days_back` hari terakhir. HANYA status kemunculan -- ingat, backtest
    Kering Screener sendiri NEGATIF di semua horizon (H=5: -9,44% mean,
    win 21,9%, -9,79pp vs pasar; lihat docstring kering_screener.py),
    jadi jadi kandidat bukan alasan untuk membeli, malah sebaliknya.
    """
    try:
        data = kering_refresh()
    except Exception:
        return None
    events = data.get('events')
    if events is None or events.empty:
        return None
    sub = events[events['ticker'] == ticker]
    if sub.empty:
        return None
    cutoff = events['date'].max() - pd.Timedelta(days=days_back)
    sub = sub[sub['date'] >= cutoff]
    if sub.empty:
        return None
    row = sub.sort_values(['date', 'skor'], ascending=[False, False]).iloc[0]
    return {'date': row['date'].strftime('%Y-%m-%d'), 'skor': round(float(row['skor']), 3),
            'K': int(row['K'])}


def _current_score(price, ownership):
    """
    Skor pola dari kondisi HARI INI (H-5 s/d sekarang), bukan dari
    tanggal sinyal scanner historis -- reuse score_signal() yang sama
    persis dipakai Scanner Lab, cuma barisnya direkonstruksi dari data
    hari ini (vol_mult, konteks kepemilikan, arus ritel 5 hari) alih-
    alih dari baris CSV hasil scan pada satu tanggal sinyal. Skor pola
    scanner asli TETAP ditampilkan terpisah di bagian "Sinyal Scanner
    Berjalan" di bawah -- ini bukan pengganti, cuma versi yang SELALU
    ada dan tidak pernah basi untuk kartu keputusan.

    retail_median sengaja None -- tidak ada acuan pasar "hari ini" yang
    murah dihitung di sini tanpa scan seluruh bursa, jadi faktor basis
    ritel (bobotnya kecil di score_signal()) tidak ikut dihitung
    daripada memakai angka yang dikarang.
    """
    if not price:
        return None
    row = {
        'vol_mult': price.get('vol_mult'),
        # Bucket individu KSEI MENTAH, bukan pct_retail hasil carve-out.
        # score_signal() disusun dari variabel yang mentah; menyuapkan angka
        # yang sudah disaring ke sana berarti memakai aturan pada variabel
        # yang bukan penyusunnya. Halaman Kepemilikan Saham tetap menampilkan
        # yang carve-out -- itu yang benar untuk dibaca manusia.
        'own_pct_individu': ownership.get('pct_retail_raw') if ownership else None,
        'retail_cum20': price.get('retail_5d'),
        'own_d_individu': ownership.get('delta_retail_raw') if ownership else None,
        'retrospective': False,
    }
    score, reasons = score_signal(row, retail_median=None)
    return {'score': score, 'reasons': [{'kind': k, 'text': t} for k, t in reasons],
            'as_of': price.get('date'), 'window': 5}


def build_hub(ticker, light=False):
    """
    Semua yang diketahui tentang satu emiten. Tiap bagian dibungkus
    sendiri supaya satu sumber yang gagal tidak menjatuhkan yang lain.

    `light=True` melewati bagian yang TIDAK dipakai DecisionCard (screen
    otomatis penuh, daftar transaksi insider yang di-enrich harga) --
    dipakai Watchlist/Screens (stocks_image.html) yang cuma butuh kartu
    keputusan, bukan seluruh detail Halaman Saham. insider_buy_cluster_5d
    tetap dihitung karena murah (filter+hitung, tanpa lookup harga).
    """
    import re
    ticker = re.sub(r'[^A-Z0-9]', '', (ticker or '').upper())[:6]
    if not ticker:
        return {'available': False, 'message': 'Kode saham tidak valid.'}

    df = load_summary(ticker)
    if df is None or df.empty:
        return {'available': False, 'ticker': ticker,
                'message': 'Tidak ada data harian untuk %s.' % ticker}

    out = {'available': True, 'ticker': ticker,
           'baseline': MARKET_BASELINE_20D,
           'price': _price_snapshot(df)}

    try:
        own = build_ownership(ticker)
        out['ownership'] = own if own.get('available') else None
    except Exception:
        out['ownership'] = None

    try:
        out['current_score'] = _current_score(out['price'], out['ownership'])
    except Exception:
        out['current_score'] = None

    try:
        out['current_flow'] = flow_check_current(ticker, window=5, df=None)
    except Exception:
        out['current_flow'] = {'available': False}

    if light:
        out['screen'] = None
    else:
        try:
            out['screen'] = _current_screen(df)
        except Exception:
            out['screen'] = None

    try:
        out['signals'] = _live_signals(ticker)
    except Exception:
        out['signals'] = []

    if light:
        out['insider'] = []
    else:
        try:
            out['insider'] = recent_insider(ticker, days_back=180, market_trades_only=True)
        except Exception:
            out['insider'] = []

    try:
        out['kering'] = _kering_status(ticker)
    except Exception:
        out['kering'] = None

    try:
        from .broker_fingerprint import modal_ringkas
        out['modal_bandar'] = modal_ringkas(ticker)
    except Exception:
        out['modal_bandar'] = None

    try:
        out['independence'] = compute_independence(ticker)
    except Exception:
        out['independence'] = {'available': False}

    try:
        out['insider_buy_cluster_5d'] = buy_cluster_count(load_insider_all(), ticker)
    except Exception:
        out['insider_buy_cluster_5d'] = 0

    if light:
        out['pattern_matches'] = None
    else:
        try:
            from .pattern_miner import matches_for_stock
            out['pattern_matches'] = matches_for_stock(ticker)
        except Exception:
            out['pattern_matches'] = {'available': False}

    return out
