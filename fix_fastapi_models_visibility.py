#!/usr/bin/env python3
"""
Fix FastAPI Models Visibility Issue

This script will:
1. Check if FastAPI is running
2. Check MLflow connection
3. Verify models are registered and in Production stage
4. Restart FastAPI with correct MLflow URI if needed
5. Refresh models in FastAPI
"""

import os
import sys
import time
import requests
import subprocess
from pathlib import Path

# Add project root to path
project_root = Path(__file__).resolve().parent
sys.path.insert(0, str(project_root))

FASTAPI_URL = os.getenv("FASTAPI_URL", "http://localhost:8000")
MLFLOW_URI = os.getenv("MLFLOW_TRACKING_URI", "http://localhost:5000")

def print_header(text):
    print("\n" + "=" * 60)
    print(text)
    print("=" * 60)

def check_fastapi_running():
    """Check if FastAPI is running"""
    try:
        response = requests.get(f"{FASTAPI_URL}/health", timeout=5)
        if response.status_code == 200:
            data = response.json()
            print(f"[OK] FastAPI is running (models loaded: {data.get('models_loaded', 0)})")
            return True
    except:
        pass
    print("[ERROR] FastAPI is not running")
    return False

def check_mlflow_connection():
    """Check MLflow connection directly"""
    try:
        import mlflow
        mlflow.set_tracking_uri(MLFLOW_URI)
        mlflow.tracking.MlflowClient().search_registered_models()
        print(f"[OK] MLflow connection OK at {MLFLOW_URI}")
        return True
    except Exception as e:
        print(f"[ERROR] MLflow connection failed: {e}")
        return False

def check_models_in_mlflow():
    """Check what models are available in MLflow"""
    try:
        import mlflow
        from utils.artifact_control.model_manager import ModelManager
        
        mlflow.set_tracking_uri(MLFLOW_URI)
        model_manager = ModelManager(tracking_uri=MLFLOW_URI)
        
        registered_models = model_manager.client.search_registered_models()
        print(f"[OK] Found {len(registered_models)} registered model(s) in MLflow")
        
        if not registered_models:
            print("[ERROR] No models registered in MLflow")
            print("   Run: python register_models_to_mlflow.py")
            return False, []
        
        production_models = []
        for model in registered_models:
            model_name = model.name
            versions = model_manager.client.get_latest_versions(model_name, stages=["Production"])
            for v in versions:
                production_models.append((model_name, v.version))
                print(f"   - {model_name} v{v.version} (Production)")
        
        if not production_models:
            print("[ERROR] No models in Production stage")
            print("   Models need to be in Production stage for FastAPI to load them")
            # Show available stages
            for model in registered_models:
                all_versions = model_manager.client.search_model_versions(f"name='{model.name}'")
                stages = [v.current_stage or "None" for v in all_versions]
                print(f"   {model.name} stages: {set(stages)}")
            return False, []
        
        # Check ONNX availability
        print("\nChecking ONNX availability...")
        onnx_available = []
        for model_name, version in production_models:
            try:
                session = model_manager.load_onnx_model(model_name, version)
                print(f"   [OK] {model_name} v{version} has ONNX")
                onnx_available.append((model_name, version))
            except Exception as e:
                print(f"   [ERROR] {model_name} v{version} - ONNX not available: {str(e)[:80]}")
        
        if not onnx_available:
            print("\n[ERROR] No models have ONNX artifacts")
            print("   Re-register models with ONNX: python register_models_to_mlflow.py")
            return False, []
        
        return True, onnx_available
    except Exception as e:
        print(f"[ERROR] Error checking MLflow: {e}")
        import traceback
        traceback.print_exc()
        return False, []

def check_fastapi_mlflow_uri():
    """Check if FastAPI is using correct MLflow URI"""
    try:
        response = requests.get(f"{FASTAPI_URL}/debug/mlflow", timeout=10)
        if response.status_code == 200:
            data = response.json()
            current_uri = data.get('mlflow_tracking_uri')
            connection_status = data.get('connection_status')
            
            print(f"FastAPI MLflow URI: {current_uri}")
            print(f"Connection Status: {connection_status}")
            
            if current_uri == "http://mlflow:5000" or connection_status == "failed":
                print("[ERROR] FastAPI is using incorrect MLflow URI or connection failed")
                return False
            else:
                print("[OK] FastAPI MLflow URI and connection are correct")
                return True
    except Exception as e:
        print(f"[ERROR] Error checking FastAPI MLflow URI: {e}")
        return False

