"""
Producer for fetching cryptocurrency price data from Binance API
and publishing to Kafka topics.
"""

import os
import sys
import time
import argparse
import json
import pandas as pd
from datetime import datetime, timezone
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from quixstreams import Application
from utils.database.db import CryptoDB
from utils.producer_consumer.consumer_utils import state_checker, state_write
from utils.producer_consumer.logger import setup_logger

# Configuration
KAFKA_BROKER = f"{os.environ.get('KAFKA_HOST', 'localhost')}:9092"
SYMBOLS = ["BTCUSDT"]  # Supported cryptocurrencies
INTERVAL = "1m"  # Data interval
BATCH_SIZE = 1000  # Records per batch (reduced from 10000 to avoid Kafka message size errors)
# Use Path for cross-platform compatibility
DATA_PATH_STR = os.getenv("DATA_PATH", "/opt/airflow/custom_persistent_shared/data/prices")
DATA_PATH = Path(DATA_PATH_STR)

# Setup logger
logger = setup_logger("producer")

# Database will be initialized lazily if GCP credentials are available
crypto_db = None


def download_full_history(symbol: str, interval: str = "1m", start_str: str = None) -> pd.DataFrame:
    """
    Download historical OHLCV data with resume support.
    
    Args:
        symbol: Cryptocurrency symbol (e.g., "BTCUSDT")
        interval: Data interval (e.g., "1m")
        start_str: Start date string (e.g., "2023-01-01")
        
    Returns:
        DataFrame with OHLCV data
    """
    import requests
    
    base_url = "https://api.binance.com/api/v3/klines"
    all_data = []
    
    # Determine start time
    if start_str:
        start_time = int(pd.to_datetime(start_str).timestamp() * 1000)
    else:
        # Default to 1 year ago
        start_time = int((datetime.now(timezone.utc).timestamp() - 365 * 24 * 3600) * 1000)
    
    end_time = int(datetime.now(timezone.utc).timestamp() * 1000)
    
    logger.info(f"Downloading {symbol} data from {pd.to_datetime(start_time, unit='ms')} to {pd.to_datetime(end_time, unit='ms')}")
    
    current_time = start_time
    
    while current_time < end_time:
        try:
            params = {
                "symbol": symbol,
                "interval": interval,
                "startTime": current_time,
                "limit": 1000
            }
            
            response = requests.get(base_url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            if not data:
                break
            
            all_data.extend(data)
            
            # Update current_time to next batch
            current_time = data[-1][0] + 1
            
            # Rate limiting (0.25s delay)
            time.sleep(0.25)
            
        except Exception as e:
            logger.error(f"Error fetching data for {symbol}: {e}")
            time.sleep(1)
            continue
    
    if not all_data:
        logger.warning(f"No data fetched for {symbol}")
        return pd.DataFrame()
    
    # Convert to DataFrame
    df = pd.DataFrame(all_data, columns=[
        "open_time", "open", "high", "low", "close", "volume",
        "close_time", "quote_volume", "trades", "taker_buy_base",
        "taker_buy_quote", "ignore"
    ])
    
    # Select required columns
    df = df[["open_time", "open", "high", "low", "close", "volume"]].copy()
    
    # Convert types
    df["open_time"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
    df["open"] = df["open"].astype(float)
    df["high"] = df["high"].astype(float)
    df["low"] = df["low"].astype(float)
    df["close"] = df["close"].astype(float)
    df["volume"] = df["volume"].astype(float)
    
    logger.info(f"Downloaded {len(df)} records for {symbol}")
    return df


def send_df_to_quix(app: Application, symbol: str, df: pd.DataFrame, batch_size: int = BATCH_SIZE):
    """
    Publish DataFrame data to Kafka.
    
    Args:
        app: QuixStreams Application instance
        symbol: Cryptocurrency symbol
        df: DataFrame with OHLCV data
        batch_size: Number of records per batch
    """
    if df.empty:
        return
    
    topic = app.topic(symbol)
    
    # Process in batches
    for i in range(0, len(df), batch_size):
        batch_df = df.iloc[i:i + batch_size]
        
        # Convert to JSON-serializable format
        batch_data = batch_df.to_dict(orient="records")
        
        # Convert datetime objects to strings for JSON serialization
        for record in batch_data:
            if "open_time" in record and pd.notna(record["open_time"]):
                if isinstance(record["open_time"], pd.Timestamp):
                    record["open_time"] = record["open_time"].isoformat()
                elif hasattr(record["open_time"], "isoformat"):
                    record["open_time"] = record["open_time"].isoformat()
        
        # Serialize to JSON bytes for Kafka
        batch_data_json = json.dumps(batch_data).encode('utf-8')
        
        # Create key
        timestamp = int(datetime.now(timezone.utc).timestamp() * 1000)
        key = f"{symbol}_batch_{timestamp}_{i}"
        
        try:
            # Publish to Kafka using QuixStreams
            # QuixStreams API: Use get_producer() with context manager
            # This is the standard way to publish messages in QuixStreams
            # Serialize data to JSON bytes before producing
            with app.get_producer() as producer:
                producer.produce(
                    topic=topic.name,
                    key=key.encode('utf-8') if isinstance(key, str) else key,
                    value=batch_data_json
                )
            
            logger.info(f"Published batch {i//batch_size + 1} ({len(batch_df)} records) to topic {symbol}")
            
        except AttributeError as e:
            # Fallback: Try topic.get_producer() if app.get_producer() doesn't exist
            logger.warning(f"app.get_producer() not available, trying topic.get_producer(): {e}")
            try:
                with topic.get_producer() as producer:
                    producer.produce(
                        key=key.encode('utf-8') if isinstance(key, str) else key,
                        value=batch_data_json
                    )
                logger.info(f"Published batch {i//batch_size + 1} ({len(batch_df)} records) to topic {symbol} (using topic.get_producer())")
            except AttributeError as e2:
                # Another fallback: Try topic.publish() if it exists
                logger.warning(f"topic.get_producer() not available, trying topic.publish(): {e2}")
                try:
                    topic.publish(
                        key=key.encode('utf-8') if isinstance(key, str) else key,
                        value=batch_data_json
                    )
                    logger.info(f"Published batch {i//batch_size + 1} ({len(batch_df)} records) to topic {symbol} (using topic.publish())")
                except Exception as e3:
                    logger.error(f"All producer methods failed. Last error: {e3}")
                    raise
            except Exception as e2:
                logger.error(f"Error with topic.get_producer(): {e2}")
                raise
        except Exception as e:
            logger.error(f"Error publishing batch to {symbol}: {e}", exc_info=True)
            raise  # Re-raise to allow caller to handle


def main():
    """Main producer loop."""
    parser = argparse.ArgumentParser(description="Kafka Producer for Cryptocurrency Data")
    parser.add_argument("--symbol", type=str, default="BTCUSDT", help="Cryptocurrency symbol")
    args = parser.parse_args()
    
    symbol = args.symbol.upper()
    
    logger.info(f"Starting producer for {symbol}")
    logger.info(f"Kafka broker: {KAFKA_BROKER}")
    
    # Initialize QuixStreams application with retry logic
    max_retries = 5
    retry_delay = 5
    app = None
    
    for attempt in range(max_retries):
        try:
            app = Application(
                broker_address=KAFKA_BROKER,
                consumer_group="producer-group"
            )
            logger.info(f"Connected to Kafka broker at {KAFKA_BROKER}")
            break
        except Exception as e:
            if attempt < max_retries - 1:
                logger.warning(f"Failed to connect to Kafka broker (attempt {attempt + 1}/{max_retries}): {e}")
                logger.info(f"Retrying in {retry_delay} seconds...")
                time.sleep(retry_delay)
            else:
                logger.error(f"Failed to connect to Kafka broker after {max_retries} attempts: {e}")
                sys.exit(1)
    
    if app is None:
        logger.error("Failed to initialize QuixStreams application")
        sys.exit(1)
    
    # Create topic (will be created automatically if auto.create.topics.enable is true)
    topic = app.topic(symbol)
    
    # Initialize database - REQUIRED (not optional)
    global crypto_db
    if crypto_db is None:
        try:
            crypto_db = CryptoDB(coins=SYMBOLS, data_path=str(DATA_PATH))
            logger.info("Database connection initialized successfully")
        except Exception as e:
            logger.error(f"CRITICAL: Failed to initialize GCP Firestore database: {e}")
            logger.error("GCP credentials are REQUIRED. Please set one of:")
            logger.error("  - GCP_CREDENTIALS_PATH or GOOGLE_APPLICATION_CREDENTIALS (path to service account key)")
            logger.error("  - GCP_PROJECT_ID (your GCP project ID)")
            logger.error("Producer cannot start without database connection.")
            sys.exit(1)
    
    # State management
    state_write("ALL", "producer", "main", "running")
    
    # Load existing data from CSV
    csv_path = str(DATA_PATH / f"{symbol}.csv")
    last_time = None
    
    if Path(csv_path).exists():
        try:
            existing_df = pd.read_csv(csv_path)
            if not existing_df.empty and "open_time" in existing_df.columns:
                existing_df["open_time"] = pd.to_datetime(existing_df["open_time"], utc=True)
                last_time = existing_df["open_time"].max()
                logger.info(f"Found existing data, last time: {last_time}")
        except Exception as e:
            logger.warning(f"Error reading existing CSV: {e}")
    
    # Main loop
    while True:
        try:
            # Check state
            state = state_checker("ALL", "producer", "main", timeout=5)
            
            if state == "delete":
                logger.info("Received delete command, shutting down...")
                state_write("ALL", "producer", "main", "deleted")
                break
            
            if state == "pause":
                logger.info("Producer paused, waiting...")
                time.sleep(10)
                continue
            
            if state != "running" and state != "start":
                logger.warning(f"Unknown state: {state}, waiting...")
                time.sleep(10)
                continue
            
            # Set state to running
            if state == "start":
                state_write("ALL", "producer", "main", "running")
            
            # Fetch new data
            try:
                # Determine start time for fetching
                if last_time:
                    start_str = (last_time + pd.Timedelta(minutes=1)).strftime("%Y-%m-%d %H:%M:%S")
                else:
                    # Fetch last 24 hours
                    start_str = (datetime.now(timezone.utc) - pd.Timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")
                
                # Download new data
                new_df = download_full_history(symbol, INTERVAL, start_str)
                
                if new_df.empty:
                    logger.info("No new data available, waiting...")
                    time.sleep(60)  # Wait 1 minute before next check
                    continue
                
                # Filter out data we already have
                if last_time:
                    new_df = new_df[new_df["open_time"] > last_time]
                
                if new_df.empty:
                    logger.info("No new data after filtering, waiting...")
                    time.sleep(60)
                    continue
                
                # Insert into database - REQUIRED
                try:
                    crypto_db.bulk_insert_df(symbol.lower(), new_df)
                    logger.info(f"Inserted {len(new_df)} records into GCP Firestore database")
                except Exception as e:
                    logger.error(f"CRITICAL: Error inserting into database: {e}")
                    logger.error("Database update failed. Stopping producer.")
                    raise  # Re-raise to stop the producer
                
                # Append to CSV
                try:
                    # Ensure directory exists
                    csv_path_obj = Path(csv_path)
                    csv_path_obj.parent.mkdir(parents=True, exist_ok=True)
                    
                    if csv_path_obj.exists():
                        new_df.to_csv(csv_path, mode='a', header=False, index=False)
                    else:
                        new_df.to_csv(csv_path, mode='w', header=True, index=False)
                    
                    # Set permissions (Unix only, will fail silently on Windows)
                    try:
                        os.chmod(csv_path, 0o777)
                    except (OSError, AttributeError):
                        pass
                    
                    logger.info(f"Appended {len(new_df)} records to CSV")
                except Exception as e:
                    logger.error(f"Error writing to CSV: {e}")
                
                # Publish to Kafka
                send_df_to_quix(app, symbol, new_df)
                
                # Update last_time
                last_time = new_df["open_time"].max()
                
                # Align to 1-minute intervals
                current_time = datetime.now(timezone.utc)
                next_minute = (current_time.replace(second=0, microsecond=0) + pd.Timedelta(minutes=1))
                sleep_time = (next_minute - current_time).total_seconds()
                
                if sleep_time > 0:
                    time.sleep(sleep_time)
                
            except Exception as e:
                logger.error(f"Error in main loop: {e}")
                time.sleep(10)
                continue
        
        except KeyboardInterrupt:
            logger.info("Received interrupt signal, shutting down...")
            state_write("ALL", "producer", "main", "deleted")
            break
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            time.sleep(10)
            continue
    
    logger.info("Producer stopped")


if __name__ == "__main__":
    main()

