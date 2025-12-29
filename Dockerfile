# Dockerfile for Training Jobs
# This container runs the crypto ML training pipeline

# Use Python 3.10 with CUDA support for GPU training
FROM python:3.10-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy project files
COPY . .

# Set Python path
ENV PYTHONPATH=/app

# Default command for training
# Note: This can be overridden by Vast AI startup command
CMD ["python", "-m", "utils.trainer.train_paralelly"]
