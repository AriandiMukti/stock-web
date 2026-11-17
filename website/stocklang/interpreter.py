"""
Tree-walking interpreter for StockLang.

Values are plain Python numbers/bools/strings, or pandas objects holding
one value per bar: a Series for a single stock, a DataFrame (one column
per stock) for a universe. Operators and built-ins work on those whole
objects, so the tree walk happens once per script line -- not once per
bar and not once per stock. The heavy lifting is NumPy's.
"""
import difflib
import inspect
import itertools
import math
import os

import numpy as np
import pandas as pd

from . import backtest as bt
from . import data, report, study
from . import indicators as ind
from .errors import StockLangError
from .indicators import BUILTINS, is_series, last
from .parser import (Assign, BinOp, Bool, Call, ExprStmt, FnDef, If, Lag, ListLit, Name, Num,
                     ParamStmt, Return, StockStmt, Str, UnaryOp, UniverseStmt, parse)

MAX_SWEEP = 100           # settings per param sweep
SWEEP_SPLIT = 0.7         # a sweep always judges out-of-sample; this is the split when the script gives none

COMMANDS = {
    'print': 'print(a, b, ...) show values (a series shows its latest value)',
    'backtest': 'backtest(buy, sell, capital=10M, fee_buy=0.15%, fee_sell=0.25%, stop_loss=, take_profit=, '
                'atr_stop=2 (x ATR), trailing_stop=10%, hold=10 (bars), idx_rules=true (ARA/ARB/volume), '
                'trades=true, split="2026-07-01" or 70%, positions=10 (universe: one shared pot))',
    'study': 'study(condition, days=[1, 5, 20], fee=0.4%) what happened after the condition was true, '
             'compared with the same days in general',
    'screen': 'screen(condition, sort="name", desc=true, limit=20, name=value, ...) stocks matching on the latest day',
    'rank': 'rank(x) 0-100: where each stock stands against all others that day (100 = highest; universe only)',
    'top': 'top(x, n) true for the n stocks with the highest x that day (universe only)',
    'plot': 'plot(series, ..., buy=, sell=, title="", file="") save a chart as PNG',
    'help': 'help() list everything available',
}

# Built-ins whose first argument may be a plain number.
_SCALAR_OK = {'where', 'abs', 'max', 'min', 'round', 'last'}


class _Return(Exception):
    def __init__(self, value):
        self.value = value


class UserFn:
    def __init__(self, node):
        self.name = node.name
        self.params = node.params
        self.body = node.body


