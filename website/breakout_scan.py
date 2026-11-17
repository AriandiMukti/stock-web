try:
    from .runtime_paths import runtime_file as _runtime_file, market_file as _market_file, WEBSITE_DIR as _WEBSITE_DIR, PROJECT_DIR as _PROJECT_DIR, RUNTIME_DIR as _RUNTIME_DIR
except ImportError:
    from website.runtime_paths import runtime_file as _runtime_file, market_file as _market_file, WEBSITE_DIR as _WEBSITE_DIR, PROJECT_DIR as _PROJECT_DIR, RUNTIME_DIR as _RUNTIME_DIR
import backtest_signal as bt
import pandas as pd

SIDEWAYS_DAYS = 20
SIDEWAYS_MAX_RANGE_PCT = 4
VOLUME_SPIKE_MULT = 3
FORWARD_DAYS = 20

def find_breakout_signals(df, stock):
    n = len(df)
    open_ = df['Open']
    close = df['Close']
    volume = df['Volume']
    rows = []
    i = SIDEWAYS_DAYS
    while i < n - FORWARD_DAYS:
        # Sideways band from Open/Close only, not High/Low — wicks can
        # make an otherwise flat stock look like it moved a lot.
        window_open = open_.iloc[i-SIDEWAYS_DAYS:i]
        window_close = close.iloc[i-SIDEWAYS_DAYS:i]
        window_vol = volume.iloc[i-SIDEWAYS_DAYS:i]
        combined = pd.concat([window_open, window_close])
        cmin = combined.min()
        if cmin <= 0:
            i += 1; continue
        price_range_pct = (combined.max() - cmin) / cmin * 100
        avg_vol = window_vol.mean()
        vol_today = volume.iloc[i]
        entry = close.iloc[i]
        price_up_today = entry > close.iloc[i - 1]

        is_sideways = price_range_pct <= SIDEWAYS_MAX_RANGE_PCT
        is_vol_spike = avg_vol > 0 and vol_today >= VOLUME_SPIKE_MULT * avg_vol

        if is_sideways and is_vol_spike and price_up_today and entry != 0:
            signal_date = df['Date'].iloc[i].strftime('%Y-%m-%d')
            for h in range(1, FORWARD_DAYS + 1):
                day_close = close.iloc[i + h]
                rows.append({
                    'stock': stock, 'signal_date': signal_date, 'entry_close': entry,
                    'day': h, 'close': day_close,
                    'return_pct': round((day_close - entry) / entry * 100, 2),
                    'vol_mult': round(vol_today / avg_vol, 1),
                    'sideways_range_pct': round(price_range_pct, 1),
                })
            i += FORWARD_DAYS  # cooldown so we don't re-trigger on the same breakout run
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
    all_rows.extend(find_breakout_signals(df, s))

print(f"Tested {tested}/{len(stocks)} stocks")
df = pd.DataFrame(all_rows)
n_signals = df.drop_duplicates(['stock','signal_date']).shape[0] if len(df) else 0
print(f"Breakout signals found: {n_signals}  (rows: {len(df)})")
df.to_csv(str(_runtime_file("", 'breakout_signals.csv')), index=False)

