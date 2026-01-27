"""
Data Fetcher Module - CORRECTED VERSION

Fetches real cryptocurrency price data from Binance API

Based on DATA_FETCHING_INSTRUCTIONS.md

Fixes:
1. Format open_time as string for CSV storage
2. Deduplicate by open_time (not date)
3. Consistent timezone handling
4. Fixed validation function
"""

import requests
import pandas as pd
import time
from datetime import datetime, timedelta
import os
import re
from tqdm import tqdm

BASE_URL = "https://api.binance.com/api/v3/klines"

def get_klines(symbol, interval, start_time=None, end_time=None, limit=1000):
    """
    Fetch klines (candlestick data) from Binance API.
    
    Parameters:
        symbol: Trading pair symbol (e.g., "BTCUSDT")
        interval: Candle interval ("1m", "5m", "1h", "1d", etc.)
        start_time: Start timestamp in milliseconds (optional)
        end_time: End timestamp in milliseconds (optional)
        limit: Maximum number of candles per request (default: 1000, max: 1000)
    
    Returns:
        List of candle data arrays
    """
    params = {
        "symbol": symbol,
        "interval": interval,
        "limit": limit,
    }
    if start_time:
        params["startTime"] = start_time
    if end_time:
        params["endTime"] = end_time
    
    response = requests.get(BASE_URL, params=params)
    response.raise_for_status()
    return response.json()

def parse_time_window(time_window_str):
    """
    Parse time window string (e.g., "7d", "24h", "30d") to timedelta.
    
    Returns:
        timedelta object or None if invalid
    """
    if not time_window_str:
        return None
    
    pattern = r'^(\d+)([dhms])$'
    match = re.match(pattern, time_window_str.lower())
    if not match:
        return None
    
    value = int(match.group(1))
    unit = match.group(2)
    
    unit_map = {
        's': timedelta(seconds=1),
        'm': timedelta(minutes=1),
        'h': timedelta(hours=1),
        'd': timedelta(days=1)
    }
    
    return value * unit_map.get(unit, timedelta(days=1))


