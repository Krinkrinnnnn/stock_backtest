# Stock Screeners

Multiple stock screening strategies, all runnable from `screen/screen_main.py`.

## Quick Start

```bash
# Run all screeners (outputs to screen/screen_result/screen_all_<timestamp>/)
python screen/screen_main.py --screener all

# Run specific screener (outputs to screen/screen_result/)
python screen/screen_main.py --screener stage2
python screen/screen_main.py --screener momentum
python screen/screen_main.py --screener week10_momentum
python screen/screen_main.py --screener oversold

# With custom tickers
python screen/screen_main.py --screener stage2 --tickers AAPL NVDA TSLA

# Screener → Backtest pipeline
python screen/backtest_runner.py --screener momentum --top-k 5
```

## Output Files

Each screener run produces **2 files**:

| File | Format | Content |
|---|---|---|
| `screener_<name>.txt` | Plain text | One passing ticker per line |
| `screener_<name>.xlsx` | Excel | Full results — all tickers, all metrics, sector column |

When running `--screener all`, all outputs are saved to a single session folder:
```
screen/screen_result/screen_all_2026-04-02_16-44/
├── screener_stage2.txt
├── screener_stage2.xlsx
├── screener_momentum.txt
├── screener_momentum.xlsx
├── screener_week10_momentum.txt
├── screener_week10_momentum.xlsx
├── screener_oversold.txt
└── screener_oversold.xlsx
```

## CLI Arguments — `screen/screen_main.py`

| Argument | Type | Default | Description |
|---|---|---|---|
| `--screener`, `-s` | str | `all` | Which screener: `stage2`, `momentum`, `week10_momentum`, `oversold`, `all` |
| `--config`, `-c` | str | None | Path to YAML config file |
| `--no-liquidity` | flag | False | Disable liquidity filter |
| `--no-rs-flag` | flag | False | Disable new high RS flag |
| `--no-correlation` | flag | False | Disable post-screen correlation check |
| `--liquidity-min` | float | 2B | Minimum market cap in dollars |
| `--volume-min` | float | 50M | Minimum avg dollar volume |
| `--rs-threshold` | int | 70 | RS score threshold (0-100) |
| `--tickers` | str[] | None | Custom ticker list |
| `--file` | str | None | Custom tickers file |
| `--check-correlation` | str[] | None | Standalone correlation check |

## Folder Structure

```
screen/
├── screen_main.py           # Entry point — runs all screeners
├── filters.py               # Shared filters (liquidity, ADR, earnings)
├── tickers.py               # US stock ticker fetcher (NASDAQ FTP)
├── correlation.py           # Correlation risk analysis
├── backtest_runner.py       # Screener → Backtest pipeline
├── screen_result/           # Output directory (txt + xlsx files)
└── screener_list/
    ├── __init__.py
    ├── stage2_screener.py   # Minervini Stage 2
    ├── momentum_screener.py # Momentum
    ├── week10_momentum.py   # Week 10% momentum
    └── oversold_screener.py # Spring Trap oversold
```

---

## Screener Modules

### 1. Stage 2 — `screener_list/stage2_screener.py`

Mark Minervini's 8-condition Stage 2 trend template.

**8 Entry Conditions:**
1. Price > 150MA and Price > 200MA
2. 150MA > 200MA
3. 200MA trending UP (slope > 0)
4. 50MA > 150MA and 50MA > 200MA
5. Price > 50MA
6. Price >= 30% above 52-week low
7. Price within 25% of 52-week high
8. Positive 1-year return

#### `run_screener(indices=None, tickers=None, config=None)`

| Param | Type | Default | Description |
|---|---|---|---|
| `indices` | list | `None` | Indices to scan (default: `["all"]`) |
| `tickers` | list | `None` | Custom ticker list |
| `config` | dict | `None` | Configuration dict |

Returns DataFrame with all results.

#### `check_liquidity_from_data(ticker, df, params=None)`

| Param | Type | Default | Description |
|---|---|---|---|
| `ticker` | str | required | Stock symbol |
| `df` | DataFrame | required | Pre-downloaded data |
| `params` | dict | `None` | Override parameters |

Data-driven liquidity check (no API calls). Returns bool.

---

### 2. Momentum — `screener_list/momentum_screener.py`

Screens for stocks with strong price momentum characteristics.

**Signals:** Stocks with momentum_score >= 60 pass. Score based on:
- Price within 85% of 52-week high
- 1-month change >= 5%, 3-month change >= 10%
- RS score >= 70, RS Line > 1.0
- SMA alignment (20 > 50 > 200), EMA13 bullish
- Volume ratio >= 1.0

