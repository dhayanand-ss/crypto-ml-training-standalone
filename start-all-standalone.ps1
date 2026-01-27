# PowerShell script to start all services in standalone mode (without Docker)
# This starts: FastAPI, MLflow, Prometheus (if installed locally)

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "Starting All Services (Standalone Mode)" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "This script starts services without Docker." -ForegroundColor Yellow
Write-Host "Services will run in separate PowerShell windows." -ForegroundColor Yellow
Write-Host ""

# Check if services are already running
Write-Host "1. Checking if services are already running..." -ForegroundColor Yellow

$fastapiRunning = Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue
$mlflowRunning = Get-NetTCPConnection -LocalPort 5000 -ErrorAction SilentlyContinue
$prometheusRunning = Get-NetTCPConnection -LocalPort 9090 -ErrorAction SilentlyContinue

if ($fastapiRunning) {
    Write-Host "   [WARNING] FastAPI is already running on port 8000" -ForegroundColor Yellow
}
if ($mlflowRunning) {
    Write-Host "   [WARNING] MLflow is already running on port 5000" -ForegroundColor Yellow
}
if ($prometheusRunning) {
    Write-Host "   [WARNING] Prometheus is already running on port 9090" -ForegroundColor Yellow
}

Write-Host ""

# Start MLflow
Write-Host "2. Starting MLflow..." -ForegroundColor Yellow
if (-not $mlflowRunning) {
    Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$PWD'; python start_mlflow.ps1" -WindowStyle Normal
    Write-Host "   [OK] MLflow starting in new window" -ForegroundColor Green
    Start-Sleep -Seconds 5
} else {
    Write-Host "   [SKIP] MLflow already running" -ForegroundColor Gray
}

# Start FastAPI
Write-Host "`n3. Starting FastAPI..." -ForegroundColor Yellow
if (-not $fastapiRunning) {
    $env:MLFLOW_TRACKING_URI = "http://localhost:5000"
    Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$PWD'; `$env:MLFLOW_TRACKING_URI='http://localhost:5000'; python start_fastapi_server.py" -WindowStyle Normal
    Write-Host "   [OK] FastAPI starting in new window" -ForegroundColor Green
    Start-Sleep -Seconds 5
} else {
    Write-Host "   [SKIP] FastAPI already running" -ForegroundColor Gray
}

# Start Prometheus (if installed)
Write-Host "`n4. Starting Prometheus..." -ForegroundColor Yellow
if (-not $prometheusRunning) {
    # Check if Prometheus is installed
    $prometheusPath = Get-Command prometheus -ErrorAction SilentlyContinue
    if ($prometheusPath) {
        # Check if prometheus.yml exists
        if (-not (Test-Path "prometheus.yml")) {
            Write-Host "   [WARNING] prometheus.yml not found. Creating default..." -ForegroundColor Yellow
            @"
global:
  scrape_interval: 15s
  evaluation_interval: 15s

scrape_configs:
  - job_name: 'fastapi-ml'
    static_configs:
      - targets: ['localhost:8000']
    metrics_path: '/metrics'
    scrape_interval: 15s
"@ | Out-File -FilePath "prometheus.yml" -Encoding utf8
        }
        
        Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$PWD'; prometheus --config.file=prometheus.yml" -WindowStyle Normal
        Write-Host "   [OK] Prometheus starting in new window" -ForegroundColor Green
    } else {
        Write-Host "   [SKIP] Prometheus not installed locally" -ForegroundColor Yellow
        Write-Host "   To install Prometheus:" -ForegroundColor Gray
        Write-Host "   1. Download from: https://prometheus.io/download/" -ForegroundColor Gray
        Write-Host "   2. Extract and add to PATH" -ForegroundColor Gray
        Write-Host "   3. Or use Docker: docker run -d -p 9090:9090 -v `$PWD/prometheus.yml:/etc/prometheus/prometheus.yml prom/prometheus:latest" -ForegroundColor Gray
    }
} else {
    Write-Host "   [SKIP] Prometheus already running" -ForegroundColor Gray
}

# Display access information
Write-Host "`n============================================================" -ForegroundColor Green
Write-Host "Services Started!" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Green
Write-Host ""
Write-Host "Access URLs:" -ForegroundColor Cyan
Write-Host "  FastAPI:     http://localhost:8000" -ForegroundColor White
Write-Host "               http://localhost:8000/docs" -ForegroundColor Gray
Write-Host ""
Write-Host "  MLflow:      http://localhost:5000" -ForegroundColor White
Write-Host ""
if ($prometheusPath) {
    Write-Host "  Prometheus:  http://localhost:9090" -ForegroundColor White
}
Write-Host ""
Write-Host "Note: Each service is running in a separate PowerShell window." -ForegroundColor Yellow
Write-Host "Close the windows to stop the services." -ForegroundColor Yellow
Write-Host ""