class Interpreter:
    def __init__(self, out=print, script_path=None, universe=None, params=None, quiet=False):
        self.quiet = quiet                  # parameter sweeps: compute results, print nothing
        self.out = (lambda *a: None) if quiet else out
        self.params = params or {}          # this sweep run's value for each `param`
        self.script_path = script_path
        self.vars = {}
        self.fns = {}
        self.symbol = None
        self.df = None
        self.universe = universe            # data.Universe when running a whole market
        self.results = UniverseResults() if universe is not None else None
        self.single_screens = []            # (symbol, matched, date, values) per screen() on one stock
        self.last_study = None
        self.last_backtest = None

    # ---- running ------------------------------------------------------------

    def run(self, stmts):
        result = None
        for s in stmts:
            result = self.exec(s, None)
        return result

    def exec(self, s, local):
        if isinstance(s, Assign):
            v = self.eval(s.value, local)
            (local if local is not None else self.vars)[s.name] = v
            return None
        if isinstance(s, ExprStmt):
            return self.eval(s.expr, local)
        if isinstance(s, StockStmt):
            if self.universe is not None:
                raise StockLangError("'stock' can't be used together with 'universe'", s.line, s.col)
            self.set_stock(s.symbol, s)
            return None
        if isinstance(s, UniverseStmt):
            if self.universe is None:
                raise StockLangError("'universe' only works when running a whole script file", s.line, s.col)
            return None
        if isinstance(s, ParamStmt):
            if local is not None:
                raise StockLangError("'param' only works at the top of a script, not inside a function",
                                     s.line, s.col)
            if s.name in self.params:
                v = self.params[s.name]
            else:                           # not sweeping (e.g. the prompt): use the first value
                v = _param_values(self.eval(s.value, None), s)[0]
            self.vars[s.name] = v
            return None
        if isinstance(s, FnDef):
            if s.name in BUILTINS or s.name in COMMANDS or s.name in data.COLUMNS or s.name == 'ihsg':
                raise StockLangError(f"'{s.name}' is a built-in name, pick another function name", s.line, s.col)
            self.fns[s.name] = UserFn(s)
            return None
        if isinstance(s, If):
            cond = self.eval(s.cond, local)
            if is_series(cond):
                hint = ("Use last(...) to check the latest bar, or where(cond, a, b) per bar"
                        if self.universe is None else
                        "In a universe every stock has its own answer: use where(cond, a, b) or screen()")
                raise StockLangError(f"'if' needs one true/false value, but this has many. {hint}",
                                     s.cond.line, s.cond.col)
            for inner in (s.then if cond else s.otherwise):
                self.exec(inner, local)
            return None
        if isinstance(s, Return):
            if local is None:
                raise StockLangError("'return' outside a function", s.line, s.col)
            raise _Return(self.eval(s.value, local))
        raise StockLangError(f"unknown statement {type(s).__name__}", s.line, s.col)

    def set_stock(self, symbol, node=None):
        df = data.load(symbol)
        if df is None:
            hint = difflib.get_close_matches(symbol, data.all_symbols(), n=1)
            raise StockLangError(f"no data for stock '{symbol}'" + (f" (did you mean {hint[0]}?)" if hint else ''),
                                 node.line if node else None, node.col if node else None)
        self.symbol = symbol
        self.df = df

    # ---- expressions --------------------------------------------------------

    def eval(self, node, local):
        if isinstance(node, (Num, Str, Bool)):
            return node.value
        if isinstance(node, Name):
            return self.lookup(node, local)
        if isinstance(node, UnaryOp):
            v = self.eval(node.operand, local)
            if node.op == '-':
                if isinstance(v, str):
                    raise StockLangError("can't negate text", node.line, node.col)
                return -_num(v)
            # `not unknown` stays unknown: during an indicator's warm-up
            # `not (close > sma(close, 50))` must not turn into true.
            return ~_cond(v) if is_series(v) else not v
        if isinstance(node, BinOp):
            return self.binop(node, local)
        if isinstance(node, Lag):
            target = self.eval(node.target, local)
            bars = self.eval(node.bars, local)
            if is_series(bars) or isinstance(bars, str) or bars < 0 or bars != int(bars):
                raise StockLangError("x[n] needs n to be a whole number of bars ago, like close[1]", node.line, node.col)
            return target.shift(int(bars)) if is_series(target) else target
        if isinstance(node, Call):
            return self.call(node, local)
        if isinstance(node, ListLit):
            return [self.eval(i, local) for i in node.items]
        raise StockLangError(f"can't evaluate {type(node).__name__}", node.line, node.col)

    def lookup(self, node, local):
        name = node.name
        if local is not None and name in local:
            return local[name]
        if name in self.vars:
            return self.vars[name]
        if name in data.COLUMNS or name == 'ihsg':
            if self.universe is None and self.df is None:
                raise StockLangError(f"'{name}' needs a stock first, add a line like: stock BBCA", node.line, node.col)
            if name == 'ihsg':
                return self.ihsg()
            if self.universe is not None:
                return self.universe.frames[name]
            return self.df[name]
        if name in BUILTINS or name in COMMANDS or name in self.fns:
            raise StockLangError(f"'{name}' is a function, call it like {name}(...)", node.line, node.col)
        known = list(self.vars) + list(local or {}) + list(data.COLUMNS)
        hint = difflib.get_close_matches(name, known, n=1)
        raise StockLangError(f"unknown name '{name}'" + (f", did you mean '{hint[0]}'?" if hint else ''),
                             node.line, node.col)

    def binop(self, node, local):
        a = self.eval(node.left, local)
        b = self.eval(node.right, local)
        op = node.op
        if isinstance(a, list) or isinstance(b, list):
            raise StockLangError(_LIST_ONLY, node.line, node.col)
        try:
            if op in ('and', 'or'):
                if is_series(a) or is_series(b):
                    # Three-valued: unknown and false = false, unknown or true = true.
                    a, b = _cond(a), _cond(b)
                    return (a & b) if op == 'and' else (a | b)
                return (a and b) if op == 'and' else (a or b)
            if op == '+' and (isinstance(a, str) or isinstance(b, str)):
                return _text(a) + _text(b)
            if isinstance(a, str) or isinstance(b, str):
                if op in ('==', '!='):
                    return (a == b) if op == '==' else (a != b)
                raise StockLangError(f"can't use '{op}' with text", node.line, node.col)
            a, b = _num(a), _num(b)
            if op == '+': return a + b
            if op == '-': return a - b
            if op == '*': return a * b
            if op == '/':
                if not is_series(b) and b == 0:
                    raise StockLangError("division by zero", node.line, node.col)
                r = a / b
                return r.replace([np.inf, -np.inf], np.nan) if is_series(r) else r
            if op == '<': r = a < b
            elif op == '>': r = a > b
            elif op == '<=': r = a <= b
            elif op == '>=': r = a >= b
            elif op == '==': r = a == b
            elif op == '!=': r = a != b
            else:
                r = None
            if r is not None:
                return _known(r, a, b) if is_series(r) else r
        except StockLangError:
            raise
        except Exception as e:
            raise StockLangError(f"'{op}' failed: {e}", node.line, node.col)
        raise StockLangError(f"unknown operator '{op}'", node.line, node.col)

    def call(self, node, local):
        name = node.func
        if name in self.fns:
            return self.call_user(self.fns[name], node, local)
        if name in ('rank', 'top'):
            return self.call_compare(node, local)
        if name in COMMANDS:
            args = [self.eval(a, local) for a in node.args]
            kwargs = {k: self.eval(v, local) for k, v in node.kwargs.items()}
            return getattr(self, 'cmd_' + name)(node, args, kwargs)
        if name in BUILTINS:
            fn, usage = BUILTINS[name]
            args = [self.eval(a, local) for a in node.args]
            kwargs = {k: self.eval(v, local) for k, v in node.kwargs.items()}
            if any(isinstance(v, list) for v in args + list(kwargs.values())):
                raise StockLangError(_LIST_ONLY, node.line, node.col)
            if name == 'where':
                args = args[:1] + [_num(a) for a in args[1:]]
            elif name != 'last':
                args = [_num(a) for a in args]
            if name == 'atr':
                args = [self.column(node, c) for c in ('high', 'low', 'close')] + args
            try:
                inspect.signature(fn).bind(*args, **kwargs)
            except TypeError:
                raise StockLangError(f"wrong arguments, usage: {usage}", node.line, node.col)
            if name not in _SCALAR_OK and args and not is_series(args[0]):
                raise StockLangError(f"{name}() needs a series first (like close), usage: {usage}", node.line, node.col)
            try:
                return fn(*args, **kwargs)
            except Exception as e:
                raise StockLangError(f"{name}(): {e}", node.line, node.col)
        hint = difflib.get_close_matches(name, list(BUILTINS) + list(COMMANDS) + list(self.fns), n=1)
        raise StockLangError(f"unknown function '{name}'" + (f", did you mean '{hint[0]}'?" if hint else ''),
                             node.line, node.col)

    def call_user(self, fn, node, local):
        if node.kwargs:
            raise StockLangError(f"{fn.name}() takes positional arguments only", node.line, node.col)
        if len(node.args) != len(fn.params):
            raise StockLangError(f"{fn.name}() takes {len(fn.params)} argument(s), got {len(node.args)}",
                                 node.line, node.col)
        frame = {p: self.eval(a, local) for p, a in zip(fn.params, node.args)}
        try:
            for s in fn.body:
                self.exec(s, frame)
        except _Return as r:
            return r.value
        except RecursionError:
            raise StockLangError(f"{fn.name}() calls itself too deeply", node.line, node.col)
        return None

    def column(self, node, name):
        return self.lookup(Name(name, line=node.line, col=node.col), None)

    def ihsg(self):
        """IHSG close lined up with the data: one value per bar (per stock, in a universe)."""
        close = data.ihsg()
        if self.universe is not None:
            dates, latest = self.universe.calendar, self.universe.last_date.max()
        else:
            dates, latest = self.df.index, self.df.index[-1]
        # A day IHSG doesn't have yet (Yahoo lags the Summary files) gets its last value, for a few bars at most.
        aligned = close.reindex(close.index.union(dates)).ffill(limit=5).reindex(dates)
        if close.index.max() < latest and not getattr(self, '_ihsg_noted', False):
            self._ihsg_noted = True
            self.out(f"(IHSG from Yahoo Finance ends {report.date(close.index.max())}; "
                     f"later days use that last value)")
        if self.universe is None:
            return aligned
        u = self.universe
        return u.to_bars(pd.DataFrame({s: aligned for s in u.symbols}))

    def call_compare(self, node, local):
        """rank() / top(): each stock against all the others on the same day."""
        name = node.func
        args = [self.eval(a, local) for a in node.args]
        if node.kwargs or len(args) != (1 if name == 'rank' else 2):
            raise StockLangError(f"usage: {COMMANDS[name]}", node.line, node.col)
        if self.universe is None:
            raise StockLangError(f"{name}() compares stocks with each other, so it needs a universe "
                                 f"(e.g. universe all)", node.line, node.col)
        x = _num(args[0])
        if not isinstance(x, pd.DataFrame):
            raise StockLangError(f"{name}() needs a series first (like close), usage: {COMMANDS[name]}",
                                 node.line, node.col)
        u = self.universe
        by = u.by_date(x)
        if name == 'rank':
            return u.to_bars(by.rank(axis=1, pct=True) * 100)
        n = args[1]
        if isinstance(n, (bool, str, list)) or is_series(n) or n < 1 or n != int(n):
            raise StockLangError("top(x, n) needs n to be a whole number of 1 or more", node.line, node.col)
        hit = (by.rank(axis=1, ascending=False, method='first') <= n).astype(float).where(by.notna())
        bars = u.to_bars(hit)
        return (bars == 1).astype('boolean').mask(bars.isna())

    # ---- commands -----------------------------------------------------------

    def cmd_help(self, node, args, kwargs):
        lines = ['Data columns (need `stock CODE` or `universe ...` first):',
                 '  ' + ', '.join(data.COLUMNS) + ', ihsg (IHSG close, from Yahoo Finance)',
                 '', 'Functions:']
        lines += [f"  {u}" for _, u in BUILTINS.values()]
        lines += ['', 'Commands:'] + [f"  {u}" for u in COMMANDS.values()]
        if self.fns:
            lines += ['', 'Your functions:'] + [f"  {f.name}({', '.join(f.params)})" for f in self.fns.values()]
        self.out('\n'.join(lines))

    def cmd_print(self, node, args, kwargs):
        parts = []
        for v in args:
            if isinstance(v, pd.DataFrame):
                latest = last(v)
                if pd.api.types.is_bool_dtype(latest):
                    parts.append(f"(true for {int(latest.sum())} of {len(latest)} stocks)")
                else:
                    parts.append(f"(median {report.num(float(latest.median()))} across {int(latest.notna().sum())} stocks)")
                continue
            if isinstance(v, pd.Series):
                v = last(v)
            if isinstance(v, list):
                v = '[' + ', '.join(report.value(x) for x in v) + ']'
            parts.append(report.value(v))
        self.out(' '.join(parts))

    def cmd_study(self, node, args, kwargs):
        self._need_stock(node, 'study')
        if len(args) != 1:
            raise StockLangError(f"usage: {COMMANDS['study']}", node.line, node.col)
        _check_kwargs(node, kwargs, {'days', 'fee'}, 'study')
        days = kwargs.get('days', [1, 5, 20])
        days = days if isinstance(days, list) else [days]
        if not days or any(isinstance(d, (bool, str)) or not isinstance(d, (int, float)) or d < 1 or d != int(d)
                           for d in days):
            raise StockLangError("days= needs whole numbers of 1 or more, like days=[1, 5, 20]", node.line, node.col)
        days = sorted({int(d) for d in days})
        fee = kwargs.get('fee', 0.0015 + 0.0025)
        if isinstance(fee, (bool, str, list)) or not 0 <= fee < 1:
            raise StockLangError("fee= needs a percentage like 0.4%", node.line, node.col)
        cond = args[0]
        label = _label(node.args[0])
        if self.universe is None:
            sig = _as_bool(cond) if is_series(cond) else pd.Series(bool(cond), index=self.df.index)
            r = study.single(self.df, sig, days, fee)
        else:
            u = self.universe
            sig = _as_bool(cond) if is_series(cond) else \
                pd.DataFrame(bool(cond), index=u.frames['close'].index, columns=u.symbols)
            r = study.universe(u, sig, days, fee)
        self.last_study = r
        self.out(report.study(r, label if len(label) <= 60 else label[:57] + '...'))
        self.out('')

    def cmd_backtest(self, node, args, kwargs):
        self._need_stock(node, 'backtest')
        if len(args) != 2:
            raise StockLangError(f"usage: {COMMANDS['backtest']}", node.line, node.col)
        _check_kwargs(node, kwargs, {'capital', 'fee', 'fee_buy', 'fee_sell', 'stop_loss', 'take_profit', 'trades',
                                     'split', 'positions', 'atr_stop', 'trailing_stop', 'hold', 'idx_rules'},
                      'backtest')
        fee = kwargs.get('fee')
        opts = dict(capital=kwargs.get('capital', 10_000_000),
                    fee_buy=kwargs.get('fee_buy', fee if fee is not None else 0.0015),
                    fee_sell=kwargs.get('fee_sell', fee if fee is not None else 0.0025),
                    stop_loss=kwargs.get('stop_loss'),
                    take_profit=kwargs.get('take_profit'),
                    atr_stop=kwargs.get('atr_stop'),
                    trailing_stop=kwargs.get('trailing_stop'),
                    hold=kwargs.get('hold'),
                    idx_rules=kwargs.get('idx_rules', True))
        checks = (('atr_stop', lambda v: v > 0, "a number of ATRs above 0, like atr_stop=2"),
                  ('trailing_stop', lambda v: 0 < v < 1, "a percentage like trailing_stop=10%"),
                  ('hold', lambda v: v >= 1 and v == int(v), "a whole number of bars, like hold=10"))
        for key, ok, what in checks:
            v = opts[key]
            if v is not None and (isinstance(v, (bool, str, list)) or not ok(v)):
                raise StockLangError(f"{key}= needs {what}", node.line, node.col)
        if not isinstance(opts['idx_rules'], bool):
            raise StockLangError("idx_rules= needs true or false", node.line, node.col)
        if opts['hold'] is not None:
            opts['hold'] = int(opts['hold'])
        buy, sell = args
        show = bool(kwargs.get('trades', True))
        want_split = 'split' in kwargs or self.quiet
        if self.universe is None:
            if 'positions' in kwargs:
                raise StockLangError("positions= only works with 'universe' (one pot of money shared by many stocks)",
                                     node.line, node.col)
            df = self.df
            atr = ind.atr(df['high'], df['low'], df['close']) if opts['atr_stop'] is not None else None
            if want_split:
                d = self._split_date(node, kwargs.get('split', SWEEP_SPLIT), df.index)
                r_in = bt.run(df[df.index < d], buy, sell, atr=atr, **opts)
                r_out = bt.run(df[df.index >= d], buy, sell, atr=atr, **opts)
                self.last_backtest = (r_in, r_out, d)
                self.out(report.backtest_split(self.symbol, r_in, r_out, d, show_trades=show))
            else:
                r = bt.run(df, buy, sell, atr=atr, **opts)
                self.last_backtest = (r, None, None)
                self.out(report.backtest(self.symbol, r, show_trades=show))
            self.out('')
            return

        u = self.universe
        positions = kwargs.get('positions', 10)
        if isinstance(positions, bool) or not isinstance(positions, (int, float)) or positions < 1 \
                or positions != int(positions):
            raise StockLangError("positions= needs a whole number of 1 or more", node.line, node.col)
        split = self._split_date(node, kwargs.get('split', SWEEP_SPLIT), u.calendar) if want_split else None
        r = self.results
        r.split = split
        buy_b = _as_bool(buy) if isinstance(buy, pd.DataFrame) else buy
        sell_b = _as_bool(sell) if isinstance(sell, pd.DataFrame) else sell
        atr = ind.atr(u.frames['high'], u.frames['low'], u.frames['close']) if opts['atr_stop'] is not None else None
        for sym in ([] if self.quiet else u.symbols):     # a sweep only compares the shared-pot portfolio
            df = u.stock_frame(sym)
            b = u.stock_series(buy_b, sym) if isinstance(buy_b, pd.DataFrame) else buy_b
            s = u.stock_series(sell_b, sym) if isinstance(sell_b, pd.DataFrame) else sell_b
            a_sym = u.stock_series(atr, sym) if atr is not None else None
            if split is None:
                r.backtests.append((sym, bt.run(df, b, s, atr=a_sym, **opts)))
                continue
            a, z = df[df.index < split], df[df.index >= split]
            r.split_backtests.append((sym, bt.run(a, b, s, atr=a_sym, **opts) if len(a) >= 2 else None,
                                      bt.run(z, b, s, atr=a_sym, **opts) if len(z) >= 2 else None))

        # One shared pot across every stock: what an account would really have done.
        opens, closes = u.by_date(u.frames['open']), u.by_date(u.frames['close'])

        def wide(v):
            if isinstance(v, pd.DataFrame):
                return u.by_date(_as_bool(v))
            return pd.DataFrame(bool(v), index=closes.index, columns=closes.columns)

        bw, sw = wide(buy), wide(sell)
        traded_value = (u.frames['close'] * u.frames['volume']).rolling(20, min_periods=1).mean()
        rank = u.by_date(traded_value)
        vol = u.by_date(u.frames['volume'])
        atr_d = u.by_date(atr) if atr is not None else None
        popts = dict(opts, positions=int(positions))
        if split is None:
            r.portfolio = (bt.portfolio(opens, closes, bw, sw, rank, volume=vol, atr=atr_d, **popts), None)
        else:
            parts = []
            for rows in (closes.index < split, closes.index >= split):
                parts.append(bt.portfolio(opens[rows], closes[rows], bw[rows], sw[rows], rank[rows],
                                          volume=vol[rows], atr=atr_d[rows] if atr_d is not None else None,
                                          **popts))
            r.portfolio = tuple(parts)
        r.show_trades = show
        self.last_backtest = (r.portfolio[0], r.portfolio[1], split)

    def _split_date(self, node, v, dates):
        """split="2026-07-01" or split=70% (share of the bars) -> the first out-of-sample date."""
        if isinstance(v, str):
            try:
                d = pd.Timestamp(v)
            except (ValueError, TypeError):
                d = None
            if d is None or pd.isna(d):
                raise StockLangError(f'split needs a date like "2026-07-01" or a share like 70%, not "{v}"',
                                     node.line, node.col)
        elif isinstance(v, (int, float)) and not isinstance(v, bool) and 0 < v < 1:
            d = dates[int(len(dates) * v)]
        else:
            raise StockLangError('split needs a date like "2026-07-01" or a share of the bars like 70%',
                                 node.line, node.col)
        n_in = int((dates < d).sum())
        n_out = len(dates) - n_in
        if min(n_in, n_out) < 20:
            raise StockLangError(f"split at {report.date(d)} leaves {n_in} bars before and {n_out} after; "
                                 f"each side needs at least 20 (data runs {report.date(dates[0])} to "
                                 f"{report.date(dates[-1])})", node.line, node.col)
        return d

    def cmd_screen(self, node, args, kwargs):
        self._need_stock(node, 'screen')
        if len(args) != 1:
            raise StockLangError(f"usage: {COMMANDS['screen']}", node.line, node.col)
        cond = args[0]
        opts = {k: kwargs.pop(k) for k in ('sort', 'desc', 'limit') if k in kwargs}
        if self.universe is None:
            # The latest bar only -- not last(), which would skip back over a NaN.
            hit = bool(_as_bool(cond).iloc[-1]) if is_series(cond) else bool(cond)
            cols = {k: last(v) for k, v in kwargs.items()}
            extra = '  '.join(f"{k}={report.value(v)}" for k, v in cols.items())
            self.single_screens.append((self.symbol, hit, self.df.index[-1],
                                        {k: _plain(v) for k, v in cols.items()}))
            self.out(f"{self.symbol} {'MATCHES' if hit else 'does not match'} on {report.date(self.df.index[-1])}"
                     + (f"  ({extra})" if extra else ''))
            return

        u = self.universe
        if isinstance(cond, pd.DataFrame):
            hits = _as_bool(cond).iloc[-1]
        else:
            hits = pd.Series(bool(cond), index=u.symbols)
        # A stock whose data stopped updating (suspended, delisted) isn't a match "today".
        latest = u.last_date.max()
        current = u.last_date == latest
        values = {k: (last(v) if isinstance(v, pd.DataFrame) else pd.Series([v] * len(u.symbols), index=u.symbols))
                  for k, v in kwargs.items()}
        r = self.results
        r.screened, r.screen_opts, r.latest = True, opts, latest
        r.stale = int((hits & ~current).sum())
        for sym in hits.index[hits & current]:
            r.screens.append((sym, {k: _plain(v[sym]) for k, v in values.items()}))

    def cmd_plot(self, node, args, kwargs):
        self._need_stock(node, 'plot')
        if self.quiet:
            return
        if self.universe is not None:
            self.results.skipped_plots = True
            return
        _check_kwargs(node, kwargs, {'buy', 'sell', 'title', 'file'}, 'plot')
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt

        series = [(_label(a), v) for a, v in zip(node.args, args) if isinstance(v, pd.Series)]
        if not series:
            series = [('close', self.df['close'])]
        # Lines on roughly the price's scale share the price panel; the rest
        # (RSI, volume, flow) go in a panel underneath.
        ref = self.df['close'].median()
        main, lower = [], []
        for label, s in series:
            m = s.abs().median()
            (main if ref and m and 1 / 3 < m / ref < 3 else lower).append((label, s))
        if not main:
            main = [('close', self.df['close'])]

        fig, axes = plt.subplots(2 if lower else 1, 1, figsize=(12, 7 if lower else 5), sharex=True,
                                 gridspec_kw={'height_ratios': [3, 1]} if lower else None)
        ax = axes[0] if lower else axes
        for label, s in main:
            ax.plot(s.index, s.values, label=label, linewidth=1.6 if label == 'close' else 1.1)
        close = self.df['close']
        for key, marker, color in (('buy', '^', '#1a9850'), ('sell', 'v', '#d73027')):
            sig = kwargs.get(key)
            if isinstance(sig, pd.Series):
                mask = _as_bool(sig).reindex(close.index, fill_value=False)
                ax.scatter(close.index[mask], close[mask], marker=marker, color=color, s=70, zorder=5,
                           label=f"{key} signal")
        ax.set_title(kwargs.get('title') or f"{self.symbol}")
        ax.legend(loc='upper left')
        ax.grid(alpha=0.3)
        if lower:
            for label, s in lower:
                axes[1].plot(s.index, s.values, label=label, linewidth=1.1)
            axes[1].legend(loc='upper left')
            axes[1].grid(alpha=0.3)
        fig.autofmt_xdate()
        fig.tight_layout()

        path = kwargs.get('file')
        if not path:
            stem = os.path.splitext(os.path.basename(self.script_path))[0] if self.script_path else 'stocklang'
            folder = os.path.dirname(os.path.abspath(self.script_path)) if self.script_path else os.getcwd()
            path = os.path.join(folder, f"{stem}_{self.symbol}.png")
        fig.savefig(path, dpi=110)
        plt.close(fig)
        self.out(f"Chart saved: {path}")

    def _need_stock(self, node, what):
        if self.df is None and self.universe is None:
            raise StockLangError(f"{what}() needs a stock first, add a line like: stock BBCA", node.line, node.col)


