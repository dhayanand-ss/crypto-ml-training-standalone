
import os
import sys
from pathlib import Path
import mlflow
from mlflow.tracking import MlflowClient

def list_registered_models_local_status():
    mlflow_tracking_uri = os.getenv("MLFLOW_TRACKING_URI", "http://localhost:5000")
    print(f"Connecting to MLflow at {mlflow_tracking_uri}...")
    
    client = MlflowClient(tracking_uri=mlflow_tracking_uri)
    
    try:
        registered_models = client.search_registered_models()
        print(f"Found {len(registered_models)} registered model(s)\n")
        
        for rm in registered_models:
            print(f"Model: {rm.name}")
            for mv in rm.latest_versions:
                is_local = "C:/Users/dhaya" in mv.source or "file://" in mv.source
                print(f"  Version: {mv.version}, Stage: {mv.current_stage}, Local: {is_local}")
                print(f"    Source: {mv.source}")
                print(f"    Run ID: {mv.run_id}")
            print("-" * 40)
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    list_registered_models_local_status()
