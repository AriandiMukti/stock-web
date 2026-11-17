"""
Backtest: whenever a stock first hits the app's 3-star confidence score
(Net Top5 Cumulative > 0, Retail Cumulative < 0, Net Top5 5D Slope > 0 —
same three conditions Compare/Weekly Report already score), how did its
price move over the next 20 trading days?

Reproduces the exact scoring logic from utilities.compute_cumulative_flow
and compare.html's applyCompareWindow, applied at every historical day
instead of just "today", using a rolling 50-bar window per day (matching
how the app always computes "cumulative" — the trailing 50 bars ending
at the evaluation day, not the stock's whole history).

Run: python backtest_signal.py
"""
try:
    from .runtime_paths import runtime_file as _runtime_file, market_file as _market_file, WEBSITE_DIR as _WEBSITE_DIR, PROJECT_DIR as _PROJECT_DIR, RUNTIME_DIR as _RUNTIME_DIR
except ImportError:
    from website.runtime_paths import runtime_file as _runtime_file, market_file as _market_file, WEBSITE_DIR as _WEBSITE_DIR, PROJECT_DIR as _PROJECT_DIR, RUNTIME_DIR as _RUNTIME_DIR
import os
import pandas as pd

from config import DAILY_PATH


def _load_stock_list():
    # models.py starts with `from . import db`, which only works inside
    # the Flask package context — this script is a standalone analysis
    # tool, so pull just the plain `stockList` literal out of that file
    # instead of importing the whole app/DB machinery to get it.
    models_path = os.path.join(os.path.dirname(__file__), 'models.py')
    with open(models_path, encoding='utf-8') as f:
        source = f.read()
    ns = {}
    exec(source[source.index('stockList'):source.index(']', source.index('stockList')) + 1], ns)
    return ns['stockList']


stockList = _load_stock_list()

SUMMARY_DIR = os.path.join(DAILY_PATH, "Summary")
SLOPE_DAYS = 5         # trailing bars Net Top5 / Retail are summed over
PRICE_LOOKBACK = 10    # trailing bars the price-flatness check spans
MIN_HISTORY = PRICE_LOOKBACK + 1   # need at least this many bars to evaluate a day
FORWARD_DAYS = 20      # how far ahead to measure the outcome

# Follow-up split: does the signal shortly precede an actual crossover
# (the trailing-N-bar cumulative Net Top5 Lot flipping from <=0 to >0 —
# the same "Big Lot Flow turns positive" marker the chart/Compare page
# show), or does the stock just stay flat with no follow-through?
CROSSOVER_WINDOW = 40
CROSSOVER_CHECK_DAYS = 5
CROSSOVER_PROXIMITY_DAYS = 3   # max gap allowed between the Net Top5 up-flip and the Retail down-flip


def load_stock(stock):
    path = os.path.join(SUMMARY_DIR, f"{stock}_Summary.csv")
    if not os.path.exists(path):
        return None
    try:
        df = pd.read_csv(path).fillna(0)
    except Exception:
        return None
    if df.empty or len(df) < MIN_HISTORY + FORWARD_DAYS + 1:
        return None
    df['Date'] = pd.to_datetime(df['Date'], format='%d-%b-%y')
    df = df.sort_values('Date').reset_index(drop=True)
    return df


