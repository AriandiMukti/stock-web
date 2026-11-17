"""
New angle, not tested before: domestic vs foreign Top5 divergence.
EKAD's Aug 12 breakout showed Net Top5 ALL Lot spiking hugely positive
while Net Top5 FOREIGN Lot spiked hugely negative on the same days --
i.e. domestic big money buying aggressively while foreign investors sell
into it. Testing whether that specific divergence (not just "net top5 up")
precedes a real move, using longer forward windows (40/60 days).
"""
try:
    from .runtime_paths import runtime_file as _runtime_file, market_file as _market_file, WEBSITE_DIR as _WEBSITE_DIR, PROJECT_DIR as _PROJECT_DIR, RUNTIME_DIR as _RUNTIME_DIR
except ImportError:
    from website.runtime_paths import runtime_file as _runtime_file, market_file as _market_file, WEBSITE_DIR as _WEBSITE_DIR, PROJECT_DIR as _PROJECT_DIR, RUNTIME_DIR as _RUNTIME_DIR
import backtest_signal as bt
import pandas as pd

LOOKBACK = 20
FORWARD_WINDOWS = [20, 40, 60]
Z_THRESHOLD = 2.0
COOLDOWN = 20


def zscore_today(series, i, window):
    w = series.iloc[i-window:i]
    mean, std = w.mean(), w.std()
    if std == 0 or pd.isna(std):
        return None
    return (series.iloc[i] - mean) / std


def scan(df, stock):
    n = len(df)
    close = df['Close']
    net_all = df['Net Top5 All Lot']
    net_foreign = df['Net Top5 Foreign Lot']
    domestic = net_all - net_foreign
    max_fwd = max(FORWARD_WINDOWS)
    rows = []
    i = LOOKBACK
    while i < n - max_fwd:
        dz = zscore_today(domestic, i, LOOKBACK)
        fz = zscore_today(net_foreign, i, LOOKBACK)
        if dz is not None and fz is not None and dz >= Z_THRESHOLD and fz <= -Z_THRESHOLD:
            entry = close.iloc[i]
            if entry <= 0:
                i += 1; continue
            row = {
                'stock': stock, 'signal_date': df['Date'].iloc[i].strftime('%Y-%m-%d'),
                'entry_close': entry, 'domestic_z': round(dz, 2), 'foreign_z': round(fz, 2),
                'domestic_today': domestic.iloc[i], 'foreign_today': net_foreign.iloc[i],
            }
            for fw in FORWARD_WINDOWS:
                exit_close = close.iloc[i + fw]
                row[f'fwd_return_{fw}d'] = round((exit_close - entry) / entry * 100, 2)
            rows.append(row)
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
    all_rows.extend(scan(df, s))

out = pd.DataFrame(all_rows)
print(f"Tested {tested}/{len(stocks)} stocks")
print(f"Divergence events found: {len(out)}")
out.to_csv(str(_runtime_file("", 'divergence_signals.csv')), index=False)

if len(out):
    for fw in FORWARD_WINDOWS:
        col = f'fwd_return_{fw}d'
        s = out[col]
        print(f"  {fw}D: avg={s.mean():7.2f}%  median={s.median():7.2f}%  winrate={(s>0).mean()*100:5.1f}%  best={s.max():.2f}%  worst={s.min():.2f}%")
