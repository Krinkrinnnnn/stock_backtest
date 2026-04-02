"""
Chart Plotter using Plotly
===========================
Professional stock charts with candlestick, volume, moving averages, RS, and MACD.

Auto-generates:
- Daily chart (always)
- Weekly chart (when data > 1 year)
"""

import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from diagram_indicators import MovingAverages


class MarketSmithChart:
    """
    Plotly chart with candlestick, MAs, buy/sell markers, RS, MACD, and VCP arcs.
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
        'buy': '#2196F3',
        'sell': '#FF5252',
    }

    def __init__(self, show_days=180):
        self.show_days = show_days
        self.ma = MovingAverages()

    def _plot_daily(self, df, symbol, save_path, trade_signals=None):
        """Plot daily candlestick chart with VCP arcs."""
        df = self.ma.calculate(df)
        df = self.ma.get_crossovers(df)

        for col in ['Open', 'High', 'Low', 'Close', 'Volume']:
            if col not in df.columns:
                df[col] = 0

        df = df.dropna(subset=['Open', 'Close', 'High', 'Low'])

        if len(df) > self.show_days:
            df = df.tail(self.show_days)

        # --- Create subplots ---
        fig = make_subplots(
            rows=4, cols=1,
            shared_xaxes=True,
            vertical_spacing=0.03,
            row_heights=[0.5, 0.15, 0.175, 0.175],
            subplot_titles=(f'{symbol} - Daily Chart', 'Volume', 'RS Score', 'MACD')
        )

        # --- Candlestick ---
        fig.add_trace(go.Candlestick(
            x=df.index,
            open=df['Open'], high=df['High'],
            low=df['Low'], close=df['Close'],
            increasing_line_color=self.COLORS['bullish'],
            decreasing_line_color=self.COLORS['bearish'],
            increasing_fillcolor=self.COLORS['bullish'],
            decreasing_fillcolor=self.COLORS['bearish'],
            name='Price'
        ), row=1, col=1)

        # --- Moving Averages ---
        for col, color, dash, name in [
            ('MA20', self.COLORS['ma20'], 'solid', 'MA20'),
            ('MA50', self.COLORS['ma50'], 'solid', 'MA50'),
            ('EMA13', self.COLORS['ema13'], 'dash', 'EMA13'),
            ('EMA120', self.COLORS['ema120'], 'dash', 'EMA120'),
        ]:
            if col in df.columns:
                fig.add_trace(go.Scatter(
                    x=df.index, y=df[col],
                    mode='lines', name=name,
                    line=dict(color=color, width=1.5, dash=dash),
                    showlegend=True
                ), row=1, col=1)

        # --- Trade Signals ---
        if trade_signals:
            buy_dates, buy_prices = [], []
            sell_dates, sell_prices = [], []

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
                        buy_dates.append(idx)
                        buy_prices.append(df.loc[idx, 'Low'] * 0.98)
                        print(f"  BUY  {idx_naive.strftime('%Y-%m-%d')} @ ${signal['price']:.2f}")
                    elif signal['type'] == 'SELL':
                        sell_dates.append(idx)
                        sell_prices.append(df.loc[idx, 'High'] * 1.02)
                        pnl = signal.get('pnl_pct', 0)
                        print(f"  SELL {idx_naive.strftime('%Y-%m-%d')} @ ${signal['price']:.2f} ({pnl:+.1f}%)")

            if buy_dates:
                fig.add_trace(go.Scatter(
                    x=buy_dates, y=buy_prices,
                    mode='markers', name='BUY Entry',
                    marker=dict(symbol='triangle-up', size=12, color=self.COLORS['buy'],
                                line=dict(width=1, color='darkblue')),
                    showlegend=True
                ), row=1, col=1)

            if sell_dates:
                fig.add_trace(go.Scatter(
                    x=sell_dates, y=sell_prices,
                    mode='markers', name='SELL Exit',
                    marker=dict(symbol='triangle-down', size=12, color=self.COLORS['sell'],
                                line=dict(width=1, color='darkred')),
                    showlegend=True
                ), row=1, col=1)

        # --- VCP Arcs (power-curve bowl below candles) ---
        if 'VCP_Arcs' in df.columns:
            vcp_arcs = df['VCP_Arcs'].iloc[-1] if len(df) > 0 else []
            if vcp_arcs:
                df_index = df.index
                for i, arc in enumerate(vcp_arcs):
                    peak1_date = arc.get('peak1_date')
                    trough_date = arc.get('trough_date')
                    peak2_date = arc.get('peak2_date')
                    peak1_price = arc.get('peak1_price')
                    trough_price = arc.get('trough_price')
                    peak2_price = arc.get('peak2_price')

                    if any(v is None for v in [peak1_date, trough_date, peak2_date,
                                               peak1_price, trough_price, peak2_price]):
                        continue

                    label = arc.get('wave', f'T{i+1}')
                    pct = arc.get('contraction_pct', 0)

                    # Find integer indices
                    p1_ts = pd.Timestamp(peak1_date)
                    t_ts = pd.Timestamp(trough_date)
                    p2_ts = pd.Timestamp(peak2_date)

                    if df_index.tz is not None:
                        if p1_ts.tz is None:
                            p1_ts = p1_ts.tz_localize(df_index.tz)
                        if t_ts.tz is None:
                            t_ts = t_ts.tz_localize(df_index.tz)
                        if p2_ts.tz is None:
                            p2_ts = p2_ts.tz_localize(df_index.tz)

                    p1_idx = df_index.get_indexer([p1_ts], method='nearest')[0]
                    t_idx = df_index.get_indexer([t_ts], method='nearest')[0]
                    p2_idx = df_index.get_indexer([p2_ts], method='nearest')[0]

                    if p1_idx < 0 or t_idx < 0 or p2_idx < 0:
                        continue
                    if not (p1_idx < t_idx < p2_idx):
                        continue

                    # Power-curve bowl
                    n_left = max(t_idx - p1_idx, 2) * 2
                    x_left = np.linspace(p1_idx, t_idx, n_left)
                    x_norm_left = (x_left - t_idx) / (p1_idx - t_idx)
                    y_left = trough_price + (peak1_price - trough_price) * (x_norm_left ** 2.5)

                    n_right = max(p2_idx - t_idx, 2) * 2
                    x_right = np.linspace(t_idx, p2_idx, n_right)
                    x_norm_right = (x_right - t_idx) / (p2_idx - t_idx)
                    y_right = trough_price + (peak2_price - trough_price) * (x_norm_right ** 2.5)

                    x_combined = np.concatenate([x_left, x_right[1:]])
                    y_combined = np.concatenate([y_left, y_right[1:]])

                    plot_dates = [df_index[int(round(xi))] for xi in x_combined]

                    # Arc line
                    fig.add_trace(go.Scatter(
                        x=plot_dates, y=y_combined,
                        mode='lines',
                        name=f'VCP {label} ({pct:.1f}%)',
                        line=dict(color='#00CC66', width=3),
                        showlegend=True,
                        hoverinfo='name'
                    ), row=1, col=1)

                    # Diamond markers
                    fig.add_trace(go.Scatter(
                        x=[peak1_date, trough_date, peak2_date],
                        y=[peak1_price, trough_price, peak2_price],
                        mode='markers',
                        name=f'{label} Points',
                        marker=dict(symbol='diamond', size=6, color='#00CC66',
                                    line=dict(width=1, color='darkgreen')),
                        showlegend=False,
                        hoverinfo='skip'
                    ), row=1, col=1)

                    # Trough annotation
                    fig.add_annotation(
                        x=trough_date, y=trough_price,
                        text=f'-{pct:.1f}%',
                        showarrow=False,
                        font=dict(color='#00CC66', size=11, family='Arial Black'),
                        yshift=-18,
                        row=1, col=1
                    )

        # --- Volume ---
        vol_colors = [self.COLORS['volume_up'] if c >= o else self.COLORS['volume_down']
                      for c, o in zip(df['Close'], df['Open'])]
        fig.add_trace(go.Bar(
            x=df.index, y=df['Volume'],
            marker_color=vol_colors,
            name='Volume', showlegend=False
        ), row=2, col=1)

        # --- RS Score ---
        if 'RS_Score' in df.columns:
            fig.add_trace(go.Scatter(
                x=df.index, y=df['RS_Score'],
                mode='lines', name='RS Score',
                line=dict(color=self.COLORS['rs_line'], width=1.5),
                showlegend=False
            ), row=3, col=1)
            fig.add_hline(y=70, line_dash="dot", line_color="#FF6600", row=3, col=1)

        # --- MACD ---
        close = df['Close']
        ema12 = close.ewm(span=12, adjust=False).mean()
        ema26 = close.ewm(span=26, adjust=False).mean()
        macd_line = ema12 - ema26
        signal_line = macd_line.ewm(span=9, adjust=False).mean()
        macd_hist = macd_line - signal_line

        fig.add_trace(go.Scatter(
            x=df.index, y=macd_line, mode='lines', name='MACD',
            line=dict(color='#2196F3', width=1.2), showlegend=False
        ), row=4, col=1)
        fig.add_trace(go.Scatter(
            x=df.index, y=signal_line, mode='lines', name='Signal',
            line=dict(color='#FF9800', width=1.2), showlegend=False
        ), row=4, col=1)
        hist_colors = [self.COLORS['bullish'] if v >= 0 else self.COLORS['bearish'] for v in macd_hist]
        fig.add_trace(go.Bar(
            x=df.index, y=macd_hist,
            marker_color=hist_colors, name='MACD Hist', showlegend=False
        ), row=4, col=1)

        # Layout
        fig.update_layout(
            template='plotly_white',
            height=900,
            xaxis_rangeslider_visible=False,
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
            margin=dict(l=50, r=50, t=80, b=50),
        )

        for i in range(1, 5):
            fig.update_xaxes(rangeslider_visible=False, row=i, col=1)

        if save_path:
            html_path = save_path.replace('.png', '.html')
            fig.write_html(html_path)
            try:
                fig.write_image(save_path, width=1600, height=900, scale=2)
                print(f"  Daily chart saved: {save_path}")
            except Exception as e:
                print(f"  Daily chart HTML saved: {html_path} (PNG: {e})")

        return fig

    def _plot_weekly(self, df, symbol, save_path, trade_signals=None):
        """Plot weekly candlestick chart (converted from daily)."""
        for col in ['Open', 'High', 'Low', 'Close', 'Volume']:
            if col not in df.columns:
                df[col] = 0
        df = df.dropna(subset=['Open', 'Close', 'High', 'Low'])

        if not isinstance(df.index, pd.DatetimeIndex):
            df.index = pd.to_datetime(df.index)

        weekly_df = df.resample('W-FRI').agg({
            'Open': 'first', 'High': 'max', 'Low': 'min',
            'Close': 'last', 'Volume': 'sum'
        }).dropna()

        weekly_df['MA10'] = weekly_df['Close'].rolling(window=10).mean()
        weekly_df['MA40'] = weekly_df['Close'].rolling(window=40).mean()

        fig = make_subplots(
            rows=3, cols=1,
            shared_xaxes=True,
            vertical_spacing=0.05,
            row_heights=[0.6, 0.2, 0.2],
            subplot_titles=(f'{symbol} - Weekly Chart (2-Year Trend)', 'Volume', 'MACD')
        )

        fig.add_trace(go.Candlestick(
            x=weekly_df.index,
            open=weekly_df['Open'], high=weekly_df['High'],
            low=weekly_df['Low'], close=weekly_df['Close'],
            increasing_line_color=self.COLORS['bullish'],
            decreasing_line_color=self.COLORS['bearish'],
            increasing_fillcolor=self.COLORS['bullish'],
            decreasing_fillcolor=self.COLORS['bearish'],
            name='Price'
        ), row=1, col=1)

        fig.add_trace(go.Scatter(
            x=weekly_df.index, y=weekly_df['MA10'],
            mode='lines', name='10W MA (~50D)',
            line=dict(color=self.COLORS['ma50'], width=2),
        ), row=1, col=1)
        fig.add_trace(go.Scatter(
            x=weekly_df.index, y=weekly_df['MA40'],
            mode='lines', name='40W MA (~200D)',
            line=dict(color=self.COLORS['bearish'], width=2),
        ), row=1, col=1)

        vol_colors = [self.COLORS['volume_up'] if c >= o else self.COLORS['volume_down']
                      for c, o in zip(weekly_df['Close'], weekly_df['Open'])]
        fig.add_trace(go.Bar(
            x=weekly_df.index, y=weekly_df['Volume'],
            marker_color=vol_colors, name='Volume', showlegend=False
        ), row=2, col=1)

        close = weekly_df['Close']
        macd_line = close.ewm(span=12, adjust=False).mean() - close.ewm(span=26, adjust=False).mean()
        signal_line = macd_line.ewm(span=9, adjust=False).mean()
        macd_hist = macd_line - signal_line

        fig.add_trace(go.Scatter(
            x=weekly_df.index, y=macd_line, mode='lines', name='MACD',
            line=dict(color='#2196F3', width=1.2), showlegend=False
        ), row=3, col=1)
        fig.add_trace(go.Scatter(
            x=weekly_df.index, y=signal_line, mode='lines', name='Signal',
            line=dict(color='#FF9800', width=1.2), showlegend=False
        ), row=3, col=1)
        hist_colors = [self.COLORS['bullish'] if v >= 0 else self.COLORS['bearish'] for v in macd_hist]
        fig.add_trace(go.Bar(
            x=weekly_df.index, y=macd_hist,
            marker_color=hist_colors, name='MACD Hist', showlegend=False
        ), row=3, col=1)

        fig.update_layout(
            template='plotly_white', height=800,
            xaxis_rangeslider_visible=False,
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
            margin=dict(l=50, r=50, t=80, b=50),
        )
        for i in range(1, 4):
            fig.update_xaxes(rangeslider_visible=False, row=i, col=1)

        if save_path:
            html_path = save_path.replace('.png', '.html')
            fig.write_html(html_path)
            try:
                fig.write_image(save_path, width=1800, height=800, scale=2)
                print(f"  Weekly chart saved: {save_path}")
            except Exception as e:
                print(f"  Weekly chart HTML saved: {html_path} (PNG: {e})")

        return fig

    def plot(self, df, symbol, save_path=None, trade_signals=None):
        """
        Plot chart(s):
        - Always: Daily chart
        - If > 1 year data: Also generate weekly chart
        """
        days_count = len(df)
        figs = []

        daily_save = save_path
        if save_path and days_count > 252:
            daily_save = save_path.replace('.png', '_daily.png')

        print(f"\n  Generating daily chart ({min(days_count, self.show_days)} days)...")
        fig_daily = self._plot_daily(df.copy(), symbol, daily_save, trade_signals)
        figs.append(fig_daily)

        if days_count > 252:
            weekly_save = save_path.replace('.png', '_weekly.png') if save_path else None
            print(f"  Generating weekly chart ({days_count} days -> weekly)...")
            fig_weekly = self._plot_weekly(df.copy(), symbol, weekly_save, trade_signals)
            figs.append(fig_weekly)

        return figs if len(figs) > 1 else figs[0]
