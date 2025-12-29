"""
Run Complete ML Pipeline with Model Versioning
Main entry point for running the crypto ML training pipeline with v1/v2/v3 versioning
"""

import os
import sys

def main():
    """Run the complete crypto ML pipeline with versioning"""
    print("=" * 60)
    print("Crypto ML Training Pipeline with Model Versioning")
    print("=" * 60)
    print("This will train and integrate:")
    print("- FinBERT for sentiment analysis")
    print("- LightGBM for gradient boosting")
    print("- Time Series Transformer for sequence modeling")
    print("- Ensemble model combining all predictions")
    print()
    print("Model Versioning: v1 (baseline), v2 (previous), v3 (latest)")
    print()
    
    # Import and run simplified integrated model
    try:
        from simplified_integrated_model import SimplifiedIntegratedModel
        
        print("[OK] All dependencies loaded successfully")
        print("Starting pipeline with model versioning enabled...")
        print()
        
        # Initialize with versioning enabled
        model = SimplifiedIntegratedModel(use_versioning=True)
        
        # Run complete pipeline
        model.run_complete_pipeline()
        
        print()
        print("[SUCCESS] Pipeline completed successfully!")
        print("Check the results/ directory for visualizations")
        print("Check the models/ directory for saved models")
        print()
        print("Model versions are stored in:")
        print("- models/lightgbm/v1/, v2/, v3/")
        print("- models/tst/v1/, v2/, v3/")
        print("- models/version_registry.json")
        
    except ImportError as e:
        print(f"[ERROR] Missing dependencies: {e}")
        print("Please install required packages:")
        print("pip install -r requirements.txt")
        sys.exit(1)
    except Exception as e:
        print(f"[ERROR] Error running pipeline: {e}")
        import traceback
        traceback.print_exc()
        print("Please check the error message above for details.")
        sys.exit(1)

if __name__ == "__main__":
    main()



















