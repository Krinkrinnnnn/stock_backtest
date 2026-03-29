# Harbor Stock Analysis System

A comprehensive stock analysis system with screeners, VCP/RS signal analysis, event-driven backtesting, professional charting, and risk management.

## Features

- **Stock Screeners**: Stage 2 Trend Template, Momentum, Week 10% Momentum
- **VCP + RS Analyzer**: Volatility Contraction Pattern breakout detection with Relative Strength
- **ETF/Oil Filter**: Automatically excludes ETFs and oil/energy stocks
- **Advanced Charts**: Hollow/Solid Candlestick with MAs, volume, RS line, MACD
- **Backtesting Engine**: Event-driven backtesting using Backtrader + QuantStats
- **Risk Management**: Liquidity filtering, correlation checks, position sizing

## Screener Conditions

> **Note:** Only consider stocks with RS Rating > 70

| Screener | # | Condition |
|---|---|---|
| **Stage 2** | 1 | Price > 150MA and Price > 200MA |
| | 2 | 150MA > 200MA |
| | 3 | 200MA trending UP (past 20 days) |
| | 4 | 50MA > 150MA and 50MA > 200MA |
| | 5 | Price > 50MA |
| | 6 | Price >= 30% above 52-week low |
| | 7 | Price within 25% of 52-week high |
| | 8 | Positive 1-year return |
| **Momentum** | 1 | Within 15% of 52-week high |
| | 2 | 1-month change >= 5% |
| | 3 | 3-month change >= 10% |
| | 4 | RS Score >= 70 |
| | 5 | Above SMA 50 and SMA 200 |
| **Week 10% Momentum** | 1 | Price >= $15 |
| | 2 | Price > MA200 (long-term trend) |
| | 3 | Price > MA50 (medium-term trend) |
| | 4 | Price > MA10 and Price > MA21 |
| | 5 | 5-day accumulation >= 10% |
| | 6 | 21-day avg dollar volume >= $50M |
| | 7 | RS Line > 1 (outperforms S&P 500) |

## VCP + RS Analyzer Conditions

| # | Condition |
|---|---|
| 1 | RS Score > 70 |
| 2 | RS Line > 100 (outperforms S&P 500) |
| 3 | Volatility < 12% (20-day high-low range) |
| 4 | Volatility contracting (below MA and < 85% of 10 days ago) |
| 5 | Force Index > 0 (positive momentum) |
| 6 | Breakout: Close >= 20-day high |

## Installation

```bash
pip install pandas numpy matplotlib yfinance backtrader pyyaml quantstats scipy
```

## Quick Start

### 1. Run Stock Screeners

```bash
cd screen

# Update ticker list (run daily)
python3 tickers.py

# Run all screeners
python3 main.py

# Run specific screener
python3 main.py --screener stage2
python3 main.py --screener momentum
python3 main.py --screener week10_momentum
```

### 2. Analyze a Stock (VCP + RS)

```bash
# Basic analysis with chart
python3 main.py --symbol AAPL

# With backtest
python3 main.py --symbol NVDA --backtest --years 3
```

### 3. Backtest Screened Stocks

```bash
# Use cached screener results
python3 screen/backtest_runner.py --use-cache

# Backtest specific file
python3 screen/backtest_runner.py --cache-file screen_result/screener_stage2_2026-03-25.txt
```

## Daily Screener Workflow

```bash
cd screen

# Step 1: Update ticker list (run once daily)
python3 tickers.py

# Step 2: Run Week 10% Momentum screener
python3 week10_momentum.py

# Step 3: Run all standard screeners (Stage 2 + Momentum)
python3 main.py

# Step 4: Correlation check on any list of tickers
python3 main.py --check-correlation NVDA AMD ARM AVGO
```

### Quick Commands

```bash
# All screeners
cd screen && python3 screen_main.py

# Stage 2 only
cd screen && python3 screen_main.py --screener stage2

# Momentum only
cd screen && python3 screen_main.py --screener momentum

# Week 10% Momentum (full scan)
cd screen && python3 week10_momentum.py

# Week 10% Momentum (custom tickers)
cd screen && python3 week10_momentum.py --tickers NVDA AMD ARM TSLA

# Correlation check
cd screen && python3 screen_main.py --check-correlation NVDA AMD ARM AVGO SMCI
```

## Filters

- **Liquidity**: Market cap > $2B, 21-day avg dollar volume > $50M
- **ETF/Oil Filter**: Excludes common ETFs and oil/energy stocks
- **ADR Filter**: Minimum 4% average daily range for momentum stocks
- **Earnings Filter**: Excludes stocks with earnings within 7 days (`--no-earnings` to disable)

## Configuration

Create `config.yaml` in the screen folder:

```yaml
screener: all

enable_liquidity_filter: true

liquidity:
  min_market_cap: 2000000000    # $2B
  min_avg_volume: 50000000      # $50M

stage2:
  cond_6_pct_above_52w_low: 30
  cond_7_within_pct_of_52w_high: 25

momentum:
  min_rs_score: 70
  min_price_pct_52w_high: 0.85

week10_momentum:
  min_price: 15.0
  min_rs_line: 1.0
  accumulation_days: 5
  accumulation_threshold: 0.10
```

Then run:
```bash
python3 main.py --config config.yaml
```

## File Structure

```
Harbor_stock/
├── main.py                    # Stock analysis entry point
├── backtester.py              # Backtrader engine + QuantStats
├── vcp_rs_analyzer.py         # VCP + RS signals (breakout detection)
├── chart_plotter.py           # Advanced 3-Panel Charts
├── fetch_data.py              # Yahoo Finance data
├── positioning/
│   └── position_sizer.py      # Risk-based position sizing
│
├── screen/                    # Stock Screeners
│   ├── screen_main.py         # Screener runner
│   ├── tickers.py             # Fetch US tickers
│   ├── tickers.txt            # 7,000+ US stocks
│   ├── filters.py             # Liquidity, ADR, ETF/Oil filters
│   ├── stage2_screener.py     # Stage 2 Trend Template (8 conditions)
│   ├── momentum_screener.py   # Momentum (5 conditions)
│   ├── week10_momentum.py     # Week 10% Momentum (7 conditions)
│   ├── backtest_runner.py     # Screener + Backtest pipeline
│   └── screen_result/         # Output ticker files
│
└── output/                    # Generated charts
```

## Backtest Strategy Parameters

| Parameter | Default | Description |
|---|---|---|
| Risk Per Trade | 2.0% | Max % equity risk per trade |
| Max Drawdown | 8% | Stop-loss distance |
| Max Position | 40% | Max portfolio allocation |
| Trailing Stop | 10% | Trail from peak |
| Profit Target | 25% | Take profit |
| Max Holding | 60 bars | Maximum holding period |
