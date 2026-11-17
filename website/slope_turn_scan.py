"""
New crossover definition to test: the SLOPE (day-over-day change) of the
5-day rolling sum of Net Top5 All Lot turns from declining-or-flat to
rising (a local trough in the rolling sum, not a sign-flip of the level
itself like the crossover already live in the app).
"""
try:
    from .runtime_paths import runtime_file as _runtime_file, market_file as _market_file, WEBSITE_DIR as _WEBSITE_DIR, PROJECT_DIR as _PROJECT_DIR, RUNTIME_DIR as _RUNTIME_DIR
except ImportError:
    from website.runtime_paths import runtime_file as _runtime_file, market_file as _market_file, WEBSITE_DIR as _WEBSITE_DIR, PROJECT_DIR as _PROJECT_DIR, RUNTIME_DIR as _RUNTIME_DIR
import backtest_signal as bt
import pandas as pd

SLOPE_ROLL_WINDOW = 5
CROSSOVER_CHECK_DAYS = 5


def find_signals(df, stock):
    n = len(df)
    net_top5 = df['Net Top5 All Lot']
    retail = df['Retail']
    close = df['Close']

    roll5 = net_top5.rolling(window=SLOPE_ROLL_WINDOW).sum()
    slope = roll5.diff()
    # turn_up[i]: slope was <=0 the day before, >0 today (declining-or-flat -> rising)
    turn_up = (slope.shift(1) <= 0) & (slope > 0)

    confidence = [None] * n
    for i in range(bt.MIN_HISTORY - 1, n):
        slope_start = max(0, i - bt.SLOPE_DAYS + 1)
        net_slope = net_top5.iloc[slope_start:i + 1].sum()
        retail_slope = retail.iloc[slope_start:i + 1].sum()
        price_now = close.iloc[i]
        price_10d_ago = close.iloc[i - bt.PRICE_LOOKBACK]
        price_flat = price_10d_ago != 0 and abs((price_now - price_10d_ago) / price_10d_ago * 100) < 5
        confidence[i] = sum([net_slope > 0, retail_slope < 0, price_flat])

    rows = []
    for i in range(bt.MIN_HISTORY - 1, n - bt.FORWARD_DAYS):
        if confidence[i] != 3:
            continue
        prev_conf = confidence[i - 1] if i - 1 >= bt.MIN_HISTORY - 1 else None
        if prev_conf == 3:
            continue

        entry = close.iloc[i]
        if entry == 0:
            continue

        check_end = min(n - 1, i + CROSSOVER_CHECK_DAYS)
        if i - 1 < 0 or pd.isna(slope.iloc[i]) or pd.isna(slope.iloc[check_end]):
            group = 'insufficient_history'
        else:
            group = 'no_crossover'
            for j in range(i + 1, check_end + 1):
                if pd.isna(turn_up.iloc[j]):
                    continue
                if bool(turn_up.iloc[j]):
                    group = 'crossover_soon'
                    break

        signal_date = df['Date'].iloc[i].strftime('%Y-%m-%d')
        for h in range(1, bt.FORWARD_DAYS + 1):
            day_close = close.iloc[i + h]
            rows.append({
                'stock': stock, 'signal_date': signal_date, 'entry_close': entry,
                'group': group, 'day': h, 'close': day_close,
                'return_pct': round((day_close - entry) / entry * 100, 2),
            })
    return rows


stocks = bt.stockList
all_rows = []
tested = 0
for s in stocks:
    df = bt.load_stock(s)
    if df is None:
        continue
    tested += 1
    all_rows.extend(find_signals(df, s))

df = pd.DataFrame(all_rows)
print(f"Tested {tested}/{len(stocks)} stocks")
print(f"Signals found: {df.drop_duplicates(['stock','signal_date']).shape[0]} (rows: {len(df)})")
print()
print("Signal groups:", df.drop_duplicates(['stock','signal_date'])['group'].value_counts().to_dict())
print()
for grp in ['crossover_soon', 'no_crossover']:
    sub = df[df['group'] == grp]
    print(f"=== Group: {grp} ===")
    bt.print_curve(sub)
    print()
df.to_csv(str(_runtime_file("", 'slope_turn_results.csv')), index=False)
