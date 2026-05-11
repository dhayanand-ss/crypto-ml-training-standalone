import os
import json
import logging
from pathlib import Path


logger = logging.getLogger(__name__)

class ModelManager:
    """
    Model Manager for MLflow and local registry integration.
    """
    def __init__(self, tracking_uri=None, models_dir=None):
        # Resolve project root based on this file location
        project_root = Path(__file__).resolve().parent.parent.parent
        
        # Default models directory
        default_models_dir = project_root / "models"
        
        # If models_dir explicitly provided, use it, otherwise use default
        if models_dir:
            resolved_models_dir = Path(models_dir).resolve()
        elif default_models_dir.exists():
            resolved_models_dir = default_models_dir
        elif Path("/app/models").exists():
            resolved_models_dir = Path("/app/models")
        else:
            raise FileNotFoundError(
                f"Models directory not found. Checked: {default_models_dir} and /app/models"
            )
            
        self.models_dir = str(resolved_models_dir)
        self.registry_path = str(resolved_models_dir / "version_registry.json")
        
        logger.info(f"Resolved models directory: {self.models_dir}")
        logger.info(f"Resolved registry path: {self.registry_path}")
            
        self.local_registry = self._load_registry()

    def _load_registry(self):
        if os.path.exists(self.registry_path):
            try:
                with open(self.registry_path, 'r') as f:
                    registry = json.load(f)
                    logger.info(f"Loaded local model registry from {self.registry_path}")
                    return registry
            except Exception as e:
                logger.error(f"Error loading registry: {e}")
        else:
            logger.warning(f"Local registry not found at {self.registry_path}")
        return {}

    def load_model(self, model_name, version, model_type="lightgbm"):
        """Load model from local registry or MLflow."""
        # Try local first
        local_path = self.get_local_model_path(model_name, version)
        if local_path and os.path.exists(local_path):
            logger.info(f"Loading local {model_type} model from {local_path}")
            try:
                if model_type == "lightgbm":
                    import lightgbm as lgb
                    # Use model_str for better compatibility across environments/paths
                    with open(local_path, 'r') as f:
                        content = f.read()
                    return lgb.Booster(model_str=content), version
                elif model_type == "pytorch":
                    import torch
                    # Note: Loading raw .pth might require the model class in the same scope
                    # or it might be a scripted/traced model.
                    return torch.load(local_path, map_location='cpu'), version
            except Exception as e:
                logger.error(f"Failed to load local model from {local_path}: {e}")
        
        # Fallback to MLflow - REMOVED
        # if self.client:
        #    pass
        
        raise ValueError(f"Model {model_name} version {version} not found locally or in MLflow")

    def get_local_model_path(self, model_name, version):
        """Map model name and version to a local file path using the registry."""
        name_lower = model_name.lower()
        key = None
        if "lightgbm" in name_lower: key = "lightgbm"
        elif "tst" in name_lower: key = "tst"
        elif "finbert" in name_lower: key = "finbert"
        elif "ensemble" in name_lower: key = "ensemble"
        
        if key and key in self.local_registry:
            v_key = f"v{version}" if not str(version).startswith("v") else version
            # Also try ONNX first as standard fallback
            onnx_path = Path(self.models_dir) / "onnx" / f"{key}_{version}.onnx"
            if onnx_path.exists():
                return str(onnx_path.resolve())

            model_data = self.local_registry[key].get(v_key)
            if model_data and model_data.get("path"):
                # Path in registry is relative to project root, e.g., "models\\lightgbm\\v3\\lgb_model.txt"
                rel_path = Path(model_data["path"])

                # If already absolute, use directly
                if rel_path.is_absolute():
                    if rel_path.exists():
                        return str(rel_path)
                    return None
                
                # Otherwise resolve relative to project root
                project_root = Path(self.models_dir).parent
                full_path = project_root / rel_path
                
                if full_path.exists():
                    return str(full_path.resolve())
                
                # Also try resolving relative to models_dir (extra safety)
                alt_path = Path(self.models_dir) / rel_path.name
                
                if alt_path.exists():
                    return str(alt_path.resolve())
                
                logger.error(f"Model file not found. Tried: {full_path} and {alt_path}")
                
                return None
        return None

    def load_onnx_model(self, model_name, version):
        """Load ONNX model artifact from MLflow or local models/onnx directory."""
        import onnxruntime as ort
        import tempfile
        
        # Try local ONNX first
        onnx_path = Path(self.models_dir) / "onnx" / f"{model_name}_{version}.onnx"
        if onnx_path.exists():
            logger.info(f"Loading local ONNX model from {onnx_path}")
            return ort.InferenceSession(str(onnx_path))
            
        # Fallback to MLflow - REMOVED
        
        raise ValueError(f"ONNX model {model_name} version {version} not found at {onnx_path}")
