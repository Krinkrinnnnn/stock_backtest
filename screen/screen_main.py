"""
Main Screener Runner
====================
Central entry point for all stock screeners.
All parameters are configurable via config.yaml or command line arguments.

Usage:
    python3 main.py                           # Run all screeners with defaults
    python3 main.py --screener stage2         # Run specific screener
    python3 main.py --config config.yaml      # Use custom config file
    
    # Override parameters
    python3 main.py --liquidity-min 5000000000 --rs-threshold 70
"""

import argparse
import os
import sys
import yaml
import pandas as pd
from datetime import datetime

SCREEN_DIR = os.path.dirname(os.path.abspath(__file__))
SCREEN_RESULT_DIR = os.path.join(SCREEN_DIR, "screen_result")
sys.path.insert(0, os.path.join(SCREEN_DIR, "screener_list"))

DEFAULT_CONFIG = {
    "screener": "all",  # stage2, momentum, week10_momentum, oversold, all
    
    # Data source
    "tickers_file": "tickers.txt",
    
    # Filters
    "enable_liquidity_filter": True,
    "enable_new_high_rs": True,
    "enable_correlation_check": True,
    
    # Liquidity parameters
    "liquidity": {
        "min_market_cap": 2_000_000_000,  # $2B
        "min_avg_volume": 50_000_000,    # $50M dollar volume
    },
    
    # Stage 2 screener params
    "stage2": {
        "cond_1_price_above_ma": True,
        "cond_2_ma150_above_ma200": True,
        "cond_3_ma200_trending_up": True,
        "cond_4_ma50_above_ma150_ma200": True,
        "cond_5_price_above_ma50": True,
        "cond_6_pct_above_52w_low": 30,  # 30%
        "cond_7_within_pct_of_52w_high": 25,  # 25%
        "cond_8_positive_1y_return": True,
    },
    
    # Momentum screener params
    "momentum": {
        "data_period": "1y",
        "min_price_pct_52w_high": 0.85,
        "min_price_change_1m": 0.05,
        "min_price_change_3m": 0.10,
        "min_rs_score": 70,
        "min_rs_line": 1.0,
        "sma_short_period": 20,
        "sma_medium_period": 50,
        "sma_long_period": 200,
        "ema_period": 13,
        "min_volume_avg": 500000,
        "min_price": 20.0,
        "max_price": 10000.0,
    },
    
    # Week 10% momentum screener params
    "week10_momentum": {
        "min_price": 15.0,
        "max_price": 10000.0,
        "sma_long_period": 200,
        "sma_medium_period": 50,
        "sma_short_period": 10,
        "sma_mid_period": 21,
        "min_rs_score": 60,
        "min_rs_line": 1.0,
        "accumulation_days": 5,
        "accumulation_threshold": 0.10,
        "min_volume_avg": 50000000,
        "volume_period": 21,
        "min_price_pct_52w_high": 0.85,
        "ema_period": 13,
        "min_volume_ratio": 1.0,
        "data_period": "1y",
    },
    
    # Oversold screener params (Spring Trap)
    "oversold": {
        "rsi_threshold": 30,        # Max RSI (oversold)
        "volume_ratio": 1.2,        # Min volume vs 20d avg
        "price_above_200ma": True,  # Must be above 200MA
        "price_below_50ma": True,   # Must be below 50MA
    },
    
    # Output
    "output_dir": "output",
    "save_results": True,
    "verbose": True,
}


def load_config(config_file=None):
    """Load configuration from YAML file or use defaults."""
    config = DEFAULT_CONFIG.copy()
    
    if config_file and os.path.exists(config_file):
        with open(config_file, 'r') as f:
            user_config = yaml.safe_load(f)
            if user_config:
                config.update(user_config)
    
    return config


# ── Sector Enrichment Helpers ──────────────────────────────────────────

