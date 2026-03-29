"""
Chart Plotter using mplfinance
==============================
Professional stock charts with candlestick, volume, moving averages, RS, and MACD.

Auto-generates:
- Daily chart (always)
- Weekly chart (when data > 1 year)
"""

import pandas as pd
import numpy as np
import mplfinance as mpf
import matplotlib.lines as mlines
from diagram_indicators import MovingAverages


# Custom style: light theme
MARKETSMITH_STYLE = mpf.make_mpf_style(
    base_mpf_style='yahoo',
    gridstyle='-',
    gridcolor='#E5E5E5',
    y_on_right=True,
    rc={
        'font.size': 10,
        'axes.labelsize': 10,
        'figure.facecolor': '#FFFFFF',
        'axes.facecolor': '#FFFFFF',
    }
)


class MarketSmithChart:
    """
    MarketSmith 風格圖表 (mplfinance)
    - Auto daily/weekly chart generation
    - Moving Averages (MA20, MA50, EMA13, EMA120)
    - RS Score subplot
    - MACD subplot
    - Trade signal markers with legend
    """

    COLORS = {
        'bullish': '#00A699',
        'bearish': '#FF333D',
        'ma20': '#FFA500',
        'ma50': '#1E90FF',
        'ema13': '#FF1493',
        'ema120': '#8A2BE2',
        'rs_line': '#0066CC',
        'volume_up': '#00A699',
        'volume_down': '#FF333D',
    }

    def __init__(self, figsize=(22, 16), show_days=180):
        self.figsize = figsize
        self.show_days = show_days
        self.ma = MovingAverages()

    def _prepare_data(self, df):
        """Prepare DataFrame for mplfinance"""
        df = df.copy()
        required = ['Open', 'High', 'Low', 'Close', 'Volume']
        for col in required:
            if col not in df.columns:
                df[col] = 0
        return df

    def _get_addplots(self, df):
        """Build addplot objects for overlays and subplots"""
        addplots = []

        # Moving Averages on main panel
        for col, color, style, width in [
            ('MA20', self.COLORS['ma20'], '-', 1.2),
            ('MA50', self.COLORS['ma50'], '-', 1.5),
            ('EMA13', self.COLORS['ema13'], '--', 1.0),
            ('EMA120', self.COLORS['ema120'], '--', 1.0),
        ]:
            if col in df.columns:
                addplots.append(mpf.make_addplot(
                    df[col], color=color, linestyle=style, width=width,
                    panel=0, ylabel='Price'
                ))

        # RS Score or RS Line on panel 2
        if 'RS_Score' in df.columns:
            addplots.append(mpf.make_addplot(
                df['RS_Score'], color=self.COLORS['rs_line'], width=1.5,
                panel=2, ylabel='RS Score'
            ))
            addplots.append(mpf.make_addplot(
                pd.Series(70, index=df.index), color='#FF6600', linestyle=':',
                width=1, panel=2
            ))
        elif 'RS_Line' in df.columns:
            addplots.append(mpf.make_addplot(
                df['RS_Line'], color=self.COLORS['rs_line'], width=1.5,
                panel=2, ylabel='RS Line'
            ))

        # MACD on panel 3
        close = df['Close']
        ema12 = close.ewm(span=12, adjust=False).mean()
        ema26 = close.ewm(span=26, adjust=False).mean()
        macd_line = ema12 - ema26
        signal_line = macd_line.ewm(span=9, adjust=False).mean()
        macd_hist = macd_line - signal_line

        addplots.append(mpf.make_addplot(
            macd_line, color='#2196F3', width=1.2, panel=3, ylabel='MACD'
        ))
        addplots.append(mpf.make_addplot(
            signal_line, color='#FF9800', width=1.2, panel=3
        ))
        hist_colors = [self.COLORS['bullish'] if v >= 0 else self.COLORS['bearish'] for v in macd_hist]
        addplots.append(mpf.make_addplot(
            macd_hist, type='bar', color=hist_colors, panel=3, alpha=0.5
        ))

        # VCP Signal markers
        if 'VCP_Signal' in df.columns:
            vcp_markers = pd.Series(np.nan, index=df.index)
            vcp_signals = df[df['VCP_Signal'] == True]
            if not vcp_signals.empty:
                for idx in vcp_signals.index:
                    vcp_markers.loc[idx] = df.loc[idx, 'Close'] * 1.02
                addplots.append(mpf.make_addplot(
                    vcp_markers, scatter=True, marker='^', color='#FFA726',
                    markersize=80, panel=0
                ))

        # Buy Signal markers
        if 'Signal' in df.columns:
            buy_markers = pd.Series(np.nan, index=df.index)
            buy_signals = df[df['Signal'] == True]
            if not buy_signals.empty:
                for idx in buy_signals.index:
                    buy_markers.loc[idx] = df.loc[idx, 'Close'] * 1.02
                addplots.append(mpf.make_addplot(
                    buy_markers, scatter=True, marker='*', color='#66BB6A',
                    markersize=200, panel=0
                ))

        return addplots

    def _add_trade_signals(self, df, trade_signals, addplots):
        """Add backtest trade signals (BUY/SELL markers) to chart"""
        if not trade_signals:
            return addplots
        
        buy_markers = pd.Series(np.nan, index=df.index)
        sell_markers = pd.Series(np.nan, index=df.index)
        
        df_tz = df.index.tz
        df_index_naive = df.index.tz_localize(None) if df_tz is not None else df.index
        
        for signal in trade_signals:
            sig_date = pd.Timestamp(signal['date'])
            if sig_date.tz is not None:
                sig_date = sig_date.tz_localize(None)
            
            matching = df_index_naive[df_index_naive >= sig_date]
            if len(matching) > 0:
                idx_naive = matching[0]
                idx = idx_naive.tz_localize(df_tz) if df_tz is not None else idx_naive
                
                if signal['type'] == 'BUY':
                    buy_markers.loc[idx] = df.loc[idx, 'Low'] * 0.98
                    print(f"  BUY  {idx_naive.strftime('%Y-%m-%d')} @ ${signal['price']:.2f}")
                elif signal['type'] == 'SELL':
                    sell_markers.loc[idx] = df.loc[idx, 'High'] * 1.02
                    pnl = signal.get('pnl_pct', 0)
                    print(f"  SELL {idx_naive.strftime('%Y-%m-%d')} @ ${signal['price']:.2f} ({pnl:+.1f}%)")
        
        if buy_markers.notna().any():
            addplots.append(mpf.make_addplot(
                buy_markers, scatter=True, marker='^', color='#2196F3',
                markersize=150, panel=0
            ))
        
        if sell_markers.notna().any():
            addplots.append(mpf.make_addplot(
                sell_markers, scatter=True, marker='v', color='#FF5252',
                markersize=150, panel=0
            ))
        
        return addplots

    def _add_legend(self, fig, ax, df, trade_signals=None):
        """Add legend to upper left corner"""
        legend_handles = []
        
        ma_info = [
            ('MA20', self.COLORS['ma20'], '-'),
            ('MA50', self.COLORS['ma50'], '-'),
            ('EMA13', self.COLORS['ema13'], '--'),
            ('EMA120', self.COLORS['ema120'], '--'),
        ]
        for name, color, style in ma_info:
            if name in df.columns:
                legend_handles.append(mlines.Line2D(
                    [], [], color=color, linestyle=style, linewidth=1.5, label=name
                ))
        
        if trade_signals:
            if any(s['type'] == 'BUY' for s in trade_signals):
                legend_handles.append(mlines.Line2D(
                    [], [], color='#2196F3', marker='^', linestyle='None',
                    markersize=10, label='BUY Entry'
                ))
            if any(s['type'] == 'SELL' for s in trade_signals):
                legend_handles.append(mlines.Line2D(
                    [], [], color='#FF5252', marker='v', linestyle='None',
                    markersize=10, label='SELL Exit'
                ))
        
        legend_handles.append(mlines.Line2D([], [], color=self.COLORS['bullish'], linewidth=2, label='Bullish'))
        legend_handles.append(mlines.Line2D([], [], color=self.COLORS['bearish'], linewidth=2, label='Bearish'))
        
        if legend_handles:
            ax.legend(handles=legend_handles, loc='upper left', fontsize=9,
                      framealpha=0.9, edgecolor='#CCCCCC', ncol=2)

    def _plot_daily(self, df, symbol, save_path, trade_signals=None):
        """Plot daily candlestick chart"""
        df = self._prepare_data(df)
        df = df.dropna(subset=['Open', 'Close', 'High', 'Low'])
        
        # Limit days for readability
        if len(df) > self.show_days:
            df = df.tail(self.show_days)

        addplots = self._get_addplots(df)
        
        if trade_signals:
            addplots = self._add_trade_signals(df, trade_signals, addplots)

        panel_ratios = (5, 1, 1.5, 1.5)

        mc = mpf.make_marketcolors(
            up=self.COLORS['bullish'],
            down=self.COLORS['bearish'],
            edge={'up': self.COLORS['bullish'], 'down': self.COLORS['bearish']},
            wick={'up': self.COLORS['bullish'], 'down': self.COLORS['bearish']},
            volume={'up': self.COLORS['volume_up'], 'down': self.COLORS['volume_down']},
        )

        style = mpf.make_mpf_style(
            marketcolors=mc,
            gridstyle='-',
            gridcolor='#E5E5E5',
            y_on_right=True,
            rc={'figure.facecolor': '#FFFFFF', 'axes.facecolor': '#FFFFFF', 'font.size': 11}
        )

        fig, axes = mpf.plot(
            df,
            type='candle',
            style=style,
            volume=True,
            addplot=addplots,
            figsize=self.figsize,
            panel_ratios=panel_ratios,
            title=f'\n{symbol} - Daily Chart',
            returnfig=True,
            tight_layout=True,
            scale_padding={'left': 0.5, 'right': 1.2, 'top': 0.8, 'bottom': 0.5},
        )
        
        self._add_legend(fig, axes[0], df, trade_signals)

        if save_path:
            fig.savefig(save_path, bbox_inches='tight', dpi=150)
            print(f"  Daily chart saved: {save_path}")

        return fig

    def _plot_weekly(self, df, symbol, save_path, trade_signals=None):
        """Plot weekly candlestick chart (converted from daily)"""
        df = self._prepare_data(df)
        df = df.dropna(subset=['Open', 'Close', 'High', 'Low'])
        
        # Ensure DatetimeIndex
        if not isinstance(df.index, pd.DatetimeIndex):
            df.index = pd.to_datetime(df.index)
        
        # Resample to weekly (Friday close)
        weekly_df = df.resample('W-FRI').agg({
            'Open': 'first',
            'High': 'max',
            'Low': 'min',
            'Close': 'last',
            'Volume': 'sum'
        }).dropna()
        
        # Calculate weekly MAs (10wk ≈ 50day, 40wk ≈ 200day)
        weekly_df['MA10'] = weekly_df['Close'].rolling(window=10).mean()
        weekly_df['MA40'] = weekly_df['Close'].rolling(window=40).mean()
        
        # Build addplots for weekly
        addplots = []
        if 'MA10' in weekly_df.columns:
            addplots.append(mpf.make_addplot(
                weekly_df['MA10'], color=self.COLORS['ma50'], linestyle='-', width=1.5,
                panel=0, ylabel='Price'
            ))
        if 'MA40' in weekly_df.columns:
            addplots.append(mpf.make_addplot(
                weekly_df['MA40'], color=self.COLORS['bearish'], linestyle='-', width=1.5,
                panel=0
            ))

        # Weekly MACD
        close = weekly_df['Close']
        ema12 = close.ewm(span=12, adjust=False).mean()
        ema26 = close.ewm(span=26, adjust=False).mean()
        macd_line = ema12 - ema26
        signal_line = macd_line.ewm(span=9, adjust=False).mean()
        macd_hist = macd_line - signal_line

        addplots.append(mpf.make_addplot(macd_line, color='#2196F3', width=1.2, panel=2, ylabel='MACD'))
        addplots.append(mpf.make_addplot(signal_line, color='#FF9800', width=1.2, panel=2))
        hist_colors = [self.COLORS['bullish'] if v >= 0 else self.COLORS['bearish'] for v in macd_hist]
        addplots.append(mpf.make_addplot(macd_hist, type='bar', color=hist_colors, panel=2, alpha=0.5))

        mc = mpf.make_marketcolors(
            up=self.COLORS['bullish'],
            down=self.COLORS['bearish'],
            edge={'up': self.COLORS['bullish'], 'down': self.COLORS['bearish']},
            wick={'up': self.COLORS['bullish'], 'down': self.COLORS['bearish']},
            volume={'up': self.COLORS['volume_up'], 'down': self.COLORS['volume_down']},
        )

        style = mpf.make_mpf_style(
            marketcolors=mc,
            gridstyle='-',
            gridcolor='#E5E5E5',
            y_on_right=True,
            rc={'figure.facecolor': '#FFFFFF', 'axes.facecolor': '#FFFFFF', 'font.size': 12}
        )

        fig, axes = mpf.plot(
            weekly_df,
            type='candle',
            style=style,
            volume=True,
            addplot=addplots,
            figsize=(24, 12),
            panel_ratios=(5, 1, 1.5),
            title=f'\n{symbol} - Weekly Chart (2-Year Trend)',
            returnfig=True,
            tight_layout=True,
        )
        
        # Add legend
        legend_handles = [
            mlines.Line2D([], [], color=self.COLORS['ma50'], linewidth=1.5, label='10W MA (~50D)'),
            mlines.Line2D([], [], color=self.COLORS['bearish'], linewidth=1.5, label='40W MA (~200D)'),
            mlines.Line2D([], [], color=self.COLORS['bullish'], linewidth=2, label='Bullish'),
            mlines.Line2D([], [], color=self.COLORS['bearish'], linewidth=2, label='Bearish'),
        ]
        axes[0].legend(handles=legend_handles, loc='upper left', fontsize=9,
                       framealpha=0.9, edgecolor='#CCCCCC', ncol=2)

        if save_path:
            fig.savefig(save_path, bbox_inches='tight', dpi=300)
            print(f"  Weekly chart saved: {save_path}")

        return fig

    def plot(self, df, symbol, save_path=None, trade_signals=None):
        """
        Plot chart(s):
        - Always: Daily chart (last 180 days or show_days)
        - If > 1 year data: Also generate weekly chart (full 2 years)
        """
        # Calculate indicators
        df = self.ma.calculate(df)
        df = self.ma.get_crossovers(df)
        
        days_count = len(df)
        figs = []
        
        # --- Daily Chart ---
        daily_save = save_path
        if save_path and days_count > 252:
            # Rename daily path
            daily_save = save_path.replace('.png', '_daily.png')
        
        print(f"\n  Generating daily chart ({min(days_count, self.show_days)} days)...")
        fig_daily = self._plot_daily(df.copy(), symbol, daily_save, trade_signals)
        figs.append(fig_daily)
        
        # --- Weekly Chart (if > 1 year) ---
        if days_count > 252:
            weekly_save = save_path.replace('.png', '_weekly.png') if save_path else None
            print(f"  Generating weekly chart ({days_count} days -> weekly)...")
            fig_weekly = self._plot_weekly(df.copy(), symbol, weekly_save, trade_signals)
            figs.append(fig_weekly)
        
        return figs if len(figs) > 1 else figs[0]


# ==========================================
# STANDALONE QUICK PLOT FUNCTION
# ==========================================

def quick_plot(df, symbol, save_path=None):
    """Quick plot function"""
    chart = MarketSmithChart()
    return chart.plot(df, symbol, save_path)
