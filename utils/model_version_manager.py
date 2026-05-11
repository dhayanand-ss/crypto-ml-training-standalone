import os
import json
import logging
import shutil
from datetime import datetime

logger = logging.getLogger(__name__)

class ModelVersionManager:
    """
    Manages model versions (v1, v2, v3) using a local JSON registry.
    v1: Baseline (frozen)
    v2: Previous
    v3: Latest
    """
    def __init__(self, models_dir="models"):
        self.models_dir = models_dir
        self.registry_path = os.path.join(self.models_dir, "version_registry.json")
        self.registry = self._load_registry()

    def _load_registry(self):
        if os.path.exists(self.registry_path):
            try:
                with open(self.registry_path, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Error loading registry: {e}")
        return {"metadata": {"last_updated": datetime.now().isoformat(), "version_history": []}}

    def _save_registry(self):
        try:
            self.registry.setdefault("metadata", {})["last_updated"] = datetime.now().isoformat()
            with open(self.registry_path, 'w') as f:
                json.dump(self.registry, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving registry: {e}")

    def get_model_path(self, model_type, version):
        """
        Get the path for a specific model version.
        """
        if model_type not in self.registry:
            return None
        
        v_key = f"v{version}"
        model_data = self.registry[model_type].get(v_key)
        if model_data:
            path = model_data.get("path")
            if path:
                # Handle relative paths (make them absolute based on cwd)
                # The registry might contain paths like "models\\lightgbm\\..."
                # We assume running from root
                if os.path.exists(path):
                    return os.path.abspath(path)
                
                # Check if it is relative to models dir
                rel_path = os.path.join(self.models_dir, os.path.basename(path)) # Weak heuristic?
                # Better: clean path separators
                clean_path = path.replace("\\", os.sep).replace("/", os.sep)
                if os.path.exists(clean_path):
                    return os.path.abspath(clean_path)
                
                # Try simple relative to root
                if os.path.exists(os.path.abspath(clean_path)):
                    return os.path.abspath(clean_path)
                    
        return None

    def initialize_baseline(self, model_type, source_path, metadata=None):
        """
        Initialize v1 baseline from a source model file.
        """
        logger.info(f"Initializing baseline for {model_type} from {source_path}")
        self._register_version(model_type, "1", source_path, metadata)

    def register_new_model(self, model_type, source_path, metadata=None):
        """
        Register a new model as v3 (Latest), moving current v3 to v2 (Previous).
        """
        logger.info(f"Registering new model for {model_type} from {source_path}")
        
        # 1. Promote current v3 to v2
        current_v3_path = self.get_model_path(model_type, "3")
        
        # Check if we have a valid v3 to move
        if current_v3_path and os.path.exists(current_v3_path):
             # Define v2 target
             target_dir_v2 = os.path.join(self.models_dir, model_type, "v2")
             os.makedirs(target_dir_v2, exist_ok=True)
             filename = os.path.basename(current_v3_path)
             target_path_v2 = os.path.join(target_dir_v2, filename)
             
             try:
                 shutil.copy2(current_v3_path, target_path_v2)
                 # Get v3 metadata to preserve it
                 v3_meta = self.registry.get(model_type, {}).get("v3", {}).get("metadata")
                 self._update_registry_entry(model_type, "2", target_path_v2, v3_meta)
                 logger.info(f"Promoted v3 to v2: {target_path_v2}")
             except Exception as e:
                 logger.error(f"Failed to promote v3 to v2: {e}")

        # 2. Register new model as v3
        self._register_version(model_type, "3", source_path, metadata)
        return "3"

    def _register_version(self, model_type, version, source_path, metadata):
        target_dir = os.path.join(self.models_dir, model_type, f"v{version}")
        os.makedirs(target_dir, exist_ok=True)
        filename = os.path.basename(source_path)
        target_path = os.path.join(target_dir, filename)
        
        try:
            shutil.copy2(source_path, target_path)
            self._update_registry_entry(model_type, version, target_path, metadata)
            logger.info(f"Registered {model_type} v{version} at {target_path}")
        except Exception as e:
            logger.error(f"Failed to register version {version}: {e}")
            raise

    def _update_registry_entry(self, model_type, version, path, metadata):
        if model_type not in self.registry:
            self.registry[model_type] = {}
        
        v_key = f"v{version}"
        # Store relative path for portability if possible, else absolute
        # using generic relative path logic
        try:
            rel_path = os.path.relpath(path, start=os.getcwd())
        except ValueError:
            rel_path = path

        self.registry[model_type][v_key] = {
            "path": rel_path,
            "created_at": datetime.now().isoformat(),
            "metadata": metadata or {}
        }
        
        # Update history
        history_entry = {
            "model_type": model_type,
            "action": "update",
            "version": version,
            "timestamp": datetime.now().isoformat()
        }
        self.registry.setdefault("metadata", {}).setdefault("version_history", []).append(history_entry)
        
        self._save_registry()


class ConsumerManager:
    """
    Manager for controlling model consumers (e.g. restart on model update).
    In standalone/local mode, this might just log actions.
    """
    def __init__(self, version_manager):
        self.version_manager = version_manager

    def stop_consumers(self, model_type, versions):
        logger.info(f"Request to stop consumers for {model_type} versions {versions}")
        # Add actual logic here if needed (e.g. docker restart)

    def start_consumers(self, model_type, versions):
        logger.info(f"Request to start consumers for {model_type} versions {versions}")
