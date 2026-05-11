import os
import json
import logging
import torch
import numpy as np
import lightgbm as lgb
from pathlib import Path
from utils.artifact_control.model_manager import ModelManager
from trainer.time_series_transformer import TimeSeriesTransformer

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def convert_lightgbm_to_onnx(model_path, onnx_path):
    import onnxmltools
    from onnxmltools.convert.common.data_types import FloatTensorType
    
    logger.info(f"Converting LightGBM model: {model_path}")
    
    with open(model_path, 'r') as f:
        model_str = f.read()
    
    model = lgb.Booster(model_str=model_str)
    
    # Assuming 35 features based on output logs from LightGBM training
    num_features = 35 
    initial_type = [('float_input', FloatTensorType(['None', num_features]))]
    
    onnx_model = onnxmltools.convert_lightgbm(model, initial_types=initial_type)
    
    os.makedirs(os.path.dirname(onnx_path), exist_ok=True)
    with open(onnx_path, "wb") as f:
        f.write(onnx_model.SerializeToString())
    
    logger.info(f"Saved ONNX model to {onnx_path}")

def convert_pytorch_to_onnx(model_path, onnx_path):
    logger.info(f"Converting PyTorch model: {model_path}")
    
    # Instantiate the model with expected parameters
    # Note: These must match trainer/time_series_transformer.py configuration
    # Wait, the main() function says:
    # input_dim = 7
    # hidden_dim = 32
    # num_heads = 2
    # ff_dim = 64
    # num_layers = 1
    # num_classes = 3
    model = TimeSeriesTransformer(
        input_dim=7,
        hidden_dim=32,
        num_heads=2,
        ff_dim=64,
        num_layers=1,
        dropout=0.1,
        num_classes=3
    )
    
    # Load state dict
    try:
        model.load_state_dict(torch.load(model_path, map_location='cpu'))
    except RuntimeError as e:
        logger.error(f"Failed to load state dict. Architecture mismatch? Error: {e}")
        return
        
    model.eval()
    
    # Create dummy input: (batch_size, sequence_length, input_dim)
    # Sequence length is 15 based on main() in time_series_transformer.py
    dummy_input = torch.randn(1, 15, 7)
    
    os.makedirs(os.path.dirname(onnx_path), exist_ok=True)
    
    # Export to ONNX
    torch.onnx.export(
        model, 
        dummy_input, 
        onnx_path, 
        export_params=True, 
        opset_version=14, 
        do_constant_folding=True, 
        input_names=['input'], 
        output_names=['output'], 
        dynamic_axes={
            'input': {0: 'batch_size'}, 
            'output': {0: 'batch_size'}
        }
    )
    
    logger.info(f"Saved ONNX model to {onnx_path}")

def main():
    manager = ModelManager()
    registry = manager.local_registry
    
    if not registry:
        logger.error("No local registry found or it is empty.")
        return

    # Process LightGBM models
    lgb_registry = registry.get('lightgbm', {})
    for version, data in lgb_registry.items():
        if data and data.get('path'):
            model_path = manager.get_local_model_path('lightgbm', version.replace('v', ''))
            if model_path:
                onnx_path = os.path.join(manager.models_dir, 'onnx', f'lightgbm_{version.replace("v", "")}.onnx')
                try:
                    convert_lightgbm_to_onnx(model_path, onnx_path)
                except Exception as e:
                    logger.error(f"Error converting LightGBM {version}: {e}")

    # Process TST (PyTorch) models
    tst_registry = registry.get('tst', {})
    for version, data in tst_registry.items():
        if data and data.get('path'):
            model_path = manager.get_local_model_path('tst', version.replace('v', ''))
            if model_path:
                onnx_path = os.path.join(manager.models_dir, 'onnx', f'tst_{version.replace("v", "")}.onnx')
                try:
                    convert_pytorch_to_onnx(model_path, onnx_path)
                except Exception as e:
                    logger.error(f"Error converting PyTorch TST {version}: {e}")

if __name__ == "__main__":
    main()
