# Start Airflow using Docker
# This script starts Airflow in Docker to avoid Windows path issues

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "Starting Airflow with Docker" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

# Check if Docker is running
Write-Host "Checking Docker..." -ForegroundColor Yellow
try {
    docker ps | Out-Null
    Write-Host "[OK] Docker is running" -ForegroundColor Green
} catch {
    Write-Host "[ERROR] Docker is not running!" -ForegroundColor Red
    Write-Host "Please start Docker Desktop and try again." -ForegroundColor Yellow
    exit 1
}

Write-Host ""
Write-Host "Building and starting Airflow services..." -ForegroundColor Yellow
Write-Host "This may take a few minutes on first run..." -ForegroundColor Yellow
Write-Host ""

# Build and start services
docker-compose -f docker-compose.airflow.yml up -d --build

if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "============================================================" -ForegroundColor Green
    Write-Host "Airflow is starting!" -ForegroundColor Green
    Write-Host "============================================================" -ForegroundColor Green
    Write-Host ""
    Write-Host "Waiting for services to be ready..." -ForegroundColor Yellow
    Write-Host ""
    
    # Wait a bit for services to start
    Start-Sleep -Seconds 10
    
    Write-Host "Services are starting. Check status with:" -ForegroundColor Yellow
    Write-Host "  docker-compose -f docker-compose.airflow.yml ps" -ForegroundColor White
    Write-Host ""
    Write-Host "View logs with:" -ForegroundColor Yellow
    Write-Host "  docker-compose -f docker-compose.airflow.yml logs -f" -ForegroundColor White
    Write-Host ""
    Write-Host "Once ready, access Airflow UI at:" -ForegroundColor Yellow
    Write-Host "  http://localhost:8080" -ForegroundColor White
    Write-Host ""
    Write-Host "Login credentials:" -ForegroundColor Yellow
    Write-Host "  Username: admin" -ForegroundColor White
    Write-Host "  Password: admin" -ForegroundColor White
    Write-Host ""
    Write-Host "To stop Airflow:" -ForegroundColor Yellow
    Write-Host "  docker-compose -f docker-compose.airflow.yml down" -ForegroundColor White
    Write-Host ""
} else {
    Write-Host ""
    Write-Host "[ERROR] Failed to start Airflow services" -ForegroundColor Red
    Write-Host "Check the error messages above for details." -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Common issues:" -ForegroundColor Yellow
    Write-Host "  1. Docker Desktop not running" -ForegroundColor White
    Write-Host "  2. Port 8080 already in use" -ForegroundColor White
    Write-Host "  3. Insufficient Docker resources" -ForegroundColor White
    Write-Host ""
}
















