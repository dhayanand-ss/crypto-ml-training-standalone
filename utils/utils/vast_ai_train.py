"""
Vast.ai Instance Management for Distributed ML Training

This module provides functions to create and manage Vast.ai GPU instances
for parallel machine learning model training. It integrates with Apache Airflow
for automated training pipelines.

Key Features:
- Automatic cost optimization (budget enforcement)
- Blacklist mechanism for problematic machines
- Automatic retry logic with timeouts
- Instance lifecycle management
"""

import os
import json
import time
import subprocess
import logging
import pickle
import tempfile
import stat
import re
import uuid
from pathlib import Path
from typing import Dict, List, Optional, Set
from datetime import datetime

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration Constants
BUDGET = 0.25  # $0.25 per hour maximum
MAX_POD_WAIT = 600  # 10 minutes maximum wait for pod to become "running"
MAX_RETRY_TIME = 1200  # 20 minutes maximum time to retry finding available pods
FIND_POD_SLEEP = 30  # 30 seconds between offer searches

# GPU Requirements
GPU_QUERY = "gpu_total_ram>=11 disk_space>=30 verified=True datacenter=True"

# Docker Image - configurable via environment variable
# Default to a public Python image (Vast AI instances have CUDA drivers pre-installed)
# The startup command clones repo and installs dependencies, so we just need a base image
DOCKER_IMAGE = os.getenv(
    "VASTAI_DOCKER_IMAGE",
    "python:3.10-slim"  # Public Python image - CUDA drivers available on Vast AI hosts
)

# Blacklist storage path (configurable via environment variable)
BLACKLIST_DIR = os.getenv(
    "VASTAI_BLACKLIST_DIR",
    "/opt/airflow/custom_persistent_shared"
)
BLACKLIST_FILE = os.path.join(BLACKLIST_DIR, "blacklisted_machines.pkl")


def get_vastai_api_key() -> str:
    """Get Vast.ai API key from environment variable."""
    key = os.getenv("VASTAI_API_KEY")
    if not key:
        raise ValueError("VASTAI_API_KEY environment variable not set.")
    return key


def setup_vastai_cli():
    """Configure Vast.ai CLI with API key."""
    key = get_vastai_api_key()
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


def load_blacklist() -> Set[int]:
    """Load blacklisted machine IDs from persistent storage."""
    if os.path.exists(BLACKLIST_FILE):
        try:
            with open(BLACKLIST_FILE, "rb") as f:
                blacklist = pickle.load(f)
                logger.info(f"Loaded {len(blacklist)} blacklisted machines")
                return set(blacklist)
        except Exception as e:
            logger.warning(f"Failed to load blacklist: {e}. Starting with empty blacklist.")
            return set()
    else:
        # Create directory if it doesn't exist
        os.makedirs(BLACKLIST_DIR, exist_ok=True)
        return set()


def save_blacklist(blacklist: Set[int]):
    """Save blacklisted machine IDs to persistent storage."""
    try:
        os.makedirs(BLACKLIST_DIR, exist_ok=True)
        with open(BLACKLIST_FILE, "wb") as f:
            pickle.dump(list(blacklist), f)
        logger.info(f"Saved {len(blacklist)} blacklisted machines to {BLACKLIST_FILE}")
    except Exception as e:
        logger.error(f"Failed to save blacklist: {e}")


def calculate_full_pod_cost(
    pod: dict,
    hours: float = 1,
    extra_storage_tb: float = 0,
    internet_up_tb: float = 0.005,  # 5 GB upload
    internet_down_tb: float = 0.01   # 10 GB download
) -> float:
    """
    Calculate total cost for a pod including storage and bandwidth.
    
    Args:
        pod: Pod offer dictionary from Vast.ai
        hours: Number of hours to run
        extra_storage_tb: Additional storage in TB beyond base
        internet_up_tb: Upload bandwidth in TB
        internet_down_tb: Download bandwidth in TB
    
    Returns:
        Total cost in USD
    """
    # Base hourly cost
    dph_total = pod.get("dph_total", 0)
    base_cost = dph_total * hours
    
    # Storage cost (prorated monthly)
    storage_monthly_cost = pod.get("storage_cost", 0)
    storage_cost = (storage_monthly_cost / (30 * 24)) * extra_storage_tb * hours
    
    # Internet costs
    internet_up_cost_per_tb = pod.get("inet_up_cost", 0)
    internet_down_cost_per_tb = pod.get("inet_down_cost", 0)
    internet_cost = (
        internet_up_cost_per_tb * internet_up_tb +
        internet_down_cost_per_tb * internet_down_tb
    )
    
    total_cost = base_cost + storage_cost + internet_cost
    return total_cost


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


