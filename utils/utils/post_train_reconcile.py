
import os
import sys
import subprocess
import argparse
import logging
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from utils.database.status_db import status_db
from utils.utils.vast_ai_train import setup_vastai_cli

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def main():
    parser = argparse.ArgumentParser(description="Retrieve trained LGBM or TST models from Vast.ai")
    parser.add_argument("--crypto", type=str, required=True, help="Crypto pair (e.g., BTCUSDT)")
    parser.add_argument("--instance_id", type=str, help="Vast.ai instance ID (manual override)")
    args = parser.parse_args()
    
    logger.info(f"Starting post-training model retrieval for {args.crypto} {args.model}...")
    
    # Setup Vast.ai CLI
    try:
        setup_vastai_cli()
    except Exception as e:
        logger.error(f"Failed to setup Vast.ai CLI: {e}")
        sys.exit(1)
        
    # Get Airflow context
    run_id = os.getenv("AIRFLOW_CTX_DAG_RUN_ID")
    dag_id = os.getenv("AIRFLOW_CTX_DAG_ID")
    
    if not run_id and not args.instance_id:
        run_id = os.getenv("AIRFLOW_RUN_ID")
        dag_id = os.getenv("AIRFLOW_DAG_ID")
        
    if not run_id and not args.instance_id:
        logger.error("Neither AIRFLOW_CTX_DAG_RUN_ID nor --instance_id provided")
        sys.exit(1)
        
    if run_id:
        logger.info(f"Looking up status for DAG: {dag_id}, Run: {run_id}")
    
    # Get instance ID from DB
    try:
        instance_id = args.instance_id
        
        if not instance_id:
            status_list = status_db.get_status(dag_id, run_id)
            
            # Look for the specific model status
            model_name = f"{args.crypto}_{args.model}"
            model_status = next((item for item in status_list if item.get('model_name') == model_name), None)
            
            if model_status:
                metadata = model_status.get('metadata', {})
                instance_id = metadata.get('instance_id')
            
        if not instance_id:
            logger.info("Checking for 'vast_ai_train' task metadata as fallback...")
            vast_train_status = next((item for item in status_list if item.get('task_name') == 'vast_ai_train'), None)
            if vast_train_status:
                instance_id = vast_train_status.get('metadata', {}).get('instance_id')

        if not instance_id:
            logger.warning("Instance ID not found in status snapshot metadata. Checking event logs...")
            events = status_db.get_events(dag_id, run_id, limit=100)
            for event in events:
                if event.get('event_type') == 'INSTANCE_CREATED' and event.get('metadata'):
                    instance_id = event['metadata'].get('instance_id')
                    if instance_id:
                        logger.info(f"Found instance ID from event logs: {instance_id}")
                        break
                        
        if not instance_id:
            logger.error(f"Could not find instance ID for run {run_id}. Model cannot be retrieved.")
            sys.exit(1)
            
        logger.info(f"Retrieving {args.model} model from instance {instance_id}")
        
        # Local base path
        local_base = project_root / "models" / args.model
        local_base.mkdir(parents=True, exist_ok=True)
        
        # Determine remote path based on VASTAI_GITHUB_REPO
        github_repo = os.getenv("VASTAI_GITHUB_REPO", "")
        if github_repo:
            repo_name = github_repo.split("/")[-1].replace(".git", "")
        else:
            repo_name = "crypto-ml-training"
            
        # TST and LGBM use v3 for the latest results
        remote_path = f"/workspace/{repo_name}/models/{args.model}/v3"
        local_target = str(local_base) 
        
        cmd = ["vastai", "copy", f"{instance_id}:{remote_path}", local_target]
        
        logger.info(f"Running: {' '.join(cmd)}")
        subprocess.run(cmd, check=True)
        
        logger.info(f"Model {args.model} v3 retrieved successfully!")
        
    except Exception as e:
        logger.error(f"Error retrieving model: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
