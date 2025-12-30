# Vast AI Docker Image Fix

## Problem
The Docker image `dhayanandss/mlops:latest` doesn't exist on Docker Hub, causing:
```
Error: pull access denied for dhayanandss/mlops, repository does not exist
```

## Solution ✅

I've updated the code to use a **public base image** instead. The startup command already:
1. Clones your repository from GitHub
2. Installs all dependencies from `requirements.txt`
3. Runs the training

So we don't need a pre-built custom image - a base Python image is sufficient.

## Changes Made

### Updated `utils/utils/vast_ai_train.py`:

1. **Made Docker image configurable:**
   ```python
   DOCKER_IMAGE = os.getenv(
       "VASTAI_DOCKER_IMAGE",
       "python:3.10-slim"  # Public Python image
   )
   ```

2. **Updated startup command** to install requirements:
   ```bash
   pip install --upgrade pip
   pip install -r requirements.txt
   pip install wandb
   ```

## Options

### Option 1: Use Default (Recommended)
The code now defaults to `python:3.10-slim` which is a public image. This should work immediately.

### Option 2: Use Your Own Image
If you want to build and push your own image:

1. **Build the image:**
   ```bash
   docker build -t dhayanandss/mlops:latest -f Dockerfile .
   ```

2. **Push to Docker Hub:**
   ```bash
   docker login
   docker push dhayanandss/mlops:latest
   ```

3. **Or set custom image via environment variable:**
   ```powershell
   # In .env file or docker-compose.airflow.yml
   VASTAI_DOCKER_IMAGE=your-username/mlops:latest
   ```

### Option 3: Use CUDA Base Image
If you need CUDA libraries in the base image, you can set:
```powershell
VASTAI_DOCKER_IMAGE=nvidia/cuda:11.8.0-cudnn8-runtime-ubuntu22.04
```

**Note:** Vast AI instances typically have CUDA drivers pre-installed, so a Python image is usually sufficient.

## Verification

After the fix, when you run the `vast_ai_train` task, it should:
1. ✅ Successfully pull the `python:3.10-slim` image (public, no auth needed)
2. ✅ Create the Vast AI instance
3. ✅ Clone your repository
4. ✅ Install dependencies
5. ✅ Start training

## Summary

- ✅ **Fixed:** Changed from private image to public `python:3.10-slim`
- ✅ **Configurable:** Can override via `VASTAI_DOCKER_IMAGE` environment variable
- ✅ **No action needed:** The fix is automatic - just run the DAG again

The error should be resolved on the next DAG run!