def get_offers(max_retries: int = 3, retry_delay: int = 5) -> List[dict]:
    """
    Search for available GPU offers matching requirements.
    
    Args:
        max_retries: Maximum number of retry attempts for network errors
        retry_delay: Initial delay between retries (exponential backoff)
    
    Returns:
        List of pod offer dictionaries
    """
    cmd = [
        "vastai", "search", "offers",
        "--raw",
        GPU_QUERY
    ]
    
    for attempt in range(max_retries):
        try:
            result = subprocess.run(
                cmd,
                check=True,
                capture_output=True,
                text=True,
                timeout=60  # 60 second timeout
            )
            
            # Parse JSON output
            offers = json.loads(result.stdout)
            if not isinstance(offers, list):
                offers = [offers] if offers else []
            
            logger.info(f"Found {len(offers)} available offers")
            return offers
            
        except subprocess.CalledProcessError as e:
            error_msg = e.stderr or str(e)
            is_network = is_network_error(error_msg)
            
            if is_network and attempt < max_retries - 1:
                wait_time = retry_delay * (2 ** attempt)  # Exponential backoff
                logger.warning(
                    f"Network error searching offers (attempt {attempt + 1}/{max_retries}): {error_msg[:200]}"
                )
                logger.info(f"Retrying in {wait_time} seconds...")
                time.sleep(wait_time)
                continue
            else:
                logger.error(f"Failed to search offers: {e}")
                if e.stderr:
                    logger.error(f"Error output: {e.stderr[:500]}")
                return []
                
        except subprocess.TimeoutExpired:
            if attempt < max_retries - 1:
                wait_time = retry_delay * (2 ** attempt)
                logger.warning(f"Timeout searching offers (attempt {attempt + 1}/{max_retries}). Retrying in {wait_time} seconds...")
                time.sleep(wait_time)
                continue
            else:
                logger.error("Timeout searching offers after all retries")
                return []
                
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse offers JSON: {e}")
            return []
    
    return []


def verify_instance_exists(instance_id: str) -> Optional[Dict]:
    """
    Verify that an instance ID actually exists by listing all instances.
    
    Args:
        instance_id: Vast.ai instance ID to verify
    
    Returns:
        Instance dict if found, None otherwise
    """
    try:
        cmd = ["vastai", "show", "instances", "--raw"]
        result = subprocess.run(
            cmd,
            check=True,
            capture_output=True,
            text=True,
            timeout=30
        )
        
        instances = json.loads(result.stdout)
        if not isinstance(instances, list):
            instances = [instances] if instances else []
        
        # Look for the instance ID
        for inst in instances:
            inst_id = str(inst.get("id", ""))
            if inst_id == str(instance_id):
                logger.info(f"Verified instance {instance_id} exists in instance list")
                return inst
        
        logger.warning(f"Instance {instance_id} not found in instance list")
        logger.debug(f"Available instance IDs: {[str(i.get('id', '')) for i in instances]}")
        return None
        
    except subprocess.CalledProcessError as e:
        # Combine stderr and stdout for error detection
        error_output = (e.stderr or "") + (e.stdout or "")
        error_msg = error_output.lower() if error_output else str(e).lower()
        
        # Check if instance doesn't exist (various error formats)
        instance_id_str = str(instance_id)
        instance_not_found_patterns = [
            "no such container",
            "not found",
            "does not exist",
            f"c.{instance_id_str}",  # Vast AI internal format like "C.29306163" (case-insensitive)
            f"c.{instance_id_str.lower()}",  # Lowercase variant
            f"c.{instance_id_str.upper()}",  # Uppercase variant
            f"container.*{instance_id_str}",
            "error response from daemon",  # Docker daemon error prefix
        ]
        
        # Also check if instance ID appears in error with error keywords
        if instance_id_str in error_output or instance_id_str in str(e):
            if any(pattern in error_msg for pattern in ["no such", "not found", "does not exist", "error response from daemon"]):
                logger.warning(f"Instance {instance_id} does not exist (no such container)")
                return None
        
        if any(pattern in error_msg for pattern in instance_not_found_patterns):
            logger.warning(f"Instance {instance_id} does not exist (no such container)")
        else:
            logger.warning(f"Failed to verify instance existence: {e}")
            if error_output:
                logger.debug(f"Error details: {error_output[:500]}")
        return None
    except Exception as e:
        logger.warning(f"Failed to verify instance existence: {e}")
        return None


def find_newly_created_instance(before_instances: List[Dict], after_instances: List[Dict]) -> Optional[str]:
    """
    Find the newly created instance by comparing before/after instance lists.
    
    Args:
        before_instances: List of instances before creation
        after_instances: List of instances after creation
    
    Returns:
        Instance ID of newly created instance, or None
    """
    before_ids = {str(inst.get("id", "")) for inst in before_instances}
    after_ids = {str(inst.get("id", "")) for inst in after_instances}
    
    new_ids = after_ids - before_ids
    if new_ids:
        new_id = list(new_ids)[0]
        logger.info(f"Found newly created instance: {new_id}")
        return new_id
    
    return None


def get_all_instances() -> List[Dict]:
    """Get all instances from Vast.ai."""
    try:
        cmd = ["vastai", "show", "instances", "--raw"]
        result = subprocess.run(
            cmd,
            check=True,
            capture_output=True,
            text=True,
            timeout=30
        )
        
        instances = json.loads(result.stdout)
        if not isinstance(instances, list):
            instances = [instances] if instances else []
        
        return instances
    except Exception as e:
        logger.warning(f"Failed to get instances: {e}")
        return []


