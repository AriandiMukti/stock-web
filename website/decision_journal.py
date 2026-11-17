"""
Menangkap dan membaca snapshot kartu keputusan (lihat DecisionSnapshot di
models.py) untuk dua fitur:

1. Jurnal Keputusan (reason='watchlist_add') -- "waktu Anda menambah
   saham ini, kartu keputusannya bilang apa, dan apa yang terjadi
   sejak itu". Bukan tentang apakah pasar bisa diprediksi, tapi apakah
   keputusan ANDA SENDIRI cenderung benar saat sinyalnya begini vs
   begitu -- sesuatu yang tidak dijawab backtest pasar manapun karena
   itu pola Anda, bukan pola saham.

2. Perubahan Sejak Kemarin (reason='daily') -- satu snapshot per ticker
   per hari kalender, dipakai untuk mencari bendera yang berubah warna
   dari hari ke hari, bukan cuma status hari ini.

TIDAK menghitung ulang apa pun yang baru: scanner/kering/flow dipakai
ulang dari fungsi yang sama persis dengan digest.py (_scanner_signals_
by_ticker, _kering_candidates_by_ticker, flow_check), disimpan dalam
bentuk mentah yang sama supaya DecisionCard.scoreVerdict/flowVerdict/
keringVerdict (static/js/stock_chart.js) bisa dipakai ulang tanpa
logika verdict baru di Python.
"""
import json
from datetime import datetime, timedelta

from . import db
from .models import DecisionSnapshot
from .digest import _scanner_signals_by_ticker, _kering_candidates_by_ticker
from .flow_health import check as flow_check
from .stock_hub import load_summary


def _capture_fields(ticker):
    """(entryPrice, scanner_dict_or_None, kering_dict_or_None, flow_dict_or_None) untuk satu ticker, sekarang."""
    df = load_summary(ticker)
    entry_price = float(df['Close'].iloc[-1]) if df is not None and not df.empty else None

    scanner = _scanner_signals_by_ticker([ticker]).get(ticker)
    kering = _kering_candidates_by_ticker([ticker]).get(ticker)

    flow = None
    anchor_date = scanner['signal_date'] if scanner else (kering['date'] if kering else None)
    if anchor_date:
        try:
            fh = flow_check(ticker, anchor_date)
            if fh.get('available'):
                available_cps = [c for c in fh['checkpoints'] if c['available']]
                if available_cps:
                    flow = max(available_cps, key=lambda c: c['horizon'])
        except Exception:
            flow = None

    return entry_price, scanner, kering, flow


def capture_snapshot(ticker, list_type, reason, app=None, user_id=None):
    """
    Menangkap satu snapshot dan menyimpannya. Dipanggil dari thread
    background (lihat pemanggilnya di utilities.py/digest.py) supaya
    tidak menambah latensi ke aksi yang memicunya (nambah ke watchlist,
    atau memuat Ringkasan Watchlist) -- `app` wajib diisi kalau dipanggil
    dari luar request context, supaya bisa buka app_context sendiri.
    """
    def _run():
        try:
            entry_price, scanner, kering, flow = _capture_fields(ticker)
            db.session.add(DecisionSnapshot(
                stock=ticker, listType=list_type, reason=reason,
                userId=user_id,
                entryPrice=entry_price,
                scannerJson=json.dumps(scanner) if scanner else None,
                keringJson=json.dumps(kering) if kering else None,
                flowJson=json.dumps(flow) if flow else None,
            ))
            db.session.commit()
        except Exception:
            db.session.rollback()
            raise

    if app is not None:
        with app.app_context():
            _run()
    else:
        _run()


def capture_daily_for_tickers(tickers, app=None):
    """
    Satu snapshot reason='daily' per ticker per hari kalender -- dilewati
    kalau ticker itu sudah punya snapshot 'daily' hari ini (dicek dulu,
    bukan upsert, supaya tidak menimpa snapshot pagi dengan versi sore
    yang datanya sama tapi lebih baru waktunya tanpa alasan).
    """
    def _run():
        # UTC, bukan waktu lokal -- func.now() (default kolom timestamp
        # di models.py) menyimpan UTC di SQLite, jadi pembanding "hari
        # ini" harus UTC juga. Ketahuan lewat bug nyata: dipakai
        # datetime.now() (lokal, WIB/UTC+7) sempat lolos dua snapshot
        # 'daily' di hari kalender lokal yang sama karena batas tengah
        # malam lokal jatuh 7 jam lebih awal dari batas UTC yang
        # sebenarnya dipakai buat menyimpan.
        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        already = {row[0] for row in db.session.query(DecisionSnapshot.stock)
                   .filter(DecisionSnapshot.reason == 'daily',
                           DecisionSnapshot.timestamp >= today_start,
                           DecisionSnapshot.stock.in_(tickers)).all()}
        missing = [t for t in tickers if t not in already]
        for t in missing:
            try:
                entry_price, scanner, kering, flow = _capture_fields(t)
                db.session.add(DecisionSnapshot(
                    stock=t, listType=None, reason='daily',
                    entryPrice=entry_price,
                    scannerJson=json.dumps(scanner) if scanner else None,
                    keringJson=json.dumps(kering) if kering else None,
                    flowJson=json.dumps(flow) if flow else None,
                ))
            except Exception:
                continue
        if missing:
            db.session.commit()

    if app is not None:
        with app.app_context():
            _run()
    else:
        _run()