class UniverseResults:
    """What backtest()/screen() produced across a universe, printed at the end."""

    def __init__(self):
        self.backtests = []
        self.split_backtests = []
        self.split = None
        self.portfolio = None
        self.show_trades = True
        self.screens = []
        self.screened = False
        self.screen_opts = {}
        self.latest = None
        self.stale = 0
        self.skipped_plots = False

    def _report_split(self, out):
        rows = sorted([(s, a, z) for s, a, z in self.split_backtests if a and z],
                      key=lambda x: x[1]['return_pct'], reverse=True)
        if not rows:
            return
        out(f"Each stock on its own, split at {report.date(self.split)} "
            f"(sorted by IN-sample return{', top 20' if len(rows) > 20 else ''}):")
        out(report.table(
            ['Stock', 'In return', 'In B&H', 'Out return', 'Out B&H', 'Out trades'],
            [[s, report.pct(a['return_pct']), report.pct(a['buy_hold_pct']), report.pct(z['return_pct']),
              report.pct(z['buy_hold_pct']), z['n_trades']] for s, a, z in rows[:20]]))
        top = [z for _, a, z in rows[:20] if a['n_trades'] or a['open_trade']]
        both = [(a['return_pct'], z['return_pct']) for _, a, z in rows
                if (a['n_trades'] or a['open_trade']) and (z['n_trades'] or z['open_trade'])]
        out('')
        if top:
            out(f"  Of the top {len(top)} in-sample (with trades), {sum(z['return_pct'] > 0 for z in top)} "
                f"made money out-of-sample.")
        if len(both) >= 10:
            x, y = pd.Series([v for v, _ in both]), pd.Series([v for _, v in both])
            rho = x.rank().corr(y.rank())
            out(f"  Rank correlation in vs out across {len(both)} stocks that traded in both: rho = {rho:+.2f}"
                + (" (near zero: this period's winners don't stay winners)" if abs(rho) < 0.2 else ''))
        out('')

    def report(self, out, n_symbols):
        if self.skipped_plots:
            out("(plot() is skipped when running a universe)")
        if self.portfolio:
            p, p_out = self.portfolio
            out(report.portfolio(p, show_trades=self.show_trades, split_r=p_out, split=self.split))
            out('')
        if self.split_backtests:
            self._report_split(out)
        if self.backtests:
            rows = sorted(self.backtests, key=lambda x: x[1]['return_pct'], reverse=True)
            out(f"Each stock on its own, full capital each ({len(rows)} stocks, best first"
                + (", top 20" if len(rows) > 20 else '') + "):")
            out(report.table(
                ['Stock', 'Return', 'Buy&hold', 'Trades', 'Win rate', 'Max DD'],
                [[s, report.pct(r['return_pct']), report.pct(r['buy_hold_pct']), r['n_trades'],
                  report.pct(r['win_rate'], sign=False), report.pct(r['max_drawdown_pct'])] for s, r in rows[:20]]))
            traded = [r for _, r in rows if r['n_trades'] or r['open_trade']]
            if traded:
                rets = np.array([r['return_pct'] for r in traded])
                beat = sum(1 for r in traded if r['return_pct'] > r['buy_hold_pct'])
                out('')
                out(f"  Stocks with at least one trade: {len(traded)}")
                out(f"  Median return {report.pct(float(np.median(rets)))}, "
                    f"profitable on {(rets > 0).mean() * 100:.0f}% of them, "
                    f"beat buy & hold on {beat / len(traded) * 100:.0f}%")
            out('')
        if self.screened:
            opts = self.screen_opts
            limit = int(opts.get('limit', 20))
            rows = self.screens
            key = opts.get('sort')
            if key:
                desc = bool(opts.get('desc', True))
                rows = sorted(rows, key=lambda x: _sort_key(x[1].get(key), desc))
            when = report.date(self.latest)
            if not rows:
                out(f"No stocks matched on {when} (checked {n_symbols}).")
            else:
                out(f"{len(rows)} of {n_symbols} stocks match on {when}"
                    + (f", showing top {limit}" if len(rows) > limit else '') + ':')
                headers = ['Stock'] + list(rows[0][1])
                out(report.table(headers, [[s] + [report.value(v) for v in cols.values()]
                                           for s, cols in rows[:limit]]))
            if self.stale:
                out(f"({self.stale} more matched on older data and were left out: their data isn't up to date)")


