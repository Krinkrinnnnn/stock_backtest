"""
Screener + Backtest Pipeline
==============================
Runs screener to get passing tickers, then backtests each one.
Shows top 5 most profitable and top 5 most drawdown.

Usage:
    python3 backtest_runner.py
    python3 backtest_runner.py --screener stage2
    python3 backtest_runner.py --top-k 10
    python3 backtest_runner.py --use-cache          # Use cached results
    python3 backtest_runner.py --cache-file results_2026-03-25_00-30.txt
"""

import sys
import os
import argparse
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from stage2_screener import run_screener as run_stage2
from momentum_screener import run_screener as run_momentum
from backtester import run_backtest, VCP_STRATEGY_PARAMS

SCREEN_RESULT_DIR = os.path.join(os.path.dirname(__file__), "screen_result")


def save_tickers_to_file(tickers, filename=None):
    """Save tickers to a timestamped file."""
    os.makedirs(SCREEN_RESULT_DIR, exist_ok=True)
    
    if filename is None:
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
        filename = f"screener_results_{timestamp}.txt"
    
    filepath = os.path.join(SCREEN_RESULT_DIR, filename)
    
    with open(filepath, "w") as f:
        f.write(f"# Screener Results - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"# Total tickers: {len(tickers)}\n")
        f.write("\n")
        for t in tickers:
            f.write(f"{t}\n")
    
    print(f"  Saved {len(tickers)} tickers to: {filepath}")
    return filepath


def load_tickers_from_file(filepath):
    """Load tickers from a cached file."""
    if not os.path.exists(filepath):
        print(f"  Error: File not found: {filepath}")
        return []
    
    tickers = []
    with open(filepath, "r") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                tickers.append(line)
    
    print(f"  Loaded {len(tickers)} tickers from: {filepath}")
    return tickers


def list_cache_files():
    """List all cached result files."""
    os.makedirs(SCREEN_RESULT_DIR, exist_ok=True)
    files = [f for f in os.listdir(SCREEN_RESULT_DIR) if f.startswith("screener_results_") and f.endswith(".txt")]
    files.sort(reverse=True)
    return files


def run_screener_get_tickers(screener_name="stage2", use_cache=False, cache_file=None):
    """Run screener and return passing tickers."""
    
    # Try to load from cache
    if use_cache and cache_file:
        filepath = os.path.join(SCREEN_RESULT_DIR, cache_file) if not os.path.isabs(cache_file) else cache_file
        if os.path.exists(filepath):
            return load_tickers_from_file(filepath)
    
    if use_cache:
        # List available cache files
        cache_files = list_cache_files()
        if cache_files:
            print(f"\n  Available cache files:")
            for i, f in enumerate(cache_files):
                print(f"    [{i+1}] {f}")
            print(f"  Use --cache-file to specify which one, or run without --use-cache to create new")
    
    print(f"\n{'='*70}")
    print(f"  RUNNING {screener_name.upper()} SCREENER TO GET TICKERS")
    print(f"{'='*70}")
    
    config = {
        "enable_liquidity_filter": True,
        "enable_new_high_rs": False,  # Skip for speed
    }
    
    if screener_name == "stage2":
        result = run_stage2(indices=["all"], tickers=None, config=config)
    elif screener_name == "momentum":
        result = run_momentum(indices=["all"], tickers=None, config=config)
    else:
        raise ValueError(f"Unknown screener: {screener_name}")
    
    # Get passing tickers from DataFrame
    try:
        passing = result[result["pass"] == True]
        tickers = passing["ticker"].tolist()
    except:
        tickers = []
    
    print(f"\n  Got {len(tickers)} passing tickers")
    
    # Save to file
    filepath = save_tickers_to_file(tickers)
    
    return tickers


def run_backtests(tickers, years=3, initial_capital=100000):
    """Run backtests on list of tickers."""
    print(f"\n{'='*70}")
    print(f"  RUNNING BACKTESTS ON {len(tickers)} TICKERS")
    print(f"{'='*70}")
    
    results = []
    
    for i, ticker in enumerate(tickers):
        print(f"\n  [{i+1}/{len(tickers)}] Backtesting {ticker}...", end=" ")
        
        try:
            result = run_backtest(
                symbol=ticker,
                years=years,
                initial_capital=initial_capital,
                params=VCP_STRATEGY_PARAMS,
                plot=False
            )
            
            if result:
                results.append({
                    "ticker": ticker,
                    "final_value": result.get("final_value", 0),
                    "total_return": result.get("total_return", 0),
                    "max_drawdown": result.get("max_drawdown", 0),
                    "num_trades": result.get("total_trades", 0),
                    "win_rate": result.get("win_rate", 0),
                })
                print(f"Return: {result.get('total_return', 0):.1f}%, DD: {result.get('max_drawdown', 0):.1f}%")
            else:
                print("Failed")
                
        except Exception as e:
            print(f"Error: {e}")
            continue
    
    return results


def print_top_results(results, top_k=5):
    """Print top profitable and top drawdown."""
    if not results:
        print("\n  No results to display")
        return
    
    # Sort by return (descending)
    by_profit = sorted(results, key=lambda x: x.get("total_return", 0), reverse=True)
    # Sort by drawdown (ascending - smaller is better)
    by_drawdown = sorted(results, key=lambda x: x.get("max_drawdown", 0))
    
    print(f"\n{'='*90}")
    print(f"  TOP {top_k} MOST PROFITABLE")
    print(f"{'='*90}")
    print(f"  {'Ticker':<8} {'Return':>10} {'Max DD':>10} {'Trades':>8} {'Win Rate':>10}")
    print(f"  {'-'*8} {'-'*10} {'-'*10} {'-'*8} {'-'*10}")
    
    for r in by_profit[:top_k]:
        print(f"  {r['ticker']:<8} {r['total_return']:>+9.1f}% {r['max_drawdown']:>9.1f}% {r['num_trades']:>8} {r['win_rate']:>9.1f}%")
    
    print(f"\n{'='*90}")
    print(f"  TOP {top_k} LEAST DRAWDOWN (Safest)")
    print(f"{'='*90}")
    print(f"  {'Ticker':<8} {'Return':>10} {'Max DD':>10} {'Trades':>8} {'Win Rate':>10}")
    print(f"  {'-'*8} {'-'*10} {'-'*10} {'-'*8} {'-'*10}")
    
    for r in by_drawdown[:top_k]:
        print(f"  {r['ticker']:<8} {r['total_return']:>+9.1f}% {r['max_drawdown']:>9.1f}% {r['num_trades']:>8} {r['win_rate']:>9.1f}%")
    
    # Summary
    avg_return = sum(r["total_return"] for r in results) / len(results)
    avg_dd = sum(r["max_drawdown"] for r in results) / len(results)
    print(f"\n{'='*90}")
    print(f"  SUMMARY")
    print(f"{'='*90}")
    print(f"  Total tickers tested: {len(results)}")
    print(f"  Average return: {avg_return:+.1f}%")
    print(f"  Average max drawdown: {avg_dd:.1f}%")
    profitable = sum(1 for r in results if r["total_return"] > 0)
    print(f"  Profitable: {profitable}/{len(results)} ({100*profitable/len(results):.1f}%)")


def main():
    parser = argparse.ArgumentParser(description="Screener + Backtest Pipeline")
    parser.add_argument("--screener", choices=["stage2", "momentum"], default="stage2")
    parser.add_argument("--top-k", type=int, default=5, help="Number of top results to show")
    parser.add_argument("--years", type=int, default=3, help="Backtest years")
    parser.add_argument("--capital", type=float, default=100000, help="Initial capital")
    parser.add_argument("--tickers", nargs="+", help="Use custom tickers instead of screener")
    parser.add_argument("--use-cache", action="store_true", help="Use cached screener results")
    parser.add_argument("--cache-file", type=str, help="Specific cache file to use")
    parser.add_argument("--list-cache", action="store_true", help="List available cache files")
    args = parser.parse_args()
    
    # List cache files
    if args.list_cache:
        files = list_cache_files()
        print("\nAvailable cache files:")
        for f in files:
            print(f"  {f}")
        return
    
    print(f"\n{'#'*70}")
    print(f"#  SCREENER + BACKTEST PIPELINE")
    print(f"#  Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'#'*70}")
    
    # Get tickers
    if args.tickers:
        tickers = args.tickers
    else:
        tickers = run_screener_get_tickers(args.screener, args.use_cache, args.cache_file)
    
    if not tickers:
        print("No tickers to backtest!")
        return
    
    # Run backtests
    results = run_backtests(tickers, args.years, args.capital)
    
    # Print results
    print_top_results(results, args.top_k)
    
    print(f"\n{'#'*70}")
    print(f"#  COMPLETED: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'#'*70}")


if __name__ == "__main__":
    main()
