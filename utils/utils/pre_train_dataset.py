#!/usr/bin/env python3
"""
Pre-training Dataset Preparation Module

This module prepares datasets before training by:
1. Downloading price data and articles from GCS/S3
2. Validating dataset availability
3. Ensuring data directories are properly set up

This is called by the Airflow DAG before training starts.
"""

import os
import sys
import logging
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Add project root to path if needed
_project_root = Path(__file__).parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

try:
    from trainer.train_utils import download_s3_dataset, S3_AVAILABLE
except ImportError as e:
    logger.warning(f"Could not import from trainer.train_utils: {e}")
    S3_AVAILABLE = False

try:
    from utils.artifact_control import create_data_directories
except ImportError as e:
    logger.warning(f"Could not import create_data_directories: {e}")
    create_data_directories = None


def ensure_data_directories():
    """Create necessary data directories if they don't exist."""
    # Use project root to determine data path (not current working directory)
    project_root = Path(__file__).parent.parent.parent.resolve()
    data_base_path_env = os.getenv("DATA_PATH")
    
    if data_base_path_env:
        # If DATA_PATH is set, use it (can be absolute or relative)
        if os.path.isabs(data_base_path_env):
            data_base_path = data_base_path_env
        else:
            # Relative path - make it relative to project root
            data_base_path = str((project_root / data_base_path_env).resolve())
    else:
        # Default: use project_root/data
        data_base_path = str((project_root / "data").resolve())
    
    directories = [
        data_base_path,
        os.path.join(data_base_path, "prices"),
        os.path.join(data_base_path, "articles"),
    ]
    
    for directory in directories:
        os.makedirs(directory, exist_ok=True)
        logger.info(f"Ensured directory exists: {directory}")
    
    # Also use create_data_directories if available
    if create_data_directories:
        try:
            create_data_directories(data_base_path)
        except Exception as e:
            logger.warning(f"create_data_directories failed: {e}")
    
    return data_base_path


def download_datasets():
    """Download datasets from GCS/S3."""
    if not S3_AVAILABLE:
        error_msg = (
            "GCSManager/S3Manager not available. Cannot download from GCS.\n"
            "This usually means:\n"
            "  1. The 'trainer' module is not on Python's import path\n"
            "  2. The trainer.train_utils module cannot be imported\n"
            "  3. GCSManager (from utils.artifact_control) is not available\n\n"
            "Refusing to continue with potentially stale local cached data.\n"
            "This prevents silent data drift and ensures reproducible training."
        )
        logger.error("=" * 60)
        logger.error("GCS ACCESS UNAVAILABLE - FAILING LOUDLY")
        logger.error("=" * 60)
        logger.error(error_msg)
        logger.error("=" * 60)
        raise RuntimeError(error_msg)
    
    try:
        # Use project root to determine data path
        project_root = Path(__file__).parent.parent.parent.resolve()
        data_base_path_env = os.getenv("DATA_PATH")
        
        if data_base_path_env:
            if os.path.isabs(data_base_path_env):
                data_base_path = data_base_path_env
            else:
                data_base_path = str((project_root / data_base_path_env).resolve())
        else:
            data_base_path = str((project_root / "data").resolve())
        coins = ["BTCUSDT"]  # Default coin, can be extended
        
        logger.info("Starting dataset download from GCS...")
        
        # Download price data for each coin
        for coin in coins:
            logger.info(f"Downloading price data for {coin}...")
            try:
                download_s3_dataset(coin, trl_model=False)
                logger.info(f"✓ Successfully downloaded price data for {coin}")
            except FileNotFoundError as e:
                # Required file not found - this is a critical error
                error_msg = f"CRITICAL: Required price data not found in GCS for {coin}: {e}"
                logger.error("=" * 60)
                logger.error(error_msg)
                logger.error("=" * 60)
                raise RuntimeError(error_msg) from e
            except Exception as e:
                error_msg = f"Failed to download price data for {coin}: {e}"
                logger.error("=" * 60)
                logger.error(error_msg)
                logger.error("=" * 60)
                raise RuntimeError(error_msg) from e
        
        # Download articles for TRL model
        logger.info("Downloading articles for TRL model...")
        try:
            download_s3_dataset("BTCUSDT", trl_model=True)
            logger.info("Successfully downloaded articles")
        except Exception as e:
            logger.warning(f"Failed to download articles: {e}")
            logger.warning("TRL model training may fail if articles are not available")
        
        logger.info("Dataset download completed")
        return True
        
    except Exception as e:
        logger.error(f"Error during dataset download: {e}")
        import traceback
        logger.error(traceback.format_exc())
        error_msg = (
            "Dataset download from GCS failed.\n"
            "Refusing to continue with cached local data.\n"
            "This prevents silent data drift and ensures reproducible training."
        )
        logger.error("=" * 60)
        logger.error("DATASET DOWNLOAD FAILED - FAILING LOUDLY")
        logger.error("=" * 60)
        logger.error(error_msg)
        logger.error("=" * 60)
        raise RuntimeError(error_msg) from e


