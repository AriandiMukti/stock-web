"""
Made-up Summary CSVs in a temp folder, so tests never read (or depend on)
the real market data. Use SyntheticMarket as a base class.
"""
import os
import shutil
import tempfile
import unittest

import numpy as np
import pandas as pd

from stocklang import data
from stocklang.interpreter import run_source

CSV_COLUMNS = {v: k for k, v in data.COLUMNS.items()}


def write_stock(folder, symbol, df):
    """df: date-indexed, columns named like data.COLUMNS keys (close, volume, ...)."""
    out = pd.DataFrame({'Date': [d.strftime('%d-%b-%y') for d in df.index]})
    for name, csv_name in data.COLUMNS.items():
        out[csv_name] = df[name].to_numpy() if name in df else 0.0
    out.to_csv(os.path.join(folder, f"{symbol}_Summary.csv"), index=False)


def random_stock(seed, n=300, start=1000.0, dates=None):
    rng = np.random.RandomState(seed)
    idx = dates if dates is not None else pd.bdate_range('2025-01-01', periods=n)
    close = start * np.exp(np.cumsum(rng.normal(0, 0.02, len(idx))))
    open_ = close * (1 + rng.normal(0, 0.005, len(idx)))
    return pd.DataFrame({
        'open': open_, 'close': close,
        'high': np.maximum(open_, close) * 1.01, 'low': np.minimum(open_, close) * 0.99,
        'volume': rng.randint(1_000_000, 5_000_000, len(idx)).astype(float),
        'net_top5': rng.normal(0, 1000, len(idx)), 'net_top3': rng.normal(0, 800, len(idx)),
        'retail': rng.normal(0, 1000, len(idx)), 'foreign_top5': rng.normal(0, 500, len(idx)),
    }, index=idx)


class SyntheticMarket(unittest.TestCase):
    """Points StockLang at a temp folder of made-up stocks for each test class."""

    stocks = {}          # symbol -> DataFrame; subclasses override

    @classmethod
    def setUpClass(cls):
        cls.folder = tempfile.mkdtemp(prefix='stocklang_test_')
        cls._saved = (data.SUMMARY_DIR, data.CACHE_FILE)
        data.SUMMARY_DIR = cls.folder
        data.CACHE_FILE = os.path.join(cls.folder, '.cache', 'summary.pkl')
        data.load.cache_clear()
        for sym, df in cls.stocks.items():
            write_stock(cls.folder, sym, df)

    @classmethod
    def tearDownClass(cls):
        data.SUMMARY_DIR, data.CACHE_FILE = cls._saved
        data.load.cache_clear()
        shutil.rmtree(cls.folder, ignore_errors=True)

    def run_script(self, src):
        """Run a script, return (interpreter, printed text)."""
        lines = []
        interp = run_source(src, out=lines.append, script_path=os.path.join(self.folder, 'test.stk'))
        return interp, '\n'.join(lines)
