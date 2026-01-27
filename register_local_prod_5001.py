
import os
import sys
import mlflow
from mlflow.tracking import MlflowClient
from pathlib import Path

def register_and_produce():
    # Use port 5001 as seen in the terminal metadata
    tracking_uri = "http://localhost:5001"
    mlflow.set_tracking_uri(tracking_uri)
    client = MlflowClient(tracking_uri=tracking_uri)
    
    print(f"Using tracking URI: {tracking_uri}")
    
    models = [
        {
            "name": "lightgbm_local",
            "path": "models/lightgbm/v3/lgb_model.txt",
            "type": "lightgbm"
        },
        {
            "name": "finbert_grpo_local",
            "path": "models/finbert/finbert_grpo.pth",
            "type": "pytorch" # TST/Finbert usually pytorch here
        }
    ]
    
    for m in models:
        name = m["name"]
        path = m["path"]
        
        if not os.path.exists(path):
            print(f"File not found: {path}")
            continue
            
        print(f"\nRegistering {name} from {path}...")
        try:
            with mlflow.start_run(run_name=f"manual_reg_{name}") as run:
                # Log the file as an artifact
                mlflow.log_artifact(path, artifact_path="model")
                
                # Register the model
                model_uri = f"runs:/{run.info.run_id}/model"
                mv = mlflow.register_model(model_uri, name)
                
                print(f"Registered {name} version {mv.version}")
                
                # Transition to Production
                print(f"Transitioning {name} v{mv.version} to Production...")
                client.transition_model_version_stage(
                    name=name,
                    version=mv.version,
                    stage="Production",
                    archive_existing_versions=True
                )
                print(f"Successfully pushed {name} to Production.")
                
        except Exception as e:
            print(f"Error with {name}: {e}")

if __name__ == "__main__":
    register_and_produce()
