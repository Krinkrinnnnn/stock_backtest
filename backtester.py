"""
VCP + RS Strategy Backtester using backtrader
=============================================
Uses backtrader library for reliable, event-driven backtesting.
"""

import matplotlib
matplotlib.use('Agg')  # Must be set before importing any matplotlib-dependent libraries

import backtrader as bt
import yfinance as yf
import pandas as pd
from datetime import datetime
from positioning.position_sizer import calculate_position_size


# ==========================================
# RECOMMENDED PROGRAMMATIC TRADER PARAMETERS
# ==========================================
VCP_STRATEGY_PARAMS = {
    # --- Entry Signal Parameters ---
    "rs_period": 252,              # Lookback period for RS calculation
    "rs_score_threshold": 60,      # Minimum RS Percentile (0-100)
    "rs_line_threshold": 1.0,      # RS ratio vs benchmark (1.0 = equal)
    "volatility_period": 20,       # ATR period for volatility
    "volatility_max": 0.08,        # Max volatility (8% of price)
    "breakout_period": 20,         # N-day high for breakout
    "force_index_period": 13,      # Elder Force Index period
    "ema_short_period": 13,        # EMA for short-term trend
    "ema_long_period": 120,        # EMA for long-term trend
    "sma_period": 50,              # SMA for trend filter

    # --- Risk Management Parameters ---
    "risk_per_trade_pct": 0.02,         # Default: 2% of total account maximum drawdown
    "max_drawdown_per_trade_pct": 0.08, # Stop-loss/max drawdown per trade: 8%
    "max_position_size_pct": 0.40,      # Maximum position size: 40% of total account
    "trailing_stop_pct": 0.10,          # Trailing stop: 10%
    "profit_target_pct": 0.25,          # Take profit: 25%
    "max_holding_days": 60,             # Max holding period
}


class ForceIndex(bt.Indicator):
    """
    Elder Force Index = (Close - Close_prev) * Volume
    Smoothed with EMA over a given period.
    """
    lines = ('forceindex',)
    params = (('period', 13),)

    plotinfo = dict(plot=False)

    def next(self):
        if len(self) < 2:
            self.lines.forceindex[0] = 0
            return
        raw = (self.data.close[0] - self.data.close[-1]) * self.data.volume[0]
        # Simple EMA calculation
        if len(self) <= self.p.period:
            self.lines.forceindex[0] = raw
        else:
            k = 2.0 / (self.p.period + 1)
            self.lines.forceindex[0] = raw * k + self.lines.forceindex[-1] * (1 - k)