def download_full_history(symbol, interval="1m", start_str="2017-08-01", skip_start=False, 
                          max_records=None, end_date=None, time_window=None):
    """
    Download full OHLCV history with pagination and resume support.
    
    Parameters:
        symbol: Trading pair (e.g., "BTCUSDT")
        interval: Candle interval (default: "1m")
        start_str: Start date as string (format: "YYYY-MM-DD")
        skip_start: If True, exclude data before start_str
        max_records: Maximum number of candles to fetch (None = no limit)
        end_date: End date as string (format: "YYYY-MM-DD") - stops at this date instead of "now"
        time_window: Time window string (e.g., "7d", "24h") - fetches last N days/hours from start
    
    Returns:
        pd.DataFrame with columns: open_time, open, high, low, close, volume,
        quote_asset_volume, trades, taker_base, taker_quote, ignore
        (open_time is formatted as 'YYYY-MM-DD HH:MM:SS' string per instructions)
    """
    start_ts = int(pd.Timestamp(start_str).timestamp() * 1000)
    
    # Calculate end timestamp
    if time_window:
        # Parse time window (e.g., "7d" = 7 days from start)
        window_delta = parse_time_window(time_window)
        if window_delta:
            start_dt = pd.Timestamp(start_str)
            end_dt = start_dt + window_delta
            end_ts = int(end_dt.timestamp() * 1000)
        else:
            print(f"⚠️  Invalid time_window format: {time_window}. Using 'now' as end time.")
            end_ts = int(datetime.now().timestamp() * 1000)
    elif end_date:
        # Use specified end date
        end_ts = int(pd.Timestamp(end_date).timestamp() * 1000)
    else:
        # Default: fetch up to current time
        end_ts = int(datetime.now().timestamp() * 1000)
    
    # Ensure end_ts is after start_ts
    if end_ts <= start_ts:
        raise ValueError(f"End time must be after start time. Start: {start_str}, End: {end_date or 'now'}")
    
    all_candles = []
    request_count = 0
    start_time = time.time()
    
    # Calculate estimated total records
    time_range_ms = end_ts - start_ts
    interval_seconds = {
        '1m': 60, '3m': 180, '5m': 300, '15m': 900, '30m': 1800,
        '1h': 3600, '2h': 7200, '4h': 14400, '6h': 21600, '8h': 28800, '12h': 43200,
        '1d': 86400, '3d': 259200, '1w': 604800, '1M': 2592000
    }
    seconds_per_candle = interval_seconds.get(interval, 60)
    estimated_total = int(time_range_ms / 1000 / seconds_per_candle)
    
    # Apply max_records limit if set
    if max_records:
        estimated_total = min(estimated_total, max_records)
    
    # Warn if very large dataset
    if estimated_total > 100000 and not max_records:
        print(f"⚠️  Warning: Estimated {estimated_total:,} candles to fetch!")
        print(f"   This may take {estimated_total // 240:.0f} minutes or more.")
        print(f"   Consider using --max-records, --end-date, or --time-window to limit the fetch.")
        print(f"   Press Ctrl+C to cancel, or wait for it to complete...")
        print()
    
    # Build status message
    status_msg = f"Downloading {symbol} data from {start_str}"
    if end_date:
        status_msg += f" to {end_date}"
    elif time_window:
        status_msg += f" (last {time_window})"
    else:
        status_msg += " to now"
    status_msg += "..."
    print(status_msg)
    
    if max_records:
        print(f"Limiting to {max_records:,} records maximum")
    
    # Initialize progress bar
    pbar = tqdm(total=estimated_total, unit='candles', desc='Fetching', 
                bar_format='{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}, {rate_fmt}]')
    
    try:
        while True:
            # Set end_time for API request if we're near the end
            request_end_ts = None
            if end_ts < int(datetime.now().timestamp() * 1000):
                request_end_ts = end_ts
            
            try:
                candles = get_klines(symbol, interval, start_time=start_ts, end_time=request_end_ts)
            except Exception as e:
                pbar.write(f"⚠️ Error: {e}, retrying in 5s...")
                time.sleep(5)
                continue
            
            if not candles:
                break
            
            # Filter candles that exceed end_ts if needed
            if end_ts < int(datetime.now().timestamp() * 1000):
                filtered_candles = [c for c in candles if c[6] <= end_ts]  # c[6] is close_time
                if not filtered_candles:
                    break
                candles = filtered_candles
            
            all_candles.extend(candles)
            request_count += 1
            
            # Update progress bar
            pbar.update(len(candles))
            
            # Get last close time to continue pagination
            last_close_time = candles[-1][6]  # Index 6 is close_time
            start_ts = last_close_time + 1
            
            # Respect rate limits
            time.sleep(0.25)
            
            # Stop if we've reached end time
            if last_close_time >= end_ts:
                pbar.write(f"  Reached end time. Stopping...")
                break
            
            # Stop if we've reached max_records
            if max_records and len(all_candles) >= max_records:
                pbar.write(f"  Reached maximum record limit ({max_records:,}). Stopping...")
                break
            
            # Stop if API returns fewer candles (no more data available)
            if len(candles) < 1000:
                pbar.write(f"  No more data available. Stopping...")
                break
        
        pbar.close()
    
    except KeyboardInterrupt:
        pbar.close()
        print("\n⚠️ Operation cancelled by user")
        if all_candles:
            print(f"  Saving {len(all_candles):,} candles fetched so far...")
    
    if not all_candles:
        print(f"⚠️ No data found for {symbol}")
        return pd.DataFrame()
    
    # Convert to DataFrame
    df = pd.DataFrame(all_candles, columns=[
        "open_time", "open", "high", "low", "close", "volume",
        "close_time", "quote_asset_volume", "trades", "taker_base",
        "taker_quote", "ignore"
    ])
    
    # Drop close_time (redundant with open_time)
    df = df.drop(columns=["close_time"])
    
    # Convert open_time from milliseconds to datetime (UTC)
    df["open_time"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
    
    if skip_start:
        df = df[df["open_time"] > pd.to_datetime(start_str, utc=True)]
    
    # Format open_time as string per instructions: 'YYYY-MM-DD HH:MM:SS'
    df["open_time"] = df["open_time"].dt.strftime('%Y-%m-%d %H:%M:%S')
    
    # Convert numeric columns
    numeric_cols = ["open", "high", "low", "close", "volume", "taker_base", 
                     "taker_quote", "quote_asset_volume", "ignore"]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col])
    
    # Sort by open_time
    df = df.sort_values("open_time").reset_index(drop=True)
    
    return df

