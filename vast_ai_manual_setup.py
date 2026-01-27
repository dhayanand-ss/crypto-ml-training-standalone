#!/usr/bin/env python3
"""
Generate Vast AI setup commands for manual execution
Since the REST API has authentication issues, this generates commands
that can be run manually via Vast AI CLI or web interface
"""

import os

def generate_vast_ai_commands():
    """Generate commands for manual Vast AI setup"""
    
    api_key = os.getenv("VASTAI_API_KEY", "YOUR_API_KEY_HERE")
    
    print("=" * 60)
    print("Vast AI Manual Setup Commands")
    print("=" * 60)
    print()
    print("Since the REST API has authentication issues, use these commands:")
    print()
    print("OPTION 1: Using Vast AI CLI (Recommended)")
    print("-" * 60)
    print("1. Install Vast AI CLI in Python 3.10/3.11 environment:")
    print("   py -3.10 -m venv venv_vastai")
    print("   venv_vastai\\Scripts\\activate")
    print("   pip install vastai")
    print()
    print("2. Set API key:")
    print(f"   vastai set api-key {api_key}")
    print()
    print("3. Search for GPU offers:")
    print("   vastai search offers 'gpu_total_ram>=11 disk_space>=30 verified=True datacenter=True' --raw")
    print()
    print("4. Create instance (replace OFFER_ID with actual ID from step 3):")
    print("   vastai create instance OFFER_ID \\")
    print("     --image pytorch/pytorch:latest \\")
    print("     --disk 30 \\")
    print("     --ssh \\")
    print("     --on-demand \\")
    print("     --onstart 'set -e && cd /workspace && [ ! -d crypto-ml-training-standalone ] && git clone https://github.com/dhayanand-ss/crypto-ml-training-standalone-clean.git crypto-ml-training-standalone || true && cd crypto-ml-training-standalone && pip install -q -r requirements.txt && python -m utils.trainer.trl_train --coin BTCUSDT --epochs 10 --batch_size 4 --lora_rank 4 --window_hours 12 --threshold 0.005 --clip_eps 0.2 --kl_coef 0.1 --lr 2e-5'")
    print()
    print("5. Monitor instance:")
    print("   vastai show instance INSTANCE_ID")
    print("   vastai ssh INSTANCE_ID")
    print()
    print("OPTION 2: Using Vast AI Web Interface")
    print("-" * 60)
    print("1. Go to: https://console.vast.ai/")
    print("2. Click 'Create' to create a new instance")
    print("3. Select a GPU instance within your budget ($0.25/hour)")
    print("4. Use image: pytorch/pytorch:latest")
    print("5. Set disk: 30 GB")
    print("6. In 'On Start' command, paste:")
    print()
    onstart_cmd = """set -e && cd /workspace && [ ! -d crypto-ml-training-standalone ] && git clone https://github.com/dhayanand-ss/crypto-ml-training-standalone-clean.git crypto-ml-training-standalone || true && cd crypto-ml-training-standalone && pip install -q -r requirements.txt && python -m utils.trainer.trl_train --coin BTCUSDT --epochs 10 --batch_size 4 --lora_rank 4 --window_hours 12 --threshold 0.005 --clip_eps 0.2 --kl_coef 0.1 --lr 2e-5"""
    print(f"   {onstart_cmd}")
    print()
    print("7. Click 'Create' and wait for instance to start")
    print("8. SSH into instance to monitor training")
    print()
    print("OPTION 3: Alternative - Use Vast AI Python SDK")
    print("-" * 60)
    print("If available, install: pip install vast-ai")
    print("Then use the SDK to create instances programmatically")
    print()
    print("=" * 60)
    print("Training Configuration:")
    print("=" * 60)
    print("  Coin: BTCUSDT")
    print("  Epochs: 10")
    print("  Batch Size: 4")
    print("  LoRA Rank: 4")
    print("  Window Hours: 12")
    print("  Threshold: 0.005")
    print("  Clip Epsilon: 0.2")
    print("  KL Coefficient: 0.1")
    print("  Learning Rate: 2e-5")
    print("=" * 60)

if __name__ == "__main__":
    generate_vast_ai_commands()




