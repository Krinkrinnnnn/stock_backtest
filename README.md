# Harbor Stock Analysis System

A comprehensive stock analysis system with Minervini & Momentum screeners, event-driven backtesting, professional charting, and risk management.

## Features

- **Stock Screeners**: Minervini Trend Template, Momentum strategies
- **ETF/Oil Filter**: Automatically excludes ETFs and oil/energy stocks
- **Advanced Charts**: Hollow/Solid Candlestick with MAs, volume, RS line, MACD
- **Backtesting Engine**: Event-driven backtesting using Backtrader + QuantStats
- **Risk Management**: Liquidity filtering, correlation checks, position sizing
- **Clean Output**: Screened tickers saved as simple text files for watchlists

## Installation

```bash
pip install pandas numpy matplotlib yfinance backtrader pyyaml quantstats
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
python3 main.py --screener minervini
python3 main.py --screener momentum
```

### 2. Analyze a Stock

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
python3 screen/backtest_runner.py --cache-file screen_result/screener_minervini_2026-03-25.txt
```

## Screener Parameters

| Screener | Key Criteria |
|---|---|
| Minervini | Price > 150MA & 200MA, 200MA trending up, price within 25% of 52w high |
| Momentum | Within 15% of 52w high, 1M change > 5%, RS Score > 70 |
| VCP + RS | RS Score > 60, volatility < 12%, breakout, positive Force Index |
| Week 10% Momentum | Price > 15, Price > MA10/MA21/MA50/MA200, 5d gain >= 10%, RS >= 80, $vol >= $50M |

## Daily Screener Tasks

Copy and run these commands for your daily screening workflow:

```bash
cd C:\Users\williamchung\Documents\offside\Harbor_stock\screen

# Step 1: Update ticker list (run once daily or when needed)
python tickers.py

# Step 2: Run Weekly 10% Momentum screener on ALL stocks in tickers.txt
python "week10%_momentum.py"

# Step 3: Run all standard screeners (Minervini + Momentum + VCP)
python main.py

# Step 4: Standalone correlation check on any list of tickers
python main.py --check-correlation NVDA AMD ARM AVGO
```

### Quick Copy Commands

```bash
# Weekly 10% Momentum (full scan, all 7,000+ stocks)
cd screen && python "week10%_momentum.py"

# Weekly 10% Momentum (custom tickers only)
cd screen && python "week10%_momentum.py" --tickers NVDA AMD ARM TSLA

# All screeners at once
cd screen && python main.py

# Minervini only
cd screen && python main.py --screener minervini

# VCP + RS only
cd screen && python main.py --screener vcp

# Momentum only
cd screen && python main.py --screener momentum

# Correlation check (standalone)
cd screen && python main.py --check-correlation NVDA AMD ARM AVGO SMCI
```

## Filters

- **Liquidity**: Market cap > $2B, 21-day avg volume > $50M
- **ETF/Oil Filter**: Excludes common ETFs and oil/energy stocks
- **ADR Filter**: Minimum 4% average daily range for momentum stocks

## File Structure

```
Harbor_stock/
├── main.py                    # Stock analysis entry point
├── backtester.py              # Backtrader engine + QuantStats
├── vcp_rs_analyzer.py         # VCP + RS signals
├── chart_plotter.py           # Advanced 3-Panel Charts
├── fetch_data.py              # Yahoo Finance data
├── positioning/
│   └── position_sizer.py      # Risk-based position sizing
│
├── screen/                    # Stock Screeners
│   ├── main.py                # Screener runner
│   ├── tickers.py             # Fetch US tickers
│   ├── tickers.txt            # 7,000+ US stocks
│   ├── filters.py             # Liquidity, ADR, ETF/Oil filters
│   ├── minervini_screener.py  # Minervini Trend Template
│   ├── momentum_screener.py   # Momentum
│   ├── week10%_momentum.py    # Weekly 10% Momentum (7 conditions)
│   ├── backtest_runner.py     # Screener + Backtest pipeline
│   └── screen_result/         # Output ticker files
│
└── output/                    # Generated charts
```

## Usage Examples

```bash
cd screen

# Custom parameters
python3 main.py --liquidity-min 5000000000   # $5B market cap
python3 main.py --rs-threshold 80
python3 main.py --no-liquidity

# Custom tickers
python3 main.py --tickers NVDA AMD TSLA --screener momentum
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
