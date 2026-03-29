"""
Stage 2 Screener
================
Screens all stocks using Mark Minervini's 8-condition Stage 2 trend template.

Architecture:
    Phase 1: Sequential download of all ticker data (single process)
    Phase 2: Parallel technical analysis (all CPU cores)
    Phase 3: Print results

Usage:
    python3 stage2_screener.py
    python3 stage2_screener.py --tickers AAPL NVDA TSLA
"""

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import warnings
import sys
import os
import time
from multiprocessing import Pool, cpu_count

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from filters import (
    LIQUIDITY_PARAMS,
    download_all_data, 
    filter_etf_and_oil
)

warnings.filterwarnings("ignore")

NUM_WORKERS = max(1, cpu_count() - 1)


# ==========================================
# TICKER SOURCES
# ==========================================

def get_all_us_tickers(filename="tickers.txt"):
    """Load all US stock tickers from a specific file."""
    tickers_file = os.path.join(os.path.dirname(__file__), filename)
    if not os.path.exists(tickers_file):
        print(f"Error: {tickers_file} not found. Run tickers.py first.")
        return []
    
    with open(tickers_file, "r") as f:
        return [line.strip() for line in f if line.strip()]


INDEX_MAP = {
    "all": ("All US Stocks", lambda: get_all_us_tickers()),
}


# ==========================================
# LIQUIDITY CHECK (data-driven, no API calls)
# ==========================================

def check_liquidity_from_data(ticker, df, params=None):
    """
    Check if a ticker passes liquidity criteria using pre-downloaded data.
    No API calls - uses the data already downloaded.
    """
    if params is None:
        params = LIQUIDITY_PARAMS
    
    if df is None or df.empty or len(df) < 5:
        return False
    
    try:
        close = df['Close'].dropna()
        volume = df['Volume'].dropna()
        
        if close.empty or volume.empty:
            return False
        
        latest_price = float(close.iloc[-1])
        avg_dollar_vol = float((close.tail(params["volume_period"]) * 
                                volume.tail(params["volume_period"])).mean())
        
        passes_price = latest_price >= params["min_price"]
        passes_volume = avg_dollar_vol >= params["min_avg_volume"]
        
        return passes_price and passes_volume
    except Exception:
        return False


# ==========================================
# PARALLEL WORKER (receives pre-downloaded data)
# ==========================================

