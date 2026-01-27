
import os
import sys
import mlflow
import lightgbm as lgb
import pickle
from onnxmltools import convert_lightgbm
from skl2onnx.common.data_types import FloatTensorType
from mlflow.tracking import MlflowClient

def register_lgb_onnx():
    tracking_uri = "http://localhost:5001"
    mlflow.set_tracking_uri(tracking_uri)
    client = MlflowClient(tracking_uri=tracking_uri)
    
    model_path = 'models/lightgbm/v3/model.txt'
    features_path = 'models/lightgbm/v3/model_features.pkl'
    name = "lightgbm_local"
    
    if not os.path.exists(model_path):
        print(f"Model not found: {model_path}")
        return

    # 1. Convert to ONNX
    print(f"Loading LightGBM model from {model_path}")
    model = lgb.Booster(model_file=model_path)
    
    with open(features_path, 'rb') as f:
        features = pickle.load(f)
    num_features = len(features)
    
    initial_type = [('input', FloatTensorType([None, num_features]))]
    print("Converting to ONNX...")
    onnx_model = convert_lightgbm(model, initial_types=initial_type, target_opset=12)
    
    onnx_file = "lightgbm_local_tmp.onnx"
    with open(onnx_file, "wb") as f:
        f.write(onnx_model.SerializeToString())
    
    # 2. Register to MLflow
    print(f"Registering {name} to MLflow...")
    try:
        with mlflow.start_run(run_name=f"reg_onnx_{name}") as run:
            # ModelManager expects the ONNX file at onnx/{name}_tmp.onnx
            # or onnx/model.onnx etc.
            # Looking at model_manager.py:
            # onnx_path = os.path.join(local_path, f'onnx/{name}_tmp.onnx')
            
            # We need to log it so the artifact path has 'onnx' directory
            # and the filename is {name}_tmp.onnx
            
            target_filename = f"{name}_tmp.onnx"
            # Rename our local file to match
            if os.path.exists(target_filename):
                os.remove(target_filename)
            os.rename(onnx_file, target_filename)
            
            mlflow.log_artifact(target_filename, artifact_path=f"{name}/onnx")
            print(f"Logged artifact to {name}/onnx/{target_filename}")
            
            # Register version
            # The model_uri should point to the parent of 'onnx' directory
            # actually ModelManager uses version_obj.source which is the 'model' directory
            # so we should log it under the name
            
            model_uri = f"runs:/{run.info.run_id}/{name}"
            mv = mlflow.register_model(model_uri, name)
            print(f"Registered {name} version {mv.version}")
            
            # Transition to Production
            client.transition_model_version_stage(
                name=name,
                version=mv.version,
                stage="Production",
                archive_existing_versions=True
            )
            print(f"Successfully pushed {name} v{mv.version} to Production.")
            os.remove(target_filename)
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    register_lgb_onnx()
