"""
Market Health Scoring System (0-4 Points) + Decision Engine
=============================================================
Calculates 4 structural indicators (breadth, net highs, smart money, VIX),
combines with Risk Appetite Pro (institutional sentiment) via a 2×2 matrix
to produce a unified Final Regime + Confidence Score.

Usage:
    python3 market_regime.py
    python3 market_regime.py --skip-chart    # Skip chart generation
"""

import yfinance as yf
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import os
import json
from datetime import datetime, timedelta
from risk_appetite_pro import calculate_risk_appetite_pro
from decision_engine import compute_decision, print_decision

# --- 路徑設定 ---
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
RESULT_DIR = os.path.join(SCRIPT_DIR, "screen_result")
OUTPUT_DIR = os.path.join(SCRIPT_DIR, "output")

os.makedirs(RESULT_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

# --- 快取設定 ---
CACHE_HOURS = 4
FORCE_REFRESH = False  # Set by --force-refresh flag


# ==========================================
# DATA FRESHNESS VALIDATION
# ==========================================

def is_market_open_today() -> bool:
    """Check if today is a US trading day (weekday, not a major holiday)."""
    today = datetime.now()
    # Weekend
    if today.weekday() >= 5:  # Sat=5, Sun=6
        return False
    # Major US market holidays (month, day) — extend as needed
    HOLIDAYS = [
        (1, 1),   # New Year's
        (1, 20),  # MLK Day (3rd Mon Jan — approximate)
        (2, 17),  # Presidents Day (3rd Mon Feb — approximate)
        (4, 18),  # Good Friday (approximate)
        (5, 26),  # Memorial Day (last Mon May — approximate)
        (7, 4),   # Independence Day
        (9, 1),   # Labor Day (1st Mon Sep — approximate)
        (11, 27), # Thanksgiving (4th Thu Nov — approximate)
        (12, 25), # Christmas
    ]
    if (today.month, today.day) in HOLIDAYS:
        return False
    return True


def get_last_trading_day() -> datetime:
    """Get the most recent trading day (skip weekends/holidays)."""
    d = datetime.now()
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


def validate_data_freshness(df: pd.DataFrame, label: str = "Data", max_age_days: int = 3) -> dict:
    """
    Validate that a DataFrame's last date is recent enough.

    Args:
        df: DataFrame with DatetimeIndex
        label: Name for logging (e.g., "Stock Data", "Macro Data")
        max_age_days: Maximum acceptable age in calendar days

    Returns:
        {"is_fresh": bool, "last_date": str, "age_days": int, "warning": str}
    """
    if df is None or df.empty:
        return {"is_fresh": False, "last_date": "N/A", "age_days": 999, "warning": f"{label}: empty DataFrame"}

    last_date = df.index[-1]
    if hasattr(last_date, 'tz_localize'):
        last_date = last_date.tz_localize(None) if last_date.tz else last_date

    now = datetime.now()
    age = (now - last_date).days if hasattr(last_date, 'year') else 999

    is_fresh = age <= max_age_days
    warning = ""

    if age == 0:
        warning = f"{label}: ✅ Today's data ({last_date.strftime('%Y-%m-%d')})"
    elif age == 1:
        warning = f"{label}: ✅ Yesterday's data ({last_date.strftime('%Y-%m-%d')})"
    elif age <= max_age_days:
        warning = f"{label}: ⚠️ {age} days old ({last_date.strftime('%Y-%m-%d')})"
    else:
        warning = f"{label}: ❌ STALE — {age} days old ({last_date.strftime('%Y-%m-%d')})"

    print(f"  {warning}")

    return {
        "is_fresh": is_fresh,
        "last_date": last_date.strftime("%Y-%m-%d") if hasattr(last_date, 'strftime') else str(last_date),
        "age_days": age,
        "warning": warning,
    }


# ==========================================
# CACHE UTILITIES
# ==========================================

def is_cache_fresh(filepath, max_hours=CACHE_HOURS):
    """檢查快取是否在有效期內"""
    if not os.path.exists(filepath):
        return False
    mtime = datetime.fromtimestamp(os.path.getmtime(filepath))
    return (datetime.now() - mtime) < timedelta(hours=max_hours)


def load_cached_data(filepath):
    """從 parquet 快取載入"""
    try:
        df = pd.read_parquet(filepath)
        print(f"  ✅ Cache: {os.path.basename(filepath)}")
        return df
    except Exception as e:
        print(f"  ⚠️ Cache miss: {e}")
        return None


def save_cached_data(df, filepath):
    """儲存到 parquet 快取"""
    try:
        df.to_parquet(filepath)
    except Exception as e:
        print(f"  ⚠️ Cache save failed: {e}")


# ==========================================
# TICKER MANAGEMENT
# ==========================================

def get_or_load_sp500_tickers():
    """自動從維基百科獲取 S&P 500 清單，失敗則讀本地檔案"""
    filepath = os.path.join(RESULT_DIR, "sp500_tickers.txt")

    # 快取有效期 24 小時
    if is_cache_fresh(filepath, max_hours=24):
        with open(filepath, "r") as f:
            tickers = [line.strip() for line in f if line.strip()]
        tickers = list(dict.fromkeys(tickers))
        print(f"  ✅ S&P 500 cache: {len(tickers)} tickers")
        return tickers

    print("  📥 Fetching S&P 500 from Wikipedia...")
    try:
        url = 'https://en.wikipedia.org/wiki/List_of_S%26P_500_companies'
        headers = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)'}
        table = pd.read_html(url, storage_options=headers)[0]
        tickers = table['Symbol'].tolist()
        tickers = [t.replace('.', '-') for t in tickers]

        with open(filepath, "w") as f:
            for t in tickers:
                f.write(f"{t}\n")
        print(f"  ✅ Updated: {len(tickers)} tickers")
        return tickers
    except Exception as e:
        print(f"  ⚠️ Network failed ({e}), using local file...")
        if os.path.exists(filepath):
            with open(filepath, "r") as f:
                tickers = [line.strip() for line in f if line.strip()]
            return list(dict.fromkeys(tickers))
        return []


