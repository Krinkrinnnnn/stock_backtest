"""
Stock Screen Filters
====================
Liquidity filter and new high Relative Strength flag for stock screeners.

Liquidity Filter:
- Market cap > $2B
- 21-day average volume > $50M

New High RS Flag:
- Stock's RS Line is at a new N-day high
- Indicates the stock is outperforming the market at its strongest point
"""

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
import warnings

warnings.filterwarnings("ignore")


LIQUIDITY_PARAMS = {
    "min_market_cap": 2_000_000_000,  # $2B
    "min_avg_volume": 50_000_000,     # $50M (21-day)
    "min_price": 20,                  # $20 minimum price
    "volume_period": 21,
    "valid_exchanges": ["NYSE", "NASDAQ", "AMEX"],  # Only major US exchanges
}

# Common ETFs to exclude from stock screeners
EXCLUDED_ETFS = {
    # Major Index ETFs
    "SPY", "QQQ", "IWM", "DIA", "VTI", "VOO", "VEA", "VWO", "EFA", "EEM",
    "IVV", "VO", "VB", "VTV", "VUG", "VGT", "VGK", "VPL", "VXUS", "BND",
    "AGG", "TLT", "IEF", "SHY", "LQD", "HYG", "JNK", "MUB", "TIP",
    # Sector ETFs
    "XLF", "XLK", "XLV", "XLE", "XLI", "XLP", "XLY", "XLU", "XLB", "XLRE", "XLC",
    "XOP", "OIH", "KBE", "KRE", "SMH", "SOXX", "IGV", "HACK", "BOTZ", "ARKK",
    "ARKW", "ARKG", "ARKF", "ARKQ", "ICLN", "TAN", "LIT", "REMX", "GDX", "GDXJ",
    "SLV", "GLD", "USO", "UNG", "DBA", "DBC", "PDBC",
    # Leveraged/Inverse ETFs
    "TQQQ", "SQQQ", "SPXL", "SPXS", "UPRO", "SPXU", "UDOW", "SDOW",
    "TNA", "TZA", "LABU", "LABD", "NUGT", "DUST", "JNUG", "JDST",
    # Bond ETFs
    "BND", "BNDX", "VCIT", "VCSH", "VGIT", "VGLT", "BSV", "BIV", "BLV",
    # International ETFs
    "EWJ", "EWZ", "EWT", "EWY", "EWW", "EWG", "EWU", "EWL", "EWA", "EWC",
    "FXI", "MCHI", "KWEB", "ASHR", "EEM", "VWO",
    # Commodity ETFs
    "USO", "UCO", "SCO", "UNG", "BOIL", "KOLD", "GLD", "IAU", "SLV",
    "DBA", "CORN", "WEAT", "SOYB",
    # Volatility ETFs
    "VXX", "VIXY", "UVXY", "SVXY",
}

# Oil/Energy sector tickers to exclude
EXCLUDED_OIL_ENERGY = {
    # Major Oil Companies
    "XOM", "CVX", "COP", "EOG", "PXD", "MPC", "PSX", "VLO", "HES", "DVN",
    "OXY", "FANG", "HES", "MRO", "APA", "CTRA", "EQT", "AR", "OVV",
    "COP", "HAL", "SLB", "BKR", "FTI", "NOV", "CHX", "LBRT",
    # Oil Services
    "SLB", "HAL", "BKR", "FTI", "NOV", "CHX", "LBRT", "PTEN", "HP",
    "RIG", "VAL", "NE", "DO", "BORR", "SDRL",
    # Midstream/Pipeline
    "ET", "EPD", "ETP", "MPLX", "PAA", "PAGP", "WMB", "KMI", "OKE",
    "TRGP", "AM", "GEL", "NS", "CEQP", "HESM", "SMLP",
    # Refining
    "MPC", "PSX", "VLO", "PBF", "DK", "CVI", "DINO", "CLMT",
    # Exploration & Production
    "XOM", "CVX", "COP", "EOG", "PXD", "DVN", "OXY", "FANG", "HES",
    "MRO", "APA", "CTRA", "EQT", "AR", "OVV", "MTDR", "PR", "SM",
    "CIVI", "GPOR", "RRC", "SU", "CNQ", "CVE", "IMO", "TRP",
}