def run_source(src, filename='<script>', out=print, script_path=None):
    """Parse and run a whole script. Handles single-stock, `universe` and `param` sweep scripts."""
    program = parse(src)
    universes = [s for s in program if isinstance(s, UniverseStmt)]
    params = [s for s in program if isinstance(s, ParamStmt)]
    universe = None
    if len(universes) > 1:
        u = universes[1]
        raise StockLangError("only one 'universe' line per script", u.line, u.col)
    if universes:
        stmt = universes[0]
        universe = data.Universe(stmt.symbols or data.all_symbols())
        if stmt.symbols and universe.missing:
            known = data.all_symbols()
            bad = ', '.join(m + (f" (did you mean {h[0]}?)" if (h := difflib.get_close_matches(m, known, n=1)) else '')
                            for m in universe.missing)
            raise StockLangError(f"no data for: {bad}", stmt.line, stmt.col)
        if not universe.symbols:
            raise StockLangError("no stocks with data in this universe", stmt.line, stmt.col)

    if params:
        return _sweep(program, params, universe, out, script_path)
    interp = Interpreter(out=out, script_path=script_path, universe=universe)
    interp.run(program)
    if universe is not None:
        interp.results.report(out, len(universe.symbols))
    return interp


def _sweep(program, params, universe, out, script_path):
    """Run the script once per combination of `param` values and compare the backtests,
    ranked on the in-sample part but always shown with the out-of-sample part."""
    seen = set()
    for p in params:
        if p.name in seen:
            raise StockLangError(f"'param {p.name}' is given twice", p.line, p.col)
        seen.add(p.name)
    probe = Interpreter(out=out)
    values = []
    for p in params:
        try:
            v = probe.eval(p.value, None)
        except StockLangError:
            v = None
        values.append(_param_values(v, p))
    combos = list(itertools.product(*values))
    if len(combos) > MAX_SWEEP:
        p = params[0]
        raise StockLangError(f"{len(combos)} combinations is too many for one sweep (max {MAX_SWEEP}); "
                             f"use fewer values", p.line, p.col)
    names = [p.name for p in params]
    rows, interp, split = [], None, None
    for combo in combos:
        interp = Interpreter(out=out, script_path=script_path, universe=universe,
                             params=dict(zip(names, combo)), quiet=True)
        interp.run(program)
        if interp.last_backtest is None:
            p = params[0]
            raise StockLangError("a param sweep compares backtest() results: add a backtest(buy, sell) line",
                                 p.line, p.col)
        r_in, r_out, split = interp.last_backtest
        rows.append((combo, r_in, r_out))
    out(report.sweep(names, rows, split))
    return interp


