"""
Oversold Screener — Spring Trap / Mean Reversion
==================================================
Designed for ACCUMULATION_PHASE or HARD_MONEY_PROTECT regimes.

Finds high-quality stocks that are temporarily oversold:
  1. Long-term trend intact:   Price > 200-day SMA
  2. Short-term extreme:       14-day RSI < 30 (Wilder's)
  3. Below short-term average: Price < 50-day SMA
  4. Volume climax:            Today's Volume > 1.2x 20-day Avg Volume

Usage:
    python screen/oversold_screener.py
    python screen/oversold_screener.py --tickers AAPL NVDA TSLA
    python screen/oversold_screener.py --force-refresh
"""

import yfinance as yf
import pandas as pd
import numpy as np
import os
import sys
import json
import warnings
import time
from datetime import datetime, timedelta
from multiprocessing import Pool, cpu_count

warnings.filterwarnings("ignore")

# ── Paths ────────────────────────────────────────────────────────────────────
SCREEN_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCREEN_DIR, "..", ".."))
RESULT_DIR = os.path.join(PROJECT_ROOT, "screen", "screen_result")
CACHE_PATH = os.path.join(RESULT_DIR, "oversold_data.parquet")
OUTPUT_CSV = os.path.join(RESULT_DIR, "oversold_candidates.csv")
REGIME_JSON = os.path.join(PROJECT_ROOT, "market_health", "screen_result", "market_regime.json")

os.makedirs(RESULT_DIR, exist_ok=True)

CACHE_HOURS = 4
FORCE_REFRESH = False


# ==========================================
# REGIME CHECK
# ==========================================

def check_market_regime():
    """Read market_regime.json and warn if in EASY_MONEY_PRO."""
    if not os.path.exists(REGIME_JSON):
        return None
    try:
        with open(REGIME_JSON, "r") as f:
            data = json.load(f)
        regime = data.get("Final_Regime", data.get("Regime", ""))
        return regime
    except Exception:
        return None


# ==========================================
# TICKER LOADING
# ==========================================

def load_tickers():
    """Load tickers from screen/tickers.txt (preferred) or S&P 500 fallback."""
    # Look in parent directory (screen/) since screener_list is a subdirectory
    screen_parent_dir = os.path.dirname(SCREEN_DIR)
    path = os.path.join(screen_parent_dir, "tickers.txt")
    if os.path.exists(path):
        with open(path, "r") as f:
            tickers = [line.strip() for line in f if line.strip() and not line.startswith("#")]
        tickers = [t for t in tickers if len(t) <= 5 and t.isalpha() or "-" in t]
        return list(dict.fromkeys(tickers))

    # Fallback: S&P 500 from Wikipedia
    print("   Fetching S&P 500 from Wikipedia...")
    try:
        url = 'https://en.wikipedia.org/wiki/List_of_S%26P_500_companies'
        headers = {'User-Agent': 'Mozilla/5.0'}
        table = pd.read_html(url, storage_options=headers)[0]
        tickers = table['Symbol'].tolist()
        tickers = [t.replace('.', '-') for t in tickers]
        return list(dict.fromkeys(tickers))
    except Exception as e:
        print(f"  [X] Failed to load tickers: {e}")
        return []


# ==========================================
# CACHE
# ==========================================

def is_cache_fresh(max_hours=CACHE_HOURS):
    if FORCE_REFRESH or not os.path.exists(CACHE_PATH):
        return False
    mtime = datetime.fromtimestamp(os.path.getmtime(CACHE_PATH))
    return (datetime.now() - mtime) < timedelta(hours=max_hours)


def load_cached_data():
    try:
        return pd.read_parquet(CACHE_PATH)
    except Exception:
        return None


def save_cached_data(df):
    try:
        df.to_parquet(CACHE_PATH)
    except Exception as e:
        print(f"  [!] Cache save failed: {e}")


# ==========================================
# DATA DOWNLOAD (chunked to avoid rate limits)
# ==========================================

