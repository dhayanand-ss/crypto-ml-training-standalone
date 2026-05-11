"""
Consumer for processing cryptocurrency price data from Kafka topics
and generating ML predictions.
"""

import os
import sys
import time
import argparse
import pandas as pd
import numpy as np
import requests
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Any
from threading import Thread

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from quixstreams import Application
from utils.database.db import CryptoDB
from utils.producer_consumer.consumer_utils import state_checker, state_write, get_state_data
from utils.producer_consumer.logger import setup_logger

# Configuration
kafka_host = os.environ.get('KAFKA_HOST', 'localhost')
if ":" in kafka_host:
    KAFKA_BROKER = kafka_host
else:
    KAFKA_BROKER = f"{kafka_host}:9092"
seq_len = 60  # Sequence length for time series models (increased to 60 for SMA_50)
url = os.getenv("FASTAPI_URL", "http://127.0.0.1:8000/predict")
DATA_PATH = os.getenv("DATA_PATH", "/opt/airflow/custom_persistent_shared/data")
PREDICTIONS_PATH = os.path.join(DATA_PATH, "predictions")
PRICES_PATH = os.path.join(DATA_PATH, "prices")

# Setup logger
logger = setup_logger("consumer")

# Initialize database
crypto_db = CryptoDB(coins=["BTCUSDT"], data_path=PRICES_PATH)


def get_predictions(features: List[List[float]], model_name: str, version: str, max_retries: int = 3) -> List[List[float]]:
    """
    Call FastAPI service for batch predictions.
    
    Args:
        features: Feature matrix (list of feature vectors)
        model_name: Model name (e.g., "lightgbm", "tst")
        version: Model version (e.g., "v1", "v2", "v3")
        max_retries: Maximum number of retries
        
    Returns:
        List of predictions
    """
    
    # Batch requests (max 5000 per request)
    batch_size = 5000
    all_predictions = []
    
    for i in range(0, len(features), batch_size):
        batch_features = features[i:i + batch_size]
        
        attempt = 0
        while attempt < max_retries:
            try:
                response = requests.post(
                    url,
                    json={"features": batch_features},
                    params={"model_name": model_name, "version": str(version)},
                    timeout=20
                )
                response.raise_for_status()
                preds = response.json()["predictions"]
                all_predictions.extend(preds)
                break
            except Exception as e:
                attempt += 1
                if hasattr(e, 'response') and e.response is not None:
                    try:
                        error_detail = e.response.json()
                        logger.error(f"Error calling FastAPI (attempt {attempt}/{max_retries}) [Status {e.response.status_code}]: {error_detail}")
                    except:
                        logger.error(f"Error calling FastAPI (attempt {attempt}/{max_retries}) [Status {e.response.status_code}]: {e.response.text}")
                else:
                    logger.error(f"Error calling FastAPI (attempt {attempt}/{max_retries}): {e}")
                
                if attempt == max_retries:
                    # Final fallback: return neutral probabilities if batch fails
                    logger.warning(f"Returning default neutral predictions for batch {i//batch_size + 1}")
                    all_predictions.extend([[0.0, 1.0, 0.0]] * len(batch_features))
                else:
                    time.sleep(1)
    
    return all_predictions


def check_model_availability(model_name: str, version: str) -> bool:
    """
    Check if model is available in FastAPI service.
    
    Args:
        model_name: Model name
        version: Model version
        
    Returns:
        True if model is available
    """
    check_url = url.replace("/predict", "/is_model_available")
    logger.info(f"Checking model availability on {check_url} for {model_name} {version}")
    try:
        response = requests.post(
            check_url,
            json={"model_name": model_name, "version": str(version)},
            timeout=10
        )
        response.raise_for_status()
        available = response.json().get("available", False)
        logger.info(f"Model availability result: {available}")
        return available
    except Exception as e:
        logger.error(f"Error checking model availability on {check_url}: {e} | type: {type(e)}")
        # Log health check as well
        try:
            health_url = url.replace("/predict", "/health")
            health = requests.get(health_url, timeout=5).json()
            logger.info(f"FastAPI health: {health}")
        except:
            pass
        return False


