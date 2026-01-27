
import mlflow
import os
from pathlib import Path

def register_models_robustly():
    # Revert to file-based tracking to avoid SQLAlchemy dependency issues
    tracking_uri = "file:./mlruns"
    mlflow.set_tracking_uri(tracking_uri)
    
    # Ensure the directory for artifacts exists
    # If the user was using 'file:./mlruns', we'll transition to SQL for metadata
    # while keeping artifacts in ./mlruns
    os.makedirs("mlruns", exist_ok=True)
    
    print("=" * 60)
    print("Robust Local Model Registration to MLflow")
    print(f"Tracking URI: {tracking_uri}")
    print("=" * 60)

    # List of models to register
    models_to_register = [
        {
            "name": "lightgbm_local",
            "path": "models/lightgbm/v3/lgb_model.txt",
            "type": "artifact"
        },
        {
            "name": "finbert_grpo_local",
            "path": "models/finbert/finbert_grpo.pth",
            "type": "artifact",
            "extra": "models/finbert/tokenizer"
        }
    ]

    for model_info in models_to_register:
        name = model_info["name"]
        path = Path(model_info["path"])
        
        if not path.exists():
            print(f"Warning: model file not found for {name}: {path}")
            continue

        print(f"\nProcessing {name}...")
        try:
            # Start run
            with mlflow.start_run(run_name=f"register_{name}") as run:
                # Log model file as artifact
                mlflow.log_artifact(str(path), artifact_path="model")
                
                # Log extra (e.g. tokenizer)
                if "extra" in model_info:
                    extra_path = Path(model_info["extra"])
                    if extra_path.exists():
                        mlflow.log_artifacts(str(extra_path), artifact_path="tokenizer")

                # Alternative registration method: Create Model first if needed
                from mlflow.tracking import MlflowClient
                client = MlflowClient()
                try:
                    client.create_registered_model(name)
                except:
                    pass # Already exists
                
                model_uri = f"runs:/{run.info.run_id}/model"
                mv = client.create_model_version(name, model_uri, run.info.run_id)
                print(f"Successfully registered model '{name}' version {mv.version}")
                print(f"Run ID: {run.info.run_id}")
        except Exception as e:
            print(f"Failed to register {name}: {e}")

    print("\nRegistration process completed.")
    print("\nTIP: If you still don't see the models in the MLflow UI:")
    print("1. Ensure you ran 'mlflow ui' from: " + os.getcwd())
    print("2. In the UI, try toggling the 'New model registry UI' switch.")


if __name__ == "__main__":
    register_local_models_path = Path("utils/manual_model_registration.py")
    register_models_robustly()