# ==========================================
# DATA DOWNLOAD
# ==========================================

def download_stock_data(tickers, fetch_days=550):
    """下載 S&P 500 股票數據 (支援快取 + freshness check)"""
    cache_path = os.path.join(RESULT_DIR, "market_data.parquet")

    if not FORCE_REFRESH and is_cache_fresh(cache_path):
        cached = load_cached_data(cache_path)
        if cached is not None and len(cached) > 100:
            if isinstance(cached.columns, pd.MultiIndex):
                cached.columns = cached.columns.get_level_values(0)
            if len(cached.columns) >= len(tickers) * 0.8:
                freshness = validate_data_freshness(cached, "Stock Cache", max_age_days=3)
                if freshness["is_fresh"]:
                    return cached
                else:
                    print(f"  🔄 Cache stale ({freshness['age_days']}d), re-downloading...")

    print(f"  📥 Downloading {len(tickers)} stocks ({fetch_days} days)...")
    data = yf.download(tickers, period=f"{fetch_days}d", progress=False)['Close']

    if isinstance(data.columns, pd.MultiIndex):
        data.columns = data.columns.get_level_values(0)

    validate_data_freshness(data, "Stock Data", max_age_days=3)
    save_cached_data(data, cache_path)
    return data


def download_macro_data(fetch_days=300):
    """下載宏觀數據: HYG, IEF, VIX (支援快取 + freshness check)"""
    cache_path = os.path.join(RESULT_DIR, "macro_data.parquet")

    if not FORCE_REFRESH and is_cache_fresh(cache_path):
        cached = load_cached_data(cache_path)
        if cached is not None and len(cached) > 50:
            if isinstance(cached.columns, pd.MultiIndex):
                cached.columns = cached.columns.get_level_values(0)
            freshness = validate_data_freshness(cached, "Macro Cache", max_age_days=3)
            if freshness["is_fresh"]:
                return cached
            else:
                print(f"  🔄 Cache stale ({freshness['age_days']}d), re-downloading...")

    print(f"  📥 Downloading macro data (HYG, IEF, VIX)...")
    symbols = ['HYG', 'IEF', '^VIX']
    data = yf.download(symbols, period=f"{fetch_days}d", progress=False)['Close']

    if isinstance(data.columns, pd.MultiIndex):
        data.columns = data.columns.get_level_values(0)

    # Rename ^VIX to VIX for easier access
    if '^VIX' in data.columns:
        data = data.rename(columns={'^VIX': 'VIX'})

    validate_data_freshness(data, "Macro Data", max_age_days=3)
    save_cached_data(data, cache_path)
    return data


