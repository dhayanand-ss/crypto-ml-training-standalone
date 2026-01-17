"""
FastAPI ML Model Inference API

Serves ML models for predictions with:
- Model management: loads models from MLflow using pyfunc (RECOMMENDED) with ONNX fallback
- Loads by Production stage, falls back to latest version if no stage set
- Prometheus metrics: /metrics
- Thread-safe model refresh with locks
- Batch predictions (up to 5000 per request)
"""

import os
import logging
import threading
import time
from typing import Dict, List, Optional, Any, Union
from contextlib import asynccontextmanager

import numpy as np
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse, RedirectResponse
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
from utils.serve.data_api import router as data_api_router, start_background_tasks
import asyncio

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

# Check MLflow availability
try:
    import mlflow
    MLFLOW_AVAILABLE = True
except ImportError:
    MLFLOW_AVAILABLE = False

# Helper function to detect if running in Docker
def is_running_in_docker() -> bool:
    """
    Detect if the application is running inside a Docker container.
    Checks multiple indicators of Docker environment.
    """
    # Check for .dockerenv file (most reliable)
    if os.path.exists("/.dockerenv"):
        return True
    
    # Check if hostname looks like a container ID (12+ hex chars)
    import socket
    hostname = socket.gethostname()
    if len(hostname) >= 12 and all(c in '0123456789abcdef' for c in hostname.lower()):
        return True
    
    # Check for Docker-specific environment variables
    if os.getenv("container") == "docker" or os.getenv("DOCKER_CONTAINER"):
        return True
    
    return False

def normalize_mlflow_uri(uri: str) -> str:
    """
    Normalize MLflow URI based on environment.
    
    Rule: Only fix Docker hostnames when running locally (not in Docker).
    Never switch hostnames in Docker - respect the environment variable.
    
    Args:
        uri: MLflow tracking URI from environment
        
    Returns:
        Normalized URI (unchanged in Docker, fixed for local dev)
    """
    in_docker = is_running_in_docker()
    
    # If running locally and URI contains Docker hostname, switch to localhost
    if not in_docker:
        if "mlflow" in uri and "localhost" not in uri and "127.0.0.1" not in uri:
            logger.info(f"Running locally - converting Docker hostname '{uri}' to 'http://localhost:5000'")
            return "http://localhost:5000"
    
    # In Docker or other environments, keep the URI as-is
    return uri


def connect_to_mlflow_with_retry(tracking_uri: str, max_retries: int = 10, initial_delay: float = 2.0) -> ModelManager:
    """
    Connect to MLflow with exponential backoff retry logic.
    
    Never switches hostnames - only retries with the provided URI.
    Fails fast with clear error if MLflow is unreachable after all retries.
    
    Args:
        tracking_uri: MLflow tracking URI (never changed)
        max_retries: Maximum number of retry attempts
        initial_delay: Initial delay in seconds (doubles each retry)
        
    Returns:
        ModelManager instance connected to MLflow
        
    Raises:
        RuntimeError: If MLflow is unreachable after all retries
    """
    delay = initial_delay
    
    for attempt in range(max_retries):
        try:
            logger.info(f"Attempting to connect to MLflow at {tracking_uri} (attempt {attempt + 1}/{max_retries})")
            model_manager = ModelManager(tracking_uri=tracking_uri)
            # Test connection
            model_manager.client.search_registered_models()
            logger.info(f"Successfully connected to MLflow at {tracking_uri}")
            return model_manager
        except Exception as e:
            error_str = str(e)
            if attempt < max_retries - 1:
                logger.warning(f"MLflow connection attempt {attempt + 1} failed: {error_str}")
                logger.info(f"Retrying in {delay:.1f} seconds...")
                time.sleep(delay)
                delay *= 2  # Exponential backoff
            else:
                # Final attempt failed
                error_msg = (
                    f"Failed to connect to MLflow at {tracking_uri} after {max_retries} attempts. "
                    f"Last error: {error_str}. "
                    f"Please verify MLflow is running and accessible at the configured URI."
                )
                logger.error(error_msg)
                raise RuntimeError(error_msg) from e
    
    # Should never reach here, but just in case
    raise RuntimeError(f"Failed to connect to MLflow at {tracking_uri} after {max_retries} attempts")