NEW_HIGH_RS_PARAMS = {
    "lookback_days": 252,  # 1 year
    "confirm_days": 5,      # Must be at new high for this many days
}

ADR_PARAMS = {
    "min_adr_percent": 4.0,  # Minimum average daily range > 4%
    "lookback_days": 20,     # Number of days to average over
}

# Ticker substrings that indicate invalid/warrant/share classes
INVALID_TICKER_SUBSTRINGS = ['.W', '-W', '-P', '.P', '-R', '.R', '^', '/', '$', '.U', '.PR', 'PR', '.A', '.B', '.V']


def is_etf_or_oil(ticker):
    """
    Check if a ticker is an ETF or oil/energy stock.
    
    Args:
        ticker: Stock symbol
        
    Returns:
        bool: True if ticker should be excluded (is ETF or oil/energy)
    """
    ticker_upper = ticker.upper().strip()
    return ticker_upper in EXCLUDED_ETFS or ticker_upper in EXCLUDED_OIL_ENERGY


def filter_etf_and_oil(tickers):
    """
    Filter out ETFs and oil/energy stocks from a list of tickers.
    
    Args:
        tickers: List of stock symbols
        
    Returns:
        tuple: (valid_tickers, excluded_tickers)
    """
    valid = []
    excluded = []
    for t in tickers:
        if is_etf_or_oil(t):
            excluded.append(t)
        else:
            valid.append(t)
    return valid, excluded


def filter_invalid_tickers(tickers):
    """Pre-filter obviously invalid ticker formats."""
    valid = []
    invalid = []
    for t in tickers:
        if any(sub in t for sub in INVALID_TICKER_SUBSTRINGS):
            invalid.append(t)
        else:
            valid.append(t)
    return valid, invalid


def download_all_data(tickers, period="1mo", chunk_size=100, pause=0.5):
    """
    Download OHLCV data for a large list of tickers sequentially in chunks.
    
    This single-threaded approach prevents Yahoo Finance rate-limiting by:
    - Downloading chunks of `chunk_size` tickers at a time
    - Pausing between chunks to avoid overwhelming the API
    - Handling multi-index columns from yfinance
    
    Args:
        tickers: List of stock symbols
        period: yfinance period string (e.g., "1mo", "3mo", "1y")
        chunk_size: Number of tickers per download request (default 100)
        pause: Seconds to pause between chunks (default 0.5)
        
    Returns:
        dict: {ticker: DataFrame} with OHLCV data for each ticker
    """
    import time
    
    # Pre-filter invalid tickers
    valid_tickers, _ = filter_invalid_tickers(tickers)
    
    if not valid_tickers:
        print("    No valid tickers to download.")
        return {}
    
    print(f"    Downloading data for {len(valid_tickers)} tickers in chunks of {chunk_size}...")
    
    all_data = {}
    total_chunks = (len(valid_tickers) + chunk_size - 1) // chunk_size
    
    for chunk_idx in range(0, len(valid_tickers), chunk_size):
        chunk = valid_tickers[chunk_idx:chunk_idx + chunk_size]
        chunk_num = chunk_idx // chunk_size + 1
        
        try:
            raw = yf.download(
                chunk, 
                period=period, 
                progress=False, 
                group_by="ticker",
                timeout=60
            )
            
            if raw is None or raw.empty:
                print(f"      Chunk {chunk_num}/{total_chunks}: No data returned")
                continue
            
            # Parse MultiIndex columns (multi-ticker download)
            if isinstance(raw.columns, pd.MultiIndex):
                for t in chunk:
                    if t in raw.columns.levels[0]:
                        df = raw[t].dropna(how='all')
                        if not df.empty and 'Close' in df.columns:
                            all_data[t] = df
            else:
                # Single ticker case
                if len(chunk) == 1 and not raw.empty:
                    if 'Close' in raw.columns:
                        all_data[chunk[0]] = raw
            
            print(f"      Chunk {chunk_num}/{total_chunks}: {len(chunk)} tickers "
                  f"({len([t for t in chunk if t in all_data])} with data)")
                  
        except Exception as e:
            print(f"      Chunk {chunk_num}/{total_chunks}: Failed ({e})")
        
        # Pause between chunks to respect rate limits
        if chunk_idx + chunk_size < len(valid_tickers):
            time.sleep(pause)
    
    print(f"    Download complete: {len(all_data)}/{len(valid_tickers)} tickers with data")
    return all_data


