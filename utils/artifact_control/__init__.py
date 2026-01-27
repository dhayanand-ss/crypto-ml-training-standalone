"""
Artifact Control Module
Provides Google Cloud Storage and MLflow model management for crypto ML training.
"""

from .gcs_manager import GCSManager, create_data_directories

# Backward compatibility: alias GCSManager as S3Manager
# This allows existing code using S3Manager to work with GCS
S3Manager = GCSManager

try:
    from .model_manager import ModelManager
    __all__ = ['GCSManager', 'S3Manager', 'ModelManager', 'create_data_directories']
except ImportError:
    # ModelManager requires MLflow, which may not be available
    __all__ = ['GCSManager', 'S3Manager', 'create_data_directories']














