import pandas as pd
import numpy as np
from scipy.signal import find_peaks
from scipy.interpolate import interp1d


def calculate_rs_line(df, benchmark_df):
    """
    計算每日 RS 曲線 (相對強度線)
    RS = 股價 / 標竿價格 * 基準值
    """
    if benchmark_df is None or benchmark_df.empty:
        return pd.Series(index=df.index, data=100.0)
    
    aligned_benchmark = benchmark_df.reindex(df.index, method='ffill')
    
    base_stock = df['Close'].iloc[0]
    base_benchmark = aligned_benchmark['Close'].iloc[0]
    
    if base_benchmark == 0 or pd.isna(base_benchmark):
        return pd.Series(index=df.index, data=100.0)
    
    rs_line = (df['Close'] / base_stock) / (aligned_benchmark['Close'] / base_benchmark) * 100
    
    return rs_line


def detect_vcp_arcs(prices, dates, window=15):
    """
    Detect VCP contraction arcs using peak/trough detection and quadratic curve fitting.
    Returns a list of arc dicts with x_points, y_points, arc_x, arc_y for drawing.
    """
    peaks, _ = find_peaks(prices, distance=window)
    troughs, _ = find_peaks(-prices, distance=window)
    
    arcs = []
    
    if len(peaks) < 2 or len(troughs) < 1:
        return arcs
    
    # Pair consecutive Peak-Trough-Peak sequences
    all_points = sorted(
        [(i, prices[i], 'peak') for i in peaks] + [(i, prices[i], 'trough') for i in troughs],
        key=lambda x: x[0]
    )
    
    # Find valid P-T-P triplets for arc fitting
    for i in range(len(all_points) - 2):
        p1, t, p2 = all_points[i], all_points[i+1], all_points[i+2]
        if p1[2] == 'peak' and t[2] == 'trough' and p2[2] == 'peak':
            # Only keep arcs where the second peak is lower (contraction)
            if p2[1] < p1[1] * 0.98:
                x_points = [p1[0], t[0], p2[0]]
                y_points = [p1[1], t[1], p2[1]]
                
                # Quadratic curve fitting for smooth arc
                f_arc = interp1d(x_points, y_points, kind='quadratic')
                x_new = np.linspace(x_points[0], x_points[-1], 100)
                y_new = f_arc(x_new)
                
                # Filter out-of-bound indices
                valid_mask = x_new.astype(int) < len(dates)
                x_new = x_new[valid_mask]
                y_new = y_new[valid_mask]
                
                if len(x_new) > 0:
                    arc_dates = dates[x_new.astype(int)]
                    contraction_pct = (p1[1] - p2[1]) / p1[1] * 100
                    
                    arcs.append({
                        'peak1_date': dates[p1[0]],
                        'peak1_price': p1[1],
                        'trough_date': dates[t[0]],
                        'trough_price': t[1],
                        'peak2_date': dates[p2[0]],
                        'peak2_price': p2[1],
                        'contraction_pct': contraction_pct,
                        'arc_dates': arc_dates,
                        'arc_prices': y_new,
                    })
    
    return arcs


def detect_vcp_pattern(df, lookback=60):
    """
    Detect VCP using arc-based contraction detection.
    Returns contraction wave info (T1, T2, ...) and arc data for charting.
    """
    prices = df['High'].values
    dates = df.index.values
    
    arcs = detect_vcp_arcs(prices, dates, window=max(5, len(prices) // 30))
    
    contractions = []
    for i, arc in enumerate(arcs):
        contractions.append({
            'wave': f'T{i+1}',
            'date': arc['peak2_date'],
            'price': arc['peak2_price'],
            'prev_price': arc['peak1_price'],
            'contraction_pct': arc['contraction_pct'],
            'arc_dates': arc['arc_dates'],
            'arc_prices': arc['arc_prices'],
            'peak1_date': arc['peak1_date'],
            'peak1_price': arc['peak1_price'],
            'trough_date': arc['trough_date'],
            'trough_price': arc['trough_price'],
            'peak2_date': arc['peak2_date'],
            'peak2_price': arc['peak2_price'],
        })
    
    return contractions


def calculate_daily_signals(df, benchmark_df, params=None):
    """
    逐日計算 VCP 和 RS 信號
    返回包含每日信號的 DataFrame
    """
    if params is None:
        params = {
            'rs_score_threshold': 70,
            'rs_line_threshold': 100,
            'volatility_max': 12.0,
            'volatility_ma_period': 10,
            'contraction_pct': 0.85,
            'breakout_window': 20,
            'force_index_span': 13,
        }

    df = df.copy()
    
    df['RS_Line'] = calculate_rs_line(df, benchmark_df)
    
    rs_min = df['RS_Line'].rolling(window=252, min_periods=20).min()
    rs_max = df['RS_Line'].rolling(window=252, min_periods=20).max()
    df['RS_Score'] = ((df['RS_Line'] - rs_min) / (rs_max - rs_min) * 100).fillna(50)
    
    window = params.get('breakout_window', 20)
    df['High_20'] = df['High'].rolling(window=window, min_periods=1).max()
    df['Low_20'] = df['Low'].rolling(window=window, min_periods=1).min()
    df['Volatility'] = (df['High_20'] - df['Low_20']) / df['Low_20'] * 100
    
    ma_period = params.get('volatility_ma_period', 10)
    df['Volatility_MA'] = df['Volatility'].rolling(window=ma_period).mean()
    
    # Contraction: current volatility is below the MA and decreasing vs 10 days ago
    contraction_pct = params.get('contraction_pct', 0.85)
    df['Contraction_Trend'] = (
        (df['Volatility'] < df['Volatility_MA']) &
        (df['Volatility'] < df['Volatility'].shift(10) * contraction_pct)
    )
    
    force_span = params.get('force_index_span', 13)
    force_index = (df['Close'] - df['Close'].shift(1)) * df['Volume']
    df['Force_Index'] = force_index.ewm(span=force_span).mean()
    
    rs_thresh = params.get('rs_score_threshold', 70)
    vol_max = params.get('volatility_max', 12.0)
    
    df['VCP_Signal'] = (
        (df['RS_Score'] > rs_thresh) &
        (df['RS_Line'] > params.get('rs_line_threshold', 100)) &
        (df['Volatility'] < vol_max) &
        (df['Contraction_Trend']) &
        (df['Force_Index'] > 0)
    )
    
    df['Breakout'] = df['Close'] >= df['High_20']
    
    df['Signal'] = df['VCP_Signal'] & df['Breakout']
    
    vcp_contractions = detect_vcp_pattern(df)
    df['VCP_Contractions'] = [vcp_contractions] * len(df)
    
    # Store arcs separately for chart drawing
    df['VCP_Arcs'] = [vcp_contractions] * len(df)
    
    return df


def print_signal_summary(df):
    """
    打印信號摘要
    """
    signals = df[df['Signal']].copy()
    
    if signals.empty:
        print("\nNo breakout signals found.")
        return
    
    print("\n" + "="*70)
    print("SIGNAL SUMMARY - Breakout Points")
    print("="*70)
    print(f"{'Date':<12} {'Price':>10} {'RS Line':>10} {'RS Score':>10} {'Volatility':>12}")
    print("-"*70)
    
    for idx, row in signals.iterrows():
        date_str = idx.strftime('%Y-%m-%d')
        print(f"{date_str:<12} ${row['Close']:>8.2f} {row['RS_Line']:>10.1f} "
              f"{row['RS_Score']:>10.1f} {row['Volatility']:>10.2f}%")
    
    print("="*70)
    print(f"Total breakout signals: {len(signals)}")