def check_liquidity(ticker, params=None):
    """
    Check if stock meets liquidity criteria.
    
    Args:
        ticker: Stock symbol
        params: Optional override parameters
        
    Returns:
        tuple: (passes: bool, details: dict)
    """
    if params is None:
        params = LIQUIDITY_PARAMS
    
    # Skip invalid ticker formats (preferred shares, warrants, etc.)
    # We check for these exact substrings or suffixes, not just any character match
    invalid_substrings = ['.W', '-W', '-P', '.P', '-R', '.R', '^', '/']
    if any(sub in ticker for sub in invalid_substrings):
        return False, {"ticker": ticker, "passes": False, "reason": "invalid_format"}
    
    details = {
        "ticker": ticker,
        "exchange": None,
        "price": 0,
        "market_cap": 0,
        "avg_volume_21d": 0,
        "avg_dollar_volume": 0,
        "passes": False,
    }
    
    # Filter out preferred stocks, warrants, units, etc.
    if any(c in ticker for c in ['$', '.W', '.U', '.R', '.P']):
        return False, details
    
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        
        if not info:
            return False, details
        
        # Get exchange
        exchange = info.get("exchange", "") or ""
        details["exchange"] = exchange
        
        # Check exchange is valid (NYSE, NASDAQ, or AMEX)
        valid_exchanges = params.get("valid_exchanges", ["NYSE", "NASDAQ", "AMEX"])
        exchange_valid = exchange in valid_exchanges
        
        # Get price
        current_price = info.get("currentPrice", 0) or info.get("regularMarketPrice", 0) or 0
        if current_price == 0:
            hist = stock.history(period="1d")
            if not hist.empty:
                current_price = hist['Close'].iloc[-1]
        
        details["price"] = current_price
        
        # Check price >= min_price
        min_price = params.get("min_price", 20)
        price_valid = current_price >= min_price if min_price > 0 else True
        
        # Get market cap
        market_cap = info.get("marketCap", 0) or 0
        details["market_cap"] = market_cap
        
        # Get volume
        avg_volume_21d = info.get("averageVolume", 0) or 0
        if avg_volume_21d == 0:
            hist = stock.history(period="1mo")
            if not hist.empty:
                avg_volume_21d = hist['Volume'].rolling(21).mean().iloc[-1]
        
        details["avg_volume_21d"] = avg_volume_21d
        
        # Calculate dollar volume
        dollar_volume = current_price * avg_volume_21d if current_price > 0 else 0
        details["avg_dollar_volume"] = dollar_volume
        
        # All conditions must pass
        passes = (
            exchange_valid and
            price_valid and
            market_cap >= params["min_market_cap"] and
            dollar_volume >= params["min_avg_volume"]
        )
        details["passes"] = passes
        
        return passes, details
        
    except Exception as e:
        return False, details