# ==========================================
# INDICATOR 1: MARKET BREADTH (Trend)
# ==========================================

def calculate_breadth_score(data, chart_days=250):
    """
    計算市場寬度評分
    - 計算 S&P 500 股票中高於 50MA 和 200MA 的百分比
    - 應用 3-day EMA 平滑
    - Bullish (+1): Smoothed 50MA% > 50% AND Smoothed 200MA% > 50%
    """
    fetch_days = chart_days + 300

    print("  📊 Calculating Market Breadth...")
    breadth_df = pd.DataFrame(index=data.index)

    ma50 = data.rolling(window=50).mean()
    ma200 = data.rolling(window=200).mean()

    total_stocks = data.notna().sum(axis=1)

    # Raw percentages
    breadth_df['Above_50MA'] = ((data > ma50).sum(axis=1) / total_stocks * 100).where(ma50.notna().any(axis=1))
    breadth_df['Above_200MA'] = ((data > ma200).sum(axis=1) / total_stocks * 100).where(ma200.notna().any(axis=1))

    # 3-day EMA smoothing
    breadth_df['Breadth_50MA_Smooth'] = breadth_df['Above_50MA'].ewm(span=3, adjust=False).mean()
    breadth_df['Breadth_200MA_Smooth'] = breadth_df['Above_200MA'].ewm(span=3, adjust=False).mean()

    breadth_df = breadth_df.dropna()

    # Latest values
    latest = breadth_df.iloc[-1]
    breadth_50 = round(float(latest['Breadth_50MA_Smooth']), 2)
    breadth_200 = round(float(latest['Breadth_200MA_Smooth']), 2)

    # Score: +1 if both > 50%
    score = 1 if (breadth_50 > 50 and breadth_200 > 50) else 0

    # Previous day values
    prev_breadth_50 = None
    prev_breadth_200 = None
    prev_breadth_date = None
    if len(breadth_df) >= 2:
        prev_row = breadth_df.iloc[-2]
        prev_breadth_50 = round(float(prev_row['Breadth_50MA_Smooth']), 2)
        prev_breadth_200 = round(float(prev_row['Breadth_200MA_Smooth']), 2)
        prev_idx = breadth_df.index[-2]
        prev_breadth_date = prev_idx.strftime("%Y-%m-%d") if hasattr(prev_idx, 'strftime') else str(prev_idx)

    return {
        "score": score,
        "breadth_50": breadth_50,
        "breadth_200": breadth_200,
        "prev_breadth_50": prev_breadth_50,
        "prev_breadth_200": prev_breadth_200,
        "prev_breadth_date": prev_breadth_date,
        "breadth_df": breadth_df.tail(chart_days)
    }


# ==========================================
# INDICATOR 2: NET NEW HIGHS vs NEW LOWS
# ==========================================

