#!/usr/bin/env python3
"""
Force refresh FastAPI models and check what happens
"""

import requests
import json

FASTAPI_URL = "http://localhost:8000"

print("=" * 60)
print("Force Refresh and Check Models")
print("=" * 60)
print()

# Step 1: Check current state
print("Step 1: Current state")
try:
    response = requests.get(f"{FASTAPI_URL}/health", timeout=5)
    if response.status_code == 200:
        data = response.json()
        print(f"   Models loaded: {data.get('models_loaded', 0)}")
except Exception as e:
    print(f"   ERROR: {e}")
    exit(1)

# Step 2: Check debug endpoint
print()
print("Step 2: Debug endpoint (this should trigger auto-fix)")
try:
    response = requests.get(f"{FASTAPI_URL}/debug/mlflow", timeout=15)
    if response.status_code == 200:
        data = response.json()
        print(f"   MLflow URI: {data.get('mlflow_tracking_uri')}")
        print(f"   Connection: {data.get('connection_status')}")
        print(f"   Registered models: {len(data.get('registered_models', []))}")
        print(f"   Production models: {len(data.get('production_models', []))}")
        
        # Show production models with ONNX status
        prod_models = data.get('production_models', [])
        if prod_models:
            print()
            print("   Production Models:")
            for model in prod_models:
                onnx_status = "YES" if model.get('onnx_available') else "NO"
                print(f"     - {model.get('name')} v{model.get('version')}: ONNX={onnx_status}")
                if not model.get('onnx_available') and model.get('onnx_error'):
                    print(f"       Error: {model.get('onnx_error')[:100]}")
except Exception as e:
    print(f"   ERROR: {e}")
    import traceback
    traceback.print_exc()

# Step 3: Force refresh
print()
print("Step 3: Force refresh models")
try:
    response = requests.post(
        f"{FASTAPI_URL}/refresh",
        json={},
        timeout=30
    )
    if response.status_code == 200:
        data = response.json()
        print(f"   Status: {data.get('status')}")
        models = data.get('models', {})
        if models:
            print("   Loaded models:")
            for name, versions in models.items():
                print(f"     - {name}: {versions}")
        else:
            print("   WARNING: No models loaded")
    else:
        print(f"   ERROR: Status {response.status_code}")
        print(f"   Response: {response.text}")
except Exception as e:
    print(f"   ERROR: {e}")
    import traceback
    traceback.print_exc()

# Step 4: Check /models endpoint
print()
print("Step 4: Check /models endpoint")
try:
    response = requests.get(f"{FASTAPI_URL}/models", timeout=10)
    if response.status_code == 200:
        models = response.json()
        print(f"   Found {len(models)} model(s)")
        if models:
            print("   Models:")
            for model in models:
                print(f"     - {model.get('model_name')} v{model.get('version')}")
                print(f"       Input: {model.get('input_shape')}")
                print(f"       Output: {model.get('output_shape')}")
        else:
            print("   WARNING: Empty list returned")
    else:
        print(f"   ERROR: Status {response.status_code}")
        print(f"   Response: {response.text}")
except Exception as e:
    print(f"   ERROR: {e}")

print()
print("=" * 60)


