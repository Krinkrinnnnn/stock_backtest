"""
VCP + RS Stock Screener
=======================
Screens a list of stocks for VCP (Volatility Contraction Pattern) + RS setups.

Architecture:
    Phase 1: Sequential download of all ticker data (single process)
    Phase 2: Filter for liquidity using downloaded data (no API calls)
    Phase 3: Parallel technical analysis (all CPU cores)

Usage:
    python3 vcp_screener.py
    python3 vcp_screener.py --tickers AAPL TSLA NVDA
"""

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime
import sys, os
from multiprocessing import Pool, cpu_count

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from minervini_screener import INDEX_MAP, get_all_us_tickers
from filters import (
    check_new_high_rs, LIQUIDITY_PARAMS,
    download_all_data, filter_invalid_tickers, filter_liquidity_batch
)

NUM_WORKERS = max(1, cpu_count() - 1)


# ==========================================
# SCREENER PARAMETERS
# ==========================================
SCREENER_PARAMS = {
    "rs_score_threshold": 60,
    "rs_line_threshold": 1.0,
    "volatility_max": 0.12,
    "volatility_contraction": 0.85,
    "breakout_window": 20,
    "ema_short_period": 13,
    "ema_long_period": 120,
    "sma_period": 50,
    "force_index_period": 13,
    "min_volume_avg": 500000,
    "min_price": 20.0,
    "data_period": "1y",
}


# ==========================================
# LIQUIDITY CHECK (data-driven, no API calls)
# ==========================================

def check_liquidity_from_data(ticker, df, params=None):
    """Check liquidity using pre-downloaded data (no API calls)."""
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
        
        return (latest_price >= params["min_price"] and 
                avg_dollar_vol >= params["min_avg_volume"])
    except Exception:
        return False


# ==========================================
# INDICATOR CALCULATION (pure CPU, no API)
# ==========================================

def calculate_indicators(df, benchmark_df, params):
    """Calculate VCP + RS indicators. Pure CPU math."""
    result = {
        "ticker": None,
        "price": 0,
        "rs_line": 0,
        "rs_score": 0,
        "volatility": 0,
        "atr_ratio": 0,
        "force_index": 0,
        "above_sma50": False,
        "ema_bullish": False,
        "breakout": False,
        "vol_contracting": False,
        "signal": False,
        "signal_strength": 0,
        "volume_avg": 0,
    }

    if df is None or len(df) < 60:
        return result

    # Handle multi-level columns
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    price = float(df['Close'].iloc[-1])
    result["price"] = price
    result["volume_avg"] = float(df['Volume'].rolling(20).mean().iloc[-1])

    if price < params["min_price"]:
        return result
    if result["volume_avg"] < params["min_volume_avg"]:
        return result

    # RS Line vs benchmark
    if benchmark_df is not None and not benchmark_df.empty:
        aligned_bench = benchmark_df.reindex(df.index, method='ffill')
        if not aligned_bench.empty:
            base_stock = float(df['Close'].iloc[0])
            base_bench = float(aligned_bench['Close'].iloc[0])
            if base_bench > 0:
                rs_line = (df['Close'] / base_stock) / (aligned_bench['Close'] / base_bench)
                result["rs_line"] = float(rs_line.iloc[-1])

                rs_min = float(rs_line.rolling(252, min_periods=20).min().iloc[-1])
                rs_max = float(rs_line.rolling(252, min_periods=20).max().iloc[-1])
                if rs_max > rs_min:
                    result["rs_score"] = ((result["rs_line"] - rs_min) / (rs_max - rs_min)) * 100

    # Moving Averages
    ema_short = df['Close'].ewm(span=params["ema_short_period"], adjust=False).mean()
    ema_long = df['Close'].ewm(span=params["ema_long_period"], adjust=False).mean()
    sma = df['Close'].rolling(window=params["sma_period"]).mean()

    result["above_sma50"] = price > float(sma.iloc[-1]) if not pd.isna(sma.iloc[-1]) else False
    result["ema_bullish"] = float(ema_short.iloc[-1]) > float(ema_long.iloc[-1]) if not pd.isna(ema_long.iloc[-1]) else False

    # ATR (volatility)
    high_low = df['High'] - df['Low']
    high_close = abs(df['High'] - df['Close'].shift(1))
    low_close = abs(df['Low'] - df['Close'].shift(1))
    true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    atr = float(true_range.rolling(window=20).mean().iloc[-1])
    result["atr_ratio"] = atr / price if price > 0 else 0

    # Volatility contraction
    current_vol = float((df['High'].rolling(20).max() - df['Low'].rolling(20).min()).iloc[-1]) / price
    shifted_close = df['Close'].shift(10).iloc[-1]
    past_vol = float((df['High'].rolling(20).max() - df['Low'].rolling(20).min()).shift(10).iloc[-1]) / float(shifted_close) if not pd.isna(shifted_close) else 1
    result["volatility"] = current_vol
    result["vol_contracting"] = current_vol < past_vol * params["volatility_contraction"] if past_vol > 0 else False

    # Breakout
    high_n = float(df['High'].rolling(window=params["breakout_window"]).max().iloc[-1])
    result["breakout"] = price >= high_n

    # Force Index
    force = (df['Close'] - df['Close'].shift(1)) * df['Volume']
    force_ema = float(force.ewm(span=params["force_index_period"]).mean().iloc[-1])
    result["force_index"] = force_ema

    # Composite Signal
    conditions = [
        result["rs_score"] >= params["rs_score_threshold"],
        result["rs_line"] >= params["rs_line_threshold"],
        result["above_sma50"],
        result["ema_bullish"],
        result["atr_ratio"] <= params["volatility_max"],
        result["vol_contracting"],
        result["breakout"],
        result["force_index"] > 0,
    ]
    result["signal"] = all(conditions)
    result["signal_strength"] = sum(conditions) / len(conditions) * 100

    return result


