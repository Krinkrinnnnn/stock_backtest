# Market Breadth Chart Explanation

## What It Shows

The Market Breadth chart displays the **percentage of S&P 500 stocks trading above their moving averages** (20, 50, 100, 200-day). This measures overall market health and participation.

## Lines

| Line | Color | Meaning |
|---|---|---|
| **20-Day** | Green | Short-term trend strength |
| **50-Day** | Yellow | Medium-term trend strength (core) |
| **100-Day** | Orange | Intermediate trend strength |
| **200-Day** | Red | Long-term trend strength (bull/bear line) |

**Interpretation:** Higher % = more stocks in uptrend = healthier market.

## Zones

### Overbought (Red Zone)
| Zone | Range | Meaning |
|---|---|---|
| Mild | 70-78% | Elevated, watch for weakness |
| High | 78-85% | Stretched, tighten stops |
| Extreme | 85-95% | Very overextended |
| Blow-off | 95-100% | Near-term top likely |

### Oversold (Green Zone)
| Zone | Range | Meaning |
|---|---|---|
| Mild | 21-33% | Declining, caution |
| High | 14-21% | Heavily sold |
| Extreme | 2-14% | Capitulation zone |
| Panic | 0-2% | Extreme fear, potential bottom |

### Neutral (White Zone)
- **48-52%** — Indecision, no clear trend

## Market Regime Signals

| Regime | Condition | Action |
|---|---|---|
| **EASY_MONEY (BULL)** | 200MA ≥ 50% AND 50MA ≥ 50% | VCP Breakout / Stage 2 Trend (Full Size) |
| **OVERBOUGHT** | 200MA ≥ 50% AND 50MA > 78% | Trailing Stops / Trim Profits / No New Buys |
| **PULLBACK** | 200MA ≥ 50% AND 50MA < 50% | Build Watchlist / Look for VCP Contraction |
| **HARD_MONEY (BEAR)** | 200MA < 50% AND 50MA ≥ 33% | Cash / Mean Reversion / Short Bias |
| **OVERSOLD (PANIC)** | 200MA < 50% AND 50MA < 33% | Mean Reversion / Spring Trap |

## How To Use

1. **Check regime before scanning stocks** — avoid buying in HARD_MONEY regime
2. **In EASY_MONEY** — aggressive screening, look for breakouts
3. **In PULLBACK** — build watchlist, look for VCP setups at support
4. **In OVERSOLD** — look for mean reversion setups, potential bottoms
5. **Above 50MA dropping below 50%** — early warning of trend change
6. **Above 200MA dropping below 50%** — bear market confirmed

## Quick Access (State Persistence)

Other scripts can read the regime instantly (0.001s) without re-downloading:

```python
from market_health.market_regime import load_regime_state

regime = load_regime_state()
print(regime["Regime"])       # OVERSOLD (PANIC)
print(regime["Above_50MA"])   # 20.08
print(regime["Action"])       # Mean Reversion / Spring Trap
```

State is saved to `screen_result/market_regime.json` after each run.

## Data Caching

| File | Purpose | Valid For |
|---|---|---|
| `market_data.parquet` | Price data (503 stocks × 550 days) | 4 hours |
| `market_breadth.parquet` | Breadth calculations | 4 hours |
| `market_regime.json` | Current regime state | 4 hours |
| `sp500_tickers.txt` | S&P 500 ticker list | 24 hours |

**First run:** ~30 seconds (downloads data)
**Subsequent runs:** ~2 seconds (reads from cache)

## Run Command

```bash
cd market_health
python3 market_regime.py
```

## Example Output

```
🧭 Harbor System - Market Navigator
=======================================================
  Current Regime    : OVERSOLD (PANIC)
  Short Trend (50MA): 20.08% stocks above
  Long Trend (200MA): 44.14% stocks above
  Recommended Action: Mean Reversion / Spring Trap (Hard Money)
=======================================================
```

This means the market is heavily sold off. Look for:
- Stocks holding key support levels
- Spring trap patterns (false breakdown then reclaim)
- Wait for breadth to recover before trend-following entries
