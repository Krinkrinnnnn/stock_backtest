# Usage Guide - Stock Analysis & Backtesting

## Stock Analysis

### Analyze a Single Stock

```bash
# Analyze with default settings (2 years, chart)
python3 main.py --symbol AAPL

# Analyze with custom years
python3 main.py --symbol TSLA --years 3

# Disable chart output
python3 main.py --symbol NVDA --no-plot
```

### Run Backtest

```bash
# Backtest with default capital ($100k)
python3 main.py --symbol NVDA --backtest

# Custom capital
python3 main.py --symbol AAPL --backtest --capital 500000

# Backtest requires at least 3 years of data
python3 main.py --symbol MSFT --backtest --years 5
```

### Standalone Backtest Runner

```bash
python3 run_backtest.py --symbol NVDA --years 3 --capital 100000
```

## Stock Screeners

See [screen/USAGE.md](screen/USAGE.md) for detailed screener instructions.

### Quick Start

```bash
cd screen

# Update ticker list (run once or daily)
python3 tickers.py

# Run all screeners
python3 screen_main.py

# Run specific screener
python3 screen_main.py --screener stage2
python3 screen_main.py --screener momentum
python3 screen_main.py --screener week10_momentum
```

## Common Commands

| Task | Command |
|---|---|
| Analyze stock | `python3 main.py --symbol AAPL` |
| Analyze + backtest | `python3 main.py --symbol NVDA --backtest` |
| Run screeners | `cd screen && python3 screen_main.py` |
| Update tickers | `cd screen && python3 tickers.py` |

## Parameter Reference

### main.py (Analysis)

| Flag | Description | Default |
|---|---|---|
| `--symbol` | Stock symbol | AAPL |
| `--years` | Years of data | 2 |
| `--no-plot` | Disable chart | False |
| `--backtest` | Run backtest | False |
| `--capital` | Initial capital | 100000 |

### screen_main.py (Screeners)

| Flag | Description | Default |
|---|---|---|
| `--screener` | Which screener | all |
| `--no-liquidity` | Disable liquidity filter | - |
| `--no-rs-flag` | Disable new high RS | - |
| `--liquidity-min` | Min market cap ($) | 2B |
| `--volume-min` | Min avg volume ($) | 50M |
| `--rs-threshold` | RS score (0-100) | 60-70 |
| `--config` | Config YAML file | - |