# Initialize ModelManager with proper URI handling and retry logic
# Rule: Environment variable decides the host - never auto-switch hostnames
initial_uri = os.getenv("MLFLOW_TRACKING_URI", "http://localhost:5000")
logger.info(f"MLflow Tracking URI from environment: {initial_uri}")

# Normalize URI (only fixes Docker hostnames when running locally)
mlflow_tracking_uri = normalize_mlflow_uri(initial_uri)
if mlflow_tracking_uri != initial_uri:
    logger.info(f"Normalized MLflow URI: {mlflow_tracking_uri}")
    os.environ["MLFLOW_TRACKING_URI"] = mlflow_tracking_uri

# Connect to MLflow with retry logic (never switches hostnames)
# This will retry with exponential backoff if MLflow is temporarily unavailable
try:
    model_manager = connect_to_mlflow_with_retry(mlflow_tracking_uri, max_retries=1, initial_delay=1.0)
    logger.info(f"MLflow connection established successfully at {mlflow_tracking_uri}")
except RuntimeError as e:
    # MLflow is unreachable after all retries - log error but don't crash the app
    # The app can still start, but model loading will fail gracefully
    logger.error(f"CRITICAL: {e}")
    logger.warning("FastAPI will start, but model operations will fail until MLflow is available")
    # Create a dummy ModelManager to prevent crashes - actual operations will fail gracefully
    model_manager = None


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
    input_shape: Optional[List[int]] = None
    output_shape: Optional[List[int]] = None


def get_model_key(model_name: str, version: Union[str, int]) -> str:
    """Generate a unique key for model cache"""
    return f"{model_name}:{version}"


