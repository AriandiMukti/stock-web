import numpy as np
import pandas as pd

from stocklang import StockLangError, data
from stocklang.tests.fixture import SyntheticMarket

DATES = pd.bdate_range('2026-01-05', periods=30)


def flat(price, dates=DATES):
    return pd.DataFrame({'open': price, 'close': price, 'high': price, 'low': price,
                         'volume': 1e6}, index=dates)


class TestRankTop(SyntheticMarket):
    # C is missing the last 5 days, so the latest date only has A and B.
    stocks = {'A': flat(10.0), 'B': flat(20.0), 'C': flat(30.0, DATES[:-5])}

    def test_rank_is_per_day_across_stocks(self):
        interp, _ = self.run_script("universe all\nr = rank(close)\n")
        u, r = interp.universe, interp.vars['r']
        day = u.stock_series(r, 'A').index[-6]              # a day all three traded
        vals = {s: u.stock_series(r, s).loc[day] for s in 'ABC'}
        self.assertAlmostEqual(vals['A'], 100 / 3)
        self.assertAlmostEqual(vals['B'], 200 / 3)
        self.assertAlmostEqual(vals['C'], 100.0)
        # On the last day C has no bar, so B is the top of two.
        self.assertAlmostEqual(u.stock_series(r, 'B').iloc[-1], 100.0)

    def test_top(self):
        _, text = self.run_script("universe all\nscreen(top(close, 1))")
        self.assertIn('1 of 3 stocks match', text)
        rows = [l.split()[0] for l in text.splitlines() if l.startswith('  ') and not l.strip().startswith(('Stock', '-'))]
        self.assertEqual(rows, ['B'])
        self.assertIn('1 more matched on older data', text)    # C topped its own last day, which is stale

    def test_errors(self):
        with self.assertRaises(StockLangError) as e:
            self.run_script("stock A\nx = rank(close)")
        self.assertIn('needs a universe', e.exception.message)
        with self.assertRaises(StockLangError):
            self.run_script("universe all\nx = top(close, 0)")


class TestIhsg(SyntheticMarket):
    stocks = {'A': flat(10.0), 'B': flat(20.0)}

    def setUp(self):
        self._real = data.ihsg
        # IHSG rising 1 a day, but ending two days before the stock data does.
        data.ihsg = lambda: pd.Series(np.arange(len(DATES) - 2, dtype=float) + 7000, index=DATES[:-2])

    def tearDown(self):
        data.ihsg = self._real

    def test_single_stock(self):
        interp, text = self.run_script("stock A\nx = ihsg\nup = ihsg > sma(ihsg, 5)\nprint(last(x))")
        x = interp.vars['x']
        self.assertEqual(x.iloc[0], 7000)
        self.assertEqual(x.iloc[-1], x.iloc[-3])             # carried forward past Yahoo's last day
        self.assertIn('IHSG from Yahoo Finance ends', text)
        self.assertEqual(text.count('IHSG from Yahoo'), 1)

    def test_universe_market_filter(self):
        _, text = self.run_script("universe all\nscreen(ihsg > sma(ihsg, 5) and close > 0)")
        self.assertIn('2 of 2 stocks match', text)
