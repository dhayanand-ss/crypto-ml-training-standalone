
import torch
import sys
import os
try:
    import pyparsing
    print(f"Debug: pyparsing version: {pyparsing.__version__}")
    print(f"Debug: pyparsing file: {pyparsing.__file__}")
except ImportError:
    print("Debug: pyparsing not found")

import sys
import os
from pathlib import Path

# Add project root to path
project_root = Path(__file__).resolve().parent
sys.path.insert(0, str(project_root))

from trainer.time_series_transformer import TimeSeriesTransformer
from trainer.train_utils import convert_to_onnx

def test_tst_conversion():
    print("Testing TST conversion...")
    
    version = "v1"
    model_file = project_root / "models" / "tst" / version / "tst_model.pth"
    
    if not model_file.exists():
        print(f"Model file not found: {model_file}")
        return

    try:
        print(f"Loading TST model from {model_file}")
        model_state = torch.load(model_file, map_location='cpu')
        
        input_dim = 7
        hidden_dim = 32
        num_heads = 2
        ff_dim = 64
        num_layers = 1
        dropout = 0.1
        num_classes = 3
        
        model = TimeSeriesTransformer(
            input_dim=input_dim,
            hidden_dim=hidden_dim,
            num_heads=num_heads,
            ff_dim=ff_dim,
            num_layers=num_layers,
            dropout=dropout,
            num_classes=num_classes
        )
        model.load_state_dict(model_state)
        model.eval()
        print("Model loaded successfully")
        
        sample_input = torch.zeros(1, 15, input_dim, dtype=torch.float32)
        print("Converting to ONNX...")
        onnx_model = convert_to_onnx(model, type="pytorch", sample_input=sample_input)
        print("ONNX conversion successful")
        
        onnx_path = "test_tst.onnx"
        import onnx
        onnx.save(onnx_model, onnx_path)
        print(f"Saved ONNX model to {onnx_path}")
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_tst_conversion()
