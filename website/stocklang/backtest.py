"""
Long-only backtest with IDX conventions.

- A signal seen at the close of day i is filled at the *open* of day i+1,
  so the strategy never trades on a price it couldn't have known yet.
- Shares are bought in whole lots of 100.
- Buy and sell fees are separate (IDX brokers usually charge more on the
  sell side because of the 0.1% sales tax).
- Optional exits are checked on each close and fill at the next open, same
  as a sell signal: stop_loss / take_profit (% from entry), atr_stop (N x
  ATR below entry, ATR as of the signal day), trailing_stop (% below the
  highest close since entry) and hold (sell after N bars in the trade).

IDX trading rules (idx_rules=True, the default):
- A buy can't fill at an open that is already at the upper auto-rejection
  limit (ARA): nobody is selling there. It's skipped, not queued.
- A sell can't fill at an open already at the lower limit (ARB): nobody is
  buying. It waits and tries again at the next open.
- A buy is capped at MAX_VOLUME_SHARE of that day's traded volume; a
  strategy can't buy 50 lots of a stock that trades 3.
The limits come from twin/aturan.py, the app's one copy of the IDX rules
(measured from raw prices there: ARA 35/25/20% by price band, ARB a flat
15% since 8 Apr 2025, tick sizes, Rp50 floor). Prices in the Summary files
are dividend-adjusted, so on older bars the limits are approximate.

This part is inherently sequential (today's position depends on
yesterday's), so it's a plain loop -- over NumPy arrays, a few hundred
bars take well under a millisecond.
"""
import math

import numpy as np
import pandas as pd

try:
    from ..twin import aturan             # imported as website.stocklang
except ImportError:
    from twin import aturan               # run from inside website/

LOT = 100
MAX_VOLUME_SHARE = 0.10

REASONS = (None, 'signal', 'stop loss', 'take profit', 'atr stop', 'trailing stop', 'max hold')


def upper_limit(prev_close):
    return float(aturan.batas_harian(prev_close)[1])


def lower_limit(prev_close):
    return float(aturan.batas_harian(prev_close)[0])


def _at_upper(price, prev_close):
    return not math.isnan(prev_close) and prev_close > 0 and price >= upper_limit(prev_close)


def _at_lower(price, prev_close):
    # At the Rp50 floor the limit equals yesterday's close: that's not a locked drop.
    if math.isnan(prev_close) or prev_close <= 0:
        return False
    low = lower_limit(prev_close)
    return low < prev_close and price <= low


def _exit_reason(c, entry, stop_px, peak, held, stop_loss, take_profit, trailing_stop, hold):
    """Index into REASONS of the first exit rule hit at this close, or 0."""
    change = c / entry - 1
    if stop_loss is not None and change <= -stop_loss:
        return 2
    if stop_px is not None and c <= stop_px:
        return 4
    if trailing_stop is not None and c <= peak * (1 - trailing_stop):
        return 5
    if take_profit is not None and change >= take_profit:
        return 3
    if hold is not None and held >= hold:
        return 6
    return 0


