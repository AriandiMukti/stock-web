"""Event study satu saham: hanya data tersedia saat sinyal, entry open T+1."""
try:
    from .runtime_paths import runtime_file as _runtime_file, market_file as _market_file, WEBSITE_DIR as _WEBSITE_DIR, PROJECT_DIR as _PROJECT_DIR, RUNTIME_DIR as _RUNTIME_DIR
except ImportError:
    from website.runtime_paths import runtime_file as _runtime_file, market_file as _market_file, WEBSITE_DIR as _WEBSITE_DIR, PROJECT_DIR as _PROJECT_DIR, RUNTIME_DIR as _RUNTIME_DIR
import os
from functools import lru_cache

import numpy as np
import pandas as pd

from .broker_consistency import ALL_DIR, session_dates, read_days
from .config import DAILY_PATH

LABELS = {'buy': 'Top 5 beli lebih konsisten', 'sell': 'Top 5 jual lebih konsisten',
          'balanced': 'Top 5 seimbang'}


def comparison(returns, buy, sell, horizon):
    """Circular moving-block bootstrap; pertahankan ketergantungan antar sesi."""
    values = np.asarray(returns, dtype=float)
    buy, sell = np.asarray(buy, dtype=bool), np.asarray(sell, dtype=bool)
    valid = np.isfinite(values)
    buy, sell = buy & valid, sell & valid
    if buy.sum() < 2 or sell.sum() < 2:
        return None
    spread = float(values[buy].mean() - values[sell].mean())
    rng = np.random.default_rng(42)
    block = min(horizon + 4, len(values))
    n_blocks = int(np.ceil(len(values) / block))
    estimates = []
    for _ in range(1000):
        indexes = ((rng.integers(len(values), size=n_blocks)[:, None] + np.arange(block)) % len(values)).ravel()[:len(values)]
        b, s = buy[indexes], sell[indexes]
        if b.sum() >= 2 and s.sum() >= 2:
            sampled = values[indexes]
            estimates.append(sampled[b].mean() - sampled[s].mean())
    if len(estimates) < 200:
        return None
    low, high = np.percentile(estimates, [2.5, 97.5])
    return dict(spread=spread, low=float(low), high=float(high), draws=len(estimates))


def calculate(dates, daily, prices):
    dates = pd.DatetimeIndex(pd.to_datetime(dates)).sort_values().unique()
    prices = prices.copy()
    prices.index = pd.to_datetime(prices.index)
    prices = prices[~prices.index.duplicated(keep='last')].sort_index()
    # Kalender harga mengisi sesi bursa yang folder brokernya hilang.
    calendar = prices.index.union(dates).sort_values()
    p = prices.reindex(calendar)
    daily = {pd.Timestamp(d): v for d, v in daily.items()}
    observed = pd.Series([bool(daily.get(d)) for d in calendar], index=calendar)
    net = pd.DataFrame.from_dict({d: v for d, v in daily.items() if v}, orient='index').reindex(calendar).fillna(0)
    if len(calendar) < 30 or net.empty:
        return {'error': 'Histori belum cukup untuk backtest (minimal 30 sesi).'}
    def top5_counts(positive):
        counts = positive.rolling(5, min_periods=5).sum().to_numpy()
        return pd.Series(np.sort(counts, axis=1)[:, -5:].sum(axis=1) / 5, index=calendar)

    counts_buy = top5_counts(net.gt(0))
    counts_sell = top5_counts(net.lt(0))
    complete = observed.rolling(5, min_periods=5).sum().eq(5)
    masks = {'buy': counts_buy.gt(counts_sell), 'sell': counts_sell.gt(counts_buy),
             'balanced': counts_buy.eq(counts_sell)}
    split = int(len(calendar) * .7)
    positions = np.arange(len(calendar))
    rows, comparisons = [], []
    for horizon in (1, 5, 10, 20):
        entry = pd.to_numeric(p['Open'], errors='coerce').shift(-1)
        exit_price = pd.to_numeric(p['Close'], errors='coerce').shift(-horizon)
        returns = (exit_price / entry - 1) * 100
        valid = complete & entry.gt(0) & exit_price.gt(0) & np.isfinite(returns)
        if 'Volume' in p:
            volume = pd.to_numeric(p['Volume'], errors='coerce')
            valid &= volume.shift(-1).gt(0) & volume.shift(-horizon).gt(0)
        for period, period_mask in (
                ('Awal 70%', positions + horizon < split),
                ('Akhir 30%', positions >= split)):
            eligible = valid & period_mask
            baseline = returns[eligible].mean()
            stats = comparison(returns.where(valid)[period_mask],
                               masks['buy'][period_mask], masks['sell'][period_mask], horizon)
            if stats:
                comparisons.append(dict(period=period, horizon=horizon, **stats))
            for key, mask in masks.items():
                samples = returns[eligible & mask]
                if samples.empty:
                    continue
                rows.append(dict(period=period, label=LABELS[key], signal=key,
                                 horizon=horizon, n=len(samples), mean=float(samples.mean()),
                                 median=float(samples.median()), win_rate=float(samples.gt(0).mean() * 100),
                                 baseline=float(baseline), excess=float(samples.mean() - baseline)))
    return dict(start=str(calendar[0].date()), end=str(calendar[-1].date()),
                observations=int(complete.sum()), split=str(calendar[split].date()),
                rows=rows, comparisons=comparisons)


