"""
Built-in functions available to StockLang scripts.

Every function works on whole pandas objects at once (vectorized): a
Series when the script runs on one stock, a DataFrame with one column per
stock when it runs on a universe. Either way `rsi(close, 14)` is a single
NumPy pass over the data -- the interpreter runs once per script line,
never once per bar or once per stock.
"""
import numpy as np
import pandas as pd

SERIES = (pd.Series, pd.DataFrame)


def is_series(x):
    return isinstance(x, SERIES)


def _like(x, like):
    """Promote a scalar to the same shape as `like`."""
    if is_series(x):
        return x
    if isinstance(like, pd.DataFrame):
        return pd.DataFrame(float(x), index=like.index, columns=like.columns)
    return pd.Series(float(x), index=like.index)


def _n(x, name='length'):
    try:
        n = int(x)
    except (TypeError, ValueError):
        raise ValueError(f"{name} must be a number")
    if n < 1:
        raise ValueError(f"{name} must be at least 1")
    return n


def _bar_number(x):
    """0, 1, 2, ... down the rows, shaped like x."""
    t = np.arange(len(x), dtype=float)
    if isinstance(x, pd.DataFrame):
        return pd.DataFrame(np.repeat(t[:, None], x.shape[1], axis=1), index=x.index, columns=x.columns)
    return pd.Series(t, index=x.index)


# ---- moving averages & bands ---------------------------------------------

def sma(x, n):
    return x.rolling(_n(n)).mean()


def ema(x, n):
    return x.ewm(span=_n(n), adjust=False, min_periods=_n(n)).mean()


def wma(x, n):
    # sum(w_k * x_k) with weights 1..n, from rolling sums instead of a
    # Python lambda per window:  sum((t - i + n) * x) = sum(t*x) - (i - n) * sum(x)
    n = _n(n)
    t = _bar_number(x)
    num = (t * x).rolling(n).sum() - (t - n) * x.rolling(n).sum()
    return num / (n * (n + 1) / 2)


def stdev(x, n):
    return x.rolling(_n(n)).std(ddof=0)


def bb_upper(x, n=20, k=2):
    return sma(x, n) + k * stdev(x, n)


def bb_lower(x, n=20, k=2):
    return sma(x, n) - k * stdev(x, n)


# ---- momentum -------------------------------------------------------------

def rsi(x, n=14):
    n = _n(n)
    d = x.diff()
    gain = d.clip(lower=0).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    loss = (-d).clip(lower=0).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    out = 100 - 100 / (1 + gain / loss)
    return out.where(loss != 0, 100.0).where(gain.notna())


def macd(x, fast=12, slow=26):
    return ema(x, fast) - ema(x, slow)


def macd_signal(x, fast=12, slow=26, signal=9):
    return ema(macd(x, fast, slow), signal)


def macd_hist(x, fast=12, slow=26, signal=9):
    return macd(x, fast, slow) - macd_signal(x, fast, slow, signal)


def roc(x, n=1):
    """Percent change over n bars."""
    return x.pct_change(_n(n), fill_method=None) * 100


def slope(x, n):
    """Average change per bar over the last n bars (least-squares slope)."""
    n = _n(n)
    if n < 2:
        return x.diff()
    t = _bar_number(x)
    mean = lambda v: v.rolling(n).mean()
    cov = mean(t * x) - mean(t) * mean(x)
    var_t = (n * n - 1) / 12          # variance of n consecutive integers
    return cov / var_t


# ---- volatility -----------------------------------------------------------

def atr(high, low, close, n=14):
    n = _n(n)
    prev = close.shift(1)
    tr = np.fmax(np.fmax(high - low, (high - prev).abs()), (low - prev).abs())
    return tr.ewm(alpha=1 / n, adjust=False, min_periods=n).mean()


# ---- windows --------------------------------------------------------------

def highest(x, n):
    return x.rolling(_n(n)).max()


def lowest(x, n):
    return x.rolling(_n(n)).min()


def total(x, n):
    """Sum of the last n bars (e.g. 5-day net foreign flow)."""
    return x.rolling(_n(n)).sum()


