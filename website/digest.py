"""
Ringkasan Watchlist: satu halaman yang menyilangkan Portfolio/Best/Best
Low/Pattern Up dengan SEMUA modul sinyal yang sudah dibangun -- Scanner
Lab, Kering Screener, Screen Eval, Kesehatan Arus, Aktivitas Insider.

KENAPA INI ADA
Setiap modul di atas menjawab pertanyaannya sendiri dengan baik, tapi
tidak ada satu pun yang menjawab "dari saham yang SAYA pantau, mana yang
hari ini punya sesuatu yang layak dilihat?" -- untuk tahu itu, sebelumnya
harus membuka Scanner Lab, Kering Screener, dan tiap Halaman Saham satu
per satu lalu mencocokkan sendiri kode sahamnya.

TIDAK MENGHITUNG APA PUN YANG BARU
Modul ini murni menyilangkan: query keanggotaan watchlist dari database,
lalu panggil fungsi yang SUDAH ADA di live_scan/kering_screener/
screen_eval/insider_activity untuk tiap ticker yang cocok. Semua modul
itu sudah punya cache sendiri (live_scan ~50s pertama kali lalu ~2 detik,
kering_screener ~30s lalu instan, screen_eval ~16s lalu instan), jadi
Ringkasan Watchlist ikut cepat begitu cache-nya sudah pernah dipanaskan
dari halaman masing-masing.

TIDAK MEMBERI SKOR PRIORITAS TUNGGAL, SENGAJA
Screen record sudah membuktikan sebagian screen historisnya KALAH dari
pasar (Consol -5,29pp, Retail Sell -3,27pp) -- memberi angka "prioritas"
tunggal yang menggabungkan semua sinyal akan menyembunyikan itu di balik
satu angka yang terlihat meyakinkan. Yang ditampilkan adalah FAKTA per
sumber (ada sinyal scanner? ada kandidat Kering? sedang di screen apa,
dan bagaimana rekam jejak screen itu? ada insider beli/jual?) --
pengguna yang menimbang, bukan satu skor yang menyamarkan sumbernya.
"""
from .models import scoped_query
import re

import pandas as pd

from . import db
from .models import PortfolioStocks, BestStocks, BestLowStocks, PatternUpStocks
from .live_scan import cached_scan, FORWARD_NEEDED
from .kering_screener import refresh as kering_refresh
from .screen_eval import classify_history, _load as load_summary_for_screen, build_report as screen_build_report
from .insider_activity import load_all as load_insider, enrich_prices as insider_enrich_prices
from .insider_activity import buy_cluster_count
from .scanner import score_signal, enrich as scanner_enrich, SCANNERS
from .flow_health import check as flow_check
from .market_regime import get_regime

WATCHLIST_MODELS = [
    ('PortfolioStocks', 'Portfolio', PortfolioStocks),
    ('BestStocks', 'Best', BestStocks),
    ('BestLowStocks', 'Best Low', BestLowStocks),
    ('PatternUpStocks', 'Pattern Up', PatternUpStocks),
]


def watchlist_membership():
    """{ticker: [nama_watchlist, ...]} dari keempat watchlist sekaligus."""
    membership = {}
    for _, label, model in WATCHLIST_MODELS:
        for row in scoped_query(model).all():
            ticker = (row.data or '').strip().upper()
            if not ticker:
                continue
            membership.setdefault(ticker, []).append(label)
    return membership