def calculate_net_highs_score(data):
    """
    計算淨新高新低評分
    - 252-day New High: 今日收盤價 = 過去252天最高
    - 252-day New Low: 今日收盤價 = 過去252天最低
    - Net_Highs = Count(New Highs) - Count(New Lows)
    - 應用 10-day EMA
    - Bullish (+1): Net_Highs > 0 AND Net_Highs > 10-day EMA
    """
    print("  📊 Calculating Net New Highs vs Lows...")

    # 252-day rolling high and low
    rolling_high = data.rolling(window=252, min_periods=50).max()
    rolling_low = data.rolling(window=252, min_periods=50).min()

    # New High: current price == 252-day high
    new_highs = (data >= rolling_high * 0.999).sum(axis=1)  # Allow 0.1% tolerance

    # New Low: current price == 252-day low
    new_lows = (data <= rolling_low * 1.001).sum(axis=1)  # Allow 0.1% tolerance

    # Net Highs
    net_highs = new_highs - new_lows

    # 10-day EMA
    net_highs_ema = net_highs.ewm(span=10, adjust=False).mean()

    # Combine
    net_df = pd.DataFrame({
        'New_Highs': new_highs,
        'New_Lows': new_lows,
        'Net_Highs': net_highs,
        'Net_Highs_EMA': net_highs_ema
    }).dropna()

    # Latest values
    latest = net_df.iloc[-1]
    net_highs_val = int(latest['Net_Highs'])
    net_highs_ema_val = round(float(latest['Net_Highs_EMA']), 1)

    # Score: +1 if Net_Highs > 0 AND Net_Highs > EMA
    score = 1 if (net_highs_val > 0 and net_highs_val > net_highs_ema_val) else 0

    # Previous day values
    prev_net_highs = None
    prev_net_date = None
    if len(net_df) >= 2:
        prev_net_highs = int(net_df.iloc[-2]['Net_Highs'])
        prev_idx = net_df.index[-2]
        prev_net_date = prev_idx.strftime("%Y-%m-%d") if hasattr(prev_idx, 'strftime') else str(prev_idx)

    return {
        "score": score,
        "net_highs": net_highs_val,
        "net_highs_ema": net_highs_ema_val,
        "prev_net_highs": prev_net_highs,
        "prev_net_date": prev_net_date,
        "net_df": net_df
    }


# ==========================================
# INDICATOR 3: SMART MONEY FLOW (Risk-On/Off)
# ==========================================

def calculate_smart_money_score(macro_data):
    """
    計算聰明錢評分
    - Ratio = HYG_Close / IEF_Close
    - 50-day SMA of Ratio
    - Bullish (+1): Current Ratio > 50-day SMA (機構買垃圾債 > 安全國債)
    """
    print("  📊 Calculating Smart Money Flow (HYG/IEF)...")

    if 'HYG' not in macro_data.columns or 'IEF' not in macro_data.columns:
        print("  ⚠️ HYG/IEF data not available")
        return {"score": 0, "ratio": 0, "ratio_sma": 0, "trend": "Unknown", "smart_df": pd.DataFrame()}

    # Calculate ratio
    ratio = macro_data['HYG'] / macro_data['IEF']
    ratio_sma = ratio.rolling(window=50).mean()

    smart_df = pd.DataFrame({
        'HYG_IEF_Ratio': ratio,
        'Ratio_SMA50': ratio_sma
    }).dropna()

    # Latest values
    latest = smart_df.iloc[-1]
    ratio_val = round(float(latest['HYG_IEF_Ratio']), 4)
    ratio_sma_val = round(float(latest['Ratio_SMA50']), 4)

    # Score: +1 if ratio > SMA (risk-on)
    score = 1 if ratio_val > ratio_sma_val else 0
    trend = "Bullish (Risk-On)" if score == 1 else "Bearish (Risk-Off)"

    # Previous day values
    prev_ratio = None
    prev_smart_date = None
    if len(smart_df) >= 2:
        prev_ratio = round(float(smart_df.iloc[-2]['HYG_IEF_Ratio']), 4)
        prev_idx = smart_df.index[-2]
        prev_smart_date = prev_idx.strftime("%Y-%m-%d") if hasattr(prev_idx, 'strftime') else str(prev_idx)

    return {
        "score": score,
        "ratio": ratio_val,
        "ratio_sma": ratio_sma_val,
        "trend": trend,
        "prev_ratio": prev_ratio,
        "prev_smart_date": prev_smart_date,
        "smart_df": smart_df
    }