def fetch_new_data(symbol, last_timestamp, interval="1m"):
    """
    Fetch new data since last timestamp.
    
    Parameters:
        symbol: Trading pair
        last_timestamp: Last known timestamp (pd.Timestamp or string in 'YYYY-MM-DD HH:MM:SS' format)
        interval: Candle interval
    
    Returns:
        pd.DataFrame with new candles (open_time formatted as string)
    """
    # Ensure last_timestamp is datetime if string
    if isinstance(last_timestamp, str):
        last_timestamp = pd.to_datetime(last_timestamp, format='%Y-%m-%d %H:%M:%S', utc=True)
    
    start_time = int(last_timestamp.timestamp() * 1000)
    candles = get_klines(symbol, interval, start_time=start_time)
    
    if not candles:
        return pd.DataFrame()
    
    df = pd.DataFrame(candles, columns=[
        "open_time", "open", "high", "low", "close", "volume",
        "close_time", "quote_asset_volume", "trades", "taker_base",
        "taker_quote", "ignore"
    ])
    
    df = df.drop(columns=["close_time"])
    df["open_time"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
    
    # Filter to only new data (after last_timestamp)
    df = df[df["open_time"] > last_timestamp]
    
    if df.empty:
        return pd.DataFrame()
    
    # Format open_time as string per instructions
    df["open_time"] = df["open_time"].dt.strftime('%Y-%m-%d %H:%M:%S')
    
    # Convert numeric columns
    numeric_cols = ["open", "high", "low", "close", "volume", "taker_base", 
                     "taker_quote", "quote_asset_volume", "ignore"]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col])
    
    # Sort by open_time
    df = df.sort_values("open_time").reset_index(drop=True)
    
    return df

def validate_price_data(df):
    """
    Validate price DataFrame.
    
    Note: Assumes df has open_time as datetime for validation checks.
    For CSV-loaded data, convert to datetime first.
    """
    if df.empty:
        return False
    
    # open_time is required per instructions
    assert "open_time" in df.columns, "Missing open_time column"
    
    # Convert to datetime if string
    df_temp = df.copy()
    if df_temp["open_time"].dtype == 'object':
        df_temp["open_time"] = pd.to_datetime(df_temp["open_time"], format='%Y-%m-%d %H:%M:%S', utc=True)
    
    # Validation checks
    assert df_temp["open_time"].is_unique, "Duplicate timestamps found"
    assert df_temp["open_time"].is_monotonic_increasing, "Data not sorted by time"
    
    assert (df_temp["high"] >= df_temp["low"]).all(), "Invalid price ranges"
    assert (df_temp["high"] >= df_temp["open"]).all(), "Invalid price ranges"
    assert (df_temp["high"] >= df_temp["close"]).all(), "Invalid price ranges"
    assert (df_temp["low"] <= df_temp["open"]).all(), "Invalid price ranges"
    assert (df_temp["low"] <= df_temp["close"]).all(), "Invalid price ranges"
    assert (df_temp["volume"] >= 0).all(), "Negative volumes found"
    
    return True

