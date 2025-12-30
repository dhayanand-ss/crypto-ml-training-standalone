#!/usr/bin/env python3
"""
Start FastAPI ML Model Inference Server

This script starts the FastAPI server for serving ML models.
Set MLFLOW_TRACKING_URI environment variable to configure MLflow connection.
"""

import os
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).resolve().parent
sys.path.insert(0, str(project_root))

# Set default MLflow URI if not set (use localhost for local development)
if "MLFLOW_TRACKING_URI" not in os.environ:
    os.environ["MLFLOW_TRACKING_URI"] = "http://localhost:5000"

# Import and run the FastAPI app
from utils.serve.fastapi_app import app
import uvicorn

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    host = os.getenv("HOST", "127.0.0.1")
    
    print("=" * 60)
    print("Starting FastAPI ML Model Inference Server")
    print("=" * 60)
    print(f"Host: {host}")
    print(f"Port: {port}")
    print(f"MLflow Tracking URI: {os.environ.get('MLFLOW_TRACKING_URI', 'http://localhost:5000')}")
    print("=" * 60)
    print()
    print("API Documentation: http://{}:{}/docs".format(host, port))
    print("Health Check: http://{}:{}/health".format(host, port))
    print("Models Endpoint: http://{}:{}/models".format(host, port))
    print()
    print("Press Ctrl+C to stop the server")
    print("=" * 60)
    print()
    
    uvicorn.run(app, host=host, port=port)
