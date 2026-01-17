#!/usr/bin/env python3
"""
Parallel Training Runner for Vast AI Instances

This module runs all training scripts sequentially.
Each training script will update its own status in Firestore.
"""

import os
import sys
import importlib
from pathlib import Path
import time

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

def run_training_script(script_module, script_name):
    """
    Run a training script by importing and calling its main() function.
    
    Args:
        script_module: Python module path (e.g., "utils.trainer.trl_train")
        script_name: Human-readable name (e.g., "TRL")
    
    Returns:
        (script_name, success: bool, error_message: str)
    """
    print(f"\n{'='*60}")
    print(f"Starting {script_name} Training")
    print(f"{'='*60}")
    
    try:
        # Import the module
        module = importlib.import_module(script_module)
        
        # Call main() if it exists
        if hasattr(module, 'main'):
            module.main()
            print(f"\n{script_name} training completed successfully!")
            return (script_name, True, None)
        else:
            error_msg = f"{script_name} module has no main() function"
            print(f"\n{error_msg}")
            return (script_name, False, error_msg)
            
    except KeyboardInterrupt:
        error_msg = f"{script_name} training interrupted by user"
        print(f"\n{error_msg}")
        return (script_name, False, error_msg)
    except Exception as e:
        error_msg = f"{script_name} training error: {str(e)}"
        print(f"\n{error_msg}")
        import traceback
        traceback.print_exc()
        return (script_name, False, error_msg)


def run_all_training_sequential():
    """
    Run all training scripts sequentially.
    This ensures each script can update status independently.
    Continues running even if one script fails.
    """
    print("=" * 60)
    print("Starting All Training Scripts (Sequential)")
    print("=" * 60)
    
    # Define training scripts to run
    training_scripts = [
        ("utils.trainer.trl_train", "TRL"),
        ("trainer.lightgbm_trainer", "LightGBM"),
        ("trainer.time_series_transformer", "TST"),
    ]
    
    results = []
    
    for script_module, script_name in training_scripts:
        print(f"\n{'='*60}")
        print(f"Running {script_name} Training")
        print(f"{'='*60}")
        
        result = run_training_script(script_module, script_name)
        results.append(result)
        
        # Continue to next script even if this one failed
        if not result[1]:  # If failed
            print(f"\n⚠️  {script_name} training failed, but continuing with next script...")
        
        # Small delay between scripts
        time.sleep(2)
    
    # Print summary
    print("\n" + "=" * 60)
    print("Training Summary")
    print("=" * 60)
    
    for script_name, success, error_msg in results:
        status = "✅ SUCCESS" if success else "❌ FAILED"
        print(f"{script_name}: {status}")
        if error_msg:
            print(f"  Error: {error_msg}")
    
    # Return success if at least one passed (allows partial success)
    any_success = any(success for _, success, _ in results)
    if any_success:
        print("\n✓ At least one training script completed successfully")
        return 0
    else:
        print("\n✗ All training scripts failed")
        return 1

def upload_results_to_gcs():
    """Upload trained models to GCS for retrieval by Airflow worker."""
    print("\n" + "=" * 60)
    print("Uploading Results to GCS")
    print("=" * 60)
    
    try:
        from trainer.train_utils import S3Manager, S3_AVAILABLE
        if not S3_AVAILABLE:
            print("GCSManager not available. Skipping upload.")
            return

        gcs_manager = S3Manager(bucket='mlops-new')
        models_dir = project_root / "models"
        
        if not models_dir.exists():
            print("No models directory found to upload.")
            return

        # Create a zip of the models directory
        print("Zipping models directory...")
        import shutil
        zip_name = project_root / "models_latest"
        shutil.make_archive(str(zip_name), 'zip', str(models_dir))
        zip_file = f"{zip_name}.zip"
        
        # Upload to GCS
        print(f"Uploading {zip_file} to GCS...")
        gcs_manager.upload_file(zip_file, "training_artifacts/models_latest.zip")
        print("Upload complete!")
        
        # Clean up zip
        os.remove(zip_file)
        
    except Exception as e:
        print(f"Failed to upload results to GCS: {e}")
        import traceback
        traceback.print_exc()

def main():
    """Main entry point - runs all training scripts sequentially"""
    exit_code = run_all_training_sequential()
    
    # Upload results if at least one script succeeded (or simply always upload what we have)
    if exit_code == 0:
        upload_results_to_gcs()
        
    sys.exit(exit_code)


if __name__ == "__main__":
    main()