def load_production_models() -> Dict[str, Any]:
    """
    Load all production models from MLflow using pyfunc (RECOMMENDED).
    Falls back to version-based loading if no Production stage is set.
    Returns a dictionary of model_key -> PyFuncModel or ONNX InferenceSession
    """
    global model_manager, mlflow_tracking_uri
    
    loaded_models = {}
    
    # Check if model_manager is available (might be None if MLflow connection failed at startup)
    if model_manager is None:
        logger.error("ModelManager is not available - MLflow connection failed at startup")
        return loaded_models
    
    try:
        # Get registered models with retry logic (never switches hostnames)
        # Use the same retry pattern as initialization
        registered_models = None
        max_retries = 5
        delay = 1.0
        
        for attempt in range(max_retries):
            try:
                registered_models = model_manager.client.search_registered_models()
                break  # Success
            except Exception as e:
                error_str = str(e)
                if attempt < max_retries - 1:
                    logger.warning(f"Failed to fetch registered models (attempt {attempt + 1}/{max_retries}): {error_str}")
                    logger.info(f"Retrying in {delay:.1f} seconds...")
                    time.sleep(delay)
                    delay *= 2  # Exponential backoff
                else:
                    # Final attempt failed - re-raise the exception
                    logger.error(f"Failed to fetch registered models after {max_retries} attempts: {error_str}")
                    raise
        
        if registered_models is None:
            raise RuntimeError("Failed to fetch registered models from MLflow")
        
        logger.info(f"Found {len(registered_models)} registered model(s) in MLflow")
        
        if not registered_models:
            logger.warning("No registered models found in MLflow. Make sure models are registered.")
            return loaded_models
        
        total_production_versions = 0
        for model in registered_models:
            model_name = model.name
            logger.info(f"Checking model: {model_name}")
            
            # Get production versions
            try:
                versions = model_manager.client.get_latest_versions(
                    model_name,
                    stages=["Production"]
                )
                logger.info(f"Found {len(versions)} Production version(s) for {model_name}")
                
                # FALLBACK: If no Production stage, load by version (latest version)
                if not versions:
                    logger.warning(f"No Production versions found for {model_name}. Falling back to latest version.")
                    all_versions = model_manager.client.search_model_versions(f"name='{model_name}'")
                    if all_versions:
                        # Sort by version number and get latest
                        sorted_versions = sorted(all_versions, key=lambda v: int(v.version))
                        versions = [sorted_versions[-1]]  # Latest version
                        logger.info(f"Loading latest version {versions[0].version} for {model_name}")
                    else:
                        logger.warning(f"No versions found for {model_name}")
                        continue
                
                total_production_versions += len(versions)
                
                for version_obj in versions:
                    version = version_obj.version
                    model_key = get_model_key(model_name, version)
                    
                    try:
                        logger.info(f"Loading model: {model_name} version {version} using pyfunc (RECOMMENDED)")
                        
                        # Try pyfunc loading first (RECOMMENDED)
                        try:
                            pyfunc_model = model_manager.load_model_pyfunc(model_name, version=version)
                            
                            # Get model info for input/output shapes (if available)
                            input_shape = None
                            output_shape = None
                            try:
                                model_uri = f"models:/{model_name}/{version}"
                                model_info = mlflow.models.get_model_info(model_uri)
                                # Try to infer shape from model signature if available
                                if hasattr(model_info, 'signature') and model_info.signature:
                                    if model_info.signature.inputs:
                                        input_shape = [None]  # Dynamic batch size
                                        if len(model_info.signature.inputs) > 0:
                                            # Try to get feature count from first input
                                            first_input = model_info.signature.inputs[0]
                                            if hasattr(first_input, 'shape'):
                                                input_shape = list(first_input.shape)
                            except Exception:
                                pass  # Shape info not critical
                            
                            loaded_models[model_key] = {
                                'model': pyfunc_model,
                                'model_type': 'pyfunc',
                                'model_name': model_name,
                                'version': version,
                                'input_shape': input_shape,
                                'output_shape': output_shape,
                                'loaded_at': time.time()
                            }
                            
                            logger.info(f"Successfully loaded {model_key} using pyfunc")
                            
                        except Exception as pyfunc_error:
                            # Fallback to ONNX if pyfunc fails
                            logger.warning(f"Pyfunc loading failed for {model_key}: {pyfunc_error}. Trying ONNX...")
                            try:
                                ort_session = model_manager.load_onnx_model(model_name, version)
                                
                                # Get input/output shapes
                                input_shape = None
                                output_shape = None
                                if ort_session.get_inputs():
                                    input_shape = list(ort_session.get_inputs()[0].shape)
                                if ort_session.get_outputs():
                                    output_shape = list(ort_session.get_outputs()[0].shape)
                                
                                loaded_models[model_key] = {
                                    'session': ort_session,
                                    'model_type': 'onnx',
                                    'model_name': model_name,
                                    'version': version,
                                    'input_shape': input_shape,
                                    'output_shape': output_shape,
                                    'loaded_at': time.time()
                                }
                                
                                logger.info(f"Successfully loaded {model_key} using ONNX (fallback)")
                            except Exception as onnx_error:
                                logger.error(f"Both pyfunc and ONNX loading failed for {model_key}: {onnx_error}")
                                raise
                        
                        if active_models:
                            active_models.labels(model_name=model_name, version=str(version)).set(1)
                            
                    except Exception as e:
                        logger.error(f"Failed to load {model_key}: {e}", exc_info=True)
                        if model_load_errors:
                            model_load_errors.labels(model_name=model_name, version=str(version)).inc()
                        
            except Exception as e:
                logger.error(f"Error getting versions for {model_name}: {e}", exc_info=True)
        
        logger.info(f"Total versions found: {total_production_versions}, Successfully loaded: {len(loaded_models)}")
        
        if total_production_versions > 0 and len(loaded_models) == 0:
            logger.error("Models exist but none could be loaded. Check model availability and logs above.")
                    
    except Exception as e:
        logger.error(f"Error loading models: {e}", exc_info=True)
    
    return loaded_models


