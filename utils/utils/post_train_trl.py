
import os
import sys
import subprocess
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
    logger.info("Starting post-training TRL model retrieval...")
    
    # Setup Vast.ai CLI
    try:
        setup_vastai_cli()
    except Exception as e:
        logger.error(f"Failed to setup Vast.ai CLI: {e}")
        sys.exit(1)
        
    # Get Airflow context
    run_id = os.getenv("AIRFLOW_CTX_DAG_RUN_ID")
    dag_id = os.getenv("AIRFLOW_CTX_DAG_ID")
    
    if not run_id or not dag_id:
        # Fallback for manual testing
        run_id = os.getenv("AIRFLOW_RUN_ID")
        dag_id = os.getenv("AIRFLOW_DAG_ID")
        
    if not run_id:
        logger.error("AIRFLOW_CTX_DAG_RUN_ID not set")
        sys.exit(1)
        
    logger.info(f"Looking up status for DAG: {dag_id}, Run: {run_id}")
    
    # Get status from DB
    try:
        # We look for the 'vast_ai_train' task which created the instance
        # Or better, we look for the 'trl' model status which we updated in trl_train.py
        # vast_ai_train.py logs instance_creation for model 'trl' (as per my update)
        
        # Method 1: Check status snapshot
        status_list = status_db.get_status(dag_id, run_id)
        
        trl_status = next((item for item in status_list if item.get('model_name') == 'trl'), None)
        
        instance_id = None
        if trl_status:
            metadata = trl_status.get('metadata', {})
            instance_id = metadata.get('instance_id')
            
        if not instance_id:
            logger.warning("Instance ID not found in status snapshot metadata. Checking event logs...")
            # Method 2: Check event logs directly for INSTANCE_CREATED event
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
            
        logger.info(f"Retrieving model from instance {instance_id}")
        
        # Define paths
        # Remote path: /workspace/crypto-ml-training-standalone/models/finbert
        # Local path: ./models/finbert
        
        local_base = project_root / "models"
        local_base.mkdir(parents=True, exist_ok=True)
        
        # We target the parent 'models' folder because 'finbert' is the folder name inside
        remote_path = "/workspace/crypto-ml-training-standalone/models/finbert"
        local_target = str(local_base) 
        
        # 'vastai copy' syntax: src dst
        # If dst is a directory, it puts the src basename inside it
        
        cmd = ["vastai", "copy", f"{instance_id}:{remote_path}", local_target]
        
        logger.info(f"Running: {' '.join(cmd)}")
        subprocess.run(cmd, check=True)
        
        logger.info("Model retrieved successfully!")
        
    except Exception as e:
        logger.error(f"Error retrieving model: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
