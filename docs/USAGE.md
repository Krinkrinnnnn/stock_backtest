# Usage Guide - Stock Analysis & Backtesting

## Quick Start

```bash
# Stock analysis (single or multiple symbols)
python main.py --symbol AAPL
python main.py --symbols AAPL TSLA NVDA

# With backtest
python main.py --symbol NVDA --backtest

# Screeners
python screen/screen_main.py --screener all
python screen/screen_main.py --screener momentum --tickers AAPL NVDA

# Market regime
python market_health/market_regime.py
```

## Output

All chart images are saved to a session folder:
```
output/session_AAPL_TSLA_20260402_143000/
├── AAPL_analysis_daily.html
├── AAPL_analysis_weekly.html
├── TSLA_analysis_daily.html
└── TSLA_analysis_weekly.html
```

Screener results (1 txt + 1 xlsx per screener):
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

---

## Daily Development Flow

Copy & paste in order:

```bash
# 1. Pull latest code
git pull

# 2. Check market regime
python market_health/market_regime.py

# 3. Run screeners
python screen/screen_main.py --screener all

# 4. Analyze specific stocks
python main.py --symbols AAPL TSLA NVDA

# 5. Review outputs
ls output/
ls screen/screen_result/

# 6. Stage, commit, push
git add -A && git commit -m "daily update" && git push
```

---

## Stock Analysis

### Analyze Stocks

```bash
# Single stock (default: 2 years, chart)
python main.py --symbol AAPL

# Multiple stocks (all charts saved to one session folder)
python main.py --symbols AAPL TSLA NVDA

# Custom years
python main.py --symbol TSLA --years 3

# Disable chart output
python main.py --symbol NVDA --no-plot
```

### Run Backtest

```bash
# Backtest with default capital ($100k)
python main.py --symbol NVDA --backtest

# Custom capital
python main.py --symbol AAPL --backtest --capital 500000

# Backtest requires at least 3 years of data
python main.py --symbol MSFT --backtest --years 5
```

## Stock Screeners

See [docs/screen_README.md](docs/screen_README.md) for detailed screener instructions.

### Quick Start

```bash
# Run all screeners (outputs to screen/screen_result/screen_all_<timestamp>/)
python screen/screen_main.py --screener all

# Run specific screener
python screen/screen_main.py --screener stage2
python screen/screen_main.py --screener momentum
python screen/screen_main.py --screener week10_momentum
python screen/screen_main.py --screener oversold

# Custom tickers
python screen/screen_main.py --screener momentum --tickers AAPL NVDA TSLA
```

### Output

Each screener produces **1 .txt** (ticker list) and **1 .xlsx** (full data with sector column).

## Common Commands

| Task | Command |
|---|---|
| Analyze stock | `python main.py --symbol AAPL` |
| Analyze multiple | `python main.py --symbols AAPL TSLA NVDA` |
| Analyze + backtest | `python main.py --symbol NVDA --backtest` |
| Run all screeners | `python screen/screen_main.py --screener all` |
| Run one screener | `python screen/screen_main.py --screener momentum` |
| Market regime | `python market_health/market_regime.py` |

## Parameter Reference

### main.py (Analysis)

| Flag | Description | Default |
|---|---|---|
| `--symbol` | Single stock symbol | AAPL |
| `--symbols` | Multiple stock symbols | - |
| `--years` | Years of data | 2 |
| `--no-plot` | Disable chart | False |
| `--backtest` | Run backtest | False |
| `--capital` | Initial capital | 100000 |

### screen_main.py (Screeners)

| Flag | Description | Default |
|---|---|---|
| `--screener`, `-s` | Which screener: `stage2`, `momentum`, `week10_momentum`, `oversold`, `all` | all |
| `--tickers` | Custom ticker list | - |
| `--no-liquidity` | Disable liquidity filter | - |
| `--no-rs-flag` | Disable new high RS | - |
| `--no-correlation` | Disable correlation check | - |
| `--liquidity-min` | Min market cap ($) | 2B |
| `--volume-min` | Min avg volume ($) | 50M |
| `--rs-threshold` | RS score (0-100) | 60-70 |
| `--config` | Config YAML file | - |
