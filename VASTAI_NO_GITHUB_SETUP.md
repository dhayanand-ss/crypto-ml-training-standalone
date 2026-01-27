# Vast AI Setup Without GitHub Repository

## Problem
The Vast AI training setup tries to clone code from GitHub, but you don't have a GitHub repository.

## Solution Options

### Option 1: Create a GitHub Repository (Recommended) 🚀

This is the easiest way to deploy code to Vast AI instances:

1. **Create a new repository on GitHub:**
   - Go to https://github.com/new
   - Name it: `crypto-mlops` (or any name you prefer)
   - Make it **private** or **public** (your choice)

2. **Push your code to GitHub:**
   ```powershell
   # Initialize git (if not already done)
   git init
   git add .
   git commit -m "Initial commit"
   
   # Add your GitHub repository as remote
   git remote add origin https://github.com/YOUR_USERNAME/crypto-mlops.git
   git branch -M main
   git push -u origin main
   ```

3. **Set the repository URL in environment:**
   ```powershell
   # Add to .env file
   VASTAI_GITHUB_REPO=https://github.com/YOUR_USERNAME/crypto-mlops.git
   ```

4. **Or set in docker-compose.airflow.yml:**
   ```yaml
   environment:
     VASTAI_GITHUB_REPO: ${VASTAI_GITHUB_REPO}
   ```

### Option 2: Manual Code Upload via SSH 📤

If you don't want to use GitHub, you can upload code manually:

1. **Vast AI will create instances with SSH access**
2. **After instance is created, SSH into it:**
   ```bash
   vastai ssh <instance_id>
   ```

3. **Upload your code:**
   ```bash
   # From your local machine, use SCP or rsync
   scp -r /path/to/your/code/* root@<instance_ip>:/workspace/crypto-ml-training/
   ```

4. **Or use Vast AI's file upload feature** (if available in their web interface)

### Option 3: Use S3/GCS for Code Distribution ☁️

Upload your code to S3/GCS and download it on the instance:

1. **Upload code to S3:**
   ```powershell
   # Create a zip of your code
   Compress-Archive -Path . -DestinationPath code.zip
   
   # Upload to S3 (using AWS CLI or boto3)
   aws s3 cp code.zip s3://your-bucket/code.zip
   ```

2. **Update startup command to download from S3:**
   The startup command can be modified to download from S3 instead of GitHub.

### Option 4: Build and Push Docker Image 🐳

Build a Docker image with your code pre-packaged:

1. **Build the image:**
   ```powershell
   docker build -t your-username/crypto-mlops:latest -f Dockerfile .
   ```

2. **Push to Docker Hub:**
   ```powershell
   docker login
   docker push your-username/crypto-mlops:latest
   ```

3. **Set the image in environment:**
   ```powershell
   VASTAI_DOCKER_IMAGE=your-username/crypto-mlops:latest
   ```

4. **Update startup command** to not clone (code is already in image)

## Current Configuration

The code has been updated to:
- ✅ Make GitHub clone **optional** (only if `VASTAI_GITHUB_REPO` is set)
- ✅ Create a workspace directory if no repo is configured
- ✅ Provide helpful warnings if code needs to be uploaded manually

## Recommended Approach

**I recommend Option 1 (GitHub)** because:
- ✅ Automatic code deployment
- ✅ Version control
- ✅ Easy updates
- ✅ No manual uploads needed
- ✅ Works seamlessly with the current setup

## Quick Setup for GitHub

If you want to use GitHub, here's the quickest path:

```powershell
# 1. Create .env file entry (or add to existing .env)
Add-Content -Path .env -Value "VASTAI_GITHUB_REPO=https://github.com/YOUR_USERNAME/crypto-mlops.git"

# 2. Initialize and push to GitHub (one-time setup)
git init
git add .
git commit -m "Initial commit"
git remote add origin https://github.com/YOUR_USERNAME/crypto-mlops.git
git push -u origin main
```

Then restart your Airflow containers to pick up the new environment variable.

## Summary

- ✅ **Code updated** to make GitHub optional
- ✅ **Multiple options** available for code deployment
- ✅ **GitHub is recommended** but not required
- ✅ **Manual upload via SSH** is always an option

Choose the option that works best for your setup!

