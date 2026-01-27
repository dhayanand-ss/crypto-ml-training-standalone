#!/usr/bin/env python3
"""
Simple script to run TRL GRPO training on Vast AI.
This is a convenience wrapper around the Vast AI training script.
"""

import os
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from utils.trainer.vast_ai_trl_train import run_trl_training_on_vast_ai


def main():
    """Run TRL GRPO training on Vast AI with default parameters"""
    
    print("=" * 60)
    print("TRL GRPO Training on Vast AI")
    print("=" * 60)
    print()
    print("This script will:")
    print("1. Find an available GPU instance on Vast AI")
    print("2. Create an instance with the training environment")
    print("3. Run TRL GRPO training automatically")
    print()
    print("Make sure you have:")
    print("- VASTAI_API_KEY environment variable set")
    print("- Data files available (articles.csv and btcusdt.csv)")
    print()
    
    # Check for API key
    if not os.getenv("VASTAI_API_KEY"):
        print("ERROR: VASTAI_API_KEY environment variable not set!")
        print("Please set it with: export VASTAI_API_KEY=your_key")
        sys.exit(1)
    
    # Default parameters (can be customized)
    coin = os.getenv("TRL_COIN", "BTCUSDT")
    articles_path = os.getenv("TRL_ARTICLES_PATH", "data/articles.csv")
    prices_path = os.getenv("TRL_PRICES_PATH", None)  # Will default to data/{coin}.csv
    
    # Training parameters
    lora_rank = int(os.getenv("TRL_LORA_RANK", "4"))
    epochs = int(os.getenv("TRL_EPOCHS", "10"))
    batch_size = int(os.getenv("TRL_BATCH_SIZE", "4"))
    window_hours = int(os.getenv("TRL_WINDOW_HOURS", "12"))
    threshold = float(os.getenv("TRL_THRESHOLD", "0.005"))
    clip_eps = float(os.getenv("TRL_CLIP_EPS", "0.2"))
    kl_coef = float(os.getenv("TRL_KL_COEF", "0.1"))
    lr = float(os.getenv("TRL_LR", "2e-5"))
    
    # Logging
    use_mlflow = os.getenv("TRL_USE_MLFLOW", "false").lower() == "true"
    use_wandb = os.getenv("TRL_USE_WANDB", "false").lower() == "true"
    
    # Vast AI parameters
    budget = float(os.getenv("VASTAI_BUDGET", "0.25"))
    max_wait_time = int(os.getenv("VASTAI_MAX_WAIT", "600"))
    
    print(f"Training Parameters:")
    print(f"  Coin: {coin}")
    print(f"  Articles: {articles_path}")
    print(f"  Prices: {prices_path or f'data/{coin.lower()}.csv'}")
    print(f"  LoRA Rank: {lora_rank}")
    print(f"  Epochs: {epochs}")
    print(f"  Batch Size: {batch_size}")
    print(f"  Window Hours: {window_hours}")
    print(f"  Threshold: {threshold}")
    print(f"  Clip Epsilon: {clip_eps}")
    print(f"  KL Coefficient: {kl_coef}")
    print(f"  Learning Rate: {lr}")
    print(f"  Use MLflow: {use_mlflow}")
    print(f"  Use WandB: {use_wandb}")
    print(f"  Budget: ${budget}/hour")
    print()
    
    # Confirm before proceeding
    response = input("Proceed with training? (y/n): ")
    if response.lower() != 'y':
        print("Cancelled.")
        sys.exit(0)
    
    # Run training
    print("\nCreating Vast AI instance and starting training...")
    instance_id = run_trl_training_on_vast_ai(
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
    
    if instance_id:
        print("\n" + "=" * 60)
        print("SUCCESS! Training instance created.")
        print("=" * 60)
        print(f"Instance ID: {instance_id}")
        print(f"\nTo monitor training:")
        print(f"  vastai show instance {instance_id}")
        print(f"\nTo SSH into the instance:")
        print(f"  vastai ssh {instance_id}")
        print(f"\nTo stop the instance:")
        print(f"  vastai destroy instance {instance_id}")
        print("=" * 60)
    else:
        print("\n" + "=" * 60)
        print("FAILED to create training instance.")
        print("=" * 60)
        print("Please check:")
        print("1. VASTAI_API_KEY is set correctly")
        print("2. You have sufficient credits on Vast AI")
        print("3. There are available GPU instances")
        print("=" * 60)
        sys.exit(1)


if __name__ == "__main__":
    main()

