def refresh_models(model_name: Optional[str] = None, version: Optional[Union[str, int]] = None):
    """
    Thread-safe model refresh.
    If model_name is None, refresh all production models.
    If version is None, load latest production version.
    """
    global _model_cache, model_manager, mlflow_tracking_uri
    
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
                # Load latest production version, fallback to latest version if no Production
                try:
                    versions = model_manager.client.get_latest_versions(
                        model_name,
                        stages=["Production"]
                    )
                    if not versions:
                        # FALLBACK: Load by version (latest)
                        logger.warning(f"No Production versions found for {model_name}. Loading latest version.")
                        all_versions = model_manager.client.search_model_versions(f"name='{model_name}'")
                except Exception as e:
                    # Connection error - log and re-raise (never switch hostnames)
                    error_str = str(e)
                    logger.error(f"Failed to get model versions for {model_name}: {error_str}")
                    logger.warning("Not switching hostnames - using configured MLflow URI. Check MLflow availability.")
                    raise
            
            model_key = get_model_key(model_name, version)
            
            # Get lock for this specific model
            if model_key not in _model_locks:
                _model_locks[model_key] = threading.RLock()
            
            with _model_locks[model_key]:
                try:
                    logger.info(f"Refreshing model: {model_key} using pyfunc (RECOMMENDED)")
                    
                    # Try pyfunc loading first (RECOMMENDED)
                    try:
                        pyfunc_model = model_manager.load_model_pyfunc(model_name, version=version)
                        
                        # Get model info for shapes
                        input_shape = None
                        output_shape = None
                        try:
                            model_uri = f"models:/{model_name}/{version}"
                            model_info = mlflow.models.get_model_info(model_uri)
                            if hasattr(model_info, 'signature') and model_info.signature:
                                if model_info.signature.inputs:
                                    input_shape = [None]
                                    if len(model_info.signature.inputs) > 0:
                                        first_input = model_info.signature.inputs[0]
                                        if hasattr(first_input, 'shape'):
                                            input_shape = list(first_input.shape)
                        except Exception:
                            pass
                        
                        _model_cache[model_key] = {
                            'model': pyfunc_model,
                            'model_type': 'pyfunc',
                            'model_name': model_name,
                            'version': version,
                            'input_shape': input_shape,
                            'output_shape': output_shape,
                            'loaded_at': time.time()
                        }
                        
                        logger.info(f"Successfully refreshed {model_key} using pyfunc")
                        
                    except Exception as pyfunc_error:
                        # Fallback to ONNX
                        logger.warning(f"Pyfunc loading failed: {pyfunc_error}. Trying ONNX...")
                        ort_session = model_manager.load_onnx_model(model_name, version)
                        
                        input_shape = None
                        output_shape = None
                        if ort_session.get_inputs():
                            input_shape = list(ort_session.get_inputs()[0].shape)
                        if ort_session.get_outputs():
                            output_shape = list(ort_session.get_outputs()[0].shape)
                        
                        _model_cache[model_key] = {
                            'session': ort_session,
                            'model_type': 'onnx',
                            'model_name': model_name,
                            'version': version,
                            'input_shape': input_shape,
                            'output_shape': output_shape,
                            'loaded_at': time.time()
                        }
                        
                        logger.info(f"Successfully refreshed {model_key} using ONNX (fallback)")
                    
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
    logger.info(f"MLflow Tracking URI: {mlflow_tracking_uri}")
    
    try:
        refresh_models()  # Load all production models
        logger.info(f"Loaded {len(_model_cache)} production models on startup")
    except Exception as e:
        logger.error(f"Failed to load models on startup: {e}")

    # Start background tasks for Data API
    # task = asyncio.create_task(start_background_tasks())
    
    yield
    
    # Shutdown: Cleanup
    logger.info("Shutting down FastAPI ML Inference Service")
    _model_cache.clear()
    _model_locks.clear()
    # task.cancel()


# Create FastAPI app
app = FastAPI(
    title="ML Model Inference API",
    description="FastAPI service for ML model predictions using ONNX models from MLflow",
    version="1.0.0",
    lifespan=lifespan
)

# Include Data API Router
# Include Data API Router
print(f"DEBUG: Including Data API Router. ID: {id(data_api_router)}")
print(f"DEBUG: Router routes count: {len(data_api_router.routes)}")
for r in data_api_router.routes:
    print(f"DEBUG: Router route: {r.path}")

app.include_router(data_api_router)

@app.middleware("http")
async def log_requests(request: Request, call_next):
    print(f"DEBUG: Request: {request.method} {request.url}", flush=True)
    try:
        response = await call_next(request)
        print(f"DEBUG: Response status: {response.status_code}", flush=True)
        return response
    except Exception as e:
        print(f"DEBUG: Request failed: {e}", flush=True)
        raise

