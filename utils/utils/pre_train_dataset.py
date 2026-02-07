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
    data_base_path = os.getenv("DATA_PATH", "data")
    
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


def download_datasets():
    """Download datasets from GCS/S3."""
    if not S3_AVAILABLE:
        logger.warning("GCSManager/S3Manager not available. Skipping dataset download.")
        logger.warning("Make sure datasets are available locally or configure GCS credentials.")
        return False
    
    try:
        data_base_path = os.getenv("DATA_PATH", "data")
        coins = ["BTCUSDT"]  # Default coin, can be extended
        
        logger.info("Starting dataset download from GCS...")
        
        # Download price data for each coin
        for coin in coins:
            logger.info(f"Downloading price data for {coin}...")
            try:
                download_s3_dataset(coin, trl_model=False)
                logger.info(f"Successfully downloaded price data for {coin}")
            except Exception as e:
                logger.error(f"Failed to download price data for {coin}: {e}")
                # Continue with other coins even if one fails
        
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
        return False


def validate_datasets():
    """Validate that required datasets are available."""
    data_base_path = os.getenv("DATA_PATH", "data")
    # Get absolute path to handle working directory issues
    if not os.path.isabs(data_base_path):
        # Try to resolve relative to current working directory
        abs_data_path = os.path.abspath(data_base_path)
    else:
        abs_data_path = data_base_path
    
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
    
    # Step 1: Ensure data directories exist
    logger.info("\nStep 1: Creating data directories...")
    ensure_data_directories()
    
    # Step 2: Download datasets from GCS/S3
    logger.info("\nStep 2: Downloading datasets from GCS/S3...")
    download_success = download_datasets()
    
    if not download_success:
        logger.warning("Dataset download had issues, but continuing with validation...")
    
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




