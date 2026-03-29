#!/usr/bin/env python3
"""
Harbor Stock Pipeline
=====================
Unified pipeline: Market Regime → Screener → Backtest → Summary

Usage:
    python3 run_pipeline.py                    # Auto mode (regime-based)
    python3 run_pipeline.py --screener stage2  # Force specific screener
    python3 run_pipeline.py --backtest-only    # Skip screening, backtest cached tickers
    python3 run_pipeline.py --top-k 5          # Backtest top 5 stocks
"""

import sys
import os
import argparse
import json
from datetime import datetime

# Setup paths
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT_DIR)
sys.path.insert(0, os.path.join(ROOT_DIR, "screen"))
sys.path.insert(0, os.path.join(ROOT_DIR, "market_health"))

from backtester import run_backtest, VCP_STRATEGY_PARAMS


# ==========================================
# MARKET REGIME
# ==========================================

def get_market_regime_state():
    """快速讀取市場狀態 (從 JSON)"""
    state_path = os.path.join(ROOT_DIR, "market_health", "screen_result", "market_regime.json")
    
    if not os.path.exists(state_path):
        print("⚠️  No market_regime.json found. Run: python3 market_health/market_regime.py")
        return None
    
    with open(state_path, "r") as f:
        state = json.load(f)
    
    return state


def get_recommended_screener(regime):
    """根據市場環境推薦選股器"""
    regime_name = regime["Regime"]
    
    if "EASY_MONEY" in regime_name or "OVERBOUGHT" in regime_name:
        return "stage2"  # 牛市：趨勢追蹤
    elif "PULLBACK" in regime_name:
        return "stage2"  # 回調：尋找 Stage 2 股票
    elif "OVERSOLD" in regime_name:
        return "momentum"  # 超賣：尋找反彈動量
    else:  # HARD_MONEY / NEUTRAL
        return "week10_momentum"  # 震盪：短期動量


# ==========================================
# SCREENER
# ==========================================

def run_screener(screener_name, tickers=None):
    """執行選股器"""
    from stage2_screener import run_screener as run_stage2
    from momentum_screener import run_screener as run_momentum
    import week10_momentum
    
    print(f"\n{'='*60}")
    print(f"  📊 Running {screener_name.upper()} Screener")
    print(f"{'='*60}")
    
    config = {
        "enable_liquidity_filter": True,
        "tickers_file": "tickers.txt"
    }
    
    if screener_name == "stage2":
        result = run_stage2(tickers=tickers, indices=["all"] if not tickers else None, config=config)
    elif screener_name == "momentum":
        result = run_momentum(tickers=tickers, indices=["all"] if not tickers else None, config=config)
    elif screener_name == "week10_momentum":
        result = week10_momentum.run_screener(tickers=tickers, indices=["all"] if not tickers else None, config=config)
    else:
        print(f"Unknown screener: {screener_name}")
        return []
    
    if result is None or result.empty:
        return []
    
    # 提取通過的股票
    if "pass" in result.columns:
        passing = result[result["pass"] == True]
    elif "signal" in result.columns:
        passing = result[result["signal"] == True]
    else:
        passing = result
    
    tickers = passing["ticker"].tolist() if "ticker" in passing.columns else []
    
    # 儲存結果
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
    result_dir = os.path.join(ROOT_DIR, "screen", "screen_result")
    os.makedirs(result_dir, exist_ok=True)
    filepath = os.path.join(result_dir, f"pipeline_{screener_name}_{timestamp}.txt")
    
    with open(filepath, "w") as f:
        for t in sorted(tickers):
            f.write(f"{t}\n")
    
    print(f"\n  ✅ {len(tickers)} stocks passed. Saved to: {filepath}")
    return sorted(tickers)


# ==========================================
# BACKTEST
# ==========================================

def run_backtests(tickers, years=3, initial_capital=100000):
    """批量回測"""
    print(f"\n{'='*60}")
    print(f"  🔄 Backtesting {len(tickers)} Stocks")
    print(f"{'='*60}")
    print(f"  Capital: ${initial_capital:,.0f} | Period: {years} years")
    print(f"{'='*60}")
    
    results = []
    
    for i, ticker in enumerate(tickers):
        print(f"\n  [{i+1}/{len(tickers)}] {ticker}")
        print(f"  {'-'*40}")
        
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
                    "sharpe": result.get("sharpe_ratio", 0),
                })
        except Exception as e:
            print(f"    ❌ Error: {e}")
    
    return results


