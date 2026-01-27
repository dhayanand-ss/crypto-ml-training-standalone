
import lightgbm as lgb
import numpy as np
import pickle
import os
from onnxmltools import convert_lightgbm
from skl2onnx.common.data_types import FloatTensorType

def convert_lgb_to_onnx():
    model_path = r'c:\Users\dhaya\crypto-ml-training-standalone\models\lightgbm\v3\lgb_model.txt'
    features_path = r'c:\Users\dhaya\crypto-ml-training-standalone\models\lightgbm\v3\lgb_model_features.pkl'
    output_onnx_path = r'c:\Users\dhaya\crypto-ml-training-standalone\lightgbm_local.onnx'

    print(f"Loading LightGBM model from {model_path}")
    model = lgb.Booster(model_file=model_path)
    
    print(f"Loading features from {features_path}")
    with open(features_path, 'rb') as f:
        features = pickle.load(f)
    
    num_features = len(features)
    print(f"Model has {num_features} features")

    # Initial type for ONNX
    # LightGBM usually expects float32
    initial_type = [('input', FloatTensorType([None, num_features]))]
    
    print("Converting to ONNX...")
    onnx_model = convert_lightgbm(model, initial_types=initial_type, target_opset=12)
    
    print(f"Saving ONNX model to {output_onnx_path}")
    with open(output_onnx_path, "wb") as f:
        f.write(onnx_model.SerializeToString())
    
    print("Conversion complete!")

if __name__ == "__main__":
    convert_lgb_to_onnx()