def _screen_ticker_with_data(args):
    """
    Screen a single ticker using pre-downloaded data.
    This is called by the multiprocessing pool - no API calls.
    """
    ticker, df, benchmark_df = args
    
    details = {
        "ticker": ticker,
        "price": 0,
        "market_cap": 0,
        "sma50": 0,
        "sma150": 0,
        "sma200": 0,
        "high_52w": 0,
        "low_52w": 0,
        "pct_from_high": 0,
        "pct_from_low": 0,
        "sma200_trending_up": False,
        "rs_line": 0,
        "rs_score": 0,
        "ret_3m": 0,
        "ret_6m": 0,
        "ret_9m": 0,
        "ret_12m": 0,
        "cond_1": False,
        "cond_2": False,
        "cond_3": False,
        "cond_4": False,
        "cond_5": False,
        "cond_6": False,
        "cond_7": False,
        "cond_8": False,
        "score": 0,
        "pass": False,
    }

    try:
        if df is None or len(df) < 200:
            return False, details

        # Handle multi-level columns from yfinance
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        # Use Adj Close if available, otherwise Close
        price_col = 'Adj Close' if 'Adj Close' in df.columns else 'Close'

        # Calculate SMAs
        df['SMA_50'] = df[price_col].rolling(window=50).mean()
        df['SMA_150'] = df[price_col].rolling(window=150).mean()
        df['SMA_200'] = df[price_col].rolling(window=200).mean()

        current_price = float(df[price_col].iloc[-1])
        sma_50 = float(df['SMA_50'].iloc[-1])
        sma_150 = float(df['SMA_150'].iloc[-1])
        sma_200 = float(df['SMA_200'].iloc[-1])

        # 200-day MA trend (check 20 days ago)
        sma_200_past = float(df['SMA_200'].iloc[-20]) if len(df) >= 220 else sma_200

        # 52-week high/low
        df_52w = df.iloc[-252:]
        high_52w = float(df_52w[price_col].max())
        low_52w = float(df_52w[price_col].min())

        # Fill details
        details["price"] = current_price
        details["sma50"] = sma_50
        details["sma150"] = sma_150
        details["sma200"] = sma_200
        details["high_52w"] = high_52w
        details["low_52w"] = low_52w
        details["pct_from_high"] = (current_price / high_52w - 1) * 100
        details["pct_from_low"] = (current_price / low_52w - 1) * 100
        details["sma200_trending_up"] = sma_200 > sma_200_past

        # RS Line vs benchmark
        if benchmark_df is not None and not benchmark_df.empty:
            aligned_bench = benchmark_df.reindex(df.index, method='ffill')
            if not aligned_bench.empty:
                base_stock = float(df[price_col].iloc[0])
                base_bench = float(aligned_bench['Close'].iloc[0])
                if base_bench > 0:
                    rs_line = (df[price_col] / base_stock) / (aligned_bench['Close'] / base_bench)
                    details["rs_line"] = float(rs_line.iloc[-1])

        # Calculate weighted RS score (for percentile ranking later)
        if len(df) >= 252:
            now = current_price
            ret_3m = (now / float(df[price_col].iloc[-63])) - 1 if len(df) >= 63 else 0
            ret_6m = (now / float(df[price_col].iloc[-126])) - 1 if len(df) >= 126 else 0
            ret_9m = (now / float(df[price_col].iloc[-189])) - 1 if len(df) >= 189 else 0
            ret_12m = (now / float(df[price_col].iloc[-252])) - 1
            
            details["ret_3m"] = ret_3m
            details["ret_6m"] = ret_6m
            details["ret_9m"] = ret_9m
            details["ret_12m"] = ret_12m
            details["rs_score"] = (ret_3m * 2) + ret_6m + ret_9m + ret_12m

        # --- 8 Condition Checks ---
        details["cond_1"] = current_price > sma_150 and current_price > sma_200
        details["cond_2"] = sma_150 > sma_200
        details["cond_3"] = sma_200 > sma_200_past
        details["cond_4"] = sma_50 > sma_150 and sma_50 > sma_200
        details["cond_5"] = current_price > sma_50
        details["cond_6"] = current_price >= (low_52w * 1.30)
        details["cond_7"] = current_price >= (high_52w * 0.75)

        if len(df) >= 252:
            stock_return = (current_price / float(df[price_col].iloc[-252]) - 1) * 100
            details["cond_8"] = stock_return > 0
        else:
            details["cond_8"] = True

        # Score
        conditions = [
            details["cond_1"], details["cond_2"], details["cond_3"],
            details["cond_4"], details["cond_5"], details["cond_6"],
            details["cond_7"], details["cond_8"]
        ]
        details["score"] = sum(conditions)
        details["pass"] = all(conditions)

        return details["pass"], details

    except Exception:
        return False, details


def _screen_batch_with_data(batch):
    """Process a batch of (ticker, df, benchmark_df) tuples."""
    return [_screen_ticker_with_data(args) for args in batch]


# ==========================================
# SCREENER RUNNER
# ==========================================

