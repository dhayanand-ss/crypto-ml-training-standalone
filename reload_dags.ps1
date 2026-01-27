# Quick script to reload DAGs in Airflow
# This restarts the scheduler to pick up DAG changes

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "Reloading Airflow DAGs" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

# Check if Docker is running
Write-Host "Checking Docker..." -ForegroundColor Yellow
try {
    docker ps | Out-Null
    Write-Host "[OK] Docker is running" -ForegroundColor Green
} catch {
    Write-Host "[ERROR] Docker is not running!" -ForegroundColor Red
    exit 1
}

# Get the scheduler container name
$schedulerContainer = docker ps --filter "name=airflow-scheduler" --format "{{.Names}}" | Select-Object -First 1

if (-not $schedulerContainer) {
    Write-Host "[ERROR] Airflow scheduler container not found!" -ForegroundColor Red
    Write-Host "Make sure Airflow is running with:" -ForegroundColor Yellow
    Write-Host "  docker-compose -f docker-compose.airflow.yml up -d" -ForegroundColor White
    exit 1
}

Write-Host "Found scheduler container: $schedulerContainer" -ForegroundColor Green
Write-Host ""

# Option 1: Just restart the scheduler (quick)
Write-Host "Restarting scheduler to reload DAGs..." -ForegroundColor Yellow
docker restart $schedulerContainer

if ($LASTEXITCODE -eq 0) {
    Write-Host "[OK] Scheduler restarted successfully" -ForegroundColor Green
    Write-Host ""
    Write-Host "Waiting 10 seconds for scheduler to initialize..." -ForegroundColor Yellow
    Start-Sleep -Seconds 10
    
    Write-Host ""
    Write-Host "Checking for DAG import errors..." -ForegroundColor Yellow
    docker exec $schedulerContainer airflow dags list-import-errors 2>&1 | Select-String -Pattern "consumer_delete|ERROR" -Context 0,2
    
    Write-Host ""
    Write-Host "Listing DAGs..." -ForegroundColor Yellow
    docker exec $schedulerContainer airflow dags list | Select-String -Pattern "consumer_delete"
    
    Write-Host ""
    Write-Host "============================================================" -ForegroundColor Green
    Write-Host "DAGs reloaded! Check Airflow UI at http://localhost:8080" -ForegroundColor Green
    Write-Host "============================================================" -ForegroundColor Green
} else {
    Write-Host "[ERROR] Failed to restart scheduler" -ForegroundColor Red
}



