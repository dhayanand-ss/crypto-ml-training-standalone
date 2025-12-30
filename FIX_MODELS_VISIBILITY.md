# Fix: Models Not Visible in FastAPI

## Problem
The `/models` endpoint in FastAPI returns an empty list even though models are registered in MLflow.

## Root Cause
FastAPI is configured with `MLFLOW_TRACKING_URI=http://mlflow:5000` (Docker hostname) but is running locally, so it can't connect to MLflow.

## Solution

### Step 1: Restart FastAPI with Correct MLflow URI

**Option A: Use the provided script (Recommended)**
```powershell
.\restart_fastapi_with_correct_uri.ps1
```

**Option B: Manual restart**
```powershell
# Stop the current FastAPI server (Ctrl+C in the terminal where it's running)

# Set the correct MLflow URI
$env:MLFLOW_TRACKING_URI = "http://localhost:5000"

# Start FastAPI
python start_fastapi_server.py
```

**Option C: Use the web start script**
```powershell
.\start_fastapi_web.ps1
```

### Step 2: Verify MLflow is Running

Make sure MLflow is running on port 5000:
```powershell
mlflow ui --port 5000
```

Or check if it's already running:
```powershell
# Open in browser: http://localhost:5000
```

### Step 3: Refresh Models in FastAPI

After restarting FastAPI, refresh the models:

**Using Swagger UI (Recommended):**
1. Open: http://localhost:8000/docs
2. Find the `/refresh` endpoint
3. Click "Try it out"
4. Use this request body:
   ```json
   {}
   ```
5. Click "Execute"

**Using cURL:**
```powershell
curl -X POST "http://localhost:8000/refresh" -H "Content-Type: application/json" -d "{}"
```

**Using PowerShell:**
```powershell
Invoke-RestMethod -Uri "http://localhost:8000/refresh" -Method POST -ContentType "application/json" -Body "{}"
```

### Step 4: Verify Models are Loaded

**Check the /models endpoint:**

**Browser:**
```
http://localhost:8000/models
```

**Swagger UI:**
1. Open: http://localhost:8000/docs
2. Find the `/models` endpoint
3. Click "Try it out"
4. Click "Execute"

**Using the test script:**
```powershell
python test_models_endpoint.py
```

## Auto-Fix Feature

The FastAPI code has been updated to automatically detect and fix the MLflow URI issue. If FastAPI detects it's using `http://mlflow:5000` but can't connect, it will automatically switch to `http://localhost:5000`.

**Note:** This requires restarting FastAPI for the fix to take effect.

## Troubleshooting

### Models Still Not Visible After Restart

1. **Check if models are registered in MLflow:**
   ```powershell
   python test_models_endpoint.py
   ```
   This will show you what models are available.

2. **Check if models are in Production stage:**
   - Open MLflow UI: http://localhost:5000
   - Go to "Models" tab
   - Check that models are in "Production" stage
   - If not, transition them to Production in the MLflow UI

3. **Check if models have ONNX artifacts:**
   - FastAPI requires ONNX models for inference
   - If models don't have ONNX, re-register them:
     ```powershell
     python register_models_to_mlflow.py
     ```

4. **Check FastAPI debug endpoint:**
   ```
   http://localhost:8000/debug/mlflow
   ```
   This shows detailed information about MLflow connection and model availability.

### MLflow Connection Errors

If you see "Invalid Host header" or connection errors:

1. **Verify MLflow is running:**
   ```powershell
   # Check if port 5000 is in use
   netstat -ano | findstr :5000
   ```

2. **Start MLflow if not running:**
   ```powershell
   mlflow ui --port 5000
   ```

3. **Check MLflow URI in FastAPI:**
   - Open: http://localhost:8000/debug/mlflow
   - Check the `mlflow_tracking_uri` value
   - Should be: `http://localhost:5000`

## Quick Test

Run this comprehensive test script:
```powershell
python test_models_endpoint.py
```

This script will:
1. Check if FastAPI is running
2. Verify MLflow configuration
3. Check what models are available
4. Refresh models
5. Test the `/models` endpoint

## Success Indicators

When everything is working, you should see:

1. **Health endpoint** (`/health`):
   ```json
   {
     "status": "healthy",
     "models_loaded": 2,
     "onnxruntime_available": true
   }
   ```

2. **Models endpoint** (`/models`):
   ```json
   [
     {
       "model_name": "BTCUSDT_lightgbm",
       "version": "1",
       "loaded": true,
       "input_shape": [null, 50],
       "output_shape": [null, 3]
     }
   ]
   ```

3. **Debug endpoint** (`/debug/mlflow`):
   - `connection_status`: "connected"
   - `loaded_models_count`: > 0
   - `production_models`: list of models with `onnx_available: true`