# Log registered routes
print("DEBUG: All registered routes in app:")
for route in app.routes:
    if hasattr(route, "path"):
        print(f"DEBUG: App Route: {route.path}")

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
    Reload production models from MLflow.
    
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
    # Convert 0-indexed version to MLflow version if needed
    if isinstance(request.version, int):
        mlflow_version = str(request.version + 1)  # 0 -> v1, 1 -> v2, etc.
    else:
        mlflow_version = str(request.version)
    
    model_key = get_model_key(request.model_name, mlflow_version)
    
    with _cache_lock:
        if model_key in _model_cache:
            return {
                "available": True
            }
        else:
            # Check if model exists in MLflow
            try:
                version_obj = model_manager.client.get_model_version(
                    request.model_name,
                    mlflow_version
                )
                return {
                    "available": True
                }
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
    
    # Convert 0-indexed version to MLflow version if needed
    if isinstance(version, int):
        mlflow_version = str(version + 1)  # 0 -> v1, 1 -> v2, etc.
    else:
        mlflow_version = str(version)
    
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
    """Internal function to make predictions - supports both pyfunc and ONNX models"""
    start_time = time.time()
    
    try:
        model_type = model_info.get('model_type', 'onnx')  # Default to onnx for backward compat
        
        if model_type == 'pyfunc':
            # Use pyfunc model (RECOMMENDED)
            import pandas as pd
            model = model_info['model']
            
            # Convert features to DataFrame (pyfunc expects DataFrame)
            # If we don't know feature names, use generic column names
            num_features = len(features[0]) if features else 0
            feature_names = [f'feature_{i}' for i in range(num_features)]
            df = pd.DataFrame(features, columns=feature_names)
            
            # Make predictions using pyfunc
            predictions = model.predict(df)
            
            # Convert to list format
            if hasattr(predictions, 'tolist'):
                predictions = predictions.tolist()
            elif isinstance(predictions, np.ndarray):
                predictions = predictions.tolist()
            elif isinstance(predictions, (list, tuple)):
                predictions = list(predictions)
            else:
                # Single prediction
                predictions = [predictions]
            
        else:
            # Use ONNX model (fallback)
            session = model_info['session']
            
            # Convert features to numpy array
            features_array = np.array(features, dtype=np.float32)
            
            # Get input name from model
            input_name = session.get_inputs()[0].name
            
            # Run inference
            outputs = session.run(None, {input_name: features_array})
            
            # Get predictions (first output)
            predictions = outputs[0].tolist()
        
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
            f"(type: {model_type}, latency: {latency:.3f}s)"
        )
        
        # Return in documented format
        return {
            "predictions": predictions
        }
        
    except Exception as e:
        logger.error(f"Prediction error for {model_name} v{version}: {e}", exc_info=True)
        
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