# ==========================================
# INDICATOR 4: VOLATILITY TREND (Fear Gauge)
# ==========================================

def calculate_vix_score(macro_data):
    """
    計算波動率評分
    - VIX 20-day SMA
    - Bullish (+1): VIX < 20-day SMA AND VIX < 20.0
    """
    print("  📊 Calculating Volatility (VIX)...")

    if 'VIX' not in macro_data.columns:
        print("  ⚠️ VIX data not available")
        return {"score": 0, "vix": 0, "vix_sma": 0, "vix_df": pd.DataFrame()}

    vix = macro_data['VIX'].dropna()
    vix_sma = vix.rolling(window=20).mean()

    vix_df = pd.DataFrame({
        'VIX': vix,
        'VIX_SMA20': vix_sma
    }).dropna()

    # Latest values
    latest = vix_df.iloc[-1]
    vix_val = round(float(latest['VIX']), 2)
    vix_sma_val = round(float(latest['VIX_SMA20']), 2)

    # Score: +1 if VIX < SMA AND VIX < 20
    score = 1 if (vix_val < vix_sma_val and vix_val < 20.0) else 0

    # Previous day values
    prev_vix = None
    prev_vix_date = None
    if len(vix_df) >= 2:
        prev_vix = round(float(vix_df.iloc[-2]['VIX']), 2)
        prev_idx = vix_df.index[-2]
        prev_vix_date = prev_idx.strftime("%Y-%m-%d") if hasattr(prev_idx, 'strftime') else str(prev_idx)

    return {
        "score": score,
        "vix": vix_val,
        "vix_sma": vix_sma_val,
        "prev_vix": prev_vix,
        "prev_vix_date": prev_vix_date,
        "vix_df": vix_df
    }


# ==========================================
# SCORING & REGIME MAPPING
# ==========================================

def map_score_to_regime(total_score):
    """將總分映射到市場環境 (out of 4 — structural only)"""
    if total_score == 4:
        return {
            "Regime": "Strong (All Clear)",
            "Action": "Full Risk-On"
        }
    elif total_score == 3:
        return {
            "Regime": "Moderate (Mostly Bullish)",
            "Action": "Selective Buy"
        }
    elif total_score >= 1:
        return {
            "Regime": "Weak (Caution)",
            "Action": "Defensive"
        }
    else:
        return {
            "Regime": "Critical (Bear Market)",
            "Action": "Cash Only"
        }


# ==========================================
# EXPORT TO JSON
# ==========================================