def preprocess_data(df: pd.DataFrame, seq_len: int = 60) -> np.ndarray:
    """
    Preprocess data for ML models exactly as done during training.
    
    Args:
        df: DataFrame with OHLCV data
        seq_len: Sequence length for time series models
        
    Returns:
        Feature array of shape [None, 35] for LightGBM validation
    """
    try:
        from trainer.lightgbm_trainer import LightGBMTrainer
        import warnings
        
        # The trainer expects certain columns to exist, especially sentiment
        # In a real-time stream without a sentiment producer, we inject neutral defaults
        df = df.copy()
        
        # Ensure we have the base required columns
        for col in ["open", "high", "low", "close", "volume"]:
            if col not in df.columns:
                return np.array([])
                
        # The LightGBM trainer requires sentiment data to merge on 'date'
        if 'open_time' in df.columns:
            dates = pd.to_datetime(df['open_time']).dt.strftime('%Y-%m-%d').unique()
        else:
            dates = ['2023-01-01']
            
        sentiment_df = pd.DataFrame({
            'date': dates,
            'sentiment_mean': [0.0]*len(dates),
            'sentiment_std': [0.0]*len(dates),
            'news_count': [0]*len(dates),
            'sentiment_confidence': [0.0]*len(dates),
            'negative_sentiment': [0.0]*len(dates),
            'neutral_sentiment': [1.0]*len(dates),
            'positive_sentiment': [0.0]*len(dates)
        })
        
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            trainer = LightGBMTrainer()
            X, y, cols = trainer.prepare_features(df, sentiment_df)
            
        if len(X) == 0:
            return np.array([])
            
        # Return only the last feature vector (representing the current timestep)
        return np.array([X[-1]])
    except Exception as e:
        logger.error(f"Error in preprocess_data: {e}")
        return np.array([])


def historical_reconciliation(crypto: str, model: str, version: str):
    """
    Handle missing predictions on startup by backfilling from historical data.
    
    Args:
        crypto: Cryptocurrency symbol
        model: Model name
        version: Model version
    """
    logger.info(f"Starting historical reconciliation for {crypto} {model} {version}")
    
    # Load existing predictions from CSV
    pred_csv_path = os.path.join(PREDICTIONS_PATH, crypto, model, f"{version}.csv")
    existing_predictions = pd.DataFrame()
    
    if os.path.exists(pred_csv_path):
        try:
            existing_predictions = pd.read_csv(pred_csv_path)
            if not existing_predictions.empty and "open_time" in existing_predictions.columns:
                existing_predictions["open_time"] = pd.to_datetime(existing_predictions["open_time"], utc=True)
                logger.info(f"Loaded {len(existing_predictions)} existing predictions from CSV")
        except Exception as e:
            logger.warning(f"Error reading existing predictions CSV: {e}")
    
    # Query missing predictions from database
    missing_times = crypto_db.get_missing_prediction_times(crypto.lower(), model, version)
    
    if not missing_times:
        logger.info("No missing predictions found")
        return
    
    logger.info(f"Found {len(missing_times)} missing predictions")
    
    # Load price data
    # Use BTCUSDT.csv if BTC.csv not found (convention mismatch fix)
    price_csv_path = os.path.join(PRICES_PATH, f"{crypto}.csv")
    if not os.path.exists(price_csv_path):
        price_csv_path = os.path.join(PRICES_PATH, f"{crypto}USDT.csv")
    
    if not os.path.exists(price_csv_path):
        logger.warning(f"Price data CSV not found: {price_csv_path}")
        return
    
    try:
        price_df = pd.read_csv(price_csv_path)
        price_df["open_time"] = pd.to_datetime(price_df["open_time"], utc=True)
    except Exception as e:
        logger.error(f"Error reading price data CSV: {e}")
        return
    
    # Filter price data for missing time periods
    missing_df = price_df[price_df["open_time"].isin(missing_times)].copy()
    missing_df = missing_df.sort_values("open_time")
    
    if missing_df.empty:
        logger.info("No price data found for missing time periods")
        return
    
    logger.info(f"Processing {len(missing_df)} missing predictions")
    
    # Process in batches
    batch_size = 1000
    all_predictions = []
    all_times = []
    
    for i in range(0, len(missing_df), batch_size):
        batch_df = missing_df.iloc[i:i + batch_size]
        
        # Create rolling windows
        windows = []
        window_times = []
        
        for j in range(seq_len - 1, len(batch_df)):
            window_df = batch_df.iloc[j - seq_len + 1:j + 1]
            features = preprocess_data(window_df, seq_len)
            windows.append(features[0].tolist())
            window_times.append(batch_df.iloc[j]["open_time"])
        
        if not windows:
            continue
        
        # Get predictions
        try:
            predictions = get_predictions(windows, model, version)
            all_predictions.extend(predictions)
            all_times.extend(window_times)
        except Exception as e:
            logger.error(f"Error getting predictions for batch: {e}")
            continue
    
    if not all_predictions:
        logger.warning("No predictions generated during historical reconciliation")
        return
    
    # Upsert to database
    try:
        original_df = missing_df[["open_time", "open", "high", "low", "close", "volume"]].copy()
        crypto_db.upsert_predictions(
            crypto.lower(),
            model,
            version,
            all_times,
            all_predictions,
            original_df
        )
        logger.info(f"Upserted {len(all_predictions)} predictions to database")
    except Exception as e:
        logger.error(f"Error upserting predictions to database: {e}")
    
    # Append to CSV
    try:
        pred_df = pd.DataFrame({
            "open_time": all_times,
            "pred": [str(p) for p in all_predictions]
        })
        
        if os.path.exists(pred_csv_path):
            pred_df.to_csv(pred_csv_path, mode='a', header=False, index=False)
        else:
            os.makedirs(os.path.dirname(pred_csv_path), exist_ok=True)
            pred_df.to_csv(pred_csv_path, mode='w', header=True, index=False)
        
        # Set permissions
        try:
            os.chmod(pred_csv_path, 0o777)
            os.chmod(os.path.dirname(pred_csv_path), 0o777)
        except Exception:
            pass
        
        logger.info(f"Appended {len(all_predictions)} predictions to CSV")
    except Exception as e:
        logger.error(f"Error writing predictions to CSV: {e}")
    
    logger.info("Historical reconciliation completed")


