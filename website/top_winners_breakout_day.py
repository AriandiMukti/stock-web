"""
Refinement: for each of the biggest-rally windows already found
(top_winners_precursors.csv), locate the actual single-day breakout
candle inside that 20-day window (the day with the largest one-day % gain)
instead of just the arbitrary window-start day, then characterize what
preceded THAT specific day.
"""
try:
    from .runtime_paths import runtime_file as _runtime_file, market_file as _market_file, WEBSITE_DIR as _WEBSITE_DIR, PROJECT_DIR as _PROJECT_DIR, RUNTIME_DIR as _RUNTIME_DIR
except ImportError:
    from website.runtime_paths import runtime_file as _runtime_file, market_file as _market_file, WEBSITE_DIR as _WEBSITE_DIR, PROJECT_DIR as _PROJECT_DIR, RUNTIME_DIR as _RUNTIME_DIR
import backtest_signal as bt
import pandas as pd

LOOKBACK_DAYS = 20
FORWARD_DAYS = 20

top = pd.read_csv(_runtime_file('', 'top_winners_precursors.csv'))

dfs = {}
rows = []
for _, r in top.iterrows():
    stock = r['stock']
    if stock not in dfs:
        dfs[stock] = bt.load_stock(stock)
    df = dfs[stock]
    if df is None:
        continue
    i_start = df.index[df['Date'] == r['signal_date']]
    if len(i_start) == 0:
        continue
    i_start = i_start[0]

    close = df['Close']; open_ = df['Open']; volume = df['Volume']
    net_top5 = df['Net Top5 All Lot']; retail = df['Retail']

    window = range(i_start, min(len(df), i_start + FORWARD_DAYS + 1))
    daily_pct = []
    for j in window:
        if j == 0 or close.iloc[j-1] == 0:
            daily_pct.append((-999, j)); continue
        pct = (close.iloc[j] - close.iloc[j-1]) / close.iloc[j-1] * 100
        daily_pct.append((pct, j))
    best_pct, best_j = max(daily_pct)

    if best_j < LOOKBACK_DAYS:
        continue

    w_open = open_.iloc[best_j-LOOKBACK_DAYS:best_j]
    w_close = close.iloc[best_j-LOOKBACK_DAYS:best_j]
    w_vol = volume.iloc[best_j-LOOKBACK_DAYS:best_j]
    w_net = net_top5.iloc[best_j-LOOKBACK_DAYS:best_j]
    w_retail = retail.iloc[best_j-LOOKBACK_DAYS:best_j]
    combined = pd.concat([w_open, w_close])
    cmin = combined.min()
    sideways_range_pct = (combined.max() - cmin) / cmin * 100 if cmin > 0 else None

    avg_vol = w_vol.mean()
    vol_mult = volume.iloc[best_j] / avg_vol if avg_vol > 0 else None
    avg_abs_net = w_net.abs().mean()
    net_mult = net_top5.iloc[best_j] / avg_abs_net if avg_abs_net > 0 else None

    rows.append({
        'stock': stock, 'rally_start_date': r['signal_date'],
        'breakout_date': df['Date'].iloc[best_j].strftime('%Y-%m-%d'),
        'breakout_day_pct': round(best_pct, 2),
        'vol_mult_on_breakout': round(vol_mult, 2) if vol_mult is not None else None,
        'net_mult_on_breakout': round(net_mult, 2) if net_mult is not None else None,
        'sideways_range_pct_before': round(sideways_range_pct, 2) if sideways_range_pct is not None else None,
        'net_positive_days_of_20_before': int((w_net > 0).sum()),
        'retail_negative_days_of_20_before': int((w_retail < 0).sum()),
        'avg_retail_before': round(w_retail.mean(), 1),
        'avg_net_before': round(w_net.mean(), 1),
        'fwd_return_20d_from_rally_start': r['fwd_return_20d'],
    })

out = pd.DataFrame(rows)
out.to_csv(str(_runtime_file("", 'top_winners_breakout_day.csv')), index=False)
print(f"{len(out)} events with identified breakout day")
print()
for col in ['breakout_day_pct','vol_mult_on_breakout','net_mult_on_breakout','sideways_range_pct_before',
            'net_positive_days_of_20_before','retail_negative_days_of_20_before']:
    s = out[col].dropna()
    print(f'{col:35s} median={s.median():9.2f}  mean={s.mean():9.2f}  p25={s.quantile(.25):9.2f}  p75={s.quantile(.75):9.2f}')
