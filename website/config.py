"""Portable market inputs and private runtime locations; no local user paths."""
import os
from .runtime_paths import MARKET_DIR, RUNTIME_DIR, external_root

BASE_PATH = MARKET_DIR.as_posix() + '/'
DAILY_PATH = (MARKET_DIR / 'Daily').as_posix() + '/'
WEEKLY_PATH = (MARKET_DIR / 'Weekly').as_posix() + '/'
CHART_PATH = (MARKET_DIR / 'Chart').as_posix() + '/'
OWNERSHIP_PATH = (MARKET_DIR / 'Monthly' / 'Ownership').as_posix() + '/'
MODEL_PATH = str(external_root('PATTERN_MODEL_PATH', RUNTIME_DIR / 'models' / 'best_stock_pattern_model.keras'))
PATTERN_LOOKBACK = 10
PATTERN_FUTURE_DAYS = 20