def wait_for_pod(instance_id: str, timeout: int = MAX_POD_WAIT) -> bool:
    """
    Wait for pod to reach "running" state.
    
    Args:
        instance_id: Vast.ai instance ID
        timeout: Maximum time to wait in seconds
    
    Returns:
        True if pod is running, False if timeout
    """
    start_time = time.time()
    logger.info(f"Waiting for instance {instance_id} to become running...")
    
    while time.time() - start_time < timeout:
        try:
            cmd = ["vastai", "show", "instance", instance_id, "--raw"]
            result = subprocess.run(
                cmd,
                check=True,
                capture_output=True,
                text=True,
                timeout=30
            )
            
            # Check for error messages in output (even if command succeeded)
            error_output = (result.stderr or "") + (result.stdout or "")
            if error_output and ("error response from daemon" in error_output.lower() or 
                                f"no such container" in error_output.lower() or
                                f"c.{instance_id}" in error_output.lower()):
                instance_id_str = str(instance_id)
                if instance_id_str in error_output:
                    logger.warning(f"Instance {instance_id} container not found (may still be starting): {error_output[:200]}")
                    time.sleep(10)
                    continue
            
            # Parse JSON with error handling
            try:
                instance_data = json.loads(result.stdout)
            except json.JSONDecodeError as e:
                logger.warning(f"Failed to parse instance data JSON: {e}")
                logger.debug(f"Raw output: {result.stdout[:200]}")
                if result.stderr:
                    logger.debug(f"Stderr: {result.stderr[:200]}")
                time.sleep(10)
                continue
            
            # Handle None case - get returns default only if key doesn't exist, not if value is None
            actual_status = instance_data.get("actual_status")
            if actual_status is None:
                logger.debug(f"Instance {instance_id} status not available yet, waiting...")
                time.sleep(10)
                continue
            
            status = str(actual_status).lower()
            
            if status == "running":
                logger.info(f"Instance {instance_id} is now running")
                return True
            elif status in ["failed", "stopped", "terminated"]:
                logger.error(f"Instance {instance_id} failed with status: {status}")
                return False
            
            logger.debug(f"Instance {instance_id} status: {status}, waiting...")
            time.sleep(10)  # Check every 10 seconds
            
        except subprocess.CalledProcessError as e:
            # Combine stderr and stdout for error detection
            error_output = (e.stderr or "") + (e.stdout or "")
            error_msg = error_output.lower() if error_output else str(e).lower()
            
            # Check if instance doesn't exist (various error formats)
            # Note: Vast AI uses "C.<instance_id>" format (capital C)
            instance_not_found_patterns = [
                "no such container",
                "not found",
                "does not exist",
                f"c.{instance_id}",  # Vast AI internal format like "C.29306163" (case-insensitive match)
                f"c.{instance_id.lower()}",  # Lowercase variant
                f"c.{instance_id.upper()}",  # Uppercase variant
                f"container.*{instance_id}",
                "error response from daemon",  # Docker daemon error prefix
            ]
            
            # Also check if error contains the instance ID in any format with error keywords
            instance_id_str = str(instance_id)
            
            # First check if instance ID appears in error
            if instance_id_str in error_output or instance_id_str in str(e):
                # If instance ID is mentioned in error with "no such" or "error response", it doesn't exist
                if any(pattern in error_msg for pattern in ["no such", "not found", "does not exist", "error response from daemon"]):
                    logger.error(f"Instance {instance_id} does not exist. It may have been destroyed or never created.")
                    logger.debug(f"Error details: {error_output[:500]}")
                    return False
            
            # Check all error patterns
            if any(pattern in error_msg for pattern in instance_not_found_patterns):
                logger.error(f"Instance {instance_id} does not exist. It may have been destroyed or never created.")
                logger.debug(f"Error details: {error_output[:500]}")
                return False
            
            # Only log detailed error occasionally to avoid log spam
            elapsed = time.time() - start_time
            if int(elapsed) % 60 == 0:  # Log detailed error every minute
                logger.warning(f"Failed to check instance status: {e}")
                if e.stderr:
                    logger.warning(f"Error output (stderr): {e.stderr[:200]}")
                if e.stdout:
                    logger.warning(f"Error output (stdout): {e.stdout[:200]}")
            else:
                logger.debug(f"Failed to check instance status (will retry): {e}")
            time.sleep(10)
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse instance data: {e}")
            time.sleep(10)
    
    logger.error(f"Timeout waiting for instance {instance_id} to become running")
    return False


