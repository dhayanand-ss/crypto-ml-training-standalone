# Quick script to check if Airflow is running

Write-Host "Checking Airflow services..." -ForegroundColor Yellow
Write-Host ""

# Check Docker containers
$containers = docker ps --filter "name=airflow" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

if ($containers) {
    Write-Host "[OK] Airflow containers are running:" -ForegroundColor Green
    Write-Host $containers
    Write-Host ""
    Write-Host "Access Airflow UI at: http://localhost:8080" -ForegroundColor Cyan
    Write-Host "  Username: admin" -ForegroundColor White
    Write-Host "  Password: admin" -ForegroundColor White
} else {
    Write-Host "[INFO] Airflow is not running" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "To start Airflow, run:" -ForegroundColor Yellow
    Write-Host "  .\start_airflow_docker.ps1" -ForegroundColor White
}

Write-Host ""
Write-Host "Useful commands:" -ForegroundColor Yellow
Write-Host "  - View logs: docker-compose -f docker-compose.airflow.yml logs -f" -ForegroundColor White
Write-Host "  - Stop Airflow: docker-compose -f docker-compose.airflow.yml down" -ForegroundColor White
Write-Host "  - Restart Airflow: docker-compose -f docker-compose.airflow.yml restart" -ForegroundColor White