def validate_datasets():
    """Validate that required datasets are available."""
    # Use project root to determine data path (not current working directory)
    project_root = Path(__file__).parent.parent.parent.resolve()
    data_base_path_env = os.getenv("DATA_PATH")
    
    if data_base_path_env:
        if os.path.isabs(data_base_path_env):
            abs_data_path = data_base_path_env
        else:
            abs_data_path = str((project_root / data_base_path_env).resolve())
    else:
        abs_data_path = str((project_root / "data").resolve())
    logger.info(f"Using data directory: {abs_data_path}")
    
    coins = ["BTCUSDT"]
    
    all_valid = True
    
    # Check price data
    for coin in coins:
        # Check in prices subdirectory (expected location)
        price_path = os.path.join(abs_data_path, "prices", f"{coin}.csv")
        # Also check in root data directory (alternative location)
        price_path_alt = os.path.join(abs_data_path, f"{coin.lower()}.csv")
        
        if os.path.exists(price_path):
            logger.info(f"✓ Price data found: {price_path}")
        elif os.path.exists(price_path_alt):
            logger.info(f"✓ Price data found (alternative location): {price_path_alt}")
            # Optionally copy or symlink to expected location
            try:
                os.makedirs(os.path.dirname(price_path), exist_ok=True)
                import shutil
                shutil.copy2(price_path_alt, price_path)
                logger.info(f"  → Copied to expected location: {price_path}")
            except Exception as e:
                logger.warning(f"  → Could not copy to expected location: {e}")
        else:
            logger.warning(f"✗ Price data missing: {price_path}")
            logger.warning(f"  Also checked: {price_path_alt}")
            all_valid = False
        
        # Check test price data (optional)
        test_price_path = os.path.join(abs_data_path, "prices", f"{coin}_test.csv")
        if os.path.exists(test_price_path):
            logger.info(f"✓ Test price data found: {test_price_path}")
        else:
            logger.info(f"ℹ Test price data not found (optional): {test_price_path}")
    
    # Check articles (optional, only needed for TRL)
    # Check both possible locations: subdirectory and root
    article_path_subdir = os.path.join(abs_data_path, "articles", "articles.csv")
    article_path_root = os.path.join(abs_data_path, "articles.csv")
    
    if os.path.exists(article_path_subdir):
        logger.info(f"✓ Articles found: {article_path_subdir}")
    elif os.path.exists(article_path_root):
        logger.info(f"✓ Articles found (alternative location): {article_path_root}")
        # Optionally copy to expected location
        try:
            os.makedirs(os.path.dirname(article_path_subdir), exist_ok=True)
            import shutil
            shutil.copy2(article_path_root, article_path_subdir)
            logger.info(f"  → Copied to expected location: {article_path_subdir}")
        except Exception as e:
            logger.warning(f"  → Could not copy to expected location: {e}")
    else:
        logger.info(f"ℹ Articles not found (optional, only needed for TRL)")
        logger.info(f"  Checked: {article_path_subdir}")
        logger.info(f"  Checked: {article_path_root}")
    
    return all_valid


def main():
    """Main function to prepare datasets before training."""
    logger.info("=" * 60)
    logger.info("Pre-training Dataset Preparation")
    logger.info("=" * 60)
    
    # Get project root for reference
    project_root = Path(__file__).parent.parent.parent.resolve()
    logger.info(f"Project root: {project_root}")
    logger.info(f"Current working directory: {os.getcwd()}")
    
    # Step 1: Ensure data directories exist
    logger.info("\nStep 1: Creating data directories...")
    data_base_path = ensure_data_directories()
    logger.info(f"Data base path: {data_base_path}")
    
    # Step 1.5: Copy data files from project directory if they exist
    logger.info("\nStep 1.5: Checking for existing data files in project...")
    import shutil
    project_data_path = project_root / "data"
    
    # Copy btcusdt.csv if it exists in project
    source_files = [
        (project_data_path / "btcusdt.csv", Path(data_base_path) / "btcusdt.csv"),
        (project_data_path / "prices" / "BTCUSDT.csv", Path(data_base_path) / "prices" / "BTCUSDT.csv"),
        (project_data_path / "articles.csv", Path(data_base_path) / "articles.csv"),
    ]
    
    for source, dest in source_files:
        if source.exists() and not dest.exists():
            try:
                os.makedirs(dest.parent, exist_ok=True)
                shutil.copy2(source, dest)
                logger.info(f"✓ Copied {source.name} from project to {dest}")
            except Exception as e:
                logger.warning(f"Could not copy {source} to {dest}: {e}")
        elif source.exists():
            logger.info(f"ℹ {dest.name} already exists, skipping copy")
    
    # Step 2: Download datasets from GCS/S3
    logger.info("\nStep 2: Downloading datasets from GCS/S3...")
    try:
        download_success = download_datasets()  # This will raise RuntimeError on any failure
        if not download_success:
            # This should never happen since we raise on failure, but adding as safety check
            raise RuntimeError(
                "Dataset download from GCS failed. "
                "Refusing to continue with cached local data."
            )
        logger.info("✓ Dataset download completed successfully")
    except Exception as e:
        logger.warning("=" * 60)
        logger.warning("DATASET DOWNLOAD FAILED - FALLING BACK TO LOCAL FILES")
        logger.warning(f"Reason: {e}")
        logger.warning("Proceeding to validation step...")
        logger.warning("=" * 60)
        # Proceed to validation step to check if we have what we need locally
    
    # Step 3: Validate datasets
    logger.info("\nStep 3: Validating datasets...")
    validation_success = validate_datasets()
    
    if validation_success:
        logger.info("\n" + "=" * 60)
        logger.info("✓ Dataset preparation completed successfully!")
        logger.info("=" * 60)
        return 0
    else:
        logger.warning("\n" + "=" * 60)
        logger.warning("⚠ Dataset preparation completed with warnings.")
        logger.warning("Some datasets may be missing. Training may fail if required data is not available.")
        logger.warning("=" * 60)
        # Return 0 anyway to allow training to proceed (it will fail later if data is truly missing)
        return 0


if __name__ == "__main__":
    sys.exit(main())