def build_startup_command() -> str:
    """
    Build the startup command for the Vast.ai instance.
    
    This command will:
    1. Export environment variables
    2. Clone the repository
    3. Install Weights & Biases
    4. Start parallel training
    
    Returns:
        Multi-line bash script as a single string
    """
    # Get environment variables
    env_vars = {
        "MLFLOW_S3_ENDPOINT_URL": os.getenv("MLFLOW_S3_ENDPOINT_URL", ""),
        "MLFLOW_URI": os.getenv("MLFLOW_URI", ""),
        "MLFLOW_TRACKING_USERNAME": os.getenv("MLFLOW_TRACKING_USERNAME", ""),
        "MLFLOW_TRACKING_PASSWORD": os.getenv("MLFLOW_TRACKING_PASSWORD", ""),
        "MLFLOW_SQLALCHEMY_POOL_SIZE": os.getenv("MLFLOW_SQLALCHEMY_POOL_SIZE", "2"),
        "MLFLOW_SQLALCHEMY_MAX_OVERFLOW": os.getenv("MLFLOW_SQLALCHEMY_MAX_OVERFLOW", "0"),
        "AWS_ACCESS_KEY_ID": os.getenv("AWS_ACCESS_KEY_ID", ""),
        "AWS_SECRET_ACCESS_KEY": os.getenv("AWS_SECRET_ACCESS_KEY", ""),
        "AWS_DEFAULT_REGION": os.getenv("AWS_DEFAULT_REGION", "auto"),
        "S3_URL": os.getenv("S3_URL", ""),
        "DATABASE_URL": os.getenv("DATABASE_URL", ""),
        "TRL_DATABASE_URL": os.getenv("TRL_DATABASE_URL", ""),
        "AIRFLOW_DB": os.getenv("AIRFLOW_DB", ""),
        # GCP credentials for GCS access
        "GCP_PROJECT_ID": os.getenv("GCP_PROJECT_ID", ""),
        "GCP_CREDENTIALS_PATH": "/workspace/gcp-credentials.json",  # Path on instance
    }
    
    # Handle GCP credentials - encode and pass as environment variable
    gcp_credentials_path = os.getenv("GCP_CREDENTIALS_PATH") or os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    gcp_credentials_json = None
    
    if gcp_credentials_path and os.path.exists(gcp_credentials_path):
        try:
            with open(gcp_credentials_path, 'r') as f:
                gcp_credentials_json = f.read()
            logger.info(f"Found GCP credentials file: {gcp_credentials_path}")
        except Exception as e:
            logger.warning(f"Could not read GCP credentials file: {e}")
    elif os.path.exists("dhaya123-335710-039eabaad669.json"):
        # Try default credential file name
        try:
            with open("dhaya123-335710-039eabaad669.json", 'r') as f:
                gcp_credentials_json = f.read()
            logger.info("Found default GCP credentials file")
        except Exception as e:
            logger.warning(f"Could not read default GCP credentials file: {e}")
    
    # Build export commands
    export_cmds_list = [
        f'export {key}="{value}"'
        for key, value in env_vars.items()
        if value  # Only export non-empty values
    ]
    
    # Add GCP credentials setup - upload to GCS and use signed URL to reduce command size
    gcp_creds_setup = ""
    if gcp_credentials_json:
        import json
        import tempfile
        import uuid
        try:
            # Validate JSON
            json.loads(gcp_credentials_json)
            
            # Upload credentials to GCS and get signed URL (much smaller than embedding)
            try:
                from utils.artifact_control.gcs_manager import GCSManager
                gcs_manager = GCSManager(bucket='mlops-new')
                
                # Create temporary file with credentials
                temp_creds_file = tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False)
                temp_creds_file.write(gcp_credentials_json)
                temp_creds_file.close()
                
                # Upload to GCS with unique name
                creds_key = f"vast-ai-credentials/{uuid.uuid4().hex}.json"
                gcs_manager.upload_file(temp_creds_file.name, creds_key)
                
                # Generate signed URL (valid for 2 hours)
                signed_url = gcs_manager.generate_signed_url(creds_key, expiration_minutes=120)
                
                # Clean up temp file
                os.unlink(temp_creds_file.name)
                
                # Use compact download command (much smaller than embedded credentials)
                gcp_creds_setup = f"mkdir -p /workspace && curl -s '{signed_url}' > /workspace/gcp-credentials.json && chmod 600 /workspace/gcp-credentials.json && export GOOGLE_APPLICATION_CREDENTIALS=/workspace/gcp-credentials.json && export GCP_CREDENTIALS_PATH=/workspace/gcp-credentials.json"
                logger.info(f"GCP credentials uploaded to GCS. Using signed URL download (command size: ~{len(signed_url) + 150} chars)")
            except Exception as gcs_error:
                logger.warning(f"Failed to upload credentials to GCS: {gcs_error}. Falling back to embedded method.")
                # Fallback to compressed embedding if GCS upload fails
                # Use more aggressive compression and shorter command
                import base64
                import gzip
                creds_compressed = gzip.compress(gcp_credentials_json.encode(), compresslevel=9)
                creds_b64 = base64.b64encode(creds_compressed).decode()
                # Ultra-compact command - minimal spacing and combined exports
                gcp_creds_setup = f"mkdir -p /workspace&&echo '{creds_b64}'|base64 -d|gunzip>/workspace/gcp-credentials.json&&chmod 600 /workspace/gcp-credentials.json&&export GOOGLE_APPLICATION_CREDENTIALS=/workspace/gcp-credentials.json GCP_CREDENTIALS_PATH=/workspace/gcp-credentials.json"
                logger.warning(f"Using fallback embedded method (compressed size: {len(creds_b64)} chars)")
                if len(creds_b64) + len(gcp_creds_setup) > 2000:
                    logger.error(f"WARNING: Embedded credentials are very large ({len(creds_b64)} chars). Command may exceed Vast AI limit!")
        except Exception as e:
            logger.warning(f"Failed to setup GCP credentials: {e}")
    
    export_cmds = " && ".join(export_cmds_list) if export_cmds_list else ""
    
    # W&B API key (if available)
    wandb_key = os.getenv("WANDB_API_KEY", "")
    wandb_login = f"wandb login {wandb_key}" if wandb_key else "echo 'WANDB_API_KEY not set, skipping wandb login'"
    
    # Build complete startup command as a single line with semicolons
    # Vast.ai CLI works better with single-line commands or properly escaped multi-line
    cmd_parts = ["set -e"]
    
    # Install openssh-client FIRST to prevent SSH errors from Vast AI's .launch script
    # This must be the very first command to run
    cmd_parts.append("apt-get update && apt-get install -y openssh-client 2>&1 || true")
    
    if export_cmds:
        cmd_parts.append(export_cmds)
    
    # Add GCP credentials setup if available - must be before data download
    if gcp_creds_setup:
        # Convert multi-line to single line with && separators
        gcp_creds_lines = [line.strip() for line in gcp_creds_setup.strip().split('\n') if line.strip() and not line.strip().startswith('#')]
        cmd_parts.extend(gcp_creds_lines)
        # Verify credentials and export GCP_PROJECT_ID - combined
        gcp_project_id = os.getenv("GCP_PROJECT_ID", "")
        if gcp_project_id:
            cmd_parts.append(f"[ -f /workspace/gcp-credentials.json ] && export GCP_PROJECT_ID='{gcp_project_id}' || exit 1")
        else:
            cmd_parts.append("[ -f /workspace/gcp-credentials.json ] || exit 1")
    
    # Check if using a custom Docker image (code pre-packaged) or need to clone/upload
    custom_image = os.getenv("VASTAI_DOCKER_IMAGE", "")
    if not custom_image:
        custom_image = DOCKER_IMAGE  # Use default if not set
    github_repo = os.getenv("VASTAI_GITHUB_REPO", "")
    
    # If using a custom image (not the default python:3.10-slim), code should be pre-packaged
    # Custom images typically have a registry prefix (e.g., docker.io/user/image or user/image)
    default_image = "python:3.10-slim"
    using_custom_image = custom_image != default_image and "/" in custom_image
    
    # Determine project root directory name (for absolute paths) - do this first
    if github_repo:
        repo_name = github_repo.split("/")[-1].replace(".git", "")
    elif using_custom_image:
        repo_name = "crypto-ml-training"
    else:
        repo_name = "crypto-ml-training-standalone"
    
    project_root = f"/workspace/{repo_name}"
    
    # Create /workspace directory first (it doesn't exist in base images)
    # Note: openssh-client already installed above as first command
    cmd_parts.extend([
        "mkdir -p /workspace",
        "cd /workspace",
    ])
    
    if using_custom_image:
        # Code is pre-packaged in Docker image, just need to run training
        # The image should have code at /app, so we can use that or copy to workspace
        cmd_parts.extend([
            "cp -r /app /workspace/crypto-ml-training 2>/dev/null || true",
            "cd /workspace/crypto-ml-training || cd /app",
        ])
        logger.info(f"Using custom Docker image {custom_image} - code should be pre-packaged")
    elif github_repo:
        # Clone from GitHub - shortened commands
        cmd_parts.extend([
            f"cd /workspace && ([ -d {repo_name} ] || git clone {github_repo} {repo_name} || sleep 3 && git clone {github_repo} {repo_name})",
            f"[ -d {project_root} ] || (echo 'ERROR: {project_root} missing' && exit 1)",
            f"cd {project_root} || exit 1",
            "pip install -U pip && [ -f requirements.txt ] && pip install -q -r requirements.txt || true",
        ])
    else:
        # No GitHub repo and no custom image - create workspace and expect manual upload
        cmd_parts.extend([
            f"cd /workspace && mkdir -p {repo_name} && cd {repo_name}",
        ])
        logger.warning("No GitHub repository or custom Docker image configured.")
        logger.warning("Code must be uploaded manually via SSH. Set VASTAI_GITHUB_REPO or build a custom Docker image.")
        cmd_parts.extend([
            "pip install --upgrade pip",
            "if [ -f requirements.txt ]; then pip install -r requirements.txt; else echo 'Warning: requirements.txt not found, continuing...'; fi",
        ])
    
    # Common steps - already in project root from above
    cmd_parts.extend([
        f"cd {project_root} || exit 1",
        "[ -f requirements.txt ] || [ -d utils ] || exit 1",
        "apt-get install -y libgomp1 curl || true",
        "pip install -q wandb || true",
        wandb_login,
        "mkdir -p data/prices data/articles",
        # Download data - ultra-compact
        f"python -c \"import os,sys;sys.path.insert(0,'.');os.chdir('{project_root}');c='/workspace/gcp-credentials.json';os.environ.update({{'GOOGLE_APPLICATION_CREDENTIALS':c,'GCP_CREDENTIALS_PATH':c}});os.environ.setdefault('GCP_PROJECT_ID',os.getenv('GCP_PROJECT_ID',''));from trainer.train_utils import download_s3_dataset,S3_AVAILABLE;S3_AVAILABLE and os.path.exists(c) and download_s3_dataset('BTCUSDT',False)\" 2>&1 || true",
        # Copy files - shortened
        "[ -f data/prices/BTCUSDT.csv ] && [ ! -f data/btcusdt.csv ] && cp data/prices/BTCUSDT.csv data/btcusdt.csv || [ -f data/prices/btcusdt.csv ] && [ ! -f data/btcusdt.csv ] && cp data/prices/btcusdt.csv data/btcusdt.csv || [ -f data/BTCUSDT.csv ] && [ ! -f data/btcusdt.csv ] && cp data/BTCUSDT.csv data/btcusdt.csv || true",
        # Verify files
        "[ -f data/btcusdt.csv ] || [ -f data/prices/BTCUSDT.csv ] || (echo 'ERROR: No data file' && exit 1)",
        # Start training
        "python -m utils.trainer.train_paralelly || true"
    ])
    
    startup_cmd = " && ".join(cmd_parts)
    
    # Log command length for debugging
    cmd_length = len(startup_cmd)
    logger.info(f"Startup command total length: {cmd_length} characters")
    
    # Check if command exceeds limit
    if cmd_length > 4048:
        logger.error(f"Startup command exceeds Vast AI limit! Length: {cmd_length} chars (limit: 4048)")
        logger.error("This usually happens when GCS upload fails and fallback embedded credentials are used.")
        logger.error("In production (Airflow), GCS upload should work, so signed URL method will be used (much smaller).")
        logger.error("If this error persists in production, check GCP credentials configuration.")
        # Still return the command - let Vast AI reject it with a clear error
        # This is better than silently failing later
    
    if cmd_length > 3500:  # Warn if approaching limit
        logger.warning(f"Startup command is large ({cmd_length} chars). Vast AI limit is 4048 chars.")
        logger.warning("Consider reducing command size or using alternative credential passing method.")
    
    return startup_cmd


