import yfinance as yf
import pandas as pd
import numpy as np
import sys

def check_correlation_warnings(tickers, threshold=0.7, days=40):
    """
    Downloads historical data for the given tickers and calculates their correlation matrix.
    Prints a warning for any pairs that have a correlation coefficient > threshold.
    """
    if not tickers or len(tickers) < 2:
        return

    print(f"\n" + "="*70)
    print(f"  [!] CORRELATION RISK ANALYSIS (Lookback: {days} days)")
    print("="*70)
    print(f"  Checking for false diversification (r > {threshold:.2f})...")

    try:
        data = yf.download(tickers, period=f"{days}d", progress=False)
        
        if isinstance(data.columns, pd.MultiIndex):
            if 'Close' in data.columns.levels[0]:
                data = data['Close']
            elif 'Adj Close' in data.columns.levels[0]:
                data = data['Adj Close']
        else:
            print("  Not enough valid ticker data to compute correlation.")
            print("="*70)
            return
            
        if isinstance(data, pd.Series) or len(data.columns) < 2:
            print("  Not enough valid ticker data to compute correlation.")
            print("="*70)
            return

        returns = data.pct_change().dropna()
        corr_matrix = returns.corr()

        high_corr_pairs = []
        
        for i in range(len(corr_matrix.columns)):
            for j in range(i + 1, len(corr_matrix.columns)):
                corr_val = corr_matrix.iloc[i, j]
                if abs(corr_val) > threshold:
                    t1 = corr_matrix.columns[i]
                    t2 = corr_matrix.columns[j]
                    high_corr_pairs.append((t1, t2, corr_val))

        high_corr_pairs.sort(key=lambda x: abs(x[2]), reverse=True)

        if high_corr_pairs:
            print(f"\n  [!] HIGH RISK DETECTED: The following pairs move together.")
            print(f"  Holding them together increases sector concentration risk:\n")
            for t1, t2, corr in high_corr_pairs:
                direction = "Strong Positive" if corr > 0 else "Strong Negative"
                print(f"  - {t1:<5} & {t2:<5} (r = {corr:>5.2f})  [!] {direction}")
        else:
            print(f"\n  [OK] Pass: No highly correlated pairs found.")
            print(f"  Your portfolio appears well-diversified among these candidates.")
            
    except Exception as e:
        print(f"  Error calculating correlation: {e}")
        
    print("="*70 + "\n")
