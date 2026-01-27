"""
Vast AI REST API Client for TRL Training
Direct API implementation to avoid CLI dependency issues
"""

import os
import json
import time
import requests
import logging
from typing import Optional, Dict, List

logger = logging.getLogger(__name__)

VAST_AI_API_BASE = "https://console.vast.ai/api/v0"
# Alternative: Some endpoints might use different base
VAST_AI_ALT_BASE = "https://vast.ai/api/v0"


class VastAIClient:
    """Direct Vast AI API client using REST API"""
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        # Try different authentication formats
        self.headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {api_key}",
            # Alternative formats
            "X-API-Key": api_key,
        }
        # Also try with just the API key as a query parameter
        self.api_key_param = api_key
    
    def search_offers(self, query: str = "gpu_total_ram>=11 disk_space>=30 verified=True datacenter=True") -> List[Dict]:
        """Search for available GPU offers"""
        # Try different API endpoints
        endpoints = [
            f"{VAST_AI_API_BASE}/bundles",
            f"{VAST_AI_ALT_BASE}/bundles",
            f"{VAST_AI_API_BASE}/offers",
        ]
        
        params = {
            "q": query,
            "type": "on-demand"
        }
        
        for url in endpoints:
            try:
                response = requests.get(url, headers=self.headers, params=params, timeout=30)
                response.raise_for_status()
                offers = response.json()
                if isinstance(offers, dict):
                    if "offers" in offers:
                        return offers["offers"]
                    if "bundles" in offers:
                        return offers["bundles"]
                if isinstance(offers, list):
                    return offers
                logger.warning(f"Unexpected response format from {url}: {type(offers)}")
            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 404:
                    continue  # Try next endpoint
                logger.warning(f"HTTP {e.response.status_code} from {url}: {e}")
            except Exception as e:
                logger.warning(f"Failed to search offers from {url}: {e}")
                continue
        
        logger.error("All API endpoints failed for searching offers")
        return []
    
    def create_instance(self, offer_id: int, image: str, onstart: str, disk: int = 30) -> Optional[Dict]:
        """Create a Vast AI instance"""
        # Try different API endpoints and methods
        endpoints = [
            (f"{VAST_AI_API_BASE}/asks/{offer_id}/", "PUT"),
            (f"{VAST_AI_ALT_BASE}/asks/{offer_id}/", "PUT"),
            (f"{VAST_AI_API_BASE}/bundles/{offer_id}/", "PUT"),
            (f"{VAST_AI_API_BASE}/offers/{offer_id}/", "PUT"),
        ]
        
        data = {
            "client_id": "me",
            "image": image,
            "onstart": onstart,
            "disk": disk,
            "ssh": True
        }
        
        for url, method in endpoints:
            try:
                if method == "PUT":
                    response = requests.put(url, headers=self.headers, json=data, timeout=60)
                else:
                    response = requests.post(url, headers=self.headers, json=data, timeout=60)
                
                response.raise_for_status()
                result = response.json()
                logger.info(f"Successfully created instance using {url}")
                return result
            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 404:
                    continue  # Try next endpoint
                logger.warning(f"HTTP {e.response.status_code} from {url}: {e.response.text[:200]}")
            except Exception as e:
                logger.warning(f"Failed to create instance from {url}: {e}")
                continue
        
        logger.error("All API endpoints failed for creating instance")
        return None
    
    def get_instance(self, instance_id: str) -> Optional[Dict]:
        """Get instance status"""
        url = f"{VAST_AI_API_BASE}/instances/{instance_id}/"
        
        try:
            response = requests.get(url, headers=self.headers, timeout=30)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Failed to get instance: {e}")
            return None
    
    def wait_for_instance(self, instance_id: str, timeout: int = 600) -> bool:
        """Wait for instance to become running"""
        start_time = time.time()
        logger.info(f"Waiting for instance {instance_id} to become running...")
        
        while time.time() - start_time < timeout:
            instance = self.get_instance(instance_id)
            if instance:
                status = instance.get("actual_status", "").lower()
                if status == "running":
                    logger.info(f"Instance {instance_id} is now running")
                    return True
                elif status in ["failed", "stopped", "terminated"]:
                    logger.error(f"Instance {instance_id} failed with status: {status}")
                    return False
            
            time.sleep(10)
        
        logger.error(f"Timeout waiting for instance {instance_id}")
        return False


