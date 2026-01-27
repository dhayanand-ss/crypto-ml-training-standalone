
import os
import sys
import mlflow
from mlflow.tracking import MlflowClient

def register_and_produce():
    tracking_uri = "http://localhost:5001"
    mlflow.set_tracking_uri(tracking_uri)
    client = MlflowClient(tracking_uri=tracking_uri)
    
    print(f"Using tracking URI: {tracking_uri}")
    
    models = [
        {
            "name": "lightgbm_local",
            "path": "models/lightgbm/v3/lgb_model.txt"
        },
        {
            "name": "finbert_grpo_local",
            "path": "models/finbert/finbert_grpo.pth"
        }
    ]
    
    for m in models:
        name = m["name"]
        path = m["path"]
        
        if not os.path.exists(path):
            print(f"File not found: {path}")
            continue
            
        print(f"\n--- Processing {name} ---")
        try:
            # Ensure model exists
            try:
                client.get_registered_model(name)
                print(f"Model {name} already exists.")
            except:
                print(f"Creating registered model {name}...")
                client.create_registered_model(name)

            with mlflow.start_run(run_name=f"manual_reg_{name}") as run:
                print(f"Started run {run.info.run_id}")
                # Log the file
                mlflow.log_artifact(path, artifact_path="model")
                print(f"Logged artifact {path}")
                
                # Create version
                model_uri = f"runs:/{run.info.run_id}/model"
                mv = client.create_model_version(name, model_uri, run.info.run_id)
                print(f"Created version {mv.version}")
                
                # Transition to Production
                print(f"Transitioning v{mv.version} to Production...")
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