def run_screener(indices=None, tickers=None, config=None):
    """
    Run Stage 2 screener.
    
    Architecture:
        1. Download all data sequentially (single process)
        2. Filter for liquidity using downloaded data
        3. Run technical analysis in parallel (all CPUs)
    """
    if config is None:
        config = {
            "enable_liquidity_filter": True,
        }
    
    enable_liquidity = config.get("enable_liquidity_filter", True)
    
    if indices is None:
        indices = ["all"]

    # Collect all tickers
    all_tickers = []
    index_names = []

    if tickers:
        all_tickers = [t.upper() for t in tickers]
        index_names = ["Custom"]
    else:
        for idx in indices:
            if idx == "all":
                tickers_file = config.get("tickers_file", "tickers.txt")
                idx_tickers = get_all_us_tickers(tickers_file)
                all_tickers.extend(idx_tickers)
                index_names.append(f"File ({tickers_file})")
            elif idx in INDEX_MAP:
                name, getter = INDEX_MAP[idx]
                idx_tickers = getter()
                all_tickers.extend(idx_tickers)
                index_names.append(name)

    # Deduplicate
    all_tickers = list(dict.fromkeys(all_tickers))
    
    # Filter out ETFs and oil/energy stocks
    all_tickers, excluded_tickers = filter_etf_and_oil(all_tickers)
    if excluded_tickers:
        print(f"\n  Excluded {len(excluded_tickers)} ETFs/oil-energy stocks: {', '.join(excluded_tickers[:10])}{'...' if len(excluded_tickers) > 10 else ''}")

    print(f"\n{'='*90}")
    print(f"  STAGE 2 SCREENER")
    
    if config and config.get("tickers_file"):
        print(f"  Tickers File: {config['tickers_file']}")
    else:
        print(f"  Indices: {', '.join(index_names)}")
        
    print(f"  Total stocks to scan: {len(all_tickers)}")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*90}")

    print(f"\n  Filters:")
    print(f"    Liquidity Filter: {'ON' if enable_liquidity else 'OFF'} (Market Cap > $2B, Vol > $50M)")
    
    print(f"\n  Conditions:")
    print(f"    1. Price > 150MA and Price > 200MA")
    print(f"    2. 150MA > 200MA")
    print(f"    3. 200MA trending UP (past 20 days)")
    print(f"    4. 50MA > 150MA and 50MA > 200MA")
    print(f"    5. Price > 50MA")
    print(f"    6. Price >= 30% above 52-week low")
    print(f"    7. Price within 25% of 52-week high")
    print(f"    8. Positive 1-year return")

    # ==========================================
    # PHASE 1: Download all data sequentially
    # ==========================================
    # Minervini needs ~2 years of data for SMA200 calculations
    print(f"\n  [Phase 1] Downloading data sequentially (2y period)...")
    all_data = download_all_data(all_tickers, period="2y", chunk_size=100, pause=0.5)
    
    # ==========================================
    # PHASE 2: Filter for liquidity (no API calls)
    # ==========================================
    liquid_tickers = set()
    if enable_liquidity:
        print(f"\n  [Phase 2] Filtering for liquidity (using downloaded data)...")
        for ticker, df in all_data.items():
            if check_liquidity_from_data(ticker, df):
                liquid_tickers.add(ticker)
        print(f"    Liquid stocks: {len(liquid_tickers)}/{len(all_data)}")
    else:
        liquid_tickers = set(all_data.keys())
    
    if not liquid_tickers:
        print(f"\n  No liquid stocks found. Check data download above.")
        return pd.DataFrame()

    # ==========================================
    # PHASE 3: Fetch benchmark + parallel analysis
    # ==========================================
    print(f"\n  [Phase 3] Fetching S&P 500 benchmark data...")
    benchmark_df = None
    try:
        benchmark_df = yf.download("^GSPC", period="2y", progress=False)
        if isinstance(benchmark_df.columns, pd.MultiIndex):
            benchmark_df.columns = benchmark_df.columns.get_level_values(0)
        benchmark_df.columns = [col.capitalize() for col in benchmark_df.columns]
    except Exception:
        benchmark_df = None

    print(f"\n  [Phase 4] Running Stage 2 screening with {NUM_WORKERS} workers...")
    liquid_list = list(liquid_tickers)
    
    # Prepare (ticker, df, benchmark_df) tuples for workers
    worker_data = [(t, all_data[t], benchmark_df) for t in liquid_list if t in all_data]
    
    batch_size = max(1, len(worker_data) // NUM_WORKERS)
    batches = [worker_data[i:i + batch_size] for i in range(0, len(worker_data), batch_size)]
    
    print(f"    Split into {len(batches)} batches...")
    
    passing = []
    near_passing = []
    all_results = []
    
    with Pool(NUM_WORKERS) as pool:
        for batch_idx, batch_results in enumerate(pool.imap_unordered(_screen_batch_with_data, batches)):
            for passed, details in batch_results:
                details["liquidity_pass"] = True
                all_results.append(details)
                
                if passed:
                    passing.append(details)
                elif details.get("score", 0) >= 6:
                    near_passing.append(details)
            
            print(f"    Batch {batch_idx + 1}/{len(batches)} completed", end="", flush=True)
    
    print(f"\n    Processed {len(all_results)} stocks")

    # Calculate RS Rating (percentile ranking 0-99)
    valid_results = [d for d in all_results if d["price"] > 0 and d["rs_score"] != 0]
    if valid_results:
        scores = [d["rs_score"] for d in valid_results]
        for d in valid_results:
            # Calculate percentile rank
            rank = sum(1 for s in scores if s < d["rs_score"])
            d["rs_rating"] = int((rank / len(scores)) * 99)
    else:
        for d in all_results:
            d["rs_rating"] = 0

    print(f"\n\n  Screening complete: {len(all_results)} stocks analyzed")

    # Print results
    def format_market_cap(cap):
        if cap >= 1_000_000_000_000:
            return f"${cap/1_000_000_000_000:.2f}T"
        elif cap >= 1_000_000_000:
            return f"${cap/1_000_000_000:.2f}B"
        elif cap >= 1_000_000:
            return f"${cap/1_000_000:.2f}M"
        else:
            return "$0"
    
    print(f"\n  * Only consider RS Rating > 70")
    print(f"\n  {'Ticker':<7} {'Price':>8} {'MktCap':>10} {'SMA50':>8} {'SMA200':>8} "
          f"{'52wHi%':>7} {'RS':>4} {'Score':>5} {'Pass':>5}")
    print(f"  {'-'*7} {'-'*8} {'-'*10} {'-'*8} {'-'*8} {'-'*7} "
          f"{'-'*4} {'-'*5} {'-'*5}")

    for d in sorted(all_results, key=lambda x: x["score"], reverse=True):
        if d["price"] == 0:
            continue
        print(f"  {d['ticker']:<7} ${d['price']:>6.2f} {format_market_cap(d.get('market_cap', 0)):>10} "
              f"${d['sma50']:>6.2f} ${d['sma200']:>6.2f} "
              f"{d['pct_from_high']:>+6.1f}% "
              f"{d['rs_rating']:>4} {d['score']:>5}/8 {' PASS' if d['pass'] else '   --':>5}")

    # Print passing stocks
    if passing:
        print(f"\n  {'='*80}")
        print(f"  [+] STAGE 2 — PASS ({len(passing)} stocks)")
        print(f"  {'='*80}")
        for d in passing:
            mkt_cap = format_market_cap(d.get("market_cap", 0))
            print(f"  * {d['ticker']:<6} ${d['price']:>7.2f}  {mkt_cap:>9}  "
                  f"52wHi:{d['pct_from_high']:+.1f}%  RS:{d['rs_rating']}")
    else:
        print(f"\n  No stocks passed all 8 conditions.")

    if near_passing:
        print(f"\n  [!] Near-Passing (6-7/8 conditions):")
        for d in sorted(near_passing, key=lambda x: x["score"], reverse=True)[:20]:
            mkt_cap = format_market_cap(d.get("market_cap", 0))
            print(f"    {d['ticker']:<6} ${d['price']:>7.2f}  {mkt_cap:>9}  Score:{d['score']}/8")

    print(f"\n{'='*90}\n")

    return pd.DataFrame(all_results)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Stage 2 Screener")
    parser.add_argument("--index", nargs="+", choices=["nq100", "sp500", "russell2000", "all"],
                        help="Indices to scan")
    parser.add_argument("--tickers", nargs="+", help="Custom ticker list")
    parser.add_argument("--no-liquidity", action="store_true", help="Disable liquidity filter")
    args = parser.parse_args()

    config = {
        "enable_liquidity_filter": not args.no_liquidity,
    }
    
    run_screener(indices=args.index, tickers=args.tickers, config=config)