def cumsum(x):
    # Leading NaNs (warm-up / padding) stay NaN; gaps after that count as 0.
    return x.fillna(0).cumsum().where(x.ffill().notna())


# ---- signals --------------------------------------------------------------

def cross_up(a, b):
    a, b = _align(a, b)
    return ((a > b) & (a.shift(1) <= b.shift(1))).fillna(False)


def cross_down(a, b):
    a, b = _align(a, b)
    return ((a < b) & (a.shift(1) >= b.shift(1))).fillna(False)


def rising(x, n=1):
    return (x.diff() > 0).astype(float).rolling(_n(n)).sum() == _n(n)


def falling(x, n=1):
    return (x.diff() < 0).astype(float).rolling(_n(n)).sum() == _n(n)


def where(cond, a, b):
    if not is_series(cond):
        return a if cond else b
    cond = cond.fillna(False).astype(bool)
    return _like(a, cond).where(cond, _like(b, cond))


def _align(a, b):
    if is_series(a):
        return a, _like(b, a)
    if is_series(b):
        return _like(a, b), b
    raise ValueError("needs at least one series (like close or an indicator)")


# ---- math -----------------------------------------------------------------

def abs_(x):
    return x.abs() if is_series(x) else abs(x)


def max_(a, b):
    if is_series(a) or is_series(b):
        return np.maximum(*_align(a, b))
    return max(a, b)


def min_(a, b):
    if is_series(a) or is_series(b):
        return np.minimum(*_align(a, b))
    return min(a, b)


def round_(x, digits=0):
    return x.round(int(digits)) if is_series(x) else round(x, int(digits))


def last(x):
    """
    Most recent value. One stock: a plain number. A universe: one value
    per stock (so `if last(x) > 0` only makes sense on a single stock).
    """
    if isinstance(x, pd.DataFrame):
        return x.ffill().iloc[-1]
    if not isinstance(x, pd.Series):
        return x
    v = x.dropna()
    if v.empty:
        return float('nan')
    v = v.iloc[-1]
    return bool(v) if isinstance(v, (bool, np.bool_)) else float(v)


# name -> (function, short description). atr() gets high/low/close filled
# in by the interpreter.
BUILTINS = {
    'sma': (sma, 'sma(x, n) simple moving average'),
    'ema': (ema, 'ema(x, n) exponential moving average'),
    'wma': (wma, 'wma(x, n) weighted moving average'),
    'stdev': (stdev, 'stdev(x, n) standard deviation'),
    'bb_upper': (bb_upper, 'bb_upper(x, n=20, k=2) upper Bollinger band'),
    'bb_lower': (bb_lower, 'bb_lower(x, n=20, k=2) lower Bollinger band'),
    'rsi': (rsi, 'rsi(x, n=14) relative strength index'),
    'macd': (macd, 'macd(x, fast=12, slow=26) MACD line'),
    'macd_signal': (macd_signal, 'macd_signal(x, fast=12, slow=26, signal=9)'),
    'macd_hist': (macd_hist, 'macd_hist(x, fast=12, slow=26, signal=9)'),
    'roc': (roc, 'roc(x, n=1) percent change over n bars'),
    'slope': (slope, 'slope(x, n) average change per bar'),
    'atr': (atr, 'atr(n=14) average true range'),
    'highest': (highest, 'highest(x, n) highest value of last n bars'),
    'lowest': (lowest, 'lowest(x, n) lowest value of last n bars'),
    'total': (total, 'total(x, n) sum of last n bars'),
    'cumsum': (cumsum, 'cumsum(x) running total'),
    'cross_up': (cross_up, 'cross_up(a, b) a crosses above b'),
    'cross_down': (cross_down, 'cross_down(a, b) a crosses below b'),
    'rising': (rising, 'rising(x, n=1) up n bars in a row'),
    'falling': (falling, 'falling(x, n=1) down n bars in a row'),
    'where': (where, 'where(cond, a, b) a where cond is true, else b'),
    'abs': (abs_, 'abs(x)'),
    'max': (max_, 'max(a, b)'),
    'min': (min_, 'min(a, b)'),
    'round': (round_, 'round(x, digits=0)'),
    'last': (last, 'last(x) most recent value'),
}