def print_summary(results, regime, screener_name):
    """列印回測摘要"""
    if not results:
        print("\n  ❌ No backtest results to display")
        return
    
    # 排序
    by_return = sorted(results, key=lambda x: x["total_return"], reverse=True)
    by_dd = sorted(results, key=lambda x: x["max_drawdown"])
    
    print(f"\n{'='*70}")
    print(f"  📊 BACKTEST SUMMARY")
    print(f"{'='*70}")
    print(f"  Market Regime: {regime['Regime']}")
    print(f"  Screener: {screener_name}")
    print(f"  Stocks Tested: {len(results)}")
    print(f"{'='*70}")
    
    # Top 5 最賺
    print(f"\n  🏆 TOP 5 MOST PROFITABLE")
    print(f"  {'Ticker':<8} {'Return':>10} {'Max DD':>10} {'Trades':>8} {'Win Rate':>10} {'Sharpe':>8}")
    print(f"  {'-'*8} {'-'*10} {'-'*10} {'-'*8} {'-'*10} {'-'*8}")
    
    for r in by_return[:5]:
        sharpe_str = f"{r['sharpe']:.2f}" if r['sharpe'] else "N/A"
        print(f"  {r['ticker']:<8} {r['total_return']:>+9.1f}% {r['max_drawdown']:>9.1f}% "
              f"{r['num_trades']:>8} {r['win_rate']:>9.1f}% {sharpe_str:>8}")
    
    # Top 5 最低回撤
    print(f"\n  🛡️ TOP 5 LEAST DRAWDOWN (Safest)")
    print(f"  {'Ticker':<8} {'Return':>10} {'Max DD':>10} {'Trades':>8} {'Win Rate':>10} {'Sharpe':>8}")
    print(f"  {'-'*8} {'-'*10} {'-'*10} {'-'*8} {'-'*10} {'-'*8}")
    
    for r in by_dd[:5]:
        sharpe_str = f"{r['sharpe']:.2f}" if r['sharpe'] else "N/A"
        print(f"  {r['ticker']:<8} {r['total_return']:>+9.1f}% {r['max_drawdown']:>9.1f}% "
              f"{r['num_trades']:>8} {r['win_rate']:>9.1f}% {sharpe_str:>8}")
    
    # 統計摘要
    avg_return = sum(r["total_return"] for r in results) / len(results)
    avg_dd = sum(r["max_drawdown"] for r in results) / len(results)
    avg_win_rate = sum(r["win_rate"] for r in results) / len(results)
    profitable = sum(1 for r in results if r["total_return"] > 0)
    
    print(f"\n  {'='*70}")
    print(f"  📈 STATISTICS")
    print(f"  {'='*70}")
    print(f"  Total Stocks Tested: {len(results)}")
    print(f"  Profitable: {profitable}/{len(results)} ({100*profitable/len(results):.0f}%)")
    print(f"  Average Return: {avg_return:+.1f}%")
    print(f"  Average Max Drawdown: {avg_dd:.1f}%")
    print(f"  Average Win Rate: {avg_win_rate:.1f}%")
    print(f"  {'='*70}")
    
    # 策略建議
    print(f"\n  💡 RECOMMENDATION")
    print(f"  {'='*70}")
    if avg_return > 10 and profitable > len(results) * 0.5:
        print(f"  ✅ Market conditions are favorable for this strategy")
    elif avg_return > 0:
        print(f"  ⚠️ Mixed results - be selective with entries")
    else:
        print(f"  ❌ Poor conditions - consider reducing position sizes")
    print(f"  {'='*70}\n")


# ==========================================
# MAIN
# ==========================================

def main():
    parser = argparse.ArgumentParser(description="Harbor Stock Pipeline")
    parser.add_argument("--screener", choices=["stage2", "momentum", "week10_momentum", "auto"],
                        default="auto", help="Which screener to run (default: auto)")
    parser.add_argument("--tickers", nargs="+", help="Custom tickers to backtest (skip screening)")
    parser.add_argument("--top-k", type=int, default=10, help="Number of stocks to backtest (default: 10)")
    parser.add_argument("--years", type=int, default=3, help="Backtest period in years (default: 3)")
    parser.add_argument("--capital", type=float, default=100000, help="Initial capital (default: 100000)")
    parser.add_argument("--backtest-only", action="store_true", help="Skip screening, use cached tickers")
    args = parser.parse_args()
    
    print(f"\n{'#'*60}")
    print(f"  🚀 HARBOR STOCK PIPELINE")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'#'*60}")
    
    # Step 1: Market Regime
    regime = get_market_regime_state()
    if regime:
        print(f"\n  🧭 Market Regime: {regime['Regime']}")
        print(f"     Above 50MA: {regime['Above_50MA']}% | Above 200MA: {regime['Above_200MA']}%")
        print(f"     Action: {regime['Action']}")
    else:
        regime = {"Regime": "UNKNOWN", "Above_50MA": 0, "Above_200MA": 0, "Action": "N/A"}
    
    # Step 2: Determine screener
    if args.screener == "auto":
        screener_name = get_recommended_screener(regime)
        print(f"\n  🎯 Auto-selected: {screener_name} (based on {regime['Regime']})")
    else:
        screener_name = args.screener
    
    # Step 3: Get tickers
    if args.tickers:
        tickers = [t.upper() for t in args.tickers]
        print(f"\n  📋 Using custom tickers: {tickers}")
    elif args.backtest_only:
        # Load from latest cached file
        result_dir = os.path.join(ROOT_DIR, "screen", "screen_result")
        files = [f for f in os.listdir(result_dir) if f.endswith(".txt")] if os.path.exists(result_dir) else []
        files.sort(reverse=True)
        if files:
            filepath = os.path.join(result_dir, files[0])
            with open(filepath, "r") as f:
                tickers = [line.strip() for line in f if line.strip() and not line.startswith("#")]
            print(f"\n  📁 Loaded {len(tickers)} tickers from: {files[0]}")
        else:
            print("\n  ❌ No cached tickers found. Run screening first.")
            return
    else:
        tickers = run_screener(screener_name)
    
    if not tickers:
        print("\n  ❌ No tickers to backtest!")
        return
    
    # Step 4: Limit to top-k
    tickers = tickers[:args.top_k]
    print(f"\n  📊 Backtesting top {len(tickers)} stocks: {', '.join(tickers)}")
    
    # Step 5: Backtest
    results = run_backtests(tickers, years=args.years, initial_capital=args.capital)
    
    # Step 6: Summary
    print_summary(results, regime, screener_name)


if __name__ == "__main__":
    main()