class VCPStrategy(bt.Strategy):
    """
    VCP + RS Breakout Strategy for backtrader.
    """
    params = (
        ('rs_period', 252),
        ('rs_score_threshold', 60),
        ('volatility_period', 20),
        ('volatility_max', 0.08),
        ('breakout_period', 20),
        ('force_index_period', 13),
        ('ema_short_period', 13),
        ('ema_long_period', 120),
        ('sma_period', 50),
        ('risk_per_trade_pct', 0.02),
        ('max_drawdown_per_trade_pct', 0.08),
        ('max_position_size_pct', 0.40),
        ('trailing_stop_pct', 0.10),
        ('profit_target_pct', 0.25),
        ('max_holding_days', 60),
    )

    def __init__(self):
        # Indicators
        self.ema_short = bt.indicators.EMA(self.data.close, period=self.p.ema_short_period)
        self.ema_long = bt.indicators.EMA(self.data.close, period=self.p.ema_long_period)
        self.sma = bt.indicators.SMA(self.data.close, period=self.p.sma_period)
        
        # ATR for volatility
        self.atr = bt.indicators.ATR(self.data, period=self.p.volatility_period)
        
        # N-day high for breakout
        self.highest = bt.indicators.Highest(self.data.high, period=self.p.breakout_period)
        
        # Elder Force Index (custom)
        self.force_index = ForceIndex(self.data, period=self.p.force_index_period)
        
        # Volume SMA for volume filter
        self.volume_sma = bt.indicators.SMA(self.data.volume, period=20)

        # Trade tracking
        self.order = None
        self.entry_price = None
        self.peak_price = None
        self.holding_days = 0
        self.trade_count = 0
        self.wins = 0
        self.losses = 0
        self.total_pnl = 0
        
        # Store trade signals for chart plotting
        self.trade_signals = []  # List of (date, price, type) tuples

    def log(self, txt, dt=None):
        dt = dt or self.datas[0].datetime.date(0)
        print(f'  [{dt}] {txt}')

    def notify_order(self, order):
        if order.status in [order.Submitted, order.Accepted]:
            return
        if order.status in [order.Completed]:
            if order.isbuy():
                self.log(f'BUY EXECUTED  Price: ${order.executed.price:.2f}  '
                         f'Size: {order.executed.size:.0f}  '
                         f'Cost: ${order.executed.value:.2f}')
                self.entry_price = order.executed.price
                self.peak_price = order.executed.price
                self.holding_days = 0
                # Record buy signal
                buy_date = bt.num2date(order.executed.dt)
                self.trade_signals.append({
                    'date': buy_date,
                    'price': order.executed.price,
                    'type': 'BUY'
                })
            else:
                pnl = (order.executed.price - self.entry_price) * abs(order.executed.size)
                pnl_pct = (order.executed.price / self.entry_price - 1) * 100
                self.log(f'SELL EXECUTED Price: ${order.executed.price:.2f}  '
                         f'PnL: ${pnl:.2f} ({pnl_pct:+.1f}%)')
                self.trade_count += 1
                self.total_pnl += pnl
                if pnl > 0:
                    self.wins += 1
                else:
                    self.losses += 1
                # Record sell signal
                sell_date = bt.num2date(order.executed.dt)
                self.trade_signals.append({
                    'date': sell_date,
                    'price': order.executed.price,
                    'type': 'SELL',
                    'pnl_pct': pnl_pct
                })
        elif order.status in [order.Canceled, order.Margin, order.Rejected]:
            self.log(f'Order Canceled/Margin/Rejected: {order.Status[order.status]}')
        self.order = None

    def notify_trade(self, trade):
        if not trade.isclosed:
            return
        self.log(f'TRADE CLOSED   Gross: ${trade.pnl:.2f}  Net: ${trade.pnlcomm:.2f}')

    def _check_entry(self):
        """
        Check entry conditions:
        1. Price above SMA50 (uptrend)
        2. EMA13 above EMA120 (short-term bullish)
        3. ATR/volatility below threshold (tight range)
        4. Force Index positive (buying pressure)
        5. Breakout: close above N-day high
        6. Volume above average
        """
        close = self.data.close[0]
        sma50 = self.sma[0]
        ema13 = self.ema_short[0]
        ema120 = self.ema_long[0]
        atr = self.atr[0]
        highest = self.highest[-1]  # Previous bar's N-day high
        force = self.force_index[0]
        vol = self.data.volume[0]
        vol_avg = self.volume_sma[0]

        # Trend filter: price above SMA50
        if close < sma50:
            return False

        # Short-term bullish: EMA13 > EMA120
        if ema13 < ema120:
            return False

        # Volatility check: ATR must be below threshold
        if atr / close > self.p.volatility_max:
            return False

        # Force Index must be positive
        if force <= 0:
            return False

        # Breakout: close above previous N-day high
        if close < highest:
            return False

        # Volume filter: above average
        if vol_avg > 0 and vol < vol_avg * 1.0:
            return False

        return True

    def _check_exit(self):
        """
        Check exit conditions:
        1. Stop-loss
        2. Trailing stop
        3. Profit target
        4. Max holding days
        5. Price below EMA13
        """
        close = self.data.close[0]

        if self.entry_price is None:
            return False, None

        # Stop-loss
        if close <= self.entry_price * (1 - self.p.max_drawdown_per_trade_pct):
            return True, 'StopLoss'

        # Trailing stop
        self.peak_price = max(self.peak_price, close)
        trailing_threshold = self.peak_price * (1 - self.p.trailing_stop_pct)
        if close <= trailing_threshold:
            return True, 'TrailingStop'

        # Profit target
        if close >= self.entry_price * (1 + self.p.profit_target_pct):
            return True, 'ProfitTarget'

        # Max holding days
        if self.holding_days >= self.p.max_holding_days:
            return True, 'MaxHolding'

        # Price below EMA13
        if close < self.ema_short[0]:
            return True, 'EMA13Break'

        return False, None

    def next(self):
        # If we have an open position
        if self.position:
            self.holding_days += 1
            should_exit, reason = self._check_exit()
            if should_exit:
                self.log(f'EXIT SIGNAL: {reason}  Price: ${self.data.close[0]:.2f}')
                self.close()
        else:
            # Check entry
            if self._check_entry():
                # Use positioning module to calculate size
                size = calculate_position_size(
                    total_equity=self.broker.getvalue(),
                    available_cash=self.broker.getcash(),
                    entry_price=self.data.close[0],
                    risk_per_trade_pct=self.p.risk_per_trade_pct,
                    max_drawdown_per_trade_pct=self.p.max_drawdown_per_trade_pct,
                    max_position_size_pct=self.p.max_position_size_pct
                )
                
                if size > 0:
                    self.log(f'ENTRY SIGNAL  Price: ${self.data.close[0]:.2f}  Size: {size}')
                    self.buy(size=size)


