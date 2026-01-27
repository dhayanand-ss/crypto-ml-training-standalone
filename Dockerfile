# Dockerfile for Training Jobs
# This container runs the crypto ML training pipeline

FROM pytorch/pytorch:2.1.0-cuda12.1-cudnn8-runtime

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONPATH="/workspace/crypto-ml-training-standalone"

# Set working directory
WORKDIR /workspace/crypto-ml-training-standalone
RUN mkdir -p /workspace/crypto-ml-training-standalone && chmod -R 777 /workspace

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    git \
    libnss3 \
    libnspr4 \
    libdbus-glib-1-2 \
    libgtk-3-0 \
    libxss1 \
    libxkbcommon-x11-0 \
    libwayland-cursor0 \
    libwayland-egl1 \
    libfontconfig1 \
    libglib2.0-0 \
    libasound2 \
    openssh-client \
    openssh-server \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright browsers (as it's in requirements.txt)
RUN playwright install --with-deps chromium

# Copy the rest of the application
COPY . .

# Note: This can be overridden by Vast AI startup command
CMD ["python", "-m", "utils.trainer.trl_train"]
