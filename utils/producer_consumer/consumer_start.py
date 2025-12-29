"""
Consumer start script that initializes consumers and producer.
"""

import os
import sys
import time
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from utils.producer_consumer.consumer_utils import (
    state_write, state_checker, delete_all_states, get_state_data
)
from utils.producer_consumer.logger import setup_logger
from utils.artifact_control.s3_manager import S3Manager

# Configuration
JOBS_DIR = os.getenv("JOBS_DIR", "/opt/airflow/custom_persistent_shared/jobs")
DATA_PATH = os.getenv("DATA_PATH", "/opt/airflow/custom_persistent_shared/data")
PRICES_PATH = os.path.join(DATA_PATH, "prices")
PREDICTIONS_PATH = os.path.join(DATA_PATH, "predictions")

# Supported configurations
SYMBOLS = ["BTCUSDT"]
MODELS = ["lightgbm", "tst"]
VERSIONS = ["v1", "v2", "v3"]

# Setup logger
logger = setup_logger("consumer_start")


def create_job_file(crypto: str, model: str, version: str, process_type: str = "consumer"):
    """
    Create a job file for launching a process.
    
    Args:
        crypto: Cryptocurrency symbol
        model: Model name
        version: Model version
        process_type: "producer" or "consumer"
    """
    # Ensure jobs directory exists
    Path(JOBS_DIR).mkdir(parents=True, exist_ok=True)
    
    # Generate filename
    if process_type == "producer":
        filename = "ALL_producer_main.sh"
    else:
        filename = f"{crypto}_{model}_{version}.sh"
    
    filepath = os.path.join(JOBS_DIR, filename)
    
    # Generate command
    if process_type == "producer":
        command = f"""#!/bin/bash
export PYTHONPATH=..:$PYTHONPATH
python -m utils.producer_consumer.producer --symbol {crypto}
"""
    else:
        command = f"""#!/bin/bash
export PYTHONPATH=..:$PYTHONPATH
python -m utils.producer_consumer.consumer --crypto {crypto} --model {model} --version {version}
"""
    
    # Write job file
    with open(filepath, 'w') as f:
        f.write(command)
    
    # Set permissions
    try:
        os.chmod(filepath, 0o777)
    except Exception:
        pass  # Ignore permission errors on Windows
    
    logger.info(f"Created job file: {filepath}")


def download_datasets_from_s3():
    """Download datasets and predictions from S3 if available."""
    try:
        s3_manager = S3Manager()
        logger.info("Downloading datasets from S3...")
        
        # Download price data
        for symbol in SYMBOLS:
            try:
                s3_manager.download_price_data(symbol, os.path.join(PRICES_PATH, f"{symbol}.csv"))
                logger.info(f"Downloaded price data for {symbol}")
            except Exception as e:
                logger.warning(f"Could not download price data for {symbol}: {e}")
        
        # Download predictions
        for symbol in SYMBOLS:
            for model in MODELS:
                for version in VERSIONS:
                    try:
                        key = f"predictions/{symbol}/{model}/{version}.parquet"
                        local_path = os.path.join(PREDICTIONS_PATH, symbol, model, f"{version}.csv")
                        s3_manager.download_df(local_path, key)
                        logger.info(f"Downloaded predictions for {symbol} {model} {version}")
                    except Exception as e:
                        logger.debug(f"Could not download predictions for {symbol} {model} {version}: {e}")
        
        logger.info("Dataset download completed")
    
    except Exception as e:
        logger.warning(f"Error downloading datasets from S3: {e}")


def wait_for_producer(timeout: int = 300):
    """
    Wait for producer to be running.
    
    Args:
        timeout: Maximum time to wait (seconds)
        
    Returns:
        True if producer is running, False otherwise
    """
    logger.info("Waiting for producer to start...")
    start_time = time.time()
    
    while time.time() - start_time < timeout:
        state = state_checker("ALL", "producer", "main", timeout=5)
        
        if state == "running":
            logger.info("Producer is running")
            return True
        
        if state == "error":
            logger.error("Producer encountered an error")
            return False
        
        time.sleep(5)
    
    logger.error("Timeout waiting for producer to start")
    return False


def wait_for_consumer(crypto: str, model: str, version: str, timeout: int = 300):
    """
    Wait for consumer to be running.
    
    Args:
        crypto: Cryptocurrency symbol
        model: Model name
        version: Model version
        timeout: Maximum time to wait (seconds)
        
    Returns:
        True if consumer is running, False otherwise
    """
    logger.info(f"Waiting for consumer {crypto} {model} {version} to start...")
    start_time = time.time()
    
    while time.time() - start_time < timeout:
        state = state_checker(crypto, model, version, timeout=5)
        
        if state == "running":
            logger.info(f"Consumer {crypto} {model} {version} is running")
            return True
        
        if state == "error":
            logger.error(f"Consumer {crypto} {model} {version} encountered an error")
            return False
        
        if state == "deleted":
            logger.warning(f"Consumer {crypto} {model} {version} was deleted")
            return False
        
        time.sleep(5)
    
    logger.error(f"Timeout waiting for consumer {crypto} {model} {version} to start")
    return False


def main():
    """Main consumer start process."""
    logger.info("Starting consumer initialization process")
    
    # Clean up old state files
    logger.info("Cleaning up old state files...")
    delete_all_states()
    
    # Download datasets from S3
    try:
        download_datasets_from_s3()
    except Exception as e:
        logger.warning(f"Error downloading datasets: {e}")
    
    # Create producer job file
    logger.info("Creating producer job file...")
    create_job_file(SYMBOLS[0], None, None, process_type="producer")
    
    # Wait for producer to start
    if not wait_for_producer():
        logger.error("Failed to start producer, aborting")
        return
    
    # Create consumer job files for all available model versions
    logger.info("Creating consumer job files...")
    
    for symbol in SYMBOLS:
        for model in MODELS:
            for version in VERSIONS:
                # Download available predictions from S3 if not present locally
                pred_path = os.path.join(PREDICTIONS_PATH, symbol, model, f"{version}.csv")
                if not os.path.exists(pred_path):
                    try:
                        s3_manager = S3Manager()
                        key = f"predictions/{symbol}/{model}/{version}.parquet"
                        s3_manager.download_df(pred_path, key)
                        logger.info(f"Downloaded predictions for {symbol} {model} {version} from S3")
                    except Exception as e:
                        logger.debug(f"Could not download predictions for {symbol} {model} {version}: {e}")
                
                # Create consumer job file
                create_job_file(symbol, model, version, process_type="consumer")
                
                # Set state to "start" to begin processing
                state_write(symbol, model, version, "start")
                
                logger.info(f"Created consumer job for {symbol} {model} {version}")
    
    # Wait for all consumers to be running
    logger.info("Waiting for all consumers to start...")
    
    all_started = True
    for symbol in SYMBOLS:
        for model in MODELS:
            for version in VERSIONS:
                if not wait_for_consumer(symbol, model, version):
                    all_started = False
    
    if all_started:
        logger.info("All consumers started successfully")
    else:
        logger.warning("Some consumers failed to start")
    
    logger.info("Consumer initialization process completed")


if __name__ == "__main__":
    main()







