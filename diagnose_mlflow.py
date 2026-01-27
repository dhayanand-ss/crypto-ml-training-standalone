
import mlflow
from mlflow.tracking import MlflowClient

def diagnose():
    tracking_uri = "file:./mlruns"
    mlflow.set_tracking_uri(tracking_uri)
    client = MlflowClient()
    
    print(f"Tracking URI: {mlflow.get_tracking_uri()}")
    
    print("\n--- Registered Models ---")
    try:
        models = client.search_registered_models()
        if not models:
            print("No registered models found.")
        for m in models:
            print(f"Model: {m.name}")
            for v in m.latest_versions:
                print(f"  Version: {v.version}, Stage: {v.current_stage}, RunID: {v.run_id}")
    except Exception as e:
        print(f"Error searching models: {e}")

    print("\n--- Experiments ---")
    try:
        exps = client.search_experiments()
        for e in exps:
            print(f"Exp: {e.name} (ID: {e.experiment_id})")
    except Exception as e:
        print(f"Error searching experiments: {e}")

if __name__ == "__main__":
    diagnose()
