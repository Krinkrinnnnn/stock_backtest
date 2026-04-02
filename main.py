import argparse
import os
from datetime import datetime
import pandas as pd
import numpy as np
from fetch_data import fetch_stock_data
from vcp_rs_analyzer import calculate_daily_signals, print_signal_summary
from chart_plotter import MarketSmithChart
from backtester import run_backtest, VCP_STRATEGY_PARAMS

# ==========================================
# SYSTEM PARAMETERS & CONFIGURATION
# ==========================================
CONFIG = {
    # Data Settings
    "symbols": ["AAPL"],         # Target stock symbols (e.g., ["AAPL", "TSLA", "NVDA"])
    "years_of_data": 2,          # Number of years of historical data to fetch
    "benchmark": "^GSPC",        # Benchmark symbol for RS calculation (default: S&P 500)
    
    # Feature Flags
    "print_summary": True,       # Whether to print the signal summary table in console
    "print_latest_data": True,   # Whether to print the latest day's data & signals
    "enable_plotting": True,     # Whether to render the visual chart
    "save_chart": True,          # Whether to save the chart as a PNG image
    "run_backtest": False,       # Whether to run the strategy backtest
    "initial_capital": 100000,   # Initial capital for backtesting
    
    # Chart Settings
    "chart_figsize": (22, 16),   # Dimensions of the generated chart (larger for readability)
    "chart_show_days": 180,      # Number of recent days to show (more visible candles)
    
    # Backtest Settings (override VCP_STRATEGY_PARAMS if needed)
    "custom_params": None,       # None = use default VCP_STRATEGY_PARAMS
}
# ==========================================


def run_analysis(config, session_dir=None):
    """
    Main execution pipeline using the provided configuration.
    """
    for symbol in config["symbols"]:
        run_single_analysis(config, symbol, session_dir)


def run_single_analysis(config, symbol, session_dir=None):
    """
    Analysis pipeline for a single stock symbol.
    """
    years = config["years_of_data"]
    benchmark = config["benchmark"]
    
    print(f"Starting analysis for {symbol} ({years} years)")
    print("-" * 50)
    
    # 1. Fetch Data
    df, benchmark_df = fetch_stock_data(symbol, years, benchmark)
    
    if df is None:
        print(f"Failed to fetch data for {symbol}. Exiting.")
        return
        
    print(f"Successfully loaded {len(df)} trading days.")
    
    # 2. Analyze Signals (VCP, RS, etc.)
    df_with_signals = calculate_daily_signals(df, benchmark_df)
    
    # 3. Print Summaries
    if config["print_summary"]:
        print_signal_summary(df_with_signals)
        
    if config["print_latest_data"]:
        latest = df_with_signals.iloc[-1]
        print(f"\nLatest Data ({df_with_signals.index[-1].strftime('%Y-%m-%d')}):")
        print(f"  Close Price: ${latest['Close']:.2f}")
        print(f"  RS Line: {latest['RS_Line']:.1f}")
        print(f"  RS Score: {latest['RS_Score']:.1f}")
        print(f"  Volatility: {latest['Volatility']:.2f}%")
        print(f"  Force Index: {latest['Force_Index']:.0f}")
        print(f"  VCP Signal: {'Yes' if latest['VCP_Signal'] else 'No'}")
        print(f"  Breakout Signal: {'Yes' if latest['Signal'] else 'No'}")

    # 4. Run Backtest
    backtest_signals = []
    bt_result_dir = None
    if config["run_backtest"]:
        bt_result = run_backtest(
            symbol=symbol,
            years=years,
            initial_capital=config["initial_capital"],
            params=config["custom_params"],
            plot=False
        )
        if bt_result:
            backtest_signals = bt_result.get('trade_signals', [])
            bt_result_dir = bt_result.get('result_dir', None)

    # 5. Plot Chart (always generate chart)
    if config["enable_plotting"] or backtest_signals:
        show_days = config.get("chart_show_days", 180)
        # For backtest, show more days to see all trade signals
        if backtest_signals:
            show_days = 365
        chart = MarketSmithChart(show_days=show_days)
        save_path = None
        if config["save_chart"]:
            if bt_result_dir:
                # Save chart in back_test_result folder with summary.txt
                save_path = os.path.join(bt_result_dir, f"{symbol}_chart.png")
            elif session_dir:
                # Save chart in session folder
                save_path = os.path.join(session_dir, f"{symbol}_analysis.png")
            else:
                # Fallback: save chart in output folder
                output_dir = "output"
                os.makedirs(output_dir, exist_ok=True)
                save_path = os.path.join(output_dir, f"{symbol}_analysis.png")
        
        print("\nRendering chart...")
        chart.plot(df_with_signals, symbol, save_path=save_path, trade_signals=backtest_signals)


if __name__ == "__main__":
    # Optional CLI arguments to override config
    parser = argparse.ArgumentParser(description="Stock VCP & RS Analysis System")
    parser.add_argument("--symbol", type=str, help="Stock symbol to analyze")
    parser.add_argument("--symbols", type=str, nargs="+", help="Multiple stock symbols to analyze")
    parser.add_argument("--years", type=int, help="Years of data to fetch")
    parser.add_argument("--no-plot", action="store_true", help="Disable chart plotting")
    parser.add_argument("--backtest", action="store_true", help="Run strategy backtest")
    parser.add_argument("--capital", type=float, help="Initial capital for backtesting")
    
    args = parser.parse_args()
    
    # Apply CLI overrides if provided
    if args.symbols:
        CONFIG["symbols"] = [s.upper() for s in args.symbols]
    elif args.symbol:
        CONFIG["symbols"] = [args.symbol.upper()]
    if args.years:
        CONFIG["years_of_data"] = args.years
    if args.no_plot:
        CONFIG["enable_plotting"] = False
        CONFIG["save_chart"] = False
    if args.backtest:
        CONFIG["run_backtest"] = True
        CONFIG["years_of_data"] = max(CONFIG["years_of_data"], 3)
    if args.capital:
        CONFIG["initial_capital"] = args.capital
    
    # Create session folder with all tickers in the name
    session_dir = None
    if CONFIG["save_chart"] and not CONFIG["run_backtest"]:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        ticker_str = "_".join(CONFIG["symbols"])
        session_name = f"session_{ticker_str}_{timestamp}"
        session_dir = os.path.join("output", session_name)
        os.makedirs(session_dir, exist_ok=True)
        print(f"Session output folder: {session_dir}")
        
    run_analysis(CONFIG, session_dir=session_dir)
