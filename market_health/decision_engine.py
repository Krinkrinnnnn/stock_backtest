"""
Decision Engine — Unified Market Regime
========================================
Combines Market Health (0-4 structural) with Risk Appetite Pro (0-4 sentiment)
using a 2x2 matrix to produce a Final Regime + Confidence Score.

Matrix:
  Health >= 3  +  Risk-On  ->  EASY_MONEY_PRO      (confidence 1.0)
  Health >= 3  +  Risk-Off ->  DISTRIBUTION_DANGER  (confidence 0.5)
  Health <= 2  +  Risk-On  ->  ACCUMULATION_PHASE   (confidence 0.3)
  Health <= 2  +  Risk-Off ->  HARD_MONEY_PROTECT   (confidence 0.0)
"""

import os
import json
from datetime import datetime


# ==========================================
# HELPERS
# ==========================================

def score_bar(score: int, max_score: int = 4) -> str:
    """Generate a visual score bar like '██░░'."""
    return "█" * score + "░" * (max_score - score)


def mark(val) -> str:
    """Return checkmark or X based on truthy value."""
    return "✅" if val else "❌"


# ==========================================
# 2x2 DECISION MATRIX
# ==========================================

MATRIX = {
    # (health_on, appetite_on) -> (regime, confidence, action, position_pct)
    (True,  True):  {
        "regime": "EASY_MONEY_PRO",
        "confidence": 1.0,
        "action": "Full Aggression — VCP / Stage 2 Breakouts, Max Position Size",
        "position_pct": 100,
    },
    (True,  False): {
        "regime": "DISTRIBUTION_DANGER",
        "confidence": 0.5,
        "action": "Half Size / Tight Stops — Reduce Winners, Watch for Topping",
        "position_pct": 50,
    },
    (False, True):  {
        "regime": "ACCUMULATION_PHASE",
        "confidence": 0.3,
        "action": "Mean Reversion / Bottom Fishing — Small Pilot Positions Only",
        "position_pct": 30,
    },
    (False, False): {
        "regime": "HARD_MONEY_PROTECT",
        "confidence": 0.0,
        "action": "Cash Only — Preserve Capital, Wait for Confirmation",
        "position_pct": 0,
    },
}

DIVERGENCE_MESSAGES = {
    (False, True): (
        "⚠️  DIVERGENCE: Structure weak ({mh}/4) but sentiment risk-on ({ra}/4)\n"
        "      → Accumulation phase — early recovery signals forming\n"
        "      → Credit spreads tightening before breadth recovers"
    ),
    (True, False): (
        "⚠️  DIVERGENCE: Structure healthy ({mh}/4) but sentiment risk-off ({ra}/4)\n"
        "      → Distribution phase — smart money rotating out quietly\n"
        "      → Breadth holding but credit/growth signals weakening"
    ),
}


# ==========================================
# PREVIOUS REGIME LOADER
# ==========================================

def load_previous_regime(state_path: str) -> dict | None:
    """Load the previous market_regime.json for regime transition comparison."""
    if not os.path.exists(state_path):
        return None
    try:
        with open(state_path, "r") as f:
            return json.load(f)
    except Exception:
        return None


# ==========================================
# CORE DECISION
# ==========================================

def compute_decision(market_health_score: int, risk_appetite_signal: str) -> dict:
    """
    Apply the 2x2 matrix.

    Args:
        market_health_score:  0-4 (structural breadth/vix/net-highs)
        risk_appetite_signal: "Risk-On" or "Risk-Off"

    Returns:
        dict with Final_Regime, Confidence, Action, Position_Pct, and inputs.
    """
    health_on = market_health_score >= 3
    appetite_on = risk_appetite_signal == "Risk-On"

    decision = MATRIX[(health_on, appetite_on)]

    return {
        "Final_Regime": decision["regime"],
        "Confidence": decision["confidence"],
        "Action": decision["action"],
        "Position_Pct": decision["position_pct"],
        "Inputs": {
            "Market_Health_Score": market_health_score,
            "Market_Health_Pass": health_on,
            "Risk_Appetite_Signal": risk_appetite_signal,
            "Risk_Appetite_Pass": appetite_on,
        },
    }


