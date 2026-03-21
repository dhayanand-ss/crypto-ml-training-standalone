"""
FastAPI ML Model Inference API

Serves ML models for predictions with:
- Model management: loads production models from MLflow (ONNX)
- Prometheus metrics: /metrics
- Thread-safe model refresh with locks
- Batch predictions (up to 5000 per request)
"""

import asyncio
import os
import json
import logging
import threading
import time
import urllib.request
from collections import deque
from datetime import datetime
from typing import Dict, List, Optional, Any, Union
from contextlib import asynccontextmanager

import numpy as np
import pandas as pd
import joblib
from fastapi import FastAPI, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse, StreamingResponse
from pydantic import BaseModel, Field, validator

try:
    import onnxruntime as ort
    ONNXRUNTIME_AVAILABLE = True
except ImportError:
    ONNXRUNTIME_AVAILABLE = False

try:
    from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST
    from starlette.responses import Response
    from prometheus_fastapi_instrumentator import Instrumentator
    PROMETHEUS_AVAILABLE = True
    INSTRUMENTATOR_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False
    INSTRUMENTATOR_AVAILABLE = False

# Import ModelManager from the project
import sys
from pathlib import Path

# Add parent directory to path to import utils
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from utils.artifact_control.model_manager import ModelManager

# GCS credential manager (non-fatal if GCS is not configured)
try:
    from gcs_credentials import gcs_creds
    _GCS_CREDS_LOADED = True
except ImportError:
    gcs_creds = None
    _GCS_CREDS_LOADED = False

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Global model cache with thread-safe locks
_model_cache: Dict[str, Any] = {}
_model_locks: Dict[str, threading.RLock] = {}
_cache_lock = threading.RLock()

# Live prediction ring buffer + SSE subscriber queues
_prediction_buffer: deque = deque(maxlen=200)
_sse_subscribers: List[asyncio.Queue] = []
# WebSocket clients list (populated at runtime; lock created inside async context)
_ws_clients: List = []

# Prometheus metrics
if PROMETHEUS_AVAILABLE:
    prediction_counter = Counter(
        'ml_predictions_total',
        'Total number of predictions made',
        ['model_name', 'version', 'status']
    )
    prediction_latency = Histogram(
        'ml_predictions_duration_seconds',
        'Prediction latency in seconds',
        ['model_name', 'version']
    )
    model_load_errors = Counter(
        'ml_model_load_errors_total',
        'Total number of model load errors',
        ['model_name', 'version']
    )
    active_models = Gauge(
        'ml_active_models',
        'Number of active models loaded in memory',
        ['model_name', 'version']
    )
else:
    prediction_counter = None
    prediction_latency = None
    model_load_errors = None
    active_models = None



# Initialize ModelManager
# Initialize ModelManager
model_manager = ModelManager()


# Pydantic models for request/response
class RefreshRequest(BaseModel):
    """Request model for refreshing models"""
    model_name: Optional[str] = None  # If None, refresh all production models
    version: Optional[Union[str, int]] = None  # If None, load latest production version


class ModelAvailabilityRequest(BaseModel):
    """Request model for checking model availability"""
    model_name: str
    version: Union[str, int]


class PredictionRequest(BaseModel):
    """Request model for predictions"""
    features: List[List[float]] = Field(..., description="Feature matrix for predictions")
    
    @validator('features')
    def validate_features(cls, v):
        if not v:
            raise ValueError("Features list cannot be empty")
        if len(v) > 5000:
            raise ValueError("Maximum 5000 samples per request")
        # Validate all rows have same length
        if len(set(len(row) for row in v)) > 1:
            raise ValueError("All feature vectors must have the same length")
        return v


class PredictionResponse(BaseModel):
    """Response model for predictions"""
    predictions: List[List[float]] = Field(..., description="Prediction probabilities")
    model_name: str
    version: str
    num_samples: int


class ModelInfo(BaseModel):
    """Model information"""
    model_name: str
    version: str
    loaded: bool
    input_shape: Optional[List[Any]] = None
    output_shape: Optional[List[Any]] = None


def get_model_key(model_name: str, version: Union[str, int]) -> str:
    """Generate a unique key for model cache"""
    return f"{model_name}:{version}"


def load_production_models() -> Dict[str, Any]:
    """
    Load all production models from local registry.
    Returns a dictionary of model_key -> ONNX InferenceSession
    """
    loaded_models = {}
    
    try:
        # Load models from local registry
        logger.info("Loading models from local registry...")
        
        for model_type, versions in model_manager.local_registry.items():
            if model_type == "metadata":
                continue
            for v_key, v_data in versions.items():
                if v_data is None:
                    continue
                version = v_key.replace("v", "")
                model_key = get_model_key(model_type, version)
                
                try:
                    logger.info(f"Loading local model: {model_type} version {version}")
                    
                    # Try ONNX first
                    try:
                        logger.info(f"Attempting to load as ONNX model: {model_type}")
                        ort_session = model_manager.load_onnx_model(model_type, version)
                         # Get input/output shapes
                        input_shape = None
                        output_shape = None
                        if ort_session.get_inputs():
                            input_shape = list(ort_session.get_inputs()[0].shape)
                        if ort_session.get_outputs():
                            output_shape = list(ort_session.get_outputs()[0].shape)
                        
                        loaded_models[model_key] = {
                            'session': ort_session,
                            'type': 'onnx',
                            'model_name': model_type,
                            'version': version,
                            'input_shape': input_shape,
                            'output_shape': output_shape,
                            'loaded_at': time.time()
                        }
                    except Exception as onnx_err:
                        # Fallback to PyTorch/LightGBM
                        logger.warning(f"Could not load {model_type} as ONNX: {onnx_err}. Trying native loader...")
                        
                        m_type = "pytorch"
                        if "lightgbm" in model_type.lower():
                            m_type = "lightgbm"
                        
                        model, loaded_version = model_manager.load_model(model_type, version, model_type=m_type)
                        loaded_models[model_key] = {
                            'model': model,
                            'type': m_type,
                            'model_name': model_type,
                            'version': version,
                            'loaded_at': time.time()
                        }
                    
                    logger.info(f"Successfully loaded {model_key}")
                    if active_models:
                        active_models.labels(model_name=model_type, version=str(version)).set(1)

                except Exception as e:
                    logger.error(f"Failed to load local model {model_key}: {e}")
        
    except Exception as e:
        logger.error(f"Error loading models: {e}", exc_info=True)
    
    return loaded_models
    
    return loaded_models


