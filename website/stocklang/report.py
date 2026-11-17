"""Text formatting for everything StockLang prints."""
import math

import numpy as np
import pandas as pd


def num(v):
    if isinstance(v, bool):
        return 'true' if v else 'false'
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return 'n/a'
    if isinstance(v, float) and v.is_integer() and abs(v) < 1e15:
        return f"{int(v):,}"
    if abs(v) >= 1000:
        return f"{v:,.0f}"
    return f"{v:,.2f}"


def pct(v, sign=True):
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return 'n/a'
    return f"{v:+.1f}%" if sign else f"{v:.1f}%"


def rp(v):
    return f"Rp {v:,.0f}"


def date(d):
    return pd.Timestamp(d).strftime('%Y-%m-%d')


def value(v):
    """How a value shows up in print() and REPL echo."""
    if isinstance(v, pd.Series):
        tail = v.dropna().tail(5)
        if tail.empty:
            return '(no data yet: not enough bars)'
        return '\n'.join(f"  {date(d)}  {num(_plain(x))}" for d, x in tail.items())
    if isinstance(v, str):
        return v
    return num(v)


def _plain(x):
    return bool(x) if isinstance(x, (bool, np.bool_)) else float(x)


def table(headers, rows, align=None):
    cells = [[str(h) for h in headers]] + [[str(c) for c in r] for r in rows]
    widths = [max(len(r[i]) for r in cells) for i in range(len(headers))]
    align = align or ['<'] + ['>'] * (len(headers) - 1)
    lines = []
    for k, r in enumerate(cells):
        lines.append('  ' + '  '.join(f"{c:{a}{w}}" for c, a, w in zip(r, align, widths)))
        if k == 0:
            lines.append('  ' + '  '.join('-' * w for w in widths))
    return '\n'.join(lines)


def rules_note(*results):
    """One line on what the IDX trading rules changed, or None if nothing."""
    tot = {k: sum(r['rules'][k] for r in results if r) for k in ('ara_skipped', 'arb_delayed', 'volume_capped')}
    s = lambda n, word: f"{n:,} {word}{'s' if n != 1 else ''}"
    parts = []
    if tot['ara_skipped']:
        parts.append(f"{s(tot['ara_skipped'], 'buy')} skipped (opened at the upper limit, ARA)")
    if tot['arb_delayed']:
        parts.append(f"{s(tot['arb_delayed'], 'sell')} delayed a day (opened at the lower limit, ARB)")
    if tot['volume_capped']:
        parts.append(f"{s(tot['volume_capped'], 'buy')} cut to 10% of the day's volume")
    return ("  IDX rules: " + '; '.join(parts) + '.') if parts else None


def backtest(symbol, r, show_trades=True):
    out = [
        f"Backtest {symbol} | {date(r['start'])} to {date(r['end'])} ({r['bars']} bars)",
        f"  Starting capital  {rp(r['capital'])}",
        f"  Final value       {rp(r['final'])}   ({pct(r['return_pct'])})",
        f"  Buy & hold        {pct(r['buy_hold_pct'])}",
        f"  Trades            {r['n_trades']}   (won {r['wins']}, lost {r['n_trades'] - r['wins']}, win rate {pct(r['win_rate'], sign=False)})",
        f"  Avg trade         {pct(r['avg_trade_pct'])}   best {pct(r['best_pct'])}, worst {pct(r['worst_pct'])}",
        f"  Max drawdown      {pct(r['max_drawdown_pct'])}",
        f"  Time in market    {pct(r['exposure_pct'], sign=False)}",
    ]
    if rules_note(r):
        out.append(rules_note(r))
    trades = r['trades'] + ([r['open_trade']] if r['open_trade'] else [])
    if show_trades and trades:
        rows = [[date(t['entry_date']), num(t['entry']), date(t['exit_date']), num(t['exit']),
                 f"{t['shares'] // 100:,}", pct(t['return_pct']), t['reason']] for t in trades]
        out.append('')
        out.append(table(['Bought', 'Price', 'Sold', 'Price', 'Lots', 'Return', 'Why'], rows,
                         ['<', '>', '<', '>', '>', '>', '<']))
    return '\n'.join(out)


def _period(r):
    return f"{date(r['start'])} to {date(r['end'])}"