def _param_values(v, node):
    v = v if isinstance(v, list) else [v]
    if not v or any(x is None or is_series(x) or isinstance(x, list) for x in v):
        raise StockLangError("param needs fixed values, like param n = [10, 20, 50]", node.line, node.col)
    return v


# ---- helpers ----------------------------------------------------------------

_LIST_ONLY = "a list like [1, 5, 20] only works as an option, e.g. study(cond, days=[1, 5, 20])"


def _as_bool(v):
    if is_series(v):
        return v.fillna(False).astype(bool)
    return bool(v)


def _is_cond(v):
    """A true/false series that can also hold 'unknown' (pandas' nullable boolean)."""
    dtype = v.dtype if isinstance(v, pd.Series) else (v.dtypes.iloc[0] if v.shape[1] else None)
    return isinstance(dtype, pd.BooleanDtype)


def _cond(v):
    """Any value as true/false/unknown: unknown where the series has no value yet."""
    if not is_series(v):
        return bool(v)
    if _is_cond(v):
        return v
    if pd.api.types.is_bool_dtype(v.dtype if isinstance(v, pd.Series) else v.dtypes.iloc[0]):
        return v.astype('boolean')
    return (v != 0).astype('boolean').mask(v.isna())


def _known(r, a, b):
    """A comparison's result, unknown wherever either side has no value yet."""
    unknown = None
    for x in (a, b):
        if is_series(x):
            m = x.isna()
            unknown = m if unknown is None else (unknown | m)
    return r.astype('boolean').mask(unknown)


