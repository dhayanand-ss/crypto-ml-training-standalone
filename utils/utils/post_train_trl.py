#!/usr/bin/env python3
"""
Post-Training TRL Reconciliation Script
Handles post-training tasks for TRL (FinBERT) models:
1. Reconciles with ModelVersionManager
2. Registers models to MLflow
3. Updates pipeline status
"""

import os
import sys
import argparse
import logging
from pathlib import Path
import shutil
import joblib
import pandas as pd

# Add project root to path
project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Suppress excessive logging
logging.getLogger("utils.artifact_control.gcs_manager").setLevel(logging.CRITICAL)

try:
    import mlflow
except ImportError:
    logger.warning("MLflow not installed. Registration will fail.")

# Import project utilities
try:
    from utils.database.airflow_db import db
    STATUS_DB_AVAILABLE = True
except ImportError:
    STATUS_DB_AVAILABLE = False
    logger.warning("airflow_db not available. Status updates will be skipped.")

from utils.model_version_manager import ModelVersionManager

def register_trl_to_mlflow(version, model_path):
    """Register TRL model to MLflow"""
    
    if not os.path.exists(model_path):
        logger.error(f"TRL model path does not exist: {model_path}")
        return False
        
    try:
        # Load logic - TRL models are usually just a folder passed to transformers or a .pth
        # For MLflow registration, we can log the artifact folder or file
        
        mlflow.set_experiment("crypto-ml-pipeline")
        
        with mlflow.start_run(run_name=f"trl_{version}_reconcile"):
            model_name = "finbert_rl"
            
            # Log artifacts
            # If path is a file, log it. If dir, log artifacts.
            # TRL script saves as .pth but `ModelVersionManager` might point to it
            path_obj = Path(model_path)
            
            if path_obj.is_file():
                mlflow.log_artifact(str(path_obj), artifact_path=model_name)
                # Also look for tokenizer in sibling dir
                tokenizer_dir = path_obj.parent / "tokenizer"
                if tokenizer_dir.exists():
                    mlflow.log_artifacts(str(tokenizer_dir), artifact_path=f"{model_name}/tokenizer")
            elif path_obj.is_dir():
                mlflow.log_artifacts(str(path_obj), artifact_path=model_name)
            
            # Register
            run_id = mlflow.active_run().info.run_id
            model_uri = f"runs:/{run_id}/{model_name}"
            
            client = mlflow.tracking.MlflowClient()
            
            # TRL models often don't support ONNX easily due to custom architecture/environment
            # So we skip ONNX conversion here unless strictly required
            
            registered_model = mlflow.register_model(model_uri=model_uri, name=model_name)
            logger.info(f"Registered {model_name} version {registered_model.version}")
            
            # Set to Production
            client.transition_model_version_stage(
                name=model_name,
                version=registered_model.version,
                stage="Production"
            )
            logger.info(f"Transitioned {model_name} v{registered_model.version} to Production")
            
        return True
    
    except Exception as e:
        logger.error(f"TRL registration failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    logger.info("Starting TRL reconciliation...")
    
    # 0. Sync models from GCS
    try:
        from utils.utils.gcs_sync import download_models_from_gcs
        download_models_from_gcs(project_root)
    except Exception as e:
        logger.warning(f"Model sync failed: {e}")
    
    # 1. Get Latest Version from Manager
    manager = ModelVersionManager()
    
    # TRL script (trl_train.py) uses 'finbert' as model type usually
    # Check registry
    v3_info = manager.registry.get("finbert", {}).get("v3")
    
    success = False
    error_msg = None
    
    if v3_info and v3_info.get("path"):
        v3_path = v3_info["path"]
        logger.info(f"Found v3 TRL model at {v3_path}")
        
        if register_trl_to_mlflow("v3", v3_path):
            success = True
        else:
            error_msg = "Failed to register TRL model to MLflow"
    else:
        error_msg = "No TRL v3 model found in registry"
        logger.error(error_msg)
        
    # 2. Update Status DB
    if STATUS_DB_AVAILABLE:
        try:
            current_state = "SUCCESS" if success else "FAILED"
            # TRL uses 'trl' as model name and 'ALL' as coin often, but DAG passes nothing
            # DAG calls: python -m utils.utils.post_train_trl
            # We assume model='trl', coin='ALL'
            db.set_state(
                model="trl", 
                coin="ALL", 
                state=current_state,
                error_message=error_msg if not success else None
            )
            logger.info(f"Updated status DB to {current_state}")
        except Exception as e:
            logger.error(f"Failed to update status DB: {e}")
            
    if not success:
        sys.exit(1)

if __name__ == "__main__":
    main()