def export_market_regime(mh_result, ra_result, decision):
    """儲存統一市場狀態到 JSON"""
    state_path = os.path.join(RESULT_DIR, "market_regime.json")

    state = {
        "Date": datetime.now().strftime("%Y-%m-%d"),
        "Timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),

        # ── Unified Decision ──
        "Final_Regime": decision["Final_Regime"],
        "Confidence": decision["Confidence"],
        "Position_Pct": decision["Position_Pct"],
        "Recommended_Action": decision["Action"],

        # ── Panel A: Market Health (Structural) ──
        "Market_Health": {
            "Score": mh_result["Total_Score"],
            "Max_Score": 4,
            "Regime": mh_result["Regime"],
            "Indicator_Scores": mh_result["Indicator_Scores"],
            "Metrics": mh_result["Metrics"],
            # Previous day deltas
            "Prev_Deltas": {
                "Breadth_50": mh_result.get("prev_breadth_50"),
                "Breadth_200": mh_result.get("prev_breadth_200"),
                "Breadth_Date": mh_result.get("prev_breadth_date"),
                "Net_Highs": mh_result.get("prev_net_highs"),
                "Net_Date": mh_result.get("prev_net_date"),
                "Smart_Money_Ratio": mh_result.get("prev_ratio"),
                "Smart_Date": mh_result.get("prev_smart_date"),
                "VIX": mh_result.get("prev_vix"),
                "VIX_Date": mh_result.get("prev_vix_date"),
            },
        },

        # ── Panel B: Risk Appetite (Sentiment) ──
        "Risk_Appetite": {
            "Score": ra_result["score"],
            "Max_Score": 4,
            "Signal": ra_result["signal"],
            "Indicator_Scores": ra_result["indicator_scores"],
            "Metrics": ra_result["metrics"],
            # Previous day deltas
            "Prev_Deltas": {
                "QQQ_XLP_Ratio": ra_result.get("details", {}).get("qqq_xlp_prev_ratio"),
                "HYG_IEF_Ratio": ra_result.get("details", {}).get("hyg_ief_prev_ratio"),
            },
            "Details": ra_result.get("details", {}),
        },

        # ── Backwards compat (run_pipeline.py reads these) ──
        "Regime": decision["Final_Regime"],
        "Total_Score": mh_result["Total_Score"],
    }

    with open(state_path, "w") as f:
        json.dump(state, f, indent=2)

    print(f"\n  💾 Saved to: {state_path}")
    return state


def load_regime_state(max_hours=CACHE_HOURS):
    """快速讀取市場狀態 (0.001 秒)"""
    state_path = os.path.join(RESULT_DIR, "market_regime.json")

    if not os.path.exists(state_path):
        return None

    if not is_cache_fresh(state_path, max_hours=max_hours):
        print("  ⚠️ Regime state expired, run market_regime.py")
        return None

    with open(state_path, "r") as f:
        return json.load(f)


# ==========================================
# CHART
# ==========================================

