#!/usr/bin/env python3
"""
Vast AI Runner for TRL GRPO Training
This script sets up and runs TRL GRPO training on Vast AI instances.
"""

import os
import sys
import subprocess
import json
import time
import logging
from pathlib import Path

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Import Vast AI utilities - try REST API first, fallback to CLI
try:
    from utils.trainer.vast_ai_api import run_trl_training_vast_ai_api
    USE_REST_API = True
except ImportError:
    USE_REST_API = False
    try:
        from utils.utils.vast_ai_train import (
            setup_vastai_cli,
            get_offers,
            create_instance,
            calculate_full_pod_cost,
            wait_for_pod,
            load_blacklist,
            save_blacklist,
            copy_data_to_instance
        )
    except ImportError:
        logger.error("Failed to import Vast AI utilities. Make sure utils/utils/vast_ai_train.py exists.")
        sys.exit(1)


def build_trl_startup_command(
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
    use_wandb=False
):
    """
    Build the startup command for TRL GRPO training on Vast AI.
    
    Returns:
        Multi-line bash script as a single string
    """
    # Set default prices path if not provided
    if prices_path is None:
        prices_path = f"data/prices/{coin}.csv"
    if articles_path == "data/articles.csv":
        articles_path = "data/articles/articles.csv"
    
    # Get environment variables
    env_vars = {
        "MLFLOW_S3_ENDPOINT_URL": os.getenv("MLFLOW_S3_ENDPOINT_URL", ""),
        "MLFLOW_URI": os.getenv("MLFLOW_URI", ""),
        "MLFLOW_TRACKING_USERNAME": os.getenv("MLFLOW_TRACKING_USERNAME", ""),
        "MLFLOW_TRACKING_PASSWORD": os.getenv("MLFLOW_TRACKING_PASSWORD", ""),
        "AWS_ACCESS_KEY_ID": os.getenv("AWS_ACCESS_KEY_ID", ""),
        "AWS_SECRET_ACCESS_KEY": os.getenv("AWS_SECRET_ACCESS_KEY", ""),
    }
    # Build export commands
    export_cmds_list = [
        f'export {key}="{value}"'
        for key, value in env_vars.items()
        if value
    ]
    # Add project root to PYTHONPATH explicitly
    export_cmds_list.append('export PYTHONPATH="/workspace/crypto-ml-training-standalone:$PYTHONPATH"')
    export_cmds = " && ".join(export_cmds_list) if export_cmds_list else ""
    
    # W&B API key (if available)
    wandb_key = os.getenv("WANDB_API_KEY", "")
    wandb_login = f"wandb login {wandb_key}" if wandb_key and use_wandb else "echo 'WANDB_API_KEY not set, skipping wandb login'"
    
    # Build training command arguments
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
    
    # Build complete startup command
    cmd_parts = ["set -e"]
    
    # 0. Self-healing: Ensure basic tools are present (Vast.ai needs ssh/git)
    cmd_parts.append("apt-get update && apt-get install -y git openssh-client openssh-server rsync || echo 'Apt failed, continuing...'")
    
    if export_cmds:
        cmd_parts.append(export_cmds)
    
    cmd_parts.extend([
        "mkdir -p /workspace",
        "cd /workspace",
        f"if [ ! -d crypto-ml-training-standalone ]; then git clone https://github.com/dhayanand-ss/crypto-ml-training-standalone-clean.git crypto-ml-training-standalone; fi",
        "cd crypto-ml-training-standalone",
        "pip install -q --upgrade pip || true",
        "pip install -q -r requirements.txt || echo 'Warning: requirements.txt not found'",
    ])
    
    if use_wandb:
        cmd_parts.append("pip install -q wandb")
        cmd_parts.append(wandb_login)
    
    # Remote download replaced by direct host-to-remote upload
    # cmd_parts.append("python -m utils.utils.pre_train_dataset || echo 'Data download failed'")
    cmd_parts.append(f"python -m utils.trainer.trl_train {train_cmd}")
    
    startup_cmd = " && ".join(cmd_parts)
    
    return startup_cmd


