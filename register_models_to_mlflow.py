#!/usr/bin/env python3
"""
Register existing local models to MLflow

This script registers models that were saved locally to MLflow.
It reads models from the models/ directory and registers them to MLflow.
"""

import os
import sys
from pathlib import Path
import logging

# Add project root to path
project_root = Path(__file__).resolve().parent
sys.path.insert(0, str(project_root))

# Suppress GCS errors - we don't need GCS for MLflow registration
logging.getLogger("utils.artifact_control.gcs_manager").setLevel(logging.CRITICAL)

from utils.artifact_control.model_manager import ModelManager
import mlflow

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def register_lightgbm_models():
    """Register LightGBM models to MLflow"""
    logger.info("Registering LightGBM models...")
    
    # Initialize ModelManager (GCS errors are expected and harmless)
    try:
        model_manager = ModelManager()
    except Exception as e:
        # If ModelManager fails completely, we can't proceed
        logger.error(f"Failed to initialize ModelManager: {e}")
        raise
    lightgbm_dir = project_root / "models" / "lightgbm"
    
    if not lightgbm_dir.exists():
        logger.warning(f"LightGBM directory not found: {lightgbm_dir}")
        return
    
    # Try to get sample input for ONNX conversion
    # This is needed for FastAPI to work
    sample_input = None
    try:
        import pandas as pd
        import numpy as np
        # Try to load feature info to get input shape
        features_file = lightgbm_dir / "v3" / "lgb_model_features.pkl"
        if features_file.exists():
            import joblib
            feature_info = joblib.load(features_file)
            if 'feature_names' in feature_info:
                num_features = len(feature_info['feature_names'])
                # Create dummy input with correct shape (batch_size=1, num_features)
                sample_input = np.zeros((1, num_features), dtype=np.float32)
                logger.info(f"Using sample input shape: {sample_input.shape}")
    except Exception as e:
        logger.warning(f"Could not determine sample input shape: {e}")
        logger.warning("ONNX conversion will be skipped. FastAPI may not work without ONNX models.")
    
    # Register each version
    for version in ["v1", "v2", "v3"]:
        version_dir = lightgbm_dir / version
        model_file = version_dir / "lgb_model.txt"
        
        if not model_file.exists():
            logger.warning(f"Model file not found: {model_file}")
            continue
        
        try:
            import lightgbm as lgb
            
            # Load the model
            logger.info(f"Loading LightGBM model from {model_file}")
            model = lgb.Booster(model_file=str(model_file))
            
            # Convert to ONNX if possible
            onnx_model = None
            if sample_input is not None:
                try:
                    from trainer.train_utils import convert_to_onnx
                    logger.info(f"Converting {version} to ONNX...")
                    onnx_model = convert_to_onnx(model, type="lightgbm", sample_input=sample_input)
                    logger.info(f"✅ ONNX conversion successful for {version}")
                except Exception as e:
                    logger.warning(f"⚠️  ONNX conversion failed for {version}: {e}")
                    logger.warning("Model will be registered without ONNX. FastAPI may not work.")
            
            # Start MLflow run
            mlflow.set_experiment("crypto-ml-pipeline")
            with mlflow.start_run(run_name=f"lightgbm_{version}_registration"):
                model_name = f"BTCUSDT_lightgbm"
                
                # Log model
                mlflow.lightgbm.log_model(model, artifact_path=model_name)
                
                # Log ONNX model if available
                if onnx_model is not None:
                    try:
                        import onnx
                        import tempfile
                        import os
                        temp_onnx = tempfile.NamedTemporaryFile(suffix='.onnx', delete=False)
                        onnx.save(onnx_model, temp_onnx.name)
                        mlflow.log_artifact(temp_onnx.name, artifact_path=f"{model_name}/onnx")
                        os.unlink(temp_onnx.name)
                        logger.info(f"✅ ONNX model logged for {version}")
                    except Exception as e:
                        logger.warning(f"Failed to log ONNX model: {e}")
                
                # Register model
                run_id = mlflow.active_run().info.run_id
                model_uri = f"runs:/{run_id}/{model_name}"
                
                registered_model = mlflow.register_model(
                    model_uri=model_uri,
                    name=model_name
                )
                
                logger.info(f"✅ Registered {model_name} version {registered_model.version} from {version}")
                
                # Set to Production if it's v1 or v3
                if version in ["v1", "v3"]:
                    model_manager.client.transition_model_version_stage(
                        name=model_name,
                        version=registered_model.version,
                        stage="Production"
                    )
                    logger.info(f"✅ Set {model_name} v{registered_model.version} to Production stage")
                
        except Exception as e:
            logger.error(f"❌ Failed to register {version}: {e}")
            import traceback
            traceback.print_exc()


