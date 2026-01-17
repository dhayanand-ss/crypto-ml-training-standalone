import os
import shutil
import logging
from pathlib import Path

# Configure logging
logger = logging.getLogger(__name__)

try:
    from trainer.train_utils import S3Manager, S3_AVAILABLE
except ImportError:
    S3_AVAILABLE = False

def download_models_from_gcs(project_root: Path):
    """
    Download and unzip trained models from GCS.
    
    Args:
        project_root: Path to the project root directory
    """
    print("=" * 60)
    print("Syncing Models from GCS")
    print("=" * 60)

    if not S3_AVAILABLE:
        logger.warning("GCSManager not available. Skipping model download.")
        return

    try:
        gcs_manager = S3Manager(bucket='mlops-new')
        zip_name = "models_latest.zip"
        gcs_path = f"training_artifacts/{zip_name}"
        local_zip = project_root / zip_name
        
        logger.info(f"Downloading {gcs_path} to {local_zip}...")
        
        # S3Manager.download_df is a wrapper for blob.download_to_filename
        # Logic: check if file exists? download_df doesn't return value.
        try:
            gcs_manager.download_df(str(local_zip), gcs_path)
        except Exception as e:
            logger.warning(f"Failed to download {gcs_path}: {e}")
            logger.warning("This is expected if no training run has completed and uploaded results yet.")
            return

        if local_zip.exists():
            models_dir = project_root / "models"
            models_dir.mkdir(parents=True, exist_ok=True)
            
            logger.info(f"Unzipping to {models_dir}...")
            shutil.unpack_archive(str(local_zip), str(models_dir))
            
            # Clean up zip
            os.remove(local_zip)
            logger.info("Models successfully synced from GCS.")
        else:
            logger.warning(f"Downloaded file not found at {local_zip}")
            
    except Exception as e:
        logger.error(f"Failed to sync models from GCS: {e}")
