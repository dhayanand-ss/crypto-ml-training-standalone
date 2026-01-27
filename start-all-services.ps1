# PowerShell script to start all services simultaneously
# This script starts: FastAPI, MLflow, Prometheus, and Grafana
#
# Build Times:
#   First run: 5-10 minutes (downloads PyTorch ~2GB and all dependencies)
#   Subsequent runs: ~10-15 seconds (images cached, no build needed)

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "Starting All Services (FastAPI + MLflow + Prometheus + Grafana)" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

# Check if Docker is running and accessible
Write-Host "1. Checking Docker..." -ForegroundColor Yellow
$dockerCheck = docker ps 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "   [ERROR] Docker is not accessible!" -ForegroundColor Red
    Write-Host "   Error details: $dockerCheck" -ForegroundColor Red
    Write-Host ""
    Write-Host "   Troubleshooting steps:" -ForegroundColor Yellow
    Write-Host "   1. Make sure Docker Desktop is running" -ForegroundColor White
    Write-Host "   2. Wait for Docker Desktop to fully initialize (check system tray)" -ForegroundColor White
    Write-Host "   3. Try running: docker ps" -ForegroundColor White
    Write-Host "   4. If using WSL2, ensure Docker Desktop is configured for WSL2 integration" -ForegroundColor White
    Write-Host ""
    exit 1
}

# Verify Docker can pull images (test connectivity)
Write-Host "   Testing Docker connectivity..." -ForegroundColor Yellow
$dockerInfo = docker info 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "   [ERROR] Docker daemon is not responding!" -ForegroundColor Red
    Write-Host "   Please ensure Docker Desktop is fully started." -ForegroundColor Yellow
    exit 1
}
Write-Host "   [OK] Docker is running and accessible" -ForegroundColor Green

# Check if prometheus.yml exists
Write-Host "`n2. Checking Prometheus configuration..." -ForegroundColor Yellow
if (-not (Test-Path "prometheus.yml")) {
    Write-Host "   [WARNING] prometheus.yml not found. Creating default configuration..." -ForegroundColor Yellow
    # The file should have been created, but if not, we'll create it
    @"
global:
  scrape_interval: 15s
  evaluation_interval: 15s

scrape_configs:
  - job_name: 'fastapi-ml'
    static_configs:
      - targets: ['fastapi-ml:8000']
    metrics_path: '/metrics'
    scrape_interval: 15s
"@ | Out-File -FilePath "prometheus.yml" -Encoding utf8
    Write-Host "   [OK] Created prometheus.yml" -ForegroundColor Green
} else {
    Write-Host "   [OK] prometheus.yml found" -ForegroundColor Green
}

# Stop any existing containers
Write-Host "`n3. Stopping existing containers..." -ForegroundColor Yellow
docker-compose -f docker-compose.full.yml down 2>&1 | Out-Null

# Initialize variable
$servicesAlreadyStarted = $false

# Check if images need to be built by attempting to start without build
Write-Host "`n4. Checking if images need to be built..." -ForegroundColor Yellow
$testOutput = docker-compose -f docker-compose.full.yml up -d --no-build 2>&1
$needsBuild = ($LASTEXITCODE -ne 0 -or $testOutput -match "no such image|Cannot find image|requires an image")

if ($needsBuild) {
    # Clean up test attempt
    docker-compose -f docker-compose.full.yml down 2>&1 | Out-Null
    
    Write-Host "   Pre-pulling base images to speed up build..." -ForegroundColor Yellow
    docker pull python:3.10-slim 2>&1 | Out-Null
    
    Write-Host "   Building images (first time)..." -ForegroundColor Yellow
    Write-Host "   Note: Installing PyTorch (~2GB) and dependencies takes 5-10 minutes" -ForegroundColor Gray
    Write-Host "   This is a one-time process. Subsequent builds will be faster." -ForegroundColor Gray
    Write-Host ""
    
    # Enable BuildKit for faster builds if available
    $env:DOCKER_BUILDKIT = "1"
    $env:COMPOSE_DOCKER_CLI_BUILD = "1"
    
    # Build images with progress visible and parallel builds
    # Use --progress=plain to see all output
    $buildStartTime = Get-Date
    docker-compose -f docker-compose.full.yml build --parallel --progress=plain 2>&1 | ForEach-Object {
        $line = $_
        # Highlight important steps
        if ($line -match "Step \d+/\d+") {
            Write-Host $line -ForegroundColor Cyan
        } elseif ($line -match "RUN pip install|Installing|Downloading") {
            Write-Host $line -ForegroundColor Yellow
        } elseif ($line -match "ERROR|FAILED") {
            Write-Host $line -ForegroundColor Red
        } else {
            Write-Host $line -ForegroundColor Gray
        }
    }
    
    if ($LASTEXITCODE -ne 0) {
        Write-Host "   [ERROR] Failed to build images!" -ForegroundColor Red
        exit 1
    }
    
    $buildDuration = (Get-Date) - $buildStartTime
    $minutes = [math]::Round($buildDuration.TotalMinutes, 1)
    Write-Host ""
    Write-Host "   [OK] Images built successfully in ${minutes} minutes" -ForegroundColor Green
} else {
    Write-Host "   [OK] Images already exist, services started" -ForegroundColor Green
    # Services are already started, skip the start step
    $servicesAlreadyStarted = $true
}

