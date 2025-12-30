#!/usr/bin/env python3
"""
Fix FastAPI MLflow URI and test model loading
This script will:
1. Check current FastAPI MLflow URI
2. Test connection with correct URI
3. Check if models have ONNX artifacts
4. Provide instructions to restart FastAPI with correct URI
"""

import os
import sys
import requests
from pathlib import Path

# Add project root to path
project_root = Path(__file__).resolve().parent
sys.path.insert(0, str(project_root))

print("=" * 60)
print("FastAPI MLflow URI Fix Script")
print("=" * 60)
print()

# Check FastAPI debug endpoint
FASTAPI_URL = os.getenv("FASTAPI_URL", "http://localhost:8000")

print("Step 1: Checking current FastAPI configuration...")
try:
    response = requests.get(f"{FASTAPI_URL}/debug/mlflow", timeout=10)
    if response.status_code == 200:
        debug_data = response.json()
        current_uri = debug_data.get('mlflow_tracking_uri')
        print(f"   Current MLflow URI: {current_uri}")
        print(f"   Connection Status: {debug_data.get('connection_status')}")
        
        if current_uri == "http://mlflow:5000":
            print()
            print("PROBLEM FOUND: FastAPI is using Docker hostname 'http://mlflow:5000'")
            print("   This won't work for local development!")
            print()
            print("SOLUTION:")
            print("   1. Stop the current FastAPI server (Ctrl+C)")
            print("   2. Set the correct MLflow URI:")
            print("      PowerShell: $env:MLFLOW_TRACKING_URI='http://localhost:5000'")
            print("      CMD:        set MLFLOW_TRACKING_URI=http://localhost:5000")
            print("   3. Restart FastAPI:")
            print("      python start_fastapi_server.py")
            print()
            print("   OR use the start script:")
            print("      .\\start_fastapi_web.ps1")
        elif current_uri == "http://localhost:5000":
            print("OK: FastAPI is using correct MLflow URI")
        else:
            print(f"WARNING: FastAPI is using: {current_uri}")
            print("   Expected: http://localhost:5000")
    else:
        print(f"ERROR: FastAPI returned status {response.status_code}")
except Exception as e:
    print(f"ERROR: Error checking FastAPI: {e}")
    print("   Make sure FastAPI is running: python start_fastapi_server.py")

print()
print("Step 2: Testing MLflow connection directly...")
try:
    import mlflow
    mlflow.set_tracking_uri("http://localhost:5000")
    experiments = mlflow.search_experiments()
    print(f"OK: MLflow is accessible at http://localhost:5000")
    print(f"   Found {len(experiments)} experiment(s)")
    
    # Check registered models
    from utils.artifact_control.model_manager import ModelManager
    model_manager = ModelManager(tracking_uri="http://localhost:5000")
    registered_models = model_manager.client.search_registered_models()
    print(f"   Found {len(registered_models)} registered model(s)")
    
    if registered_models:
        print()
        print("Checking ONNX availability for Production models...")
        for model in registered_models:
            model_name = model.name
            versions = model_manager.client.get_latest_versions(model_name, stages=["Production"])
            for v in versions:
                try:
                    onnx_session = model_manager.load_onnx_model(model_name, v.version)
                    print(f"   OK: {model_name} v{v.version}: ONNX available")
                except Exception as e:
                    print(f"   ERROR: {model_name} v{v.version}: ONNX NOT available - {str(e)[:100]}")
    
except Exception as e:
    print(f"ERROR: Error connecting to MLflow: {e}")
    print("   Make sure MLflow is running: mlflow ui --port 5000")

print()
print("=" * 60)
print("Next Steps:")
print("=" * 60)
print("1. If FastAPI URI is wrong, restart it with:")
print("   PowerShell: $env:MLFLOW_TRACKING_URI='http://localhost:5000'; python start_fastapi_server.py")
print()
print("2. After restarting, refresh models:")
print("   POST http://localhost:8000/refresh")
print("   Body: {}")
print()
print("3. Check models:")
print("   GET http://localhost:8000/models")
print()
print("4. If models don't have ONNX, re-register them:")
print("   python register_models_to_mlflow.py")
print("=" * 60)