def _get_passing_tickers(result):
    """Extract passing tickers from a screener result DataFrame."""
    if result is None or result.empty or "ticker" not in result.columns:
        return []
    if "signal" in result.columns:
        passing = result[result["signal"] == True]
    elif "pass" in result.columns:
        passing = result[result["pass"] == True]
    elif "momentum_score" in result.columns:
        passing = result[result["momentum_score"] >= 60]
    elif "signal_strength" in result.columns:
        passing = result[result["signal_strength"] >= 60]
    elif "score" in result.columns:
        passing = result[result["score"] >= 6]
    else:
        passing = result
    return sorted(passing["ticker"].tolist())


def _enrich_with_sectors(tickers):
    """
    Add sector column to a list of tickers.
    Tries PortfolioManager cache first, falls back to direct yfinance lookup.

    Returns:
        pd.DataFrame with columns: ticker, sector
    """
    if not tickers:
        return pd.DataFrame(columns=["ticker", "sector"])

    sector_map = {}

    # Try PortfolioManager cache first
    try:
        from positioning.portfolio_manager import PortfolioManager
        pm = PortfolioManager()
        for t in tickers:
            meta = pm._get_stock_metadata(t)
            s = meta.get("sector")
            if s:
                sector_map[t] = s
    except (ImportError, Exception):
        pass

    # Fallback: direct yfinance for any missing sectors
    import yfinance as yf
    for t in tickers:
        if t not in sector_map:
            try:
                info = yf.Ticker(t).info
                if info and info.get("sector"):
                    sector_map[t] = info["sector"]
            except Exception:
                pass

    rows = [{"ticker": t, "sector": sector_map.get(t, "Unknown")} for t in tickers]
    return pd.DataFrame(rows)


def _print_sector_summary(sector_df):
    """Print a sector distribution table from a ticker-sector DataFrame."""
    if sector_df.empty:
        print("\n  [SECTOR SUMMARY] No passing tickers.")
        return

    total = len(sector_df)
    counts = sector_df["sector"].value_counts()

    print(f"\n  [SECTOR SUMMARY]  {total} passing ticker(s)")
    print(f"  {'Sector':<30} {'Count':>6} {'Weight':>8}")
    print(f"  {'-'*30} {'-'*6} {'-'*8}")
    for sector, count in counts.items():
        pct = count / total * 100
        print(f"  {sector:<30} {count:>6} {pct:>7.1f}%")


def _save_screened_results(filepath_txt, filepath_xlsx, tickers, sector_df, full_result=None):
    """
    Save screener results to .txt (tickers only) and .xlsx (full data + sector).

    Args:
        filepath_txt: Path for plain ticker list
        filepath_xlsx: Path for full data Excel file
        tickers: List of passing ticker strings
        sector_df: DataFrame with 'ticker' and 'sector' columns
        full_result: Full DataFrame from screener (all rows, all metrics)
    """
    # Plain text — one ticker per line (backward compatible)
    with open(filepath_txt, "w") as f:
        for t in tickers:
            f.write(f"{t}\n")

    # Excel with full screener data + sector
    if full_result is not None and not full_result.empty:
        export_df = full_result.copy()
        # Merge sector into full result
        if not sector_df.empty and "ticker" in export_df.columns:
            export_df = export_df.merge(sector_df, on="ticker", how="left")
            if "sector" in export_df.columns:
                export_df["sector"] = export_df["sector"].fillna("Unknown")
        # Clean column names for Excel
        export_df.columns = [str(c).replace("_", " ").title() for c in export_df.columns]
        export_df.to_excel(filepath_xlsx, index=False, sheet_name="Results")
        print(f"  Saved: {filepath_xlsx}  ({len(export_df)} rows)")
    elif not sector_df.empty:
        sector_df.to_excel(filepath_xlsx, index=False, sheet_name="Results")
        print(f"  Saved: {filepath_xlsx}")

    print(f"  Saved: {filepath_txt}")


