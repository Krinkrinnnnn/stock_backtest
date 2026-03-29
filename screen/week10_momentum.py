"""
Week 10% Momentum Stock Screener
================================
Screens for stocks with strong momentum and 10% weekly accumulation.

Architecture:
    Phase 1: Sequential download of all ticker data (single process)
    Phase 2: Filter for liquidity using downloaded data (no API calls)
    Phase 3: Parallel technical analysis (all CPU cores)

Usage:
    python3 week10_momentum.py
    python3 week10_momentum.py --tickers AAPL TSLA NVDA
"""

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime
import sys, os
from multiprocessing import Pool, cpu_count

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from stage2_screener import INDEX_MAP, get_all_us_tickers
from filters import (
    check_new_high_rs, check_earnings, LIQUIDITY_PARAMS,
    download_all_data, filter_invalid_tickers, filter_liquidity_batch
)

NUM_WORKERS = max(1, cpu_count() - 1)


# ==========================================
# SCREENER PARAMETERS
# ==========================================
SCREENER_PARAMS = {
    # --- Price Filters ---
    "min_price": 15.0,                  # Condition 1: Price > 15
    "max_price": 10000.0,

    # --- Moving Average Conditions ---
    "sma_long_period": 200,             # Condition 2: Price > MA200
    "sma_medium_period": 50,            # Condition 3: Price > MA50
    "sma_short_period": 10,             # Condition 4a: Price > MA10
    "sma_mid_period": 21,               # Condition 4b: Price > MA21

    # --- Accumulation Condition ---
    "accumulation_days": 5,             # Condition 5: 5-day accumulation window
    "accumulation_threshold": 0.10,     # Condition 5: >= 10% increase over window

    # --- Volume Filter (21-day avg dollar volume) ---
    "min_volume_avg": 50000000,         # Condition 6: 21-day avg dollar volume >= $50M (handled by filters.py)
    "volume_period": 21,                # Matches filters.py LIQUIDITY_PARAMS

    # --- Other Parameters ---
    "min_price_pct_52w_high": 0.85,
    "min_rs_score": 60,                 # Condition 7: RS Rating >= 60
    "min_rs_line": 1.0,
    "ema_period": 13,
    "min_volume_ratio": 1.0,
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
# MOMENTUM CALCULATION (pure CPU, no API)
# ==========================================

def calculate_momentum(df, benchmark_df, params):
    """Calculate momentum indicators for a stock. Pure CPU math."""
    result = {
        "ticker": None,
        "price": 0,
        "high_52w": 0,
        "pct_from_52w_high": 0,
        "change_1m": 0,
        "change_3m": 0,
        "change_6m": 0,
        "rs_line": 0,
        "rs_score": 0,
        "above_ma10": False,
        "above_ma21": False,
        "above_sma20": False,
        "above_sma50": False,
        "above_sma200": False,
        "sma_alignment": False,
        "ema_bullish": False,
        "volume_avg": 0,
        "volume_ratio": 0,
        "accumulation_5d": 0,
        "accumulation_pass": False,
        "momentum_score": 0,
        "signal": False,
        "signal_strength": 0,
    }

    if df is None or len(df) < 200:
        return result

    # Handle multi-level columns
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    price = float(df['Close'].iloc[-1])
    result["price"] = price

    if price < params["min_price"] or price > params["max_price"]:
        return result

    # 52-week high
    if len(df) >= 252:
        high_52w = float(df['High'].rolling(252).max().iloc[-1])
    else:
        high_52w = float(df['High'].max())
    result["high_52w"] = high_52w
    result["pct_from_52w_high"] = price / high_52w if high_52w > 0 else 0

    # Price changes
    if len(df) >= 21:
        result["change_1m"] = (price / float(df['Close'].iloc[-21]) - 1)
    if len(df) >= 63:
        result["change_3m"] = (price / float(df['Close'].iloc[-63]) - 1)
    if len(df) >= 126:
        result["change_6m"] = (price / float(df['Close'].iloc[-126]) - 1)

    # Volume
    vol_avg_20 = float(df['Volume'].rolling(20).mean().iloc[-1])
    result["volume_avg"] = vol_avg_20
    result["volume_ratio"] = float(df['Volume'].iloc[-1]) / vol_avg_20 if vol_avg_20 > 0 else 0

    # Moving Averages
    sma10 = df['Close'].rolling(params["sma_short_period"]).mean()
    sma21 = df['Close'].rolling(params["sma_mid_period"]).mean()
    sma20 = df['Close'].rolling(20).mean()
    sma50 = df['Close'].rolling(params["sma_medium_period"]).mean()
    sma200 = df['Close'].rolling(params["sma_long_period"]).mean()
    ema13 = df['Close'].ewm(span=params["ema_period"], adjust=False).mean()

    result["above_ma10"] = price > float(sma10.iloc[-1])
    result["above_ma21"] = price > float(sma21.iloc[-1])
    result["above_sma20"] = price > float(sma20.iloc[-1])
    result["above_sma50"] = price > float(sma50.iloc[-1])
    result["above_sma200"] = price > float(sma200.iloc[-1])
    result["sma_alignment"] = (float(sma20.iloc[-1]) > float(sma50.iloc[-1]) > float(sma200.iloc[-1]))
    result["ema_bullish"] = price > float(ema13.iloc[-1])

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

    # 5-day accumulation (Condition 5)
    accum_days = params["accumulation_days"]
    if len(df) >= accum_days:
        price_now = float(df['Close'].iloc[-1])
        price_before = float(df['Close'].iloc[-accum_days])
        result["accumulation_5d"] = (price_now / price_before - 1) if price_before > 0 else 0
        result["accumulation_pass"] = result["accumulation_5d"] >= params["accumulation_threshold"]

    # Momentum Score
    score = 0
    if result["price"] >= params["min_price"]: score += 10          # Condition 1
    if result["above_sma200"]: score += 15                           # Condition 2
    if result["above_sma50"]: score += 15                            # Condition 3
    if result["above_ma10"] and result["above_ma21"]: score += 15    # Condition 4
    if result["accumulation_pass"]: score += 20                      # Condition 5
    if result["volume_avg"] * price >= params["min_volume_avg"]: score += 10  # Condition 6
    if result["rs_line"] >= params["min_rs_line"]: score += 15        # Condition 7

    result["momentum_score"] = score

    conditions = [
        result["price"] >= params["min_price"],                    # Condition 1: Price >= 15
        result["above_sma200"],                                     # Condition 2: Price > MA200
        result["above_sma50"],                                      # Condition 3: Price > MA50
        result["above_ma10"] and result["above_ma21"],              # Condition 4: Price > MA10 & MA21
        result["accumulation_pass"],                                # Condition 5: 5d gain >= 10%
        result["volume_avg"] * price >= params["min_volume_avg"],   # Condition 6: 21d avg $volume >= $50M
        result["rs_line"] >= params["min_rs_line"],                  # Condition 7: RS Line > 1
    ]
    result["signal"] = all(conditions)
    result["signal_strength"] = sum(conditions) / len(conditions) * 100

    return result


# ==========================================
# PARALLEL WORKERS (receive pre-downloaded data)
# ==========================================

def _screen_momentum_worker(args):
    ticker, df, benchmark_df, params = args
    r = calculate_momentum(df, benchmark_df, params)
    r["ticker"] = ticker
    return r


def _screen_momentum_batch(args_batch):
    return [_screen_momentum_worker(args) for args in args_batch]


# ==========================================
# SCREENER RUNNER
# ==========================================

def run_screener(tickers=None, params=None, benchmark_df=None, indices=None, config=None):
    """
    Run Momentum screener.
    
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
    enable_earnings = config.get("enable_earnings_filter", True)

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

    print(f"\n{'='*90}")
    print(f"  WEEKLY 10% MOMENTUM SCREENER")
    if config and config.get("tickers_file"):
        print(f"  Tickers File: {config['tickers_file']}")
    else:
        print(f"  Indices: {', '.join(index_names)}")
    print(f"  Total stocks to scan: {len(tickers)}")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*90}")
    
    print(f"\n  Filters:")
    print(f"    Liquidity Filter: {'ON' if enable_liquidity else 'OFF'} (21d avg $vol >= $50M)")
    print(f"    New High RS Flag: {'ON' if enable_new_high_rs else 'OFF'}")
    print(f"    Earnings Filter: {'ON' if enable_earnings else 'OFF'} (exclude within 7 days)")
    
    print(f"\n  Conditions (all configurable in SCREENER_PARAMS):")
    print(f"    1. Price >= ${params['min_price']:.0f}")
    print(f"    2. Price > MA{params['sma_long_period']} (long-term trend)")
    print(f"    3. Price > MA{params['sma_medium_period']} (medium-term trend)")
    print(f"    4. Price > MA{params['sma_short_period']} & Price > MA{params['sma_mid_period']}")
    print(f"    5. {params['accumulation_days']}-day accumulation >= {params['accumulation_threshold']*100:.0f}%")
    print(f"    6. 21-day avg dollar volume >= ${params['min_volume_avg']/1e6:.0f}M")
    print(f"    7. RS Line > {params['min_rs_line']} (outperforms S&P 500)")

    # ==========================================
    # PHASE 1: Download all data sequentially
    # ==========================================
    print(f"\n  [Phase 1] Downloading data sequentially (1mo period)...")
    all_data = download_all_data(tickers, period="1mo", chunk_size=200, pause=1.0)

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
    # PHASE 2.5: Earnings date filter (optional)
    # ==========================================
    if enable_earnings:
        print(f"\n  [Phase 2.5] Checking earnings dates (excl. within 7 days)...")
        safe_tickers = set()
        excluded_count = 0
        for ticker in liquid_tickers:
            passes, details = check_earnings(ticker)
            if passes:
                safe_tickers.add(ticker)
            else:
                excluded_count += 1
                if details.get("days_until_earnings") is not None:
                    print(f"    Excluded {ticker}: {details['reason']} ({details['days_until_earnings']}d)")
        print(f"    Safe stocks: {len(safe_tickers)}/{len(liquid_tickers)} ({excluded_count} excluded)")
        liquid_tickers = safe_tickers

    if not liquid_tickers:
        print(f"\n  No stocks remaining after filters.")
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

    print(f"\n  [Phase 4] Running Momentum screening with {NUM_WORKERS} workers...")
    
    liquid_list = list(liquid_tickers)
    worker_data = [(t, all_data[t], benchmark_df, params) for t in liquid_list if t in all_data]
    
    batch_size = max(1, len(worker_data) // NUM_WORKERS)
    batches = [worker_data[i:i + batch_size] for i in range(0, len(worker_data), batch_size)]
    
    with Pool(NUM_WORKERS) as pool:
        batch_results_list = pool.map(_screen_momentum_batch, batches)
    
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
    print(f"  {'='*86}")

    # Print all results sorted by momentum score
    results.sort(key=lambda x: x["momentum_score"], reverse=True)

    rs_col = " RS>Hi" if enable_new_high_rs else ""
    print(f"\n  {'Ticker':<7} {'Price':>8} {'MA10':>5} {'MA21':>5} {'MA50':>5} {'MA200':>5} {'5d%':>6} {'RS%':>5} {'Signal':>7} {'Score':>5}{rs_col}")
    print(f"  {'-'*7} {'-'*8} {'-'*5} {'-'*5} {'-'*5} {'-'*5} {'-'*6} {'-'*5} {'-'*7} {'-'*5}{'-'*6 if enable_new_high_rs else ''}")

    for r in results:
        if r["price"] == 0:
            continue
        ma10_str = "+" if r["above_ma10"] else "-"
        ma21_str = "+" if r["above_ma21"] else "-"
        ma50_str = "+" if r["above_sma50"] else "-"
        ma200_str = "+" if r["above_sma200"] else "-"
        signal_str = "  + BUY" if r["signal"] else "  ---"
        rs_flag = f"  *RS" if enable_new_high_rs and r.get("new_high_rs", False) else ""
        print(f"  {r['ticker']:<7} ${r['price']:>6.2f} {ma10_str:>5} {ma21_str:>5} {ma50_str:>5} {ma200_str:>5} "
              f"{r['accumulation_5d']*100:>+5.1f}% {r['rs_score']:>4.0f} {signal_str:>7} {r['momentum_score']:>5.0f}{rs_flag}")

    # Print top signals
    if signal_stocks:
        print(f"\n  {'='*86}")
        print(f"  [+] WEEKLY 10% MOMENTUM SIGNALS ({len(signal_stocks)} stocks)")
        print(f"  {'='*86}")
        for r in signal_stocks:
            rs_indicator = " *RS" if enable_new_high_rs and r.get("new_high_rs", False) else ""
            print(f"  * {r['ticker']:<6} ${r['price']:>8.2f}  "
                  f"MA10:{('+' if r['above_ma10'] else '-'):>1}  "
                  f"MA21:{('+' if r['above_ma21'] else '-'):>1}  "
                  f"MA50:{('+' if r['above_sma50'] else '-'):>1}  "
                  f"MA200:{('+' if r['above_sma200'] else '-'):>1}  "
                  f"5d:{r['accumulation_5d']*100:+.1f}%  "
                  f"RS:{r['rs_score']:.0f}  Score:{r['momentum_score']:.0f}{rs_indicator}")
    else:
        print(f"\n  No momentum signals found at this time.")
        near = [r for r in results if r["momentum_score"] >= 60 and r["price"] > 0]
        if near:
            print(f"\n  [!] Near-Signal Stocks (Score >= 60):")
            for r in near[:10]:
                print(f"    {r['ticker']:<6} ${r['price']:>8.2f}  Score:{r['momentum_score']:.0f}")

    print(f"\n{'='*90}\n")

    # Save results
    try:
        os.makedirs("screen_result", exist_ok=True)
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
        filepath = f"screen_result/week10_momentum_{timestamp}.txt"
        
        all_tickers = sorted(set(r["ticker"] for r in results if r["price"] > 0))
        signal_tickers = sorted(set(r["ticker"] for r in signal_stocks))
        near_tickers = sorted(set(r["ticker"] for r in results if r["momentum_score"] >= 60 and r["price"] > 0))
        
        with open(filepath, "w") as f:
            f.write(f"# Weekly 10% Momentum Screener Results\n")
            f.write(f"# {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"# Total analyzed: {len(all_tickers)}\n")
            f.write(f"# Signals (7/7): {len(signal_tickers)}\n")
            f.write(f"# Near-signal (score >= 60): {len(near_tickers)}\n")
            f.write(f"# Conditions: Price>=15, >MA200, >MA50, >MA10&MA21, 5d>=10%, $vol>=50M, RS>=80\n")
            f.write(f"# Earnings filter: {'ON' if enable_earnings else 'OFF'}\n\n")
            
            if signal_tickers:
                f.write(f"[SIGNALS]\n")
                for t in signal_tickers:
                    f.write(f"{t}\n")
                f.write(f"\n")
            
            if near_tickers:
                f.write(f"[NEAR-SIGNALS (score >= 60)]\n")
                for t in near_tickers:
                    f.write(f"{t}\n")
                f.write(f"\n")
            
            f.write(f"[ALL ANALYZED]\n")
            for t in all_tickers:
                f.write(f"{t}\n")
        
        print(f"  Results saved to: {filepath}")
    except Exception as e:
        print(f"  Could not save results: {e}")

    return pd.DataFrame(results)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Momentum Stock Screener")
    parser.add_argument("--tickers", nargs="+", help="List of tickers to screen")
    parser.add_argument("--file", type=str, help="File with tickers (one per line)")
    parser.add_argument("--index", nargs="+", choices=["nq100", "sp500", "russell2000", "all"],
                        help="Indices to scan (default: all)")
    parser.add_argument("--no-liquidity", action="store_true", help="Disable liquidity filter")
    parser.add_argument("--no-rs-flag", action="store_true", help="Disable new high RS flag")
    parser.add_argument("--no-earnings", action="store_true", help="Disable earnings date filter")
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
        "enable_earnings_filter": not args.no_earnings,
    }

    run_screener(tickers, indices=args.index, config=config)
