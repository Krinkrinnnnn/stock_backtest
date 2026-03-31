# Positioning Module

Portfolio-level risk management: individual position sizing and portfolio-wide diversification guards.

## Files

| File | Purpose |
|---|---|
| `position_sizer.py` | Calculate share count per trade based on risk |
| `portfolio_manager.py` | Filter candidates against sector/correlation limits |
| `__init__.py` | Package init |

---

## 1. Position Sizer — `position_sizer.py`

Calculates optimal trade size based on **Account Risk** and **Trade Risk**.

### Formula

```
1. Risk Amount     = Total Equity x Risk Per Trade % (default: 2%)
2. Risk Per Share  = Entry Price x Stop Loss Distance % (default: 8%)
3. Target Shares   = Risk Amount / Risk Per Share
4. Final Shares    = MIN(Target, Max Position Cap, Available Cash)
```

### `calculate_position_size(...)`

```python
from positioning.position_sizer import calculate_position_size

shares = calculate_position_size(
    total_equity=100_000,
    available_cash=80_000,
    entry_price=150.00,
    risk_per_trade_pct=0.02,          # 2% of equity at risk
    max_drawdown_per_trade_pct=0.08,  # 8% stop loss
    max_position_size_pct=0.40        # 40% max position
)
# Returns: 166
```

| Parameter | Type | Description |
|---|---|---|
| `total_equity` | float | Total portfolio value (cash + positions) |
| `available_cash` | float | Currently available cash |
| `entry_price` | float | Stock price to buy |
| `risk_per_trade_pct` | float | Max % of equity to risk (e.g. 0.02 = 2%) |
| `max_drawdown_per_trade_pct` | float | Stop loss distance (e.g. 0.08 = 8%) |
| `max_position_size_pct` | float | Max % of equity per position (e.g. 0.40 = 40%) |

**Returns:** `int` — Number of shares to buy.

### Three Safety Constraints

| Constraint | Formula | Purpose |
|---|---|---|
| Risk-based | `risk_amount / risk_per_share` | Limits loss to 2% of equity |
| Position cap | `(equity x max_position%) / price` | Prevents over-concentration |
| Cash limit | `available_cash / price` | Prevents over-leveraging |

---

## 2. Portfolio Manager — `portfolio_manager.py`

Filters screener candidates against portfolio-level risk constraints before they enter the portfolio.

### `PortfolioManager` Class

```python
from positioning.portfolio_manager import PortfolioManager

pm = PortfolioManager(
    max_sector_weight=0.25,   # No sector > 25%
    max_corr=0.80,            # No pair correlation > 0.80
    lookback_days=60,         # 60-day price history for correlation
    default_alloc_pct=0.10,   # Assume 10% allocation per candidate
)

approved, rejected = pm.filter_candidates(
    candidates=["NVDA", "AMD", "AVGO", "TSLA", "META"],
    current_portfolio=[
        {"ticker": "AAPL", "weight": 0.20},
        {"ticker": "MSFT", "weight": 0.15},
        {"ticker": "JPM",  "weight": 0.10},
    ]
)
```

#### Constructor Parameters

| Parameter | Type | Default | Description |
|---|---|---|---|
| `max_sector_weight` | float | `0.25` | Max total portfolio weight per sector (25%) |
| `max_corr` | float | `0.80` | Max Pearson correlation with any single holding |
| `lookback_days` | int | `60` | Days of price history for correlation calculation |
| `default_alloc_pct` | float | `0.10` | Assumed allocation % for each new candidate |
| `cache_path` | str | `market_health/screen_result/sector_cache.json` | JSON cache for sector/industry data |

#### `_get_stock_metadata(ticker)`

Fetches sector and industry for a ticker. Uses a local JSON cache to avoid repeated `yfinance .info` calls.

```python
meta = pm._get_stock_metadata("NVDA")
# Returns: {"sector": "Technology", "industry": "Semiconductors"}
```

| Param | Type | Description |
|---|---|---|
| `ticker` | str | Stock symbol |

**Returns:** `dict` with `sector` and `industry` keys (both `str` or `None`).

#### `check_sector_limit(candidate_ticker, current_portfolio, candidate_weight=None)`

Checks if adding a candidate would breach the sector exposure limit.

```python
passes, details = pm.check_sector_limit(
    candidate_ticker="NVDA",
    current_portfolio=[{"ticker": "AAPL", "weight": 0.20}],
    candidate_weight=0.10
)
# passes=False if projected sector weight > 25%
```

| Param | Type | Description |
|---|---|---|
| `candidate_ticker` | str | Ticker to evaluate |
| `current_portfolio` | list[dict] | Current holdings: `[{"ticker": str, "weight": float}]` |
| `candidate_weight` | float | Assumed weight for candidate (default: `default_alloc_pct`) |

**Returns:** `(passes: bool, details: dict)` — details include `sector`, `current_sector_weight`, `projected_weight`, `max_allowed`.

#### `check_correlation(candidate_ticker, current_portfolio_tickers, max_corr=None, lookback_days=None)`

Checks if a candidate is too correlated with any existing holding.