def run_stage2(config, output_dir=None):
    """Run Stage 2 screener."""
    print("\n" + "="*70)
    print("  RUNNING STAGE 2 SCREENER")
    print("="*70)
    
    from stage2_screener import run_screener
    
    screener_config = {
        "enable_liquidity_filter": config["enable_liquidity_filter"],
        "tickers_file": config.get("tickers_file", "tickers.txt")
    }
    
    result = run_screener(
        tickers=config.get("custom_tickers", None),
        indices=["all"] if not config.get("custom_tickers") else None,
        config=screener_config
    )
    
    if config.get("save_results", True):
        save_dir = output_dir or SCREEN_RESULT_DIR
        os.makedirs(save_dir, exist_ok=True)
        
        tickers = _get_passing_tickers(result)
        all_tickers = sorted(result["ticker"].tolist()) if isinstance(result, pd.DataFrame) and "ticker" in result.columns else tickers
        sector_df = _enrich_with_sectors(all_tickers)
        _print_sector_summary(sector_df[sector_df["ticker"].isin(tickers)]) if tickers else None
        
        filepath_txt = f"{save_dir}/screener_stage2.txt"
        filepath_xlsx = f"{save_dir}/screener_stage2.xlsx"
        full_df = result if isinstance(result, pd.DataFrame) else None
        _save_screened_results(filepath_txt, filepath_xlsx, tickers, sector_df, full_result=full_df)
        
        # --- Correlation Check ---
        if config.get("enable_correlation_check", True) and len(tickers) >= 2:
            try:
                from correlation import check_correlation_warnings
                check_correlation_warnings(tickers, threshold=0.7, days=40)
            except ImportError:
                print("  Correlation module not found.")
    
    return result


def run_momentum(config, output_dir=None):
    """Run Momentum screener."""
    print("\n" + "="*70)
    print("  RUNNING MOMENTUM SCREENER")
    print("="*70)
    
    from momentum_screener import run_screener as run_mom_screener
    
    momentum_params = config["momentum"].copy()
    screener_config = {
        "enable_liquidity_filter": config["enable_liquidity_filter"],
        "enable_new_high_rs": config["enable_new_high_rs"],
        "tickers_file": config.get("tickers_file", "tickers.txt")
    }
    
    result = run_mom_screener(
        tickers=config.get("custom_tickers", None),
        params=momentum_params,
        benchmark_df=None,
        indices=["all"] if not config.get("custom_tickers") else None,
        config=screener_config
    )
    
    if config.get("save_results", True):
        save_dir = output_dir or SCREEN_RESULT_DIR
        os.makedirs(save_dir, exist_ok=True)
        
        tickers = _get_passing_tickers(result)
        all_tickers = sorted(result["ticker"].tolist()) if isinstance(result, pd.DataFrame) and "ticker" in result.columns else tickers
        sector_df = _enrich_with_sectors(all_tickers)
        _print_sector_summary(sector_df[sector_df["ticker"].isin(tickers)]) if tickers else None
        
        filepath_txt = f"{save_dir}/screener_momentum.txt"
        filepath_xlsx = f"{save_dir}/screener_momentum.xlsx"
        full_df = result if isinstance(result, pd.DataFrame) else None
        _save_screened_results(filepath_txt, filepath_xlsx, tickers, sector_df, full_result=full_df)
        
        # --- Correlation Check ---
        if config.get("enable_correlation_check", True) and len(tickers) >= 2:
            try:
                from correlation import check_correlation_warnings
                check_correlation_warnings(tickers, threshold=0.7, days=40)
            except ImportError:
                print("  Correlation module not found.")
    
    return result


