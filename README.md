# Stock Analysis & Backtesting System

A comprehensive stock analysis system equipped with VCP+RS analysis, event-driven backtesting, professional-grade visual charting, and robust risk-management screeners.

## Recent System Upgrades

- **Dynamic Position Sizing Module:** Mathematically sizes trades based on account risk limits (e.g., max 2% total equity risk per trade, max 40% position sizing cap) ensuring risk is always controlled before entry.
- **Correlation Filter Screener:** Automatically scans final screener results to detect and flag "False Diversification" (e.g., holding NVDA & AMD simultaneously when $r > 0.70$), protecting against sector-wide drawdowns.
- **QuantStats HTML Tear Sheets:** Backtests now automatically generate interactive HTML performance reports comparing your strategy against the S&P 500 (SPY), calculating Sortino ratio, max drawdown, and recovery factors.
- **Professional Charting Layout:** Completely overhauled `MarketSmithChart` renderer. Features Hollow Teal/Green and Solid Red Japanese candlesticks, a dedicated MACD oscillator subplot, an RS Score momentum curve, and a volume underlay.
- **ADR Volatility Filter:** Added Average Daily Range (ADR) filter to ensure screeners only pick stocks with sufficient volatility (>4%) required for momentum trading.

## Features

- **VCP Pattern Detection**: Identifies Mark Minervini's Volatility Contraction Pattern
- **Relative Strength Analysis**: Calculates RS line and RS Score percentile vs S&P 500 benchmark
- **Advanced 3-Panel Charts**: Hollow/Solid Candlestick charts with MAs, volume overlays, RS line, and MACD oscillator
- **Backtesting Engine**: Event-driven backtesting using Backtrader + QuantStats
- **Stock Screeners**: Minervini Trend Template, VCP+RS, Momentum strategies
- **Risk Management**: Correlation filtering, ADR minimums, and strict position sizing

## Installation

```bash
pip install pandas numpy matplotlib yfinance backtrader pyyaml quantstats
```

## Quick Start

### 1. Analyze a Stock (Visual Chart Generation)

```bash
# Basic analysis with professional 3-panel chart output
python main.py --symbol AAPL

# Analyze with custom years
python main.py --symbol TSLA --years 3
```

### 2. Run Backtest (QuantStats + Strategy Check)

```bash
# Backtest with default capital ($100k) - outputs PNG chart, Summary TXT, and HTML report
python backtester.py --symbol NVDA --years 3

# Custom capital without generating a plot
python backtester.py --symbol AAPL --capital 500000 --no-plot
```

### 3. Run Stock Screeners

```bash
cd screen

# Update ticker list (run daily)
python tickers.py

# Run all screeners (Includes automatic Correlation Check at the end)
python main.py

# Run specific screener
python main.py --screener minervini
python main.py --screener vcp
python main.py --screener momentum
```

## Screener Usage Examples

```bash
cd screen

# Run with custom parameters
python main.py --liquidity-min 5000000000   # $5B market cap
python main.py --rs-threshold 80
python main.py --no-liquidity               # Disable liquidity filter
python main.py --no-correlation             # Disable the r > 0.7 correlation warning check

# Use specific custom tickers instead of scanning all 7,000+
python main.py --tickers NVDA AMD SMCI ARM --screener momentum
```

## Strategy Parameters

### VCP Strategy (Backtest Risk Management)

Configured inside `VCP_STRATEGY_PARAMS` in `backtester.py`:

| Parameter | Default | Description |
|---|---|---|
| Risk Per Trade | 2.0% | Max % of total equity to risk on a single trade |
| Max Drawdown | 8% | Hard stop-loss distance / max drawdown allowed per trade |
| Max Position Size | 40% | Absolute cap on how much portfolio equity one position can consume |
| Trailing Stop | 10% | Trailing stop from peak |
| Profit Target | 25% | Take profit target |
| Max Holding | 60 bars | Maximum holding period |

### Screeners

| Screener | Key Criteria |
|---|---|
| Minervini | Price > 150MA & 200MA, 200MA trending up, price within 25% of 52w high |
| VCP + RS | RS Score > 60, volatility < 12%, breakout, positive Force Index |
| Momentum | Within 15% of 52w high, 1M change > 5%, RS Score > 70, ADR > 4% |

## File Structure

