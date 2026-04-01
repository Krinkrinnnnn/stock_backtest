"""
Harbor Market Health — Discord Notifier (Embed Edition)
========================================================
Reads market_regime.json, formats a dual-panel embed with regime-colored
border, attaches the health chart, and sends via Discord webhook.

Usage:
    python notifier.py
    docker compose run --rm harbor-engine python notifier.py
"""

import os
import json
import sys
import requests
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

# ── Paths ────────────────────────────────────────────────────────────────────
ROOT_DIR = Path(__file__).resolve().parent
JSON_PATH = ROOT_DIR / "market_health" / "screen_result" / "market_regime.json"
CHART_PATH = ROOT_DIR / "market_health" / "output" / "market_health.png"

# ── Regime → Discord embed color (decimal) ───────────────────────────────────
REGIME_COLOR = {
    "EASY_MONEY_PRO":       0x00E676,   # Green
    "DISTRIBUTION_DANGER":  0xFFEB3B,   # Yellow
    "ACCUMULATION_PHASE":   0xFF9800,   # Orange
    "HARD_MONEY_PROTECT":   0xFF5252,   # Red
}

REGIME_EMOJI = {
    "EASY_MONEY_PRO":       "🟢",
    "DISTRIBUTION_DANGER":  "🟡",
    "ACCUMULATION_PHASE":   "🟠",
    "HARD_MONEY_PROTECT":   "🔴",
}


def load_env() -> str:
    load_dotenv(ROOT_DIR / ".env")
    url = os.getenv("DISCORD_WEBHOOK_URL", "").strip()
    if not url:
        print("ERROR: DISCORD_WEBHOOK_URL not found.")
        sys.exit(1)
    return url


def load_regime() -> dict:
    if not JSON_PATH.exists():
        print(f"ERROR: {JSON_PATH} not found. Run market_regime.py first.")
        sys.exit(1)
    with open(JSON_PATH, "r") as f:
        return json.load(f)


def mark(val) -> str:
    return "✅" if val else "❌"


def score_bar(score: int, max_score: int = 4) -> str:
    return "█" * score + "░" * (max_score - score)


def fmt_delta(current, prev, prev_date=None, invert=False) -> str:
    """Format a short delta string for Discord embed."""
    if prev is None or current is None:
        return ""
    try:
        diff = float(current) - float(prev)
        if abs(diff) < 0.005:
            return f" `(→ {prev} —)`"
        arrow = "↑" if diff > 0 else "↓"
        if invert:
            arrow = "↓" if diff > 0 else "↑"
        date_str = f" {prev_date}" if prev_date else ""
        return f" `(prev: {prev}{date_str} {arrow})`"
    except (TypeError, ValueError):
        return ""