def _trades_table(trades, with_symbol=False, with_period=False):
    head = (['Stock'] if with_symbol else []) + ['Bought', 'Price', 'Sold', 'Price', 'Lots', 'Return', 'Why'] \
        + (['Period'] if with_period else [])
    align = (['<'] if with_symbol else []) + ['<', '>', '<', '>', '>', '>', '<'] + (['<'] if with_period else [])
    rows = []
    for t in trades:
        row = [date(t['entry_date']), num(t['entry']), date(t['exit_date']), num(t['exit']),
               f"{t['shares'] // 100:,}", pct(t['return_pct']), t['reason']]
        rows.append(([t['symbol']] if with_symbol else []) + row + ([t['period']] if with_period else []))
    return table(head, rows, align)


def _verdict(r_out):
    gap = r_out['return_pct'] - r_out['buy_hold_pct']
    line = (f"  Out-of-sample {'beat' if gap >= 0 else 'trailed'} buy & hold by {abs(gap):.1f} points"
            if not math.isnan(gap) else "  Out-of-sample: no buy & hold to compare")
    if r_out['n_trades'] < 10:
        line += f"; only {r_out['n_trades']} closed trades there, too few to call it"
    return line + '.'


def backtest_split(symbol, r_in, r_out, split, show_trades=True):
    rows = [
        ['Period', _period(r_in), _period(r_out)],
        ['Bars', r_in['bars'], r_out['bars']],
        ['Return', pct(r_in['return_pct']), pct(r_out['return_pct'])],
        ['Buy & hold', pct(r_in['buy_hold_pct']), pct(r_out['buy_hold_pct'])],
        ['Trades', r_in['n_trades'], r_out['n_trades']],
        ['Win rate', pct(r_in['win_rate'], sign=False), pct(r_out['win_rate'], sign=False)],
        ['Avg trade', pct(r_in['avg_trade_pct']), pct(r_out['avg_trade_pct'])],
        ['Max drawdown', pct(r_in['max_drawdown_pct']), pct(r_out['max_drawdown_pct'])],
        ['Time in market', pct(r_in['exposure_pct'], sign=False), pct(r_out['exposure_pct'], sign=False)],
    ]
    out = [f"Backtest {symbol} | split at {date(split)}, each side starts with {rp(r_in['capital'])}",
           table(['', 'In-sample', 'Out-of-sample'], rows), '', _verdict(r_out)]
    if rules_note(r_in, r_out):
        out.append(rules_note(r_in, r_out))
    trades = []
    for label, r in (('in', r_in), ('out', r_out)):
        for t in r['trades'] + ([r['open_trade']] if r['open_trade'] else []):
            trades.append(dict(t, period=label))
    if show_trades and trades:
        out += ['', _trades_table(trades, with_period=True)]
    return '\n'.join(out)


def study(r, label):
    rows = r['rows']
    n = max((x['n'] for x in rows), default=0)
    if not n:
        return f"Study {label}: the condition was never true on a day with a result to measure."
    out = [f"Study {label}: {n:,} signals on {r['stocks']:,} stock{'s' if r['stocks'] != 1 else ''}, "
           f"{date(r['first'])} to {date(r['last'])}",
           f"  Entry at the next open, exit at the close of day H; returns are after a "
           f"{r['fee'] * 100:.2f}% round-trip fee.",
           table(['After', 'Signals', 'Avg return', 'Median', 'Win rate', r['bench_label'], 'Edge'],
                 [[f"{x['days']} day{'s' if x['days'] != 1 else ''}", f"{x['n']:,}", pct(x['avg']),
                   pct(x['median']), pct(x['win'], sign=False), pct(x['bench']), pct(x['edge'])]
                  for x in rows]),
           f"  Edge = the signal's average minus the benchmark over the exact same days (both before fee)."]
    if n < 30:
        out.append(f"  Only {n} signals: too few to tell an edge from luck.")
    elif r['stocks'] and n / r['stocks'] > 5:
        out.append("  Many signals come from the same stocks on nearby days; they overlap, so the real "
                   "number of independent tries is smaller.")
    return '\n'.join(out)