```
Harbor_stock/
├── main.py                    # Stock analysis entry point
├── backtester.py              # Backtrader engine + QuantStats integration
├── vcp_rs_analyzer.py         # VCP + RS signals
├── chart_plotter.py           # Advanced 3-Panel Charts (Candles, RS, MACD)
├── diagram_indicators.py      # Moving averages
├── positioning/
│   └── position_sizer.py      # Dynamic risk-based sizing mathematics
│
├── screen/                    # Stock Screeners
│   ├── main.py                # Screener runner
│   ├── correlation.py         # False diversification risk checker
│   ├── filters.py             # Liquidity, RS, and ADR filters
│   ├── minervini_screener.py  # Minervini Trend Template
│   ├── vcp_screener.py        # VCP + RS
│   └── momentum_screener.py   # Momentum
│
├── output/                    # Generated Visual Charts (main.py)
└── back_test_result/          # Generated Backtest HTMLs, Summaries, and PNGs
```

## Quick Start

### 1. Analyze a Stock

```bash
# Basic analysis with chart
python3 main.py --symbol AAPL

# With backtest
python3 main.py --symbol NVDA --backtest --years 3
```

### 2. Run Stock Screeners

```bash
cd screen

# Update ticker list (run daily)
python3 tickers.py

# Run all screeners
python3 main.py

# Run specific screener
python3 main.py --screener minervini
python3 main.py --screener vcp
python3 main.py --screener momentum
```

## Usage Examples

### Stock Analysis

```bash
# Analyze Apple with 2 years of data
python3 main.py --symbol AAPL --years 2

# Analyze and save chart
python3 main.py --symbol TSLA --years 2

# Run backtest
python3 main.py --symbol NVDA --backtest --capital 100000
```

### Stock Screeners

```bash
cd screen

# Run with custom parameters
python3 main.py --liquidity-min 5000000000   # $5B market cap
python3 main.py --rs-threshold 80
python3 main.py --no-liquidity              # Disable liquidity filter
python3 main.py --no-rs-flag                 # Disable new high RS flag

# Use config file
python3 main.py --config config.yaml
```

## Strategy Parameters

### VCP Strategy (Backtest)

| Parameter | Default | Description |
|---|---|---|
| EMA Short | 13 | Short-term EMA period |
| EMA Long | 120 | Long-term EMA period |
| SMA | 50 | Trend filter SMA |
| Breakout Period | 20 | N-day high for breakout |
| ATR Period | 20 | Volatility measurement |
| Stop Loss | 7% | Hard stop-loss |
| Trailing Stop | 10% | Trailing stop from peak |
| Profit Target | 25% | Take profit target |
| Max Holding | 60 bars | Maximum holding period |

### Screeners

| Screener | Key Criteria |
|---|---|
| Minervini | Price > 150MA & 200MA, 200MA trending up, price within 25% of 52w high |
| VCP + RS | RS Score > 60, volatility < 12%, breakout, positive Force Index |
| Momentum | Within 15% of 52w high, 1M change > 5%, RS Score > 70 |

## File Structure

```
Stock_python/
├── main.py                    # Stock analysis entry point
├── run_backtest.py            # Backtest runner
├── backtester.py              # Backtrader engine
├── vcp_rs_analyzer.py         # VCP + RS signals
├── chart_plotter.py           # MarketSmith-style charts
├── diagram_indicators.py      # Moving averages
├── fetch_data.py              # Yahoo Finance data
├── enums.py                   # Constants
│
├── screen/                    # Stock Screeners
│   ├── main.py                # Screener runner
│   ├── tickers.py             # Fetch US tickers
│   ├── tickers.txt            # 7,000+ US stocks
│   ├── filters.py             # Liquidity & RS filters
│   ├── minervini_screener.py  # Minervini Trend Template
│   ├── vcp_screener.py        # VCP + RS
│   └── momentum_screener.py  # Momentum
│
└── output/                    # Generated charts
```

## Scheduling

### Daily Ticker Update (macOS)

```bash
crontab -e
```

Add:
```
0 6 * * * /opt/anaconda3/bin/python3 /Users/krin-mac/Documents/Stock_python/screen/tickers.py
```

## Configuration

Create `screen/config.yaml`:

```yaml
screener: all

enable_liquidity_filter: true
enable_new_high_rs: true

liquidity:
  min_market_cap: 2000000000
  min_avg_volume: 50000000

vcp:
  rs_score_threshold: 60
  volatility_max: 0.12

momentum:
  min_rs_score: 70
```