def download_data(tickers, period="250d"):
    """Download OHLCV data with caching and chunked requests."""
    if is_cache_fresh():
        cached = load_cached_data()
        if cached is not None and len(cached) > 50:
            # Verify coverage
            if isinstance(cached.columns, pd.MultiIndex):
                cached.columns = cached.columns.get_level_values(0)
            close_cols = [c for c in cached.columns.get_level_values(0) if c in tickers] if isinstance(cached.columns, pd.MultiIndex) else [c for c in cached.columns if c in tickers]
            if len(close_cols) >= len(tickers) * 0.5:
                print(f"  [OK] Cache: {len(cached)} rows, {len(close_cols)} tickers")
                return cached

    print(f"   Downloading {len(tickers)} tickers ({period})...")

    # Chunked download to avoid rate limiting
    chunk_size = 200
    all_chunks = []
    for i in range(0, len(tickers), chunk_size):
        chunk = tickers[i:i + chunk_size]
        chunk_num = i // chunk_size + 1
        total_chunks = (len(tickers) + chunk_size - 1) // chunk_size
        print(f"    Chunk {chunk_num}/{total_chunks} ({len(chunk)} tickers)...")

        try:
            data = yf.download(chunk, period=period, progress=False, group_by="ticker")
            if data is not None and not data.empty:
                all_chunks.append(data)
        except Exception as e:
            print(f"    [!] Chunk {chunk_num} failed: {e}")

        if i + chunk_size < len(tickers):
            time.sleep(1)  # Rate limit pause

    if not all_chunks:
        print("  [X] No data downloaded")
        return pd.DataFrame()

    # Merge chunks — each chunk has columns like (ticker, Close) or just Close
    # We need to extract Close prices into a unified DataFrame
    close_frames = {}
    for chunk_data in all_chunks:
        if isinstance(chunk_data.columns, pd.MultiIndex):
            for ticker in chunk_data.columns.get_level_values(0).unique():
                try:
                    close = chunk_data[(ticker, "Close")]
                    close.name = ticker
                    close_frames[ticker] = close
                except (KeyError, TypeError):
                    pass
        else:
            # Single ticker download
            if "Close" in chunk_data.columns:
                close_frames[list(chunk_data.columns)[0]] = chunk_data["Close"]

    if not close_frames:
        print("  [X] No Close prices found")
        return pd.DataFrame()

    combined = pd.DataFrame(close_frames)
    save_cached_data(combined)
    print(f"  [OK] Downloaded {len(combined)} rows, {len(combined.columns)} tickers")
    return combined


# ==========================================
# RSI CALCULATION (Wilder's Method)
# ==========================================

def calc_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """Standard Wilder's RSI (Robust — handles avg_loss=0)."""
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).fillna(0)
    loss = (-delta.where(delta < 0, 0)).fillna(0)

    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()

    # Avoid division by zero: if avg_loss=0 → rs=NaN → RSI=NaN
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    # If avg_loss was 0 (only gains), RSI should be 100
    rsi = rsi.fillna(100)
    return rsi


# ==========================================
# MACD CALCULATION (Elder's Method)
# ==========================================