def build_embed(data: dict) -> dict:
    """Build a Discord embed JSON object with deltas, divergence, regime transition."""
    date = data.get("Date", "N/A")
    final_regime = data.get("Final_Regime", data.get("Regime", "UNKNOWN"))
    confidence = data.get("Confidence", 0)
    position_pct = data.get("Position_Pct", 0)
    action = data.get("Recommended_Action", "N/A")
    emoji = REGIME_EMOJI.get(final_regime, "📊")
    color = REGIME_COLOR.get(final_regime, 0x808080)

    # ── Market Health ──
    mh = data.get("Market_Health", {})
    mh_score = mh.get("Score", data.get("Total_Score", 0))
    mh_ind = mh.get("Indicator_Scores", {})
    mh_met = mh.get("Metrics", {})
    mh_prev = mh.get("Prev_Deltas", {})

    # ── Risk Appetite ──
    ra = data.get("Risk_Appetite", {})
    ra_score = ra.get("Score", 0)
    ra_signal = ra.get("Signal", "N/A")
    ra_ind = ra.get("Indicator_Scores", {})
    ra_met = ra.get("Metrics", {})
    ra_prev = ra.get("Prev_Deltas", {})
    ra_details = ra.get("Details", {})

    # Score bars
    mh_bar = score_bar(mh_score)
    ra_bar = score_bar(ra_score)

    # ── MH deltas ──
    b50 = mh_met.get('Breadth_50MA_Pct', 'N/A')
    b200 = mh_met.get('Breadth_200MA_Pct', 'N/A')
    b_delta = fmt_delta(b50, mh_prev.get("Breadth_50"), mh_prev.get("Breadth_Date"))

    nh = mh_met.get('Net_New_Highs', 'N/A')
    nh_delta = fmt_delta(nh, mh_prev.get("Net_Highs"), mh_prev.get("Net_Date"))

    sm_ratio = mh.get("Metrics", {})
    sm_prev_val = mh_prev.get("Smart_Money_Ratio")
    sm_delta = ""
    if sm_prev_val is not None and ra_details.get("hyg_ief_ratio") is not None:
        sm_delta = fmt_delta(ra_details["hyg_ief_ratio"], sm_prev_val, mh_prev.get("Smart_Date"))

    vix_lvl = mh_met.get('VIX_Level', 'N/A')
    vix_delta = fmt_delta(vix_lvl, mh_prev.get("VIX"), mh_prev.get("VIX_Date"))

    # ── RA deltas ──
    qqq_prev = ra_prev.get("QQQ_XLP_Ratio")
    qqq_curr = ra_details.get("qqq_xlp_ratio")
    qqq_delta = fmt_delta(qqq_curr, qqq_prev) if qqq_curr and qqq_prev else ""

    hyg_prev = ra_prev.get("HYG_IEF_Ratio")
    hyg_curr = ra_details.get("hyg_ief_ratio")
    hyg_delta = fmt_delta(hyg_curr, hyg_prev) if hyg_curr and hyg_prev else ""

    hy_spread = ra_details.get("hy_spread_pct")
    hy_source = ra_details.get("hy_source", "")
    yield_spread = ra_details.get("yield_spread_pct")
    yield_source = ra_details.get("yield_source", "")

    # ── Divergence ──
    mh_pass = mh_score >= 3
    ra_pass = ra_signal == "Risk-On"
    divergence_text = ""
    if mh_pass != ra_pass:
        if not mh_pass and ra_pass:
            divergence_text = (
                f"⚠️ **DIVERGENCE:** Structure weak ({mh_score}/4) but sentiment risk-on ({ra_score}/4)\n"
                f"→ Accumulation phase — early recovery signals forming"
            )
        elif mh_pass and not ra_pass:
            divergence_text = (
                f"⚠️ **DIVERGENCE:** Structure healthy ({mh_score}/4) but sentiment risk-off ({ra_score}/4)\n"
                f"→ Distribution phase — smart money rotating out"
            )

    # ── Regime transition ──
    prev_regime_file = JSON_PATH
    regime_transition = ""
    try:
        # Load the previous JSON (before this run overwrote it, we compare with what the file had)
        # Actually we can't get the old file since it's already overwritten.
        # We'll skip this for Discord embed — the CLI output already shows it.
        pass
    except Exception:
        pass

    # ── Build fields ──
    fields = [
        # ── Decision ──
        {
            "name": "═══ Final Decision ═══",
            "value": (
                f"**Regime:** `{final_regime}`\n"
                f"**Confidence:** `{confidence:.0%}` | **Position:** `{position_pct}%`\n"
                f"**Strategy:** {action}"
            ),
            "inline": False,
        },
    ]

    # Divergence warning (if any)
    if divergence_text:
        fields.append({
            "name": "⚡ Signal Conflict",
            "value": divergence_text,
            "inline": False,
        })

    # ── Panel A ──
    fields.extend([
        {
            "name": f"🦴 Panel A: Market Structure  `{mh_bar}` {mh_score}/4",
            "value": f"**Regime:** {mh_met.get('Regime', mh.get('Regime', 'N/A'))}",
            "inline": False,
        },
        {
            "name": "Breadth (50MA/200MA)",
            "value": f"{mark(mh_ind.get('Breadth'))} {b50}% / {b200}%{b_delta}",
            "inline": True,
        },
        {
            "name": "Net New Highs",
            "value": f"{mark(mh_ind.get('Net_Highs'))} {nh}{nh_delta}",
            "inline": True,
        },
        {
            "name": "Smart Money (HYG/IEF)",
            "value": f"{mark(mh_ind.get('Smart_Money'))} {mh_met.get('Smart_Money_Ratio_Trend', 'N/A')}{sm_delta}",
            "inline": True,
        },
        {
            "name": "VIX",
            "value": f"{mark(mh_ind.get('VIX'))} {vix_lvl}{vix_delta}",
            "inline": True,
        },
    ])

    # ── Panel B ──
    fields.extend([
        {
            "name": "\u200b",  # spacer
            "value": f"🧬 **Panel B: Institutional Sentiment**  `{ra_bar}` {ra_score}/4 | **{ra_signal}**",
            "inline": False,
        },
        {
            "name": "Growth vs Defensive (QQQ/XLP)",
            "value": f"{mark(ra_ind.get('Growth_vs_Defensive'))} {ra_met.get('QQQ_XLP_Trend', 'N/A')}{qqq_delta}",
            "inline": True,
        },
        {
            "name": "Credit Appetite (HYG/IEF)",
            "value": f"{mark(ra_ind.get('Credit_Appetite'))} {ra_met.get('HYG_IEF_Trend', 'N/A')}{hyg_delta}",
            "inline": True,
        },
        {
            "name": "High Yield OAS",
            "value": f"{mark(ra_ind.get('High_Yield_Spread'))} {ra_met.get('HY_OAS_Spread', 'N/A')}",
            "inline": True,
        },
        {
            "name": "Yield Curve (10Y-2Y)",
            "value": f"{mark(ra_ind.get('Yield_Curve'))} {ra_met.get('Yield_Curve_Trend', 'N/A')}",
            "inline": True,
        },
    ])

    embed = {
        "title": f"{emoji} Unified Market Report — {date}",
        "color": color,
        "fields": fields,
        "footer": {
            "text": f"Harbor Engine • {data.get('Timestamp', 'N/A')}",
        },
    }

    return embed