def plot_market_health(breadth_df, net_df, smart_df, vix_df, output_path=None):
    """繪製 4-in-1 市場健康圖表"""
    if output_path is None:
        output_path = os.path.join(OUTPUT_DIR, "market_health.png")

    # Guard: skip if any DataFrame is empty
    empty = []
    if breadth_df is None or breadth_df.empty:
        empty.append("breadth")
    if net_df is None or net_df.empty:
        empty.append("net_highs")
    if smart_df is None or smart_df.empty:
        empty.append("smart_money")
    if vix_df is None or vix_df.empty:
        empty.append("vix")
    if empty:
        print(f"  ⚠️ Chart skipped — empty data: {', '.join(empty)}")
        return

    fig, axes = plt.subplots(4, 1, figsize=(14, 16), facecolor='#131722')

    for ax in axes:
        ax.set_facecolor('#131722')
        ax.tick_params(axis='x', colors='#B2B5BE', labelsize=9)
        ax.tick_params(axis='y', colors='#B2B5BE', labelsize=9)
        ax.grid(color='#2A2E39', linestyle='-', linewidth=0.5, alpha=0.5)
        for spine in ax.spines.values():
            spine.set_color('#2A2E39')

    # Panel 1: Market Breadth
    ax1 = axes[0]
    dates1 = breadth_df.index
    ax1.plot(dates1, breadth_df['Breadth_50MA_Smooth'], color='#FFEB3B', linewidth=2, label='50MA % (3d EMA)')
    ax1.plot(dates1, breadth_df['Breadth_200MA_Smooth'], color='#F44336', linewidth=2, label='200MA % (3d EMA)')
    ax1.axhline(50, color='white', linewidth=1, linestyle='--', alpha=0.4)
    ax1.fill_between(dates1, 50, 100, color='#00E676', alpha=0.05)
    ax1.fill_between(dates1, 0, 50, color='#FF5252', alpha=0.05)
    ax1.set_ylim(0, 100)
    ax1.set_title('1. Market Breadth (% Above MA)', fontsize=12, fontweight='bold', color='white')
    ax1.legend(loc='upper right', frameon=False, labelcolor='white', fontsize=9)

    # Panel 2: Net New Highs
    ax2 = axes[1]
    dates2 = net_df.index
    colors = ['#00E676' if v >= 0 else '#FF5252' for v in net_df['Net_Highs']]
    ax2.bar(dates2, net_df['Net_Highs'], color=colors, alpha=0.6, width=1)
    ax2.plot(dates2, net_df['Net_Highs_EMA'], color='#FFEB3B', linewidth=2, label='10-day EMA')
    ax2.axhline(0, color='white', linewidth=1, linestyle='-', alpha=0.3)
    ax2.set_title('2. Net New Highs vs New Lows', fontsize=12, fontweight='bold', color='white')
    ax2.legend(loc='upper right', frameon=False, labelcolor='white', fontsize=9)

    # Panel 3: Smart Money (HYG/IEF)
    ax3 = axes[2]
    dates3 = smart_df.index
    ax3.plot(dates3, smart_df['HYG_IEF_Ratio'], color='#2196F3', linewidth=1.5, label='HYG/IEF Ratio')
    ax3.plot(dates3, smart_df['Ratio_SMA50'], color='#FF9800', linewidth=2, label='50-day SMA')
    # Fill green when ratio > SMA (risk-on)
    ax3.fill_between(dates3, smart_df['HYG_IEF_Ratio'], smart_df['Ratio_SMA50'],
                     where=smart_df['HYG_IEF_Ratio'] > smart_df['Ratio_SMA50'],
                     color='#00E676', alpha=0.15)
    ax3.fill_between(dates3, smart_df['HYG_IEF_Ratio'], smart_df['Ratio_SMA50'],
                     where=smart_df['HYG_IEF_Ratio'] <= smart_df['Ratio_SMA50'],
                     color='#FF5252', alpha=0.15)
    ax3.set_title('3. Smart Money Flow (HYG/IEF Risk-On/Off)', fontsize=12, fontweight='bold', color='white')
    ax3.legend(loc='upper right', frameon=False, labelcolor='white', fontsize=9)

    # Panel 4: VIX
    ax4 = axes[3]
    dates4 = vix_df.index
    ax4.plot(dates4, vix_df['VIX'], color='#E040FB', linewidth=1.5, label='VIX')
    ax4.plot(dates4, vix_df['VIX_SMA20'], color='#FFEB3B', linewidth=2, label='20-day SMA')
    ax4.axhline(20, color='#FF5252', linewidth=1, linestyle='--', alpha=0.5, label='Threshold (20)')
    ax4.fill_between(dates4, 0, 20, color='#00E676', alpha=0.05)
    ax4.fill_between(dates4, 20, 50, color='#FF5252', alpha=0.05)
    ax4.set_ylim(0, max(50, vix_df['VIX'].max() * 1.2))
    ax4.set_title('4. Volatility (VIX Fear Gauge)', fontsize=12, fontweight='bold', color='white')
    ax4.legend(loc='upper right', frameon=False, labelcolor='white', fontsize=9)

    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    print(f"\n  📊 Chart saved to: {output_path}")
    plt.close()


# ==========================================
# MAIN
# ==========================================