# ==========================================
# PARALLEL WORKERS (receive pre-downloaded data)
# ==========================================

def _screen_vcp_worker(args):
    ticker, df, benchmark_df, params = args
    r = calculate_indicators(df, benchmark_df, params)
    r["ticker"] = ticker
    return r

def _screen_vcp_batch(args_batch):
    return [_screen_vcp_worker(args) for args in args_batch]


# ==========================================
# SCREENER RUNNER
# ==========================================

def run_screener(tickers=None, params=None, benchmark_df=None, indices=None, config=None):
    """
    Run VCP + RS screener.
    
    Architecture:
        1. Download all data sequentially (single process)
        2. Filter for liquidity using downloaded data
        3. Run technical analysis in parallel (all CPUs)
    """
    if params is None:
        params = SCREENER_PARAMS
    
    if config is None:
        config = {
            "enable_liquidity_filter": True,
            "enable_new_high_rs": True,
        }
    
    enable_liquidity = config.get("enable_liquidity_filter", True)
    enable_new_high_rs = config.get("enable_new_high_rs", True)

    # Collect tickers
    if tickers is None:
        if indices is None:
            indices = ["all"]
        tickers = []
        index_names = []
        for idx in indices:
            if idx == "all":
                tickers_file = str(config.get("tickers_file", "tickers.txt"))
                idx_tickers = get_all_us_tickers(tickers_file)
                tickers.extend(idx_tickers)
                index_names.append(f"File ({tickers_file})")
            elif idx in INDEX_MAP:
                name, getter = INDEX_MAP[idx]
                tickers.extend(getter())
                index_names.append(name)
        tickers = list(dict.fromkeys(tickers))
    else:
        tickers = [t.upper() for t in tickers]
        index_names = ["Custom"]

    print(f"\n{'='*80}")
    print(f"  VCP + RS STOCK SCREENER")
    if config and config.get("tickers_file"):
        print(f"  Tickers File: {config['tickers_file']}")
    else:
        print(f"  Indices: {', '.join(index_names)}")
    print(f"  Total stocks to scan: {len(tickers)}")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*80}")
    
    print(f"\n  Filters:")
    print(f"    Liquidity Filter: {'ON' if enable_liquidity else 'OFF'} (Market Cap > $2B, Vol > $50M)")
    print(f"    New High RS Flag: {'ON' if enable_new_high_rs else 'OFF'}")

    # ==========================================
    # PHASE 1: Download all data sequentially
    # ==========================================
    print(f"\n  [Phase 1] Downloading data sequentially (1y period)...")
    all_data = download_all_data(tickers, period="1y", chunk_size=100, pause=0.5)

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
    # PHASE 3: Fetch benchmark + parallel screening
    # ==========================================
    if benchmark_df is None:
        print(f"\n  [Phase 3] Fetching S&P 500 benchmark data...")
        try:
            benchmark_df = yf.download("^GSPC", period=params["data_period"], progress=False)
            if isinstance(benchmark_df.columns, pd.MultiIndex):
                benchmark_df.columns = benchmark_df.columns.get_level_values(0)
            benchmark_df.columns = [col.capitalize() for col in benchmark_df.columns]
        except Exception:
            benchmark_df = None

    results = []
    signal_stocks = []

    print(f"\n  [Phase 4] Running VCP+RS screening with {NUM_WORKERS} workers...")
    
    liquid_list = list(liquid_tickers)
    worker_data = [(t, all_data[t], benchmark_df, params) for t in liquid_list if t in all_data]
    
    batch_size = max(1, len(worker_data) // NUM_WORKERS)
    batches = [worker_data[i:i + batch_size] for i in range(0, len(worker_data), batch_size)]
    
    with Pool(NUM_WORKERS) as pool:
        batch_results_list = pool.map(_screen_vcp_batch, batches)
    
    for batch_results in batch_results_list:
        for r in batch_results:
            r["liquidity_pass"] = True
            
            if enable_new_high_rs and r["signal"]:
                is_new_high, rs_details = check_new_high_rs(r["ticker"], df=None)
                r["new_high_rs"] = is_new_high
            else:
                r["new_high_rs"] = False
            
            results.append(r)
            
            if r["signal"]:
                signal_stocks.append(r)
    
    print(f"    Processed {len(results)} stocks")

    print(f"\n\n  Screening complete: {len(results)} stocks analyzed")
    print(f"  {'='*76}")

    # Print all results sorted by signal strength
    results.sort(key=lambda x: x["signal_strength"], reverse=True)

    rs_col = " RS>Hi" if enable_new_high_rs else ""
    print(f"\n  {'Ticker':<8} {'Price':>8} {'RS Line':>8} {'RS%':>6} {'ATR%':>6} "
          f"{'Force':>10} {'SMA50':>5} {'EMA':>5} {'B/O':>4} {'VCP':>4} {'Signal':>7} {'Str%':>5}{rs_col}")
    print(f"  {'-'*8} {'-'*8} {'-'*8} {'-'*6} {'-'*6} "
          f"{'-'*10} {'-'*5} {'-'*5} {'-'*4} {'-'*4} {'-'*7} {'-'*5}{'-'*6 if enable_new_high_rs else ''}")

    for r in results:
        if r["price"] == 0:
            continue
        rs_flag = f"  *RS" if enable_new_high_rs and r.get("new_high_rs", False) else ""
        print(f"  {r['ticker']:<8} ${r['price']:>6.2f} {r['rs_line']:>8.2f} "
              f"{r['rs_score']:>5.0f} {r['atr_ratio']*100:>5.1f} "
              f"{r['force_index']:>10.0f} "
              f"{'  +' if r['above_sma50'] else '  -':>5} "
              f"{'  +' if r['ema_bullish'] else '  -':>5} "
              f"{' +' if r['breakout'] else ' -':>4} "
              f"{' +' if r['vol_contracting'] else ' -':>4} "
              f"{'  + BUY' if r['signal'] else '  ---':>7} "
              f"{r['signal_strength']:>5.0f}{rs_flag}")

    # Print top signals
    if signal_stocks:
        print(f"\n  {'='*76}")
        print(f"  [+] TOP VCP + RS SIGNALS ({len(signal_stocks)} stocks)")
        print(f"  {'='*76}")
        for r in signal_stocks:
            rs_indicator = " *RS" if enable_new_high_rs and r.get("new_high_rs", False) else ""
            print(f"  * {r['ticker']:<6} ${r['price']:>8.2f}  RS:{r['rs_score']:.0f}  "
                  f"ATR:{r['atr_ratio']*100:.1f}%  Strength:{r['signal_strength']:.0f}%{rs_indicator}")
    else:
        print(f"\n  No VCP + RS signals found at this time.")
        near = [r for r in results if r["signal_strength"] >= 75 and r["price"] > 0]
        if near:
            print(f"\n  [!] Near-Signal Stocks (>=75% criteria met):")
            for r in near[:10]:
                print(f"    {r['ticker']:<6} ${r['price']:>8.2f}  Strength:{r['signal_strength']:.0f}%")

    print(f"\n{'='*80}\n")

    return pd.DataFrame(results)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="VCP + RS Stock Screener")
    parser.add_argument("--tickers", nargs="+", help="List of tickers to screen")
    parser.add_argument("--file", type=str, help="File with tickers (one per line)")
    parser.add_argument("--index", nargs="+", choices=["nq100", "sp500", "russell2000", "all"],
                        help="Indices to scan (default: all)")
    parser.add_argument("--no-liquidity", action="store_true", help="Disable liquidity filter")
    parser.add_argument("--no-rs-flag", action="store_true", help="Disable new high RS flag")
    args = parser.parse_args()

    tickers = None
    if args.tickers:
        tickers = [t.upper() for t in args.tickers]
    elif args.file:
        with open(args.file, 'r') as f:
            tickers = [line.strip().upper() for line in f if line.strip()]
    
    config = {
        "enable_liquidity_filter": not args.no_liquidity,
        "enable_new_high_rs": not args.no_rs_flag,
    }

    run_screener(tickers, indices=args.index, config=config)
