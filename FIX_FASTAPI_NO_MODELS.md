# Fix: No Models Visible in FastAPI

## Problem
FastAPI `/models` endpoint returns an empty list even though models are registered in MLflow.

## Root Causes Identified

1. **FastAPI MLflow URI Issue** (if FastAPI is using Docker hostname)
   - FastAPI may be configured with `MLFLOW_TRACKING_URI=http://mlflow:5000` (Docker hostname)
   - When running locally, this hostname doesn't resolve
   - **Solution**: Restart FastAPI with `MLFLOW_TRACKING_URI=http://localhost:5000`

2. **Missing ONNX Artifacts** (PRIMARY ISSUE)
   - Models are registered in MLflow and in Production stage
   - BUT they don't have ONNX artifacts
   - FastAPI requires ONNX models to load them
   - **Solution**: Re-register models with ONNX artifacts

## Step-by-Step Fix

### Step 1: Check Current Status

Run the diagnostic script:
```powershell
python fix_fastapi_models_visibility.py
```

This will show:
- MLflow connection status
- Registered models
- Production stage models
- ONNX availability

### Step 2: Fix FastAPI MLflow URI (if needed)

If FastAPI is using the wrong MLflow URI:

**Option A: Use the restart script**
```powershell
.\restart_fastapi_with_correct_uri.ps1
```

**Option B: Manual restart**
1. Stop FastAPI (Ctrl+C in the terminal where it's running)
2. Set environment variable and restart:
```powershell
$env:MLFLOW_TRACKING_URI = "http://localhost:5000"
python start_fastapi_server.py
```

**Option C: Use the web start script (sets correct URI automatically)**
```powershell
.\start_fastapi_web.ps1
```

### Step 3: Re-register Models with ONNX

The models need to be re-registered with ONNX artifacts:

```powershell
python register_models_to_mlflow.py
```

This script will:
- Load local models from `models/` directory
- Convert them to ONNX format
- Register them to MLflow with ONNX artifacts
- Set them to Production stage

### Step 4: Refresh Models in FastAPI

After re-registering models, refresh FastAPI:

**Option A: Using Swagger UI**
1. Open: http://localhost:8000/docs
2. Find the `/refresh` endpoint
3. Click "Try it out"
4. Use request body: `{}`
5. Click "Execute"

**Option B: Using PowerShell**
```powershell
Invoke-RestMethod -Uri "http://localhost:8000/refresh" -Method POST -ContentType "application/json" -Body "{}"
```

**Option C: Using cURL**
```powershell
curl -X POST "http://localhost:8000/refresh" -H "Content-Type: application/json" -d "{}"
```

### Step 5: Verify Models are Loaded

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

## Quick Fix Script

Run this comprehensive fix script:
```powershell
python fix_fastapi_models_visibility.py
```

This will:
1. Check MLflow connection
2. Check models in MLflow
3. Check FastAPI status
4. Check FastAPI MLflow URI
5. Refresh models
6. Test /models endpoint

## Troubleshooting

### Issue: "No models in Production stage"
- Models need to be in Production stage for FastAPI to load them
- Run `python register_models_to_mlflow.py` to register and set to Production

### Issue: "ONNX not available"
- Models must have ONNX artifacts for FastAPI
- Re-register models: `python register_models_to_mlflow.py`
- Make sure local models exist in `models/` directory

### Issue: "MLflow connection failed"
- Make sure MLflow is running: `mlflow ui --port 5000`
- Check if MLflow is accessible: http://localhost:5000

### Issue: "FastAPI is using Docker hostname"
- Restart FastAPI with correct URI
- Use: `.\restart_fastapi_with_correct_uri.ps1` or `.\start_fastapi_web.ps1`

## Summary

The main issue is that **models don't have ONNX artifacts**. FastAPI requires ONNX models to serve them. Re-register the models with ONNX using `register_models_to_mlflow.py`, then refresh FastAPI.