def _scanner_signals_by_ticker(tickers, days_back=14):
    """
    Sinyal Scanner Lab yang sedang berjalan, dipersempit ke ticker
    watchlist saja. Memakai cached_scan yang sama dengan Scanner Lab --
    tidak memindai ulang.
    """
    try:
        payload = cached_scan(days_back=days_back)
    except Exception:
        return {}
    df = payload.get('df')
    if df is None or df.empty:
        return {}

    sub = df[df['stock'].isin(tickers)].copy()
    if sub.empty:
        return {}
    sub['scanner_label'] = sub['scanner'].map(lambda k: SCANNERS.get(k, {}).get('label', k))
    sub['retrospective'] = False
    sub['fwd20'] = None
    try:
        sub = scanner_enrich(sub)
    except Exception:
        pass

    out = {}
    for _, row in sub.iterrows():
        ticker = row['stock']
        score, reasons = score_signal(row, None)
        entry = {
            'signal_date': row['signal_date'].strftime('%Y-%m-%d'),
            'scanner_label': row['scanner_label'],
            'pending': bool(row.get('pending')),
            'forward_needed': FORWARD_NEEDED.get(row['scanner'], 20),
            'score': score,
        }
        # Simpan yang skornya PALING TINGGI per ticker -- itu yang paling
        # layak dilihat dulu kalau satu saham punya beberapa sinyal.
        if ticker not in out or entry['score'] > out[ticker]['score']:
            out[ticker] = entry
    return out


def _kering_candidates_by_ticker(tickers, days_back=14):
    """Kandidat Kering Screener terbaru, dipersempit ke ticker watchlist."""
    try:
        data = kering_refresh()
    except Exception:
        return {}
    events = data.get('events')
    if events is None or events.empty:
        return {}

    cutoff = events['date'].max() - pd.Timedelta(days=days_back)
    sub = events[(events['date'] >= cutoff) & (events['ticker'].isin(tickers))]
    if sub.empty:
        return {}
    sub = sub.sort_values('skor', ascending=False)

    out = {}
    for _, r in sub.iterrows():
        ticker = r['ticker']
        if ticker in out:
            continue
        out[ticker] = {
            'date': r['date'].strftime('%Y-%m-%d'),
            'skor': round(float(r['skor']), 3),
            'K': int(r['K']),
        }
    return out


def _screen_by_ticker(tickers):
    """Screen yang sedang menampung tiap ticker, beserta rekam jejaknya."""
    try:
        report = screen_build_report()
    except Exception:
        report = {'available': False}
    record_by_key = {}
    if report.get('available'):
        for s in report['screens']:
            record_by_key[s['key']] = s

    out = {}
    for ticker in tickers:
        df = load_summary_for_screen(ticker)
        if df is None or len(df) < 60:
            continue
        try:
            cats, _ = classify_history(df)
        except Exception:
            continue
        if not cats or not cats[-1]:
            continue
        key = cats[-1]
        streak = 0
        for cat in reversed(cats):
            if cat != key:
                break
            streak += 1
        out[ticker] = {'key': key, 'streak_days': streak,
                       'record': record_by_key.get(key)}
    return out


def _insider_by_ticker(tickers, days_back=30):
    """Ringkasan Beli/Jual insider per ticker dalam N hari terakhir."""
    df = load_insider()
    if df.empty:
        return {}
    cutoff = df['date'].max() - pd.Timedelta(days=days_back)
    sub = df[(df['date'] >= cutoff) & (df['ticker'].isin(tickers)) & (df['is_market_trade'])]
    if sub.empty:
        return {}
    sub = insider_enrich_prices(sub)

    out = {}
    for ticker, g in sub.groupby('ticker'):
        n_buy = int((g['action_type'] == 'ACTION_TYPE_BUY').sum())
        n_sell = int((g['action_type'] == 'ACTION_TYPE_SELL').sum())
        buy_value = float(g.loc[g['action_type'] == 'ACTION_TYPE_BUY', 'value_idr'].fillna(0).sum())
        sell_value = float(g.loc[g['action_type'] == 'ACTION_TYPE_SELL', 'value_idr'].fillna(0).sum())
        last_date = g['date'].max()
        out[ticker] = {
            'n_buy': n_buy, 'n_sell': n_sell,
            'net_value_idr': buy_value - sell_value,
            'last_date': last_date.strftime('%Y-%m-%d'),
            # Observasi pasif, bukan sinyal tervalidasi -- lihat docstring
            # insider_activity.buy_cluster_count().
            'buy_cluster_5d': buy_cluster_count(df, ticker),
        }
    return out