def run_market_health(skip_chart=False):
    """執行完整的市場健康評分系統"""
    print(f"\n{'='*60}")
    print(f"  🏥 HARBOR MARKET HEALTH SCORING SYSTEM")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}")

    # 1. 載入 S&P 500
    print(f"\n  [1/6] Loading S&P 500 tickers...")
    tickers = get_or_load_sp500_tickers()
    if not tickers:
        print("  ❌ No tickers available")
        return None

    # 2. 下載數據
    print(f"\n  [2/6] Downloading stock data...")
    stock_data = download_stock_data(tickers, fetch_days=550)

    print(f"\n  [3/6] Downloading macro data...")
    macro_data = download_macro_data(fetch_days=300)

    # 3. 計算 4 個結構指標
    print(f"\n  [4/7] Calculating Market Health indicators...")

    # Indicator 1: Breadth
    breadth_result = calculate_breadth_score(stock_data)

    # Indicator 2: Net Highs
    net_result = calculate_net_highs_score(stock_data)

    # Indicator 3: Smart Money
    smart_result = calculate_smart_money_score(macro_data)

    # Indicator 4: VIX
    vix_result = calculate_vix_score(macro_data)

    # Market Health total (out of 4)
    mh_score = (breadth_result["score"] +
                net_result["score"] +
                smart_result["score"] +
                vix_result["score"])

    mh_regime = map_score_to_regime(mh_score)

    mh_result = {
        "Total_Score": mh_score,
        "Regime": mh_regime["Regime"],
        "Metrics": {
            "Breadth_50MA_Pct": breadth_result["breadth_50"],
            "Breadth_200MA_Pct": breadth_result["breadth_200"],
            "Net_New_Highs": net_result["net_highs"],
            "Smart_Money_Ratio_Trend": smart_result["trend"],
            "VIX_Level": vix_result["vix"],
        },
        "Indicator_Scores": {
            "Breadth": breadth_result["score"],
            "Net_Highs": net_result["score"],
            "Smart_Money": smart_result["score"],
            "VIX": vix_result["score"],
        },
        # Previous day values for delta comparison
        "prev_breadth_50": breadth_result.get("prev_breadth_50"),
        "prev_breadth_200": breadth_result.get("prev_breadth_200"),
        "prev_breadth_date": breadth_result.get("prev_breadth_date"),
        "prev_net_highs": net_result.get("prev_net_highs"),
        "prev_net_date": net_result.get("prev_net_date"),
        "prev_ratio": smart_result.get("prev_ratio"),
        "prev_smart_date": smart_result.get("prev_smart_date"),
        "ratio": smart_result.get("ratio"),
        "prev_vix": vix_result.get("prev_vix"),
        "prev_vix_date": vix_result.get("prev_vix_date"),
    }

    # 4. 計算 Risk Appetite Pro
    print(f"\n  [5/7] Calculating Risk Appetite Pro...")
    ra_result = calculate_risk_appetite_pro()

    # 5. Unified Decision Engine
    decision = compute_decision(mh_score, ra_result["signal"])

    # Previous state path for regime transition comparison
    state_path = os.path.join(RESULT_DIR, "market_regime.json")
    print_decision(decision, mh_result=mh_result, ra_result=ra_result, prev_state_path=state_path)

    # 6. 匯出 JSON
    print(f"\n  [6/7] Exporting to JSON...")
    export_market_regime(mh_result, ra_result, decision)

    # 7. 繪製圖表
    if not skip_chart:
        print(f"\n  [7/7] Generating chart...")
        plot_market_health(
            breadth_result["breadth_df"],
            net_result["net_df"],
            smart_result["smart_df"],
            vix_result["vix_df"]
        )
    else:
        print(f"\n  [7/7] Chart skipped")

    return {"market_health": mh_result, "risk_appetite": ra_result, "decision": decision}


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Market Health Scoring System")
    parser.add_argument("--skip-chart", action="store_true", help="Skip chart generation")
    parser.add_argument("--force-refresh", action="store_true", help="Ignore cache, re-download all data")
    args = parser.parse_args()

    if args.force_refresh:
        FORCE_REFRESH = True
        print("  🔄 Force refresh: bypassing all caches")

    run_market_health(skip_chart=args.skip_chart)

    # Auto-send to Discord
    print(f"\n  [8/8] Sending Discord notification...")
    import subprocess
    notifier_path = os.path.join(SCRIPT_DIR, "..", "notifier.py")
    try:
        subprocess.run(
            ["python", notifier_path],
            check=False,
            timeout=60,
        )
    except Exception as e:
        print(f"  ⚠️ Notifier failed: {e}")
