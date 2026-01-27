"""
Vast.ai Instance Termination Utility

This module provides functions to terminate all active Vast.ai instances.
Used for cleanup before creating new instances and on DAG completion/failure.
"""

import os
import json
import subprocess
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import List, Dict

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Log file path (configurable via environment variable)
LOG_DIR = os.getenv(
    "VASTAI_LOG_DIR",
    "/opt/airflow/custom_persistent_shared"
)
LOG_FILE = os.path.join(LOG_DIR, "kill_vastai_instances.log")


def setup_vastai_cli():
    """Configure Vast.ai CLI with API key."""
    key = os.getenv("VASTAI_API_KEY")
    if not key:
        raise ValueError("VASTAI_API_KEY environment variable not set.")
    
    try:
        subprocess.run(
            ["vastai", "set", "api-key", key],
            check=True,
            capture_output=True,
            text=True
        )
        logger.info("Vast.ai CLI configured successfully")
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to set Vast.ai API key: {e}")
        raise
    except FileNotFoundError:
        raise FileNotFoundError(
            "Vast.ai CLI not found. Install with: pip install vastai"
        )


def is_network_error(error_output: str) -> bool:
    """Check if error is a network/connection error."""
    network_error_keywords = [
        "ConnectionError",
        "Connection aborted",
        "Name or service not known",
        "Failed to establish",
        "Remote end closed connection",
        "Max retries exceeded",
        "socket.gaierror",
        "NewConnectionError"
    ]
    error_lower = error_output.lower()
    return any(keyword.lower() in error_lower for keyword in network_error_keywords)


def get_all_instances(max_retries: int = 2, retry_delay: int = 3) -> List[Dict]:
    """
    Get all active Vast.ai instances.
    
    Args:
        max_retries: Maximum number of retry attempts for network errors
        retry_delay: Initial delay between retries (exponential backoff)
    
    Returns:
        List of instance dictionaries
    """
    cmd = ["vastai", "show", "instances", "--raw"]
    
    for attempt in range(max_retries):
        try:
            result = subprocess.run(
                cmd,
                check=True,
                capture_output=True,
                text=True,
                timeout=30  # 30 second timeout
            )
            
            # Parse JSON output
            instances = json.loads(result.stdout)
            if not isinstance(instances, list):
                instances = [instances] if instances else []
            
            # Filter for active instances (running, starting, etc.)
            active_instances = [
                inst for inst in instances
                if inst.get("actual_status", "").lower() not in ["stopped", "terminated", "failed"]
            ]
            
            logger.info(f"Found {len(active_instances)} active instances")
            return active_instances
            
        except subprocess.CalledProcessError as e:
            error_msg = e.stderr or str(e)
            is_network = is_network_error(error_msg)
            
            if is_network and attempt < max_retries - 1:
                wait_time = retry_delay * (2 ** attempt)  # Exponential backoff
                logger.warning(
                    f"Network error listing instances (attempt {attempt + 1}/{max_retries}): {error_msg[:200]}"
                )
                logger.info(f"Retrying in {wait_time} seconds...")
                time.sleep(wait_time)
                continue
            else:
                # For network errors on last attempt, return empty (assume no instances)
                if is_network:
                    logger.warning("Network error listing instances. Assuming no active instances.")
                else:
                    logger.error(f"Failed to list instances: {e}")
                    if e.stderr:
                        logger.error(f"Error output: {e.stderr[:500]}")
                return []
                
        except subprocess.TimeoutExpired:
            if attempt < max_retries - 1:
                wait_time = retry_delay * (2 ** attempt)
                logger.warning(f"Timeout listing instances (attempt {attempt + 1}/{max_retries}). Retrying in {wait_time} seconds...")
                time.sleep(wait_time)
                continue
            else:
                logger.warning("Timeout listing instances. Assuming no active instances.")
                return []
                
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse instances JSON: {e}")
            return []
    
    return []


def log_action(message: str):
    """Log action to file and console."""
    timestamp = datetime.utcnow().isoformat()
    log_message = f"[{timestamp}] {message}"
    
    # Log to console
    logger.info(message)
    
    # Log to file (non-critical, continue if it fails)
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        # Try to set permissions if possible (may fail, but that's okay)
        try:
            os.chmod(LOG_DIR, 0o777)
        except:
            pass  # Ignore permission errors on chmod
        with open(LOG_FILE, "a") as f:
            f.write(log_message + "\n")
    except (PermissionError, OSError) as e:
        # Only log permission errors at debug level to avoid spam
        logger.debug(f"Could not write to log file (non-critical): {e}")
    except Exception as e:
        logger.debug(f"Failed to write to log file (non-critical): {e}")


def kill_instance(instance_id: str) -> bool:
    """
    Terminate a single Vast.ai instance.
    
    Args:
        instance_id: Vast.ai instance ID
    
    Returns:
        True if successful, False otherwise
    """
    try:
        cmd = ["vastai", "destroy", "instance", str(instance_id)]
        result = subprocess.run(
            cmd,
            check=True,
            capture_output=True,
            text=True
        )
        logger.info(f"Successfully terminated instance {instance_id}")
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to terminate instance {instance_id}: {e}")
        logger.error(f"Error output: {e.stderr}")
        return False


def kill_all_vastai_instances():
    """
    Terminate all active Vast.ai instances.
    
    This function:
    1. Logs the action
    2. Fetches all running instances
    3. Destroys each instance by ID
    4. Confirms completion
    """
    log_action("=" * 60)
    log_action("Starting Vast.ai Instance Cleanup")
    log_action("=" * 60)
    
    # Setup Vast.ai CLI
    try:
        setup_vastai_cli()
    except Exception as e:
        log_action(f"ERROR: Failed to setup Vast.ai CLI: {e}")
        return
    
    # Get all active instances
    instances = get_all_instances()
    
    if not instances:
        log_action("No active instances found. Nothing to terminate.")
        return
    
    log_action(f"Found {len(instances)} active instance(s) to terminate")
    
    # Terminate each instance
    success_count = 0
    failure_count = 0
    
    for instance in instances:
        instance_id = instance.get("id") or instance.get("new_contract")
        if not instance_id:
            logger.warning(f"Instance missing ID: {instance}")
            continue
        
        status = instance.get("actual_status", "unknown")
        log_action(f"Terminating instance {instance_id} (status: {status})")
        
        if kill_instance(instance_id):
            success_count += 1
        else:
            failure_count += 1
    
    # Log summary
    log_action("=" * 60)
    log_action(f"Cleanup Complete: {success_count} succeeded, {failure_count} failed")
    log_action("=" * 60)


if __name__ == "__main__":
    # For testing
    kill_all_vastai_instances()