@lru_cache(maxsize=16)
def _cached(stock, directory, price_path, signature):
    dates = session_dates(directory)
    daily, _ = read_days(stock, dates, directory)
    prices = pd.read_csv(price_path, usecols=lambda c: c in ('Date', 'Open', 'Close', 'Volume'))
    prices['Date'] = pd.to_datetime(prices['Date'], format='%d-%b-%y', errors='coerce')
    prices = prices.dropna(subset=['Date']).set_index('Date')
    return calculate(dates, daily, prices)


def build(stock):
    price_path = os.path.join(DAILY_PATH, 'Summary', stock + '_Summary.csv')
    if not os.path.isfile(price_path):
        return {'error': 'Data harga historis saham ini belum tersedia.'}
    dates = session_dates(ALL_DIR)
    # Invalidate ketika arsip salah satu sesi diperbarui, termasuk overwrite.
    signature = [os.stat(price_path).st_mtime_ns]
    for day in dates:
        folder = os.path.join(ALL_DIR, day)
        signature.append(os.stat(folder).st_mtime_ns)
        for name in (stock + '.xls', '%s_ALL_%s.json' % (stock, day),
                     '%s_ALL_%s.json' % (stock, day.replace('-', ''))):
            path = os.path.join(folder, name)
            if os.path.isfile(path):
                info = os.stat(path)
                signature.extend((info.st_mtime_ns, info.st_size))
    return _cached(stock, ALL_DIR, price_path, tuple(signature))


if __name__ == '__main__':
    import argparse
    import json
    from datetime import datetime
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stocks', nargs='+', default=['ADRO', 'BBCA', 'BBRI', 'TLKM', 'ASII'])
    args = parser.parse_args()
    reports = {}
    for ticker in args.stocks:
        ticker = ticker.strip().upper()
        from .broker_consistency import build as current_build
        current_build(ticker)  # validasi kode yang sama dengan halaman
        reports[ticker] = build(ticker)
        print(ticker, json.dumps([r for r in reports[ticker].get('rows', [])
                                  if r['period'] == 'Akhir 30%' and r['horizon'] == 5]), flush=True)
        print('bootstrap', json.dumps([r for r in reports[ticker].get('comparisons', [])
                                       if r['period'] == 'Akhir 30%' and r['horizon'] == 5]), flush=True)
    destination = str(_runtime_file('', 'reports', 'broker_consistency_backtest.json'))
    os.makedirs(os.path.dirname(destination), exist_ok=True)
    with open(destination, 'w', encoding='utf-8') as fh:
        json.dump(dict(generated=datetime.now().isoformat(), stocks=reports), fh, indent=2, allow_nan=False)
    print('Saved:', destination)
