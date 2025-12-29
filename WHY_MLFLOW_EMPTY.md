# Why MLflow Doesn't Have Any Models

## The Problem

MLflow is empty because **models are being saved locally but never registered to MLflow**.

## Root Cause

Looking at your codebase:

1. **Training scripts save models locally:**
   - `simplified_integrated_model.py` uses `ModelVersionManager` to save models to `models/` directory
   - Models are saved as files (`.txt` for LightGBM, `.pth` for PyTorch)
   - This creates local files but doesn't register them to MLflow

2. **ModelManager.save_model() exists but isn't called:**
   - `utils/artifact_control/model_manager.py` has a `save_model()` method
   - This method can register models to MLflow
   - But your training scripts don't call it!

3. **Two separate versioning systems:**
   - **Local versioning:** `ModelVersionManager` manages v1/v2/v3 locally
   - **MLflow registry:** `ModelManager` can register models to MLflow
   - These two systems aren't connected!

## What's Happening

```
Training Script
    ↓
ModelVersionManager.register_new_model()
    ↓
Saves to: models/lightgbm/v3/lgb_model.txt  ✅ (Local file)
    ↓
❌ NOT registered to MLflow
```

## What Should Happen

```
Training Script
    ↓
ModelManager.save_model()
    ↓
Logs to MLflow run ✅
    ↓
mlflow.register_model() ✅
    ↓
Model appears in MLflow registry ✅
```

## Solutions

### Option 1: Register Existing Models (Quick Fix)

Use the script I created: `register_models_to_mlflow.py`

```bash
# Make sure MLflow is running
mlflow ui --port 5000

# In another terminal
python register_models_to_mlflow.py
```

This will:
- Read your existing local models from `models/` directory
- Register them to MLflow
- Set v1 and v3 models to "Production" stage

### Option 2: Modify Training to Auto-Register (Long-term Fix)

Update your training scripts to use `ModelManager.save_model()`:

**Example for LightGBM training:**

```python
from utils.artifact_control.model_manager import ModelManager
import mlflow

# After training
model_manager = ModelManager()

# Convert model to ONNX (if needed for FastAPI)
onnx_model = convert_to_onnx(model, type="lightgbm", sample_input=X_sample)

# Register to MLflow
mlflow.set_experiment("crypto-ml-pipeline")
with mlflow.start_run():
    model_manager.save_model(
        model_type="lightgbm",
        model=trained_model,
        name="BTCUSDT_lightgbm",
        onnx_model=onnx_model  # Important for FastAPI!
    )
    
    # Set to Production
    model_manager.set_production("BTCUSDT_lightgbm", keep_latest_n=2)
```

### Option 3: Hybrid Approach

Keep local versioning for your system, but also register to MLflow:

```python
# Save locally (existing code)
new_version = self.version_manager.register_new_model("lightgbm", temp_path, metadata)

# ALSO register to MLflow
model_manager = ModelManager()
with mlflow.start_run():
    model_manager.save_model(
        model_type="lightgbm",
        model=trained_model,
        name="BTCUSDT_lightgbm",
        onnx_model=onnx_model
    )
```

## Why This Matters for FastAPI

FastAPI's `/models` endpoint is empty because:

1. FastAPI queries MLflow for registered models
2. MLflow has no registered models
3. So FastAPI finds nothing to load

**After registering models:**
1. Models appear in MLflow registry
2. FastAPI can discover them
3. FastAPI loads Production models into memory
4. `/models` endpoint returns the loaded models

## Required for FastAPI

For FastAPI to work, models need:

1. ✅ **Registered in MLflow** (use `register_models_to_mlflow.py`)
2. ✅ **In "Production" stage** (script does this automatically)
3. ✅ **Have ONNX versions** (you'll need to convert models to ONNX)

## ONNX Conversion

FastAPI requires ONNX models. You'll need to:

1. Convert existing models to ONNX
2. Or retrain with ONNX conversion during training

**Example ONNX conversion:**

```python
from trainer.train_utils import convert_to_onnx

# For LightGBM
onnx_model = convert_to_onnx(
    model=lgb_model,
    type="lightgbm",
    sample_input=X_sample  # Sample feature array
)

# Save ONNX with model
model_manager.save_model(
    model_type="lightgbm",
    model=lgb_model,
    name="BTCUSDT_lightgbm",
    onnx_model=onnx_model  # This is what FastAPI needs!
)
```

## Summary

- **Current state:** Models saved locally, not in MLflow
- **Why empty:** Training doesn't call `ModelManager.save_model()`
- **Quick fix:** Run `register_models_to_mlflow.py`
- **Long-term:** Modify training to register models during training
- **For FastAPI:** Need ONNX models registered in Production stage












