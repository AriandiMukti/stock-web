"""Yahoo weekly EMA10/20 screener. Downloads run outside request threads."""
try:
    from .runtime_paths import runtime_file as _runtime_file, market_file as _market_file, WEBSITE_DIR as _WEBSITE_DIR, PROJECT_DIR as _PROJECT_DIR, RUNTIME_DIR as _RUNTIME_DIR
except ImportError:
    from website.runtime_paths import runtime_file as _runtime_file, market_file as _market_file, WEBSITE_DIR as _WEBSITE_DIR, PROJECT_DIR as _PROJECT_DIR, RUNTIME_DIR as _RUNTIME_DIR
import copy
import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Lock, Thread

import pandas as pd
from flask import Blueprint, jsonify, render_template
from flask_login import current_user, login_required

ema_weekly = Blueprint('ema_weekly', __name__)
JAKARTA = timezone(timedelta(hours=7))
CACHE_FILE = _runtime_file('', 'ema_weekly_cache.json')
TTL = timedelta(hours=1)
_lock = Lock()
_state = {'running': False, 'processed': 0, 'total': 0, 'error': None}
_report = None
log = logging.getLogger(__name__)


def last_closed_week(now=None):
    """Friday label; conservatively wait until 18:00 WIB on Friday."""
    now = now or datetime.now(JAKARTA)
    if now.tzinfo is None:
        now = now.replace(tzinfo=JAKARTA)
    now = now.astimezone(JAKARTA)
    friday = now.date() + timedelta(days=4 - now.weekday())
    if now.date() < friday or (now.date() == friday and now.hour < 18):
        friday -= timedelta(days=7)
    return pd.Timestamp(friday)


def ticker_frame(data, symbol):
    if data is None or data.empty:
        return pd.DataFrame()
    if isinstance(data.columns, pd.MultiIndex):
        for level in range(data.columns.nlevels):
            if symbol in data.columns.get_level_values(level):
                return data.xs(symbol, axis=1, level=level).dropna(how='all')
        return pd.DataFrame()
    return data.dropna(how='all')