def check_new_high_rs(ticker, benchmark_symbol="^GSPC", params=None, df=None):
    """
    Check if stock's RS Line is at a new high.
    
    Args:
        ticker: Stock symbol
        benchmark_symbol: Benchmark ticker (default: ^GSPC)
        params: Optional override parameters
        df: Pre-fetched stock data (optional)
        
    Returns:
        tuple: (is_new_high: bool, details: dict)
    """
    if params is None:
        params = NEW_HIGH_RS_PARAMS
    
    details = {
        "ticker": ticker,
        "rs_line": 0,
        "rs_252d_high": 0,
        "rs_52w_high": 0,
        "is_new_high_252d": False,
        "is_new_high_52w": False,
        "is_new_high_rs": False,
    }
    
    try:
        end_date = datetime.now()
        start_date = end_date - timedelta(days=params["lookback_days"] + 50)
        
        if df is None:
            stock = yf.Ticker(ticker)
            df = stock.history(start=start_date, end=end_date, progress=False)
        
        if df is None or len(df) < 60:
            return False, details
        
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        
        benchmark = yf.Ticker(benchmark_symbol)
        benchmark_df = benchmark.history(start=start_date, end=end_date, progress=False)
        
        if benchmark_df is None or len(benchmark_df) < 60:
            return False, details
        
        if isinstance(benchmark_df.columns, pd.MultiIndex):
            benchmark_df.columns = benchmark_df.columns.get_level_values(0)
        
        price_col = 'Adj Close' if 'Adj Close' in df.columns else 'Close'
        bench_col = 'Adj Close' if 'Adj Close' in benchmark_df.columns else 'Close'
        
        aligned_bench = benchmark_df.reindex(df.index, method='ffill')
        
        if aligned_bench.empty or df[price_col].iloc[0] <= 0 or aligned_bench[bench_col].iloc[0] <= 0:
            return False, details
        
        base_stock = df[price_col].iloc[0]
        base_bench = aligned_bench[bench_col].iloc[0]
        
        rs_line = (df[price_col] / base_stock) / (aligned_bench[bench_col] / base_bench)
        
        details["rs_line"] = rs_line.iloc[-1]
        
        rs_252d_high = rs_line.rolling(252).max().iloc[-1]
        rs_52w_high = rs_line.rolling(52).max().iloc[-1]
        
        details["rs_252d_high"] = rs_252d_high
        details["rs_52w_high"] = rs_52w_high
        
        current_rs = rs_line.iloc[-1]
        epsilon = 0.0001
        
        details["is_new_high_252d"] = current_rs >= rs_252d_high - epsilon
        details["is_new_high_52w"] = current_rs >= rs_52w_high - epsilon
        
        min_periods = min(params["lookback_days"], len(rs_line))
        rolling_max = rs_line.rolling(params["lookback_days"], min_periods=20).max()
        
        recent_highs = rolling_max.iloc[-params["confirm_days"]:].iloc[0]
        
        details["is_new_high_rs"] = (
            details["is_new_high_252d"] and
            current_rs >= rolling_max.iloc[-params["confirm_days"]] - epsilon if len(rolling_max) >= params["confirm_days"] else details["is_new_high_252d"]
        )
        
        details["is_new_high_rs"] = details["is_new_high_252d"]
        
        return details["is_new_high_rs"], details
        
    except Exception as e:
        return False, details


def check_adr(ticker, params=None, df=None):
    """
    Check if stock meets Average Daily Range (ADR) > threshold.
    
    Args:
        ticker: Stock symbol
        params: Optional override parameters
        df: Pre-fetched stock data (optional)
        
    Returns:
        tuple: (passes: bool, details: dict)
    """
    if params is None:
        params = ADR_PARAMS
    
    details = {
        "ticker": ticker,
        "adr_percent": 0.0,
        "min_adr_percent": params["min_adr_percent"],
        "lookback_days": params["lookback_days"],
        "passes": False,
    }
    
    try:
        if df is None:
            stock = yf.Ticker(ticker)
            # Fetch enough history for lookback_days
            df = stock.history(period="3mo")
        
        if df is None or len(df) < params["lookback_days"]:
            return False, details
        
        # Ensure we have the required columns
        if 'High' not in df.columns or 'Low' not in df.columns:
            return False, details
        
        # Calculate Daily Range: (High/Low - 1) * 100
        df['DR'] = (df['High'] / df['Low'] - 1) * 100
        
        # Calculate ADR over the last lookback_days
        adr = df['DR'].iloc[-params["lookback_days"]:].mean()
        
        details["adr_percent"] = adr
        details["passes"] = adr >= params["min_adr_percent"]
        
        return details["passes"], details
        
    except Exception as e:
        return False, details


