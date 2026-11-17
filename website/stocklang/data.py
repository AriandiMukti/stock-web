"""
Price + broker-flow data for StockLang, read from the same Daily\\Summary
CSVs the rest of the app uses (one <CODE>_Summary.csv per stock).

Columns are exposed to scripts under short snake_case names so a script
says `net_top5` instead of `col("Net Top5 All Lot")`.
"""
try:
    from ..runtime_paths import runtime_file as _runtime_file, market_file as _market_file, WEBSITE_DIR as _WEBSITE_DIR, PROJECT_DIR as _PROJECT_DIR, RUNTIME_DIR as _RUNTIME_DIR
except ImportError:
    from website.runtime_paths import runtime_file as _runtime_file, market_file as _market_file, WEBSITE_DIR as _WEBSITE_DIR, PROJECT_DIR as _PROJECT_DIR, RUNTIME_DIR as _RUNTIME_DIR
import os
import pickle
import time
from functools import lru_cache

import numpy as np
import pandas as pd

from .errors import StockLangError

try:
    from ..config import DAILY_PATH          # imported as website.stocklang
except ImportError:
    try:
        from config import DAILY_PATH        # run from inside website/
    except ImportError:
        DAILY_PATH = os.environ.get('BDM_BASE_PATH', _market_file('')) + 'Daily/'

SUMMARY_DIR = os.environ.get('STOCKLANG_DATA', os.path.join(DAILY_PATH, 'Summary'))

# script name -> CSV column
COLUMNS = {
    'open': 'Open',
    'high': 'High',
    'low': 'Low',
    'close': 'Close',
    'volume': 'Volume',
    'avg_price': 'Avg Price',
    'net_top3': 'Net Top3 All Lot',
    'net_top5': 'Net Top5 All Lot',
    'foreign_top3': 'Net Top3 Foreign Lot',
    'foreign_top5': 'Net Top5 Foreign Lot',
    'net_value': 'Net Value',
    'net_lot': 'Net Lot',
    'buyers': 'Total Buyer',
    'sellers': 'Total Seller',
    'retail': 'Retail',
}


_RENAME = {v: k for k, v in COLUMNS.items()}
_WANTED = set(COLUMNS.values()) | {'Date'}
# Flow columns are blank on days with no broker activity; those mean zero.
FLOW = [c for c in COLUMNS if c not in ('open', 'high', 'low', 'close', 'volume', 'avg_price')]


def all_symbols():
    if not os.path.isdir(SUMMARY_DIR):
        raise StockLangError(f"data folder not found: {SUMMARY_DIR}")
    return sorted(f[:-len('_Summary.csv')] for f in os.listdir(SUMMARY_DIR) if f.endswith('_Summary.csv'))


@lru_cache(maxsize=None)
def load(symbol):
    """DataFrame indexed by date with the COLUMNS above, or None if there's no data."""
    path = os.path.join(SUMMARY_DIR, f"{symbol}_Summary.csv")
    if not os.path.exists(path):
        return None
    try:
        raw = pd.read_csv(path, usecols=lambda c: c in _WANTED)
    except (pd.errors.EmptyDataError, ValueError):
        return None
    if raw.empty or 'Date' not in raw:
        return None
    raw.index = pd.to_datetime(raw.pop('Date'), format='%d-%b-%y', errors='coerce')
    raw = raw[raw.index.notna()]
    raw = raw[~raw.index.duplicated(keep='last')].sort_index()
    try:
        num = raw.astype(float)
    except (TypeError, ValueError):
        num = raw.apply(pd.to_numeric, errors='coerce')
    out = num.rename(columns=_RENAME).reindex(columns=list(COLUMNS))
    out[FLOW] = out[FLOW].fillna(0.0)
    out.index.name = None
    return out if len(out) else None


CACHE_FILE = str(_runtime_file('stocklang', '.cache', 'summary.pkl'))


def load_many(symbols):
    """
    Load many stocks at once, through an on-disk cache keyed by each CSV's
    modification time, size, and exposed columns: parsing ~900 CSVs takes a few seconds,
    unpickling them takes a fraction of one. Only files that changed since
    the last run get parsed again.
    """
    try:
        with open(CACHE_FILE, 'rb') as f:
            cache = pickle.load(f)
    except Exception:
        cache = {}
    changed = False
    out = []
    for sym in symbols:
        path = os.path.join(SUMMARY_DIR, f"{sym}_Summary.csv")
        try:
            st = os.stat(path)
        except OSError:
            out.append(None)
            continue
        key = (st.st_mtime_ns, st.st_size, tuple(COLUMNS))
        hit = cache.get(sym)
        if hit is not None and hit[0] == key:
            out.append(hit[1])
            continue
        df = load.__wrapped__(sym)
        cache[sym] = (key, df)
        changed = True
        out.append(df)
    if changed:
        try:
            os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
            tmp = CACHE_FILE + '.tmp'
            with open(tmp, 'wb') as f:
                pickle.dump(cache, f, protocol=pickle.HIGHEST_PROTOCOL)
            os.replace(tmp, CACHE_FILE)
        except OSError:
            pass    # a cache we can't write just means a slower next run
    return out