class PandasData(bt.feeds.PandasData):
    """
    Custom Pandas data feed for backtrader.
    """
    params = (
        ('datetime', None),
        ('open', 'Open'),
        ('high', 'High'),
        ('low', 'Low'),
        ('close', 'Close'),
        ('volume', 'Volume'),
        ('openinterest', -1),
    )


def run_backtest(symbol, years=3, initial_capital=100000, params=None, plot=True):
    """
    Run backtest using backtrader.
    """
    p = params or VCP_STRATEGY_PARAMS

    # Fetch data
    print(f"\nFetching {years} years of data for {symbol}...")
    period = f"{years}y"
    ticker = yf.Ticker(symbol)
    df = ticker.history(period=period)
    if df.empty:
        print(f"Error: No data for {symbol}")
        return None

    print(f"Loaded {len(df)} trading days from {df.index[0].strftime('%Y-%m-%d')} to {df.index[-1].strftime('%Y-%m-%d')}")

    # Setup backtrader
    cerebro = bt.Cerebro()
    cerebro.broker.setcash(initial_capital)
    cerebro.broker.setcommission(commission=0.001)  # 0.1% commission

    # Add data
    data = PandasData(dataname=df)
    cerebro.adddata(data, name=symbol)

    # Add strategy
    cerebro.addstrategy(
        VCPStrategy,
        rs_period=p['rs_period'],
        rs_score_threshold=p['rs_score_threshold'],
        volatility_period=p['volatility_period'],
        volatility_max=p['volatility_max'],
        breakout_period=p['breakout_period'],
        force_index_period=p['force_index_period'],
        ema_short_period=p['ema_short_period'],
        ema_long_period=p['ema_long_period'],
        sma_period=p['sma_period'],
        risk_per_trade_pct=p['risk_per_trade_pct'],
        max_drawdown_per_trade_pct=p['max_drawdown_per_trade_pct'],
        max_position_size_pct=p['max_position_size_pct'],
        trailing_stop_pct=p['trailing_stop_pct'],
        profit_target_pct=p['profit_target_pct'],
        max_holding_days=p['max_holding_days'],
    )

    # Add analyzers
    cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name='sharpe')
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name='drawdown')
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name='trades')
    cerebro.addanalyzer(bt.analyzers.Returns, _name='returns')
    cerebro.addanalyzer(bt.analyzers.TimeReturn, _name='time_return')

    # Run
    print("\nRunning backtest...")
    print(f"  Initial Capital:  ${initial_capital:,.2f}")
    print(f"  Strategy: VCP Breakout + RS")
    print(f"  EMA Short: {p['ema_short_period']} | EMA Long: {p['ema_long_period']} | SMA: {p['sma_period']}")
    print(f"  Breakout: {p['breakout_period']}-day high | ATR Period: {p['volatility_period']}")
    print(f"  Account Risk per Trade: {p['risk_per_trade_pct']*100:.1f}% | Stop Loss: {p['max_drawdown_per_trade_pct']*100:.0f}% | Trailing: {p['trailing_stop_pct']*100:.0f}%")
    print(f"  Max Position Size: {p['max_position_size_pct']*100:.0f}% | Target: {p['profit_target_pct']*100:.0f}% | Max Holding: {p['max_holding_days']} days")
    print("-" * 70)

    results = cerebro.run()
    strat = results[0]

    # Results
    final_value = cerebro.broker.getvalue()
    total_return = (final_value / initial_capital - 1) * 100

    # Analyzers
    sharpe = strat.analyzers.sharpe.get_analysis()
    dd = strat.analyzers.drawdown.get_analysis()
    ta = strat.analyzers.trades.get_analysis()
    returns = strat.analyzers.returns.get_analysis()

    # Calculate Sortino Ratio (annualized)
    # Get daily returns from TimeReturn analyzer
    daily_returns = list(strat.analyzers.time_return.get_analysis().values())
    if len(daily_returns) > 0:
        import numpy as np
        # Only take negative returns
        downside_returns = [r for r in daily_returns if r < 0]
        downside_risk = np.std(downside_returns) * np.sqrt(252) if len(downside_returns) > 0 else 0
        annualized_return = np.mean(daily_returns) * 252
        sortino_ratio = (annualized_return) / downside_risk if downside_risk > 0 else 0
    else:
        sortino_ratio = 0

    # --------------------------------------------------------------------
    # FORMAT RESULTS & SAVE TO FOLDERS
    # --------------------------------------------------------------------
    import os
    from datetime import datetime

    # Prepare result folder structure
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    parent_dir = "back_test_result"
    child_dir = os.path.join(parent_dir, f"{symbol}_{timestamp}")
    os.makedirs(child_dir, exist_ok=True)

    summary_text = []
    summary_text.append("\n" + "=" * 70)
    summary_text.append(f"  VCP + RS STRATEGY BACKTEST RESULTS — {symbol}")
    summary_text.append("=" * 70)

    summary_text.append("\n  [ PERFORMANCE SUMMARY ]")
    summary_text.append(f"  {'Initial Capital:':<30} ${initial_capital:>12,.2f}")
    summary_text.append(f"  {'Final Equity:':<30} ${final_value:>12,.2f}")
    summary_text.append(f"  {'Total Return:':<30} {total_return:>11.2f}%")

    sharpe_ratio = sharpe.get('sharperatio', 0) or 0
    max_drawdown = dd.get('max', {}).get('drawdown', 0)
    
    # Calculate Recovery Factor
    recovery_factor = (total_return) / max_drawdown if max_drawdown > 0 else float('inf')

    summary_text.append(f"  {'Sharpe Ratio:':<30} {sharpe_ratio:>12.3f}")
    summary_text.append(f"  {'Sortino Ratio:':<30} {sortino_ratio:>12.3f}")
    summary_text.append(f"  {'Max Drawdown:':<30} {max_drawdown:>11.2f}%")
    summary_text.append(f"  {'Recovery Factor:':<30} {recovery_factor:>12.2f}")

    summary_text.append("\n  [ TRADE STATISTICS ]")
    total_trades = ta.get('total', {}).get('total', 0)
    won = ta.get('won', {}).get('total', 0)
    lost = ta.get('lost', {}).get('total', 0)
    win_rate = (won / total_trades * 100) if total_trades > 0 else 0
    avg_win = ta.get('won', {}).get('pnl', {}).get('average', 0)
    avg_loss = ta.get('lost', {}).get('pnl', {}).get('average', 0)
    profit_factor = abs(
        ta.get('won', {}).get('pnl', {}).get('total', 0) /
        ta.get('lost', {}).get('pnl', {}).get('total', 1)
    ) if lost > 0 else float('inf')

    summary_text.append(f"  {'Total Trades:':<30} {total_trades:>12d}")
    summary_text.append(f"  {'Won:':<30} {won:>12d}")
    summary_text.append(f"  {'Lost:':<30} {lost:>12d}")
    summary_text.append(f"  {'Win Rate:':<30} {win_rate:>11.1f}%")
    summary_text.append(f"  {'Avg Win ($):':<30} ${avg_win:>11.2f}")
    summary_text.append(f"  {'Avg Loss ($):':<30} ${avg_loss:>11.2f}")
    summary_text.append(f"  {'Profit Factor:':<30} {profit_factor:>12.2f}")

    if total_trades > 0:
        avg_duration = ta.get('len', {}).get('average', 0)
        summary_text.append(f"  {'Avg Holding (bars):':<30} {avg_duration:>12.1f}")

    summary_text.append("\n" + "=" * 70)
    
    # Print to console and write to txt
    full_summary = "\n".join(summary_text)
    print(full_summary)
    
    summary_file = os.path.join(child_dir, f"{symbol}_summary.txt")
    with open(summary_file, "w", encoding="utf-8") as f:
        f.write(full_summary)
    print(f"[SUCCESS] Summary saved to: {summary_file}")

    # QuantStats Integration
    try:
        import quantstats as qs
        import pandas as pd
        
        # Extract daily returns
        portfolio_returns = pd.Series(strat.analyzers.time_return.get_analysis())
        portfolio_returns.index = pd.to_datetime(portfolio_returns.index)
        
        # Ensure we don't have timezone issues
        if portfolio_returns.index.tz is not None:
            portfolio_returns.index = portfolio_returns.index.tz_localize(None)
            
        # Download SPY benchmark data for the same period
        print(f"\nGenerating QuantStats HTML report (vs SPY)...")
        benchmark = yf.download("SPY", start=portfolio_returns.index.min(), end=portfolio_returns.index.max(), progress=False)
        
        if not benchmark.empty:
            # Handle multi-index column from yfinance
            if isinstance(benchmark.columns, pd.MultiIndex):
                bench_close = benchmark['Close']['SPY']
            else:
                bench_close = benchmark['Close']
                
            bench_returns = bench_close.pct_change().dropna()
            
            # Ensure indices match timezone-wise
            if bench_returns.index.tz is not None:
                bench_returns.index = bench_returns.index.tz_localize(None)
                
            # Align indices
            idx = portfolio_returns.index.intersection(bench_returns.index)
            port_ret_aligned = portfolio_returns.loc[idx]
            bench_ret_aligned = bench_returns.loc[idx]
            
            report_name = os.path.join(child_dir, f"backtest_report_{symbol}.html")
            qs.reports.html(port_ret_aligned, benchmark=bench_ret_aligned, output=report_name, title=f"{symbol} VCP Strategy vs SPY")
            print(f"[SUCCESS] Full performance report generated: {report_name}")
        else:
            print("Failed to download benchmark data for QuantStats.")
            
    except ImportError:
        print("\nTip: Install quantstats (pip install quantstats) to generate a detailed HTML performance report comparing your strategy against SPY!")
    except Exception as e:
        print(f"\nCould not generate QuantStats report: {e}")

    # Plot and save image (do not show interactive window)
    if plot:
        try:
            import matplotlib
            matplotlib.use('Agg')
            import matplotlib.pyplot as plt
            
            # Since backtrader often attempts GUI operations regardless of Agg,
            # we need to disable the viewer by passing multiple flags
            figs = cerebro.plot(
                style='candlestick',
                barup='white', barupfill=False,
                bardown='#EF5350', bardownfill=True,
                volume=False,
                iplot=False,
            )
            
            if figs and len(figs) > 0 and len(figs[0]) > 0:
                fig = figs[0][0]
                # Try to safely adjust size or just use default if TK fails
                try:
                    fig.set_size_inches(16, 10)
                except:
                    pass
                
                chart_path = os.path.join(child_dir, f"{symbol}_chart.png")
                # Try to use tight layout safely
                try:
                    fig.savefig(chart_path, bbox_inches='tight', dpi=100)
                except:
                    fig.savefig(chart_path, dpi=100)
                print(f"[SUCCESS] Chart saved to: {chart_path}")
                
            plt.close('all')
                
        except Exception as e:
            print(f"Could not save chart: {e}")

    return {
        'final_value': final_value,
        'total_return': total_return,
        'sharpe_ratio': sharpe_ratio,
        'max_drawdown': max_drawdown,
        'total_trades': total_trades,
        'win_rate': win_rate,
        'profit_factor': profit_factor,
        'sortino_ratio': sortino_ratio,
        'recovery_factor': recovery_factor,
        'trade_signals': strat.trade_signals,
        'result_dir': child_dir,
        'df': df,
    }


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="VCP + RS Strategy Backtester (backtrader)")
    parser.add_argument("--symbol", type=str, default="AAPL", help="Stock symbol")
    parser.add_argument("--years", type=int, default=3, help="Years of data")
    parser.add_argument("--capital", type=float, default=100000, help="Initial capital")
    parser.add_argument("--no-plot", action="store_true", help="Disable plotting")
    args = parser.parse_args()

    run_backtest(args.symbol, args.years, args.capital, plot=not args.no_plot)
