# Market Breadth & Unified Decision Engine

## Overview

The Harbor system uses a **dual-engine architecture** to determine market regime:

| Engine | What It Measures | Score |
|---|---|---|
| **Market Health** | Structural participation (breadth, net highs, smart money, VIX) | 0-4 |
| **Risk Appetite Pro** | Institutional sentiment (QQQ/XLP, HYG/IEF, HY OAS, Yield Curve) | 0-4 |

These two scores feed into a **2×2 Decision Matrix** that produces a Final Regime and Position Size recommendation.

---

## Market Health Indicators (Panel A — Skeleton)

### Breadth (% of S&P 500 Above Moving Average)

| Line | Color | Meaning |
|---|---|---|
| **50-Day (3d EMA smoothed)** | Yellow | Medium-term trend strength |
| **200-Day (3d EMA smoothed)** | Red | Long-term trend strength (bull/bear line) |

**Bullish (+1):** Smoothed 50MA% > 50% **AND** Smoothed 200MA% > 50%

### Breadth Zones

| Zone | 50MA Range | Meaning |
|---|---|---|
| Overbought | > 78% | Stretched, tighten stops |
| Healthy | 50-78% | Bullish participation |
| Neutral | 48-52% | Indecision |
| Weak | 33-48% | Caution |
| Oversold | < 33% | Capitulation, potential bottom |

### Net New Highs vs Lows

**Bullish (+1):** Net Highs > 0 AND Net Highs > 10-day EMA

### Smart Money (HYG/IEF Ratio)

**Bullish (+1):** Current Ratio > 50-day SMA (institutions buying credit risk)

### VIX (Fear Gauge)

**Bullish (+1):** VIX < 20-day SMA AND VIX < 20.0

---

## Risk Appetite Pro (Panel B — Nerve System)

| Indicator | Source | Bullish (+1) |
|---|---|---|
| **Growth vs Defensive (QQQ/XLP)** | yfinance | Ratio > 50-day SMA |
| **Credit Appetite (HYG/IEF)** | yfinance | Ratio > 50-day SMA |
| **High Yield OAS Spread** | FRED `BAMLH0A0HYM2` | Spread < 4.0% |
| **Yield Curve (10Y-2Y)** | FRED `DGS10`, `DGS2` | Spread > 0% |

**FRED fallback chain:** Direct FRED API → yfinance ETF proxies (HYG for OAS, TLT/SHY for curve)

---

## Decision Matrix (2×2)

```
                      Risk-On (RA ≥ 2)      Risk-Off (RA < 2)
                    ┌─────────────────────┬─────────────────────┐
Health ≥ 3         │ 🟢 EASY_MONEY_PRO    │ 🟡 DISTRIBUTION_    │
(Most stocks up)   │    Confidence: 100%  │    DANGER           │
                   │    Position: 100%    │    Confidence: 50%  │
                   │    → VCP Breakouts   │    Position: 50%    │
                   │                      │    → Tight Stops    │
                   ├─────────────────────┼─────────────────────┤
Health ≤ 2         │ 🟠 ACCUMULATION_     │ 🔴 HARD_MONEY_      │
(Most stocks down) │    PHASE             │    PROTECT          │
                   │    Confidence: 30%   │    Confidence: 0%   │
                   │    Position: 30%     │    Position: 0%     │
                   │    → Bottom Fish     │    → Cash Only      │
                   └─────────────────────┴─────────────────────┘
```

---

## Regime Actions

| Regime | Position | Strategy | Screener |
|---|---|---|---|
| 🟢 EASY_MONEY_PRO | 100% | VCP / Stage 2 Breakouts | `stage2_screener.py` |
| 🟡 DISTRIBUTION_DANGER | 50% | Reduce winners, tight stops | `stage2_screener.py` (selective) |
| 🟠 ACCUMULATION_PHASE | 30% | Mean reversion, pilot positions | `oversold_screener.py` |
| 🔴 HARD_MONEY_PROTECT | 0% | Cash only, build watchlist | `oversold_screener.py` (observe) |

---

## JSON Output Structure

