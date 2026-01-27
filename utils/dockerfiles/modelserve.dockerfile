# Dockerfile for FastAPI ML Model Inference Service
# This container serves ML models for predictions using ONNX models from MLflow

FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY utils/dockerfiles/fastapi_requirements.txt requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r fastapi_requirements.txt && \
    pip install --no-cache-dir prometheus-fastapi-instrumentator>=6.1.0

# Copy project files
COPY . .

# Set Python path
ENV PYTHONPATH=/app

# Expose FastAPI port
EXPOSE 8000

# Set default MLflow tracking URI (can be overridden via env var)
ENV MLFLOW_TRACKING_URI=http://mlflow:5000

# Run FastAPI app
CMD ["python", "-m", "uvicorn", "utils.serve.fastapi_app:app", "--host", "0.0.0.0", "--port", "8000"]



