"""
Backtest: Spring Trap Strategy (MACD + RSI + 200MA)
===================================================
Backtest the Oversold Spring Trap strategy using the backtesting library.

Uses the same RSI and MACD calculations from oversold_screener.py (DRY).

Usage:
    python backtest_oversold.py AAPL
    python backtest_oversold.py NVDA TSLA
    python backtest_oversold.py --tickers AAPL NVDA
"""

import sys
import os

import matplotlib
matplotlib.use('Agg')
import matplotlib.font_manager as fm
try:
    for font_path in [
        '/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf',
        'C:/Windows/Fonts/arial.ttf',
        '/System/Library/Fonts/Arial.ttf',
    ]:
        if os.path.exists(font_path):
            fm.fontManager.addfont(font_path)
            break
except Exception:
    pass
matplotlib.rcParams['font.family'] = 'Liberation Sans'

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# DRY: Import RSI and MACD from oversold_screener
from screen.oversold_screener import calc_rsi, calc_macd
from fetch_data import fetch_stock_data

# Backtesting framework
from backtesting import Backtest, Strategy


# ==========================================
# WRAPPER FUNCTIONS FOR BACKTESTING LIBRARY
# ==========================================
# The backtesting library passes numpy arrays, not pandas Series.
# These wrappers convert arrays to Series before calling the original functions.

def rsi_for_backtest(close, period=14):
    """Wrapper for calc_rsi to work with backtesting library's numpy arrays."""
    close_series = pd.Series(close)
    return calc_rsi(close_series, period).values


def macd_for_backtest(close, fast=12, slow=26, signal=9):
    """Wrapper for calc_macd to work with backtesting library's numpy arrays."""
    close_series = pd.Series(close)
    macd_df = calc_macd(close_series, fast, slow, signal)
    # Return transposed to (n_lines, n_data) for backtesting library
    return macd_df.values.T


# ==========================================

class SpringTrapStrategy(Strategy):
    """
    Spring Trap Strategy (MACD + RSI + 200MA)
    
    Entry Conditions:
        - Close > 200-day SMA
        - RSI(14) < 30
        - MACD_Hist < 0 AND MACD_Hist[-1] > MACD_Hist[-2] (ticking up)
    
    Exit Conditions:
        - Stop Loss: Close < Entry_Low * 0.98 (2% below entry day low)
        - Take Profit A: High > 50-day SMA
        - Take Profit B: RSI > 65
        - Time Stop: Bar index > Entry_Bar_Index + 8
    """
    
    # Class variables to track position state
    entry_low = None
    entry_bar_index = None
    
    def init(self):
        """Pre-calculate indicators using wrapper functions."""
        close = self.data.Close
        
        # RSI (using wrapper for backtesting library)
        self.rsi = self.I(rsi_for_backtest, close, 14)
        
        # MACD Histogram (using wrapper)
        self.macd_line, self.signal_line, self.macd_hist = self.I(macd_for_backtest, close)
        
        # Moving Averages (native numpy)
        self.sma50 = self.I(lambda x: pd.Series(x).rolling(50).mean(), close)
        self.sma200 = self.I(lambda x: pd.Series(x).rolling(200).mean(), close)
        
    def next(self):
        """Daily execution logic."""
        # Get current values
        close = self.data.Close[-1]
        low = self.data.Low[-1]
        high = self.data.High[-1]
        
        rsi = self.rsi[-1]
        macd_hist = self.macd_hist[-1]
        macd_hist_prev = self.macd_hist[-2] if len(self.macd_hist) > 1 else 0
        sma50 = self.sma50[-1]
        sma200 = self.sma200[-1]
        
        # Skip if indicators not ready
        if np.isnan(sma50) or np.isnan(sma200):
            return
        
        # ── ENTRY LOGIC ──
        if not self.position:
            # Must be above 200MA (long-term trend intact)
            if close <= sma200:
                return
            
            # Must be oversold (RSI < 40 for testing, usually 30)
            if rsi >= 40:
                return
            
            # MACD Histogram must be negative but improving (ticking up)
            if not (macd_hist < 0 and macd_hist > macd_hist_prev):
                return
            
            # Execute entry
            self.buy()
            
            # Record entry day low for stop loss
            SpringTrapStrategy.entry_low = low
            # Record entry bar index for time stop
            SpringTrapStrategy.entry_bar_index = len(self.data) - 1
            
        # ── EXIT LOGIC ──
        else:
            # Stop Loss: Close < Entry_Low * 0.98
            if SpringTrapStrategy.entry_low and close < SpringTrapStrategy.entry_low * 0.98:
                self.position.close()
                SpringTrapStrategy.entry_low = None
                SpringTrapStrategy.entry_bar_index = None
                return
            
            # Take Profit A: High > 50MA
            if high > sma50:
                self.position.close()
                SpringTrapStrategy.entry_low = None
                SpringTrapStrategy.entry_bar_index = None
                return
            
            # Take Profit B: RSI > 65
            if rsi > 65:
                self.position.close()
                SpringTrapStrategy.entry_low = None
                SpringTrapStrategy.entry_bar_index = None
                return
            
            # Time Stop: Exit if held > 8 bars
            if SpringTrapStrategy.entry_bar_index is not None:
                bars_held = len(self.data) - 1 - SpringTrapStrategy.entry_bar_index
                if bars_held > 8:
                    self.position.close()
                    SpringTrapStrategy.entry_low = None
                    SpringTrapStrategy.entry_bar_index = None
                    return


