
import os
import sys
import mlflow
from mlflow.tracking import MlflowClient

def debug_models_file():
    uri = "file:C:/Users/dhaya/crypto-ml-training-standalone/mlruns"
    client = MlflowClient(tracking_uri=uri)
    print(f"Registered Models on {uri}:")
    try:
        rms = client.search_registered_models()
        for rm in rms:
            print(f"- {rm.name}")
            versions = client.search_model_versions(f"name='{rm.name}'")
            print(f"  Versions: {[v.version for v in versions]}")
    except Exception as e:
        print(f"Error on {uri}: {e}")

if __name__ == "__main__":
    debug_models_file()