def load_or_fetch_price_data(symbol="BTCUSDT", interval="1m", start_str="2023-01-01", data_path="data",
                             max_records=None, end_date=None, time_window=None):
    """
    Load price data from CSV if exists, otherwise fetch from Binance.
    
    Parameters:
        symbol: Trading pair (e.g., "BTCUSDT")
        interval: Candle interval (default: "1m")
        start_str: Start date (default: "2023-01-01")
        data_path: Directory to save/load data
        max_records: Maximum number of candles to fetch (None = no limit)
        end_date: End date as string (format: "YYYY-MM-DD") - stops at this date instead of "now"
        time_window: Time window string (e.g., "7d", "24h") - fetches last N days/hours from start
    
    Returns:
        pd.DataFrame with price data
        - open_time: formatted as 'YYYY-MM-DD HH:MM:SS' string
        - Required columns: open, high, low, close, volume
        - Optional columns: quote_asset_volume, trades, taker_base, taker_quote, ignore
    """
    os.makedirs(data_path, exist_ok=True)
    csv_path = os.path.join(data_path, f"{symbol.lower()}.csv")
    
    # Try to load existing data
    if os.path.exists(csv_path):
        print(f"Loading existing data from {csv_path}...")
        df = pd.read_csv(csv_path)
        
        # Parse open_time if it's a string
        if "open_time" in df.columns:
            if df["open_time"].dtype == 'object':
                df_time = pd.to_datetime(df["open_time"], format='%Y-%m-%d %H:%M:%S', utc=True)
            else:
                df_time = pd.to_datetime(df["open_time"], utc=True)
        else:
            raise ValueError("CSV missing required 'open_time' column")
        
        # Check if we need to update
        if len(df) > 0:
            last_time = df_time.max()
            print(f"Last data point: {last_time}")
            
            # Fetch new data if more than 1 day old
            now_utc = datetime.now(last_time.tzinfo)
            days_since_update = (now_utc - last_time).days
            
            if days_since_update > 1:
                print(f"Data is {days_since_update} days old. Fetching updates...")
                new_data = fetch_new_data(symbol, last_time, interval)
                
                if not new_data.empty:
                    # Parse new_data open_time for comparison
                    new_data_time = pd.to_datetime(new_data["open_time"], format='%Y-%m-%d %H:%M:%S', utc=True)
                    
                    # Combine dataframes
                    df = pd.concat([df, new_data], ignore_index=True)
                    
                    # Convert all open_time to datetime for sorting and deduplication
                    df["open_time"] = pd.to_datetime(df["open_time"], format='%Y-%m-%d %H:%M:%S', utc=True)
                    
                    # Deduplicate by open_time (not date!) - keep last
                    df = df.drop_duplicates(subset=["open_time"], keep="last")
                    
                    # Sort and format back to string
                    df = df.sort_values("open_time").reset_index(drop=True)
                    df["open_time"] = df["open_time"].dt.strftime('%Y-%m-%d %H:%M:%S')
                    
                    # Save updated data
                    df.to_csv(csv_path, index=False)
                    print(f"Updated data saved to {csv_path}. Total rows: {len(df)}")
        
        # Ensure open_time is string format (if it was parsed)
        if "open_time" in df.columns and hasattr(df["open_time"].iloc[0] if len(df) > 0 else None, 'strftime'):
            df["open_time"] = pd.to_datetime(df["open_time"], utc=True).dt.strftime('%Y-%m-%d %H:%M:%S')
        
        return df
    
    # Fetch new data
    print(f"Fetching {symbol} data from Binance API...")
    df = download_full_history(symbol, interval, start_str, 
                               max_records=max_records, end_date=end_date, time_window=time_window)
    
    if df.empty:
        raise ValueError(f"No data fetched for {symbol}. Check symbol name and API connection.")
    
    # Validate data (convert to datetime temporarily for validation)
    df_temp = df.copy()
    df_temp["open_time"] = pd.to_datetime(df_temp["open_time"], format='%Y-%m-%d %H:%M:%S', utc=True)
    
    try:
        validate_price_data(df_temp)
        print("Data validation passed")
    except AssertionError as e:
        print(f"⚠️ Warning: Data validation issue: {e}")
        print("Continuing anyway...")
    
    # Save to CSV (open_time is already formatted as string)
    df.to_csv(csv_path, index=False)
    print(f"Data saved to {csv_path}")
    print(f"Loaded {len(df)} data points")
    print(f"Date range: {df['open_time'].min()} to {df['open_time'].max()}")
    
    return df