# Start all services (if not already started)
if (-not $servicesAlreadyStarted) {
    Write-Host "`n5. Starting all services..." -ForegroundColor Yellow
    $startOutput = docker-compose -f docker-compose.full.yml up -d 2>&1
    $startExitCode = $LASTEXITCODE

    if ($startExitCode -ne 0) {
        Write-Host "   [ERROR] Failed to start services!" -ForegroundColor Red
        Write-Host ""
        Write-Host "   Error output:" -ForegroundColor Yellow
        Write-Host $startOutput -ForegroundColor Red
        Write-Host ""
        Write-Host "   Common issues:" -ForegroundColor Yellow
        Write-Host "   - Docker Desktop not fully started (wait 30 seconds and try again)" -ForegroundColor White
        Write-Host "   - Port conflicts (check if ports 8000, 5000, 9090, 3000 are in use)" -ForegroundColor White
        Write-Host "   - Network issues (check Docker Desktop network settings)" -ForegroundColor White
        Write-Host "   - Insufficient disk space for images" -ForegroundColor White
        Write-Host ""
        Write-Host "   Try manually:" -ForegroundColor Yellow
        Write-Host "   docker-compose -f docker-compose.full.yml up -d" -ForegroundColor White
        exit 1
    }

    Write-Host "   [OK] Services started in background" -ForegroundColor Green
} else {
    Write-Host "`n5. Services already running" -ForegroundColor Green
}

# Wait for services to be ready (adaptive wait, shorter timeout)
Write-Host "`n6. Waiting for services to initialize..." -ForegroundColor Yellow
$maxWait = 30  # Reduced from 60 to 30 seconds
$waitInterval = 3  # Check every 3 seconds (faster checks)
$elapsed = 0
$allReady = $false

while ($elapsed -lt $maxWait -and -not $allReady) {
    Start-Sleep -Seconds $waitInterval
    $elapsed += $waitInterval
    
    # Check if containers are running
    $containers = docker ps --filter "name=fastapi-ml" --filter "name=mlflow" --filter "name=prometheus" --filter "name=grafana" --format "{{.Names}}" 2>&1
    $runningCount = ($containers -split "`n" | Where-Object { $_ -ne "" }).Count
    
    if ($runningCount -ge 4) {
        Write-Host "   [OK] All services are running ($runningCount/4)" -ForegroundColor Green
        $allReady = $true
    } elseif ($elapsed -lt $maxWait) {
        # Only show progress, don't spam
        if ($elapsed % 6 -eq 0) {  # Show every 6 seconds
            Write-Host "   Waiting... ($runningCount/4 services running)" -ForegroundColor Gray
        }
    }
}

if (-not $allReady) {
    Write-Host "   [INFO] Services are starting in background. They may need a few more seconds." -ForegroundColor Yellow
}

# Check service status
Write-Host "`n6. Checking service status..." -ForegroundColor Yellow
docker ps --filter "name=fastapi-ml" --filter "name=mlflow" --filter "name=prometheus" --filter "name=grafana" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

# Display access information
Write-Host "`n============================================================" -ForegroundColor Green
Write-Host "All Services Started Successfully!" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Green
Write-Host ""
Write-Host "Access URLs:" -ForegroundColor Cyan
Write-Host "  FastAPI:     http://localhost:8000" -ForegroundColor White
Write-Host "               http://localhost:8000/docs (API Documentation)" -ForegroundColor Gray
Write-Host "               http://localhost:8000/metrics (Prometheus Metrics)" -ForegroundColor Gray
Write-Host ""
Write-Host "  MLflow:      http://localhost:5000" -ForegroundColor White
Write-Host ""
Write-Host "  Prometheus:  http://localhost:9090" -ForegroundColor White
Write-Host "               Status → Targets (to verify FastAPI scraping)" -ForegroundColor Gray
Write-Host ""
Write-Host "  Grafana:     http://localhost:3000" -ForegroundColor White
Write-Host "               Username: admin" -ForegroundColor Gray
Write-Host "               Password: admin" -ForegroundColor Gray
Write-Host ""
Write-Host "Useful Commands:" -ForegroundColor Cyan
Write-Host "  View logs:    docker-compose -f docker-compose.full.yml logs -f" -ForegroundColor White
Write-Host "  Stop all:     docker-compose -f docker-compose.full.yml down" -ForegroundColor White
Write-Host "  Restart:      docker-compose -f docker-compose.full.yml restart" -ForegroundColor White
Write-Host ""
Write-Host "Next Steps:" -ForegroundColor Cyan
Write-Host "  1. Verify FastAPI is healthy: curl http://localhost:8000/health" -ForegroundColor White
Write-Host "  2. Check Prometheus targets: http://localhost:9090/targets" -ForegroundColor White
Write-Host "  3. Configure Grafana data source: http://localhost:3000" -ForegroundColor White
Write-Host "     → Configuration → Data Sources → Add Prometheus" -ForegroundColor Gray
Write-Host "     → URL: http://prometheus:9090" -ForegroundColor Gray
Write-Host ""

