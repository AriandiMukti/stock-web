import os

import pandas as pd

from stocklang import StockLangError
from stocklang.tests.fixture import SyntheticMarket, random_stock

DATES = pd.bdate_range('2025-06-02', periods=200)


class TestSweep(SyntheticMarket):
    stocks = {'AAAA': random_stock(1, dates=DATES), 'BBBB': random_stock(2, dates=DATES)}

    def test_single_stock_sweep_matches_separate_runs(self):
        src = ("stock AAAA\nparam n = [5, 10, 20]\nbuy = cross_up(close, sma(close, n))\n"
               "sell = cross_down(close, sma(close, n))\nbacktest(buy, sell, split = 70%)\n")
        _, text = self.run_script(src)
        self.assertIn('Sweep: 3 settings of n', text)
        for n in (5, 10, 20):
            row = next(l for l in text.splitlines() if l.split()[:1] == [str(n)])
            r_in, r_out, _ = self.run_script(src.replace("param n = [5, 10, 20]", f"n = {n}"))[0].last_backtest
            self.assertEqual(row.split()[1:4:2], [f"{r_in['return_pct']:+.1f}%", f"{r_out['return_pct']:+.1f}%"])

    def test_sweep_splits_even_without_split(self):
        _, text = self.run_script("stock AAAA\nparam n = [5, 10]\n"
                                  "backtest(close > sma(close, n), close < sma(close, n))")
        self.assertIn('split at', text)
        self.assertIn('Out return', text)
        self.assertIn('mostly luck', text)               # 200 made-up bars: few trades per setting

    def test_two_params_and_universe(self):
        _, text = self.run_script("universe all\nparam f = [3, 5]\nparam s = [20, 30]\n"
                                  "backtest(cross_up(sma(close, f), sma(close, s)), "
                                  "cross_down(sma(close, f), sma(close, s)))")
        self.assertIn('Sweep: 4 settings of f, s', text)
        self.assertNotIn('Each stock on its own', text)

    def test_sweep_prints_and_plots_nothing_else(self):
        _, text = self.run_script("stock AAAA\nparam n = [5, 10]\nprint(\"hello\")\nplot(close)\n"
                                  "backtest(close > sma(close, n), close < sma(close, n))")
        self.assertNotIn('hello', text)
        self.assertFalse([f for f in os.listdir(self.folder) if f.endswith('.png')])

    def test_errors(self):
        with self.assertRaises(StockLangError) as e:
            self.run_script("stock AAAA\nparam n = [5, 10]\nprint(n)")
        self.assertIn('add a backtest', e.exception.message)
        with self.assertRaises(StockLangError) as e:
            self.run_script("stock AAAA\nparam n = close\nbacktest(true, false)")
        self.assertIn('fixed values', e.exception.message)
        with self.assertRaises(StockLangError) as e:
            self.run_script("stock AAAA\nparam a = [1,2,3,4,5,6,7,8,9,10,11]\nparam b = [1,2,3,4,5,6,7,8,9,10]\n"
                            "backtest(true, false)")
        self.assertIn('too many', e.exception.message)

    def test_param_outside_a_sweep_takes_the_first_value(self):
        from stocklang import Interpreter, parse
        interp = Interpreter(out=lambda *a: None)
        interp.run(parse("param n = [7, 9]"))
        self.assertEqual(interp.vars['n'], 7)
