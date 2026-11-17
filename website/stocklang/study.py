"""
Event study: "every time the condition was true, what happened next?"

Same rules as the backtester and the forward journal (stocklang_jurnal.py):
the condition is seen at a day's close, entry is the next bar's OPEN, and
the H-day result exits at the CLOSE of the H-th bar counting the entry bar
(H=1 is the entry day itself). Average/median/win rate are net of a
round-trip fee; the edge compares the gross result with a benchmark over
the exact same days, so a market-wide rally doesn't pass for a good signal.

- One stock: the benchmark is the same stock entered on any day.
- A universe: the benchmark is every stock entered on that same day.

Signals on consecutive days overlap (a 20-day window started on Monday
mostly shares its days with Tuesday's), so many signals is not the same as
many independent tries; the report says how many distinct stocks they
came from.
"""
import numpy as np
import pandas as pd


def forward(opens, closes, k):
    """Gross return entering at the next bar's open, exiting at the close k bars after the signal."""
    opens = opens.where(opens.notna(), closes)
    return closes.shift(-k) / opens.shift(-1) - 1


def _row(k, gross, bench, fee):
    net = gross - fee
    return {
        'days': k, 'n': int(len(gross)),
        'avg': float(net.mean() * 100) if len(net) else float('nan'),
        'median': float(np.median(net) * 100) if len(net) else float('nan'),
        'win': float((net > 0).mean() * 100) if len(net) else float('nan'),
        'bench': float(bench.mean() * 100) if len(bench) else float('nan'),
        'edge': float((gross - bench).mean() * 100) if len(gross) else float('nan'),
    }


def single(df, signal, days, fee):
    """df: one stock's date-indexed frame; signal: bool Series on the same index."""
    rows, first, last = [], None, None
    for k in days:
        fwd = forward(df['open'], df['close'], k)
        hit = signal & fwd.notna()
        gross = fwd[hit]
        bench = pd.Series(fwd.dropna().mean(), index=gross.index)
        rows.append(_row(k, gross, bench, fee))
        if len(gross):
            first = gross.index[0] if first is None else min(first, gross.index[0])
            last = gross.index[-1] if last is None else max(last, gross.index[-1])
    return {'rows': rows, 'stocks': 1 if first is not None else 0, 'first': first, 'last': last,
            'bench_label': 'Stock any day', 'fee': fee}


def universe(u, signal, days, fee):
    """u: data.Universe; signal: bar-aligned bool DataFrame (a column per stock)."""
    sig = u.by_date(signal) == True                  # noqa: E712  (NaN on non-trading days -> False)
    rows, stocks, first, last = [], set(), None, None
    for k in days:
        fwd = u.by_date(forward(u.frames['open'], u.frames['close'], k))
        market = fwd.mean(axis=1)                    # every stock, same entry day
        hit = sig & fwd.notna()
        gross = fwd.where(hit).stack(future_stack=True).dropna()
        bench = pd.Series(market.reindex(gross.index.get_level_values(0)).to_numpy(), index=gross.index)
        rows.append(_row(k, gross, bench, fee))
        if len(gross):
            dates = gross.index.get_level_values(0)
            stocks.update(gross.index.get_level_values(1))
            first = dates.min() if first is None else min(first, dates.min())
            last = dates.max() if last is None else max(last, dates.max())
    return {'rows': rows, 'stocks': len(stocks), 'first': first, 'last': last,
            'bench_label': 'All stocks same days', 'fee': fee}
