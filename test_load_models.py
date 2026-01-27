
import os
import sys
import logging
from pathlib import Path

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Set env var
os.environ["MLFLOW_TRACKING_URI"] = "http://localhost:5000"

# Add project root
project_root = Path(".").resolve()
sys.path.insert(0, str(project_root))

try:
    from utils.serve.fastapi_app import load_production_models, model_manager
    
    print(f"MLFLOW_TRACKING_URI: {os.environ.get('MLFLOW_TRACKING_URI')}")
    # print(f"ModelManager URI: {model_manager.tracking_uri}")
    
    print("Attempting to load production models...")
    models = load_production_models()
    print(f"Loaded {len(models)} models.")
    for k, v in models.items():
        print(f" - {k}: {v.get('type')}")
        
except Exception as e:
    logger.exception("Failed to run test")
