"""
Reverse approach: instead of defining a pattern and testing forward
returns, find stocks that already had a big rally (like EKAD) and look
backward at what was happening in the 20 days before the rally started,
to see if there's a common precursor pattern.
"""
try:
    from .runtime_paths import runtime_file as _runtime_file, market_file as _market_file, WEBSITE_DIR as _WEBSITE_DIR, PROJECT_DIR as _PROJECT_DIR, RUNTIME_DIR as _RUNTIME_DIR
except ImportError:
    from website.runtime_paths import runtime_file as _runtime_file, market_file as _market_file, WEBSITE_DIR as _WEBSITE_DIR, PROJECT_DIR as _PROJECT_DIR, RUNTIME_DIR as _RUNTIME_DIR
import backtest_signal as bt
import pandas as pd

LOOKBACK_DAYS = 20      # days before the rally start to characterize
BIG_RETURN_PCT = 30     # rally = price up this much within RALLY_WINDOW days
RALLY_WINDOW = 20
COOLDOWN = 20           # skip ahead this many days after a detected rally start


def find_big_rallies(df, stock):
    n = len(df)
    close = df['Close']
    open_ = df['Open']
    volume = df['Volume']
    net_top5 = df['Net Top5 All Lot']
    retail = df['Retail']
    rows = []
    i = LOOKBACK_DAYS
    while i < n - RALLY_WINDOW:
        entry = close.iloc[i]
        if entry <= 0:
            i += 1; continue
        future_max = close.iloc[i+1:i+RALLY_WINDOW+1].max()
        rally_pct = (future_max - entry) / entry * 100

        if rally_pct >= BIG_RETURN_PCT:
            w_open = open_.iloc[i-LOOKBACK_DAYS:i]
            w_close = close.iloc[i-LOOKBACK_DAYS:i]
            w_vol = volume.iloc[i-LOOKBACK_DAYS:i]
            w_net = net_top5.iloc[i-LOOKBACK_DAYS:i]
            w_retail = retail.iloc[i-LOOKBACK_DAYS:i]
            combined = pd.concat([w_open, w_close])
            cmin = combined.min()
            sideways_range_pct = (combined.max() - cmin) / cmin * 100 if cmin > 0 else None

            avg_vol = w_vol.mean()
            vol_today = volume.iloc[i]
            vol_mult = vol_today / avg_vol if avg_vol > 0 else None

            avg_abs_net = w_net.abs().mean()
            net_today = net_top5.iloc[i]
            net_mult = net_today / avg_abs_net if avg_abs_net > 0 else None

            price_up_today = entry > close.iloc[i-1]
            net_positive_lookback_days = int((w_net > 0).sum())
            retail_negative_lookback_days = int((w_retail < 0).sum())

            rows.append({
                'stock': stock, 'signal_date': df['Date'].iloc[i].strftime('%Y-%m-%d'),
                'entry_close': entry, 'rally_pct_20d': round(rally_pct, 2),
                'sideways_range_pct': round(sideways_range_pct, 2) if sideways_range_pct is not None else None,
                'vol_mult': round(vol_mult, 2) if vol_mult is not None else None,
                'net_mult': round(net_mult, 2) if net_mult is not None else None,
                'price_up_today': price_up_today,
                'net_positive_days_of_20': net_positive_lookback_days,
                'retail_negative_days_of_20': retail_negative_lookback_days,
                'avg_vol_lookback': round(avg_vol, 0),
                'avg_net_lookback': round(w_net.mean(), 1),
                'avg_retail_lookback': round(w_retail.mean(), 1),
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
    all_rows.extend(find_big_rallies(df, s))

print(f"Tested {tested}/{len(stocks)} stocks")
df = pd.DataFrame(all_rows)
print(f"Big-rally events found (>= {BIG_RETURN_PCT}% within {RALLY_WINDOW} days): {len(df)}")
df.to_csv(str(_runtime_file("", 'big_winner_precursors.csv')), index=False)
