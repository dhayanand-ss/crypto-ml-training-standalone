"""
Model Version Manager
Manages v1 (baseline), v2 (previous), v3 (latest) model versions
Implements version shifting, rollback, and consumer management
"""

import os
import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, List, Tuple
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ModelVersionManager:
    """
    Manages model versions for production deployment.
    
    Version roles:
    - v1: Baseline/Stable (never deleted, baseline for comparison)
    - v2: Previous version (before latest, used for comparison/rollback)
    - v3: Latest/Newest (most recently trained, becomes v2 when new model trained)
    
    When a new model is trained:
    1. Stop v2 and v3 consumers
    2. Shift versions: old v3 → new v2, new model → new v3
    3. v1 stays unchanged
    4. Restart consumers for v2 and v3
    """
    
    def __init__(self, base_models_dir: str = "models"):
        """
        Initialize version manager.
        
        Args:
            base_models_dir: Base directory for model storage
        """
        self.base_models_dir = Path(base_models_dir)
        self.version_registry_path = self.base_models_dir / "version_registry.json"
        self.registry = self._load_registry()
        
        # Ensure base directory exists
        self.base_models_dir.mkdir(parents=True, exist_ok=True)
    
    def _load_registry(self) -> Dict:
        """Load version registry from disk."""
        if self.version_registry_path.exists():
            try:
                with open(self.version_registry_path, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Error loading registry: {e}. Creating new registry.")
        
        # Initialize empty registry
        return {
            "lightgbm": {"v1": None, "v2": None, "v3": None},
            "tst": {"v1": None, "v2": None, "v3": None},
            "finbert": {"v1": None, "v2": None, "v3": None},
            "ensemble": {"v1": None, "v2": None, "v3": None},
            "metadata": {
                "last_updated": None,
                "version_history": []
            }
        }
    
    def _save_registry(self):
        """Save version registry to disk."""
        self.registry["metadata"]["last_updated"] = datetime.now().isoformat()
        with open(self.version_registry_path, 'w') as f:
            json.dump(self.registry, f, indent=2)
    
    def _get_model_dir(self, model_type: str, version: str) -> Path:
        """Get directory path for a specific model version."""
        return self.base_models_dir / model_type / f"v{version}"
    
    def _get_model_path(self, model_type: str, version: str, filename: str) -> Path:
        """Get full path for a model file."""
        return self._get_model_dir(model_type, version) / filename
    
    def initialize_baseline(self, model_type: str, model_path: str, metadata: Optional[Dict] = None):
        """
        Initialize v1 (baseline) version. Only called once per model type.
        
        Args:
            model_type: Type of model ('lightgbm', 'tst', 'finbert', 'ensemble')
            model_path: Path to the model file to use as baseline
            metadata: Optional metadata about the model
        """
        if self.registry[model_type]["v1"] is not None:
            logger.warning(f"v1 baseline already exists for {model_type}. Skipping initialization.")
            return
        
        v1_dir = self._get_model_dir(model_type, "1")
        v1_dir.mkdir(parents=True, exist_ok=True)
        
        # Copy model to v1 directory
        source_path = Path(model_path)
        if not source_path.exists():
            raise FileNotFoundError(f"Model file not found: {model_path}")
        
        dest_path = v1_dir / source_path.name
        shutil.copy2(source_path, dest_path)
        
        # Copy associated files (e.g., scaler, features)
        if model_type == "lightgbm":
            features_path = source_path.parent / source_path.name.replace('.txt', '_features.pkl')
            if features_path.exists():
                shutil.copy2(features_path, v1_dir / features_path.name)
        elif model_type == "tst":
            scaler_path = source_path.parent / source_path.name.replace('tst_model.pth', 'tst_scaler.pkl')
            if scaler_path.exists():
                shutil.copy2(scaler_path, v1_dir / scaler_path.name)
        
        # Update registry
        self.registry[model_type]["v1"] = {
            "path": str(dest_path),
            "created_at": datetime.now().isoformat(),
            "metadata": metadata or {}
        }
        
        self._save_registry()
        logger.info(f"Initialized v1 baseline for {model_type} at {dest_path}")
    
    def register_new_model(self, model_type: str, model_path: str, metadata: Optional[Dict] = None) -> str:
        """
        Register a newly trained model. Shifts versions and returns the new version.
        
        Args:
            model_type: Type of model ('lightgbm', 'tst', 'finbert', 'ensemble')
            model_path: Path to the newly trained model
            metadata: Optional metadata about the model
            
        Returns:
            Version string ('1', '2', or '3') where the model was saved
        """
        source_path = Path(model_path)
        if not source_path.exists():
            raise FileNotFoundError(f"Model file not found: {model_path}")
        
        # Shift versions: v3 → v2, new → v3
        # Handle two scenarios:
        # 1. If v3 exists: Move v3 → v2, then new → v3
        # 2. If v3 doesn't exist but v1 exists: Create v2 from v1, then new → v3
        if self.registry[model_type]["v3"] is not None:
            # Scenario 1: v3 exists - shift it to v2
            old_v3_path = Path(self.registry[model_type]["v3"]["path"])
            v2_dir = self._get_model_dir(model_type, "2")
            v2_dir.mkdir(parents=True, exist_ok=True)
            
            # Copy v3 files to v2
            if old_v3_path.exists():
                v2_path = v2_dir / old_v3_path.name
                shutil.copy2(old_v3_path, v2_path)
                
                # Copy associated files
                self._copy_associated_files(model_type, old_v3_path.parent, v2_dir)
                
                # Update registry for v2
                self.registry[model_type]["v2"] = {
                    "path": str(v2_path),
                    "created_at": self.registry[model_type]["v3"]["created_at"],
                    "promoted_at": datetime.now().isoformat(),
                    "metadata": self.registry[model_type]["v3"]["metadata"]
                }
                logger.info(f"Promoted v3 to v2 for {model_type}")
        elif self.registry[model_type]["v1"] is not None and self.registry[model_type]["v2"] is None:
            # Scenario 2: v3 doesn't exist, but v1 exists and v2 is missing
            # Create v2 from v1 (first model after migration/baseline)
            v1_path = Path(self.registry[model_type]["v1"]["path"])
            v2_dir = self._get_model_dir(model_type, "2")
            v2_dir.mkdir(parents=True, exist_ok=True)
            
            if v1_path.exists():
                v2_path = v2_dir / v1_path.name
                shutil.copy2(v1_path, v2_path)
                
                # Copy associated files
                self._copy_associated_files(model_type, v1_path.parent, v2_dir)
                
                # Update registry for v2
                self.registry[model_type]["v2"] = {
                    "path": str(v2_path),
                    "created_at": self.registry[model_type]["v1"]["created_at"],
                    "created_from_v1": True,
                    "metadata": self.registry[model_type]["v1"]["metadata"].copy()
                }
                logger.info(f"Created v2 from v1 for {model_type} (first model after baseline)")
        
        # Save new model as v3
        v3_dir = self._get_model_dir(model_type, "3")
        v3_dir.mkdir(parents=True, exist_ok=True)
        
        dest_path = v3_dir / source_path.name
        shutil.copy2(source_path, dest_path)
        
        # Copy associated files
        self._copy_associated_files(model_type, source_path.parent, v3_dir)
        
        # Update registry for v3
        self.registry[model_type]["v3"] = {
            "path": str(dest_path),
            "created_at": datetime.now().isoformat(),
            "metadata": metadata or {}
        }
        
        # Record version history
        self.registry["metadata"]["version_history"].append({
            "model_type": model_type,
            "action": "new_model_registered",
            "timestamp": datetime.now().isoformat(),
            "new_version": "3",
            "previous_v3_promoted_to_v2": self.registry[model_type]["v2"] is not None
        })
        
        self._save_registry()
        logger.info(f"Registered new model for {model_type} as v3 at {dest_path}")
        
        return "3"
    
    def _copy_associated_files(self, model_type: str, source_dir: Path, dest_dir: Path):
        """Copy associated files (scaler, features, etc.) for a model."""
        if model_type == "lightgbm":
            # Copy features file
            for file in source_dir.glob("*_features.pkl"):
                shutil.copy2(file, dest_dir / file.name)
        elif model_type == "tst":
            # Copy scaler file
            for file in source_dir.glob("*scaler*.pkl"):
                shutil.copy2(file, dest_dir / file.name)
    
    def get_model_path(self, model_type: str, version: str) -> Optional[str]:
        """
        Get path to a specific model version.
        
        Args:
            model_type: Type of model
            version: Version ('1', '2', or '3')
            
        Returns:
            Path to model file or None if not found
        """
        if version not in ["1", "2", "3"]:
            raise ValueError(f"Invalid version: {version}. Must be '1', '2', or '3'")
        
        version_info = self.registry[model_type].get(f"v{version}")
        if version_info is None:
            return None
        
        path = Path(version_info["path"])
        if path.exists():
            return str(path)
        
        return None
    
    def get_all_versions(self, model_type: str) -> Dict[str, Optional[str]]:
        """
        Get paths for all versions of a model type.
        
        Args:
            model_type: Type of model
            
        Returns:
            Dictionary with 'v1', 'v2', 'v3' keys and paths (or None)
        """
        return {
            "v1": self.get_model_path(model_type, "1"),
            "v2": self.get_model_path(model_type, "2"),
            "v3": self.get_model_path(model_type, "3")
        }
    
    def rollback_to_version(self, model_type: str, target_version: str):
        """
        Rollback to a specific version by promoting it to v3.
        
        Args:
            model_type: Type of model
            target_version: Version to rollback to ('1' or '2')
        """
        if target_version not in ["1", "2"]:
            raise ValueError("Can only rollback to v1 or v2")
        
        target_path = self.get_model_path(model_type, target_version)
        if target_path is None:
            raise ValueError(f"Version {target_version} not found for {model_type}")
        
        # Save current v3 as backup
        if self.registry[model_type]["v3"] is not None:
            backup_dir = self.base_models_dir / model_type / "backups"
            backup_dir.mkdir(parents=True, exist_ok=True)
            backup_path = backup_dir / f"v3_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            old_v3_path = Path(self.registry[model_type]["v3"]["path"])
            if old_v3_path.exists():
                shutil.copytree(old_v3_path.parent, backup_path, dirs_exist_ok=True)
                logger.info(f"Backed up v3 to {backup_path}")
        
        # Copy target version to v3
        v3_dir = self._get_model_dir(model_type, "3")
        v3_dir.mkdir(parents=True, exist_ok=True)
        
        source_dir = Path(target_path).parent
        for file in source_dir.iterdir():
            if file.is_file():
                shutil.copy2(file, v3_dir / file.name)
        
        # Update registry
        target_info = self.registry[model_type][f"v{target_version}"]
        self.registry[model_type]["v3"] = {
            "path": str(v3_dir / Path(target_path).name),
            "created_at": target_info["created_at"],
            "rolled_back_at": datetime.now().isoformat(),
            "metadata": target_info["metadata"]
        }
        
        # Record rollback in history
        self.registry["metadata"]["version_history"].append({
            "model_type": model_type,
            "action": "rollback",
            "timestamp": datetime.now().isoformat(),
            "target_version": target_version
        })
        
        self._save_registry()
        logger.info(f"Rolled back {model_type} to v{target_version}")
    
    def get_version_info(self, model_type: str, version: str) -> Optional[Dict]:
        """Get metadata for a specific version."""
        return self.registry[model_type].get(f"v{version}")
    
    def list_all_models(self) -> Dict:
        """List all models and their versions."""
        result = {}
        for model_type in ["lightgbm", "tst", "finbert", "ensemble"]:
            result[model_type] = {
                "v1": self.get_version_info(model_type, "1"),
                "v2": self.get_version_info(model_type, "2"),
                "v3": self.get_version_info(model_type, "3")
            }
        return result


class ConsumerManager:
    """
    Manages consumers for different model versions.
    In a production environment, this would interface with actual consumer processes.
    """
    
    def __init__(self, version_manager: ModelVersionManager):
        self.version_manager = version_manager
        self.active_consumers = {}  # Track active consumers
    
    def stop_consumers(self, model_type: str, versions: List[str] = ["2", "3"]):
        """
        Stop consumers for specific versions.
        
        Args:
            model_type: Type of model
            versions: List of versions to stop (default: ['2', '3'])
        """
        for version in versions:
            consumer_key = f"{model_type}_v{version}"
            if consumer_key in self.active_consumers:
                # In production, this would stop actual consumer processes
                logger.info(f"Stopping consumer for {model_type} v{version}")
                del self.active_consumers[consumer_key]
            else:
                logger.info(f"No active consumer found for {model_type} v{version}")
    
    def start_consumers(self, model_type: str, versions: List[str] = ["2", "3"]):
        """
        Start consumers for specific versions.
        
        Args:
            model_type: Type of model
            versions: List of versions to start (default: ['2', '3'])
        """
        for version in versions:
            model_path = self.version_manager.get_model_path(model_type, version)
            if model_path is None:
                logger.warning(f"Cannot start consumer for {model_type} v{version}: model not found")
                continue
            
            consumer_key = f"{model_type}_v{version}"
            # In production, this would start actual consumer processes
            self.active_consumers[consumer_key] = {
                "model_type": model_type,
                "version": version,
                "model_path": model_path,
                "started_at": datetime.now().isoformat()
            }
            logger.info(f"Started consumer for {model_type} v{version} at {model_path}")
    
    def get_active_consumers(self) -> Dict:
        """Get list of active consumers."""
        return self.active_consumers.copy()


def main():
    """Example usage of ModelVersionManager."""
    manager = ModelVersionManager()
    
    # Example: Initialize baseline
    # manager.initialize_baseline("lightgbm", "models/lgb_model.txt")
    
    # Example: Register new model
    # manager.register_new_model("lightgbm", "models/new_lgb_model.txt")
    
    # Example: Get model paths
    # paths = manager.get_all_versions("lightgbm")
    # print(paths)
    
    # Example: Rollback
    # manager.rollback_to_version("lightgbm", "1")
    
    print("Model Version Manager initialized")
    print(f"Registry location: {manager.version_registry_path}")


if __name__ == "__main__":
    main()


