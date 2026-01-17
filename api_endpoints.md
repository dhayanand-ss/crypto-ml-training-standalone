# API Endpoints Documentation

This document lists all API endpoints available in the FastAPI ML Inference Service (`utils/serve/fastapi_app.py`).

## Base URL
The service typically runs on port 8000 (e.g., `http://localhost:8000`).

## Endpoints

### 1. Root
- **Method:** `GET`
- **Path:** `/`
- **Description:** Redirects to the automatic API documentation (`/docs`).

### 2. Health Check
- **Method:** `GET`
- **Path:** `/health`
- **Description:** Checks the health status of the service and reports loaded models.
- **Response:**
  ```json
  {
    "status": "healthy",
    "models_loaded": 0,
    "onnxruntime_available": true,
    "prometheus_available": true
  }
  ```

### 3. Metrics
- **Method:** `GET`
- **Path:** `/metrics`
- **Description:** Exposes Prometheus metrics.
- **Note:** This endpoint is automatically provided by `prometheus-fastapi-instrumentator`. If instrumentator is unavailable, a fallback implementation is used.

### 4. Refresh Models
- **Method:** `POST`
- **Path:** `/refresh`
- **Description:** Reloads production models from MLflow.
- **Request Body:**
  ```json
  {
    "model_name": "string (optional)",
    "version": "string or int (optional)"
  }
  ```
  - If `model_name` is omitted, all production models are refreshed.
  - If `version` is omitted, the latest production version is loaded.
- **Response:**
  ```json
  {
    "status": "models loaded",
    "models": {
      "model_name": [[version, version], ...]
    }
  }
  ```

### 5. Check Model Availability
- **Method:** `POST`
- **Path:** `/is_model_available`
- **Description:** Checks if a specific model version is available.
- **Request Body:**
  ```json
  {
    "model_name": "string",
    "version": "string or int"
  }
  ```
- **Response:**
  ```json
  {
    "available": true
  }
  ```

### 6. Predict
- **Method:** `POST`
- **Path:** `/predict`
- **Description:** Makes batch predictions using the specified model.
- **Query Parameters:**
  - `model_name`: Name of the model.
  - `version`: Model version (0-indexed integer or string).
- **Request Body:**
  - A list of feature vectors (List of Lists of floats).
  - Example: `[[0.1, 0.2], [0.3, 0.4]]`
  - **Constraints:**
    - Maximum 5000 samples per request.
    - All feature vectors must have the same length.
- **Response:**
  ```json
  {
    "predictions": [0.5, 0.6, ...]
  }
  ```

### 7. List Models
- **Method:** `GET`
- **Path:** `/models`
- **Description:** Lists all currently loaded models.
- **Response:**
  ```json
  [
    {
      "model_name": "string",
      "version": "string",
      "loaded": true,
      "input_shape": [null, 10],
      "output_shape": [null, 1]
    }
  ]
  ```

### 8. Debug MLflow
- **Method:** `GET`
- **Path:** `/debug/mlflow`
- **Description:** Debug endpoint to check MLflow connection and available models.
- **Response:** JSON object containing MLflow connection status, registered models, and any errors.
