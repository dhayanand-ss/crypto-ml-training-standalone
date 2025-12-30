# Restart FastAPI with correct MLflow URI
Write-Host "Restarting FastAPI with correct MLflow URI..." -ForegroundColor Green
Write-Host ""

# Set the correct MLflow URI
$env:MLFLOW_TRACKING_URI = "http://localhost:5000"
Write-Host "Set MLFLOW_TRACKING_URI = $env:MLFLOW_TRACKING_URI" -ForegroundColor Cyan
Write-Host ""

# Check if FastAPI is already running
Write-Host "Checking if FastAPI is running..." -ForegroundColor Yellow
try {
    $response = Invoke-WebRequest -Uri "http://localhost:8000/health" -TimeoutSec 2 -ErrorAction Stop
    Write-Host "FastAPI is running. Please stop it first (Ctrl+C in the terminal where it's running)" -ForegroundColor Yellow
    Write-Host "Then run this script again." -ForegroundColor Yellow
    exit 1
} catch {
    Write-Host "FastAPI is not running. Starting it now..." -ForegroundColor Green
}

Write-Host ""
Write-Host "Starting FastAPI server..." -ForegroundColor Green
Write-Host "FastAPI will be available at: http://localhost:8000" -ForegroundColor Cyan
Write-Host "Swagger UI: http://localhost:8000/docs" -ForegroundColor Cyan
Write-Host ""

# Start FastAPI
python start_fastapi_server.py