def build_pipeline(crypto: str, model: str, version: str):
    """
    Build and run the QuixStreams processing pipeline.
    
    Args:
        crypto: Cryptocurrency symbol
        model: Model name
        version: Model version
    """
    logger.info(f"Building pipeline for {crypto} {model} {version}")
    
    # Initialize QuixStreams application with retry logic
    max_retries = 5
    retry_delay = 5
    app = None
    
    for attempt in range(max_retries):
        try:
            app = Application(
                broker_address=KAFKA_BROKER,
                consumer_group=f"{model}-{version}-consumer",
                auto_offset_reset="earliest"
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
                state_write(crypto, model, version, "error", str(e))
                return
    
    if app is None:
        logger.error("Failed to initialize QuixStreams application")
        state_write(crypto, model, version, "error", "Failed to initialize application")
        return
    
    # Subscribe to topic
    topic_name = crypto if crypto.endswith("USDT") else f"{crypto}USDT"
    logger.info(f"Subscribing to topic: {topic_name}")
    topic = app.topic(topic_name)
    
    # State management
    state_write(crypto, model, version, "wait")
    
    # Wait for start command
    logger.info("Waiting for start command...")
    while True:
        state = state_checker(crypto, model, version, timeout=5)
        if state in ["start", "running"]:
            logger.info(f"Transitioning from {state} to running")
            break
        if state == "delete":
            logger.info("Received delete command before start")
            state_write(crypto, model, version, "deleted")
            return
        time.sleep(5)
    
    # Set state to running
    logger.info("Setting state to running...")
    state_write(crypto, model, version, "running")
    logger.info("State set to running. Checking model availability...")
    
    # Check model availability
    if not check_model_availability(model, version):
        logger.error(f"Model {model} {version} is not available in FastAPI service")
        state_write(crypto, model, version, "error", "Model not available")
        return
    
    # Historical reconciliation
    logger.info("Starting historical reconciliation phase...")
    try:
        historical_reconciliation(crypto, model, version)
    except Exception as e:
        logger.error(f"Error during historical reconciliation: {e}")
    
    logger.info("Historical reconciliation complete. Initializing pipeline...")
    
    # Maintain rolling window
    rolling_window = []
    last_processed_time = None
    
    # State monitor thread
    def state_monitor():
        while True:
            state = state_checker(crypto, model, version, timeout=5)
            if state == "delete":
                logger.info("Received delete command, shutting down...")
                state_write(crypto, model, version, "deleted")
                os._exit(0)
            elif state == "pause":
                logger.info("Consumer paused")
                state_write(crypto, model, version, "paused")
            time.sleep(5)
    
    monitor_thread = Thread(target=state_monitor, daemon=True)
    monitor_thread.start()
    
    # Message processing callback
    # QuixStreams passes (value, context) to the processing function
    def maybe_process(value, context=None):
        nonlocal last_processed_time, rolling_window
        
        try:
            # Check state
            state = state_checker(crypto, model, version, timeout=1)
            
            if state in ["wait", "pause", "paused", "delete"]:
                return value
            
            if state != "running":
                return value
            
            # Get message data
            # QuixStreams automatically deserializes JSON messages
            batch_data = value
            
            if not batch_data:
                return value
            
            # Convert to DataFrame
            if isinstance(batch_data, list):
                df = pd.DataFrame(batch_data)
            else:
                # Single record
                df = pd.DataFrame([batch_data])
            
            if "open_time" not in df.columns:
                return value
            
            df["open_time"] = pd.to_datetime(df["open_time"], utc=True)
            df = df.sort_values("open_time")
            
            # Filter duplicates
            if last_processed_time:
                df = df[df["open_time"] > last_processed_time]
            
            if df.empty:
                return value
            
            # Update rolling window
            rolling_window.extend(df.to_dict(orient="records"))
            
            # Keep only last seq_len rows
            if len(rolling_window) > seq_len:
                rolling_window = rolling_window[-seq_len:]
            
            if len(rolling_window) < seq_len:
                return value
            
            # Convert to DataFrame
            window_df = pd.DataFrame(rolling_window[-seq_len:])
            window_df["open_time"] = pd.to_datetime(window_df["open_time"], utc=True)
            
            # Preprocess
            features = preprocess_data(window_df, seq_len)
            
            if len(features) == 0:
                return value
            
            # Get prediction for last row
            last_time = window_df.iloc[-1]["open_time"]
            # Ensure feature_vector is a flat python list of floats
            if len(features.shape) > 1:
                feature_vector = [float(x) for x in features[-1].flatten()]
            else:
                feature_vector = [float(x) for x in features.flatten()]
            
            # Get prediction
            try:
                predictions = get_predictions([feature_vector], model, version)
                if not predictions:
                    return value
                
                prediction = predictions[0]
                
                # Upsert to database
                original_df = window_df[["open_time", "open", "high", "low", "close", "volume"]].iloc[-1:].copy()
                crypto_db.upsert_predictions(
                    crypto.lower(),
                    model,
                    version,
                    [last_time],
                    [prediction],
                    original_df
                )
                
                # Append to CSV
                pred_csv_path = os.path.join(PREDICTIONS_PATH, crypto, model, f"{version}.csv")
                pred_df = pd.DataFrame({
                    "open_time": [last_time],
                    "pred": [str(prediction)]
                })
                
                if os.path.exists(pred_csv_path):
                    pred_df.to_csv(pred_csv_path, mode='a', header=False, index=False)
                else:
                    os.makedirs(os.path.dirname(pred_csv_path), exist_ok=True)
                    pred_df.to_csv(pred_csv_path, mode='w', header=True, index=False)
                
                # Update last processed time
                last_processed_time = last_time
                
                logger.info(f"Processed prediction for {last_time}")
                
            except Exception as e:
                logger.error(f"Error processing prediction: {e}")
            
            return value
        
        except Exception as e:
            logger.error(f"Error in message processing: {e}")
            return value
    
    # Build pipeline using QuixStreams
    logger.info("Starting consumer pipeline...")
    try:
        # Create streaming dataframe from topic
        # QuixStreams API: app.dataframe(topic) creates a StreamingDataFrame
        sdf = app.dataframe(topic)
        
        # Apply processing function to each message
        # The function receives (value, context) where value is the deserialized message
        sdf = sdf.apply(maybe_process)
        
        # Run the application (this blocks and processes messages)
        # QuixStreams handles consumer group management, offset commits, etc.
        app.run(sdf)
    
    except KeyboardInterrupt:
        logger.info("Consumer interrupted, shutting down...")
        state_write(crypto, model, version, "deleted")
    except Exception as e:
        logger.error(f"Error running pipeline: {e}", exc_info=True)
        state_write(crypto, model, version, "error", str(e))
        raise


def main():
    """Main consumer entry point."""
    parser = argparse.ArgumentParser(description="Kafka Consumer for ML Predictions")
    parser.add_argument("--crypto", type=str, required=True, help="Cryptocurrency symbol")
    parser.add_argument("--model", type=str, required=True, help="Model name")
    parser.add_argument("--version", type=str, required=True, help="Model version")
    args = parser.parse_args()
    
    crypto = args.crypto.upper()
    model = args.model.lower()
    version = args.version.lower()
    
    logger.info(f"Starting consumer for {crypto} {model} {version}")
    logger.info(f"Kafka broker: {KAFKA_BROKER}")
    logger.info(f"FastAPI URL: {url}")
    
    try:
        build_pipeline(crypto, model, version)
    except KeyboardInterrupt:
        logger.info("Received interrupt signal, shutting down...")
        state_write(crypto, model, version, "deleted")
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        state_write(crypto, model, version, "error", str(e))
        raise


if __name__ == "__main__":
    main()