def run_week10_momentum(config, output_dir=None):
    """Run Week 10% Momentum screener."""
    print("\n" + "="*70)
    print("  RUNNING WEEK 10% MOMENTUM SCREENER")
    print("="*70)
    
    from week10_momentum import run_screener as run_wk10_screener
    
    wk10_params = config["week10_momentum"].copy()
    screener_config = {
        "enable_liquidity_filter": config["enable_liquidity_filter"],
        "enable_new_high_rs": config["enable_new_high_rs"],
        "enable_earnings_filter": True,
        "tickers_file": config.get("tickers_file", "tickers.txt")
    }
    
    result = run_wk10_screener(
        tickers=config.get("custom_tickers", None),
        params=wk10_params,
        benchmark_df=None,
        indices=["all"] if not config.get("custom_tickers") else None,
        config=screener_config
    )
    
    if config.get("save_results", True):
        save_dir = output_dir or SCREEN_RESULT_DIR
        os.makedirs(save_dir, exist_ok=True)
        
        tickers = _get_passing_tickers(result)
        all_tickers = sorted(result["ticker"].tolist()) if isinstance(result, pd.DataFrame) and "ticker" in result.columns else tickers
        sector_df = _enrich_with_sectors(all_tickers)
        _print_sector_summary(sector_df[sector_df["ticker"].isin(tickers)]) if tickers else None
        
        filepath_txt = f"{save_dir}/screener_week10_momentum.txt"
        filepath_xlsx = f"{save_dir}/screener_week10_momentum.xlsx"
        full_df = result if isinstance(result, pd.DataFrame) else None
        _save_screened_results(filepath_txt, filepath_xlsx, tickers, sector_df, full_result=full_df)
    
    return result


def run_oversold(config, output_dir=None):
    """Run Oversold Spring Trap screener."""
    print("\n" + "="*70)
    print("  RUNNING OVERSOLD SCREENER (Spring Trap)")
    print("="*70)
    
    from oversold_screener import run_screener as run_oversold_screener
    
    result = run_oversold_screener(
        tickers=config.get("custom_tickers", None)
    )
    
    if config.get("save_results", True):
        save_dir = output_dir or SCREEN_RESULT_DIR
        os.makedirs(save_dir, exist_ok=True)
        
        tickers = _get_passing_tickers(result)
        all_tickers = sorted(result["ticker"].tolist()) if isinstance(result, pd.DataFrame) and "ticker" in result.columns else tickers
        sector_df = _enrich_with_sectors(all_tickers)
        _print_sector_summary(sector_df[sector_df["ticker"].isin(tickers)]) if tickers else None
        
        filepath_txt = f"{save_dir}/screener_oversold.txt"
        filepath_xlsx = f"{save_dir}/screener_oversold.xlsx"
        full_df = result if isinstance(result, pd.DataFrame) else None
        _save_screened_results(filepath_txt, filepath_xlsx, tickers, sector_df, full_result=full_df)
    
    return result


