import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.patches import Rectangle, FancyBboxPatch
from matplotlib.lines import Line2D
from matplotlib.widgets import CheckButtons
from diagram_indicators import MovingAverages, IndicatorPlotter


class MarketSmithChart:
    """
    MarketSmith / TradingView / StockPlot 風格圖表繪製類
    - 蠟燭圖 (綠/紅) - 更美觀的樣式，沒有週末空隙 (StockPlot 風格)
    - 支援交互式十字線 (Crosshair)
    - RS 線
    - VCP 收縮波 (T1, T2, T3)
    - 移動平均線 (MA20, MA50, EMA13, EMA120)
    - 成交量柱狀圖
    """
    
    COLORS = {
        'bullish': '#00A699',      # Teal/Green Outline & Wicks
        'bearish': '#FF333D',      # Red Outline & Wicks & Fill
        'bullish_fill': 'none',    # Hollow fill for Bullish candles (transparent)
        'background': '#FFFFFF',   # White background
        'grid': '#E5E5E5',
        'text': '#333333',
        'ma20': '#FFA500',         # Orange
        'ma50': '#1E90FF',         # DodgerBlue
        'ema13': '#FF1493',        # DeepPink
        'ema120': '#8A2BE2',       # BlueViolet
        'rs_line': '#0066CC',
        'rs_fill_up': '#00AA00',
        'rs_fill_down': '#CC0000',
        'volume_up': '#00A699',
        'volume_down': '#FF333D',
        'crosshair': '#757575'
    }
    
    def __init__(self, figsize=(18, 12)):
        self.figsize = figsize
        self.fig = None
        self.ax_price = None
        self.ax_volume = None
        self.ax_rs = None
        self.ma = MovingAverages()
        
        # 儲存 X 軸的日期映射 (消除週末空隙用)
        self.date_mapping = {}
        self.inv_date_mapping = {}
        self.dates = []
    
    def _prepare_continuous_x_axis(self, df):
        """
        準備連續的 X 軸 (跳過週末，類似 StockPlot 的處理方式)
        """
        df = df.copy()
        df = df.dropna(subset=['Open', 'Close'])
        
        self.dates = df.index.tolist()
        
        for i, date in enumerate(self.dates):
            self.date_mapping[date] = i
            self.inv_date_mapping[i] = date
            
        return df
    
    def _format_x_axis(self, ax, num_ticks=10):
        """
        格式化 X 軸標籤 (將連續索引轉換回日期)
        """
        if not self.dates:
            return
            
        total_dates = len(self.dates)
        step = max(1, total_dates // num_ticks)
        
        tick_positions = list(range(0, total_dates, step))
        tick_labels = [self.dates[i].strftime('%Y-%m-%d') for i in tick_positions]
        
        ax.set_xticks(tick_positions)
        ax.set_xticklabels(tick_labels, rotation=45, ha='right')
    
    def _draw_candlestick(self, ax, df):
        """
        繪製美觀的蠟燭圖 (StockPlot 風格)，使用連續的 X 軸索引
        空心綠色蠟燭 = 上漲 (Close >= Open)
        實心紅色蠟燭 = 下跌 (Close < Open)
        """
        width = 0.6
        
        for i, (idx, row) in enumerate(df.iterrows()):
            x_pos = self.date_mapping[idx]
            
            open_price = row['Open']
            close_price = row['Close']
            high_price = row['High']
            low_price = row['Low']
            
            is_bullish = close_price >= open_price
            
            body_color = self.COLORS['bullish_fill'] if is_bullish else self.COLORS['bearish']
            edge_color = self.COLORS['bullish'] if is_bullish else self.COLORS['bearish']
            wick_color = self.COLORS['bullish'] if is_bullish else self.COLORS['bearish']
            
            body_bottom = min(open_price, close_price)
            body_height = abs(close_price - open_price)
            
            # 繪製上下影線 (Wicks)
            ax.plot([x_pos, x_pos], [low_price, high_price],
                    color=wick_color, linewidth=1.5, zorder=1)
            
            # 繪製實體 (Body)
            if body_height > 0:
                rect = Rectangle(
                    (x_pos - width/2, body_bottom),
                    width,
                    body_height,
                    facecolor=body_color,
                    edgecolor=edge_color,
                    linewidth=1.2,
                    zorder=2
                )
                ax.add_patch(rect)
            else:
                # 十字線 (Doji)
                ax.plot([x_pos - width/2, x_pos + width/2], 
                        [close_price, close_price],
                        color=edge_color, linewidth=1.5, zorder=2)
    
    def _draw_volume(self, ax, df):
        """
        繪製獨立成交量柱狀圖與 50 日均線 (重疊在價格圖底部)
        """
        df_mapped = df[df.index.isin(self.date_mapping)]
        if df_mapped.empty:
            return
            
        x_pos = [self.date_mapping[idx] for idx in df_mapped.index]
        
        colors = [self.COLORS['volume_up'] if c >= o else self.COLORS['volume_down'] 
                  for c, o in zip(df_mapped['Close'], df_mapped['Open'])]
        
        # Plot Volume Bars
        ax.bar(x_pos, df_mapped['Volume'], color=colors, width=0.6, alpha=0.4)
        
        # Calculate and plot 50-day Volume MA
        vol_ma50 = df_mapped['Volume'].rolling(window=50, min_periods=1).mean()
        ax.plot(x_pos, vol_ma50, color='#333333', linewidth=1.5, linestyle='-', alpha=0.6, label='Vol MA50')
        
        # Scale Y axis so volume stays at the bottom quarter of the chart
        max_vol = df_mapped['Volume'].max()
        if max_vol > 0:
            ax.set_ylim(0, max_vol * 4)
            
        # Hide volume Y-axis to keep main chart clean
        ax.set_yticks([])
        ax.legend(loc='lower right', fontsize=8, framealpha=0.6)
    
    def _draw_vcp_pattern(self, ax, df):
        """
        繪製 VCP 收縮波
        """
        if 'VCP_Contractions' not in df.columns:
            return
        
        contractions = df['VCP_Contractions'].iloc[-1]
        
        if not contractions:
            return
        
        colors = ['#FF6B6B', '#4ECDC4', '#45B7D1']
        
        for i, c in enumerate(contractions):
            wave = c['wave']
            date = c['date']
            price = c['price']
            contraction_pct = c.get('contraction_pct', 0)
            
            if date not in self.date_mapping:
                continue
                
            x_pos = self.date_mapping[date]
            color = colors[i % len(colors)]
            
            ax.hlines(y=price, xmin=0, xmax=x_pos,
                      colors=color, linestyles='--', linewidth=1.5, alpha=0.7)
            
            ax.plot(x_pos, price, 'o', color=color, markersize=8, zorder=7)
            
            bbox_props = dict(boxstyle="round,pad=0.3", facecolor='white', 
                              edgecolor=color, alpha=0.9, linewidth=1.5)
            ax.annotate(f'{wave}\n-{contraction_pct:.1f}%',
                        xy=(x_pos, price),
                        xytext=(10, 15),
                        textcoords='offset points',
                        fontsize=9,
                        fontweight='bold',
                        color=color,
                        ha='left',
                        va='bottom',
                        bbox=bbox_props,
                        zorder=10)
        
        if len(contractions) >= 2:
            wave_x = [self.date_mapping[c['date']] for c in contractions if c['date'] in self.date_mapping]
            wave_prices = [c['price'] for c in contractions if c['date'] in self.date_mapping]
            
            if len(wave_x) >= 2:
                ax.plot(wave_x, wave_prices, '-', color='#9B59B6', 
                        linewidth=2, alpha=0.7, zorder=4)
    
    def _draw_signals(self, ax, df):
        """
        繪製信號標記
        """
        vcp_signals = df[df['VCP_Signal']]
        for idx, row in vcp_signals.iterrows():
            if idx in self.date_mapping:
                x_pos = self.date_mapping[idx]
                ax.scatter(x_pos, row['Close'] * 1.02,
                           color='#FFA726', marker='^', s=100, label='VCP Signal' if idx == vcp_signals.index[0] else "",
                           zorder=8, alpha=0.9, edgecolors='#E65100', linewidths=1)
        
        breakout_signals = df[df['Signal']]
        for idx, row in breakout_signals.iterrows():
            if idx in self.date_mapping:
                x_pos = self.date_mapping[idx]
                ax.scatter(x_pos, row['Close'] * 1.02,
                           color='#66BB6A', marker='*', s=200, label='Buy Signal' if idx == breakout_signals.index[0] else "",
                           zorder=9, edgecolors='#1B5E20', linewidths=1)
                print(f"[{idx.strftime('%Y-%m-%d')}] BUY SIGNAL DETECTED at ${row['Close']:.2f}!")
    
    def _draw_rs_score(self, ax, df):
        """
        繪製 RS Score 線 (在獨立子圖)
        """
        df_mapped = df[df.index.isin(self.date_mapping)]
        if df_mapped.empty:
            return
            
        x_values = [self.date_mapping[idx] for idx in df_mapped.index]
        
        # Plot RS Score if available, otherwise RS Line
        if 'RS_Score' in df_mapped.columns:
            rs_values = df_mapped['RS_Score'].tolist()
            label = 'RS Score'
            ax.set_ylim(-10, 110)  # Standard 0-100 range with padding
            # Add a 70 threshold line
            ax.axhline(y=70, color='#FF6600', linestyle=':', linewidth=1.5, alpha=0.8)
        elif 'RS_Line' in df_mapped.columns:
            rs_values = df_mapped['RS_Line'].tolist()
            label = 'RS Line'
        else:
            return
            
        ax.plot(x_values, rs_values, color=self.COLORS['rs_line'], 
                linewidth=2.0, alpha=0.9, label=label)
        
        # Settings
        ax.yaxis.tick_right()
        ax.set_ylabel(label, fontsize=10, fontweight='bold')
        ax.legend(loc='upper left', fontsize=8)
        
        # Grid
        ax.grid(True, alpha=0.2, color='#000000', linestyle='-')
        ax.spines['top'].set_visible(False)
        ax.spines['left'].set_visible(False)
        ax.spines['bottom'].set_visible(False)
                
    def _draw_macd(self, ax, df):
        """
        繪製 MACD 子圖
        """
        df_mapped = df[df.index.isin(self.date_mapping)]
        if df_mapped.empty:
            return
            
        # 計算 MACD
        close = df_mapped['Close']
        ema12 = close.ewm(span=12, adjust=False).mean()
        ema26 = close.ewm(span=26, adjust=False).mean()
        macd_line = ema12 - ema26
        signal_line = macd_line.ewm(span=9, adjust=False).mean()
        macd_hist = macd_line - signal_line
        
        x_values = [self.date_mapping[idx] for idx in df_mapped.index]
        
        # Plot lines
        ax.plot(x_values, macd_line, color='#2196F3', linewidth=1.5, label='MACD Line')
        ax.plot(x_values, signal_line, color='#FF9800', linewidth=1.5, label='Signal Line')
        
        # Plot histogram
        colors = [self.COLORS['bullish'] if val >= 0 else self.COLORS['bearish'] for val in macd_hist]
        ax.bar(x_values, macd_hist, color=colors, alpha=0.5, width=0.6)
        
        # Add zero line
        ax.axhline(0, color='#999999', linewidth=1, linestyle='--')
        
        # Settings
        ax.yaxis.tick_right()
        ax.set_ylabel('MACD', fontsize=10, fontweight='bold')
        ax.legend(loc='upper left', fontsize=8)
        
        # Grid
        ax.grid(True, alpha=0.2, color='#000000', linestyle='-')
        ax.spines['top'].set_visible(False)
        ax.spines['left'].set_visible(False)
        ax.spines['bottom'].set_visible(False)
        """
        繪製移動平均線
        """
        x_values = [self.date_mapping[idx] for idx in df.index if idx in self.date_mapping]
        lines = {}
        
        for ma_name, color, style, width in [
            ('MA20', self.COLORS['ma20'], '-', 1.5),
            ('MA50', self.COLORS['ma50'], '-', 1.5),
            ('EMA13', self.COLORS['ema13'], ':', 1.5),
            ('EMA120', self.COLORS['ema120'], ':', 1.5)
        ]:
            if ma_name in df.columns:
                ma_values = [df.loc[idx, ma_name] for idx in df.index if idx in self.date_mapping]
                line, = ax.plot(x_values, ma_values, color=color, linestyle=style,
                                linewidth=width, label=ma_name, alpha=0.85)
                lines[ma_name] = line
                
        return lines

    def _draw_moving_averages(self, ax, df):
        """
        繪製移動平均線
        """
        x_values = [self.date_mapping[idx] for idx in df.index if idx in self.date_mapping]
        lines = {}
        
        for ma_name, color, style, width in [
            ('MA20', self.COLORS['ma20'], '-', 1.5),
            ('MA50', self.COLORS['ma50'], '-', 1.5),
            ('EMA13', self.COLORS['ema13'], ':', 1.5),
            ('EMA120', self.COLORS['ema120'], ':', 1.5)
        ]:
            if ma_name in df.columns:
                ma_values = [df.loc[idx, ma_name] for idx in df.index if idx in self.date_mapping]
                line, = ax.plot(x_values, ma_values, color=color, linestyle=style,
                                linewidth=width, label=ma_name, alpha=0.85)
                lines[ma_name] = line
                
        return lines

    def plot(self, df, symbol, save_path=None):
        """
        繪製完整圖表
        """
        df = self.ma.calculate(df)
        df = self.ma.get_crossovers(df)
        
        # 準備連續的 X 軸 (跳過週末空隙)
        df_clean = self._prepare_continuous_x_axis(df)
        
        self.fig = plt.figure(figsize=self.figsize, facecolor=self.COLORS['background'], layout="constrained")
        
        # 使用 GridSpec 分配 3 個子圖： 主圖包含成交量(3), RS(0.8), MACD(1)
        gs = self.fig.add_gridspec(3, 1, height_ratios=[3, 0.8, 1], hspace=0.05)
        
        self.ax_price = self.fig.add_subplot(gs[0])
        self.ax_volume = self.ax_price.twinx()  # Overlay volume on price
        self.ax_rs = self.fig.add_subplot(gs[1], sharex=self.ax_price)
        self.ax_macd = self.fig.add_subplot(gs[2], sharex=self.ax_price)
        
        for ax in [self.ax_price, self.ax_rs, self.ax_macd]:
            ax.set_facecolor(self.COLORS['background'])
            
        # Z-order magic so volume bars stay behind price candles
        self.ax_volume.set_zorder(1)
        self.ax_price.set_zorder(2)
        self.ax_price.patch.set_visible(False)
        
        # 設定價格 Y 軸在右側
        self.ax_price.yaxis.tick_right()
        self.ax_price.yaxis.set_label_position("right")
        self.ax_price.set_ylabel('Price', fontsize=10, fontweight='bold')
        
        # 繪製各個組件
        self._draw_candlestick(self.ax_price, df_clean)
        self._draw_vcp_pattern(self.ax_price, df_clean)
        ma_lines = self._draw_moving_averages(self.ax_price, df_clean)
        self._draw_signals(self.ax_price, df_clean)
        
        self._draw_volume(self.ax_volume, df_clean)
        self._draw_rs_score(self.ax_rs, df_clean)
        self._draw_macd(self.ax_macd, df_clean)
        
        # 設置標題
        self.ax_price.set_title(f'{symbol} - Technical Analysis', 
                                fontsize=14, fontweight='bold', loc='left')
        
        # 網格線設定
        self.ax_price.grid(True, alpha=0.2, color='#000000', linestyle='-')
        self.ax_price.spines['top'].set_visible(False)
        self.ax_price.spines['left'].set_visible(False)
        
        # 隱藏上方圖表的 X 軸標籤
        plt.setp(self.ax_price.get_xticklabels(), visible=False)
        plt.setp(self.ax_volume.get_xticklabels(), visible=False)
        plt.setp(self.ax_rs.get_xticklabels(), visible=False)
        
        # Add CheckButtons for toggling indicators
        if ma_lines:
            rax = self.fig.add_axes((0.02, 0.8, 0.08, 0.12))
            rax.set_facecolor(self.COLORS['background'])
            rax.set_title("Indicators", fontsize=9, fontweight='bold')
            labels = list(ma_lines.keys())
            visibility = [True] * len(labels)
            self.check = CheckButtons(rax, labels, visibility)
            
            for label in self.check.labels:
                label.set_fontsize(8)
                
            def toggle_lines(label):
                line = ma_lines[label]
                line.set_visible(not line.get_visible())
                if self.fig.canvas:
                    self.fig.canvas.draw_idle()
                
            self.check.on_clicked(toggle_lines)
        
        # 設定 X 軸限制和格式
        max_x = len(self.dates) - 1
        self.ax_price.set_xlim(-1, max_x + 2)
        
        # 格式化 X 軸 (現在主圖是最下方的 ax_macd)
        self._format_x_axis(self.ax_macd)
        
        # Y 軸限制
        price_min = df_clean['Low'].min()
        price_max = df_clean['High'].max()
        price_range = price_max - price_min
        self.ax_price.set_ylim(price_min - price_range * 0.05, price_max + price_range * 0.1)
        
        # 圖例設定
        legend_elements = [
            Line2D([0], [0], color=self.COLORS['bullish'], linewidth=2, label='Up'),
            Line2D([0], [0], color=self.COLORS['bearish'], linewidth=2, label='Down'),
        ]
        
        for ma_name, color, style in [
            ('MA20', self.COLORS['ma20'], '-'),
            ('MA50', self.COLORS['ma50'], '-'),
            ('EMA13', self.COLORS['ema13'], ':'),
            ('EMA120', self.COLORS['ema120'], ':')
        ]:
            if ma_name in ma_lines:
                legend_elements.append(Line2D([0], [0], color=color, linewidth=1.5, linestyle=style, label=ma_name))
                
        self.ax_price.legend(handles=legend_elements, loc='upper left', fontsize=8, 
                             ncol=3, framealpha=0.8, edgecolor='#DDDDDD')
        
        # 標示最新價格
        latest_price = df_clean['Close'].iloc[-1]
        self.ax_price.axhline(y=latest_price, color=self.COLORS['crosshair'], 
                              linestyle=':', linewidth=1, alpha=0.5)
        self.ax_price.annotate(f'{latest_price:.2f}',
                               xy=(max_x + 0.5, latest_price),
                               xytext=(5, 0), textcoords='offset points',
                               va='center', ha='left',
                               bbox=dict(boxstyle='square,pad=0.2', 
                                         fc=self.COLORS['crosshair'], ec='none', alpha=0.8),
                               color='white', fontsize=9, fontweight='bold')
        
        if save_path:
            self.fig.savefig(save_path, bbox_inches='tight', dpi=150)
            print(f"Chart saved to {save_path}")
        else:
            plt.show()
        
        return self.fig
