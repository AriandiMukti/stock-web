"""
Find actual single-day breakout candles (like EKAD's Aug 12 jump: price up
a lot in one day, on a volume spike) across the whole watchlist, then look
BACKWARD at what preceded them (sideways or not, quiet volume or not) and
FORWARD at whether the move actually continued.
"""
try:
    from .runtime_paths import runtime_file as _runtime_file, market_file as _market_file, WEBSITE_DIR as _WEBSITE_DIR, PROJECT_DIR as _PROJECT_DIR, RUNTIME_DIR as _RUNTIME_DIR
except ImportError:
    from website.runtime_paths import runtime_file as _runtime_file, market_file as _market_file, WEBSITE_DIR as _WEBSITE_DIR, PROJECT_DIR as _PROJECT_DIR, RUNTIME_DIR as _RUNTIME_DIR
import backtest_signal as bt
import pandas as pd

LOOKBACK_DAYS = 20
JUMP_PCT = 15          # single-day close-to-close jump defining a "breakout candle"
VOLUME_SPIKE_MULT = 3
FORWARD_DAYS = 20
COOLDOWN = 20


def find_jump_days(df, stock):
    n = len(df)
    close = df['Close']
    open_ = df['Open']
    volume = df['Volume']
    net_top5 = df['Net Top5 All Lot']
    retail = df['Retail']
    rows = []
    i = LOOKBACK_DAYS
    while i < n - FORWARD_DAYS:
        prev_close = close.iloc[i-1]
        entry = close.iloc[i]
        if prev_close <= 0 or entry <= 0:
            i += 1; continue
        day_jump_pct = (entry - prev_close) / prev_close * 100

        w_vol = volume.iloc[i-LOOKBACK_DAYS:i]
        avg_vol = w_vol.mean()
        vol_today = volume.iloc[i]
        vol_mult = vol_today / avg_vol if avg_vol > 0 else 0

        if day_jump_pct >= JUMP_PCT and vol_mult >= VOLUME_SPIKE_MULT:
            w_open = open_.iloc[i-LOOKBACK_DAYS:i]
            w_close = close.iloc[i-LOOKBACK_DAYS:i]
            w_net = net_top5.iloc[i-LOOKBACK_DAYS:i]
            w_retail = retail.iloc[i-LOOKBACK_DAYS:i]
            combined = pd.concat([w_open, w_close])
            cmin = combined.min()
            sideways_range_pct = (combined.max() - cmin) / cmin * 100 if cmin > 0 else None

            future = close.iloc[i+1:i+FORWARD_DAYS+1]
            fwd_return_20d = (future.iloc[-1] - entry) / entry * 100 if len(future) == FORWARD_DAYS else None

            rows.append({
                'stock': stock, 'signal_date': df['Date'].iloc[i].strftime('%Y-%m-%d'),
                'entry_close': entry, 'day_jump_pct': round(day_jump_pct, 2),
                'vol_mult': round(vol_mult, 2),
                'sideways_range_pct': round(sideways_range_pct, 2) if sideways_range_pct is not None else None,
                'avg_retail_lookback': round(w_retail.mean(), 1),
                'avg_net_lookback': round(w_net.mean(), 1),
                'fwd_return_20d': round(fwd_return_20d, 2) if fwd_return_20d is not None else None,
            })
            i += COOLDOWN
        else:
            i += 1
    return rows


stocks = bt.stockList
all_rows = []
tested = 0
for s in stocks:
    df = bt.load_stock(s)
    if df is None:
        continue
    tested += 1
    all_rows.extend(find_jump_days(df, s))

print(f"Tested {tested}/{len(stocks)} stocks")
df = pd.DataFrame(all_rows)
print(f"Jump-day events found (>= {JUMP_PCT}% in 1 day, volume >= {VOLUME_SPIKE_MULT}x): {len(df)}")
df.to_csv(str(_runtime_file("", 'big_jump_days.csv')), index=False)