def calc_macd(series: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame:
    """
    Calculate standard MACD components.
    
    Returns DataFrame with:
        - MACD_Line: EMA_fast - EMA_slow
        - Signal_Line: EMA of MACD_Line
        - MACD_Hist: MACD_Line - Signal_Line
    """
    ema_fast = series.ewm(span=fast, adjust=False).mean()
    ema_slow = series.ewm(span=slow, adjust=False).mean()
    
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    macd_hist = macd_line - signal_line
    
    return pd.DataFrame({
        "MACD": macd_line,
        "Signal": signal_line,
        "Hist": macd_hist
    })


def check_macd_tick_up(macd_hist: pd.Series) -> bool:
    """Elder's Tick Up: Histogram negative but improving (less negative than yesterday)."""
    if len(macd_hist) < 2:
        return False
    today = float(macd_hist.iloc[-1])
    yesterday = float(macd_hist.iloc[-2])
    return today < 0 and today > yesterday


def check_macd_divergence(price: pd.Series, macd_hist: pd.Series, lookback: int = 20) -> bool:
    """
    Elder's MACD Divergence: 
    Price makes lower low, but MACD Histogram makes higher low (bullish).
    """
    if len(price) < lookback + 5 or len(macd_hist) < lookback + 5:
        return False
    
    # Get recent window
    price_recent = price.iloc[-lookback:]
    hist_recent = macd_hist.iloc[-lookback:]
    
    # Find price low
    price_low_idx = price_recent.idxmin()
    price_low_val = price_recent.loc[price_low_idx]
    
    # Find price low BEFORE the absolute low (earlier swing)
    earlier_mask = price_recent.index < price_low_idx
    if earlier_mask.sum() < 5:
        return False
    
    earlier_price_low_val = price_recent[earlier_mask].min()
    
    # Check if we have a lower low in price
    if price_low_val >= earlier_price_low_val:
        return False  # No lower low in price
    
    # Now check MACD at those points
    hist_at_earlier_low = hist_recent.loc[price_recent[earlier_mask].idxmin()]
    hist_at_recent_low = hist_recent.loc[price_low_idx]
    
    # Bullish divergence: MACD higher at recent low despite price lower
    return hist_at_recent_low > hist_at_earlier_low


# ==========================================
# SINGLE STOCK ANALYSIS
# ==========================================

def analyze_stock(args):
    """
    Analyze one ticker for Spring Trap setup.
    Returns dict if all criteria are met, else None.
    """
    ticker, close_series = args

    try:
        close = close_series.dropna()
        if len(close) < 210:
            return None

        price = float(close.iloc[-1])

        # Moving averages
        ma50 = float(close.rolling(50).mean().iloc[-1])
        ma200 = float(close.rolling(200).mean().iloc[-1])

        # RSI
        rsi_series = calc_rsi(close, 14)
        rsi = float(rsi_series.iloc[-1])

        # MACD Histogram
        macd_df = calc_macd(close)
        macd_hist = macd_df["Hist"]
        macd_hist_now = float(macd_hist.iloc[-1])

        # ── Spring Trap Criteria ──

        # 1. Long-term trend intact
        if price <= ma200:
            return None

        # 2. RSI < 30 (extreme oversold)
        if rsi >= 30:
            return None

        # 3. Below 50MA
        if price >= ma50:
            return None

        # All 3 price-based criteria passed — now add MACD signals
        dist_200ma = round((price / ma200 - 1) * 100, 2)
        dist_50ma = round((price / ma50 - 1) * 100, 2)

        # Build signals list
        signals = []

        # MACD-TickUp: Histogram negative but improving (+1)
        if check_macd_tick_up(macd_hist):
            signals.append("MACD-TickUp")

        # MACD-Divergence: Price lower low, MACD higher low (+2)
        if check_macd_divergence(close, macd_hist):
            signals.append("MACD-Divergence")

        return {
            "ticker": ticker,
            "price": round(price, 2),
            "rsi": round(rsi, 1),
            "macd_hist": round(macd_hist_now, 4),
            "ma50": round(ma50, 2),
            "ma200": round(ma200, 2),
            "dist_200ma_pct": dist_200ma,
            "dist_50ma_pct": dist_50ma,
            "signals": signals,
        }

    except Exception:
        return None


# ==========================================
# VOLUME CLIMAX CHECK (batch)
# ==========================================

def enrich_with_volume(candidates: list[dict]) -> list[dict]:
    """
    Re-download recent data for candidates to get volume,
    then filter for volume climax (> 1.2x 20-day avg).
    """
    if not candidates:
        return []

    tickers = [c["ticker"] for c in candidates]
    print(f"\n   Checking volume for {len(tickers)} candidates...")

    enriched = []
    for ticker in tickers:
        try:
            df = yf.download(ticker, period="30d", progress=False)
            if df is None or df.empty:
                continue

            # Handle MultiIndex columns
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)

            vol = df["Volume"].squeeze()
            avg_vol_20 = float(vol.tail(20).mean())
            vol_today = float(vol.iloc[-1])
            vol_ratio = round(vol_today / avg_vol_20, 2) if avg_vol_20 > 0 else 0

            # Today's candle
            close_today = float(df["Close"].iloc[-1])
            open_today = float(df["Open"].iloc[-1])

            # Condition 1: Volume climax (> 1.2x avg)
            # Condition 2: Bullish candle (Close >= Open) — reject "falling knife"
            if vol_ratio >= 1.2 and close_today >= open_today:
                candidate = next(c for c in candidates if c["ticker"] == ticker)
                candidate["vol_today"] = int(vol_today)
                candidate["vol_avg_20d"] = int(avg_vol_20)
                candidate["vol_ratio"] = vol_ratio
                enriched.append(candidate)
                print(f"    [OK] {ticker}: Vol {vol_ratio}x | Close {close_today:.2f} >= Open {open_today:.2f}")
            else:
                reason = "Volume too low" if vol_ratio < 1.2 else "Bearish candle (Close < Open)"
                print(f"    [X] {ticker}: {reason}")

        except Exception as e:
            print(f"    [!] {ticker}: {e}")

    return enriched


# ==========================================
# MAIN SCREENER
# ==========================================