def run_all_screeners(config):
    """Run all screeners. All outputs saved to a single session folder."""
    results = {}
    
    # Create a shared output folder for this run
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
    session_dir = os.path.join(SCREEN_RESULT_DIR, f"screen_all_{timestamp}")
    os.makedirs(session_dir, exist_ok=True)
    
    print(f"\n{'#'*70}")
    print(f"#  STOCK SCREENER SUITE")
    print(f"#  Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"#  Tickers Source: {config['tickers_file']}")
    print(f"#  Liquidity Filter: {'ON' if config['enable_liquidity_filter'] else 'OFF'}")
    print(f"#  New High RS: {'ON' if config['enable_new_high_rs'] else 'OFF'}")
    print(f"#  Output Folder: {session_dir}")
    print(f"{'#'*70}")
    
    for screener_name in ["stage2", "momentum", "week10_momentum", "oversold"]:
        try:
            if screener_name == "stage2":
                results["stage2"] = run_stage2(config, output_dir=session_dir)
            elif screener_name == "momentum":
                results["momentum"] = run_momentum(config, output_dir=session_dir)
            elif screener_name == "week10_momentum":
                results["week10_momentum"] = run_week10_momentum(config, output_dir=session_dir)
            elif screener_name == "oversold":
                results["oversold"] = run_oversold(config, output_dir=session_dir)
        except Exception as e:
            print(f"Error running {screener_name} screener: {e}")
            results[screener_name] = None
    
    print(f"\n{'#'*70}")
    print(f"#  ALL SCREENERS COMPLETED")
    print(f"#  Finished: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"#  Output: {session_dir}")
    print(f"{'#'*70}")
    
    return results


def main():
    parser = argparse.ArgumentParser(
        description="Main Stock Screener Runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 main.py                           # Run all screeners
  python3 main.py --screener stage2         # Run only Stage 2
  python3 main.py --screener momentum       # Run only Momentum
  python3 main.py --screener oversold        # Run only Oversold (Spring Trap)
  python3 main.py --no-liquidity            # Disable liquidity filter
  python3 main.py --no-rs-flag              # Disable new high RS flag
  python3 main.py --config config.yaml      # Use custom config file
        """
    )
    
    # Screener selection
    parser.add_argument(
        "--screener", "-s",
        choices=["stage2", "momentum", "week10_momentum", "oversold", "all"],
        default="all",
        help="Which screener to run (default: all)"
    )
    
    # Config file
    parser.add_argument(
        "--config", "-c",
        type=str,
        help="Path to YAML config file"
    )
    
    # Filters
    parser.add_argument(
        "--no-liquidity",
        action="store_true",
        help="Disable liquidity filter"
    )
    parser.add_argument(
        "--no-rs-flag",
        action="store_true",
        help="Disable new high RS flag"
    )
    parser.add_argument(
        "--no-correlation",
        action="store_true",
        help="Disable post-screen correlation analysis"
    )
    
    # Override parameters
    parser.add_argument(
        "--liquidity-min",
        type=float,
        help="Minimum market cap in dollars (e.g., 2000000000 for $2B)"
    )
    parser.add_argument(
        "--volume-min",
        type=float,
        help="Minimum average volume in dollars"
    )
    parser.add_argument(
        "--rs-threshold",
        type=int,
        help="RS score threshold (0-100)"
    )
    
    # Tickers
    parser.add_argument(
        "--tickers",
        nargs="+",
        help="Custom ticker list (overrides tickers file)"
    )
    parser.add_argument(
        "--file",
        type=str,
        help="Custom text file with tickers (e.g., custom_list.txt)"
    )
    
    # Output
    parser.add_argument(
        "--save/--no-save",
        default=True,
        help="Save results to file (default: save)"
    )
    
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Verbose output"
    )
    
    parser.add_argument(
        "--check-correlation",
        nargs="+",
        metavar="TICKER",
        help="Run standalone correlation check on a list of tickers (e.g., --check-correlation NVDA AMD ARM AVGO)"
    )
    
    args = parser.parse_args()
    
    # Load config
    config = load_config(args.config)
    
    # Override with CLI args
    if args.no_liquidity:
        config["enable_liquidity_filter"] = False
    if args.no_rs_flag:
        config["enable_new_high_rs"] = False
    if args.no_correlation:
        config["enable_correlation_check"] = False
    if args.liquidity_min:
        config["liquidity"]["min_market_cap"] = args.liquidity_min
    if args.volume_min:
        config["liquidity"]["min_avg_volume"] = args.volume_min
    if args.rs_threshold:
        config["momentum"]["min_rs_score"] = args.rs_threshold
        config["week10_momentum"]["min_rs_score"] = args.rs_threshold
    if args.tickers:
        config["custom_tickers"] = args.tickers
    elif args.file:
        config["tickers_file"] = args.file
        
    if args.verbose:
        config["verbose"] = True
    
    # Standalone correlation check
    if args.check_correlation:
        tickers = [t.upper() for t in args.check_correlation]
        if len(tickers) < 2:
            print("Error: Need at least 2 tickers for correlation check.")
            return
        print(f"\nRunning correlation check on {len(tickers)} tickers...")
        from correlation import check_correlation_warnings
        check_correlation_warnings(tickers, threshold=0.7, days=40)
        return
    
    # Run selected screener(s)
    if args.screener == "all":
        run_all_screeners(config)
    elif args.screener == "stage2":
        run_stage2(config)
    elif args.screener == "momentum":
        run_momentum(config)
    elif args.screener == "week10_momentum":
        run_week10_momentum(config)
    elif args.screener == "oversold":
        run_oversold(config)


if __name__ == "__main__":
    main()