EARNINGS_PARAMS = {
    "exclude_days_before": 7,   # Skip stocks with earnings within 7 days
    "exclude_days_after": 1,    # Skip stocks that reported earnings within 1 day
}


def check_earnings(ticker, params=None):
    """
    Check if a stock has upcoming or recent earnings that should be avoided.
    Returns (passes, details) where passes=True means safe to trade (no earnings near).
    
    Args:
        ticker: Stock symbol
        params: Optional override parameters
        
    Returns:
        tuple: (passes: bool, details: dict)
    """
    if params is None:
        params = EARNINGS_PARAMS
    
    details = {
        "ticker": ticker,
        "next_earnings_date": None,
        "days_until_earnings": None,
        "last_earnings_date": None,
        "days_since_earnings": None,
        "passes": True,
        "reason": "no_earnings_found",
    }
    
    try:
        stock = yf.Ticker(ticker)
        cal = stock.calendar
        
        if cal is None:
            details["reason"] = "no_calendar_data"
            return True, details
        
        # Handle both dict and DataFrame formats
        earnings_date = None
        if isinstance(cal, dict):
            raw = cal.get("Earnings Date")
            if raw is None:
                details["reason"] = "no_earnings_date_found"
                return True, details
            # Could be a list of dates
            if isinstance(raw, (list, np.ndarray)):
                earnings_date = raw[0] if raw else None
            else:
                earnings_date = raw
        elif isinstance(cal, pd.DataFrame) and not cal.empty:
            if 'Earnings Date' in cal.index:
                val = cal.loc['Earnings Date']
                if isinstance(val, pd.Series):
                    earnings_date = val.iloc[0]
                else:
                    earnings_date = val
        
        if earnings_date is None:
            details["reason"] = "no_earnings_date_found"
            return True, details
        
        # Convert to date object
        if isinstance(earnings_date, str):
            earnings_date = pd.to_datetime(earnings_date).date()
        elif hasattr(earnings_date, 'date'):
            earnings_date = earnings_date
        elif isinstance(earnings_date, datetime):
            earnings_date = earnings_date.date()
        
        today = datetime.now().date()
        days_diff = (earnings_date - today).days
        
        details["next_earnings_date"] = str(earnings_date)
        details["days_until_earnings"] = days_diff
        
        # Check if earnings are within the exclusion window
        if 0 <= days_diff <= params["exclude_days_before"]:
            details["passes"] = False
            details["reason"] = f"earnings_in_{days_diff}_days"
            return False, details
        
        # Check if earnings just happened (post-earnings volatility)
        if -params["exclude_days_after"] <= days_diff < 0:
            details["passes"] = False
            details["reason"] = f"earnings_{abs(days_diff)}_days_ago"
            return False, details
        
        details["reason"] = "safe"
        return True, details
        
    except Exception as e:
        details["reason"] = f"error: {str(e)}"
        return True, details


