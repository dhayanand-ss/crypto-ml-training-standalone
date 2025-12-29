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
    
    # Return success if all passed
    all_success = all(success for _, success, _ in results)
    return 0 if all_success else 1


def main():
    """Main entry point - runs all training scripts sequentially"""
    exit_code = run_all_training_sequential()
    sys.exit(exit_code)


if __name__ == "__main__":
    main()

