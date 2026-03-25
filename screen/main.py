"""
Main Screener Runner
====================
Central entry point for all stock screeners.
All parameters are configurable via config.yaml or command line arguments.

Usage:
    python3 main.py                           # Run all screeners with defaults
    python3 main.py --screener minervini     # Run specific screener
    python3 main.py --config config.yaml     # Use custom config file
    
    # Override parameters
    python3 main.py --liquidity-min 5000000000 --rs-threshold 70
"""

import argparse
import os
import sys
import yaml
from datetime import datetime

SCREEN_DIR = os.path.dirname(os.path.abspath(__file__))

DEFAULT_CONFIG = {
    "screener": "all",  # minervini, vcp, momentum, all
    
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
    
    # Minervini screener params
    "minervini": {
        "cond_1_price_above_ma": True,
        "cond_2_ma150_above_ma200": True,
        "cond_3_ma200_trending_up": True,
        "cond_4_ma50_above_ma150_ma200": True,
        "cond_5_price_above_ma50": True,
        "cond_6_pct_above_52w_low": 30,  # 30%
        "cond_7_within_pct_of_52w_high": 25,  # 25%
        "cond_8_positive_1y_return": True,
    },
    
    # VCP screener params
    "vcp": {
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


def run_minervini(config):
    """Run Minervini Trend Template screener."""
    print("\n" + "="*70)
    print("  RUNNING MINERVIINI TREND TEMPLATE SCREENER")
    print("="*70)
    
    from minervini_screener import run_screener
    
    screener_config = {
        "enable_liquidity_filter": config["enable_liquidity_filter"],
        "enable_new_high_rs": config["enable_new_high_rs"],
        "tickers_file": config.get("tickers_file", "tickers.txt")
    }
    
    result = run_screener(
        tickers=config.get("custom_tickers", None),
        indices=["all"] if not config.get("custom_tickers") else None,
        config=screener_config
    )
    
    if config.get("save_results", True):
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
        os.makedirs("screen_result", exist_ok=True)
        filepath = f"screen_result/screener_minervini_{timestamp}.txt"
        passing = result[result["pass"] == True] if "pass" in result.columns else result
        tickers = passing["ticker"].tolist() if hasattr(passing, "tolist") else []
        with open(filepath, "w") as f:
            f.write(f"# Minervini Screener Results\n")
            f.write(f"# {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"# Total: {len(tickers)}\n\n")
            for t in tickers:
                f.write(f"{t}\n")
        print(f"\n  Saved: {filepath}")
        
        # --- Correlation Check ---
        if config.get("enable_correlation_check", True) and len(tickers) >= 2:
            try:
                from correlation import check_correlation_warnings
                check_correlation_warnings(tickers, threshold=0.7, days=40)
            except ImportError:
                print("  Correlation module not found.")
    
    return result


def run_momentum(config):
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
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
        os.makedirs("screen_result", exist_ok=True)
        filepath = f"screen_result/screener_momentum_{timestamp}.txt"
        passing = result[result["signal"] == True] if "signal" in result.columns else result
        tickers = passing["ticker"].tolist() if hasattr(passing, "tolist") else []
        with open(filepath, "w") as f:
            f.write(f"# Momentum Screener Results\n")
            f.write(f"# {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"# Total: {len(tickers)}\n\n")
            for t in tickers:
                f.write(f"{t}\n")
        print(f"\n  Saved: {filepath}")
        
        # --- Correlation Check ---
        if config.get("enable_correlation_check", True) and len(tickers) >= 2:
            try:
                from correlation import check_correlation_warnings
                check_correlation_warnings(tickers, threshold=0.7, days=40)
            except ImportError:
                print("  Correlation module not found.")
    
    return result


def run_vcp(config):
    """Run VCP screener."""
    print("\n" + "="*70)
    print("  RUNNING VCP + RS SCREENER")
    print("="*70)
    
    from vcp_screener import run_screener as run_vcp_screener
    
    vcp_params = config["vcp"].copy()
    screener_config = {
        "enable_liquidity_filter": config["enable_liquidity_filter"],
        "enable_new_high_rs": config["enable_new_high_rs"],
        "tickers_file": config.get("tickers_file", "tickers.txt")
    }
    
    result = run_vcp_screener(
        tickers=config.get("custom_tickers", None),
        params=vcp_params,
        benchmark_df=None,
        indices=["all"] if not config.get("custom_tickers") else None,
        config=screener_config
    )
    
    if config.get("save_results", True):
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
        os.makedirs("screen_result", exist_ok=True)
        filepath = f"screen_result/screener_vcp_{timestamp}.txt"
        passing = result[result["signal"] == True] if "signal" in result.columns else result
        tickers = passing["ticker"].tolist() if hasattr(passing, "tolist") else []
        with open(filepath, "w") as f:
            f.write(f"# VCP Screener Results\n")
            f.write(f"# {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"# Total: {len(tickers)}\n\n")
            for t in tickers:
                f.write(f"{t}\n")
        print(f"\n  Saved: {filepath}")
        
        # --- Correlation Check ---
        if config.get("enable_correlation_check", True) and len(tickers) >= 2:
            try:
                from correlation import check_correlation_warnings
                check_correlation_warnings(tickers, threshold=0.7, days=40)
            except ImportError:
                print("  Correlation module not found.")
    
    return result


def run_all_screeners(config):
    """Run all screeners."""
    results = {}
    
    print(f"\n{'#'*70}")
    print(f"#  STOCK SCREENER SUITE")
    print(f"#  Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"#  Tickers Source: {config['tickers_file']}")
    print(f"#  Liquidity Filter: {'ON' if config['enable_liquidity_filter'] else 'OFF'}")
    print(f"#  New High RS: {'ON' if config['enable_new_high_rs'] else 'OFF'}")
    print(f"{'#'*70}")
    
    # Run each screener
    for screener_name in ["minervini", "momentum", "vcp"]:
        try:
            if screener_name == "minervini":
                results["minervini"] = run_minervini(config)
            elif screener_name == "momentum":
                results["momentum"] = run_momentum(config)
            elif screener_name == "vcp":
                results["vcp"] = run_vcp(config)
        except Exception as e:
            print(f"Error running {screener_name} screener: {e}")
            results[screener_name] = None
    
    print(f"\n{'#'*70}")
    print(f"#  ALL SCREENERS COMPLETED")
    print(f"#  Finished: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'#'*70}")
    
    return results


def main():
    parser = argparse.ArgumentParser(
        description="Main Stock Screener Runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 main.py                           # Run all screeners
  python3 main.py --screener minervini       # Run only Minervini
  python3 main.py --screener vcp            # Run only VCP
  python3 main.py --screener momentum       # Run only Momentum
  python3 main.py --no-liquidity            # Disable liquidity filter
  python3 main.py --no-rs-flag              # Disable new high RS flag
  python3 main.py --config config.yaml      # Use custom config file
        """
    )
    
    # Screener selection
    parser.add_argument(
        "--screener", "-s",
        choices=["minervini", "momentum", "vcp", "all"],
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
    parser.add_argument(
        "--volatility-max",
        type=float,
        help="Maximum volatility ratio (e.g., 0.12 for 12%%)"
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
        config["vcp"]["rs_score_threshold"] = args.rs_threshold
        config["momentum"]["min_rs_score"] = args.rs_threshold
    if args.volatility_max:
        config["vcp"]["volatility_max"] = args.volatility_max
    if args.tickers:
        config["custom_tickers"] = args.tickers
    elif args.file:
        config["tickers_file"] = args.file
        
    if args.verbose:
        config["verbose"] = True
    
    # Run selected screener(s)
    if args.screener == "all":
        run_all_screeners(config)
    elif args.screener == "minervini":
        run_minervini(config)
    elif args.screener == "momentum":
        run_momentum(config)
    elif args.screener == "vcp":
        run_vcp(config)


if __name__ == "__main__":
    main()
