
import os
import sys
import mlflow
from mlflow.tracking import MlflowClient

def debug_models():
    client = MlflowClient(tracking_uri="http://localhost:5000")
    print("Registered Models:")
    rms = client.search_registered_models()
    for rm in rms:
        print(f"- {rm.name}")
        versions = client.search_model_versions(f"name='{rm.name}'")
        print(f"  Versions: {[v.version for v in versions]}")

if __name__ == "__main__":
    debug_models()