def refresh_fastapi_models():
    """Refresh models in FastAPI"""
    try:
        print("Refreshing models in FastAPI...")
        response = requests.post(
            f"{FASTAPI_URL}/refresh",
            json={},
            timeout=30
        )
        
        if response.status_code == 200:
            data = response.json()
            print(f"[OK] Refresh completed: {data.get('status')}")
            models = data.get('models', {})
            if models:
                print("Loaded models:")
                for model_name, versions in models.items():
                    print(f"   - {model_name}: {versions}")
                return True
            else:
                print("[WARNING] No models loaded after refresh")
                return False
        else:
            print(f"[ERROR] Refresh failed: {response.status_code}")
            print(response.text)
            return False
    except Exception as e:
        print(f"[ERROR] Error refreshing models: {e}")
        return False

def test_models_endpoint():
    """Test the /models endpoint"""
    try:
        response = requests.get(f"{FASTAPI_URL}/models", timeout=10)
        
        if response.status_code == 200:
            models = response.json()
            print(f"[OK] /models endpoint returned {len(models)} model(s)")
            
            if models:
                print("\nLoaded Models:")
                for model in models:
                    print(f"   - {model.get('model_name')} v{model.get('version')}")
                    print(f"     Input: {model.get('input_shape')}")
                    print(f"     Output: {model.get('output_shape')}")
                return True
            else:
                print("[WARNING] /models endpoint returned empty list")
                return False
        else:
            print(f"[ERROR] /models endpoint returned status {response.status_code}")
            print(response.text)
            return False
    except Exception as e:
        print(f"[ERROR] Error testing /models endpoint: {e}")
        return False

def main():
    print_header("FastAPI Models Visibility Fix")
    
    # Step 1: Check MLflow connection
    print_header("Step 1: Checking MLflow Connection")
    if not check_mlflow_connection():
        print("\n[ERROR] Cannot proceed without MLflow connection")
        print(f"   Make sure MLflow is running at {MLFLOW_URI}")
        print("   Start with: mlflow ui --port 5000")
        return False
    
    # Step 2: Check models in MLflow
    print_header("Step 2: Checking Models in MLflow")
    mlflow_ok, production_models = check_models_in_mlflow()
    if not mlflow_ok or not production_models:
        print("\n[ERROR] Cannot proceed without Production models with ONNX")
        print("   Run: python register_models_to_mlflow.py")
        return False
    
    # Step 3: Check FastAPI
    print_header("Step 3: Checking FastAPI Server")
    fastapi_running = check_fastapi_running()
    
    if fastapi_running:
        # Check MLflow URI
        print_header("Step 4: Checking FastAPI MLflow Configuration")
        uri_ok = check_fastapi_mlflow_uri()
        
        if not uri_ok:
            print("\n[WARNING] FastAPI needs to be restarted with correct MLflow URI")
            print("   Please stop FastAPI (Ctrl+C) and restart with:")
            print("   PowerShell: $env:MLFLOW_TRACKING_URI='http://localhost:5000'; python start_fastapi_server.py")
            print("   Or use: .\\start_fastapi_web.ps1")
            print("\n   After restarting, run this script again.")
            return False
    else:
        print("\n[WARNING] FastAPI is not running")
        print("   Start it with:")
        print("   PowerShell: $env:MLFLOW_TRACKING_URI='http://localhost:5000'; python start_fastapi_server.py")
        print("   Or use: .\\start_fastapi_web.ps1")
        print("\n   After starting, run this script again.")
        return False
    
    # Step 5: Refresh models
    print_header("Step 5: Refreshing FastAPI Models")
    if not refresh_fastapi_models():
        return False
    
    # Wait a bit for models to load
    time.sleep(2)
    
    # Step 6: Test /models endpoint
    print_header("Step 6: Testing /models Endpoint")
    success = test_models_endpoint()
    
    print_header("Summary")
    if success:
        print("[SUCCESS] Models are now visible in FastAPI!")
        print(f"   View at: {FASTAPI_URL}/models")
        print(f"   Swagger UI: {FASTAPI_URL}/docs")
    else:
        print("[FAILED] Models are still not visible")
        print("\nTroubleshooting:")
        print("1. Check FastAPI logs for errors")
        print("2. Verify models have ONNX: python register_models_to_mlflow.py")
        print(f"3. Check debug endpoint: {FASTAPI_URL}/debug/mlflow")
    
    return success

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)

