"""
Variations on the slope-turn idea to make it more selective (v1 was too
loose: 75% of signals passed within 5 days, and the passing group was
still net negative).
"""
import backtest_signal as bt
import pandas as pd

CROSSOVER_CHECK_DAYS = 5


def find_signals(df, stock, roll_window, z_threshold, sustain_days):
    n = len(df)
    net_top5 = df['Net Top5 All Lot']
    retail = df['Retail']
    close = df['Close']

    rollN = net_top5.rolling(window=roll_window).sum()
    slope = rollN.diff()
    slope_std = slope.rolling(window=20).std()
    slope_z = slope / slope_std.replace(0, pd.NA)

    if z_threshold > 0:
        turn_up = (slope.shift(1) <= 0) & (slope_z > z_threshold)
    else:
        turn_up = (slope.shift(1) <= 0) & (slope > 0)

    if sustain_days > 1:
        sustained = turn_up.copy()
        for k in range(1, sustain_days):
            sustained = sustained & (slope.shift(-k) > 0)
        turn_up = sustained

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
        d20_close = close.iloc[i + bt.FORWARD_DAYS]
        rows.append({
            'stock': stock, 'signal_date': signal_date, 'group': group,
            'return_pct_20': round((d20_close - entry) / entry * 100, 2),
        })
    return rows


stocks = bt.stockList
configs = [
    ('5d, plain >0 (v1 baseline)', 5, 0, 1),
    ('10d, plain >0', 10, 0, 1),
    ('5d, z>1', 5, 1.0, 1),
    ('5d, z>1.5', 5, 1.5, 1),
    ('10d, z>1', 10, 1.0, 1),
    ('5d, sustain 2 days', 5, 0, 2),
    ('5d, sustain 3 days', 5, 0, 3),
]

for label, rw, z, sus in configs:
    all_rows = []
    for s in stocks:
        df = bt.load_stock(s)
        if df is None:
            continue
        all_rows.extend(find_signals(df, s, rw, z, sus))
    d = pd.DataFrame(all_rows)
    cross = d[d['group'] == 'crossover_soon']
    no_cross = d[d['group'] == 'no_crossover']
    n_cross = len(cross)
    n_total = len(d)
    avg_c = cross['return_pct_20'].mean() if n_cross else float('nan')
    win_c = (cross['return_pct_20'] > 0).mean() * 100 if n_cross else float('nan')
    avg_nc = no_cross['return_pct_20'].mean() if len(no_cross) else float('nan')
    print(f"{label:28s} N_cross={n_cross:5d}/{n_total:5d} ({n_cross/n_total*100:4.1f}%)  "
          f"avg20={avg_c:6.2f}%  win20={win_c:5.1f}%   | no_cross avg20={avg_nc:6.2f}%")
