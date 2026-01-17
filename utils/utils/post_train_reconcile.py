#!/usr/bin/env python3
"""
Post-Training Reconciliation Script
Handles post-training tasks for LightGBM and TST models:
1. Syncs local file versions with ModelVersionManager
2. Converts models to ONNX
3. Registers models to MLflow
4. Updates pipeline status
"""

import os
import sys
import argparse
import logging
from pathlib import Path
import shutil
import joblib
import numpy as np
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
from utils.artifact_control.model_manager import ModelManager 

def sync_feature_files(model_type, version, version_dir):
    """Ensure feature/scaler files are present in the version directory"""
    if model_type == "lightgbm":
        # Check for feature file
        if not (version_dir / "lgb_model_features.pkl").exists():
            # Try to find it with old name
            old_feature_file = version_dir / "model_features.pkl"
            if old_feature_file.exists():
                shutil.copy2(old_feature_file, version_dir / "lgb_model_features.pkl")
                
    elif model_type == "tst":
        # Check for scaler file
        if not (version_dir / "tst_scaler.pkl").exists():
            # Look for scaler in parent or models/tst root
            possible_scalers = list(version_dir.parent.glob("*scaler*.pkl"))
            if possible_scalers:
                shutil.copy2(possible_scalers[0], version_dir / "tst_scaler.pkl")

def sync_versions_to_registry(model_type_arg):
    """
    Sync local file structure to ModelVersionManager registry.
    This is needed because training scripts might move files manually.
    """
    manager = ModelVersionManager()
    
    # Map CLI model arg to registry model type
    model_mapping = {
        "lightgbm": "lightgbm",
        "tst": "tst"
    }
    registry_model_type = model_mapping.get(model_type_arg)
    
    if not registry_model_type:
        logger.error(f"Unknown model type for registry sync: {model_type_arg}")
        return manager
        
    logger.info(f"Syncing {registry_model_type} versions to registry...")
    
    base_dir = project_root / "models" / registry_model_type
    
    # Check v1, v2, v3 directories
    for version in ["1", "2", "3"]:
        v_dir = base_dir / f"v{version}"
        
        # Determine expected model filename
        if registry_model_type == "lightgbm":
            model_file = v_dir / "lgb_model.txt"
            # Also check for generic model.txt
            if not model_file.exists() and (v_dir / "model.txt").exists():
                 model_file = v_dir / "model.txt"
        elif registry_model_type == "tst":
            model_file = v_dir / "tst_model.pth"
        else:
            continue
            
        if model_file.exists():
            # Update registry if missing or path changed
            current_entry = manager.registry[registry_model_type].get(f"v{version}")
            
            # Basic metadata
            metadata = {}
            try:
                stat = model_file.stat()
                from datetime import datetime
                created_at = datetime.fromtimestamp(stat.st_mtime).isoformat()
            except:
                created_at = None
                
            # If entry doesn't exist or points to wrong path, update it
            if not current_entry or current_entry.get("path") != str(model_file):
                logger.info(f"Updating registry for {registry_model_type} v{version}")
                manager.registry[registry_model_type][f"v{version}"] = {
                    "path": str(model_file),
                    "created_at": created_at or current_entry.get("created_at"),
                    "metadata": metadata
                }
                
                # Ensure associated files are synced
                sync_feature_files(registry_model_type, version, v_dir)
    
    # Save updates
    manager._save_registry()
    logger.info("Registry sync complete")
    return manager

def get_sample_input(model_type, version_dir):
    """Generate sample input for ONNX conversion"""
    try:
        if model_type == "lightgbm":
            # Try to load features pkl
            feature_file = version_dir / "lgb_model_features.pkl"
            if not feature_file.exists():
                feature_file = version_dir / "model_features.pkl"
            
            if feature_file.exists():
                feature_info = joblib.load(feature_file)
                if 'feature_names' in feature_info:
                    num_features = len(feature_info['feature_names'])
                    return np.zeros((1, num_features), dtype=np.float32)
            
            # Fallback for generic LightGBM if needed (guess or fail)
            return None
            
        elif model_type == "tst":
            # TST input shape: (batch, seq_len, input_dim)
            # Default from architecture: input_dim=7, assume seq_len=15
            import torch
            return torch.zeros(1, 15, 7, dtype=torch.float32)
            
    except Exception as e:
        logger.warning(f"Failed to create sample input: {e}")
    return None