@app.get("/debug/mlflow")
async def debug_mlflow():
    """
    Debug endpoint to check MLflow connection and available models.
    Helps diagnose why no models are loaded.
    
    Shows ALL registered models and their stages, not just Production ones.
    
    ⚠️ NON-BLOCKING: Uses timeouts to prevent hanging on file-based MLflow backends.
    """
    # Check and fix URI immediately if needed (before initializing debug_info)
    global mlflow_tracking_uri, model_manager
    
    # ALWAYS check the current state and fix if needed (works even with old cached code)
    # Check both the module variable AND the environment variable
    current_env_uri = os.getenv("MLFLOW_TRACKING_URI", mlflow_tracking_uri)
    current_module_uri = mlflow_tracking_uri
    
    # AGGRESSIVELY fix URI if it's still mlflow:5000 when running locally
    # This fix happens on EVERY request to ensure it's applied
    if not is_running_in_docker():
        needs_fix = False
        if "mlflow:5000" in str(current_module_uri) or ("mlflow" in str(current_module_uri) and "localhost" not in str(current_module_uri) and "127.0.0.1" not in str(current_module_uri)):
            needs_fix = True
        elif "mlflow:5000" in str(current_env_uri) or ("mlflow" in str(current_env_uri) and "localhost" not in str(current_env_uri) and "127.0.0.1" not in str(current_env_uri)):
            needs_fix = True
        
        if needs_fix:
            logger.warning(f"Debug endpoint: Detected mlflow:5000 while running locally - fixing immediately")
            mlflow_tracking_uri = "http://localhost:5000"
            os.environ["MLFLOW_TRACKING_URI"] = mlflow_tracking_uri
            model_manager = ModelManager(tracking_uri=mlflow_tracking_uri)
            logger.info(f"Debug endpoint: Fixed URI to {mlflow_tracking_uri}")
    
    # Use the (potentially fixed) URI for the response
    current_uri = mlflow_tracking_uri
    
    debug_info = {
        "mlflow_tracking_uri": current_uri,
        "mlflow_available": MLFLOW_AVAILABLE,
        "connection_status": "unknown",
        "registered_models": [],
        "all_model_versions": [],
        "production_models": [],
        "loaded_models_count": len(_model_cache),
        "errors": [],
        "registry_timeout": False
    }
    
    if not MLFLOW_AVAILABLE:
        debug_info["errors"].append("MLflow is not available. Install with: pip install mlflow")
        return debug_info
    
    try:
        # ✅ Fast ping test (never blocks) - use search_experiments with max_results=1
        try:
            # Quick connection test - this is fast and non-blocking
            model_manager.client.search_experiments(max_results=1)
            debug_info["mlflow_available"] = True
            debug_info["connection_status"] = "ok"
        except Exception as e:
            # Connection error - log but don't switch hostnames
            error_str = str(e)
            logger.warning(f"MLflow connection test failed: {error_str}")
            debug_info["connection_status"] = "failed"
            debug_info["errors"].append(f"Connection failed: {error_str}")
            debug_info["note"] = "Not switching hostnames - using configured MLflow URI"
        
        # ⚠️ Registry calls are SLOW with file-based backend - make them non-blocking
        registered_models = []
        registry_error = None
        
        def load_registry():
            """Load registered models in a separate thread with timeout protection"""
            nonlocal registered_models, registry_error
            try:
                registered_models = model_manager.client.search_registered_models(max_results=100)
            except Exception as e:
                registry_error = str(e)
        
        # Run registry call in thread with timeout
        registry_thread = threading.Thread(target=load_registry)
        registry_thread.daemon = True
        registry_thread.start()
        registry_thread.join(timeout=3)  # ⏱️ HARD STOP after 3 seconds
        
        if registry_thread.is_alive():
            debug_info["registry_timeout"] = True
            debug_info["errors"].append("Registry call timed out (file-based backend may be slow)")
            # Return early with basic info - don't wait for registry
            return debug_info
        
        if registry_error:
            debug_info["errors"].append(f"Registry error: {registry_error}")
            return debug_info
        
        # Successfully got registered models
        debug_info["registered_models"] = [{"name": m.name, "latest_versions": len(m.latest_versions)} for m in registered_models]
        
        # Get model versions (also with timeout protection)
        def load_model_versions():
            """Load model versions in a separate thread"""
            nonlocal debug_info
            for model in registered_models:
                model_name = model.name
                try:
                    # Get all versions with timeout protection
                    all_versions = model_manager.client.search_model_versions(f"name='{model_name}'", max_results=50)
                    
                    for v in all_versions:
                        version_info = {
                            "name": model_name,
                            "version": v.version,
                            "stage": v.current_stage or "None",
                            "source": v.source,
                            "onnx_available": None,
                            "onnx_error": None
                        }
                        
                        # Check ONNX availability (skip if registry already timed out)
                        try:
                            model_manager.load_onnx_model(model_name, v.version)
                            version_info["onnx_available"] = True
                        except Exception as e:
                            version_info["onnx_available"] = False
                            version_info["onnx_error"] = str(e)
                        
                        debug_info["all_model_versions"].append(version_info)
                        
                        # Track production models separately
                        if v.current_stage == "Production":
                            debug_info["production_models"].append(version_info)
                            
                except Exception as e:
                    debug_info["errors"].append(f"Error checking {model_name}: {str(e)}")
        
        # Load versions in thread with timeout
        versions_thread = threading.Thread(target=load_model_versions)
        versions_thread.daemon = True
        versions_thread.start()
        versions_thread.join(timeout=5)  # ⏱️ HARD STOP after 5 seconds
        
        if versions_thread.is_alive():
            debug_info["errors"].append("Model versions loading timed out (partial data returned)")
        
    except Exception as e:
        debug_info["connection_status"] = "failed"
        debug_info["errors"].append(f"Unexpected error: {str(e)}")
    
    return debug_info


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)

