# Vast AI Docker Image Setup Guide

This guide explains how to use a pre-built Docker image for Vast AI training (Option 3).

## Overview

Instead of cloning code from GitHub or uploading manually, you can build a Docker image with all your code pre-packaged. This is the most reliable and fastest option.

## Quick Start

### 1. Build and Push Your Docker Image

Run the build script:

```powershell
.\build_and_push_vastai_image.ps1
```

The script will:
- Check Docker is running
- Build a Docker image with all your code
- Optionally push it to Docker Hub
- Update your `.env` file automatically

**Note:** You'll need a Docker Hub account. If you don't have one:
1. Sign up at https://hub.docker.com
2. Login: `docker login`
3. Update the image name in the script if needed (default: `dhayanandss/mlops`)

### 2. Restart Airflow

After building the image, restart Airflow to pick up the new configuration:

```powershell
docker-compose -f docker-compose.airflow.yml restart
```

### 3. Run Your DAG

The `vast_ai_train` task will now automatically use your custom Docker image!

## How It Works

1. **Docker Image**: Contains all your code, dependencies, and configuration
2. **Vast AI Instance**: Pulls your image and runs training directly
3. **No GitHub Required**: Code is already in the image
4. **Faster Startup**: No need to clone repos or install dependencies

## Configuration

The image name is stored in `.env`:

```env
VASTAI_DOCKER_IMAGE=dhayanandss/mlops:latest
```

You can manually edit this if needed.

## Updating the Image

When you make code changes:

1. Rebuild the image:
   ```powershell
   .\build_and_push_vastai_image.ps1
   ```

2. Restart Airflow:
   ```powershell
   docker-compose -f docker-compose.airflow.yml restart
   ```

## Troubleshooting

### "Image not found" error
- Make sure you pushed the image to Docker Hub
- Check the image name in `.env` matches what you pushed
- Verify you're logged in: `docker login`

### "Permission denied" when pushing
- Make sure you're logged into Docker Hub: `docker login`
- Verify you have push permissions for the repository

### Build fails
- Check Docker is running: `docker ps`
- Ensure you have enough disk space
- Check network connection (needs to download base images)

## What's in the Image?

The Dockerfile includes:
- Python 3.10
- All dependencies from `requirements.txt`
- Your entire project code
- Proper Python path configuration

## Alternative: Use Existing Image

If you already have a Docker image, just set it in `.env`:

```env
VASTAI_DOCKER_IMAGE=your-username/your-image:tag
```

No need to run the build script!