IHSG_CACHE = str(_runtime_file('stocklang', '.cache', 'ihsg.pkl'))
_ihsg_memo = None


def _newest_summary():
    try:
        return max((e.stat().st_mtime for e in os.scandir(SUMMARY_DIR) if e.name.endswith('_Summary.csv')),
                   default=0.0)
    except OSError:
        return 0.0


def _fetch_ihsg():
    """IHSG (^JKSE) daily close from Yahoo Finance, or None if it can't be reached."""
    try:
        import yfinance as yf
        df = yf.download('^JKSE', period='5y', interval='1d', progress=False, auto_adjust=False)
        if df.empty:
            return None
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        close = df['Close'].dropna().astype(float)
        close.index = pd.DatetimeIndex(close.index).tz_localize(None).normalize()
        return close
    except Exception:
        return None


def ihsg():
    """
    IHSG daily close, date-indexed. Fetched from Yahoo Finance and cached;
    fetched again once newer Summary files arrive (the same rule as
    market_correlation.py), so a day's runs don't keep calling Yahoo.
    """
    global _ihsg_memo
    if _ihsg_memo is not None:
        return _ihsg_memo
    cached = None
    try:
        with open(IHSG_CACHE, 'rb') as f:
            cached = pickle.load(f)
    except Exception:
        pass
    if cached is not None and cached['built_at'] >= _newest_summary():
        _ihsg_memo = cached['close']
        return _ihsg_memo
    fresh = _fetch_ihsg()
    if fresh is None:
        if cached is not None:              # offline: a stale copy beats nothing
            _ihsg_memo = cached['close']
            return _ihsg_memo
        raise StockLangError("IHSG data isn't available: Yahoo Finance couldn't be reached and "
                             "there's no saved copy yet")
    try:
        os.makedirs(os.path.dirname(IHSG_CACHE), exist_ok=True)
        with open(IHSG_CACHE, 'wb') as f:
            pickle.dump({'built_at': time.time(), 'close': fresh}, f)
    except OSError:
        pass
    _ihsg_memo = fresh
    return fresh


class Universe:
    """
    Many stocks packed side by side: for each column (close, volume, ...)
    one DataFrame with a column per stock, so a script line runs once for
    the whole market instead of once per stock.

    Rows are bars counted from the end (right-aligned), not calendar dates.
    That keeps every rolling window identical to running the stock on its
    own -- a stock with a missing day doesn't get a NaN hole that would
    blank out its 20-day average for the next 20 days. Stocks with less
    history are padded with NaN at the top, just like indicator warm-up.
    """

    def __init__(self, symbols):
        loaded = load_many(symbols)
        self.missing = [s for s, df in zip(symbols, loaded) if df is None]
        pairs = [(s, df) for s, df in zip(symbols, loaded) if df is not None]
        self.symbols = [s for s, _ in pairs]
        self.dates = {s: df.index for s, df in pairs}
        n = max((len(df) for _, df in pairs), default=0)
        self.frames = {}
        for name in COLUMNS:
            arr = np.full((n, len(pairs)), np.nan)
            for j, (_, df) in enumerate(pairs):
                arr[n - len(df):, j] = df[name].to_numpy()
            self.frames[name] = pd.DataFrame(arr, columns=self.symbols)
        self.last_date = pd.Series({s: d[-1] for s, d in self.dates.items()}, dtype='datetime64[ns]')

    def stock_frame(self, symbol):
        """One stock back as a normal date-indexed DataFrame (for the backtester)."""
        k = len(self.dates[symbol])
        return pd.DataFrame({name: f[symbol].to_numpy()[-k:] for name, f in self.frames.items()},
                            index=self.dates[symbol])

    @property
    def calendar(self):
        """Every trading date any stock in the universe has, sorted."""
        if getattr(self, '_calendar', None) is None:
            dates = list(self.dates.values())
            self._calendar = dates[0].append(dates[1:]).unique().sort_values() if dates else pd.DatetimeIndex([])
        return self._calendar

    def by_date(self, frame):
        """A bar-aligned frame turned date-indexed: rows are calendar dates, NaN where a stock didn't trade."""
        cols = {s: pd.Series(frame[s].to_numpy()[-len(d):], index=d) for s, d in self.dates.items()}
        return pd.DataFrame(cols, columns=self.symbols).reindex(self.calendar)

    def stock_series(self, frame, symbol):
        k = len(self.dates[symbol])
        return pd.Series(frame[symbol].to_numpy()[-k:], index=self.dates[symbol])

    def to_bars(self, frame):
        """Inverse of by_date: a date-indexed frame back to bar-aligned rows (a value per stock per bar)."""
        n = len(self.frames['close'])
        arr = np.full((n, len(self.symbols)), np.nan)
        for j, s in enumerate(self.symbols):
            d = self.dates[s]
            col = frame[s] if s in frame else pd.Series(dtype=float)
            arr[n - len(d):, j] = col.reindex(d).to_numpy(dtype=float)
        return pd.DataFrame(arr, columns=self.symbols)