def find_three_star_signals(df, stock, crossover_window=CROSSOVER_WINDOW):
    """
    Returns one row per day the stock's confidence score == 3, with the
    return_pct at *every* offset from h+1 to h+FORWARD_DAYS (not just the
    day-20 endpoint) — so the path the price takes to get there is
    visible, not just where it lands.

    Confidence (0-3), matching utilities.compute_cumulative_flow:
      1. Net Top5 All Lot summed over the last 5 days > 0
      2. Retail summed over the last 5 days < 0
      3. Price hasn't moved more than 5% (either direction) over the
         last 10 trading days

    `crossover_window` is exposed as a parameter (not just the module
    constant) so a window sweep can reuse the same cached dataframe
    across several window sizes without re-reading CSVs each time.
    """
    n = len(df)
    net_top5 = df['Net Top5 All Lot']
    retail = df['Retail']
    close = df['Close']
    net_top5_roll = net_top5.rolling(window=crossover_window).sum()  # sum of last `crossover_window` bars ending at i
    retail_roll = retail.rolling(window=crossover_window).sum()

    confidence = [None] * n
    for i in range(MIN_HISTORY - 1, n):
        slope_start = max(0, i - SLOPE_DAYS + 1)
        net_slope = net_top5.iloc[slope_start:i + 1].sum()
        retail_slope = retail.iloc[slope_start:i + 1].sum()

        price_now = close.iloc[i]
        price_10d_ago = close.iloc[i - PRICE_LOOKBACK]
        price_flat = price_10d_ago != 0 and abs((price_now - price_10d_ago) / price_10d_ago * 100) < 5

        confidence[i] = sum([net_slope > 0, retail_slope < 0, price_flat])

    rows = []
    for i in range(MIN_HISTORY - 1, n - FORWARD_DAYS):
        if confidence[i] != 3:
            continue
        # Only count the *start* of a 3-star streak — a stock that stays
        # at 3 stars for a week shouldn't count as 5-7 separate signals
        # of the same underlying move.
        prev_conf = confidence[i - 1] if i - 1 >= MIN_HISTORY - 1 else None
        if prev_conf == 3:
            continue

        entry = close.iloc[i]
        if entry == 0:
            continue

        # Classify: does Net Top5's rolling sum flip up (<=0 -> >0) AND
        # Retail's rolling sum flip down (>0 -> <=0) within
        # CROSSOVER_CHECK_DAYS after the signal, with the two flips no
        # more than CROSSOVER_PROXIMITY_DAYS apart (not necessarily the
        # same day)? Or is there not enough history (< CROSSOVER_WINDOW
        # bars) before this signal to even check?
        check_end = min(n - 1, i + CROSSOVER_CHECK_DAYS)
        if (i - 1 < 0 or pd.isna(net_top5_roll.iloc[i]) or pd.isna(net_top5_roll.iloc[check_end])
                or pd.isna(retail_roll.iloc[i]) or pd.isna(retail_roll.iloc[check_end])):
            group = 'insufficient_history'
        else:
            net_up_days = []
            retail_down_days = []
            for j in range(i + 1, check_end + 1):
                if not pd.isna(net_top5_roll.iloc[j - 1]) and not pd.isna(net_top5_roll.iloc[j]):
                    if net_top5_roll.iloc[j - 1] <= 0 and net_top5_roll.iloc[j] > 0:
                        net_up_days.append(j)
                if not pd.isna(retail_roll.iloc[j - 1]) and not pd.isna(retail_roll.iloc[j]):
                    if retail_roll.iloc[j - 1] > 0 and retail_roll.iloc[j] <= 0:
                        retail_down_days.append(j)

            group = 'no_crossover'
            if net_up_days and retail_down_days:
                min_gap = min(abs(a - b) for a in net_up_days for b in retail_down_days)
                if min_gap <= CROSSOVER_PROXIMITY_DAYS:
                    group = 'crossover_soon'

        signal_date = df['Date'].iloc[i].strftime('%Y-%m-%d')
        for h in range(1, FORWARD_DAYS + 1):
            day_close = close.iloc[i + h]
            rows.append({
                'stock': stock,
                'signal_date': signal_date,
                'entry_close': entry,
                'group': group,
                'day': h,
                'close': day_close,
                'return_pct': round((day_close - entry) / entry * 100, 2),
            })
    return rows


_stock_df_cache = {}


def get_cached_stock_df(stock):
    if stock not in _stock_df_cache:
        _stock_df_cache[stock] = load_stock(stock)
    return _stock_df_cache[stock]


def run_backtest(stocks, crossover_window=CROSSOVER_WINDOW):
    all_signals = []
    tested = 0
    for stock in stocks:
        df = get_cached_stock_df(stock)
        if df is None:
            continue
        tested += 1
        all_signals.extend(find_three_star_signals(df, stock, crossover_window))
    return tested, all_signals


def sweep_crossover_windows(stocks, windows):
    """
    Runs the crossover_soon/no_crossover split at several window sizes
    and reports just the headline day-20 numbers for each — a quick way
    to see whether a shorter or longer window captures a stronger edge,
    instead of testing one value at a time by hand.
    """
    print(f"{'Window':>7} {'Crossover N':>12} {'AvgRet d20%':>12} {'WinRate d20%':>13} {'AvgRet d5%':>11} {'WinRate d5%':>12}")
    for window in windows:
        _, signals = run_backtest(stocks, crossover_window=window)
        if not signals:
            print(f"{window:>7}   (no signals)")
            continue
        df = pd.DataFrame(signals)
        crossover = df[df['group'] == 'crossover_soon']
        n_crossover = crossover.drop_duplicates(['stock', 'signal_date']).shape[0]
        d20 = crossover[crossover['day'] == FORWARD_DAYS]['return_pct']
        d5 = crossover[crossover['day'] == 5]['return_pct']
        if len(d20) == 0:
            print(f"{window:>7} {n_crossover:>12}   (no crossover signals at this window)")
            continue
        print(f"{window:>7} {n_crossover:>12} {d20.mean():>12.2f} {(d20 > 0).mean()*100:>13.1f} "
              f"{d5.mean():>11.2f} {(d5 > 0).mean()*100:>12.1f}")


