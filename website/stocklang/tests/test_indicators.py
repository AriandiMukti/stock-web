import unittest

import numpy as np
import pandas as pd

from stocklang import indicators as ind


class TestIndicators(unittest.TestCase):
    def setUp(self):
        rng = np.random.RandomState(0)
        self.x = pd.Series(100 + np.cumsum(rng.normal(0, 1, 120)))

    def test_sma_matches_plain_mean(self):
        self.assertAlmostEqual(ind.sma(self.x, 10).iloc[-1], self.x.iloc[-10:].mean())
        self.assertTrue(ind.sma(self.x, 10).iloc[:9].isna().all())

    def test_wma_matches_definition(self):
        w = np.arange(1, 11)
        self.assertAlmostEqual(ind.wma(self.x, 10).iloc[-1], (self.x.iloc[-10:] * w).sum() / w.sum())

    def test_slope_of_a_line(self):
        line = pd.Series(np.arange(50) * 3.0 + 7)
        self.assertAlmostEqual(ind.slope(line, 10).iloc[-1], 3.0)

    def test_rsi_bounds(self):
        r = ind.rsi(self.x, 14).dropna()
        self.assertTrue(((r >= 0) & (r <= 100)).all())
        self.assertEqual(ind.rsi(pd.Series(np.arange(40.0)), 14).iloc[-1], 100.0)

    def test_cross_up(self):
        a = pd.Series([1, 2, 3, 4.0])
        b = pd.Series([2, 2, 2, 2.0])
        self.assertEqual(ind.cross_up(a, b).tolist(), [False, False, True, False])

    def test_works_on_a_universe_frame(self):
        df = pd.DataFrame({'A': self.x, 'B': self.x * 2})
        self.assertAlmostEqual(ind.sma(df, 5)['B'].iloc[-1], 2 * ind.sma(self.x, 5).iloc[-1])
