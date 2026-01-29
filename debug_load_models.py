
import os
import sys
import logging
from pathlib import Path

# Setup paths
project_root = Path(__file__).resolve().parent
sys.path.append(str(project_root))

# Mock peft if missing (since we are debugging loading)
try:
    import peft
except ImportError:
    pass

from utils.artifact_control.model_manager import ModelManager

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Set env - Try the absolute path that we used


def test_load():
    print(f"Tracking URI: {os.environ['MLFLOW_TRACKING_URI']}")
    try:
        mm = ModelManager()
    except Exception as e:
        print(f"Failed to init ModelManager: {e}")
        return

    print("Testing direct load of BTCUSDT_lightgbm v6...")
    try:
        model, ver = mm.load_model("BTCUSDT_lightgbm", "6", model_type="lightgbm")
        print(f"Successfully loaded model: {type(model)}")
    except Exception as e:
        print(f"Failed to load model: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    test_load()