def sweep(names, rows, split):
    """rows: [(values, r_in, r_out)] from a param sweep."""
    ranked = sorted(rows, key=lambda x: x[1]['return_pct'], reverse=True)
    setting = lambda vals: ', '.join(f"{n}={value(v)}" for n, v in zip(names, vals))
    out = [f"Sweep: {len(rows)} settings of {', '.join(names)}, split at {date(split)}. "
           f"Ranked on IN-sample; the out-of-sample columns are the honest test"
           + (", top 20" if len(rows) > 20 else '') + ':',
           table(names + ['In return', 'In trades', 'Out return', 'Out trades', 'Out B&H'],
                 [[value(v) for v in vals] + [pct(a['return_pct']), a['n_trades'], pct(z['return_pct']),
                                              z['n_trades'], pct(z['buy_hold_pct'])]
                  for vals, a, z in ranked[:20]]),
           '']
    best_vals, _, best_out = ranked[0]
    outs = sorted((z['return_pct'] for _, _, z in rows), reverse=True)
    place = outs.index(best_out['return_pct']) + 1
    out.append(f"  The best in-sample setting ({setting(best_vals)}) made {pct(best_out['return_pct'])} "
               f"out-of-sample: #{place} of {len(rows)} there.")
    out.append(f"  Median out-of-sample across all settings: {pct(float(np.median(outs)))}.")
    few = float(np.median([z['n_trades'] for _, _, z in rows]))
    if few < 10:
        out.append(f"  Only ~{few:.0f} closed trades per setting out-of-sample: differences this small in "
                   f"trade count are mostly luck, not a better setting.")
    if len(rows) >= 5:
        x = pd.Series([a['return_pct'] for _, a, _ in rows])
        y = pd.Series([z['return_pct'] for _, _, z in rows])
        rho = x.rank().corr(y.rank())
        if not math.isnan(rho):
            out.append(f"  Rank correlation in vs out: rho = {rho:+.2f}"
                       + (" (near zero: the in-sample ranking says little about the future)" if abs(rho) < 0.2
                          else ''))
    out.append("  Picking the top in-sample row is how backtests fool you; trust a setting only if "
               "its neighbours do well out-of-sample too.")
    return '\n'.join(out)


def _portfolio_rows(r):
    return [
        _period(r), f"{r['bars']}",
        pct(r['return_pct']), pct(r['buy_hold_pct']),
        f"{r['n_trades']}", pct(r['win_rate'], sign=False), pct(r['avg_trade_pct']),
        pct(sum(t['pnl'] for t in r['trades']) / r['capital'] * 100),
        f"{pct(sum(t['pnl'] for t in r['open_trades']) / r['capital'] * 100)} ({len(r['open_trades'])} open)",
        pct(r['max_drawdown_pct']), pct(r['invested_pct'], sign=False), f"{r['skipped']:,}",
    ]


_PORTFOLIO_LABELS = ['Period', 'Days', 'Return (compounded)', 'Buy & hold (equal wt)', 'Trades', 'Win rate',
                     'Avg trade (simple)', 'From closed trades', 'From still-open', 'Max drawdown',
                     'Capital in use', 'Skipped signals']


def portfolio(r, show_trades=True, split_r=None, split=None):
    """One shared pot across the universe; with split_r, in- vs out-of-sample side by side."""
    head = (f"Portfolio: one pot of {rp(r['capital'])}, at most {r['positions']} positions, "
            f"{r['n_stocks']} stocks")
    out = [head + (f", split at {date(split)} (each side starts fresh)" if split_r else '') + ':']
    if split_r:
        rows = [[lab, a, b] for lab, a, b in zip(_PORTFOLIO_LABELS, _portfolio_rows(r), _portfolio_rows(split_r))]
        out.append(table(['', 'In-sample', 'Out-of-sample'], rows))
        out += ['', _verdict(split_r)]
        show = [dict(t, period='in') for t in r['trades'] + r['open_trades']] + \
               [dict(t, period='out') for t in split_r['trades'] + split_r['open_trades']]
    else:
        out.append(table(['', 'Result'], [[lab, v] for lab, v in zip(_PORTFOLIO_LABELS, _portfolio_rows(r))]))
        show = r['trades'] + r['open_trades']
    out.append("  Return is the account's compounded growth; avg trade is a plain average of closed trades, "
               "and the two can disagree a lot.")
    for label, x in (('', r), ('out-of-sample ', split_r)):
        if x and x['open_trades']:
            closed = sum(t['pnl'] for t in x['trades'])
            still = sum(t['pnl'] for t in x['open_trades'])
            if abs(still) > abs(closed):
                out.append(f"  Careful: most of the {label}result is positions still open at the end "
                           f"(valued at the last close, minus the sell fee), not closed trades.")
    if r['skipped'] or (split_r and split_r['skipped']):
        out.append("  Skipped = signals with no free slot or cash left; the most liquid stocks get slots first.")
    if rules_note(r, split_r):
        out.append(rules_note(r, split_r))
    if show_trades and show:
        recent = sorted(show, key=lambda t: t['entry_date'])[-15:]
        out += ['', f"Last {len(recent)} of {len(show)} trades:",
                _trades_table(recent, with_symbol=True, with_period=bool(split_r))]
    return '\n'.join(out)
