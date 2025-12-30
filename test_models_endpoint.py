#!/usr/bin/env python3
"""
Test and fix FastAPI /models endpoint
This script will diagnose and fix issues until models are visible
"""

import os
import sys
import time
import requests
from pathlib import Path

# Add project root to path
project_root = Path(__file__).resolve().parent
sys.path.insert(0, str(project_root))

FASTAPI_URL = os.getenv("FASTAPI_URL", "http://localhost:8000")
MLFLOW_URI = os.getenv("MLFLOW_TRACKING_URI", "http://localhost:5000")

def print_step(step_num, description):
    print()
    print("=" * 60)
    print(f"Step {step_num}: {description}")
    print("=" * 60)

def check_fastapi_running():
    """Check if FastAPI is running"""
    try:
        response = requests.get(f"{FASTAPI_URL}/health", timeout=5)
        if response.status_code == 200:
            data = response.json()
            print(f"OK: FastAPI is running")
            print(f"   Models loaded: {data.get('models_loaded', 0)}")
            return True
        return False
    except:
        print("ERROR: FastAPI is not running")
        print("   Start it with: python start_fastapi_server.py")
        print("   Or: .\\start_fastapi_web.ps1")
        return False

def check_mlflow_uri():
    """Check if FastAPI is using correct MLflow URI"""
    try:
        response = requests.get(f"{FASTAPI_URL}/debug/mlflow", timeout=10)
        if response.status_code == 200:
            data = response.json()
            current_uri = data.get('mlflow_tracking_uri')
            connection_status = data.get('connection_status')
            
            print(f"Current MLflow URI: {current_uri}")
            print(f"Connection Status: {connection_status}")
            
            if current_uri == "http://mlflow:5000":
                print()
                print("PROBLEM: FastAPI is using Docker hostname!")
                print("SOLUTION: Restart FastAPI with correct URI:")
                print("   PowerShell: $env:MLFLOW_TRACKING_URI='http://localhost:5000'; python start_fastapi_server.py")
                print("   Or use: .\\start_fastapi_web.ps1")
                return False
            elif connection_status == "failed":
                print("PROBLEM: Cannot connect to MLflow")
                print(f"   Check if MLflow is running at {current_uri}")
                return False
            else:
                print("OK: MLflow URI and connection are correct")
                return True
        return False
    except Exception as e:
        print(f"ERROR: {e}")
        return False

def check_models_in_mlflow():
    """Check what models are available in MLflow"""
    try:
        import mlflow
        from utils.artifact_control.model_manager import ModelManager
        
        mlflow.set_tracking_uri(MLFLOW_URI)
        model_manager = ModelManager(tracking_uri=MLFLOW_URI)
        
        registered_models = model_manager.client.search_registered_models()
        print(f"Found {len(registered_models)} registered model(s) in MLflow")
        
        if not registered_models:
            print("ERROR: No models registered in MLflow")
            print("   Run: python register_models_to_mlflow.py")
            return False, None
        
        production_models = []
        for model in registered_models:
            model_name = model.name
            versions = model_manager.client.get_latest_versions(model_name, stages=["Production"])
            for v in versions:
                production_models.append((model_name, v.version))
                print(f"   - {model_name} v{v.version} (Production)")
        
        if not production_models:
            print("WARNING: No models in Production stage")
            print("   Models need to be in Production stage for FastAPI to load them")
            return False, None
        
        # Check ONNX availability
        print()
        print("Checking ONNX availability...")
        onnx_available = []
        for model_name, version in production_models:
            try:
                session = model_manager.load_onnx_model(model_name, version)
                print(f"   OK: {model_name} v{version} has ONNX")
                onnx_available.append((model_name, version))
            except Exception as e:
                print(f"   ERROR: {model_name} v{version} - ONNX not available: {str(e)[:80]}")
        
        if not onnx_available:
            print()
            print("ERROR: No models have ONNX artifacts")
            print("   Re-register models with ONNX: python register_models_to_mlflow.py")
            return False, None
        
        return True, onnx_available
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False, None

def refresh_fastapi_models():
    """Refresh models in FastAPI"""
    try:
        print("Refreshing models in FastAPI...")
        response = requests.post(
            f"{FASTAPI_URL}/refresh",
            json={"model_name": None, "version": None},
            timeout=30
        )
        
        if response.status_code == 200:
            data = response.json()
            print(f"OK: Refresh completed")
            print(f"   Status: {data.get('status')}")
            models = data.get('models', {})
            if models:
                for model_name, versions in models.items():
                    print(f"   {model_name}: {versions}")
            return True
        else:
            print(f"ERROR: Refresh failed: {response.status_code}")
            print(response.text)
            return False
    except Exception as e:
        print(f"ERROR: {e}")
        return False

def test_models_endpoint():
    """Test the /models endpoint"""
    try:
        response = requests.get(f"{FASTAPI_URL}/models", timeout=10)
        
        if response.status_code == 200:
            models = response.json()
            print(f"OK: /models endpoint returned {len(models)} model(s)")
            
            if models:
                print()
                print("Loaded Models:")
                for model in models:
                    print(f"   - {model.get('model_name')} v{model.get('version')}")
                    print(f"     Input: {model.get('input_shape')}")
                    print(f"     Output: {model.get('output_shape')}")
                return True
            else:
                print("WARNING: /models endpoint returned empty list")
                return False
        else:
            print(f"ERROR: /models endpoint returned status {response.status_code}")
            print(response.text)
            return False
    except Exception as e:
        print(f"ERROR: {e}")
        return False

def main():
    print("=" * 60)
    print("FastAPI Models Endpoint Test and Fix")
    print("=" * 60)
    
    # Step 1: Check FastAPI
    print_step(1, "Checking FastAPI Server")
    if not check_fastapi_running():
        return False
    
    # Step 2: Check MLflow URI
    print_step(2, "Checking MLflow Configuration")
    if not check_mlflow_uri():
        print()
        print("ACTION REQUIRED: Restart FastAPI with correct MLflow URI")
        print("   Run: .\\restart_fastapi_with_correct_uri.ps1")
        print("   Or: .\\start_fastapi_web.ps1")
        return False
    
    # Step 3: Check models in MLflow
    print_step(3, "Checking Models in MLflow")
    mlflow_ok, production_models = check_models_in_mlflow()
    if not mlflow_ok:
        return False
    
    if not production_models:
        print("ERROR: No Production models with ONNX available")
        return False
    
    # Step 4: Refresh FastAPI models
    print_step(4, "Refreshing FastAPI Models")
    if not refresh_fastapi_models():
        return False
    
    # Wait a bit for models to load
    time.sleep(2)
    
    # Step 5: Test /models endpoint
    print_step(5, "Testing /models Endpoint")
    success = test_models_endpoint()
    
    print()
    print("=" * 60)
    if success:
        print("SUCCESS: Models are now visible in FastAPI!")
        print(f"   View at: {FASTAPI_URL}/models")
        print(f"   Swagger UI: {FASTAPI_URL}/docs")
    else:
        print("FAILED: Models are still not visible")
        print()
        print("Troubleshooting:")
        print("1. Check FastAPI logs for errors")
        print("2. Verify models have ONNX: python register_models_to_mlflow.py")
        print("3. Check debug endpoint: {}/debug/mlflow".format(FASTAPI_URL))
    print("=" * 60)
    
    return success

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)


