"""
Market Health Scoring System (0-4 Points)
==========================================
Calculates 4 indicators to determine market regime and buy confidence.

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

# --- 路徑設定 ---
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
RESULT_DIR = os.path.join(SCRIPT_DIR, "screen_result")
OUTPUT_DIR = os.path.join(SCRIPT_DIR, "output")

os.makedirs(RESULT_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

# --- 快取設定 ---
CACHE_HOURS = 4


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
    """下載 S&P 500 股票數據 (支援快取)"""
    cache_path = os.path.join(RESULT_DIR, "market_data.parquet")

    if is_cache_fresh(cache_path):
        cached = load_cached_data(cache_path)
        if cached is not None and len(cached) > 100:
            if isinstance(cached.columns, pd.MultiIndex):
                cached.columns = cached.columns.get_level_values(0)
            if len(cached.columns) >= len(tickers) * 0.8:
                return cached

    print(f"  📥 Downloading {len(tickers)} stocks ({fetch_days} days)...")
    data = yf.download(tickers, period=f"{fetch_days}d", progress=False)['Close']

    if isinstance(data.columns, pd.MultiIndex):
        data.columns = data.columns.get_level_values(0)

    save_cached_data(data, cache_path)
    return data


def download_macro_data(fetch_days=300):
    """下載宏觀數據: HYG, IEF, VIX"""
    cache_path = os.path.join(RESULT_DIR, "macro_data.parquet")

    if is_cache_fresh(cache_path):
        cached = load_cached_data(cache_path)
        if cached is not None and len(cached) > 50:
            if isinstance(cached.columns, pd.MultiIndex):
                cached.columns = cached.columns.get_level_values(0)
            return cached

    print(f"  📥 Downloading macro data (HYG, IEF, VIX)...")
    symbols = ['HYG', 'IEF', '^VIX']
    data = yf.download(symbols, period=f"{fetch_days}d", progress=False)['Close']

    if isinstance(data.columns, pd.MultiIndex):
        data.columns = data.columns.get_level_values(0)

    # Rename ^VIX to VIX for easier access
    if '^VIX' in data.columns:
        data = data.rename(columns={'^VIX': 'VIX'})

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

    return {
        "score": score,
        "breadth_50": breadth_50,
        "breadth_200": breadth_200,
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

    return {
        "score": score,
        "net_highs": net_highs_val,
        "net_highs_ema": net_highs_ema_val,
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
        return {"score": 0, "ratio": 0, "ratio_sma": 0, "trend": "Unknown"}

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

    return {
        "score": score,
        "ratio": ratio_val,
        "ratio_sma": ratio_sma_val,
        "trend": trend,
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
        return {"score": 0, "vix": 0, "vix_sma": 0}

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

    return {
        "score": score,
        "vix": vix_val,
        "vix_sma": vix_sma_val,
        "vix_df": vix_df
    }


# ==========================================
# SCORING & REGIME MAPPING
# ==========================================

def map_score_to_regime(total_score):
    """將總分映射到市場環境"""
    if total_score == 4:
        return {
            "Regime": "Aggressive Buy (Full Risk-On)",
            "Action": "VCP / Stage 2 Breakouts"
        }
    elif total_score == 3:
        return {
            "Regime": "Selective Buy (Moderate Risk)",
            "Action": "Pullbacks / High RS only"
        }
    elif total_score >= 1:
        return {
            "Regime": "Caution (Whip-saw / Hard Money)",
            "Action": "Mean Reversion / Oversold Screener"
        }
    else:
        return {
            "Regime": "Cash is King (Bear Market)",
            "Action": "Cash / Short Bias"
        }


# ==========================================
# EXPORT TO JSON
# ==========================================

def export_market_regime(result):
    """儲存市場狀態到 JSON"""
    state_path = os.path.join(RESULT_DIR, "market_regime.json")

    state = {
        "Date": datetime.now().strftime("%Y-%m-%d"),
        "Timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "Total_Score": result["Total_Score"],
        "Regime": result["Regime"],
        "Metrics": {
            "Breadth_50MA_Pct": result["Metrics"]["Breadth_50MA_Pct"],
            "Breadth_200MA_Pct": result["Metrics"]["Breadth_200MA_Pct"],
            "Net_New_Highs": result["Metrics"]["Net_New_Highs"],
            "Smart_Money_Ratio_Trend": result["Metrics"]["Smart_Money_Ratio_Trend"],
            "VIX_Level": result["Metrics"]["VIX_Level"]
        },
        "Recommended_Action": result["Recommended_Action"]
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

    # 3. 計算 4 個指標
    print(f"\n  [4/6] Calculating indicators...")

    # Indicator 1: Breadth
    breadth_result = calculate_breadth_score(stock_data)

    # Indicator 2: Net Highs
    net_result = calculate_net_highs_score(stock_data)

    # Indicator 3: Smart Money
    smart_result = calculate_smart_money_score(macro_data)

    # Indicator 4: VIX
    vix_result = calculate_vix_score(macro_data)

    # 4. 計算總分
    total_score = (breadth_result["score"] +
                   net_result["score"] +
                   smart_result["score"] +
                   vix_result["score"])

    regime_info = map_score_to_regime(total_score)

    # 5. 組裝結果
    result = {
        "Total_Score": total_score,
        "Regime": regime_info["Regime"],
        "Recommended_Action": regime_info["Action"],
        "Metrics": {
            "Breadth_50MA_Pct": breadth_result["breadth_50"],
            "Breadth_200MA_Pct": breadth_result["breadth_200"],
            "Net_New_Highs": net_result["net_highs"],
            "Smart_Money_Ratio_Trend": smart_result["trend"],
            "VIX_Level": vix_result["vix"]
        },
        "Indicator_Scores": {
            "Breadth": breadth_result["score"],
            "Net_Highs": net_result["score"],
            "Smart_Money": smart_result["score"],
            "VIX": vix_result["score"]
        }
    }

    # 6. 匯出 JSON
    print(f"\n  [5/6] Exporting to JSON...")
    export_market_regime(result)

    # 7. 繪製圖表
    if not skip_chart:
        print(f"\n  [6/6] Generating chart...")
        plot_market_health(
            breadth_result["breadth_df"],
            net_result["net_df"],
            smart_result["smart_df"],
            vix_result["vix_df"]
        )
    else:
        print(f"\n  [6/6] Chart skipped")

    # 8. 輸出結果
    print(f"\n{'='*60}")
    print(f"  🧭 MARKET HEALTH SCORE: {total_score} / 4")
    print(f"{'='*60}")
    print(f"  Breadth (50MA/200MA):  {breadth_result['breadth_50']}% / {breadth_result['breadth_200']}%  →  {'✅ +1' if breadth_result['score'] else '❌ 0'}")
    print(f"  Net New Highs:         {net_result['net_highs']} (EMA: {net_result['net_highs_ema']})  →  {'✅ +1' if net_result['score'] else '❌ 0'}")
    print(f"  Smart Money (HYG/IEF): {smart_result['trend']}  →  {'✅ +1' if smart_result['score'] else '❌ 0'}")
    print(f"  VIX Level:             {vix_result['vix']} (SMA: {vix_result['vix_sma']})  →  {'✅ +1' if vix_result['score'] else '❌ 0'}")
    print(f"{'='*60}")
    print(f"  📌 Regime: {result['Regime']}")
    print(f"  📌 Action: {result['Recommended_Action']}")
    print(f"{'='*60}\n")

    return result


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Market Health Scoring System")
    parser.add_argument("--skip-chart", action="store_true", help="Skip chart generation")
    args = parser.parse_args()

    run_market_health(skip_chart=args.skip_chart)