def main():
    """
    Command-line interface for data fetcher.
    
    Usage:
        python data_fetcher.py [--symbol SYMBOL] [--interval INTERVAL] [--start-date START_DATE] [--data-path DATA_PATH]
    """
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Fetch cryptocurrency price data from Binance API',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Fetch BTCUSDT 1-minute data from 2023-01-01 (fetches up to now)
  python data_fetcher.py --symbol BTCUSDT --interval 1m --start-date 2023-01-01
  
  # Fetch last 7 days of data (from today backwards)
  python data_fetcher.py --symbol BTCUSDT --interval 1m --start-date 2024-01-01 --time-window 7d
  
  # Fetch data between two specific dates
  python data_fetcher.py --symbol BTCUSDT --interval 1h --start-date 2023-01-01 --end-date 2023-12-31
  
  # Fetch limited records for testing (e.g., 10,000 records)
  python data_fetcher.py --symbol BTCUSDT --interval 1m --start-date 2023-01-01 --max-records 10000
  
  # Fetch hourly data with time window
  python data_fetcher.py --symbol ETHUSDT --interval 1h --start-date 2024-01-01 --time-window 30d
        """
    )
    
    parser.add_argument(
        '--symbol',
        type=str,
        default='BTCUSDT',
        help='Trading pair symbol (default: BTCUSDT)'
    )
    
    parser.add_argument(
        '--interval',
        type=str,
        default='1m',
        choices=['1m', '3m', '5m', '15m', '30m', '1h', '2h', '4h', '6h', '8h', '12h', '1d', '3d', '1w', '1M'],
        help='Candle interval (default: 1m)'
    )
    
    parser.add_argument(
        '--start-date',
        type=str,
        default='2023-01-01',
        help='Start date in YYYY-MM-DD format (default: 2023-01-01)'
    )
    
    parser.add_argument(
        '--data-path',
        type=str,
        default='data',
        help='Directory to save/load data (default: data)'
    )
    
    parser.add_argument(
        '--max-records',
        type=int,
        default=None,
        help='Stop after fetching N records (useful for testing with limited data)'
    )
    
    parser.add_argument(
        '--end-date',
        type=str,
        default=None,
        help='Stop fetching at this date (YYYY-MM-DD format). By default, fetches up to current time.'
    )
    
    parser.add_argument(
        '--time-window',
        type=str,
        default=None,
        help='Fetch last N days/hours from start date (e.g., "7d", "24h", "30d"). '
             'Overrides --end-date if both are specified.'
    )
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("Cryptocurrency Data Fetcher")
    print("=" * 60)
    print(f"Symbol: {args.symbol}")
    print(f"Interval: {args.interval}")
    print(f"Start Date: {args.start_date}")
    if args.end_date:
        print(f"End Date: {args.end_date}")
    if args.time_window:
        print(f"Time Window: {args.time_window}")
    if args.max_records:
        print(f"Max Records: {args.max_records:,}")
    print(f"Data Path: {args.data_path}")
    print("=" * 60)
    print()
    
    try:
        df = load_or_fetch_price_data(
            symbol=args.symbol,
            interval=args.interval,
            start_str=args.start_date,
            data_path=args.data_path,
            max_records=args.max_records,
            end_date=args.end_date,
            time_window=args.time_window
        )
        
        if df.empty:
            print("⚠️ Warning: No data fetched")
            return 1
        
        print()
        print("=" * 60)
        print("Data fetch completed successfully!")
        print("=" * 60)
        print(f"Total records: {len(df)}")
        print(f"Time range: {df['open_time'].min()} to {df['open_time'].max()}")
        print(f"Data saved to: {os.path.join(args.data_path, args.symbol.lower() + '.csv')}")
        print("=" * 60)
        
        return 0
        
    except KeyboardInterrupt:
        print("\n⚠️ Operation cancelled by user")
        return 130
    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
