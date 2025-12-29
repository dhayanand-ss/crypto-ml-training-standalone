# PowerShell script to trigger consumer_start DAG
# This will start the producer and all consumers

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "Triggering consumer_start DAG" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

# Check if containers are running
Write-Host "1. Checking if Airflow containers are running..." -ForegroundColor Yellow
$containers = docker ps --filter "name=airflow" --format "{{.Names}}"
if (-not $containers) {
    Write-Host "[ERROR] Airflow containers are not running!" -ForegroundColor Red
    Write-Host "Please start Airflow first:" -ForegroundColor Yellow
    Write-Host "  docker-compose -f docker-compose.airflow.yml up -d" -ForegroundColor White
    exit 1
}
Write-Host "[OK] Airflow containers are running" -ForegroundColor Green
Write-Host ""

# Wait for scheduler to be ready
Write-Host "2. Waiting for scheduler to be ready..." -ForegroundColor Yellow
Start-Sleep -Seconds 5

# Check if DAG exists
Write-Host "3. Checking if consumer_start DAG exists..." -ForegroundColor Yellow
$dagList = docker exec crypto-ml-training-standalone-airflow-scheduler-1 airflow dags list 2>&1
if ($dagList -match "consumer_start") {
    Write-Host "[OK] consumer_start DAG found" -ForegroundColor Green
} else {
    Write-Host "[WARNING] consumer_start DAG not found in list" -ForegroundColor Yellow
    Write-Host "DAGs available:" -ForegroundColor Gray
    Write-Host $dagList
}
Write-Host ""

# Trigger the DAG
Write-Host "4. Triggering consumer_start DAG..." -ForegroundColor Yellow
$result = docker exec crypto-ml-training-standalone-airflow-scheduler-1 airflow dags trigger consumer_start 2>&1

if ($LASTEXITCODE -eq 0) {
    Write-Host "[SUCCESS] DAG triggered successfully!" -ForegroundColor Green
    Write-Host $result
    Write-Host ""
    Write-Host "The producer and consumers will start shortly." -ForegroundColor Cyan
    Write-Host ""
    Write-Host "To monitor progress:" -ForegroundColor Yellow
    Write-Host "  - Web UI: http://localhost:8080" -ForegroundColor White
    Write-Host "  - View logs: docker-compose -f docker-compose.airflow.yml logs -f airflow-scheduler" -ForegroundColor White
    Write-Host "  - Check DAG runs: docker exec crypto-ml-training-standalone-airflow-scheduler-1 airflow dags list-runs -d consumer_start" -ForegroundColor White
} else {
    Write-Host "[ERROR] Failed to trigger DAG" -ForegroundColor Red
    Write-Host $result
    Write-Host ""
    Write-Host "Troubleshooting:" -ForegroundColor Yellow
    Write-Host "  - Check if DAG has import errors: docker exec crypto-ml-training-standalone-airflow-scheduler-1 airflow dags list-import-errors" -ForegroundColor White
    Write-Host "  - Check scheduler logs: docker-compose -f docker-compose.airflow.yml logs airflow-scheduler" -ForegroundColor White
}





