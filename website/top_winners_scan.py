"""
No predefined pattern this time. Find the biggest 20-trading-day rallies
across the whole watchlist first, then look at what actually preceded
each one (volume, net top5 lot, retail, price behavior) to see if a new
pattern falls out of the data instead of testing one we already guessed.
"""
try:
    from .runtime_paths import runtime_file as _runtime_file, market_file as _market_file, WEBSITE_DIR as _WEBSITE_DIR, PROJECT_DIR as _PROJECT_DIR, RUNTIME_DIR as _RUNTIME_DIR
except ImportError:
    from website.runtime_paths import runtime_file as _runtime_file, market_file as _market_file, WEBSITE_DIR as _WEBSITE_DIR, PROJECT_DIR as _PROJECT_DIR, RUNTIME_DIR as _RUNTIME_DIR
import backtest_signal as bt
import pandas as pd

FORWARD_DAYS = 20
LOOKBACK_DAYS = 20
COOLDOWN = 20


def scan_stock(df, stock):
    n = len(df)
    close = df['Close']
    open_ = df['Open']
    volume = df['Volume']
    net_top5 = df['Net Top5 All Lot']
    retail = df['Retail']
    rows = []
    for i in range(LOOKBACK_DAYS, n - FORWARD_DAYS):
        entry = close.iloc[i]
        if entry <= 0:
            continue
        exit_close = close.iloc[i + FORWARD_DAYS]
        fwd_return = (exit_close - entry) / entry * 100
        rows.append((i, fwd_return))
    return rows


stocks = bt.stockList
best_events = []  # (stock, i, fwd_return, df) picked greedily with cooldown
tested = 0
dfs = {}
for s in stocks:
    df = bt.load_stock(s)
    if df is None:
        continue
    tested += 1
    dfs[s] = df
    candidates = scan_stock(df, s)
    if not candidates:
        continue
    # Greedy non-overlapping selection: repeatedly take the single best
    # remaining day, then blank out a COOLDOWN window around it, so one
    # rally doesn't get counted dozens of times from adjacent start days.
    candidates.sort(key=lambda x: -x[1])
    used = [False] * len(df)
    picked = 0
    for i, ret in candidates:
        if used[i]:
            continue
        best_events.append((s, i, ret))
        for k in range(max(0, i - COOLDOWN), min(len(df), i + COOLDOWN)):
            used[k] = True
        picked += 1
        if picked >= 3:  # at most 3 non-overlapping rallies per stock
            break

print(f"Tested {tested}/{len(stocks)} stocks, {len(best_events)} candidate rally events")

best_events.sort(key=lambda x: -x[2])
top_events = best_events[:150]

rows = []
for stock, i, fwd_return in top_events:
    df = dfs[stock]
    close = df['Close']; open_ = df['Open']; volume = df['Volume']
    net_top5 = df['Net Top5 All Lot']; retail = df['Retail']

    entry = close.iloc[i]
    prev_close = close.iloc[i - 1]
    day_jump_pct = (entry - prev_close) / prev_close * 100 if prev_close else None

    w_open = open_.iloc[i-LOOKBACK_DAYS:i]
    w_close = close.iloc[i-LOOKBACK_DAYS:i]
    w_vol = volume.iloc[i-LOOKBACK_DAYS:i]
    w_net = net_top5.iloc[i-LOOKBACK_DAYS:i]
    w_retail = retail.iloc[i-LOOKBACK_DAYS:i]
    combined = pd.concat([w_open, w_close])
    cmin = combined.min()
    sideways_range_pct = (combined.max() - cmin) / cmin * 100 if cmin > 0 else None

    avg_vol = w_vol.mean()
    vol_mult = volume.iloc[i] / avg_vol if avg_vol > 0 else None
    avg_abs_net = w_net.abs().mean()
    net_mult = net_top5.iloc[i] / avg_abs_net if avg_abs_net > 0 else None

    rows.append({
        'stock': stock, 'signal_date': df['Date'].iloc[i].strftime('%Y-%m-%d'),
        'entry_close': entry, 'fwd_return_20d': round(fwd_return, 2),
        'day_jump_pct': round(day_jump_pct, 2) if day_jump_pct is not None else None,
        'vol_mult': round(vol_mult, 2) if vol_mult is not None else None,
        'net_mult': round(net_mult, 2) if net_mult is not None else None,
        'sideways_range_pct': round(sideways_range_pct, 2) if sideways_range_pct is not None else None,
        'net_top5_today': net_top5.iloc[i],
        'retail_today': retail.iloc[i],
        'avg_net_lookback': round(w_net.mean(), 1),
        'avg_retail_lookback': round(w_retail.mean(), 1),
        'net_positive_days_of_20': int((w_net > 0).sum()),
        'retail_negative_days_of_20': int((w_retail < 0).sum()),
        'price_up_today': entry > prev_close,
    })

out = pd.DataFrame(rows)
out.to_csv(str(_runtime_file("", 'top_winners_precursors.csv')), index=False)
print(f"Saved top {len(out)} rally events")
print(out.head(15).to_string(index=False))