def run_trl_training_on_vast_ai(
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
    Create a Vast AI instance and run TRL GRPO training.
    
    Uses REST API if available (avoids CLI dependency issues), otherwise falls back to CLI.
    
    Args:
        coin: Cryptocurrency pair (default: BTCUSDT)
        articles_path: Path to articles CSV
        prices_path: Path to prices CSV (default: data/{coin}.csv)
        lora_rank: LoRA rank (default: 4)
        epochs: Number of epochs (default: 10)
        batch_size: Batch size (default: 4)
        window_hours: Time window for price change (default: 12)
        threshold: Price change threshold (default: 0.005)
        clip_eps: PPO clipping epsilon (default: 0.2)
        kl_coef: KL divergence coefficient (default: 0.1)
        lr: Learning rate (default: 2e-5)
        use_mlflow: Enable MLflow logging (default: False)
        use_wandb: Enable W&B logging (default: False)
        budget: Maximum cost per hour in USD (default: 0.25)
        max_wait_time: Maximum time to wait for instance in seconds (default: 600)
    
    Returns:
        Instance ID if successful, None otherwise
    """
    logger.info("=" * 60)
    logger.info("Starting TRL GRPO Training on Vast AI")
    logger.info("=" * 60)
    
    # Try REST API first (avoids CLI dependency issues)
    api_key = os.getenv("VASTAI_API_KEY")
    if USE_REST_API and api_key:
        logger.info("Using Vast AI REST API (bypasses CLI dependency)")
        return run_trl_training_vast_ai_api(
            api_key=api_key,
            coin=coin,
            articles_path=articles_path,
            prices_path=prices_path,
            lora_rank=lora_rank,
            epochs=epochs,
            batch_size=batch_size,
            window_hours=window_hours,
            threshold=threshold,
            clip_eps=clip_eps,
            kl_coef=kl_coef,
            lr=lr,
            use_mlflow=use_mlflow,
            use_wandb=use_wandb,
            budget=budget,
            max_wait_time=max_wait_time
        )
    
    # Fallback to CLI
    logger.info("Using Vast AI CLI")
    try:
        setup_vastai_cli()
    except Exception as e:
        logger.error(f"Failed to setup Vast AI CLI: {e}")
        logger.error("Try setting VASTAI_API_KEY environment variable to use REST API")
        return None
    
    # Build startup command
    startup_cmd = build_trl_startup_command(
        coin=coin,
        articles_path=articles_path,
        prices_path=prices_path,
        lora_rank=lora_rank,
        epochs=epochs,
        batch_size=batch_size,
        window_hours=window_hours,
        threshold=threshold,
        clip_eps=clip_eps,
        kl_coef=kl_coef,
        lr=lr,
        use_mlflow=use_mlflow,
        use_wandb=use_wandb
    )
    
    logger.info("Startup command prepared")
    logger.debug(f"Startup command: {startup_cmd[:200]}...")
    
    # Get available offers
    offers = get_offers()
    if not offers:
        logger.error("No GPU offers available")
        return None
    
    # Filter by budget
    blacklist = load_blacklist()
    filtered_offers = [
        pod for pod in offers
        if calculate_full_pod_cost(pod) <= budget
        and pod.get("machine_id") not in blacklist
    ]
    
    if not filtered_offers:
        logger.error(f"No offers within budget (${budget}/hr) or all blacklisted")
        return None
    
    # Sort by cost (cheapest first)
    filtered_offers.sort(key=lambda p: calculate_full_pod_cost(p))
    
    # Try to create instance
    for pod in filtered_offers:
        pod_id = pod.get("id")
        machine_id = pod.get("machine_id")
        cost = calculate_full_pod_cost(pod)
        
        logger.info(f"Attempting to create instance on pod {pod_id} (machine {machine_id})")
        logger.info(f"Estimated cost: ${cost:.4f}/hour")
        
        try:
            # Create instance
            image_to_use = os.getenv("VASTAI_DOCKER_IMAGE", "pytorch/pytorch:latest")
            logger.info(f"Using Docker image: {image_to_use}")
            
            cmd = [
                "vastai", "create", "instance", str(pod_id),
                "--image", image_to_use,  # Use custom image if set
                "--onstart", startup_cmd,
                "--disk", "30",
                "--ssh",
                "--on-demand"
            ]
            
            result = subprocess.run(
                cmd,
                check=True,
                capture_output=True,
                text=True
            )
            
            # Parse instance ID
            output = result.stdout.strip()
            try:
                instance_data = json.loads(output)
                instance_id = instance_data.get("id") or instance_data.get("new_contract")
            except json.JSONDecodeError:
                instance_id = output.split()[-1] if output else None
            
            if not instance_id:
                logger.error(f"Failed to parse instance ID from output: {output}")
                continue
            
            logger.info(f"Instance created: {instance_id}")
            
            # Wait for instance to become running
            if wait_for_pod(instance_id, timeout=max_wait_time):
                logger.info(f"Instance {instance_id} is ready!")
                
                # Direct Data Upload Step
                copy_data_to_instance(instance_id)
                
                logger.info(f"You can SSH into the instance to monitor training progress")
                logger.info(f"Instance will run the training command automatically")
                return instance_id
            else:
                logger.error(f"Instance {instance_id} failed to start. Blacklisting machine {machine_id}")
                blacklist.add(machine_id)
                save_blacklist(blacklist)
                continue
                
        except subprocess.CalledProcessError as e:
            logger.warning(f"Failed to create instance on pod {pod_id}: {e}")
            logger.debug(f"Error output: {e.stderr}")
            continue
        except Exception as e:
            logger.error(f"Unexpected error creating instance: {e}")
            continue
    
    logger.error("Failed to create instance")
    return None


def main():
    """Main function for command-line usage"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Run TRL GRPO training on Vast AI",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    # Training parameters
    parser.add_argument("--coin", type=str, default="BTCUSDT",
                       help="Cryptocurrency pair (default: BTCUSDT)")
    parser.add_argument("--articles_path", type=str, default="data/articles.csv",
                       help="Path to articles CSV (default: data/articles.csv)")
    parser.add_argument("--prices_path", type=str, default=None,
                       help="Path to prices CSV (default: data/{coin}.csv)")
    parser.add_argument("--lora_rank", type=int, default=4,
                       help="LoRA rank (default: 4)")
    parser.add_argument("--epochs", type=int, default=10,
                       help="Number of epochs (default: 10)")
    parser.add_argument("--batch_size", type=int, default=4,
                       help="Batch size (default: 4)")
    parser.add_argument("--window_hours", type=int, default=12,
                       help="Time window for price change (default: 12)")
    parser.add_argument("--threshold", type=float, default=0.005,
                       help="Price change threshold (default: 0.005)")
    parser.add_argument("--clip_eps", type=float, default=0.2,
                       help="PPO clipping epsilon (default: 0.2)")
    parser.add_argument("--kl_coef", type=float, default=0.1,
                       help="KL divergence coefficient (default: 0.1)")
    parser.add_argument("--lr", type=float, default=2e-5,
                       help="Learning rate (default: 2e-5)")
    
    # Logging
    parser.add_argument("--use_mlflow", action="store_true",
                       help="Enable MLflow logging")
    parser.add_argument("--use_wandb", action="store_true",
                       help="Enable W&B logging")
    
    # Vast AI parameters
    parser.add_argument("--budget", type=float, default=0.25,
                       help="Maximum cost per hour in USD (default: 0.25)")
    parser.add_argument("--max_wait_time", type=int, default=600,
                       help="Maximum wait time for instance in seconds (default: 600)")
    
    args = parser.parse_args()
    
    # Run training
    instance_id = run_trl_training_on_vast_ai(
        coin=args.coin,
        articles_path=args.articles_path,
        prices_path=args.prices_path,
        lora_rank=args.lora_rank,
        epochs=args.epochs,
        batch_size=args.batch_size,
        window_hours=args.window_hours,
        threshold=args.threshold,
        clip_eps=args.clip_eps,
        kl_coef=args.kl_coef,
        lr=args.lr,
        use_mlflow=args.use_mlflow,
        use_wandb=args.use_wandb,
        budget=args.budget,
        max_wait_time=args.max_wait_time
    )
    
    if instance_id:
        print(f"\n[SUCCESS] Successfully created Vast AI instance: {instance_id}")
        print(f"Training is running on the instance.")
        print(f"Use 'vastai show instance {instance_id}' to check status")
    else:
        print("\n[ERROR] Failed to create Vast AI instance")
        sys.exit(1)


if __name__ == "__main__":
    main()