def print_curve(df):
    print(f"{'Day':>4} {'AvgRet%':>9} {'MedRet%':>9} {'WinRate%':>9} {'Std%':>8}")
    curve = df.groupby('day')['return_pct'].agg(['mean', 'median', 'std'])
    win_rate_by_day = df.groupby('day')['return_pct'].apply(lambda s: (s > 0).mean() * 100)
    for h in range(1, FORWARD_DAYS + 1):
        if h not in curve.index:
            continue
        row = curve.loc[h]
        print(f"{h:>4} {row['mean']:>9.2f} {row['median']:>9.2f} {win_rate_by_day.loc[h]:>9.1f} {row['std']:>8.2f}")

    day20 = df[df['day'] == FORWARD_DAYS]['return_pct']
    if len(day20):
        print(f"  -> Day {FORWARD_DAYS}: win rate {(day20 > 0).mean()*100:.1f}%, avg {day20.mean():.2f}%, "
              f"median {day20.median():.2f}%, std {day20.std():.2f}%  (best {day20.max():.2f}%, worst {day20.min():.2f}%)")


def print_per_stock(df, min_signals=1):
    """
    Per-ticker breakdown — return_pct is always relative to that signal's
    own entry_close (the price on the signal day), so this answers "which
    stocks does this signal actually work on" instead of hiding good/bad
    individual tickers inside one pooled average.
    """
    sig_count = df.drop_duplicates(['stock', 'signal_date']).groupby('stock').size()
    day20 = df[df['day'] == FORWARD_DAYS].groupby('stock')['return_pct'].agg(['mean', 'median', lambda s: (s > 0).mean() * 100])
    day20.columns = ['avg_ret_d20', 'median_ret_d20', 'win_rate_d20']
    all_days_avg = df.groupby('stock')['return_pct'].mean().rename('avg_ret_all_days')

    table = pd.concat([sig_count.rename('signals'), all_days_avg, day20], axis=1)
    table = table[table['signals'] >= min_signals].sort_values('avg_ret_all_days', ascending=False)

    print(f"{'Stock':<7} {'Signals':>7} {'AvgRet(all 20d)%':>17} {'AvgRet(d20)%':>13} {'MedRet(d20)%':>13} {'WinRate(d20)%':>14}")
    for stock, row in table.iterrows():
        print(f"{stock:<7} {int(row['signals']):>7} {row['avg_ret_all_days']:>17.2f} {row['avg_ret_d20']:>13.2f} {row['median_ret_d20']:>13.2f} {row['win_rate_d20']:>14.1f}")
    return table


def summarize(signals):
    if not signals:
        print("No 3-star signals found in the tested history.")
        return
    df = pd.DataFrame(signals)
    n_signals = df.groupby(['stock', 'signal_date']).ngroups
    print(f"Signals found: {n_signals}  (rows: {len(df)} = signals x {FORWARD_DAYS} days)")
    print()

    print("=== All signals ===")
    print_curve(df)

    print()
    counts = df.drop_duplicates(['stock', 'signal_date'])['group'].value_counts()
    print(f"Signal groups: {dict(counts)}")

    for group_name, label in [
        ('crossover_soon', f'=== Group: crossover within {CROSSOVER_CHECK_DAYS} days after signal ==='),
        ('no_crossover', '=== Group: no crossover follow-through ==='),
    ]:
        subset = df[df['group'] == group_name]
        if subset.empty:
            continue
        print()
        print(label)
        print_curve(subset)

    print()
    print("=== Per-stock breakdown (crossover_soon group, return_pct is vs each signal's own entry price) ===")
    crossover_df = df[df['group'] == 'crossover_soon']
    per_stock_table = print_per_stock(crossover_df, min_signals=1)

    out_path = str(_runtime_file('', 'backtest_3star_results.csv'))
    df.sort_values(['stock', 'signal_date', 'day']).to_csv(out_path, index=False)
    print(f"\nFull day-by-day results saved to {out_path}")

    per_stock_path = str(_runtime_file('', 'backtest_per_stock.csv'))
    per_stock_table.to_csv(per_stock_path)
    print(f"Per-stock breakdown saved to {per_stock_path}")


if __name__ == '__main__':
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == 'sweep':
        windows = [int(w) for w in sys.argv[2:]] or [10, 15, 20, 25, 30, 35, 40, 50, 60, 75]
        print(f"Sweeping crossover window sizes: {windows}")
        print()
        sweep_crossover_windows(stockList, windows)
    else:
        tested, signals = run_backtest(stockList)
        print(f"Tested {tested}/{len(stockList)} stocks with enough history (>= {MIN_HISTORY + FORWARD_DAYS + 1} daily bars)")
        print()
        summarize(signals)