def refresh_models(model_name: Optional[str] = None, version: Optional[Union[str, int]] = None):
    """
    Thread-safe model refresh.
    If model_name is None, refresh all production models.
    If version is None, load latest production version.
    """
    global _model_cache
    
    with _cache_lock:
        if model_name is None:
            # Refresh all production models
            logger.info("Refreshing all production models")
            new_cache = load_production_models()
            
            # Update locks for new models
            for model_key in new_cache:
                if model_key not in _model_locks:
                    _model_locks[model_key] = threading.RLock()
            
            # Remove old models from cache and metrics
            old_keys = set(_model_cache.keys()) - set(new_cache.keys())
            for old_key in old_keys:
                old_model = _model_cache[old_key]
                if active_models:
                    active_models.labels(
                        model_name=old_model['model_name'],
                        version=str(old_model['version'])
                    ).set(0)
                del _model_locks[old_key]
            
            _model_cache = new_cache
            logger.info(f"Refreshed {len(_model_cache)} models")
            
        else:
            # Refresh specific model
            if version is None:
                # Load latest production version
                # Load latest version from local registry for this model
                try:
                     # Find all versions from registry
                     versions = []
                     if model_name in model_manager.local_registry:
                         for v_str in model_manager.local_registry[model_name].keys():
                             if v_str.startswith('v'):
                                 try:
                                     versions.append(int(v_str[1:]))
                                 except:
                                     pass
                     
                     if not versions:
                         raise ValueError(f"No versions found for {model_name} in local registry")
                     
                     version = sorted(versions)[-1] # Use largest version number
                     
                except Exception as e:
                    logger.error(f"Failed to get latest version for {model_name}: {e}")
                    raise
            
            model_key = get_model_key(model_name, version)
            
            # Get lock for this specific model
            if model_key not in _model_locks:
                _model_locks[model_key] = threading.RLock()
            
            with _model_locks[model_key]:
                try:
                    logger.info(f"Refreshing model: {model_key}")
                    ort_session = model_manager.load_onnx_model(model_name, version)
                    
                    # Get input/output shapes
                    input_shape = None
                    output_shape = None
                    if ort_session.get_inputs():
                        input_shape = list(ort_session.get_inputs()[0].shape)
                    if ort_session.get_outputs():
                        output_shape = list(ort_session.get_outputs()[0].shape)
                    
                    _model_cache[model_key] = {
                        'session': ort_session,
                        'model_name': model_name,
                        'version': version,
                        'input_shape': input_shape,
                        'output_shape': output_shape,
                        'loaded_at': time.time()
                    }
                    
                    logger.info(f"Successfully refreshed {model_key}")
                    
                    if active_models:
                        active_models.labels(model_name=model_name, version=str(version)).set(1)
                        
                except Exception as e:
                    logger.error(f"Failed to refresh {model_key}: {e}")
                    if model_load_errors:
                        model_load_errors.labels(model_name=model_name, version=str(version)).inc()
                    raise


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup/shutdown"""
    # Startup: Load production models
    logger.info("Starting FastAPI ML Inference Service")

    try:
        refresh_models()  # Load all production models
        logger.info(f"Loaded {len(_model_cache)} production models on startup. Cache ID: {id(_model_cache)}")
    except Exception as e:
        logger.error(f"Failed to load models on startup: {e}")

    # GCS connectivity check (non-fatal — app runs fine without GCS)
    if _GCS_CREDS_LOADED and gcs_creds is not None:
        try:
            gcs_result = gcs_creds.health_check()
            if gcs_result.get("status") == "ok":
                logger.info(
                    "GCS connected — bucket: %s via %s",
                    gcs_result.get("bucket"), gcs_result.get("method"),
                )
            else:
                logger.warning(
                    "GCS connection unavailable: %s (app will continue without GCS)",
                    gcs_result.get("error"),
                )
        except Exception as _gcs_exc:
            logger.warning("GCS health check raised an exception: %s", _gcs_exc)

    # Start background prediction task
    bg_task = asyncio.create_task(_inference_background_task())

    yield

    # Shutdown: cancel background task then cleanup
    bg_task.cancel()
    try:
        await bg_task
    except asyncio.CancelledError:
        pass
    logger.info("Shutting down FastAPI ML Inference Service")
    _model_cache.clear()
    _model_locks.clear()


# Create FastAPI app
app = FastAPI(
    title="ML Model Inference API",
    description="FastAPI service for ML model predictions using local registry models",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*", "http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Prometheus instrumentation (automatic HTTP metrics)
# This automatically exposes /metrics endpoint with HTTP request metrics
if INSTRUMENTATOR_AVAILABLE:
    instrumentator = Instrumentator()
    instrumentator.instrument(app).expose(app, endpoint="/metrics")


@app.get("/")
async def root():
    """Root endpoint - redirects to API documentation"""
    return RedirectResponse(url="/docs")


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "models_loaded": len(_model_cache),
        "onnxruntime_available": ONNXRUNTIME_AVAILABLE,
        "prometheus_available": PROMETHEUS_AVAILABLE
    }


@app.get("/gcs/health")
async def gcs_health():
    """
    Verify GCS credentials and bucket connectivity.

    Returns:
        status: "ok" | "error" | "disabled"
        method: credential method used
        bucket: GCS bucket name
        project: GCP project ID
    """
    if not _GCS_CREDS_LOADED or gcs_creds is None:
        return {"status": "disabled", "reason": "gcs_credentials module not available"}
    result = gcs_creds.health_check()
    return result


# Custom metrics endpoint (if instrumentator is not available, fallback to manual)
if not INSTRUMENTATOR_AVAILABLE:
    @app.get("/metrics")
    async def metrics():
        """Prometheus metrics endpoint (fallback)"""
        if not PROMETHEUS_AVAILABLE:
            raise HTTPException(status_code=503, detail="Prometheus client not available")
        
        return Response(
            content=generate_latest(),
            media_type=CONTENT_TYPE_LATEST
        )


@app.post("/refresh", response_model=Dict[str, Any])
async def refresh(request: RefreshRequest):
    """
    Reload production models from local registry.
    
    - If model_name is None: refresh all production models
    - If model_name is provided but version is None: load latest production version
    - If both are provided: load specific model version
    
    Returns models in format: {"model_name": [(version, version), ...]}
    """
    try:
        refresh_models(request.model_name, request.version)
        
        # Build response in documented format
        with _cache_lock:
            if request.model_name:
                # Single model refresh - find the loaded version(s) for this model
                model_versions = []
                for model_key, model_info in _model_cache.items():
                    if model_info['model_name'] == request.model_name:
                        version = int(model_info['version'])
                        model_versions.append((version, version))
                
                if model_versions:
                    # Sort and deduplicate
                    model_versions = sorted(set(model_versions))
                    return {
                        "status": "models loaded",
                        "models": {
                            request.model_name: model_versions
                        }
                    }
                else:
                    return {
                        "status": "error",
                        "message": f"Model {request.model_name} not found after refresh"
                    }
            else:
                # All models refresh - group by model name
                models_dict = {}
                for model_key, model_info in _model_cache.items():
                    model_name = model_info['model_name']
                    version = int(model_info['version'])
                    if model_name not in models_dict:
                        models_dict[model_name] = []
                    models_dict[model_name].append((version, version))
                
                # Sort versions for each model
                for model_name in models_dict:
                    models_dict[model_name] = sorted(set(models_dict[model_name]))
                
                return {
                    "status": "models loaded",
                    "models": models_dict
                }
            
    except Exception as e:
        logger.error(f"Error refreshing models: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/is_model_available", response_model=Dict[str, Any])
async def is_model_available(request: ModelAvailabilityRequest):
    """
    Check if a specific model version is available.
    
    Note: version should be integer (0-indexed, where 0 = v1, 1 = v2, etc.)
    but also accepts MLflow version strings directly.
    """
    # Convert 0-indexed version or v-prefixed string to just the number
    if isinstance(request.version, int):
        mlflow_version = str(request.version + 1)  # 0 -> 1, 1 -> 2, etc.
    else:
        mlflow_version = str(request.version).replace("v", "")
    
    model_key = get_model_key(request.model_name, mlflow_version)
    
    with _cache_lock:
        if model_key in _model_cache:
            return {
                "available": True
            }
        else:
            # Check if model exists in local registry
            try:
                # model_manager.load_model raises ValueError if not found
                path = model_manager.get_local_model_path(request.model_name, mlflow_version)
                if path and os.path.exists(path):
                     return {"available": True}
                return {"available": False}
            except Exception as e:
                return {
                    "available": False
                }


@app.post("/predict", response_model=Dict[str, Any])
async def predict(
    features: List[List[float]],
    model_name: str = Query(..., description="Model name"),
    version: Union[str, int] = Query(..., description="Model version (0-indexed: 0=v1, 1=v2, etc.)")
):
    """
    Make batch predictions using the specified model.
    
    - Maximum 5000 samples per request
    - Features should be a 2D array (list of feature vectors) in JSON body
    - model_name and version are query parameters
    - Returns prediction probabilities
    
    Request body: [[0.1, 0.2, ...], [0.5, 0.6, ...]]
    """
    if not ONNXRUNTIME_AVAILABLE:
        raise HTTPException(
            status_code=503,
            detail="ONNX Runtime not available. Please install onnxruntime."
        )
    
    # Validate input
    if not features:
        raise HTTPException(status_code=400, detail="Features list cannot be empty")
    
    if len(features) > 5000:
        raise HTTPException(
            status_code=400,
            detail="Maximum 5000 samples per request"
        )
    
    # Check feature consistency
    if len(set(len(row) for row in features)) > 1:
        raise HTTPException(
            status_code=400,
            detail="All feature vectors must have the same length"
        )
    
    # Convert 0-indexed version or v-prefixed string to just the number
    if isinstance(version, int):
        mlflow_version = str(version + 1)  # 0 -> 1, 1 -> 2, etc.
    else:
        mlflow_version = str(version).replace("v", "")
    
    model_key = get_model_key(model_name, mlflow_version)
    
    # Check if model is in cache (thread-safe)
    with _cache_lock:
        model_in_cache = model_key in _model_cache
        if model_in_cache:
            model_info = _model_cache[model_key]
            model_lock = _model_locks.get(model_key)
        else:
            model_info = None
            model_lock = None
    
    # If not in cache, try to load it (outside the lock to avoid deadlock)
    if not model_in_cache:
        try:
            logger.info(f"Model {model_key} not in cache, loading...")
            refresh_models(model_name, mlflow_version)
            # Re-acquire lock to get the loaded model
            with _cache_lock:
                if model_key in _model_cache:
                    model_info = _model_cache[model_key]
                    model_lock = _model_locks.get(model_key)
                else:
                    raise HTTPException(
                        status_code=404,
                        detail=f"Model {model_name} version {mlflow_version} failed to load"
                    )
        except Exception as e:
            logger.error(f"Failed to load model {model_key}: {e}")
            raise HTTPException(
                status_code=404,
                detail=f"Model {model_name} version {mlflow_version} not found or failed to load: {str(e)}"
            )
    
    # Make predictions (thread-safe per model)
    if model_lock:
        with model_lock:
            return _make_predictions(model_info, features, model_name, mlflow_version)
    else:
        return _make_predictions(model_info, features, model_name, mlflow_version)


def _make_predictions(
    model_info: Dict[str, Any],
    features: List[List[float]],
    model_name: str,
    version: str
) -> Dict[str, Any]:
    """Internal function to make predictions"""
    start_time = time.time()
    
    try:

        model_type = model_info.get('type', 'onnx')
        
        # Convert features to numpy array
        features_array = np.array(features, dtype=np.float32)

        if model_type == 'onnx':
            session = model_info['session']
            # Get input name from model
            input_name = session.get_inputs()[0].name
            # Run inference
            outputs = session.run(None, {input_name: features_array})
            predictions = outputs[0].tolist()
            
        elif model_type == 'lightgbm':
            model = model_info['model']
            # LightGBM predict returns array
            preds = model.predict(features_array)
            # Ensure it's list of lists or list of values
            if isinstance(preds, np.ndarray):
                predictions = preds.tolist()
            else:
                predictions = list(preds)
            # If 1D array (regression/binary), make it 2D like ONNX usually is for consistency if needed
            # But standard is fine.
            
        elif model_type == 'pytorch':
            import torch
            model = model_info['model']
            device = next(model.parameters()).device
            
            with torch.no_grad():
                inputs = torch.tensor(features_array, dtype=torch.float32).to(device)
                outputs = model(inputs)
                # If tuple (TST), get first
                if isinstance(outputs, tuple):
                    outputs = outputs[0]
                predictions = outputs.cpu().numpy().tolist()
        
        else:
             raise ValueError(f"Unsupported model type for prediction: {model_type}")

        # Common post-processing (logging, metrics) happens below

        

        
        # Calculate latency
        latency = time.time() - start_time
        
        # Update metrics
        if prediction_counter:
            prediction_counter.labels(
                model_name=model_name,
                version=str(version),
                status="success"
            ).inc()
        
        if prediction_latency:
            prediction_latency.labels(
                model_name=model_name,
                version=str(version)
            ).observe(latency)
        
        logger.info(
            f"Made predictions for {len(features)} samples using {model_name} v{version} "
            f"(latency: {latency:.3f}s)"
        )
        
        # Return in documented format
        return {
            "predictions": predictions
        }
        
    except Exception as e:
        logger.error(f"Prediction error for {model_name} v{version}: {e}")
        
        # Update error metrics
        if prediction_counter:
            prediction_counter.labels(
                model_name=model_name,
                version=str(version),
                status="error"
            ).inc()
        
        raise HTTPException(status_code=500, detail=f"Prediction failed: {str(e)}")


@app.get("/models", response_model=List[ModelInfo])
async def list_models():
    """List all loaded models"""
    with _cache_lock:
        logger.info(f"Listing models from cache. Keys: {list(_model_cache.keys())}")
        models = []
        for model_key, model_info in _model_cache.items():
            models.append(ModelInfo(
                model_name=model_info['model_name'],
                version=str(model_info['version']),
                loaded=True,
                input_shape=model_info.get('input_shape'),
                output_shape=model_info.get('output_shape')
            ))
        return models





@app.get("/debug_cache")
async def debug_cache():
    return {
        "id": id(_model_cache),
        "keys": list(_model_cache.keys()),
        "len": len(_model_cache)
    }


# ── Feature engineering constants ──────────────────────────────────────────
_COIN_SYMBOLS = {"BTC": "BTCUSDT", "ETH": "ETHUSDT", "SOL": "SOLUSDT"}

_LGB_FEATURES = [
    "open", "high", "low", "close", "volume", "quote_asset_volume", "trades",
    "taker_base", "taker_quote", "ignore", "return", "log_return",
    "high_low_range", "close_open_range", "rolling_volatility",
    "rolling_mean_5", "rolling_mean_15", "rolling_mean_30", "rolling_std_15",
    "rsi", "macd", "macd_signal", "macd_diff",
    "bb_high", "bb_low", "bb_percent",
    "log_volume", "log_trades", "log_taker_base", "log_taker_quote",
    "log_quote_asset_volume",
    "lag_return_1", "lag_volume_1", "lag_return_3", "lag_volume_3",
    "lag_return_5", "lag_volume_5", "lag_return_15", "lag_volume_15",
]

_TST_FEATURES = ["open", "high", "low", "close", "volume", "taker_base", "taker_quote"]
_TST_SEQ_LEN = 15


def _fetch_binance_klines(symbol: str, limit: int = 80) -> pd.DataFrame:
    """Fetch recent 1-minute klines from Binance public API."""
    url = (
        f"https://api.binance.com/api/v3/klines"
        f"?symbol={symbol}&interval=1m&limit={limit}"
    )
    with urllib.request.urlopen(url, timeout=10) as resp:
        klines = json.loads(resp.read())

    df = pd.DataFrame(klines, columns=[
        "open_time", "open", "high", "low", "close", "volume",
        "close_time", "quote_asset_volume", "trades",
        "taker_base", "taker_quote", "ignore",
    ])
    numeric_cols = ["open", "high", "low", "close", "volume",
                    "quote_asset_volume", "trades", "taker_base", "taker_quote", "ignore"]
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def _engineer_features(df: pd.DataFrame) -> pd.DataFrame:
    """Compute all LightGBM + TST features from raw OHLCV DataFrame."""
    df = df.copy()

    # Basic derived features
    df["return"] = (df["close"] - df["open"]) / df["open"]
    df["log_return"] = np.log((df["close"] / df["open"]).clip(lower=1e-10))
    df["high_low_range"] = (df["high"] - df["low"]) / df["close"].clip(lower=1e-10)
    df["close_open_range"] = (df["close"] - df["open"]) / df["open"].clip(lower=1e-10)

    # Rolling window features
    df["rolling_volatility"] = df["return"].rolling(5).std()
    df["rolling_mean_5"] = df["close"].rolling(5).mean()
    df["rolling_mean_15"] = df["close"].rolling(15).mean()
    df["rolling_mean_30"] = df["close"].rolling(30).mean()
    df["rolling_std_15"] = df["close"].rolling(15).std()

    # RSI (14-period)
    delta = df["close"].diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    rs = gain / loss.replace(0, np.nan)
    df["rsi"] = 100 - (100 / (1 + rs))

    # MACD
    ema12 = df["close"].ewm(span=12, adjust=False).mean()
    ema26 = df["close"].ewm(span=26, adjust=False).mean()
    df["macd"] = ema12 - ema26
    df["macd_signal"] = df["macd"].ewm(span=9, adjust=False).mean()
    df["macd_diff"] = df["macd"] - df["macd_signal"]

    # Bollinger Bands (20-period)
    sma20 = df["close"].rolling(20).mean()
    std20 = df["close"].rolling(20).std()
    df["bb_high"] = sma20 + 2 * std20
    df["bb_low"] = sma20 - 2 * std20
    bb_range = (df["bb_high"] - df["bb_low"]).replace(0, np.nan)
    df["bb_percent"] = (df["close"] - df["bb_low"]) / bb_range

    # Log-transformed volume features
    df["log_volume"] = np.log(df["volume"].clip(lower=1e-10))
    df["log_trades"] = np.log(df["trades"].clip(lower=1e-10))
    df["log_taker_base"] = np.log(df["taker_base"].clip(lower=1e-10))
    df["log_taker_quote"] = np.log(df["taker_quote"].clip(lower=1e-10))
    df["log_quote_asset_volume"] = np.log(df["quote_asset_volume"].clip(lower=1e-10))

    # Lag features
    df["lag_return_1"] = df["return"].shift(1)
    df["lag_volume_1"] = df["volume"].shift(1)
    df["lag_return_3"] = df["return"].shift(3)
    df["lag_volume_3"] = df["volume"].shift(3)
    df["lag_return_5"] = df["return"].shift(5)
    df["lag_volume_5"] = df["volume"].shift(5)
    df["lag_return_15"] = df["return"].shift(15)
    df["lag_volume_15"] = df["volume"].shift(15)

    return df


def _run_lgb_signal(model_info: Dict, df_clean: pd.DataFrame):
    """Run LightGBM inference on the latest feature row."""
    available = [c for c in _LGB_FEATURES if c in df_clean.columns]
    last_row = df_clean[available].iloc[[-1]].values.astype(np.float32)

    model_type = model_info.get("type", "onnx")
    if model_type == "onnx":
        session = model_info["session"]
        input_name = session.get_inputs()[0].name
        # Pad / truncate to match expected feature count
        expected = session.get_inputs()[0].shape[1]
        if isinstance(expected, int) and last_row.shape[1] != expected:
            padded = np.zeros((1, expected), dtype=np.float32)
            cols = min(last_row.shape[1], expected)
            padded[:, :cols] = last_row[:, :cols]
            last_row = padded
        outputs = session.run(None, {input_name: last_row})
        # LightGBM ONNX has two outputs: [label (int64), probabilities (seq of map)]
        # Extract the probability map from the second output
        prob_output = outputs[1]  # seq(map(int64, tensor(float)))
        if isinstance(prob_output, list) and len(prob_output) > 0:
            prob_map = prob_output[0]  # first sample's dict {0: p0, 1: p1, 2: p2}
            probs = np.array([float(prob_map[0]), float(prob_map[1]), float(prob_map[2])], dtype=float)
        else:
            # Fallback: use the label output
            probs = np.zeros(3, dtype=float)
            probs[int(outputs[0][0])] = 1.0
    elif model_type == "lightgbm":
        raw = model_info["model"].predict(last_row)
        probs = raw[0] if raw.ndim > 1 else raw
        probs = np.array(probs[:3], dtype=float)
    else:
        return None

    return probs


def _run_tst_signal(model_info: Dict, df: pd.DataFrame, version: str):
    """Run TST (Time Series Transformer) inference on the latest sequence."""
    # Use available TST features; fall back to price_change if taker cols missing
    available_tst = [c for c in _TST_FEATURES if c in df.columns and not df[c].isna().all()]
    if len(available_tst) < 5:
        return None

    tst_df = df.dropna(subset=available_tst)
    if len(tst_df) < _TST_SEQ_LEN:
        return None

    tst_data = tst_df[available_tst].iloc[-_TST_SEQ_LEN:].values.astype(np.float32)

    # Apply the saved StandardScaler if available
    scaler_path = project_root / f"models/tst/v{version}/scaler.pkl"
    if scaler_path.exists():
        try:
            scaler = joblib.load(str(scaler_path))
            tst_data = scaler.transform(tst_data)
        except Exception as e:
            logger.warning(f"Could not apply TST scaler v{version}: {e}")

    model_type = model_info.get("type", "onnx")

    if model_type == "onnx":
        session = model_info["session"]
        input_shape = session.get_inputs()[0].shape  # e.g. [None, 15, 7] or [None, 105]
        if len(input_shape) == 3:
            n_feat = input_shape[2] if isinstance(input_shape[2], int) else tst_data.shape[1]
            seq_len = input_shape[1] if isinstance(input_shape[1], int) else _TST_SEQ_LEN
            # Pad feature dim if needed
            if tst_data.shape[1] < n_feat:
                pad = np.zeros((_TST_SEQ_LEN, n_feat - tst_data.shape[1]), dtype=np.float32)
                tst_data = np.concatenate([tst_data, pad], axis=1)
            tst_input = tst_data[:seq_len].reshape(1, seq_len, n_feat)
        else:
            # Flattened 2-D input
            tst_input = tst_data.reshape(1, -1)
        input_name = session.get_inputs()[0].name
        raw = session.run(None, {input_name: tst_input})[0]
        logits = raw[0]  # shape (3,) — raw logits, apply softmax
        e = np.exp(logits - np.max(logits))
        probs = e / e.sum()

    elif model_type == "pytorch":
        import torch
        model = model_info["model"]
        tst_input = torch.tensor(
            tst_data.reshape(1, _TST_SEQ_LEN, tst_data.shape[1]), dtype=torch.float32
        )
        with torch.no_grad():
            out = model(tst_input)
            if isinstance(out, tuple):
                out = out[0]
            probs = torch.softmax(out, dim=-1).cpu().numpy()[0]
    else:
        return None

    return np.array(probs[:3], dtype=float)


@app.get("/signals")
async def get_signals(
    coin: str = Query("BTC", description="Coin symbol: BTC, ETH, or SOL"),
):
    """
    Get live SELL / HOLD / BUY signals for a coin from all loaded models.

    Fetches the latest 80 one-minute Binance candles, engineers the full
    feature set (matching the training pipeline), runs every loaded model,
    and returns per-model probabilities plus an equal-weight ensemble consensus.
    """
    coin = coin.upper()
    symbol = _COIN_SYMBOLS.get(coin, f"{coin}USDT")

    # ── 1. Fetch live Binance candles ──────────────────────────────────────
    try:
        raw_df = _fetch_binance_klines(symbol, limit=80)
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Failed to fetch Binance data for {symbol}: {exc}",
        )

    if len(raw_df) < 30:
        raise HTTPException(
            status_code=422,
            detail="Not enough candle data returned from Binance",
        )

    # ── 2. Engineer features ───────────────────────────────────────────────
    feat_df = _engineer_features(raw_df)
    df_clean = feat_df.dropna(subset=_LGB_FEATURES[:10])  # require base cols

    if len(df_clean) == 0:
        raise HTTPException(
            status_code=422,
            detail="Feature engineering produced no valid rows",
        )

    latest_price = float(df_clean["close"].iloc[-1])

    # ── 3. Run each loaded model ───────────────────────────────────────────
    with _cache_lock:
        models_snapshot = dict(_model_cache)

    model_signals = []
    for model_key, model_info in models_snapshot.items():
        model_name = model_info["model_name"]
        version = str(model_info["version"])
        try:
            if "lightgbm" in model_name.lower():
                probs = _run_lgb_signal(model_info, df_clean)
            elif "tst" in model_name.lower():
                probs = _run_tst_signal(model_info, feat_df, version)
            else:
                continue

            if probs is None or len(probs) < 3:
                continue

            signal_idx = int(np.argmax(probs))
            model_signals.append({
                "model_name": model_name,
                "version": version,
                "signal": ["SELL", "HOLD", "BUY"][signal_idx],
                "confidence": round(float(probs[signal_idx]), 4),
                "probabilities": {
                    "sell": round(float(probs[0]), 4),
                    "hold": round(float(probs[1]), 4),
                    "buy": round(float(probs[2]), 4),
                },
            })
        except Exception as exc:
            logger.error(f"Signal inference failed for {model_key}: {exc}")

    # ── 4. Ensemble consensus (equal-weight average) ───────────────────────
    consensus = None
    if model_signals:
        avg = np.mean(
            [[s["probabilities"]["sell"], s["probabilities"]["hold"], s["probabilities"]["buy"]]
             for s in model_signals],
            axis=0,
        )
        consensus_idx = int(np.argmax(avg))
        consensus = {
            "signal": ["SELL", "HOLD", "BUY"][consensus_idx],
            "confidence": round(float(avg[consensus_idx]), 4),
            "probabilities": {
                "sell": round(float(avg[0]), 4),
                "hold": round(float(avg[1]), 4),
                "buy": round(float(avg[2]), 4),
            },
        }

    return {
        "coin": coin,
        "symbol": symbol,
        "latest_price": latest_price,
        "candles_used": len(df_clean),
        "models": model_signals,
        "consensus": consensus,
    }


# ── Pipeline monitoring endpoints (Airflow REST API-backed) ──────────────────
# Queries the Apache Airflow REST API (port 8080) running in Docker.
# DAGs available: training_pipeline, trl_inference_pipeline, consumer_start,
#                 consumer_delete, cleanup_old_events
# Auth: basic_auth (admin:admin by default, configurable via env vars)

import base64 as _b64

_AIRFLOW_API_BASE = os.getenv("AIRFLOW_API_URL", "http://localhost:8080/api/v1")
_AIRFLOW_USER     = os.getenv("AIRFLOW_API_USER", "admin")
_AIRFLOW_PASS     = os.getenv("AIRFLOW_API_PASS", "admin")
_AIRFLOW_AUTH     = _b64.b64encode(f"{_AIRFLOW_USER}:{_AIRFLOW_PASS}".encode()).decode()


def _airflow_get(path: str) -> dict:
    """GET a path from the Airflow REST API. Returns parsed JSON or raises."""
    url = f"{_AIRFLOW_API_BASE}{path}"
    req = urllib.request.Request(
        url,
        headers={"Authorization": f"Basic {_AIRFLOW_AUTH}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=8) as resp:
        return json.loads(resp.read())


def _norm_airflow_state(state: Optional[str]) -> str:
    """Map Airflow task/dag states to the frontend status vocabulary."""
    s = (state or "").lower()
    if s == "success":           return "success"
    if s in ("failed",):         return "failed"
    if s == "upstream_failed":   return "skipped"   # shown as skipped in UI
    if s == "running":           return "running"
    if s in ("queued", "scheduled", "up_for_retry"): return "queued"
    if s == "skipped":           return "skipped"
    if s in ("no_status", ""):   return "queued"
    return "queued"


def _airflow_task_instances(dag_id: str, run_id: str) -> list:
    """Fetch all task instances for a DAG run."""
    path = f"/dags/{dag_id}/dagRuns/{run_id}/taskInstances?limit=100"
    data = _airflow_get(path)
    return data.get("task_instances", [])


@app.get("/pipeline/events")
async def get_pipeline_events(
    dag_id: str = Query("training_pipeline", description="Airflow DAG ID"),
    run_id: Optional[str] = Query(None, description="Filter to one DAG run ID"),
    limit: int = Query(200, ge=1, le=500, description="Max events to return"),
):
    """
    Return pipeline events from Airflow task instances.
    Each task instance in each DAG run becomes one event row.
    Response shape: [{id, event, run_id, status, message, ts}]
    """
    try:
        # Fetch all DAG runs (newest first)
        runs_data = _airflow_get(f"/dags/{dag_id}/dagRuns?limit=20&order_by=-execution_date")
        dag_runs = runs_data.get("dag_runs", [])
    except Exception as exc:
        logger.error(f"get_pipeline_events: failed to fetch DAG runs: {exc}")
        return []

    result = []
    idx = 1
    for run in dag_runs:
        rid = run["dag_run_id"]
        if run_id and rid != run_id:
            continue
        try:
            task_instances = _airflow_task_instances(dag_id, rid)
        except Exception as exc:
            logger.warning(f"get_pipeline_events: skipping run {rid}: {exc}")
            continue

        for ti in task_instances:
            state = _norm_airflow_state(ti.get("state"))
            ts = ti.get("end_date") or ti.get("start_date") or run.get("start_date")
            duration = ti.get("duration")
            message = f"Duration: {round(duration, 2)}s" if duration else f"Run state: {run.get('state', '')}"
            result.append({
                "id": idx,
                "event": ti["task_id"],
                "run_id": rid,
                "status": state,
                "message": message,
                "ts": ts,
            })
            idx += 1
            if idx > limit:
                break
        if idx > limit:
            break

    return result


@app.get("/pipeline/runs")
async def get_pipeline_runs(
    dag_id: str = Query("training_pipeline", description="Airflow DAG ID"),
    run_id: Optional[str] = Query(None, description="Filter to one DAG run ID; defaults to latest"),
):
    """
    Return Gantt-compatible task run data from Airflow task instances.
    Response shape: [{task_id, dag_run_id, start_time, end_time, state}]
    """
    try:
        runs_data = _airflow_get(f"/dags/{dag_id}/dagRuns?limit=10&order_by=-execution_date")
        dag_runs = runs_data.get("dag_runs", [])
    except Exception as exc:
        logger.error(f"get_pipeline_runs: failed to fetch DAG runs: {exc}")
        return []

    if not dag_runs:
        return []

    # Use specified run or default to the most recent one
    target_run_id = run_id or dag_runs[0]["dag_run_id"]

    try:
        task_instances = _airflow_task_instances(dag_id, target_run_id)
    except Exception as exc:
        logger.error(f"get_pipeline_runs: failed to fetch task instances: {exc}")
        return []

    result = []
    for ti in task_instances:
        state = _norm_airflow_state(ti.get("state"))
        start = ti.get("start_date")
        end = ti.get("end_date")
        result.append({
            "task_id":     ti["task_id"],
            "dag_run_id":  target_run_id,
            "start_time":  start,
            "end_time":    end if end != start else None,
            "state":       state,
        })
    return result


@app.get("/pipeline/dag")
async def get_pipeline_dag(
    dag_id: str = Query("training_pipeline", description="Airflow DAG ID"),
):
    """
    Return the real Airflow DAG dependency graph with live task states
    from the most recent DAG run.
    Response shape: {tasks: [{id, state, depends_on}]}
    """
    # ── 1. Fetch task structure (downstream → reverse to depends_on) ─────────
    try:
        tasks_data = _airflow_get(f"/dags/{dag_id}/tasks")
        task_list = tasks_data.get("tasks", [])
    except Exception as exc:
        logger.error(f"get_pipeline_dag: failed to fetch tasks: {exc}")
        return {"tasks": []}

    # Build upstream map by reversing downstream_task_ids
    downstream: Dict[str, List[str]] = {t["task_id"]: t.get("downstream_task_ids", []) for t in task_list}
    depends_on_map: Dict[str, List[str]] = {tid: [] for tid in downstream}
    for tid, downstreams in downstream.items():
        for ds in downstreams:
            if ds in depends_on_map:
                depends_on_map[ds].append(tid)

    # ── 2. Fetch latest run's task instance states ───────────────────────────
    task_states: Dict[str, str] = {tid: "queued" for tid in downstream}
    try:
        runs_data = _airflow_get(f"/dags/{dag_id}/dagRuns?limit=1&order_by=-execution_date")
        latest_runs = runs_data.get("dag_runs", [])
        if latest_runs:
            latest_run_id = latest_runs[0]["dag_run_id"]
            tis = _airflow_task_instances(dag_id, latest_run_id)
            for ti in tis:
                task_states[ti["task_id"]] = _norm_airflow_state(ti.get("state"))
    except Exception as exc:
        logger.warning(f"get_pipeline_dag: could not fetch live states: {exc}")

    tasks = [
        {"id": tid, "state": task_states.get(tid, "queued"), "depends_on": deps}
        for tid, deps in depends_on_map.items()
    ]
    return {"tasks": tasks}


# ── Live prediction streaming (SSE) ──────────────────────────────────────────

async def _run_coin_inference_async(coin: str) -> List[Dict]:
    """
    Run LightGBM + TST inference for one coin.
    Fetches Binance candles in a thread pool to avoid blocking the event loop.
    Returns a list of prediction dicts ready for the SSE buffer.
    """
    symbol = _COIN_SYMBOLS.get(coin, f"{coin}USDT")
    loop = asyncio.get_event_loop()

    try:
        raw_df = await loop.run_in_executor(
            None, lambda: _fetch_binance_klines(symbol, limit=80)
        )
    except Exception as exc:
        logger.warning(f"Background fetch failed for {symbol}: {exc}")
        return []

    feat_df = _engineer_features(raw_df)
    df_clean = feat_df.dropna(subset=_LGB_FEATURES[:10])
    if len(df_clean) == 0:
        return []

    latest_price = float(df_clean["close"].iloc[-1])

    with _cache_lock:
        models_snapshot = dict(_model_cache)

    results = []
    for model_key, model_info in models_snapshot.items():
        model_name = model_info["model_name"]
        version = str(model_info["version"])
        try:
            if "lightgbm" in model_name.lower():
                probs = _run_lgb_signal(model_info, df_clean)
                model_label = "LightGBM"
            elif "tst" in model_name.lower():
                probs = _run_tst_signal(model_info, feat_df, version)
                model_label = "TST"
            else:
                continue

            if probs is None or len(probs) < 3:
                continue

            signal_idx = int(np.argmax(probs))
            signal = ["SELL", "HOLD", "BUY"][signal_idx]
            pred = {
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "coin": coin,
                "model": model_label,
                "model_name": model_name,
                "version": version,
                "signal": signal,
                "predicted_direction": "UP" if signal == "BUY" else ("DOWN" if signal == "SELL" else "HOLD"),
                "confidence": round(float(probs[signal_idx]), 4),
                "probabilities": {
                    "sell": round(float(probs[0]), 4),
                    "hold": round(float(probs[1]), 4),
                    "buy": round(float(probs[2]), 4),
                },
                "actual_price": latest_price,
            }
            results.append(pred)
        except Exception as exc:
            logger.error(f"Background inference error for {model_key}/{coin}: {exc}")

    return results


async def _inference_background_task():
    """
    Periodically runs inference for all supported coins and pushes results to
    the shared _prediction_buffer, all active SSE subscriber queues, and all
    active WebSocket clients.
    Runs every 15 seconds.
    """
    coins = ["BTC", "ETH", "SOL"]
    logger.info("Background inference task started")
    while True:
        for coin in coins:
            try:
                preds = await _run_coin_inference_async(coin)
                for pred in preds:
                    _prediction_buffer.append(pred)
                    # Broadcast to SSE subscribers
                    for q in _sse_subscribers.copy():
                        try:
                            q.put_nowait(pred)
                        except asyncio.QueueFull:
                            pass
                    # Broadcast to WebSocket clients (best-effort, defined later in file)
                    try:
                        await _broadcast_to_ws_clients(pred)
                    except Exception:
                        pass
                if preds:
                    logger.debug(f"Background task produced {len(preds)} predictions for {coin}")
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.error(f"Background task error for {coin}: {exc}")
        await asyncio.sleep(15)


@app.get("/predictions/latest")
async def get_latest_predictions(limit: int = Query(20, ge=1, le=200)):
    """
    Return the most recent predictions from the in-memory ring buffer.
    Newest first. Populated by the background inference task.
    """
    data = list(_prediction_buffer)
    data.reverse()  # newest first
    return {
        "predictions": data[:limit],
        "count": len(data),
        "last_updated": data[0]["timestamp"] if data else None,
    }


@app.get("/predictions/history")
async def get_prediction_history():
    """Return all buffered predictions (up to 200), newest first."""
    data = list(_prediction_buffer)
    data.reverse()
    return data


@app.get("/predictions/stream")
async def stream_predictions(request: Request):
    """
    Server-Sent Events endpoint.
    On connect: replays the last 20 buffered predictions.
    Then streams new predictions as they are produced by the background task.
    Keepalive comment sent every 30 s to prevent proxy timeouts.
    """
    async def event_gen():
        # Replay recent history first
        history = list(_prediction_buffer)[-20:]
        for pred in history:
            if await request.is_disconnected():
                return
            yield f"data: {json.dumps(pred)}\n\n"

        # Subscribe to live updates
        queue: asyncio.Queue = asyncio.Queue(maxsize=50)
        _sse_subscribers.append(queue)
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    pred = await asyncio.wait_for(queue.get(), timeout=30.0)
                    yield f"data: {json.dumps(pred)}\n\n"
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        finally:
            if queue in _sse_subscribers:
                _sse_subscribers.remove(queue)

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ── WebSocket live predictions ────────────────────────────────────────────────
# _ws_clients is declared as a module-level list above (_ws_clients: List = [])
# All WS operations run on the single asyncio event loop, so no lock is needed.


@app.websocket("/ws/predictions")
async def ws_predictions(websocket: WebSocket):
    """
    WebSocket endpoint for live predictions.
    On connect: replays the last 20 buffered predictions.
    Then the connection stays open; the background inference task broadcasts
    new predictions via _broadcast_to_ws_clients().
    """
    await websocket.accept()
    _ws_clients.append(websocket)
    try:
        # Replay recent history
        history = list(_prediction_buffer)[-20:]
        for pred in history:
            await websocket.send_text(json.dumps(pred))

        # Keep connection alive; the background task will push new predictions
        while True:
            try:
                await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
            except asyncio.TimeoutError:
                # Send keepalive to prevent proxy timeouts
                await websocket.send_text(json.dumps({"type": "keepalive"}))
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        if websocket in _ws_clients:
            _ws_clients.remove(websocket)


async def _broadcast_to_ws_clients(pred: dict):
    """Broadcast a single prediction dict to all connected WebSocket clients."""
    if not _ws_clients:
        return
    payload = json.dumps(pred)
    dead = []
    for ws in list(_ws_clients):
        try:
            await ws.send_text(payload)
        except Exception:
            dead.append(ws)
    for ws in dead:
        if ws in _ws_clients:
            _ws_clients.remove(ws)


# ── /predictions/test — inject synthetic predictions for frontend testing ─────

_FAKE_COINS = ["BTC", "ETH", "SOL"]
_FAKE_MODELS = ["TST", "LightGBM"]


@app.get("/predictions/test")
async def inject_test_predictions():
    """
    Inject 5 synthetic predictions (one per coin/model combo) into the ring
    buffer and broadcast to all live SSE / WebSocket clients.
    Useful for testing the frontend widget without a running consumer.
    """
    import random

    # Fetch a real price for each coin so numbers look plausible
    real_prices = {}
    for coin in _FAKE_COINS:
        symbol = _COIN_SYMBOLS.get(coin, f"{coin}USDT")
        try:
            loop = asyncio.get_event_loop()
            df = await loop.run_in_executor(
                None, lambda s=symbol: _fetch_binance_klines(s, limit=1)
            )
            real_prices[coin] = float(df["close"].iloc[-1]) if not df.empty else None
        except Exception:
            real_prices[coin] = None

    combos = [
        ("BTC", "TST"),
        ("BTC", "LightGBM"),
        ("ETH", "TST"),
        ("SOL", "LightGBM"),
        ("ETH", "LightGBM"),
    ]

    injected = []
    for coin, model in combos:
        probs = [random.random() for _ in range(3)]
        total = sum(probs)
        probs = [p / total for p in probs]
        signal_idx = int(max(range(3), key=lambda i: probs[i]))
        signal = ["SELL", "HOLD", "BUY"][signal_idx]
        pred = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "coin": coin,
            "model": model,
            "model_name": model.lower().replace(" ", ""),
            "version": "3",
            "signal": signal,
            "predicted_direction": "UP" if signal == "BUY" else ("DOWN" if signal == "SELL" else "HOLD"),
            "confidence": round(float(probs[signal_idx]), 4),
            "probabilities": {
                "sell": round(float(probs[0]), 4),
                "hold": round(float(probs[1]), 4),
                "buy": round(float(probs[2]), 4),
            },
            "actual_price": real_prices.get(coin),
        }
        _prediction_buffer.append(pred)
        injected.append(pred)

        # Broadcast to SSE subscribers
        for q in _sse_subscribers.copy():
            try:
                q.put_nowait(pred)
            except asyncio.QueueFull:
                pass

        # Broadcast to WebSocket clients
        await _broadcast_to_ws_clients(pred)

    return {"status": "ok", "injected": len(injected), "predictions": injected}


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)

