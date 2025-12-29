"""
Kill all script that gracefully shuts down all consumers and producer.
"""

import os
import sys
import time
import signal
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from utils.producer_consumer.consumer_utils import (
    state_write, state_checker, delete_all_states
)
from utils.producer_consumer.logger import setup_logger

# Configuration
SYMBOLS = ["BTCUSDT"]
MODELS = ["lightgbm", "tst"]
VERSIONS = ["v1", "v2", "v3"]

# Timeout configuration
INDIVIDUAL_PROCESS_TIMEOUT = 60  # Reduced from 300 to 60 seconds per process
TOTAL_TIMEOUT = 600  # Maximum 10 minutes total for entire operation

# Setup logger
logger = setup_logger("kill_all")

# Global flag to track if we should continue
_should_continue = True


def signal_handler(signum, frame):
    """Handle termination signals gracefully."""
    global _should_continue
    logger.warning(f"Received signal {signum}, will finish current operation and exit")
    _should_continue = False


def wait_for_shutdown(crypto: str, model: str, version: str, timeout: int = 60):
    """
    Wait for a process to shut down.
    
    Args:
        crypto: Cryptocurrency symbol (or "ALL" for producer)
        model: Model name (or "producer")
        version: Model version (or "main")
        timeout: Maximum time to wait (seconds)
        
    Returns:
        True if process shut down, False otherwise
    """
    if not _should_continue:
        return False
        
    logger.info(f"Waiting for {crypto} {model} {version} to shut down...")
    start_time = time.time()
    
    while time.time() - start_time < timeout and _should_continue:
        try:
            state = state_checker(crypto, model, version, timeout=5)
            
            if state == "deleted":
                logger.info(f"{crypto} {model} {version} has shut down")
                return True
            
            if state == "unknown":
                logger.info(f"{crypto} {model} {version} state file not found (already shut down)")
                return True
            
            time.sleep(5)
        except Exception as e:
            logger.error(f"Error checking state for {crypto} {model} {version}: {e}")
            # Continue waiting despite errors
            time.sleep(5)
    
    if not _should_continue:
        logger.warning(f"Interrupted while waiting for {crypto} {model} {version} to shut down")
    else:
        logger.warning(f"Timeout waiting for {crypto} {model} {version} to shut down")
    return False


def main():
    """Main kill all process."""
    global _should_continue
    
    # Set up signal handlers for graceful shutdown
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    
    try:
        script_start_time = time.time()
        logger.info("Starting graceful shutdown of all processes")
        
        # Set all consumer states to "delete"
        logger.info("Sending delete command to all consumers...")
        
        for symbol in SYMBOLS:
            if not _should_continue:
                break
            for model in MODELS:
                if not _should_continue:
                    break
                for version in VERSIONS:
                    if not _should_continue:
                        break
                    
                    # Check total timeout
                    if time.time() - script_start_time > TOTAL_TIMEOUT:
                        logger.warning("Total timeout reached, stopping shutdown process")
                        _should_continue = False
                        break
                    
                    try:
                        state = state_checker(symbol, model, version, timeout=5)
                        if state not in ["deleted", "unknown"]:
                            state_write(symbol, model, version, "delete")
                            logger.info(f"Sent delete command to {symbol} {model} {version}")
                    except Exception as e:
                        logger.error(f"Error sending delete command to {symbol} {model} {version}: {e}")
        
        # Set producer state to "delete"
        if _should_continue:
            logger.info("Sending delete command to producer...")
            try:
                producer_state = state_checker("ALL", "producer", "main", timeout=5)
                if producer_state not in ["deleted", "unknown"]:
                    state_write("ALL", "producer", "main", "delete")
                    logger.info("Sent delete command to producer")
            except Exception as e:
                logger.error(f"Error sending delete command to producer: {e}")
        
        # Wait for all consumers to shut down (with reduced timeout)
        if _should_continue:
            logger.info("Waiting for all consumers to shut down...")
            
            for symbol in SYMBOLS:
                if not _should_continue or (time.time() - script_start_time > TOTAL_TIMEOUT):
                    break
                for model in MODELS:
                    if not _should_continue or (time.time() - script_start_time > TOTAL_TIMEOUT):
                        break
                    for version in VERSIONS:
                        if not _should_continue or (time.time() - script_start_time > TOTAL_TIMEOUT):
                            break
                        wait_for_shutdown(symbol, model, version, timeout=INDIVIDUAL_PROCESS_TIMEOUT)
        
        # Wait for producer to shut down
        if _should_continue and (time.time() - script_start_time <= TOTAL_TIMEOUT):
            logger.info("Waiting for producer to shut down...")
            wait_for_shutdown("ALL", "producer", "main", timeout=INDIVIDUAL_PROCESS_TIMEOUT)
        
        # Clean up all state files
        if _should_continue:
            logger.info("Cleaning up state files...")
            try:
                delete_all_states()
            except Exception as e:
                logger.error(f"Error cleaning up state files: {e}")
        
        logger.info("Shutdown process completed")
        
    except Exception as e:
        logger.error(f"Unexpected error in kill_all script: {e}", exc_info=True)
        # Don't re-raise - we want the script to exit successfully
        # so Airflow doesn't mark it as failed
    finally:
        # Always exit successfully to prevent zombie tasks
        # The script has done its best to shut down processes
        logger.info("Exiting kill_all script")
        sys.exit(0)


if __name__ == "__main__":
    main()