def run_screener(tickers=None):
    """Run the full oversold Spring Trap screener."""
    print(f"\n{'='*60}")
    print(f"  [SEARCH] OVERSOLD SCREENER — Spring Trap Setup")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}")

    # ── Regime warning ──
    regime = check_market_regime()
    if regime and "EASY_MONEY" in regime.upper():
        print(f"\n  [!]  Market is in {regime}.")
        print(f"      Oversold screener may underperform. VCP breakouts are preferred.\n")

    # ── Load tickers ──
    if tickers is None:
        tickers = load_tickers()
    if not tickers:
        print("  [X] No tickers available")
        return pd.DataFrame()

    print(f"\n  [LIST] {len(tickers)} tickers loaded")

    # ── Download data ──
    close_data = download_data(tickers, period="250d")
    if close_data.empty:
        print("  [X] No data available")
        return pd.DataFrame()

    # ── Parallel analysis (price-based criteria) ──
    print(f"\n  [SEARCH] Screening for Spring Trap (Price > 200MA, RSI < 30, Price < 50MA)...")

    # Build args list: (ticker, series)
    args_list = []
    for ticker in close_data.columns:
        if ticker in tickers:
            args_list.append((ticker, close_data[ticker]))

    workers = max(1, cpu_count() - 1)
    with Pool(workers) as pool:
        results = pool.map(analyze_stock, args_list)

    price_pass = [r for r in results if r is not None]
    print(f"   {len(price_pass)} tickers passed price criteria")

    if not price_pass:
        print("  [X] No Spring Trap candidates found")
        return pd.DataFrame()

    # ── Volume climax filter ──
    final_candidates = enrich_with_volume(price_pass)

    if not final_candidates:
        print("  [X] No candidates passed volume climax filter")
        return pd.DataFrame()

    # ── Sort by RSI (lowest first = most oversold) ──
    final_candidates.sort(key=lambda x: x["rsi"])

    # ── Console output ──
    print(f"\n  {'Ticker':<8} {'Price':>8} {'RSI':>6} {'MACD':>8} {'200MA%':>8} {'50MA%':>8} {'VolRatio':>9} {'Signals'}")
    print(f"  {'─'*8} {'─'*8} {'─'*6} {'─'*8} {'─'*8} {'─'*8} {'─'*9} {'─'*30}")
    for c in final_candidates:
        sigs = " ".join(c.get("signals", [])) if c.get("signals") else ""
        macd_val = c.get("macd_hist", 0)
        print(f"  {c['ticker']:<8} {c['price']:>8.2f} {c['rsi']:>5.1f} {macd_val:>+7.3f} {c['dist_200ma_pct']:>+7.1f}% {c['dist_50ma_pct']:>+7.1f}% {c.get('vol_ratio', 'N/A'):>9} {sigs}")

    # ── Save to CSV ──
    df = pd.DataFrame(final_candidates)
    df.to_csv(OUTPUT_CSV, index=False)
    print(f"\n  [SAVE] Saved {len(df)} candidates to: {OUTPUT_CSV}")

    return df


# ==========================================
# CLI ENTRY POINT
# ==========================================

if __name__ == "__main__":
    import argparse
    sys.path.insert(0, os.path.join(SCREEN_DIR, ".."))
    from filters import filter_by_market_cap

    parser = argparse.ArgumentParser(description="Oversold Screener — Spring Trap")
    parser.add_argument("--tickers", nargs="+", help="Custom tickers to screen")
    parser.add_argument("--force-refresh", action="store_true", help="Ignore cache")
    parser.add_argument("--blue-chip-only", action="store_true",
                        help="Only mega-cap blue chips (>$200B market cap)")
    parser.add_argument("--exclude-blue-chip", action="store_true",
                        help="Exclude mega-caps (keep stocks <$100B)")
    args = parser.parse_args()

    if args.force_refresh:
        FORCE_REFRESH = True
        print("  [REFRESH] Force refresh enabled")

    tickers = args.tickers
    if tickers is None:
        tickers = load_tickers()

    # Apply market cap filter before running screener
    if args.blue_chip_only:
        print("  [BLUE CHIP] Filter: keeping only stocks >$200B market cap")
        tickers = filter_by_market_cap(tickers, min_cap_billions=200)
    elif args.exclude_blue_chip:
        print("  [MID CAP] Filter: keeping stocks <$100B market cap")
        tickers = filter_by_market_cap(tickers, max_cap_billions=100)

    if not tickers:
        print("  [X] No tickers after filtering")
        sys.exit(1)

    run_screener(tickers=tickers)
