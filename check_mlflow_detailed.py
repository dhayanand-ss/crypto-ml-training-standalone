
import mlflow
from mlflow.tracking import MlflowClient
import os

def diagnose():
    tracking_uri = "file:./mlruns"
    mlflow.set_tracking_uri(tracking_uri)
    client = MlflowClient()
    
    with open("mlflow_status.txt", "w") as f:
        f.write(f"Tracking URI: {mlflow.get_tracking_uri()}\n")
        
        f.write("\n--- Registered Models ---\n")
        try:
            models = client.search_registered_models()
            if not models:
                f.write("No registered models found.\n")
            for m in models:
                f.write(f"Model: {m.name}\n")
                for v in m.latest_versions:
                    f.write(f"  Version: {v.version}, Stage: {v.current_stage}, RunID: {v.run_id}\n")
                    # Check for ONNX artifact
                    try:
                        artifacts = client.list_artifacts(v.run_id)
                        onnx_found = any(a.path.endswith(".onnx") for a in artifacts)
                        f.write(f"    ONNX found: {onnx_found}\n")
                        for a in artifacts:
                            f.write(f"      - {a.path}\n")
                    except Exception as ae:
                        f.write(f"    Error listing artifacts: {ae}\n")
        except Exception as e:
            f.write(f"Error searching models: {e}\n")

        f.write("\n--- Experiments ---\n")
        try:
            exps = client.search_experiments()
            for e in exps:
                f.write(f"Exp: {e.name} (ID: {e.experiment_id})\n")
        except Exception as e:
            f.write(f"Error searching experiments: {e}\n")

if __name__ == "__main__":
    diagnose()
