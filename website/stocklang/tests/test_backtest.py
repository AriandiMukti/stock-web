import unittest

import numpy as np
import pandas as pd

from stocklang import backtest as bt


def frame(opens, closes, volume=None):
    idx = pd.bdate_range('2026-01-05', periods=len(closes))
    n = len(closes)
    return pd.DataFrame({'open': np.array(opens, float), 'close': np.array(closes, float),
                         'high': np.maximum(opens, closes), 'low': np.minimum(opens, closes),
                         'volume': np.full(n, 1e9) if volume is None else np.array(volume, float)}, index=idx)


class TestBacktest(unittest.TestCase):
    def test_signal_fills_at_next_open_in_whole_lots(self):
        df = frame([100, 110, 120, 130, 140], [105, 115, 125, 135, 145])
        buy = pd.Series([True, False, False, False, False], index=df.index)
        sell = pd.Series([False, False, True, False, False], index=df.index)
        r = bt.run(df, buy, sell, capital=1_000_000, fee_buy=0.0, fee_sell=0.0)
        t = r['trades'][0]
        self.assertEqual(t['entry'], 110)            # day 2's open, not day 1's close
        self.assertEqual(t['exit'], 130)
        self.assertEqual(t['shares'] % 100, 0)
        self.assertEqual(t['shares'], (1_000_000 // (110 * 100)) * 100)

    def test_fees(self):
        df = frame([100] * 4, [100] * 4)
        buy = pd.Series([True, False, False, False], index=df.index)
        sell = pd.Series([False, True, False, False], index=df.index)
        r = bt.run(df, buy, sell, capital=1_000_000, fee_buy=0.0015, fee_sell=0.0025)
        self.assertAlmostEqual(r['trades'][0]['return_pct'], ((1 - 0.0025) / (1 + 0.0015) - 1) * 100)

    def test_stop_loss_exits_next_open(self):
        df = frame([100, 100, 90, 85, 85], [100, 100, 89, 85, 85])
        buy = pd.Series([True] + [False] * 4, index=df.index)
        r = bt.run(df, buy, False, stop_loss=0.08, fee_buy=0, fee_sell=0)
        self.assertEqual(r['trades'][0]['reason'], 'stop loss')
        self.assertEqual(r['trades'][0]['exit'], 85)  # open after the -11% close

    def test_price_limits_and_ticks(self):
        self.assertEqual(bt.upper_limit(100), 135)      # <= 200: 35%
        self.assertEqual(bt.upper_limit(1000), 1250)    # <= 5,000: 25%
        self.assertEqual(bt.upper_limit(6000), 7200)    # above: 20%, tick 25
        self.assertEqual(bt.upper_limit(1003), 1250)    # 1253.75 rounded DOWN to the Rp 5 tick
        self.assertEqual(bt.lower_limit(1000), 850)
        self.assertEqual(bt.lower_limit(333), 284)      # 283.05 rounded UP to the Rp 2 tick
        self.assertFalse(bt._at_lower(50, 50))          # Rp50 floor: not a locked drop

    def test_buy_at_ara_is_skipped(self):
        df = frame([1000, 1250, 1300, 1300], [1000, 1300, 1300, 1300])
        buy = pd.Series([True, False, False, False], index=df.index)
        r = bt.run(df, buy, False)
        self.assertEqual(r['n_trades'] + (1 if r['open_trade'] else 0), 0)
        self.assertEqual(r['rules']['ara_skipped'], 1)
        r = bt.run(df, buy, False, idx_rules=False)
        self.assertEqual(r['open_trade']['entry'], 1250)

    def test_sell_at_arb_waits_a_day(self):
        df = frame([1000, 1000, 1000, 850, 860], [1000, 1000, 1000, 850, 860])
        buy = pd.Series([True, False, False, False, False], index=df.index)
        sell = pd.Series([False, False, True, False, False], index=df.index)
        r = bt.run(df, buy, sell)
        self.assertEqual(r['rules']['arb_delayed'], 1)
        self.assertEqual(r['trades'][0]['exit'], 860)
        self.assertEqual(r['trades'][0]['exit_date'], df.index[4])

    def test_volume_cap(self):
        df = frame([100] * 4, [100] * 4, volume=[10_000] * 4)
        buy = pd.Series([True, False, False, False], index=df.index)
        r = bt.run(df, buy, False, capital=10_000_000)
        self.assertEqual(r['open_trade']['shares'], 1_000)          # 10% of 10,000 shares
        self.assertEqual(r['rules']['volume_capped'], 1)

    def test_trailing_stop(self):
        df = frame([100, 100, 150, 200, 175, 170], [100, 150, 200, 175, 170, 170])
        buy = pd.Series([True] + [False] * 5, index=df.index)
        r = bt.run(df, buy, False, trailing_stop=0.10, fee_buy=0, fee_sell=0)
        t = r['trades'][0]
        self.assertEqual(t['reason'], 'trailing stop')
        self.assertEqual(t['exit_date'], df.index[4])                 # 175 <= 200 * 0.9 at bar 3's close

    def test_max_hold(self):
        df = frame([100] * 8, [100] * 8)
        buy = pd.Series([True] + [False] * 7, index=df.index)
        r = bt.run(df, buy, False, hold=3)
        self.assertEqual(r['trades'][0]['reason'], 'max hold')
        self.assertEqual(r['trades'][0]['bars'], 3)

    def test_atr_stop(self):
        df = frame([100, 100, 95, 79, 79], [100, 95, 79, 79, 79])
        buy = pd.Series([True] + [False] * 4, index=df.index)
        atr = pd.Series(10.0, index=df.index)
        r = bt.run(df, buy, False, atr_stop=2, atr=atr, fee_buy=0, fee_sell=0)
        self.assertEqual(r['trades'][0]['reason'], 'atr stop')        # 79 <= 100 - 2 x 10

    def test_portfolio_applies_the_same_rules(self):
        idx = pd.bdate_range('2026-01-05', periods=4)
        closes = pd.DataFrame({'A': [1000, 1300, 1300, 1300], 'B': [100, 100, 100, 100.0]}, index=idx)
        opens = pd.DataFrame({'A': [1000, 1250, 1300, 1300], 'B': [100, 100, 100, 100.0]}, index=idx)
        buy = pd.DataFrame({'A': [True, False, False, False], 'B': [True, False, False, False]}, index=idx)
        sell = buy & False
        rank = closes * 0 + 1
        vol = pd.DataFrame({'A': [1e9] * 4, 'B': [10_000.0] * 4}, index=idx)
        r = bt.portfolio(opens, closes, buy, sell, rank, positions=2, volume=vol)
        self.assertEqual(r['rules']['ara_skipped'], 1)
        self.assertEqual([t['symbol'] for t in r['open_trades']], ['B'])
        self.assertEqual(r['open_trades'][0]['shares'], 1_000)

    def test_no_lookahead(self):
        """Changing the future must not change any trade decided before it."""
        rng = np.random.RandomState(3)
        closes = 100 * np.exp(np.cumsum(rng.normal(0, 0.02, 200)))
        df = frame(closes * 0.999, closes)
        sig = pd.Series(closes, index=df.index)
        buy = sig > sig.rolling(10).mean()
        sell = sig < sig.rolling(10).mean()
        a = bt.run(df, buy, sell)
        df2 = df.copy()
        df2.iloc[150:, :2] *= 3
        sig2 = pd.Series(df2['close'].to_numpy(), index=df.index)
        b = bt.run(df2, sig2 > sig2.rolling(10).mean(), sig2 < sig2.rolling(10).mean())
        early = lambda r: [(t['entry_date'], t['exit_date']) for t in r['trades'] if t['exit_date'] < df.index[150]]
        self.assertEqual(early(a), early(b))