def register_tst_models():
    """Register TST (Time Series Transformer) models to MLflow"""
    logger.info("Registering TST models...")
    
    # Initialize ModelManager (GCS errors are expected and harmless)
    try:
        model_manager = ModelManager()
    except Exception as e:
        # If ModelManager fails completely, we can't proceed
        logger.error(f"Failed to initialize ModelManager: {e}")
        raise
    
    tst_dir = project_root / "models" / "tst"
    
    if not tst_dir.exists():
        logger.warning(f"TST directory not found: {tst_dir}")
        return
    
    # Model architecture parameters (from simplified_integrated_model.py)
    input_dim = 7  # open, high, low, close, volume, taker_base, taker_quote
    hidden_dim = 32
    num_heads = 2
    ff_dim = 64
    num_layers = 1
    dropout = 0.1
    num_classes = 3
    
    # Register each version
    for version in ["v1", "v2", "v3"]:
        version_dir = tst_dir / version
        model_file = version_dir / "tst_model.pth"
        
        if not model_file.exists():
            logger.warning(f"Model file not found: {model_file}")
            continue
        
        try:
            import torch
            import numpy as np
            from trainer.time_series_transformer import TimeSeriesTransformer
            
            # Load model state dict
            logger.info(f"Loading TST model from {model_file}")
            model_state = torch.load(model_file, map_location='cpu')
            
            # Reconstruct the full model instance
            logger.info(f"Reconstructing TST model architecture...")
            model = TimeSeriesTransformer(
                input_dim=input_dim,
                hidden_dim=hidden_dim,
                num_heads=num_heads,
                ff_dim=ff_dim,
                num_layers=num_layers,
                dropout=dropout,
                num_classes=num_classes
            )
            
            # Load the state dict
            model.load_state_dict(model_state)
            model.eval()  # Set to evaluation mode
            
            logger.info(f"✅ Model reconstructed successfully")
            
            # Convert to ONNX if possible
            onnx_model = None
            try:
                from trainer.train_utils import convert_to_onnx
                # Create sample input for ONNX conversion
                # Shape: (batch_size=1, sequence_length=15, input_dim=7)
                sample_input = torch.zeros(1, 15, input_dim, dtype=torch.float32)
                logger.info(f"Converting {version} to ONNX...")
                onnx_model = convert_to_onnx(model, type="pytorch", sample_input=sample_input)
                logger.info(f"✅ ONNX conversion successful for {version}")
            except Exception as e:
                logger.warning(f"⚠️  ONNX conversion failed for {version}: {e}")
                logger.warning("Model will be registered without ONNX. FastAPI may not work.")
            
            # Start MLflow run
            mlflow.set_experiment("crypto-ml-pipeline")
            with mlflow.start_run(run_name=f"tst_{version}_registration"):
                model_name = f"BTCUSDT_tst"
                
                # Log PyTorch model properly
                mlflow.pytorch.log_model(model, artifact_path=model_name)
                logger.info(f"✅ PyTorch model logged for {version}")
                
                # Log ONNX model if available
                if onnx_model is not None:
                    try:
                        import onnx
                        import tempfile
                        temp_onnx = tempfile.NamedTemporaryFile(suffix='.onnx', delete=False)
                        onnx.save(onnx_model, temp_onnx.name)
                        mlflow.log_artifact(temp_onnx.name, artifact_path=f"{model_name}/onnx")
                        os.unlink(temp_onnx.name)
                        logger.info(f"✅ ONNX model logged for {version}")
                    except Exception as e:
                        logger.warning(f"Failed to log ONNX model: {e}")
                
                # Register model
                run_id = mlflow.active_run().info.run_id
                model_uri = f"runs:/{run_id}/{model_name}"
                
                registered_model = mlflow.register_model(
                    model_uri=model_uri,
                    name=model_name
                )
                
                logger.info(f"✅ Registered {model_name} version {registered_model.version} from {version}")
                
                # Set to Production if it's v1 or v3
                if version in ["v1", "v3"]:
                    model_manager.client.transition_model_version_stage(
                        name=model_name,
                        version=registered_model.version,
                        stage="Production"
                    )
                    logger.info(f"✅ Set {model_name} v{registered_model.version} to Production stage")
                
        except Exception as e:
            logger.error(f"❌ Failed to register {version}: {e}")
            import traceback
            traceback.print_exc()


def main():
    """Main function to register all models"""
    print("=" * 60)
    print("Registering Local Models to MLflow")
    print("=" * 60)
    print()
    print("Note: GCS (Google Cloud Storage) errors are expected and harmless.")
    print("This script only needs MLflow, not GCS.")
    print()
    
    # Check MLflow connection
    tracking_uri = os.getenv("MLFLOW_TRACKING_URI", "http://localhost:5000")
    print(f"MLflow Tracking URI: {tracking_uri}")
    
    try:
        mlflow.set_tracking_uri(tracking_uri)
        # Test connection
        mlflow.search_experiments()
        print("✅ Connected to MLflow")
    except Exception as e:
        print(f"❌ Failed to connect to MLflow: {e}")
        print("\nMake sure MLflow server is running:")
        print("  mlflow ui --port 5000")
        return
    
    print()
    
    # Register models
    register_lightgbm_models()
    print()
    register_tst_models()
    
    print()
    print("=" * 60)
    print("Registration Complete!")
    print("=" * 60)
    print()
    print("Next steps:")
    print("1. Check MLflow UI: http://localhost:5000")
    print("2. Verify models are in 'Production' stage")
    print("3. Refresh FastAPI: POST http://localhost:8000/refresh")
    print("4. Check loaded models: GET http://localhost:8000/models")


if __name__ == "__main__":
    main()

