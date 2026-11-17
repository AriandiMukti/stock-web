"""
Another new angle: genuine slow/steady accumulation over a longer (60-day)
window, explicitly excluding cases dominated by one big spike day, and
requiring the stock hasn't already run up much -- the "stealth accumulation"
story, tested with longer 40/60-day forward windows this time instead of 20.
"""
try:
    from .runtime_paths import runtime_file as _runtime_file, market_file as _market_file, WEBSITE_DIR as _WEBSITE_DIR, PROJECT_DIR as _PROJECT_DIR, RUNTIME_DIR as _RUNTIME_DIR
except ImportError:
    from website.runtime_paths import runtime_file as _runtime_file, market_file as _market_file, WEBSITE_DIR as _WEBSITE_DIR, PROJECT_DIR as _PROJECT_DIR, RUNTIME_DIR as _RUNTIME_DIR
import backtest_signal as bt
import pandas as pd

LOOKBACK = 60
FORWARD_WINDOWS = [20, 40, 60]
COOLDOWN = 40
MAX_PRICE_DRIFT_PCT = 20   # hasn't already run up more than this over the lookback
MAX_SINGLE_DAY_SHARE = 0.3  # no single day should be >30% of the total net-lot sum


def scan(df, stock):
    n = len(df)
    close = df['Close']
    net_top5 = df['Net Top5 All Lot']
    retail = df['Retail']
    max_fwd = max(FORWARD_WINDOWS)
    rows = []
    i = LOOKBACK
    while i < n - max_fwd:
        w_net = net_top5.iloc[i-LOOKBACK:i]
        net_sum = w_net.sum()
        if net_sum <= 0:
            i += 1; continue

        max_single_day = w_net.abs().max()
        if net_sum == 0 or max_single_day / abs(net_sum) > MAX_SINGLE_DAY_SHARE if net_sum != 0 else True:
            pass
        single_day_share = max_single_day / net_sum if net_sum > 0 else 1
        if single_day_share > MAX_SINGLE_DAY_SHARE:
            i += 1; continue

        price_then = close.iloc[i - LOOKBACK]
        price_now = close.iloc[i]
        if price_then <= 0:
            i += 1; continue
        price_drift_pct = (price_now - price_then) / price_then * 100
        if abs(price_drift_pct) > MAX_PRICE_DRIFT_PCT:
            i += 1; continue

        w_retail = retail.iloc[i-LOOKBACK:i]
        retail_sum = w_retail.sum()

        entry = price_now
        if entry <= 0:
            i += 1; continue

        row = {
            'stock': stock, 'signal_date': df['Date'].iloc[i].strftime('%Y-%m-%d'),
            'entry_close': entry, 'net_top5_60d_sum': round(net_sum, 1),
            'retail_60d_sum': round(retail_sum, 1),
            'price_drift_60d_pct': round(price_drift_pct, 2),
            'single_day_share': round(single_day_share, 2),
        }
        for fw in FORWARD_WINDOWS:
            exit_close = close.iloc[i + fw]
            row[f'fwd_return_{fw}d'] = round((exit_close - entry) / entry * 100, 2)
        rows.append(row)
        i += COOLDOWN
    return rows


stocks = bt.stockList
all_rows = []
tested = 0
for s in stocks:
    df = bt.load_stock(s)
    if df is None:
        continue
    tested += 1
    all_rows.extend(scan(df, s))

out = pd.DataFrame(all_rows)
print(f"Tested {tested}/{len(stocks)} stocks")
print(f"Slow-accumulation events found: {len(out)}")
out.to_csv(str(_runtime_file("", 'slow_accumulation_signals.csv')), index=False)

if len(out):
    for fw in FORWARD_WINDOWS:
        col = f'fwd_return_{fw}d'
        s = out[col]
        print(f"  {fw}D: avg={s.mean():7.2f}%  median={s.median():7.2f}%  winrate={(s>0).mean()*100:5.1f}%  best={s.max():.2f}%  worst={s.min():.2f}%  N={len(s)}")
