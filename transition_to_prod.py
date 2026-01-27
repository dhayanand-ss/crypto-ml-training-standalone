
import os
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from utils.artifact_control.model_manager import ModelManager

def transition_to_production():
    mlflow_tracking_uri = os.getenv("MLFLOW_TRACKING_URI", "http://localhost:5000")
    print(f"Connecting to MLflow at {mlflow_tracking_uri}...")
    
    manager = ModelManager(tracking_uri=mlflow_tracking_uri)
    
    models = ["BTCUSDT_lightgbm", "BTCUSDT_tst"]
    
    for model_name in models:
        try:
            print(f"\nProcessing model: {model_name}")
            versions = manager.client.search_model_versions(f"name='{model_name}'")
            if not versions:
                print(f"No versions found for {model_name}")
                continue
            
            # Sort by version number (descending)
            versions = sorted(versions, key=lambda v: int(v.version), reverse=True)
            latest_version = versions[0].version
            
            print(f"Transitioning {model_name} v{latest_version} to Production...")
            manager.client.transition_model_version_stage(
                name=model_name,
                version=latest_version,
                stage="Production",
                archive_existing_versions=True
            )
            print(f"Successfully transitioned {model_name} v{latest_version} to Production.")
            
        except Exception as e:
            print(f"Error transitioning {model_name}: {e}")

if __name__ == "__main__":
    transition_to_production()
