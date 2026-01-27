
import os
import sys
from pathlib import Path
import mlflow
from mlflow.tracking import MlflowClient

def transition_local_models():
    mlflow_tracking_uri = os.getenv("MLFLOW_TRACKING_URI", "http://localhost:5000")
    print(f"Connecting to MLflow at {mlflow_tracking_uri}...")
    
    client = MlflowClient(tracking_uri=mlflow_tracking_uri)
    
    local_models = ["finbert_grpo_local", "lightgbm_local"]
    
    for model_name in local_models:
        try:
            print(f"\nProcessing model: {model_name}")
            versions = client.search_model_versions(f"name='{model_name}'")
            if not versions:
                print(f"No versions found for {model_name}")
                continue
            
            # Sort by version number (descending)
            versions = sorted(versions, key=lambda v: int(v.version), reverse=True)
            latest_version = versions[0].version
            
            print(f"Transitioning {model_name} v{latest_version} to Production...")
            client.transition_model_version_stage(
                name=model_name,
                version=latest_version,
                stage="Production",
                archive_existing_versions=True
            )
            print(f"Successfully transitioned {model_name} v{latest_version} to Production.")
            
        except Exception as e:
            print(f"Error transitioning {model_name}: {e}")

if __name__ == "__main__":
    transition_local_models()