```python
passes, details = pm.check_correlation(
    candidate_ticker="AMD",
    current_portfolio_tickers=["NVDA", "AVGO"],
    max_corr=0.80,
    lookback_days=60
)
# passes=False if Pearson r > 0.80 with any existing ticker
```

| Param | Type | Description |
|---|---|---|
| `candidate_ticker` | str | Ticker to evaluate |
| `current_portfolio_tickers` | list[str] | Tickers currently held |
| `max_corr` | float | Override max correlation threshold |
| `lookback_days` | int | Override lookback period |

**Returns:** `(passes: bool, details: dict)` — details include `max_correlation`, `correlated_with`.

#### `filter_candidates(candidates, current_portfolio, verbose=True)`

Orchestrator: runs both sector and correlation checks on a list of candidates. Approved candidates are added to a simulated portfolio so that sequential checks account for previously approved ones.

```python
approved, rejected = pm.filter_candidates(
    candidates=["NVDA", "AMD", "TSLA", "META", "GOOG"],
    current_portfolio=[{"ticker": "AAPL", "weight": 0.20}],
    verbose=True
)

for a in approved:
    print(a["ticker"])  # TSLA, META, GOOG

for r in rejected:
    print(f"{r['ticker']}: {r['reason']}")
    # NVDA: sector 'Technology' projected 35.0%
    # AMD: sector 'Technology' projected 35.0%
```

| Param | Type | Description |
|---|---|---|
| `candidates` | list[str] | Ticker symbols from screener output |
| `current_portfolio` | list[dict] | Current holdings: `[{"ticker": str, "weight": float}]` |
| `verbose` | bool | Print results to console (default: True) |

**Returns:** `(approved: list[dict], rejected: list[dict])` — each dict has `ticker`, `reason`, `sector_check`, `correlation_check`.

### Example Output

```
======================================================================
  PORTFOLIO RISK FILTER
======================================================================
  Candidates:       5
  Current Holdings: 3
  Sector Max:       25%
  Correlation Max:  0.80
  Lookback:         60 days
  Default Alloc:    10%
======================================================================
  [REJECT] NVDA    Reason: sector 'Technology' projected 45.0%
  [REJECT] AMD     Reason: sector 'Technology' projected 45.0%
  [PASS]   TSLA    Sector: Consumer Cyclical    Projected: 10.0%  MaxCorr: 0.34
  [PASS]   META    Sector: Communication Services  Projected: 10.0%  MaxCorr: 0.41
  [PASS]   GOOG    Sector: Communication Services  Projected: 20.0%  MaxCorr: 0.43
----------------------------------------------------------------------
  Approved: 3  |  Rejected: 2
======================================================================
```

### Sector Cache

Sector and industry data is cached to `market_health/screen_result/sector_cache.json` to avoid repeated API calls. After the first fetch, lookups are instant.

---

## Integration with Decision Engine

The Decision Engine outputs a `Position_Pct` that scales the `max_position_size_pct`:

| Regime | Position_Pct | Effective Max Position |
|---|---|---|
| EASY_MONEY_PRO | 100% | 40% x 1.0 = 40% per position |
| DISTRIBUTION_DANGER | 50% | 40% x 0.5 = 20% per position |
| ACCUMULATION_PHASE | 30% | 40% x 0.3 = 12% per position |
| HARD_MONEY_PROTECT | 0% | Skip — no trades |

### Full Pipeline Usage

```python
from market_health.market_regime import load_regime_state
from positioning.position_sizer import calculate_position_size
from positioning.portfolio_manager import PortfolioManager

# 1. Load market regime
regime = load_regime_state()
position_pct = regime.get("Position_Pct", 0) / 100

if position_pct > 0:
    # 2. Get screener candidates (e.g. from stage2 screener)
    candidates = ["NVDA", "AMD", "AVGO", "TSLA", "META", "GOOG"]

    # 3. Filter against portfolio constraints
    pm = PortfolioManager(max_sector_weight=0.25, max_corr=0.80)
    current = [
        {"ticker": "AAPL", "weight": 0.20},
        {"ticker": "MSFT", "weight": 0.15},
    ]
    approved, rejected = pm.filter_candidates(candidates, current)

    # 4. Calculate position sizes for approved candidates
    adjusted_max = 0.40 * position_pct
    for a in approved:
        shares = calculate_position_size(
            total_equity=100_000,
            available_cash=80_000,
            entry_price=150.00,
            risk_per_trade_pct=0.02 * position_pct,
            max_drawdown_per_trade_pct=0.08,
            max_position_size_pct=adjusted_max
        )
        print(f"Buy {shares} shares of {a['ticker']}")
else:
    print("HARD_MONEY_PROTECT — no trades")
```

---

## Related Modules

| Module | Role |
|---|---|
| `market_health/decision_engine.py` | Outputs `Position_Pct` based on regime |
| `market_health/risk_appetite_pro.py` | Feeds sentiment signal to decision engine |
| `screen/screen_main.py` | Generates candidates with sector enrichment |
| `screen/correlation.py` | Standalone correlation warnings |
| `backtester.py` | Uses position sizing in backtest simulations |

---

*Harbor System — Risk-first position sizing and portfolio diversification.*
