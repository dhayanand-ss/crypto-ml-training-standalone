
import os
import sys
import mlflow
import onnx
from onnx import helper, TensorProto
from mlflow.tracking import MlflowClient

def register_dummy_onnx():
    tracking_uri = "http://localhost:5001"
    mlflow.set_tracking_uri(tracking_uri)
    client = MlflowClient(tracking_uri=tracking_uri)
    
    name = "dummy_model"
    
    # 1. Create a dummy ONNX model
    print("Creating dummy ONNX model...")
    # Create nodes
    node_def = helper.make_node(
        'Relu',
        ['X'],
        ['Y'],
    )
    # Create the graph
    graph_def = helper.make_graph(
        [node_def],
        'dummy-model',
        [helper.make_tensor_value_info('X', TensorProto.FLOAT, [1, 2])],
        [helper.make_tensor_value_info('Y', TensorProto.FLOAT, [1, 2])],
    )
    # Create the model
    model_def = helper.make_model(graph_def, producer_name='onnx-example')
    
    onnx_file = "dummy_tmp.onnx"
    onnx.save(model_def, onnx_file)
    
    # 2. Register to MLflow
    print(f"Registering {name} to MLflow...")
    try:
        with mlflow.start_run(run_name=f"reg_dummy_{name}") as run:
            # ModelManager expects the ONNX file at onnx/{name}_tmp.onnx
            target_filename = f"{name}_tmp.onnx"
            if os.path.exists(target_filename):
                os.remove(target_filename)
            os.rename(onnx_file, target_filename)
            
            mlflow.log_artifact(target_filename, artifact_path=f"{name}/onnx")
            
            model_uri = f"runs:/{run.info.run_id}/{name}"
            mv = mlflow.register_model(model_uri, name)
            
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
    register_dummy_onnx()