def send_discord(webhook_url: str, embed: dict, chart_path: Path) -> None:
    """Send embed + chart attachment directly via Discord webhook."""
    payload = {
        "embeds": [embed],
    }

    if chart_path.exists():
        print(f"  📎 Attaching chart: {chart_path}")
        with open(chart_path, "rb") as f:
            files = {
                "file": (chart_path.name, f, "image/png"),
            }
            # payload_json must be a string when sending files
            resp = requests.post(
                webhook_url,
                data={"payload_json": json.dumps(payload)},
                files=files,
                timeout=30,
            )
    else:
        print(f"  ⚠️  Chart not found at {chart_path}, sending embed only.")
        resp = requests.post(
            webhook_url,
            json=payload,
            timeout=30,
        )

    if resp.status_code in (200, 204):
        print("  ✅ Notification sent successfully.")
    else:
        print(f"  ❌ Failed: HTTP {resp.status_code} — {resp.text[:200]}")
        sys.exit(1)


def main():
    print("\n📬 Harbor Discord Notifier (Embed)")
    print("-" * 40)

    webhook_url = load_env()
    data = load_regime()
    embed = build_embed(data)

    # Print preview
    mh = data.get("Market_Health", {})
    ra = data.get("Risk_Appetite", {})
    print(f"\n  Regime: {data.get('Final_Regime', 'UNKNOWN')}")
    print(f"  Confidence: {data.get('Confidence', 0):.0%}")
    print(f"  Position: {data.get('Position_Pct', 0)}%")
    print(f"  MH: {mh.get('Score', 0)}/4  {score_bar(mh.get('Score', 0))}")
    print(f"  RA: {ra.get('Score', 0)}/4  {score_bar(ra.get('Score', 0))}  {ra.get('Signal', 'N/A')}")
    print("-" * 40)

    send_discord(webhook_url, embed, CHART_PATH)


if __name__ == "__main__":
    main()
