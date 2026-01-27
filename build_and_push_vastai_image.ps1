# Script to build and push Docker image for Vast AI training
# This creates a Docker image with all your code pre-packaged

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "Building and Pushing Docker Image for Vast AI" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

# Configuration
$IMAGE_NAME = "dhayanandss/mlops"
$IMAGE_TAG = "latest"
$FULL_IMAGE_NAME = "${IMAGE_NAME}:${IMAGE_TAG}"

# Check if Docker is running
Write-Host "1. Checking Docker..." -ForegroundColor Yellow
try {
    docker ps | Out-Null
    Write-Host "   [OK] Docker is running" -ForegroundColor Green
} catch {
    Write-Host "   [ERROR] Docker is not running!" -ForegroundColor Red
    Write-Host "   Please start Docker Desktop and try again." -ForegroundColor Yellow
    exit 1
}

# Check if user is logged into Docker Hub
Write-Host "`n2. Checking Docker Hub login..." -ForegroundColor Yellow
$dockerUser = docker info 2>&1 | Select-String -Pattern "Username"
if (-not $dockerUser) {
    Write-Host "   [INFO] Not logged into Docker Hub" -ForegroundColor Yellow
    Write-Host "   Please login to Docker Hub:" -ForegroundColor White
    Write-Host "   docker login" -ForegroundColor Cyan
    $response = Read-Host "   Do you want to login now? (y/n)"
    if ($response -eq 'y') {
        docker login
        if ($LASTEXITCODE -ne 0) {
            Write-Host "   [ERROR] Docker login failed!" -ForegroundColor Red
            exit 1
        }
    } else {
        Write-Host "   [WARNING] You'll need to login before pushing the image" -ForegroundColor Yellow
    }
} else {
    Write-Host "   [OK] Logged into Docker Hub" -ForegroundColor Green
}

# Get image name from user (optional)
Write-Host "`n3. Docker Image Configuration" -ForegroundColor Yellow
Write-Host "   Default image name: $FULL_IMAGE_NAME" -ForegroundColor White
$customName = Read-Host "   Enter custom image name (or press Enter to use default)"
if ($customName) {
    $FULL_IMAGE_NAME = $customName
    $IMAGE_NAME = $customName.Split(':')[0]
    $IMAGE_TAG = if ($customName.Contains(':')) { $customName.Split(':')[1] } else { "latest" }
}

Write-Host "   Using image: $FULL_IMAGE_NAME" -ForegroundColor Cyan

# Check if Dockerfile exists
Write-Host "`n4. Checking Dockerfile..." -ForegroundColor Yellow
if (-not (Test-Path "Dockerfile")) {
    Write-Host "   [ERROR] Dockerfile not found!" -ForegroundColor Red
    Write-Host "   Creating a basic Dockerfile..." -ForegroundColor Yellow
    
    # Create a basic Dockerfile for training
    $dockerfileContent = @"
# Dockerfile for Crypto ML Training on Vast AI
FROM pytorch/pytorch:2.1.0-cuda12.1-cudnn8-runtime

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1
ENV PYTHONPATH="/workspace/crypto-ml-training-standalone"

# Set working directory
WORKDIR /workspace/crypto-ml-training-standalone

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
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright browsers
RUN playwright install --with-deps chromium

# Copy project files
COPY . .

# Default command
CMD ["python", "-m", "utils.trainer.trl_train"]
"@
    
    Set-Content -Path "Dockerfile" -Value $dockerfileContent
    Write-Host "   [OK] Created Dockerfile" -ForegroundColor Green
} else {
    Write-Host "   [OK] Dockerfile found" -ForegroundColor Green
}

# Build the image
Write-Host "`n5. Building Docker image..." -ForegroundColor Yellow
Write-Host "   This may take 10-30 minutes depending on your system and network..." -ForegroundColor Gray
Write-Host ""

$buildStartTime = Get-Date
docker build -t $FULL_IMAGE_NAME -f Dockerfile .

if ($LASTEXITCODE -ne 0) {
    Write-Host "   [ERROR] Docker build failed!" -ForegroundColor Red
    exit 1
}

$buildDuration = (Get-Date) - $buildStartTime
$minutes = [math]::Round($buildDuration.TotalMinutes, 1)
Write-Host "   [OK] Image built successfully in ${minutes} minutes" -ForegroundColor Green

# Ask if user wants to push
Write-Host "`n6. Push to Docker Hub?" -ForegroundColor Yellow
$pushResponse = Read-Host "   Push image to Docker Hub? (y/n)"
if ($pushResponse -eq 'y') {
    Write-Host "   Pushing image to Docker Hub..." -ForegroundColor Yellow
    Write-Host "   This may take a few minutes depending on image size and network speed..." -ForegroundColor Gray
    
    docker push $FULL_IMAGE_NAME
    
    if ($LASTEXITCODE -eq 0) {
        Write-Host "   [OK] Image pushed successfully!" -ForegroundColor Green
    } else {
        Write-Host "   [ERROR] Failed to push image!" -ForegroundColor Red
        Write-Host "   Make sure you're logged in: docker login" -ForegroundColor Yellow
        exit 1
    }
} else {
    Write-Host "   [INFO] Skipping push. You can push later with:" -ForegroundColor Yellow
    Write-Host "   docker push $FULL_IMAGE_NAME" -ForegroundColor Cyan
}

# Update .env file
Write-Host "`n7. Updating configuration..." -ForegroundColor Yellow
$envFile = ".env"
if (Test-Path $envFile) {
    $envContent = Get-Content $envFile
    $hasVastaiImage = $envContent | Select-String -Pattern "^VASTAI_DOCKER_IMAGE="
    
    if ($hasVastaiImage) {
        # Update existing entry
        $newContent = $envContent | ForEach-Object {
            if ($_ -match "^VASTAI_DOCKER_IMAGE=") {
                "VASTAI_DOCKER_IMAGE=$FULL_IMAGE_NAME"
            } else {
                $_
            }
        }
        Set-Content -Path $envFile -Value $newContent
    } else {
        # Add new entry
        Add-Content -Path $envFile -Value "VASTAI_DOCKER_IMAGE=$FULL_IMAGE_NAME"
    }
    Write-Host "   [OK] Updated .env file" -ForegroundColor Green
} else {
    # Create .env file
    Set-Content -Path $envFile -Value "VASTAI_DOCKER_IMAGE=$FULL_IMAGE_NAME"
    Write-Host "   [OK] Created .env file" -ForegroundColor Green
}

Write-Host ""
Write-Host "============================================================" -ForegroundColor Green
Write-Host "Docker Image Setup Complete!" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Green
Write-Host ""
Write-Host "Image: $FULL_IMAGE_NAME" -ForegroundColor Cyan
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Yellow
Write-Host "1. Restart Airflow containers to pick up the new image:" -ForegroundColor White
Write-Host "   docker-compose -f docker-compose.airflow.yml restart" -ForegroundColor Cyan
Write-Host ""
Write-Host "2. The vast_ai_train task will now use your custom image" -ForegroundColor White
Write-Host ""
Write-Host "3. To update the image after code changes:" -ForegroundColor White
Write-Host "   .\build_and_push_vastai_image.ps1" -ForegroundColor Cyan
Write-Host ""