def register_to_mlflow(model_type, version, version_dir, coin):
    """Register a specific version to MLflow"""
    
    # Determine model file
    if model_type == "lightgbm":
        model_file = version_dir / "lgb_model.txt"
        if not model_file.exists():
             model_file = version_dir / "model.txt"
        model_name_suffix = "lightgbm"
    elif model_type == "tst":
        model_file = version_dir / "tst_model.pth"
        model_name_suffix = "tst"
    else:
        return False
        
    if not model_file.exists():
        logger.warning(f"Model file missing for {model_type} {version}: {model_file}")
        return False

    try:
        # Load model logic
        loaded_model = None
        onnx_model = None
        
        sample_input = get_sample_input(model_type, version_dir)
        
        if model_type == "lightgbm":
            import lightgbm as lgb
            loaded_model = lgb.Booster(model_file=str(model_file))
            
            if sample_input is not None:
                from trainer.train_utils import convert_to_onnx
                try:
                    onnx_model = convert_to_onnx(loaded_model, type="lightgbm", sample_input=sample_input)
                except Exception as e:
                    logger.warning(f"ONNX conversion failed: {e}")

        elif model_type == "tst":
            import torch
            from trainer.time_series_transformer import TimeSeriesTransformer
            
            # We need to instantiate the model class with correct params
            # Ideally params should be saved with model, here we use defaults or try to load from status_db/metadata
            # Using defaults from known architecture for now
            loaded_model = TimeSeriesTransformer(
                input_dim=7, hidden_dim=32, num_heads=2, ff_dim=64, num_layers=1, dropout=0.1, num_classes=3
            )
            state_dict = torch.load(model_file, map_location='cpu')
            loaded_model.load_state_dict(state_dict)
            loaded_model.eval()
            
            if sample_input is not None:
                from trainer.train_utils import convert_to_onnx
                try:
                    onnx_model = convert_to_onnx(loaded_model, type="pytorch", sample_input=sample_input)
                except Exception as e:
                    logger.warning(f"ONNX conversion failed: {e}")

        # MLflow Logging
        mlflow.set_experiment("crypto-ml-pipeline")
        run_name = f"{model_name_suffix}_{version}_reconcile"
        
        with mlflow.start_run(run_name=run_name):
            full_model_name = f"{coin}_{model_name_suffix}"
            
            # Log Model
            if model_type == "lightgbm":
                mlflow.lightgbm.log_model(loaded_model, artifact_path=full_model_name)
            elif model_type == "tst":
                mlflow.pytorch.log_model(loaded_model, artifact_path=full_model_name)
                
            # Log ONNX
            if onnx_model is not None:
                import onnx
                import tempfile
                with tempfile.NamedTemporaryFile(suffix='.onnx', delete=False) as tmp:
                    onnx.save(onnx_model, tmp.name)
                    tmp_path = tmp.name
                mlflow.log_artifact(tmp_path, artifact_path=f"{full_model_name}/onnx")
                os.unlink(tmp_path)
            
            # Register
            run_id = mlflow.active_run().info.run_id
            model_uri = f"runs:/{run_id}/{full_model_name}"
            
            # Initialize ModelManager for registration helper (handles retries/client)
             # But here we might just use mlflow direct or ModelManager if available
            try:
                registered_model = mlflow.register_model(model_uri=model_uri, name=full_model_name)
                logger.info(f"Registered {full_model_name} version {registered_model.version}")
                
                # Set to Production (for v3 and v1)
                # Note: This logic assumes v3 is the one we want in production given it's latest
                if version in ["v3", "v1"]:
                    client = mlflow.tracking.MlflowClient()
                    client.transition_model_version_stage(
                        name=full_model_name,
                        version=registered_model.version,
                        stage="Production"
                    )
                    logger.info(f"Transitioned {full_model_name} v{registered_model.version} to Production")
            except Exception as reg_e:
                logger.error(f"Registration failed: {reg_e}")
                return False
                
        return True

    except Exception as e:
        logger.error(f"Failed to process {model_type} {version}: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    parser = argparse.ArgumentParser(description="Post-Training Reconciliation")
    parser.add_argument("--crypto", type=str, required=True, help="Crypto symbol (e.g. BTCUSDT)")
    parser.add_argument("--model", type=str, required=True, help="Model type (lightgbm or tst)")
    args = parser.parse_args()
    
    logger.info(f"Starting reconciliation for {args.model} on {args.crypto}")
    
    # 0. Sync models from GCS (ensure we have latest files from remote training)
    try:
        from utils.utils.gcs_sync import download_models_from_gcs
        download_models_from_gcs(project_root)
    except Exception as e:
        logger.warning(f"Model sync failed: {e}")

    # 1. Sync Registry
    manager = sync_versions_to_registry(args.model)
    
    # 2. Register v3 (Latest)
    # in a real pipeline we might only register v3, but to be safe/complete we can try others if needed
    # The requirement is primarily to get the latest trained model (v3) into Production
    
    model_type_map = {"lightgbm": "lightgbm", "tst": "tst"}
    registry_type = model_type_map.get(args.model)
    
    # Check if v3 exists logic
    v3_info = manager.registry[registry_type].get("v3")
    
    success = False
    error_msg = None
    
    if v3_info and v3_info.get("path"):
        v3_path = Path(v3_info["path"])
        v3_dir = v3_path.parent
        logger.info(f"Found v3 model at {v3_path}, proceeding to register")
        
        if register_to_mlflow(args.model, "v3", v3_dir, args.crypto):
            success = True
        else:
            error_msg = "Failed to register v3 model to MLflow"
    else:
        error_msg = "No v3 model found in registry"
        logger.error(error_msg)

    # 3. Update Status DB
    if STATUS_DB_AVAILABLE:
        try:
            current_state = "SUCCESS" if success else "FAILED"
            db.set_state(
                model=args.model, 
                coin=args.crypto, 
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
