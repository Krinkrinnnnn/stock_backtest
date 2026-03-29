# Stock Screeners

A comprehensive stock screening system with multiple strategies for finding winning stocks.

## Overview

This folder contains three stock screeners:

1. **Stage 2** - Mark Minervini's 8-condition Stage 2 trend template
2. **Momentum** - Strong momentum stocks near 52-week highs
3. **Week 10% Momentum** - Stocks with 5-day >=10% accumulation and strong RS

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

## Quick Start

```bash
cd screen

# 1. Update ticker list (run once or daily)
python3 tickers.py

# 2. Run screeners
python3 screen_main.py
```

## Ticker Management

### Fetch Latest US Stock Tickers

```bash
python3 tickers.py
```

This connects to NASDAQ FTP and fetches all US stock symbols (7,000+), excluding ETFs and test issues. Saves to `tickers.txt`.

### Load Tickers from File

```bash
python3 tickers.py --load
```

## Running Screeners

### Using main.py (Recommended)

```bash
# Run all screeners
python3 screen_main.py

# Run specific screener
python3 screen_main.py --screener stage2
python3 screen_main.py --screener momentum
python3 screen_main.py --screener week10_momentum

# With custom parameters
python3 screen_main.py --liquidity-min 5000000000   # $5B min market cap
python3 screen_main.py --volume-min 100000000       # $100M min volume
python3 screen_main.py --rs-threshold 80            # RS score threshold

# Disable filters
python3 screen_main.py --no-liquidity
python3 screen_main.py --no-rs-flag
```

### Using Individual Screeners

```bash
# Stage 2
python3 stage2_screener.py
python3 stage2_screener.py --no-liquidity --no-rs-flag

# Momentum
python3 momentum_screener.py

# Week 10% Momentum
python3 week10_momentum.py
```

## Configuration Options

### Filters

| Flag | Description |
|---|---|
| `--no-liquidity` | Disable liquidity filter (market cap > $2B, vol > $50M) |
| `--no-rs-flag` | Disable "new high RS" flag |

### Parameters

| Flag | Description | Example |
|---|---|---|
| `--liquidity-min` | Min market cap in $ | `5000000000` = $5B |
| `--volume-min` | Min avg volume in $ | `100000000` = $100M |
| `--rs-threshold` | RS score threshold | `80` |

### Config File

Create `config.yaml` for custom settings:

```yaml
screener: all

enable_liquidity_filter: true
enable_new_high_rs: true

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
  min_rs_score: 60
  accumulation_days: 5
  accumulation_threshold: 0.10
  min_volume_avg: 50000000
```

Then run:
```bash
python3 screen_main.py --config config.yaml
```

## Filter Configuration

### Liquidity Filter (Enabled by Default)
- Market Cap > $2B
- 21-day Average Dollar Volume > $50M

### New High RS Flag
- Marks stocks where RS Line is at a new 252-day high

## File Structure

```
screen/
├── screen_main.py           # Central screener runner
├── tickers.py              # Fetch US stock tickers
├── tickers.txt             # US stock ticker list (7,000+)
├── filters.py              # Liquidity & RS filter functions
├── stage2_screener.py      # Stage 2 trend template
├── momentum_screener.py    # Momentum near 52-week high
├── week10_momentum.py      # Week 10% accumulation momentum
└── README.md
```

## Scheduling

### Daily Ticker Update (macOS)

```bash
crontab -e
```

Add line to fetch tickers daily at 6 AM:
```
0 6 * * * /opt/anaconda3/bin/python3 /Users/krin-mac/Documents/Harbor_stock/screen/tickers.py
```

## Troubleshooting

### No tickers found
Run `python3 tickers.py` to fetch the latest ticker list.

### Slow screening
- Screeners process thousands of stocks
- Use `--no-liquidity` to skip market cap checks (faster)
- Use `--rs-threshold 80` for fewer but stronger signals

### Memory issues
The full US market (~7,000 stocks) requires significant memory. Consider:
- Running specific indices: `--index nq100`
- Limiting to top liquid stocks via `--liquidity-min`