#### `run_screener(tickers=None, params=None, benchmark_df=None, indices=None, config=None)`

| Param | Type | Default | Description |
|---|---|---|---|
| `tickers` | list | `None` | Custom ticker list |
| `params` | dict | `None` | Override screener parameters |
| `benchmark_df` | DataFrame | `None` | Pre-fetched benchmark |
| `indices` | list | `None` | Indices to scan |
| `config` | dict | `None` | Configuration dict |

Returns DataFrame with columns: `ticker`, `price`, `momentum_score` (0-100), `signal`, `signal_strength`.

#### `calculate_momentum(df, benchmark_df, params)`

| Param | Type | Default | Description |
|---|---|---|---|
| `df` | DataFrame | required | Stock OHLCV data |
| `benchmark_df` | DataFrame | `None` | Benchmark data |
| `params` | dict | required | Screener parameters |

Returns result dict with: `pct_from_52w_high`, `change_1m`, `change_3m`, `rs_line`, `rs_score`, `above_sma20/50/200`, `sma_alignment`, `momentum_score`.

**Default `SCREENER_PARAMS`:**
- `min_price_pct_52w_high`: 0.85
- `min_price_change_1m`: 0.05
- `min_price_change_3m`: 0.10
- `min_rs_score`: 70
- `min_rs_line`: 1.0
- `min_volume_avg`: 500000
- `min_price`: 20.0
- `data_period`: "1y"

---

### 3. Week 10% Momentum — `screener_list/week10_momentum.py`

Screens for stocks with 10% weekly accumulation + momentum.

**7 Conditions (all must pass):**
1. Price >= $15
2. Price > 200-day SMA
3. Price > 50-day SMA
4. Price > 10-day and 21-day SMA
5. 5-day accumulation >= 10%
6. 21-day avg dollar volume >= $50M
7. RS Line > 1.0

#### `run_screener(tickers=None, params=None, benchmark_df=None, indices=None, config=None)`

| Param | Type | Default | Description |
|---|---|---|---|
| `tickers` | list | `None` | Custom ticker list |
| `params` | dict | `None` | Override screener parameters |
| `benchmark_df` | DataFrame | `None` | Pre-fetched benchmark |
| `indices` | list | `None` | Indices to scan |
| `config` | dict | `None` | Config (includes `enable_earnings_filter`) |

Returns DataFrame with `accumulation_5d`, `accumulation_pass`, `momentum_score`, `signal`.

**Default `SCREENER_PARAMS`:**
- `min_price`: 15.0
- `min_volume_avg`: 50000000 ($50M)
- `accumulation_days`: 5
- `accumulation_threshold`: 0.10 (10%)
- `min_rs_score`: 60

---

### 4. Oversold Spring Trap — `screener_list/oversold_screener.py`

Finds high-quality stocks that are temporarily oversold (mean reversion).