def filter_liquidity_batch(tickers, params=None):
    """
    Check liquidity for a batch of tickers using a single yfinance download call 
    to avoid heavy rate-limiting and dramatically speed up Phase 1.
    
    Args:
        tickers: List of stock symbols
        params: Optional override parameters
        
    Returns:
        dict: {ticker: (passes: bool, details: dict)}
    """
    if params is None:
        params = LIQUIDITY_PARAMS
        
    results = {}
    
    # Fast initial filtering for obviously bad formats
    invalid_substrings = ['.W', '-W', '-P', '.P', '-R', '.R', '^', '/', '$', '.U']
    valid_tickers = []
    
    for t in tickers:
        if any(sub in t for sub in invalid_substrings):
            results[t] = (False, {"ticker": t, "passes": False, "reason": "invalid_format"})
        else:
            valid_tickers.append(t)
            
    if not valid_tickers:
        return results

    try:
        # Download 1 month of data for the whole batch
        # This is one single API call to Yahoo, totally bypassing per-ticker rate limits
        data = yf.download(valid_tickers, period="1mo", progress=False, group_by="ticker")
        
        # We need volume and close prices
        for t in valid_tickers:
            details = {
                "ticker": t,
                "exchange": "Unknown", # Can't get easily from download, assuming valid if it downloads
                "price": 0,
                "market_cap": 0, # Skip market cap constraint if using fast batch download
                "avg_volume_21d": 0,
                "avg_dollar_volume": 0,
                "passes": False,
            }
            
            try:
                # Handle MultiIndex returned by yfinance group_by="ticker"
                if isinstance(data.columns, pd.MultiIndex):
                    if t not in data.columns.levels[0]:
                        results[t] = (False, details)
                        continue
                    df = data[t]
                else:
                    # Fallback in case yfinance changes behavior
                    df = data
                    
                if df.empty or 'Close' not in df.columns or 'Volume' not in df.columns:
                    results[t] = (False, details)
                    continue
                    
                df = df.dropna(subset=['Close', 'Volume'])
                if len(df) < 5:  # Need at least a few days of data
                    results[t] = (False, details)
                    continue
                
                # Extract values safely extracting scalar from pandas series/frame
                latest_price = float(df['Close'].iloc[-1])
                avg_vol = float(df['Volume'].tail(params["volume_period"]).mean())
                avg_dollar_vol = avg_vol * latest_price
                
                details["price"] = latest_price
                details["avg_volume_21d"] = avg_vol
                details["avg_dollar_volume"] = avg_dollar_vol
                
                # Check parameters
                passes_price = latest_price >= params["min_price"]
                passes_volume = avg_dollar_vol >= params["min_avg_volume"]
                
                if passes_price and passes_volume:
                    details["passes"] = True
                    results[t] = (True, details)
                else:
                    results[t] = (False, details)
            except Exception as e:
                results[t] = (False, details)
                
    except Exception as e:
        print(f"Batch liquidity download failed: {e}")
        # Fallback to failing them gracefully
        for t in valid_tickers:
            results[t] = (False, {"ticker": t, "passes": False, "reason": "download_failed"})

    return results


def filter_adr_batch(tickers, params=None):
    """
    Check ADR for a batch of tickers.
    
    Args:
        tickers: List of stock symbols
        params: Optional override parameters
        
    Returns:
        dict: {ticker: (passes: bool, details: dict)}
    """
    if params is None:
        params = ADR_PARAMS
    
    results = {}
    for ticker in tickers:
        passes, details = check_adr(ticker, params)
        results[ticker] = (passes, details)
    
    return results


def get_adr_passing_tickers(tickers, params=None):
    """
    Filter a list of tickers to only those meeting ADR criteria.
    
    Args:
        tickers: List of stock symbols
        params: Optional override parameters
        
    Returns:
        list: Tickers that pass ADR filter
    """
    if params is None:
        params = ADR_PARAMS
    
    passing = []
    for ticker in tickers:
        passes, _ = check_adr(ticker, params)
        if passes:
            passing.append(ticker)
    
    return passing


def get_liquid_tickers(tickers, params=None):
    """
    Filter a list of tickers to only those meeting liquidity criteria.
    
    Args:
        tickers: List of stock symbols
        params: Optional override parameters
        
    Returns:
        list: Tickes that pass liquidity filter
    """
    if params is None:
        params = LIQUIDITY_PARAMS
    
    liquid = []
    for ticker in tickers:
        passes, _ = check_liquidity(ticker, params)
        if passes:
            liquid.append(ticker)
    
    return liquid


