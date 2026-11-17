import numpy as np
import pandas as pd

from stocklang import StockLangError, parse
from stocklang.tests.fixture import SyntheticMarket, random_stock


class TestParsing(SyntheticMarket):
    stocks = {'AAAA': random_stock(1)}

    def test_number_shorthand(self):
        stmts = parse("x = 10M + 1.5B + 0.15%")
        self.assertEqual(len(stmts), 1)

    def test_errors_point_at_the_line(self):
        with self.assertRaises(StockLangError) as e:
            parse("x = 1\ny = (2 +")
        self.assertEqual(e.exception.line, 2)

    def test_unknown_name_suggests(self):
        with self.assertRaises(StockLangError) as e:
            self.run_script("stock AAAA\nprint(clsoe)")
        self.assertIn("did you mean 'close'", e.exception.message)


class TestUnknownDuringWarmup(SyntheticMarket):
    """`not` must keep 'no value yet' as unknown, not flip it to true."""
    stocks = {'AAAA': random_stock(1), 'BBBB': random_stock(2)}

    def test_not_keeps_warmup_unknown(self):
        interp, _ = self.run_script("stock AAAA\nup = close > sma(close, 50)\ndown = not up\n")
        down = interp.vars['down']
        self.assertTrue(down.iloc[:49].isna().all(), "warm-up bars must stay unknown")
        self.assertTrue(down.iloc[49:].notna().all())
        up = interp.vars['up'].iloc[49:].astype(bool)
        self.assertTrue((down.iloc[49:].astype(bool) == ~up).all())

    def test_backtest_does_not_trade_in_warmup(self):
        interp, text = self.run_script(
            "stock AAAA\nbuy = not (close > sma(close, 50))\nsell = close > sma(close, 50)\n"
            "backtest(buy, sell)\n")
        first_sma = interp.df.index[49]
        bought = [l.split()[0] for l in text.splitlines() if l.strip()[:4].isdigit()]
        self.assertTrue(bought, "expected some trades")
        self.assertTrue(all(pd.Timestamp(d) > first_sma for d in bought), bought)

    def test_and_or_three_valued(self):
        interp, _ = self.run_script(
            "stock AAAA\nu = close > sma(close, 10)\na = u and false\nb = u or true\nc = u and true\n")
        self.assertFalse(interp.vars['a'].isna().any())
        self.assertTrue(interp.vars['b'].all())
        self.assertTrue(interp.vars['c'].iloc[:9].isna().all())

    def test_conditions_still_work_in_arithmetic_and_indicators(self):
        interp, _ = self.run_script(
            "stock AAAA\nup = close > open\nn = total(up, 5)\nk = up * 2\nw = where(up, 1, 0)\n")
        self.assertTrue(np.isnan(interp.vars['n'].iloc[3]))
        self.assertTrue(set(interp.vars['n'].dropna().unique()) <= {0, 1, 2, 3, 4, 5})
        self.assertTrue(set(interp.vars['k'].unique()) <= {0.0, 2.0})
        self.assertTrue(set(interp.vars['w'].unique()) <= {0.0, 1.0})

    def test_print_and_screen_handle_conditions(self):
        _, text = self.run_script("stock AAAA\nprint(not (close > sma(close, 5)))\n"
                                  "screen(close > 0, up = close > open)")
        self.assertRegex(text.splitlines()[0], r'^(true|false)$')
        self.assertIn('AAAA', text)

    def test_universe_not_and_screen(self):
        _, text = self.run_script("universe all\nx = not (close > sma(close, 20))\nprint(x)\n"
                                  "screen(x or not x, flag = x)")
        self.assertIn('true for', text)
        self.assertIn('2 of 2 stocks match', text)

    def test_universe_backtest_with_not(self):
        _, text = self.run_script("universe all\nbuy = not (close > sma(close, 50))\n"
                                  "backtest(buy, close > sma(close, 50), trades=false)")
        self.assertIn('Portfolio', text)