def build_digest(watchlists=None, insider_days=30):
    """
    Ringkasan siap-tampil: satu baris per ticker watchlist, dengan apa
    pun yang sedang terjadi pada saham itu menurut modul-modul lain.

    `watchlists`: subset nama watchlist untuk disaring (None = semua).
    """
    membership = watchlist_membership()
    if watchlists:
        wanted = set(watchlists)
        membership = {t: [w for w in ws if w in wanted]
                     for t, ws in membership.items()}
        membership = {t: ws for t, ws in membership.items() if ws}

    if not membership:
        return {'available': False, 'message': 'Watchlist kosong -- tambah saham dulu ke Portfolio/Best/Best Low/Pattern Up.'}

    tickers = list(membership.keys())

    # Tanggal acuan buat kartu mini di templates/watchlist_digest.html --
    # dipakai DecisionCard.keringVerdict() di sana buat menghitung "berapa
    # hari lalu" kandidat Kering muncul. kering_refresh() sudah kena cache
    # (dipanggil lagi di _kering_candidates_by_ticker di bawah), jadi ini
    # nyaris gratis, bukan pemindaian kedua.
    try:
        as_of = kering_refresh()['events']['date'].max().strftime('%Y-%m-%d')
    except Exception:
        as_of = None

    scanner_map = _scanner_signals_by_ticker(tickers)
    kering_map = _kering_candidates_by_ticker(tickers)
    screen_map = _screen_by_ticker(tickers)
    insider_map = _insider_by_ticker(tickers, days_back=insider_days)

    rows = []
    for ticker in tickers:
        scanner = scanner_map.get(ticker)
        kering = kering_map.get(ticker)
        screen = screen_map.get(ticker)
        insider = insider_map.get(ticker)

        # Kesehatan arus HANYA dihitung kalau ada sesuatu untuk dicek --
        # tanpa sinyal scanner maupun kandidat Kering, tidak ada tanggal
        # acuan untuk mengukur "setelah sinyal".
        flow = None
        anchor_date = None
        if scanner:
            anchor_date = scanner['signal_date']
        elif kering:
            anchor_date = kering['date']
        if anchor_date:
            try:
                fh = flow_check(ticker, anchor_date)
                if fh.get('available'):
                    available_cps = [c for c in fh['checkpoints'] if c['available']]
                    if available_cps:
                        flow = max(available_cps, key=lambda c: c['horizon'])
            except Exception:
                flow = None

        has_anything = bool(scanner or kering or screen or insider)
        rows.append({
            'ticker': ticker,
            'watchlists': membership[ticker],
            'scanner': scanner,
            'kering': kering,
            'screen': screen,
            'insider': insider,
            'flow': flow,
            'has_anything': has_anything,
        })

    # Simpan snapshot harian (reason='daily') dari data yang SUDAH
    # dihitung di atas, dedup otomatis per ticker per hari -- lihat
    # decision_journal.py. Import di dalam fungsi (bukan di atas modul)
    # untuk menghindari circular import: decision_journal.py mengimpor
    # balik _scanner_signals_by_ticker/_kering_candidates_by_ticker dari
    # modul ini.
    daily_diff = {}
    try:
        from .decision_journal import save_daily_snapshots_from_rows, daily_diff_for_tickers
        save_daily_snapshots_from_rows(rows)
        # Dipanggil SETELAH menyimpan snapshot hari ini -- supaya "dua
        # snapshot terakhir" berarti hari ini vs kemarin, bukan kemarin
        # vs kemarin-lusa.
        daily_diff = daily_diff_for_tickers(tickers)
    except Exception:
        daily_diff = {}
    for r in rows:
        r['daily_diff'] = daily_diff.get(r['ticker'])

    try:
        market_regime = get_regime()
    except Exception:
        market_regime = {'available': False}

    # Yang punya kejadian tampil duluan; sisanya (saham watchlist yang
    # hari ini "diam") tetap ditampilkan di bawah, bukan disembunyikan --
    # "tidak ada apa-apa" itu sendiri informasi yang sah.
    rows.sort(key=lambda r: (not r['has_anything'], r['ticker']))

    return {
        'available': True,
        'market_regime': market_regime,
        'total': len(rows),
        'dengan_kejadian': sum(1 for r in rows if r['has_anything']),
        'as_of': as_of,
        'rows': rows,
    }