def create_instance(DEBUG: bool = False) -> Optional[str]:
    """
    Create a Vast.ai instance for distributed ML training.
    
    This function:
    1. Cleans up existing instances
    2. Searches for available GPU offers within budget
    3. Filters by blacklist
    4. Creates instance with Docker image and startup command
    5. Waits for instance to become ready
    6. Blacklists machine if instance fails to start
    
    Args:
        DEBUG: Enable debug logging
    
    Returns:
        Instance ID if successful, None otherwise
    """
    if DEBUG:
        logging.getLogger().setLevel(logging.DEBUG)
    
    logger.info("=" * 60)
    logger.info("Starting Vast.ai Instance Creation")
    logger.info("=" * 60)
    
    # Setup Vast.ai CLI
    try:
        setup_vastai_cli()
    except Exception as e:
        logger.error(f"Failed to setup Vast.ai CLI: {e}")
        return None
    
    # Load blacklist
    blacklist = load_blacklist()
    logger.info(f"Loaded {len(blacklist)} blacklisted machines")
    
    # Cleanup existing instances
    try:
        # Import here to avoid circular dependency
        import sys
        import importlib
        kill_module = importlib.import_module("utils.utils.kill_vast_ai_instances")
        logger.info("Cleaning up existing instances...")
        kill_module.kill_all_vastai_instances()
        time.sleep(5)  # Cooldown period
    except Exception as e:
        logger.warning(f"Failed to cleanup existing instances: {e}")
    
    # Search for available pods
    start_time = time.time()
    instance_id = None
    machine_id = None
    
    while time.time() - start_time < MAX_RETRY_TIME:
        # Get offers
        offers = get_offers()
        
        if not offers:
            logger.warning(f"No offers available. Retrying in {FIND_POD_SLEEP} seconds...")
            time.sleep(FIND_POD_SLEEP)
            continue
        
        # Filter offers by budget and blacklist
        filtered_offers = [
            pod for pod in offers
            if calculate_full_pod_cost(pod) <= BUDGET
            and pod.get("machine_id") not in blacklist
        ]
        
        if not filtered_offers:
            logger.warning(
                f"No offers within budget (${BUDGET}/hr) or all blacklisted. "
                f"Retrying in {FIND_POD_SLEEP} seconds..."
            )
            time.sleep(FIND_POD_SLEEP)
            continue
        
        # Sort by cost (cheapest first)
        filtered_offers.sort(key=lambda p: calculate_full_pod_cost(p))
        
        # Try to create instance with cheapest available pod
        for pod in filtered_offers:
            pod_id = pod.get("id")
            machine_id = pod.get("machine_id")
            cost = calculate_full_pod_cost(pod)
            
            # Reset instance_id for this iteration
            instance_id = None
            
            logger.info(f"Attempting to create instance on pod {pod_id} (machine {machine_id})")
            logger.info(f"Estimated cost: ${cost:.4f}/hour")
            
            # Get instances before creation for verification
            before_instances = get_all_instances()
            before_ids = {str(inst.get("id", "")) for inst in before_instances}
            logger.debug(f"Instances before creation: {list(before_ids)}")
            
            # Small delay to avoid rate limiting
            time.sleep(0.5)
            
            try:
                # Build startup command
                logger.info("Building startup command...")
                onstart_cmd = build_startup_command()
                logger.info(f"Startup command length: {len(onstart_cmd)} characters")
                if len(onstart_cmd) > 4000:
                    logger.error(f"Startup command exceeds Vast AI limit! Length: {len(onstart_cmd)} chars (limit: 4048)")
                    logger.error("Command preview (first 500 chars):\n{onstart_cmd[:500]}")
                else:
                    logger.debug(f"Startup command preview (first 500 chars):\n{onstart_cmd[:500]}")
                
                # Vast.ai CLI expects --onstart to be a file path, not a command string
                # Write the command to a temporary file with proper encoding and permissions
                # Use mkstemp for better control over file creation
                
                logger.info("Creating temporary startup script file...")
                fd, onstart_file = tempfile.mkstemp(suffix='.sh', prefix='vastai_onstart_', text=True)
                logger.debug(f"Temporary file path: {onstart_file}")
                
                try:
                    # Write with UTF-8 encoding
                    logger.debug("Writing startup command to file...")
                    with os.fdopen(fd, 'w', encoding='utf-8') as f:
                        bytes_written = f.write(onstart_cmd)
                        f.flush()
                        os.fsync(f.fileno())  # Ensure data is written to disk
                        logger.debug(f"Wrote {bytes_written} bytes to file")
                    
                    # Verify file size
                    file_size = os.path.getsize(onstart_file)
                    logger.debug(f"File size: {file_size} bytes")
                    if file_size == 0:
                        raise ValueError(f"File is empty after write: {onstart_file}")
                    
                    # Make file executable and readable
                    logger.debug("Setting file permissions...")
                    os.chmod(onstart_file, 0o755)
                    
                    # Verify permissions
                    file_stat = os.stat(onstart_file)
                    file_mode = stat.filemode(file_stat.st_mode)
                    logger.debug(f"File permissions: {file_mode} (octal: {oct(file_stat.st_mode)})")
                    
                    # Verify file was written correctly
                    if not os.path.exists(onstart_file):
                        raise IOError(f"Failed to create temporary file: {onstart_file}")
                    
                    # Verify file is readable
                    try:
                        with open(onstart_file, 'r', encoding='utf-8') as test_f:
                            test_content = test_f.read()
                            if len(test_content) != len(onstart_cmd):
                                logger.warning(f"File content length mismatch: expected {len(onstart_cmd)}, got {len(test_content)}")
                            logger.debug(f"File verification: readable, {len(test_content)} characters")
                    except Exception as e:
                        logger.error(f"Failed to verify file readability: {e}")
                        raise
                    
                    logger.info(f"Successfully created temporary startup script: {onstart_file}")
                    logger.debug(f"File details: size={file_size} bytes, mode={file_mode}, exists={os.path.exists(onstart_file)}")
                except Exception as e:
                    # Clean up if file creation failed
                    logger.error(f"Error creating startup script file: {e}", exc_info=True)
                    try:
                        if os.path.exists(onstart_file):
                            os.unlink(onstart_file)
                            logger.debug(f"Cleaned up failed file: {onstart_file}")
                    except Exception as cleanup_error:
                        logger.warning(f"Failed to clean up file: {cleanup_error}")
                    raise
                
                try:
                    # Create instance
                    # Use custom image if set, otherwise use default
                    image_to_use = os.getenv("VASTAI_DOCKER_IMAGE", DOCKER_IMAGE)
                    logger.info(f"Using Docker image: {image_to_use}")
                    
                    # Vast.ai CLI accepts --onstart for startup commands (as a file path)
                    # Ensure we use absolute path
                    onstart_file_abs = os.path.abspath(onstart_file)
                    if not os.path.exists(onstart_file_abs):
                        raise IOError(f"Startup script file does not exist: {onstart_file_abs}")
                    
                    cmd = [
                        "vastai", "create", "instance", str(pod_id),
                        "--image", image_to_use,
                        "--onstart", onstart_file_abs,  # Use absolute path
                        "--disk", "30",
                        "--ssh"
                    ]
                    
                    # Ensure we use absolute path
                    onstart_file_abs = os.path.abspath(onstart_file)
                    logger.debug(f"Using absolute path: {onstart_file_abs}")
                    if not os.path.exists(onstart_file_abs):
                        raise IOError(f"Startup script file does not exist: {onstart_file_abs}")
                    
                    # Update command with absolute path
                    cmd = [
                        "vastai", "create", "instance", str(pod_id),
                        "--image", image_to_use,
                        "--onstart", onstart_file_abs,  # Use absolute path
                        "--disk", "30",
                        "--ssh"
                    ]
                    
                    logger.info(f"Executing Vast AI instance creation command...")
                    logger.debug(f"Full command: {' '.join(cmd)}")
                    logger.debug(f"Startup script file: {onstart_file_abs}")
                    logger.debug(f"File exists: {os.path.exists(onstart_file_abs)}")
                    logger.debug(f"File size: {os.path.getsize(onstart_file_abs)} bytes")
                    logger.debug(f"File readable: {os.access(onstart_file_abs, os.R_OK)}")
                    logger.debug(f"File executable: {os.access(onstart_file_abs, os.X_OK)}")
                    
                    # Verify file is readable before passing to Vast AI
                    try:
                        logger.debug("Pre-flight file verification...")
                        with open(onstart_file_abs, 'r', encoding='utf-8') as f:
                            content_check = f.read()
                            if not content_check:
                                raise ValueError(f"Startup script file is empty: {onstart_file_abs}")
                            if len(content_check) != len(onstart_cmd):
                                logger.warning(f"File content length mismatch: expected {len(onstart_cmd)}, got {len(content_check)}")
                            logger.debug(f"File verification passed: {len(content_check)} bytes, readable")
                            logger.debug(f"File content preview (first 200 chars):\n{content_check[:200]}")
                    except Exception as e:
                        logger.error(f"Pre-flight file verification failed: {e}", exc_info=True)
                        raise
                    
                    logger.info("Calling Vast AI CLI to create instance...")
                    result = subprocess.run(
                        cmd,
                        check=True,
                        capture_output=True,
                        text=True,
                        timeout=120  # 2 minute timeout
                    )
                    
                    # Log full output for debugging
                    logger.info("=" * 60)
                    logger.info("Vast AI Command Output:")
                    logger.info("=" * 60)
                    logger.info(f"Return code: {result.returncode}")
                    logger.info(f"STDOUT ({len(result.stdout)} chars):\n{result.stdout}")
                    if result.stderr:
                        logger.info(f"STDERR ({len(result.stderr)} chars):\n{result.stderr}")
                    logger.info("=" * 60)
                    
                    # Check for docker_build errors in output
                    output_lower = (result.stdout + (result.stderr or "")).lower()
                    if "docker_build" in output_lower:
                        logger.error("=" * 60)
                        logger.error("DOCKER_BUILD ERROR DETECTED!")
                        logger.error("=" * 60)
                        if "error writing dockerfile" in output_lower:
                            logger.error("Error type: docker_build() error writing dockerfile")
                        else:
                            logger.error(f"Error type: docker_build (other): {output_lower}")
                        logger.error(f"Startup script file: {onstart_file_abs}")
                        logger.error(f"File exists: {os.path.exists(onstart_file_abs)}")
                        logger.error(f"File size: {os.path.getsize(onstart_file_abs)} bytes")
                        logger.error(f"File permissions: {stat.filemode(os.stat(onstart_file_abs).st_mode)}")
                        logger.error(f"Startup command length: {len(onstart_cmd)} characters")
                        logger.error(f"Startup script content (first 1000 chars):\n{onstart_cmd[:1000]}")
                        logger.error("=" * 60)
                        raise RuntimeError(f"Vast AI docker_build error - startup script file issue. File: {onstart_file_abs}, Size: {os.path.getsize(onstart_file_abs)} bytes")
                finally:
                    # Clean up temporary file
                    try:
                        os.unlink(onstart_file)
                    except Exception as e:
                        logger.warning(f"Failed to delete temporary file {onstart_file}: {e}")
                
                # Parse instance ID from output
                output = result.stdout.strip()
                logger.info(f"Instance creation output: {output}")
                
                # Vast.ai CLI typically outputs instance ID or JSON
                parsed_instance_id = None
                try:
                    instance_data = json.loads(output)
                    parsed_instance_id = instance_data.get("id") or instance_data.get("new_contract") or instance_data.get("new_instance")
                    logger.debug(f"Parsed instance ID from JSON: {parsed_instance_id}")
                except json.JSONDecodeError:
                    # Try to extract ID from text output
                    # Could be just a number, or JSON-like text
                    if output:
                        # Try to find numeric ID in output
                        # Look for numeric IDs (could be at start, middle, or end)
                        numbers = re.findall(r'\d+', output)
                        if numbers:
                            # Take the last (likely largest) number as instance ID
                            parsed_instance_id = numbers[-1]
                            logger.debug(f"Extracted instance ID from numbers: {parsed_instance_id}")
                        else:
                            # Fallback to last word/token
                            parsed_instance_id = output.split()[-1] if output else None
                            logger.debug(f"Extracted instance ID from last token: {parsed_instance_id}")
                
                # Clean up instance ID - remove any non-numeric characters
                if parsed_instance_id:
                    # Extract only digits
                    cleaned_id = re.sub(r'\D', '', str(parsed_instance_id))
                    if cleaned_id:
                        parsed_instance_id = cleaned_id
                    else:
                        parsed_instance_id = None
                
                # Wait a moment for instance to appear in API
                time.sleep(2)
                
                # Get instances after creation
                after_instances = get_all_instances()
                after_ids = {str(inst.get("id", "")) for inst in after_instances}
                logger.debug(f"Instances after creation: {list(after_ids)}")
                
                # Verify the parsed instance ID exists
                if parsed_instance_id and parsed_instance_id in after_ids:
                    instance_id = parsed_instance_id
                    logger.info(f"Instance created and verified: {instance_id}")
                else:
                    # Try to find newly created instance by comparing before/after
                    new_id = find_newly_created_instance(before_instances, after_instances)
                    if new_id:
                        instance_id = new_id
                        logger.info(f"Found newly created instance (parsed ID was incorrect): {instance_id}")
                    else:
                        logger.error(f"Failed to verify instance creation. Parsed ID: {parsed_instance_id}")
                        logger.error(f"Output was: {output}")
                        logger.error(f"Before instances: {list(before_ids)}")
                        logger.error(f"After instances: {list(after_ids)}")
                        continue
                
                # Wait for instance to become running
                if wait_for_pod(instance_id, timeout=MAX_POD_WAIT):
                    # Final verification - make sure instance is still visible
                    verified = verify_instance_exists(instance_id)
                    if verified:
                        logger.info(f"Instance {instance_id} is ready and verified in instance list!")
                        return instance_id
                    else:
                        logger.warning(f"Instance {instance_id} became ready but is not visible in instance list. This may indicate an issue.")
                        # Still return it, as it might be a timing issue
                        return instance_id
                else:
                    # Instance failed to start, kill it before trying next pod
                    logger.error(f"Instance {instance_id} failed to start. Killing instance and blacklisting machine {machine_id}")
                    try:
                        # Import here to avoid circular dependency
                        import sys
                        import importlib
                        kill_module = importlib.import_module("utils.utils.kill_vast_ai_instances")
                        kill_module.kill_instance(instance_id)
                        logger.info(f"Killed failed instance {instance_id}")
                    except Exception as e:
                        logger.warning(f"Failed to kill instance {instance_id}: {e}")
                    
                    # Blacklist machine
                    blacklist.add(machine_id)
                    save_blacklist(blacklist)
                    instance_id = None
                    continue
                
            except subprocess.CalledProcessError as e:
                logger.warning(f"Failed to create instance on pod {pod_id}: {e}")
                if 'cmd' in locals():
                    logger.warning(f"Command: {' '.join(cmd)}")
                logger.warning(f"Error output (stderr): {e.stderr}")
                logger.warning(f"Standard output (stdout): {e.stdout}")
                # If subprocess failed, no instance was created, so nothing to clean up
                continue
            except Exception as e:
                logger.error(f"Unexpected error creating instance: {e}")
                # If we have an instance_id but hit an exception, try to kill it
                if instance_id:
                    try:
                        import sys
                        import importlib
                        kill_module = importlib.import_module("utils.utils.kill_vast_ai_instances")
                        kill_module.kill_instance(instance_id)
                        logger.info(f"Killed instance {instance_id} after unexpected error")
                    except Exception as kill_error:
                        logger.warning(f"Failed to kill instance {instance_id} after error: {kill_error}")
                continue
        
        # If we get here, all pods in this batch failed
        logger.warning(f"No pods available in this batch. Retrying in {FIND_POD_SLEEP} seconds...")
        time.sleep(FIND_POD_SLEEP)
    
    logger.error("Failed to create instance within retry time limit")
    return None


if __name__ == "__main__":
    # For testing
    instance_id = create_instance(DEBUG=True)
    if instance_id:
        print(f"Successfully created instance: {instance_id}")
    else:
        print("Failed to create instance")

