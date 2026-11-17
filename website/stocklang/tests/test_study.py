import numpy as np
import pandas as pd

from stocklang import StockLangError
from stocklang.tests.fixture import SyntheticMarket, random_stock


def stepped_stock(n=60):
    """Price that jumps +10% on the day after every 'flag' day (net_top5 > 0), flat otherwise."""
    idx = pd.bdate_range('2026-01-05', periods=n)
    flag = np.zeros(n)
    flag[[10, 20, 30, 40]] = 1
    close = np.full(n, 1000.0)
    for i in range(1, n):
        close[i] = close[i - 1] * (1.10 if flag[i - 1] else 1.0)
    open_ = np.r_[close[0], close[:-1]]           # opens at yesterday's close
    return pd.DataFrame({'open': open_, 'close': close, 'high': close, 'low': open_,
                         'volume': np.full(n, 1e6), 'net_top5': flag}, index=idx)


class TestStudy(SyntheticMarket):
    stocks = {'JUMP': stepped_stock(), 'FLAT': (stepped_stock() * 0 + 1000).assign(net_top5=0.0),
              'RAND': random_stock(5, n=60, dates=pd.bdate_range('2026-01-05', periods=60))}

    def test_single_stock_matches_hand_calculation(self):
        interp, text = self.run_script("stock JUMP\nstudy(net_top5 > 0, days=[1, 5], fee=0)")
        r = {x['days']: x for x in interp.last_study['rows']}
        # Signal at day i's close -> entry at day i+1's open (= day i's close) -> +10% that day.
        self.assertEqual(r[1]['n'], 4)
        self.assertAlmostEqual(r[1]['avg'], 10.0)
        self.assertAlmostEqual(r[5]['avg'], 10.0)
        self.assertEqual(r[1]['win'], 100.0)
        self.assertIn('4 signals on 1 stock', text)
        self.assertIn('too few', text)

    def test_fee_is_subtracted(self):
        interp, _ = self.run_script("stock JUMP\nstudy(net_top5 > 0, days=1, fee=1%)")
        self.assertAlmostEqual(interp.last_study['rows'][0]['avg'], 9.0)

    def test_universe_edge_vs_same_days(self):
        interp, text = self.run_script("universe [JUMP, FLAT]\nstudy(net_top5 > 0, days=1, fee=0)")
        row = interp.last_study['rows'][0]
        # On signal days JUMP made +10%, FLAT 0% -> market average +5%, so the edge is +5 points.
        self.assertAlmostEqual(row['bench'], 5.0)
        self.assertAlmostEqual(row['edge'], 5.0)
        self.assertIn('All stocks same days', text)

    def test_last_bars_without_a_future_are_skipped(self):
        interp, _ = self.run_script("stock RAND\nstudy(close > 0, days=[1, 20], fee=0)")
        r = {x['days']: x for x in interp.last_study['rows']}
        self.assertEqual(r[1]['n'], 59)
        self.assertEqual(r[20]['n'], 40)

    def test_bad_options(self):
        with self.assertRaises(StockLangError):
            self.run_script("stock RAND\nstudy(close > 0, days=[0])")
        with self.assertRaises(StockLangError):
            self.run_script("stock RAND\nstudy(close > 0, horizon=5)")
        with self.assertRaises(StockLangError) as e:
            self.run_script("stock RAND\nx = close + [1, 2]")
        self.assertIn('only works as an option', e.exception.message)

    def test_never_true(self):
        _, text = self.run_script("stock RAND\nstudy(close < 0)")
        self.assertIn('never true', text)