```json
{
  "Final_Regime": "EASY_MONEY_PRO",
  "Confidence": 1.0,
  "Position_Pct": 100,
  "Recommended_Action": "Full Aggression — VCP / Stage 2 Breakouts",
  "Market_Health": {
    "Score": 4,
    "Indicator_Scores": { "Breadth": 1, "Net_Highs": 1, "Smart_Money": 1, "VIX": 1 },
    "Metrics": { "Breadth_50MA_Pct": 65.2, "Breadth_200MA_Pct": 72.1, ... }
  },
  "Risk_Appetite": {
    "Score": 3,
    "Signal": "Risk-On",
    "Indicator_Scores": { "Growth_vs_Defensive": 1, "Credit_Appetite": 1, ... },
    "Metrics": { "QQQ_XLP_Trend": "Growth Leading", ... }
  },
  "Regime": "EASY_MONEY_PRO",
  "Total_Score": 4
}
```

---

## Data Freshness

The system validates data freshness at 3 levels:

| Layer | Check | Behavior |
|---|---|---|
| **Cache age** | File modification time < 4 hours | Uses cached parquet |
| **Data date** | Last date in DataFrame vs today (≤ 3 days) | Auto re-download if stale |
| **Force refresh** | `--force-refresh` flag | Bypasses all caches |

### FRED Data Age

FRED series show observation dates in console output:
```
📅 FRED BAMLH0A0HYM2: ✅ 2026-03-28 (fresh)
📅 FRED DGS10: ⚠️ 2026-03-27 (1d old)
```

---

## Quick Access (State Persistence)

Other scripts read the regime instantly (0.001s) without re-downloading:

```python
from market_health.market_regime import load_regime_state

regime = load_regime_state()
print(regime["Final_Regime"])      # EASY_MONEY_PRO
print(regime["Confidence"])        # 1.0
print(regime["Position_Pct"])      # 100
print(regime["Market_Health"]["Score"])  # 4
print(regime["Risk_Appetite"]["Score"])  # 3
```

State is saved to `market_health/screen_result/market_regime.json`.

---

## Data Caching

| File | Purpose | Valid For |
|---|---|---|
| `market_data.parquet` | S&P 500 price data (503 stocks × 550 days) | 4 hours |
| `macro_data.parquet` | HYG, IEF, VIX price data | 4 hours |
| `market_regime.json` | Current regime state | 4 hours |
| `sp500_tickers.txt` | S&P 500 ticker list | 24 hours |

**First run:** ~30 seconds (downloads all data)
**Cached run:** ~2 seconds

---

## Run Commands

```bash
# Full analysis (Health + Risk Appetite + Decision)
python market_health/market_regime.py

# Force fresh download (ignore all caches)
python market_health/market_regime.py --force-refresh

# Send to Discord (with embed + chart)
python notifier.py

# Oversold screener (for ACCUMULATION / HARD_MONEY regimes)
python screen/screen_main.py --screener oversold
```

---

## Example Console Output

```
══════════════════════════════════════════════════════════════
  🏥 HARBOR MARKET HEALTH SCORING SYSTEM
  2026-03-30 09:30:00
══════════════════════════════════════════════════════════════

  [4/7] Calculating Market Health indicators...
  📊 Calculating Market Breadth...
  📊 Calculating Net New Highs vs Lows...
  📊 Calculating Smart Money Flow (HYG/IEF)...
  📊 Calculating Volatility (VIX)...

  [5/7] Calculating Risk Appetite Pro...
  🧬 RISK APPETITE PRO (Institutional Sentiment)
  📊 [1/4] QQQ/XLP Growth vs Defensive...
  📊 [2/4] HYG/IEF Credit Appetite...
  📊 [3/4] High Yield OAS Spread...
  📊 [4/4] Yield Curve 10Y-2Y...
  🧬 RISK APPETITE SCORE: 2 / 4  →  Risk-On

══════════════════════════════════════════════════════════════
  🟢 UNIFIED DECISION ENGINE
══════════════════════════════════════════════════════════════
  Market Health:    3/4  (✅ Pass)
  Risk Appetite:    Risk-On  (✅ Pass)
──────────────────────────────────────────────────────────────
  Final Regime:     🟢 EASY_MONEY_PRO
  Confidence:       100%
  Position Size:    100%
  Strategy:         Full Aggression — VCP / Stage 2 Breakouts
══════════════════════════════════════════════════════════════
```
