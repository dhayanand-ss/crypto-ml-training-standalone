#!/usr/bin/env python3
"""
Direct script to run TRL GRPO training on Vast AI
Uses REST API to bypass CLI dependency
"""

import os
import sys
import logging
from pathlib import Path

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

def main():
    """Run TRL training on Vast AI"""
    
    # Get API key
    api_key = os.getenv("VASTAI_API_KEY")
    if not api_key:
        logger.error("VASTAI_API_KEY environment variable not set!")
        logger.info("Set it with: export VASTAI_API_KEY=your_key")
        sys.exit(1)
    
    logger.info("=" * 60)
    logger.info("TRL GRPO Training on Vast AI")
    logger.info("=" * 60)
    
    # Import the training function
    try:
        from utils.trainer.vast_ai_api import run_trl_training_vast_ai_api
    except ImportError as e:
        logger.error(f"Failed to import Vast AI API client: {e}")
        sys.exit(1)
    
    # Training parameters
    logger.info("Training Configuration:")
    logger.info("  Coin: BTCUSDT")
    logger.info("  Epochs: 10")
    logger.info("  Batch Size: 4")
    logger.info("  LoRA Rank: 4")
    logger.info("  Budget: $0.25/hour")
    logger.info("")
    
    # Run training
    instance_id = run_trl_training_vast_ai_api(
        api_key=api_key,
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
    )
    
    if instance_id:
        logger.info("")
        logger.info("=" * 60)
        logger.info("SUCCESS! Training instance created on Vast AI")
        logger.info("=" * 60)
        logger.info(f"Instance ID: {instance_id}")
        logger.info("")
        logger.info("To monitor training:")
        logger.info(f"  Visit: https://console.vast.ai/instances/{instance_id}")
        logger.info("")
        logger.info("To SSH into the instance (if CLI is available):")
        logger.info(f"  vastai ssh {instance_id}")
        logger.info("")
        logger.info("The training will run automatically on the instance.")
        logger.info("Check the instance logs to see training progress.")
        logger.info("=" * 60)
    else:
        logger.error("")
        logger.error("=" * 60)
        logger.error("FAILED to create training instance")
        logger.error("=" * 60)
        logger.error("Possible reasons:")
        logger.error("1. API key is invalid")
        logger.error("2. No GPU offers available within budget")
        logger.error("3. API endpoint issues (check Vast AI status)")
        logger.error("4. Network connectivity issues")
        logger.error("")
        logger.error("Try:")
        logger.error("1. Verify your API key at https://console.vast.ai/")
        logger.error("2. Check Vast AI service status")
        logger.error("3. Increase budget if needed")
        logger.error("=" * 60)
        sys.exit(1)

if __name__ == "__main__":
    main()

















