
import requests
import json
import sys

BASE_URL = "http://127.0.0.1:8019"

def trigger_refresh_and_wait():
    print("Triggering model refresh for BTCUSDT_lightgbm...")
    try:
        resp = requests.post(f"{BASE_URL}/refresh", json={"model_name": "BTCUSDT_lightgbm"})
        print(f"Refresh response: {resp.status_code}")
        print(resp.json())
    except Exception as e:
        print(f"Refresh failed: {e}")

def run_test():
    print(f"Testing FastAPI at {BASE_URL}...")
    
    # 1. Health check
    try:
        resp = requests.get(f"{BASE_URL}/health", timeout=5)
        print(f"Health check: {resp.status_code}")
        print(resp.json())
    except Exception as e:
        print(f"Error connecting to server: {e}")
        return

    # Trigger manual refresh
    trigger_refresh_and_wait()


    # 2. List models
    print("\nListing loaded models...")
    try:
        resp = requests.get(f"{BASE_URL}/models")
        models = resp.json()
        print(f"Found {len(models)} models:")
        for m in models:
            print(f"  - {m['model_name']} v{m['version']} (Input: {m.get('input_shape')})")
    except Exception as e:
        print(f"Error listing models: {e}")
        return

    # 2.5 Debug MLflow
    print("\nDebugging MLflow connection...")
    try:
        resp = requests.get(f"{BASE_URL}/debug/mlflow")
        print(json.dumps(resp.json(), indent=2))
    except Exception as e:
        print(f"Error debugging MLflow: {e}")


    # 3. Predict with BTCUSDT_lightgbm
    # Assuming it takes some number of float features. 
    # LightGBM models often take a flattened list. 
    # The error message from previous turns or introspection might hint at shape, 
    # but for now I'll try a dummy vector. 
    # Often these models have many features, e.g., 60-100.
    
    model_name = "BTCUSDT_lightgbm"
    # We saw version 6 in Production in the text file
    version = 6 
    
    # Create dummy features - let's try a small vector first, if it fails it might complain about shape
    # But usually LightGBM ONNX expects strict shape.
    # If standard crypto features, maybe 5-20?
    # Let's try to infer from the 'models' list output if possible, otherwise guess.
    
    # If I can't find it in the list, I'll pick the first one available.
    if models:
        target_model = next((m for m in models if "lightgbm" in m['model_name'].lower()), models[0])
        model_name = target_model['model_name']
        version = target_model['version']
        print(f"\nAttempting prediction on {model_name} v{version}...")
        
        # Arbitrary feature vector - 1 row, 20 columns (common guess)
        # If the server is robust it might catch shape errors.
        features = [[0.5] * 20] 
        
        payload = {
            "model_name": model_name,
            "version": int(version) - 1, # 0-indexed as per API docs? 
                                        # Wait, docs said: "version (0-indexed: 0=v1, 1=v2, etc.)"
                                        # Let's use the query param correctly.
                                        # Actually docs in code say: "version: Union[str, int] = Query(..., description='Model version (0-indexed: 0=v1, 1=v2, etc.)')"
            "features": features
        }
        
        # The endpoint expects query params for model_name and version, and body for features
        params = {
            "model_name": model_name,
            "version": int(version) - 1 # API expects 0-indexed int for version 1..N
        }
        
        try:
            # Note: The codebase's predict endpoint docs say:
            # predict(features: List[List[float]], model_name: str, version: Union[str, int])
            # So model_name and version are query params.
            
            # Let's try with a reasonable number of features. 
            # If 20 fails, I'll try checking input_shape from the /models response if available.
            
            # First, check /models output again to see if input_shape is there
             # (already printing it above)
             
            resp = requests.post(f"{BASE_URL}/predict", params=params, json=features)
            print(f"Prediction response code: {resp.status_code}")
            if resp.status_code == 200:
                print("Success!")
                print(resp.json())
            else:
                print("Failed:")
                print(resp.text)
                
                # If shape mismatch, it usually tells us expected shape in error
                if "feature" in resp.text.lower() or "shape" in resp.text.lower():
                     print("trying to adjust shape...")
                     # If it says 'expected 42' or similar, we can parse it, but for now just raw report.
        except Exception as e:
             print(f"Prediction request failed: {e}")

if __name__ == "__main__":
    run_test()