def run(df, buy, sell, capital=10_000_000, fee_buy=0.0015, fee_sell=0.0025,
        stop_loss=None, take_profit=None, atr_stop=None, atr=None, trailing_stop=None, hold=None,
        idx_rules=True):
    idx = df.index
    buy = _bool(buy, idx)
    sell = _bool(sell, idx)
    opens = df['open'].to_numpy(dtype=float)
    closes = df['close'].to_numpy(dtype=float)
    opens = np.where(np.isnan(opens), closes, opens)
    volumes = df['volume'].to_numpy(dtype=float) if 'volume' in df else np.full(len(idx), np.nan)
    atrs = atr.reindex(idx).to_numpy(dtype=float) if atr is not None else np.full(len(idx), np.nan)
    n = len(idx)

    cash = float(capital)
    shares = 0
    entry_price = entry_cost = 0.0
    entry_i = None
    stop_px = None
    peak = 0.0
    prev_close = math.nan
    pending = None           # 'buy' / ('sell', reason) to fill at next open
    trades = []
    equity = np.empty(n)
    rules = {'ara_skipped': 0, 'arb_delayed': 0, 'volume_capped': 0}

    for i in range(n):
        if pending is not None and not math.isnan(opens[i]):
            price = opens[i]
            if pending == 'buy':
                if idx_rules and _at_upper(price, prev_close):
                    rules['ara_skipped'] += 1
                else:
                    lots = int(cash // (price * LOT * (1 + fee_buy)))
                    if idx_rules and not math.isnan(volumes[i]):
                        cap = int(volumes[i] * MAX_VOLUME_SHARE // LOT)
                        if cap < lots:
                            lots = cap
                            rules['volume_capped'] += 1
                    if lots > 0:
                        shares = lots * LOT
                        entry_cost = shares * price * (1 + fee_buy)
                        cash -= entry_cost
                        entry_price, entry_i = price, i
                        peak = price
                        a = atrs[i - 1] if i else math.nan
                        stop_px = price - atr_stop * a if atr_stop is not None and not math.isnan(a) else None
                pending = None
            elif idx_rules and _at_lower(price, prev_close):
                rules['arb_delayed'] += 1          # stays pending: try again at the next open
            else:
                proceeds = shares * price * (1 - fee_sell)
                cash += proceeds
                trades.append(_trade(idx, entry_i, i, entry_price, price, shares,
                                     entry_cost, proceeds, pending[1]))
                shares = 0
                pending = None

        c = closes[i]
        equity[i] = cash + (shares * c if not math.isnan(c) else shares * entry_price)

        if math.isnan(c) or i == n - 1:
            continue
        prev_close = c
        if shares == 0:
            if buy[i] and pending is None:
                pending = 'buy'
        elif pending is None:
            peak = max(peak, c)
            reason = _exit_reason(c, entry_price, stop_px, peak, i - entry_i + 1,
                                  stop_loss, take_profit, trailing_stop, hold)
            if reason:
                pending = ('sell', REASONS[reason])
            elif sell[i]:
                pending = ('sell', 'signal')

    open_trade = None
    if shares > 0:
        last_close = closes[~np.isnan(closes)][-1]
        value = shares * last_close * (1 - fee_sell)
        open_trade = _trade(idx, entry_i, n - 1, entry_price, last_close, shares,
                            entry_cost, value, 'still open')

    equity = pd.Series(equity, index=idx)
    peak_eq = equity.cummax()
    drawdown = (equity / peak_eq - 1).min() * 100

    valid = closes[~np.isnan(closes)]
    closed = trades
    wins = [t for t in closed if t['pnl'] > 0]
    all_for_stats = closed + ([open_trade] if open_trade else [])
    final = cash + (open_trade['proceeds'] if open_trade else 0.0)
    in_market = sum(t['bars'] for t in all_for_stats)

    return {
        'start': idx[0], 'end': idx[-1], 'bars': n,
        'capital': float(capital),
        'final': final,
        'return_pct': (final / capital - 1) * 100,
        'buy_hold_pct': (valid[-1] / valid[0] - 1) * 100 if len(valid) > 1 else 0.0,
        'trades': closed,
        'open_trade': open_trade,
        'n_trades': len(closed),
        'wins': len(wins),
        'win_rate': len(wins) / len(closed) * 100 if closed else float('nan'),
        'avg_trade_pct': float(np.mean([t['return_pct'] for t in closed])) if closed else float('nan'),
        'best_pct': max((t['return_pct'] for t in all_for_stats), default=float('nan')),
        'worst_pct': min((t['return_pct'] for t in all_for_stats), default=float('nan')),
        'max_drawdown_pct': float(drawdown),
        'exposure_pct': in_market / n * 100 if n else 0.0,
        'equity': equity,
        'rules': rules,
    }


def _bool(x, idx):
    if isinstance(x, pd.Series):
        return x.reindex(idx).fillna(False).astype(bool).to_numpy()
    return np.full(len(idx), bool(x))


def _trade(idx, i0, i1, p0, p1, shares, cost, proceeds, reason):
    return {
        'entry_date': idx[i0], 'exit_date': idx[i1],
        'entry': p0, 'exit': p1, 'shares': shares,
        'cost': cost, 'proceeds': proceeds,
        'pnl': proceeds - cost,
        'return_pct': (proceeds / cost - 1) * 100,
        'bars': i1 - i0,
        'reason': reason,
    }


def portfolio(opens, closes, buy, sell, rank, capital=10_000_000, positions=10,
              fee_buy=0.0015, fee_sell=0.0025, stop_loss=None, take_profit=None,
              atr_stop=None, atr=None, trailing_stop=None, hold=None, volume=None, idx_rules=True):
    """
    The same rules as run(), but every stock shares ONE pot of money, the
    way a real account would trade them. Inputs are date-indexed DataFrames
    with a column per stock (NaN where a stock didn't trade that day).

    - At most `positions` stocks are held at once; each new position gets
      1/positions of the account's value at the previous close (or whatever
      cash is left, if less).
    - When more stocks signal than there are free slots, the ones with the
      highest `rank` on the signal day go first (the caller passes average
      daily traded value, so the most liquid win). The rest are skipped,
      not queued.
    - Exits are filled before entries on the same open, so a slot freed in
      the morning can be reused that day.

    Because the pot compounds, the return here is what an account statement
    would show, unlike an average of per-trade returns.
    """
    idx, syms = closes.index, list(closes.columns)
    C = closes.to_numpy(dtype=float)
    O = opens.to_numpy(dtype=float)
    O = np.where(np.isnan(O), C, O)
    B = buy.reindex(index=idx, columns=syms).to_numpy() == True    # NaN (no bar) -> False
    S = sell.reindex(index=idx, columns=syms).to_numpy() == True
    R = rank.reindex(index=idx, columns=syms).to_numpy(dtype=float)
    V = volume.reindex(index=idx, columns=syms).to_numpy(dtype=float) if volume is not None else np.full(C.shape, np.nan)
    A = atr.reindex(index=idx, columns=syms).to_numpy(dtype=float) if atr is not None else np.full(C.shape, np.nan)
    n, m = C.shape

    cash = float(capital)
    shares = np.zeros(m)
    entry_price = np.zeros(m)
    entry_cost = np.zeros(m)
    entry_i = np.zeros(m, dtype=int)
    stop_px = np.full(m, np.nan)
    peak = np.zeros(m)
    mark = np.full(m, np.nan)             # last known close, for valuing holdings
    last_atr = np.full(m, np.nan)         # ATR as of each stock's last bar
    pend_buy = np.zeros(m, dtype=bool)
    pend_rank = np.full(m, -np.inf)
    pend_sell = np.zeros(m, dtype=int)    # 0 none, else index into REASONS
    trades, skipped = [], 0
    rules = {'ara_skipped': 0, 'arb_delayed': 0, 'volume_capped': 0}
    equity = np.empty(n)
    invested = np.empty(n)

    for i in range(n):
        o = O[i]
        for j in np.nonzero((pend_sell > 0) & ~np.isnan(o))[0]:
            if idx_rules and _at_lower(o[j], mark[j]):
                rules['arb_delayed'] += 1         # stays pending: try again at the next open
                continue
            proceeds = shares[j] * o[j] * (1 - fee_sell)
            cash += proceeds
            t = _trade(idx, entry_i[j], i, entry_price[j], o[j], int(shares[j]),
                       entry_cost[j], proceeds, REASONS[pend_sell[j]])
            t['symbol'] = syms[j]
            trades.append(t)
            shares[j] = 0
            pend_sell[j] = 0

        cand = np.nonzero(pend_buy & ~np.isnan(o))[0]
        if cand.size:
            base = equity[i - 1] if i else float(capital)
            held = int((shares > 0).sum())
            for j in cand[np.argsort(-pend_rank[cand], kind='stable')]:
                price = o[j]
                if idx_rules and _at_upper(price, mark[j]):
                    rules['ara_skipped'] += 1
                    continue
                lots = int(min(cash, base / positions) // (price * LOT * (1 + fee_buy))) if held < positions else 0
                if idx_rules and lots > 0 and not np.isnan(V[i, j]):
                    cap = int(V[i, j] * MAX_VOLUME_SHARE // LOT)
                    if cap < lots:
                        lots = cap
                        rules['volume_capped'] += 1
                if lots <= 0:
                    skipped += 1
                    continue
                shares[j] = lots * LOT
                entry_cost[j] = shares[j] * price * (1 + fee_buy)
                cash -= entry_cost[j]
                entry_price[j], entry_i[j] = price, i
                peak[j] = price
                stop_px[j] = price - atr_stop * last_atr[j] if atr_stop is not None else np.nan
                held += 1
            pend_buy[cand] = False

        c = C[i]
        ok = ~np.isnan(c)
        mark[ok] = c[ok]
        a = A[i]
        last_atr[ok & ~np.isnan(a)] = a[ok & ~np.isnan(a)]
        holding = shares > 0
        value = float((shares[holding] * np.where(np.isnan(mark[holding]), entry_price[holding],
                                                  mark[holding])).sum())
        equity[i] = cash + value
        invested[i] = value / equity[i] if equity[i] > 0 else 0.0
        if i == n - 1:
            continue

        h = holding & ok & (pend_sell == 0)
        peak[h] = np.maximum(peak[h], c[h])
        for j in np.nonzero(h)[0]:
            reason = _exit_reason(c[j], entry_price[j], None if np.isnan(stop_px[j]) else stop_px[j], peak[j],
                                  i - entry_i[j] + 1, stop_loss, take_profit, trailing_stop, hold)
            if reason:
                pend_sell[j] = reason
            elif S[i, j]:
                pend_sell[j] = 1

        new = ~holding & ok & B[i] & ~pend_buy
        pend_buy[new] = True
        pend_rank[new] = np.nan_to_num(R[i][new], nan=-np.inf)

    open_trades = []
    for j in np.nonzero(shares > 0)[0]:
        px = mark[j] if not np.isnan(mark[j]) else entry_price[j]
        t = _trade(idx, entry_i[j], n - 1, entry_price[j], px, int(shares[j]), entry_cost[j],
                   shares[j] * px * (1 - fee_sell), 'still open')
        t['symbol'] = syms[j]
        open_trades.append(t)

    equity = pd.Series(equity, index=idx)
    final = cash + sum(t['proceeds'] for t in open_trades)
    wins = [t for t in trades if t['pnl'] > 0]
    first = closes.apply(lambda s: s.dropna().iloc[0] if s.notna().sum() > 1 else np.nan)
    lastc = closes.apply(lambda s: s.dropna().iloc[-1] if s.notna().sum() > 1 else np.nan)
    bh = ((lastc / first - 1) * 100).dropna()
    return {
        'start': idx[0], 'end': idx[-1], 'bars': n,
        'capital': float(capital), 'positions': positions,
        'final': final,
        'return_pct': (final / capital - 1) * 100,
        'buy_hold_pct': float(bh.mean()) if len(bh) else float('nan'),
        'n_stocks': len(syms),
        'trades': trades, 'open_trades': open_trades,
        'n_trades': len(trades), 'wins': len(wins),
        'win_rate': len(wins) / len(trades) * 100 if trades else float('nan'),
        'avg_trade_pct': float(np.mean([t['return_pct'] for t in trades])) if trades else float('nan'),
        'max_drawdown_pct': float((equity / equity.cummax() - 1).min() * 100),
        'invested_pct': float(invested.mean() * 100) if n else 0.0,
        'skipped': skipped,
        'rules': rules,
        'equity': equity,
    }
