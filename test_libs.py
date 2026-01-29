
import sys
print("Testing imports...")
try:
    import onnxruntime as ort
    print(f"ONNX Runtime version: {ort.__version__}")
    sess = ort.InferenceSession("dummy_model_tmp.onnx") # This file exists in root from previous list_dir
    print("ONNX Runtime session created.")
except Exception as e:
    print(f"ONNX Runtime error: {e}")

try:
    import lightgbm as lgb
    print(f"LightGBM version: {lgb.__version__}")
    print("LightGBM imported.")
except Exception as e:
    print(f"LightGBM error: {e}")