# ==========================================
# BACKTEST RUNNER
# ==========================================

def run_backtest(tickers, period="5y", cash=10000, commission=0.002, plot=True):
    """
    Run backtest for given tickers.
    
    Args:
        tickers: List of ticker symbols or single string
        period: yfinance period string (default: 5y)
        cash: Starting capital (default: $10,000)
        commission: Commission rate (default: 0.2% = 0.002)
        plot: Whether to generate HTML plot
    """
    if isinstance(tickers, str):
        tickers = [tickers]
    
    # Ensure output directory
    ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
    OUTPUT_DIR = os.path.join(ROOT_DIR, "back_test_result")
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    for ticker in tickers:
        ticker = ticker.upper().strip()
        print(f"\n{'='*60}")
        print(f"  Backtesting: {ticker} — Spring Trap Strategy")
        print(f"  Period: {period} | Cash: ${cash:,.0f} | Commission: {commission*100:.1f}%")
        print(f"{'='*60}")
        
        # Download data
        try:
            years = int(period[:-1]) if period.endswith('y') else 5
        except:
            years = 5
        
        df, _ = fetch_stock_data(ticker, years)
        
        if df is None or df.empty:
            print(f"  No data for {ticker}")
            continue
            
        # Revert the capitalization applied by fetch_data.py so backtesting logic matches
        df.columns = [c.capitalize() for c in df.columns]
        
        # Ensure required columns exist
        required = ['Open', 'High', 'Low', 'Close', 'Volume']
        if not all(col in df.columns for col in required):
            print(f"  Missing required columns for {ticker}")
            continue
        
        # Drop NaN rows (needed for 200MA)
        df = df.dropna()
        
        print(f"  {len(df)} trading days loaded")
        
        if len(df) < 200:
            print(f"  Warning: Only {len(df)} days of data. The Spring Trap strategy requires at least 200 days")
            print(f"  just to calculate the 200 SMA entry filter. Consider using a larger --years parameter.")
        
        # Run backtest
        try:
            bt = Backtest(
                df,
                SpringTrapStrategy,
                cash=cash,
                commission=commission,
                exclusive_orders=True
            )
            
            stats = bt.run()
            
            # Extract stats
            start_dt = stats.get('Start', 'N/A')
            end_dt = stats.get('End', 'N/A')
            dur = stats.get('Duration', 'N/A')
            total_return = stats.get('Return [%]', 0)
            sharpe = stats.get('Sharpe Ratio', 0)
            sortino = stats.get('Sortino Ratio', 0)
            max_dd = stats.get('Max. Drawdown [%]', 0)
            total_trades = stats.get('# Trades', 0)
            win_rate = stats.get('Win Rate [%]', 0)
            avg_trade = stats.get('Avg. Trade [%]', 0)
            best_trade = stats.get('Best Trade [%]', 0)
            worst_trade = stats.get('Worst Trade [%]', 0)
            
            # Final equity
            final_equity = cash * (1 + total_return / 100)
            
            # Win / Loss counts
            trades_df = stats.get('_trades')
            won = int(trades_df[trades_df['ReturnPct'] > 0].shape[0]) if trades_df is not None and not trades_df.empty else 0
            lost = int(trades_df[trades_df['ReturnPct'] <= 0].shape[0]) if trades_df is not None and not trades_df.empty else 0
            
            avg_win_pct = trades_df[trades_df['ReturnPct'] > 0]['ReturnPct'].mean() * 100 if won > 0 else 0
            avg_loss_pct = trades_df[trades_df['ReturnPct'] <= 0]['ReturnPct'].mean() * 100 if lost > 0 else 0
            profit_factor = abs(
                trades_df[trades_df['ReturnPct'] > 0]['PnL'].sum() /
                trades_df[trades_df['ReturnPct'] <= 0]['PnL'].sum()
            ) if lost > 0 and trades_df[trades_df['ReturnPct'] <= 0]['PnL'].sum() != 0 else float('inf')
            
            # Save summary to file
            from datetime import datetime as dt
            timestamp = dt.now().strftime("%Y%m%d_%H%M%S")
            child_dir = os.path.join(OUTPUT_DIR, f"{ticker}_{timestamp}")
            os.makedirs(child_dir, exist_ok=True)
            
            summary_text = []
            summary_text.append("\n" + "=" * 70)
            summary_text.append(f"  OVERSOLD SPRING TRAP STRATEGY BACKTEST RESULTS - {ticker}")
            summary_text.append("=" * 70)
            
            if total_trades == 0:
                summary_text.append("\n  [ PERFORMANCE SUMMARY ]")
                summary_text.append(f"  {'Start Date:':<30} {start_dt}")
                summary_text.append(f"  {'End Date:':<30} {end_dt}")
                summary_text.append(f"  {'Duration:':<30} {dur}")
                summary_text.append(f"\n  [ NO TRADES EXECUTED ]")
                summary_text.append("  This strategy requires the stock to be above its 200-day moving average (SMA200).")
                summary_text.append(f"  With a {period} backtest, the first 200 days are spent calculating the SMA200,")
                summary_text.append("  leaving very little time for actual trading. In a downtrend (e.g. INTC),")
                summary_text.append("  the price remains below the 200 SMA, yielding 0 valid entry signals.")
                summary_text.append("  Try adjusting parameters or using a longer period (e.g., --years 3).")
            else:
                summary_text.append("\n  [ PERFORMANCE SUMMARY ]")
                summary_text.append(f"  {'Initial Capital:':<30} ${cash:>12,.2f}")
                summary_text.append(f"  {'Final Equity:':<30} ${final_equity:>12,.2f}")
                summary_text.append(f"  {'Total Return:':<30} {total_return:>11.2f}%")
                summary_text.append(f"  {'Start Date:':<30} {start_dt}")
                summary_text.append(f"  {'End Date:':<30} {end_dt}")
                summary_text.append(f"  {'Duration:':<30} {dur}")
                summary_text.append(f"  {'Sharpe Ratio:':<30} {sharpe:>12.3f}")
                summary_text.append(f"  {'Sortino Ratio:':<30} {sortino:>12.3f}")
                summary_text.append(f"  {'Max Drawdown:':<30} {max_dd:>11.2f}%")
                
                summary_text.append("\n  [ TRADE STATISTICS ]")
                summary_text.append(f"  {'Total Trades:':<30} {total_trades:>12d}")
                summary_text.append(f"  {'Won:':<30} {won:>12d}")
                summary_text.append(f"  {'Lost:':<30} {lost:>12d}")
                summary_text.append(f"  {'Win Rate:':<30} {win_rate:>11.1f}%")
                summary_text.append(f"  {'Avg Win (%):':<30} {avg_win_pct:>11.2f}%")
                summary_text.append(f"  {'Avg Loss (%):':<30} {avg_loss_pct:>11.2f}%")
                summary_text.append(f"  {'Profit Factor:':<30} {profit_factor:>12.2f}")
                summary_text.append(f"  {'Best Trade:':<30} {best_trade:>11.2f}%")
                summary_text.append(f"  {'Worst Trade:':<30} {worst_trade:>11.2f}%")
                
                avg_duration = stats.get('Avg. Trade Duration', 'N/A')
                summary_text.append(f"  {'Avg Holding (bars):':<30} {avg_duration}")
                
                if trades_df is not None and not trades_df.empty:
                    summary_text.append("\n  [ TRADE LOG ]")
                    summary_text.append(f"  {'Entry Date':<12} {'Exit Date':<12} {'Entry Price':>12} {'Exit Price':>12} {'Return %':>10}")
                    summary_text.append(f"  {'-'*12} {'-'*12} {'-'*12} {'-'*12} {'-'*10}")
                    for _, trade in trades_df.iterrows():
                        entry_dt = pd.to_datetime(trade['EntryTime']).strftime('%Y-%m-%d')
                        exit_dt = pd.to_datetime(trade['ExitTime']).strftime('%Y-%m-%d')
                        ret = trade['ReturnPct'] * 100
                        summary_text.append(f"  {entry_dt:<12} {exit_dt:<12} {trade['EntryPrice']:>12.2f} {trade['ExitPrice']:>12.2f} {ret:>+10.2f}%")
            
            summary_text.append("\n" + "=" * 70)
            
            # Print to console and save to file
            full_summary = "\n".join(summary_text)
            print(full_summary)
            
            summary_file = os.path.join(child_dir, f"{ticker}_summary.txt")
            with open(summary_file, "w", encoding="utf-8") as f:
                f.write(full_summary)
            print(f"[SUCCESS] Summary saved to: {summary_file}")
            
            # Save chart
            if plot:
                chart_path = os.path.join(child_dir, f"{ticker}_oversold_backtest.html")
                bt.plot(filename=chart_path, open_browser=False)
                print(f"[SUCCESS] Chart saved to: {chart_path}")
            
        except Exception as e:
            print(f"  Backtest failed for {ticker}: {e}")
            import traceback
            traceback.print_exc()


# ==========================================
# CLI ENTRY POINT
# ==========================================

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Backtest Spring Trap Strategy")
    parser.add_argument("tickers", nargs="*", help="Ticker symbol(s) to backtest")
    parser.add_argument("--tickers", dest="tickers_flag", nargs="+", help="Ticker symbols via --tickers flag")
    parser.add_argument("--period", type=str, default="5y", help="yfinance period (default: 5y)")
    parser.add_argument("--cash", type=float, default=10000, help="Starting cash (default: 10000)")
    parser.add_argument("--commission", type=float, default=0.002, help="Commission rate (default: 0.002 = 0.2%%)")
    
    args = parser.parse_args()
    
    # Handle both positional and --tickers arguments
    tickers = args.tickers
    if args.tickers_flag:
        tickers = args.tickers_flag
    
    if not tickers:
        parser.print_help()
        sys.exit(1)
    
    run_backtest(
        tickers=tickers,
        period=args.period,
        cash=args.cash,
        commission=args.commission
    )
