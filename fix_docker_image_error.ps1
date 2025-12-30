# Fix Docker Image Pull Error
# This script configures the system to use GitHub repository with default Python image

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "Fixing Docker Image Pull Error" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

$GITHUB_USERNAME = "dhayanand-ss"
$REPO_NAME = "crypto-ml-training-standalone"
$REPO_URL = "https://github.com/$GITHUB_USERNAME/$REPO_NAME.git"

Write-Host "Configuration:" -ForegroundColor Yellow
Write-Host "  GitHub Repository: $REPO_URL" -ForegroundColor White
Write-Host "  Docker Image: python:3.10-slim (public, no auth needed)" -ForegroundColor White
Write-Host ""

# Check if .env file exists
$envFile = ".env"
$envContent = @()

if (Test-Path $envFile) {
    Write-Host "Found existing .env file" -ForegroundColor Yellow
    $envContent = Get-Content $envFile
} else {
    Write-Host "Creating new .env file" -ForegroundColor Green
}

# Process .env file
$newContent = @()
$hasVastaiRepo = $false
$hasVastaiImage = $false

foreach ($line in $envContent) {
    if ($line -match "^VASTAI_GITHUB_REPO=") {
        $newContent += "VASTAI_GITHUB_REPO=$REPO_URL"
        $hasVastaiRepo = $true
        Write-Host "  [UPDATE] VASTAI_GITHUB_REPO" -ForegroundColor Cyan
    }
    elseif ($line -match "^VASTAI_DOCKER_IMAGE=") {
        # Remove or comment out the custom Docker image setting
        # This will make it default to python:3.10-slim
        $newContent += "# VASTAI_DOCKER_IMAGE=dhayanandss/mlops:latest  # Commented out - using default python:3.10-slim"
        $hasVastaiImage = $true
        Write-Host "  [REMOVE] VASTAI_DOCKER_IMAGE (will use default python:3.10-slim)" -ForegroundColor Cyan
    }
    elseif ($line -match "^#.*VASTAI_DOCKER_IMAGE=") {
        # Already commented, keep it
        $newContent += $line
    }
    else {
        $newContent += $line
    }
}

# Add GitHub repo if it doesn't exist
if (-not $hasVastaiRepo) {
    $newContent += ""
    $newContent += "# Vast AI GitHub Repository"
    $newContent += "VASTAI_GITHUB_REPO=$REPO_URL"
    Write-Host "  [ADD] VASTAI_GITHUB_REPO" -ForegroundColor Green
}

# Add comment about Docker image if it wasn't there
if (-not $hasVastaiImage) {
    $newContent += ""
    $newContent += "# Vast AI Docker Image (using default python:3.10-slim)"
    $newContent += "# VASTAI_DOCKER_IMAGE=python:3.10-slim  # Default, no need to set"
    Write-Host "  [INFO] Docker image will use default (python:3.10-slim)" -ForegroundColor Gray
}

# Write updated .env file
Set-Content -Path $envFile -Value $newContent

Write-Host ""
Write-Host "============================================================" -ForegroundColor Green
Write-Host "Configuration Updated!" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Green
Write-Host ""
Write-Host "Changes made:" -ForegroundColor Yellow
Write-Host "  ✓ Set VASTAI_GITHUB_REPO=$REPO_URL" -ForegroundColor Green
Write-Host "  ✓ Removed custom Docker image (will use python:3.10-slim)" -ForegroundColor Green
Write-Host ""
Write-Host "How it works:" -ForegroundColor Yellow
Write-Host "  1. Vast AI will pull the public 'python:3.10-slim' image (no auth needed)" -ForegroundColor White
Write-Host "  2. The startup script will clone your code from GitHub" -ForegroundColor White
Write-Host "  3. Dependencies will be installed from requirements.txt" -ForegroundColor White
Write-Host "  4. Training will run automatically" -ForegroundColor White
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Yellow
Write-Host "1. Restart Airflow containers to apply changes:" -ForegroundColor White
Write-Host "   docker-compose -f docker-compose.airflow.yml restart" -ForegroundColor Cyan
Write-Host ""
Write-Host "2. The Docker pull error should be fixed!" -ForegroundColor Green
Write-Host ""





