#!/usr/bin/env python3
"""
Check MLflow directly to see what's available
"""

import os
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent
sys.path.insert(0, str(project_root))

print("=" * 60)
print("Direct MLflow Check")
print("=" * 60)
print()

try:
    import mlflow
    from utils.artifact_control.model_manager import ModelManager
    
    mlflow_uri = "http://localhost:5000"
    print(f"Connecting to MLflow at: {mlflow_uri}")
    mlflow.set_tracking_uri(mlflow_uri)
    
    # Test connection
    experiments = mlflow.search_experiments()
    print(f"OK: Connected to MLflow")
    print(f"   Experiments: {len(experiments)}")
    
    # Check registered models
    model_manager = ModelManager(tracking_uri=mlflow_uri)
    registered_models = model_manager.client.search_registered_models()
    print(f"   Registered models: {len(registered_models)}")
    
    if not registered_models:
        print()
        print("ERROR: No models registered in MLflow")
        print("   Run: python register_models_to_mlflow.py")
        exit(1)
    
    print()
    print("Checking Production models and ONNX availability...")
    print()
    
    all_production = []
    for model in registered_models:
        model_name = model.name
        print(f"Model: {model_name}")
        
        # Get production versions
        try:
            prod_versions = model_manager.client.get_latest_versions(model_name, stages=["Production"])
            print(f"  Production versions: {len(prod_versions)}")
            
            for v in prod_versions:
                print(f"    Version {v.version}:")
                print(f"      Stage: {v.current_stage}")
                print(f"      Source: {v.source}")
                
                # Try to load ONNX
                try:
                    print(f"      Checking ONNX...")
                    session = model_manager.load_onnx_model(model_name, v.version)
                    print(f"      OK: ONNX model loaded successfully")
                    all_production.append((model_name, v.version))
                except Exception as e:
                    error_msg = str(e)
                    print(f"      ERROR: Cannot load ONNX - {error_msg[:150]}")
                    if "No such file" in error_msg or "not found" in error_msg.lower():
                        print(f"      -> Model does not have ONNX artifact")
                        print(f"      -> Re-register model with ONNX: python register_models_to_mlflow.py")
        except Exception as e:
            print(f"  ERROR: {e}")
        
        print()
    
    if all_production:
        print("=" * 60)
        print(f"SUMMARY: {len(all_production)} Production model(s) with ONNX available")
        for name, version in all_production:
            print(f"  - {name} v{version}")
        print()
        print("These models should be visible in FastAPI after:")
        print("  1. Restart FastAPI with correct MLflow URI")
        print("  2. Call POST /refresh endpoint")
    else:
        print("=" * 60)
        print("ERROR: No Production models with ONNX available")
        print()
        print("Solutions:")
        print("  1. Re-register models with ONNX: python register_models_to_mlflow.py")
        print("  2. Ensure models are in Production stage in MLflow UI")
    
except Exception as e:
    print(f"ERROR: {e}")
    import traceback
    traceback.print_exc()
    exit(1)