# ==========================================
# PRETTY PRINT — FULL ENHANCED OUTPUT
# ==========================================

def print_decision(
    decision: dict,
    mh_result: dict | None = None,
    ra_result: dict | None = None,
    prev_state_path: str | None = None,
) -> None:
    """
    Pretty-print the unified decision with:
    - Score bars
    - Market Health breakdown
    - Divergence warning (when MH and RA disagree)
    - Regime transition (compared to previous run)
    """
    regime = decision["Final_Regime"]
    conf = decision["Confidence"]
    pos = decision["Position_Pct"]
    action = decision["Action"]
    inputs = decision["Inputs"]

    mh_score = inputs["Market_Health_Score"]
    ra_signal = inputs["Risk_Appetite_Signal"]
    ra_pass = inputs["Risk_Appetite_Pass"]

    # Determine RA score from the signal or ra_result
    ra_score = 0
    if ra_result and "score" in ra_result:
        ra_score = ra_result["score"]
    else:
        ra_score = 4 if ra_pass else 0

    emoji_map = {
        "EASY_MONEY_PRO": "🟢",
        "DISTRIBUTION_DANGER": "🟡",
        "ACCUMULATION_PHASE": "🟠",
        "HARD_MONEY_PROTECT": "🔴",
    }
    emoji = emoji_map.get(regime, "📊")

    mh_bar = score_bar(mh_score)
    ra_bar = score_bar(ra_score)

    # ── Market Health Breakdown ──
    if mh_result:
        mh_regime_str = mh_result.get("Regime", "N/A")
        mh_ind = mh_result.get("Indicator_Scores", {})
        mh_met = mh_result.get("Metrics", {})

        print(f"\n  {'─'*50}")
        print(f"  🏥 MARKET HEALTH (Structural)")
        print(f"  {'─'*50}")
        print(f"  Score: {mh_bar} {mh_score}/4  |  Regime: {mh_regime_str}")
        print(f"  {'─'*50}")

        # Breadth with delta
        b50 = mh_met.get('Breadth_50MA_Pct', 'N/A')
        b200 = mh_met.get('Breadth_200MA_Pct', 'N/A')
        b_delta = ""
        if mh_result.get("prev_breadth_50") is not None:
            try:
                diff = round(float(b50) - float(mh_result["prev_breadth_50"]), 2)
                arrow = "↑" if diff > 0 else ("↓" if diff < 0 else "—")
                prev_date = mh_result.get("prev_breadth_date", "")
                date_str = f" on {prev_date}" if prev_date else ""
                b_delta = f" (prev: {mh_result['prev_breadth_50']}% / {mh_result['prev_breadth_200']}%{date_str} {arrow})"
            except (TypeError, ValueError):
                pass
        print(f"  Breadth (50MA/200MA):  {b50}% / {b200}%  →  {mark(mh_ind.get('Breadth'))} {mh_ind.get('Breadth', 0)}{b_delta}")

        # Net Highs with delta
        nh = mh_met.get('Net_New_Highs', 'N/A')
        nh_delta = ""
        if mh_result.get("prev_net_highs") is not None:
            try:
                diff = int(nh) - int(mh_result["prev_net_highs"])
                arrow = "↑" if diff > 0 else ("↓" if diff < 0 else "—")
                prev_date = mh_result.get("prev_net_date", "")
                date_str = f" on {prev_date}" if prev_date else ""
                nh_delta = f" (prev: {mh_result['prev_net_highs']}{date_str} {arrow})"
            except (TypeError, ValueError):
                pass
        print(f"  Net New Highs:         {nh}  →  {mark(mh_ind.get('Net_Highs'))} {mh_ind.get('Net_Highs', 0)}{nh_delta}")

        # Smart Money with delta
        sm_trend = mh_met.get('Smart_Money_Ratio_Trend', 'N/A')
        sm_delta = ""
        if mh_result.get("prev_ratio") is not None:
            try:
                sm_ratio = mh_result.get("ratio", 0)
                diff = round(float(sm_ratio) - float(mh_result["prev_ratio"]), 4)
                arrow = "↑" if diff > 0 else ("↓" if diff < 0 else "—")
                prev_date = mh_result.get("prev_smart_date", "")
                date_str = f" on {prev_date}" if prev_date else ""
                sm_delta = f" (prev: {mh_result['prev_ratio']}{date_str} {arrow})"
            except (TypeError, ValueError):
                pass
        print(f"  Smart Money (HYG/IEF): {sm_trend}  →  {mark(mh_ind.get('Smart_Money'))} {mh_ind.get('Smart_Money', 0)}{sm_delta}")

        # VIX with delta
        vix_lvl = mh_met.get('VIX_Level', 'N/A')
        vix_delta = ""
        if mh_result.get("prev_vix") is not None:
            try:
                diff = round(float(vix_lvl) - float(mh_result["prev_vix"]), 2)
                arrow = "↑" if diff > 0 else ("↓" if diff < 0 else "—")
                prev_date = mh_result.get("prev_vix_date", "")
                date_str = f" on {prev_date}" if prev_date else ""
                vix_delta = f" (prev: {mh_result['prev_vix']}{date_str} {arrow})"
            except (TypeError, ValueError):
                pass
        print(f"  VIX Level:             {vix_lvl}  →  {mark(mh_ind.get('VIX'))} {mh_ind.get('VIX', 0)}{vix_delta}")

    # ── Unified Decision ──
    print(f"\n{'='*60}")
    print(f"  {emoji} UNIFIED DECISION ENGINE")
    print(f"{'='*60}")
    print(f"  Market Health:    {mh_bar} {mh_score}/4  ({'✅ Pass' if inputs['Market_Health_Pass'] else '❌ Fail'})")
    print(f"  Risk Appetite:    {ra_bar} {ra_score}/4  ({'✅ ' + ra_signal if ra_pass else '❌ ' + ra_signal})")
    print(f"{'─'*60}")

    # ── Divergence Warning ──
    health_on = inputs["Market_Health_Pass"]
    appetite_on = ra_pass
    if health_on != appetite_on:
        div_key = (health_on, appetite_on)
        if div_key in DIVERGENCE_MESSAGES:
            print(f"  {DIVERGENCE_MESSAGES[div_key].format(mh=mh_score, ra=ra_score)}")
            print(f"{'─'*60}")

    print(f"  Final Regime:     {emoji} {regime}")
    print(f"  Confidence:       {conf:.0%}")
    print(f"  Position Size:    {pos}%")
    print(f"  Strategy:         {action}")

    # ── Regime Transition ──
    if prev_state_path:
        prev = load_previous_regime(prev_state_path)
        if prev:
            prev_regime = prev.get("Final_Regime", prev.get("Regime", ""))
            if prev_regime and prev_regime != regime:
                print(f"{'─'*60}")
                print(f"  📈 Regime Change: {emoji_map.get(prev_regime, '❓')} {prev_regime} → {emoji} {regime}")

                # Direction context
                regime_order = ["HARD_MONEY_PROTECT", "ACCUMULATION_PHASE", "DISTRIBUTION_DANGER", "EASY_MONEY_PRO"]
                try:
                    prev_idx = regime_order.index(prev_regime)
                    curr_idx = regime_order.index(regime)
                    if curr_idx > prev_idx:
                        print(f"      → Improving ↑ — conditions getting better")
                    else:
                        print(f"      → Deteriorating ↓ — conditions getting worse")
                except ValueError:
                    pass

                # Show score deltas from previous
                prev_mh = prev.get("Market_Health", {}).get("Score")
                prev_ra = prev.get("Risk_Appetite", {}).get("Score")
                if prev_mh is not None:
                    mh_delta = mh_score - prev_mh
                    mh_arrow = "↑" if mh_delta > 0 else ("↓" if mh_delta < 0 else "—")
                    print(f"      → Market Health: {prev_mh}/4 → {mh_score}/4 ({mh_arrow}{abs(mh_delta)})")
                if prev_ra is not None:
                    ra_delta = ra_score - prev_ra
                    ra_arrow = "↑" if ra_delta > 0 else ("↓" if ra_delta < 0 else "—")
                    print(f"      → Risk Appetite: {prev_ra}/4 → {ra_score}/4 ({ra_arrow}{abs(ra_delta)})")
            elif prev_regime == regime:
                print(f"{'─'*60}")
                print(f"  📈 Regime: Unchanged ({regime})")

    print(f"{'='*60}\n")
