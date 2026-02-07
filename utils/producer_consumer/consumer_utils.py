"""
State management utilities for producer and consumer processes.
"""

import os
import json
import time
from pathlib import Path
from typing import Optional

# Default state directory
STATE_DIR = os.getenv(
    "STATE_DIR",
    "/opt/airflow/custom_persistent_shared/consumer_states"
)


def state_write(crypto: str, model: str, version: str, state: str, error_msg: str = ""):
    """
    Write state to JSON file with proper file permissions.
    
    Args:
        crypto: Cryptocurrency symbol (e.g., "BTCUSDT" or "ALL" for producer)
        model: Model name (e.g., "lightgbm" or "producer")
        version: Version (e.g., "v1" or "main")
        state: State value (e.g., "running", "pause", "delete")
        error_msg: Optional error message
    """
    # Ensure state directory exists
    Path(STATE_DIR).mkdir(parents=True, exist_ok=True)
    
    # Set permissions
    try:
        os.chmod(STATE_DIR, 0o777)
    except Exception:
        pass  # Ignore permission errors on Windows
    
    # Generate filename
    if crypto == "ALL" and model == "producer":
        filename = "ALL_producer_main.json"
    else:
        filename = f"{crypto}_{model}_{version}.json"
    
    filepath = os.path.join(STATE_DIR, filename)
    
    # Write state
    state_data = {
        "crypto": crypto,
        "model": model,
        "version": version,
        "state": state,
        "error_msg": error_msg
    }
    
    with open(filepath, 'w') as f:
        json.dump(state_data, f, indent=2)
    
    # Set file permissions
    try:
        os.chmod(filepath, 0o777)
    except Exception:
        pass  # Ignore permission errors on Windows


def state_checker(crypto: str, model: str, version: str, timeout: int = 120) -> str:
    """
    Read state from file with retry logic.
    
    Args:
        crypto: Cryptocurrency symbol
        model: Model name
        version: Version
        timeout: Maximum time to wait for file to appear (seconds)
        
    Returns:
        State string, or "unknown" if file doesn't exist after timeout
    """
    # Generate filename
    if crypto == "ALL" and model == "producer":
        filename = "ALL_producer_main.json"
    else:
        filename = f"{crypto}_{model}_{version}.json"
    
    filepath = os.path.join(STATE_DIR, filename)
    
    # Wait for file to appear
    start_time = time.time()
    while not os.path.exists(filepath):
        if time.time() - start_time > timeout:
            return "unknown"
        time.sleep(1)
    
    # Read state
    try:
        with open(filepath, 'r') as f:
            state_data = json.load(f)
            return state_data.get("state", "unknown")
    except (json.JSONDecodeError, KeyError, IOError) as e:
        print(f"Error reading state file {filepath}: {e}")
        return "unknown"


def get_state_data(crypto: str, model: str, version: str) -> Optional[dict]:
    """
    Get full state data from file.
    
    Args:
        crypto: Cryptocurrency symbol
        model: Model name
        version: Version
        
    Returns:
        State dictionary or None if file doesn't exist
    """
    # Generate filename
    if crypto == "ALL" and model == "producer":
        filename = "ALL_producer_main.json"
    else:
        filename = f"{crypto}_{model}_{version}.json"
    
    filepath = os.path.join(STATE_DIR, filename)
    
    if not os.path.exists(filepath):
        return None
    
    try:
        with open(filepath, 'r') as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        print(f"Error reading state file {filepath}: {e}")
        return None


def delete_state(crypto: str, model: str, version: str):
    """
    Remove state file for a specific consumer.
    
    Args:
        crypto: Cryptocurrency symbol
        model: Model name
        version: Version
    """
    # Generate filename
    if crypto == "ALL" and model == "producer":
        filename = "ALL_producer_main.json"
    else:
        filename = f"{crypto}_{model}_{version}.json"
    
    filepath = os.path.join(STATE_DIR, filename)
    
    if os.path.exists(filepath):
        try:
            os.remove(filepath)
        except Exception as e:
            print(f"Error deleting state file {filepath}: {e}")


def delete_all_states():
    """Remove all state files (used for cleanup)."""
    if not os.path.exists(STATE_DIR):
        return
    
    for filename in os.listdir(STATE_DIR):
        if filename.endswith('.json'):
            filepath = os.path.join(STATE_DIR, filename)
            try:
                os.remove(filepath)
            except Exception as e:
                print(f"Error deleting state file {filepath}: {e}")







