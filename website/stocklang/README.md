# StockLang

A small language for IDX stock analysis: indicators, backtests and
screeners in a few readable lines. Reads the same `Daily\Summary` CSVs as
the rest of the app, including broker-flow columns.

```
stock BBCA

fast = sma(close, 10)
slow = sma(close, 30)

buy  = cross_up(fast, slow) and rsi(close, 14) < 70
sell = cross_down(fast, slow)

backtest(buy, sell, capital = 10M, stop_loss = 8%)
plot(close, fast, slow, buy = buy, sell = sell)
```

## Running

From the `website` folder:

```
python -m stocklang stocklang/examples/golden_cross.stk    # run a script
python -m stocklang                                        # interactive prompt
```

Examples in `examples/`:

| File | Shows |
|---|---|
| `golden_cross.stk` | single-stock backtest + chart |
| `smart_money.stk` | broker flow, functions with blocks, `if`/`else` |
| `compare.stk` | one strategy across a list of stocks |
| `screener.stk` | scan every stock for today's matches |
| `out_of_sample.stk` | `split=` in- vs out-of-sample, one shared portfolio |
| `study.stk` | "what happened after X?" across the market, with `rank()` and an IHSG filter |
| `sweep.stk` | `param` sweep: many settings, judged out-of-sample |

## The language

- **Pick data:** `stock BBCA` for one stock, or `universe all` /
  `universe [BBCA, BBRI, TLKM]` to run the script across many at once.
- **Columns:** `open high low close volume avg_price net_top3 net_top5
  foreign_top3 foreign_top5 net_value net_lot buyers sellers retail
  total_bid total_offer` (volume is in shares), plus `ihsg`: the IHSG
  close from Yahoo Finance, lined up with the stock's days. Yahoo can lag
  the Summary files by a day or two; those days use IHSG's last value and
  the script prints a note saying so.
- **Numbers:** `10K`, `10M`, `1.5B`, `0.15%`
- **Lists:** `[1, 5, 20]`, only as options (`days=`) and `param` values.
- **Operators:** `+ - * /`, `< > <= >= == !=`, `and or not`. A comparison
  is *unknown* where either side has no value yet (an indicator's warm-up),
  and `not unknown` stays unknown, so `not (close > sma(close, 50))` can't
  buy before the average exists. `unknown and false` is false,
  `unknown or true` is true; screens and backtests treat unknown as false.
- **Bars ago:** `close[1]` is yesterday's close.
- **Functions:** `fn spread(a, b) = a - b`, or with a block:
  `fn score(n) { x = total(net_top5, n); return where(x > 0, 1, 0) }`
  (statements on one line are separated by `;`)
- **if / else** on single values: `if last(rsi(close)) < 30 { print("oversold") }`
- **Comments:** `# ...` or `// ...`

Built-ins: `sma ema wma stdev bb_upper bb_lower rsi macd macd_signal
macd_hist roc slope atr highest lowest total cumsum cross_up cross_down
rising falling where abs max min round last`. Type `help()` in the prompt
for signatures.

Commands:

- `backtest(buy, sell, capital=10M, fee_buy=0.15%, fee_sell=0.25%, stop_loss=, take_profit=, atr_stop=, trailing_stop=, hold=, idx_rules=true, trades=true, split=, positions=10)`:
  long-only, whole lots of 100, signal at close and fill at the next open.
  - Exits, checked on each close and filled at the next open:
    `stop_loss=8%` / `take_profit=20%` from the entry price,
    `atr_stop=2` (2 x ATR(14) below entry, ATR as of the signal day),
    `trailing_stop=10%` (10% below the highest close since entry),
    `hold=10` (sell after 10 bars in the trade).
  - `idx_rules=true` (the default) applies IDX trading rules from
    `twin/aturan.py`: a buy whose open is already at the upper limit (ARA)
    is skipped, a sell whose open is at the lower limit (ARB) waits for the
    next open, and a buy is capped at 10% of that day's volume. The report
    counts how often each happened. `idx_rules=false` turns them off.
  - `split="2026-07-01"` (or `split=70%` of the bars) reports in-sample and
    out-of-sample side by side, each side starting with fresh capital.
    Indicators still use the full history, so the out-of-sample side has
    its warm-up. In a universe it also shows whether the in-sample winners
    stayed winners (rank correlation in vs out).
  - In a universe, backtest() first runs **one portfolio**: a single pot,
    at most `positions` stocks held at once, each new position sized at
    1/positions of the account; when more stocks signal than there are
    free slots, the most liquid (20-day traded value) go first. Its return
    compounds the way an account would, unlike an average of per-trade
    returns. With `positions=1` and one stock it equals the single-stock
    backtest exactly. The per-stock table (full capital each) follows.
- `study(condition, days=[1, 5, 20], fee=0.4%)`: every bar where the
  condition was true, what happened next. Entry at the next open, exit at
  the close of day H (the same rules as the backtester and the forward
  journal); average, median and win rate are after the fee. The *edge*
  compares the gross result with the same days in general: the same stock
  on any day (one stock), or every stock entered that same day (universe),
  so a market rally doesn't pass for a good signal.
- `param n = [10, 20, 50]`: a **sweep**. The script runs once per value
  (once per combination with several `param` lines, at most 100) and
  prints one table comparing the backtests, ranked on the in-sample part
  with the out-of-sample part beside it. A sweep always splits: at
  `split=` if given, else at 70% of the bars. It says where the best
  in-sample setting landed out-of-sample, and the in-vs-out rank
  correlation. Nothing else prints during a sweep; `plot()` is skipped.
- `screen(condition, name=value, ..., sort="name", desc=true, limit=20)`:
  which stocks match on the latest day.
- `rank(x)` (universe only): where each stock stands against all the
  others on the same day, 0-100 (100 = highest x). `top(x, n)`: true for
  the n stocks with the highest x that day.
- `plot(series, ..., buy=, sell=, title=, file=)`: saves a PNG next to the script.
- `print(...)`

## In the web app

`/stocklang` (sidebar: Laporan) has an editor that runs scripts in a
separate process with a 60-second limit (`stocklang_web.py`). Above it,
**Tulis dengan bahasa biasa** asks Claude (`twin/llm.py`, needs
`ANTHROPIC_API_KEY` or `ant auth login`) to write a script from a plain
request, runs it, and sends any error back for a fix (up to 3 calls, each
billed). Scripts can
be saved; one saved with **Jurnal harian** is run every trading day by
`kesehatan.py` and whatever its `screen()` matches is logged to
`stocklang_jurnal.csv` (`stocklang_jurnal.py`). Only the latest day is ever
logged, never back-filled, so the H+1/H+5/H+20 results the page shows
are genuinely out-of-sample.

## Tests

From the `website` folder (made-up data in a temp folder, no network, no
Claude calls):

```
python -m unittest discover -s stocklang/tests -t .
```

## How it stays fast

Every value is a whole pandas object, so each script line is one NumPy
pass over the data rather than a loop over bars. With `universe`, all
stocks are packed into one table (a column per stock, right-aligned by
bar), so each line runs **once for the whole market**, not once per
stock. Rolling windows come out identical to running each stock on its
own. Parsed CSVs are cached in `.cache/summary.pkl` and only re-read when
a file changes.