def _num(v):
    """True/false/unknown series as 1.0/0.0/NaN, so arithmetic and indicators work on it."""
    return v.astype('Float64').astype(float) if is_series(v) and _is_cond(v) else v


def _plain(v):
    if v is pd.NA:
        return float('nan')
    if isinstance(v, (bool, np.bool_)):
        return bool(v)
    try:
        return float(v)
    except (TypeError, ValueError):
        return v


def _text(v):
    if is_series(v):
        v = last(v)
        if isinstance(v, pd.Series):
            return f"({len(v)} stocks)"
    return v if isinstance(v, str) else report.num(v)


def _check_kwargs(node, kwargs, allowed, name):
    for k in kwargs:
        if k not in allowed:
            raise StockLangError(f"{name}() has no option '{k}', options: {', '.join(sorted(allowed))}",
                                 node.line, node.col)


def _sort_key(v, desc):
    if v is None or isinstance(v, str) or (isinstance(v, float) and math.isnan(v)):
        return (1, 0)
    return (0, -v if desc else v)


def _label(node):
    """Turn an expression back into source-ish text for chart legends."""
    if isinstance(node, Name):
        return node.name
    if isinstance(node, Num):
        return report.num(node.value)
    if isinstance(node, Str):
        return repr(node.value)
    if isinstance(node, Call):
        parts = [_label(a) for a in node.args] + [f"{k}={_label(v)}" for k, v in node.kwargs.items()]
        return f"{node.func}({', '.join(parts)})"
    if isinstance(node, BinOp):
        return f"{_label(node.left)} {node.op} {_label(node.right)}"
    if isinstance(node, UnaryOp):
        return f"{node.op} {_label(node.operand)}" if node.op == 'not' else f"-{_label(node.operand)}"
    if isinstance(node, Lag):
        return f"{_label(node.target)}[{_label(node.bars)}]"
    return '?'