def add_rs_high_flag(results_df, benchmark_symbol="^GSPC"):
    """
    Add 'new_high_rs' flag to screener results.
    
    Args:
        results_df: DataFrame with 'ticker' column
        benchmark_symbol: Benchmark for RS calculation
        
    Returns:
        DataFrame with new_high_rs column added
    """
    new_high_rs_flags = []
    
    for ticker in results_df['ticker']:
        is_high, _ = check_new_high_rs(ticker, benchmark_symbol)
        new_high_rs_flags.append(is_high)
    
    results_df['new_high_rs'] = new_high_rs_flags
    return results_df


if __name__ == "__main__":
    import sys
    
    test_tickers = ["AAPL", "TSLA", "NVDA", "MSFT", "AMC", "BBBY"]
    
    print("\n" + "="*70)
    print("  LIQUIDITY FILTER TEST")
    print("="*70)
    
    for ticker in test_tickers:
        passes, details = check_liquidity(ticker)
        print(f"\n{ticker}:")
        print(f"  Market Cap: ${details['market_cap']:,.0f}" if details['market_cap'] > 0 else "  Market Cap: N/A")
        print(f"  Avg Vol (21d): {details['avg_volume_21d']:,.0f}" if details['avg_volume_21d'] > 0 else "  Avg Vol: N/A")
        print(f"  Dollar Vol: ${details['avg_dollar_volume']:,.0f}" if details['avg_dollar_volume'] > 0 else "  Dollar Vol: N/A")
        print(f"  Passes: {'YES' if passes else 'NO'}")
    
    print("\n" + "="*70)
    print("  NEW HIGH RS TEST")
    print("="*70)
    
    for ticker in test_tickers:
        is_high, details = check_new_high_rs(ticker)
        print(f"\n{ticker}:")
        print(f"  RS Line: {details['rs_line']:.2f}")
        print(f"  252d RS High: {details['rs_252d_high']:.2f}")
        print(f"  52w RS High: {details['rs_52w_high']:.2f}")
        print(f"  New High RS: {'YES' if is_high else 'NO'}")
    
    print("\n" + "="*70)
    print("  ADR (Average Daily Range) TEST")
    print("="*70)
    
    for ticker in test_tickers:
        passes, details = check_adr(ticker)
        print(f"\n{ticker}:")
        print(f"  ADR: {details['adr_percent']:.2f}%")
        print(f"  Passes (>={details['min_adr_percent']:.1f}%): {'YES' if passes else 'NO'}")
    
    print("\n" + "="*70)


def _fetch_market_cap(ticker):
    """Fetch market cap for a single ticker using fast_info."""
    try:
        cap = yf.Ticker(ticker).fast_info.get("marketCap")
        if cap and cap > 0:
            return ticker, float(cap)
    except Exception:
        pass
    return ticker, None


def filter_by_market_cap(tickers, min_cap_billions=0, max_cap_billions=float('inf')):
    """
    Filter tickers by market cap range using multi-threaded fast_info lookup.

    Args:
        tickers: List of ticker symbols.
        min_cap_billions: Minimum market cap in billions (inclusive).
        max_cap_billions: Maximum market cap in billions (exclusive).

    Returns:
        list: Tickers within the specified market cap range.
             Tickers with missing/NaN market cap are excluded.
    """
    if not tickers:
        return []

    cap_map = {}
    with ThreadPoolExecutor(max_workers=min(20, len(tickers))) as executor:
        futures = {executor.submit(_fetch_market_cap, t): t for t in tickers}
        for future in as_completed(futures):
            ticker, cap = future.result()
            if cap is not None:
                cap_map[ticker] = cap / 1e9  # Convert to billions

    filtered = [
        t for t in tickers
        if t in cap_map and min_cap_billions <= cap_map[t] < max_cap_billions
    ]

    print(f"  Market Cap Filter: {len(filtered)}/{len(tickers)} passed "
          f"(${min_cap_billions}B - ${max_cap_billions}B)")

    return sorted(filtered)