**4 Criteria:**
1. Long-term trend intact: Price > 200-day SMA
2. Short-term extreme: RSI(14) < 30 (Wilder's)
3. Below short-term average: Price < 50-day SMA
4. Volume climax: Volume > 1.2x 20-day avg volume + bullish candle

#### CLI Arguments

| Argument | Description |
|---|---|
| `--tickers` | Custom ticker list |
| `--force-refresh` | Ignore cache |
| `--blue-chip-only` | Only mega-cap blue chips (>$200B market cap) |
| `--exclude-blue-chip` | Exclude mega-caps (keep stocks <$100B) |

```bash
# Only blue chips (AAPL, NVDA, META, etc.)
python screen/screener_list/oversold_screener.py --blue-chip-only

# Exclude mega-caps, find mid-cap oversold plays
python screen/screener_list/oversold_screener.py --exclude-blue-chip
```

#### `run_screener(tickers=None)`

| Param | Type | Default | Description |
|---|---|---|---|
| `tickers` | list | `None` | Custom ticker list |

Full pipeline: check regime, download data, screen, enrich with volume. Returns DataFrame.

#### `calc_rsi(series, period=14)`

| Param | Type | Default | Description |
|---|---|---|---|
| `series` | Series | required | Price series |
| `period` | int | `14` | RSI period |

Wilder's RSI calculation. Returns Series.

#### `calc_macd(series, fast=12, slow=26, signal=9)`

| Param | Type | Default | Description |
|---|---|---|---|
| `series` | Series | required | Price series |
| `fast` | int | `12` | Fast EMA |
| `slow` | int | `26` | Slow EMA |
| `signal` | int | `9` | Signal line |

Standard MACD. Returns DataFrame with columns: `MACD`, `Signal`, `Hist`.

#### `check_macd_tick_up(macd_hist)`

| Param | Type | Default | Description |
|---|---|---|---|
| `macd_hist` | Series | required | MACD histogram |

Elder's Tick Up: histogram negative but improving. Returns bool.

#### `check_macd_divergence(price, macd_hist, lookback=20)`

| Param | Type | Default | Description |
|---|---|---|---|
| `price` | Series | required | Price series |
| `macd_hist` | Series | required | MACD histogram |
| `lookback` | int | `20` | Lookback window |

Bullish divergence: price lower low + MACD higher low. Returns bool.

---

## Shared Utilities

### `filters.py`

Core filtering infrastructure used by all screeners.

#### `filter_invalid_tickers(tickers)`

Pre-filters invalid formats (warrants, preferred shares). Returns `(valid, invalid)` tuple.

#### `filter_etf_and_oil(tickers)`

Removes ETFs and oil/energy stocks (~200 excluded). Returns `(valid, excluded)` tuple.

#### `download_all_data(tickers, period="1mo", chunk_size=100, pause=0.5)`

| Param | Type | Default | Description |
|---|---|---|---|
| `tickers` | list | required | Ticker symbols |
| `period` | str | `"1mo"` | yfinance period |
| `chunk_size` | int | `100` | Tickers per request |
| `pause` | float | `0.5` | Seconds between chunks |

Rate-limit-safe bulk download. Returns `{ticker: DataFrame}` dict.

#### `check_liquidity(ticker, params=None)`

Checks market cap (>= $2B), dollar volume (>= $50M), exchange, price (>= $20). Returns `(passes, details)`.

#### `filter_liquidity_batch(tickers, params=None)`

Batch liquidity check (single API call). Returns `{ticker: (passes, details)}`.

#### `check_new_high_rs(ticker, benchmark_symbol="^GSPC", params=None, df=None)`

Checks if RS Line is at a new 252-day high. Returns `(is_new_high, details)`.

#### `check_adr(ticker, params=None, df=None)`

Checks Average Daily Range >= 4%. Returns `(passes, details)`.

#### `check_earnings(ticker, params=None)`

Flags stocks within 7 days before or 1 day after earnings. Returns `(passes, details)`.

#### `filter_by_market_cap(tickers, min_cap_billions=0, max_cap_billions=inf)`

| Param | Type | Default | Description |
|---|---|---|---|
| `tickers` | list | required | Ticker symbols |
| `min_cap_billions` | float | `0` | Minimum market cap in billions |
| `max_cap_billions` | float | `inf` | Maximum market cap in billions |

Multi-threaded market cap filter using `yfinance.fast_info`. Tickers with missing cap data are excluded. Returns filtered list.

```bash
# Only mega-caps >$200B
python screen/screener_list/oversold_screener.py --blue-chip-only

# Exclude mega-caps <$100B
python screen/screener_list/oversold_screener.py --exclude-blue-chip
```

### `tickers.py`

#### `fetch_us_tickers()`

Downloads all US stock tickers from NASDAQ FTP. Returns sorted list.

#### `load_tickers(filepath="tickers.txt")`

Loads tickers from file. Returns list.

#### `update_tickers()`

Fetches fresh tickers and saves. Returns list.

### `correlation.py`

#### `check_correlation_warnings(tickers, threshold=0.7, days=40)`

| Param | Type | Default | Description |
|---|---|---|---|
| `tickers` | list | required | Ticker symbols |
| `threshold` | float | `0.7` | Correlation warning threshold |
| `days` | int | `40` | Lookback period |

Prints warnings for highly correlated pairs (false diversification).

### `backtest_runner.py`

#### `run_screener_get_tickers(screener_name="stage2", use_cache=False, cache_file=None)`

| Param | Type | Default | Description |
|---|---|---|---|
| `screener_name` | str | `"stage2"` | Screener to run |
| `use_cache` | bool | `False` | Use cached results |
| `cache_file` | str | `None` | Specific cache file |

Returns list of passing tickers.

#### `run_backtests(tickers, years=3, initial_capital=100000)`

| Param | Type | Default | Description |
|---|---|---|---|
| `tickers` | list | required | Tickers to backtest |
| `years` | int | `3` | Years of data |
| `initial_capital` | float | `100000` | Starting capital |

Runs VCP backtests on each ticker. Returns list of result dicts.

#### `print_top_results(results, top_k=5)`

Prints top `top_k` most profitable and top `top_k` most drawdown stocks.