def run_trl_training_vast_ai_api(
    api_key: str,
    coin="BTCUSDT",
    articles_path="data/articles.csv",
    prices_path=None,
    lora_rank=4,
    epochs=10,
    batch_size=4,
    window_hours=12,
    threshold=0.005,
    clip_eps=0.2,
    kl_coef=0.1,
    lr=2e-5,
    use_mlflow=False,
    use_wandb=False,
    budget=0.25,
    max_wait_time=600
):
    """
    Create Vast AI instance using REST API (bypasses CLI dependency)
    """
    logger.info("=" * 60)
    logger.info("Starting TRL GRPO Training on Vast AI (REST API)")
    logger.info("=" * 60)
    
    # Initialize client
    client = VastAIClient(api_key)
    
    # Build startup command
    if prices_path is None:
        prices_path = f"data/{coin.lower()}.csv"
    
    # Build training command
    train_args = [
        f"--coin {coin}",
        f"--articles_path {articles_path}",
        f"--prices_path {prices_path}",
        f"--lora_rank {lora_rank}",
        f"--epochs {epochs}",
        f"--batch_size {batch_size}",
        f"--window_hours {window_hours}",
        f"--threshold {threshold}",
        f"--clip_eps {clip_eps}",
        f"--kl_coef {kl_coef}",
        f"--lr {lr}",
    ]
    
    if use_mlflow:
        train_args.append("--use_mlflow")
    if use_wandb:
        train_args.append("--use_wandb")
    
    train_cmd = " ".join(train_args)
    
    # Build startup script
    env_vars = {
        "MLFLOW_S3_ENDPOINT_URL": os.getenv("MLFLOW_S3_ENDPOINT_URL", ""),
        "MLFLOW_URI": os.getenv("MLFLOW_URI", ""),
        "MLFLOW_TRACKING_USERNAME": os.getenv("MLFLOW_TRACKING_USERNAME", ""),
        "MLFLOW_TRACKING_PASSWORD": os.getenv("MLFLOW_TRACKING_PASSWORD", ""),
        "AWS_ACCESS_KEY_ID": os.getenv("AWS_ACCESS_KEY_ID", ""),
        "AWS_SECRET_ACCESS_KEY": os.getenv("AWS_SECRET_ACCESS_KEY", ""),
    }
    
    export_cmds = " && ".join([
        f'export {k}="{v}"' for k, v in env_vars.items() if v
    ])
    
    wandb_key = os.getenv("WANDB_API_KEY", "")
    wandb_login = f"wandb login {wandb_key}" if wandb_key and use_wandb else "echo 'WANDB_API_KEY not set'"
    
    startup_cmd_parts = ["set -e"]
    if export_cmds:
        startup_cmd_parts.append(export_cmds)
    
    startup_cmd_parts.extend([
        "cd /workspace",
        "[ ! -d crypto-ml-training-standalone ] && git clone https://github.com/dhayanand-ss/crypto-ml-training-standalone-clean.git crypto-ml-training-standalone || true",
        "cd crypto-ml-training-standalone",
        "pip install -q -r requirements.txt",
    ])
    
    if use_wandb:
        startup_cmd_parts.append("pip install -q wandb")
        startup_cmd_parts.append(wandb_login)
    
    startup_cmd_parts.append(f"python -m utils.trainer.trl_train {train_cmd}")
    
    onstart_cmd = " && ".join(startup_cmd_parts)
    
    # Search for offers
    logger.info("Searching for available GPU offers...")
    offers = client.search_offers()
    
    if not offers:
        logger.error("No GPU offers available")
        return None
    
    logger.info(f"Found {len(offers)} available offers")
    
    # Filter by budget (simple check - dph_total)
    filtered_offers = [
        o for o in offers 
        if o.get("dph_total", float('inf')) <= budget
    ]
    
    if not filtered_offers:
        logger.error(f"No offers within budget (${budget}/hr)")
        return None
    
    # Sort by cost
    filtered_offers.sort(key=lambda x: x.get("dph_total", float('inf')))
    
    # Try to create instance
    for offer in filtered_offers[:5]:  # Try top 5 cheapest
        offer_id = offer.get("id")
        cost = offer.get("dph_total", 0)
        
        logger.info(f"Attempting to create instance on offer {offer_id} (${cost:.4f}/hr)")
        
        instance_data = client.create_instance(
            offer_id=offer_id,
            image="pytorch/pytorch:latest",
            onstart=onstart_cmd,
            disk=30
        )
        
        if instance_data:
            instance_id = instance_data.get("new_contract") or instance_data.get("id")
            if instance_id:
                logger.info(f"Instance created: {instance_id}")
                
                if client.wait_for_instance(instance_id, timeout=max_wait_time):
                    logger.info(f"Instance {instance_id} is ready!")
                    return instance_id
                else:
                    logger.warning(f"Instance {instance_id} failed to start")
                    continue
        
        logger.warning(f"Failed to create instance on offer {offer_id}")
    
    logger.error("Failed to create instance")
    return None