def save_daily_snapshots_from_rows(rows):
    """
    Sama seperti capture_daily_for_tickers(), tapi menyimpan data yang
    SUDAH DIHITUNG build_digest() (rows: list of {'ticker','scanner',
    'kering','flow'}) alih-alih menghitung ulang scanner/kering/flow per
    ticker dari awal -- dipanggil langsung dari digest.py supaya tidak
    ada pemanggilan ganda ke fungsi yang sama.
    """
    if not rows:
        return
    # UTC, bukan waktu lokal -- lihat catatan di capture_daily_for_tickers().
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    tickers = [r['ticker'] for r in rows]
    already = {row[0] for row in db.session.query(DecisionSnapshot.stock)
               .filter(DecisionSnapshot.reason == 'daily',
                       DecisionSnapshot.timestamp >= today_start,
                       DecisionSnapshot.stock.in_(tickers)).all()}
    added = False
    for r in rows:
        if r['ticker'] in already:
            continue
        db.session.add(DecisionSnapshot(
            stock=r['ticker'], listType=None, reason='daily',
            entryPrice=None,
            scannerJson=json.dumps(r['scanner']) if r.get('scanner') else None,
            keringJson=json.dumps(r['kering']) if r.get('kering') else None,
            flowJson=json.dumps(r['flow']) if r.get('flow') else None,
        ))
        added = True
    if added:
        db.session.commit()


def _row_to_dict(row):
    return {
        'id': row.id, 'stock': row.stock, 'listType': row.listType,
        'reason': row.reason, 'timestamp': row.timestamp.isoformat() if row.timestamp else None,
        'entryPrice': row.entryPrice,
        'scanner': json.loads(row.scannerJson) if row.scannerJson else None,
        'kering': json.loads(row.keringJson) if row.keringJson else None,
        'flow': json.loads(row.flowJson) if row.flowJson else None,
    }


def journal_entries(limit=200):
    """
    Jurnal Keputusan: snapshot 'watchlist_add' + harga sekarang, buat
    dibandingkan client-side. Harga sekarang dibaca ulang dari Summary
    (bukan disimpan di snapshot -- kalau begitu tidak akan pernah
    ter-update).
    """
    from .models import scoped_query
    rows = (scoped_query(DecisionSnapshot).filter_by(reason='watchlist_add')
            .order_by(DecisionSnapshot.timestamp.desc()).limit(limit).all())
    out = []
    price_cache = {}
    for row in rows:
        d = _row_to_dict(row)
        if row.stock not in price_cache:
            df = load_summary(row.stock)
            price_cache[row.stock] = float(df['Close'].iloc[-1]) if df is not None and not df.empty else None
        d['currentPrice'] = price_cache[row.stock]
        if d['entryPrice'] and d['currentPrice']:
            d['pctChange'] = round((d['currentPrice'] - d['entryPrice']) / d['entryPrice'] * 100, 2)
        else:
            d['pctChange'] = None
        out.append(d)
    return out


def daily_diff_for_tickers(tickers):
    """
    Untuk tiap ticker: dua snapshot 'daily' TERAKHIR (hari ini vs
    sebelumnya) -- selisihnya dipakai client-side (DecisionCard) untuk
    menandai bendera mana yang berubah warna. None kalau kurang dari
    2 snapshot (ticker baru, atau baru pertama kali dipantau).
    """
    out = {}
    for t in tickers:
        rows = (DecisionSnapshot.query
                .filter_by(reason='daily', stock=t)
                .order_by(DecisionSnapshot.timestamp.desc()).limit(2).all())
        if len(rows) < 2:
            continue
        out[t] = {'today': _row_to_dict(rows[0]), 'yesterday': _row_to_dict(rows[1])}
    return out