def evaluate(frame, ticker, cutoff):
    """Return only actual crossings in the last TWO calendar trading weeks."""
    if frame.empty or 'Close' not in frame:
        return None, 'unavailable'
    close = pd.to_numeric(frame['Close'], errors='coerce')
    idx = pd.DatetimeIndex(close.index)
    if idx.tz is not None:
        idx = idx.tz_localize(None)
    close.index = idx
    close = close.sort_index()
    close = close[close.notna() & (close > 0)]
    # Yahoo 1wk bars normally use Monday timestamps. Use Friday week labels
    # so partial current-week bars cannot masquerade as confirmed signals.
    close = close.groupby(close.index.to_period('W-FRI')).last()
    close.index = close.index.to_timestamp(how='end').normalize()
    close = close[close.index <= cutoff]
    if len(close) < 21:
        return None, 'short_history'
    if close.index[-1] < cutoff:
        return None, 'stale'
    fast = close.ewm(span=10, adjust=False, min_periods=10).mean()
    slow = close.ewm(span=20, adjust=False, min_periods=20).mean()
    golden = (fast > slow) & (fast.shift(1) <= slow.shift(1))
    # Calendar weeks, not the last two available bars of a suspended ticker.
    hits = golden[golden & (golden.index >= cutoff - pd.Timedelta(weeks=1))]
    if hits.empty:
        return None, 'ok'
    date = hits.index[-1]
    pos = close.index.get_loc(date)
    if close.index[pos - 1] != date - pd.Timedelta(weeks=1):
        return None, 'ok'
    return {
        'ticker': ticker, 'signal_week': date.date().isoformat(),
        'weeks_ago': int((cutoff - date).days // 7),
        'close': float(close.iloc[-1]), 'ema10': float(fast.loc[date]),
        'ema20': float(slow.loc[date]),
        'previous_ema10': float(fast.iloc[pos - 1]),
        'previous_ema20': float(slow.iloc[pos - 1]),
        'still_above': bool(fast.iloc[-1] > slow.iloc[-1]),
    }, 'ok'


def _universe():
    from .models import stockList
    return sorted(set(stockList))


def _download(symbols):
    import yfinance as yf
    return yf.download(symbols, period='5y', interval='1wk',
                       auto_adjust=True, group_by='ticker', threads=4,
                       progress=False, timeout=15)


def _scan():
    global _report
    try:
        tickers = _universe()
        if not tickers:
            raise RuntimeError('Daftar saham kosong.')
        cutoff = last_closed_week()
        with _lock:
            _state.update(total=len(tickers), processed=0)
        counts = dict(ok=0, unavailable=0, short_history=0, stale=0)
        rows, skipped = [], []
        for start in range(0, len(tickers), 40):
            batch = tickers[start:start + 40]
            try:
                data = _download([t + '.JK' for t in batch])
            except Exception:
                log.exception('Unduhan Yahoo EMA weekly gagal')
                data = pd.DataFrame()
            for ticker in batch:
                try:
                    row, status = evaluate(ticker_frame(data, ticker + '.JK'), ticker, cutoff)
                except Exception:
                    log.exception('Data EMA weekly tidak valid: %s', ticker)
                    row, status = None, 'unavailable'
                counts[status] += 1
                if status != 'ok':
                    skipped.append({'ticker': ticker, 'reason': status})
                if row:
                    rows.append(row)
            with _lock:
                _state['processed'] = min(start + len(batch), len(tickers))
        if counts['ok'] == 0:
            raise RuntimeError('Tidak ada data mingguan terbaru yang dapat dianalisis dari Yahoo Finance. Coba lagi nanti.')
        report = {
            'updated_at': datetime.now(JAKARTA).isoformat(timespec='seconds'),
            'week_ending': cutoff.date().isoformat(), 'total': len(tickers),
            'counts': counts, 'skipped': skipped,
            'rows': sorted(rows, key=lambda row: (-int(row['signal_week'].replace('-', '')), row['ticker'])),
        }
        with _lock:
            _report = report
        try:
            temp = CACHE_FILE.with_suffix('.tmp')
            temp.write_text(json.dumps(report, allow_nan=False), encoding='utf-8')
            temp.replace(CACHE_FILE)
        except OSError:
            log.exception('Cache EMA weekly tidak dapat ditulis')
    except Exception as exc:
        with _lock:
            _state['error'] = str(exc)
    finally:
        with _lock:
            _state['running'] = False


def snapshot(refresh=False):
    global _report
    with _lock:
        if _report is None:
            try:
                cached = json.loads(CACHE_FILE.read_text(encoding='utf-8'))
                datetime.fromisoformat(cached['updated_at'])
                if isinstance(cached['rows'], list) and 'counts' in cached:
                    _report = cached
            except (OSError, ValueError, KeyError, TypeError):
                pass
        try:
            expired = (_report is None or
                       datetime.now(JAKARTA) - datetime.fromisoformat(_report['updated_at']) >= TTL or
                       _report['week_ending'] != last_closed_week().date().isoformat())
        except (ValueError, KeyError, TypeError):
            expired = True
        if not _state['running'] and (refresh or (expired and not _state['error'])):
            _state.update(running=True, processed=0, total=0, error=None)
            Thread(target=_scan, name='ema-weekly-scan', daemon=True).start()
        result = copy.deepcopy(dict(_state, report=_report, stale=expired))
        # Re-age cached signals against today's closed week, even if a refresh
        # fails. A saved signal must never outlive the requested two weeks.
        if result['report']:
            cutoff = last_closed_week()
            rows = result['report']['rows']
            for row in rows:
                row['weeks_ago'] = int((cutoff - pd.Timestamp(row['signal_week'])).days // 7)
            result['report']['rows'] = [row for row in rows if 0 <= row['weeks_ago'] < 2]
        return result


@ema_weekly.route('/ema-weekly')
@login_required
def page():
    return render_template('ema_weekly.html', user=current_user)


@ema_weekly.route('/ema-weekly/data')
@login_required
def data():
    return jsonify(snapshot())


@ema_weekly.route('/ema-weekly/refresh', methods=['POST'])
@login_required
def refresh():
    return jsonify(snapshot(refresh=True))
