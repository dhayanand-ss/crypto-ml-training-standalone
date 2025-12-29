# PowerShell script to check Airflow DAG status
# This script provides multiple ways to check DAG status

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "Airflow DAG Status Checker" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

# Check if containers are running
Write-Host "1. Checking Airflow containers..." -ForegroundColor Yellow
$containers = docker ps --filter "name=airflow" --format "{{.Names}}"
if (-not $containers) {
    Write-Host "[ERROR] Airflow containers are not running!" -ForegroundColor Red
    Write-Host "Start Airflow with: .\start_airflow_docker.ps1" -ForegroundColor Yellow
    exit 1
}
docker ps --filter "name=airflow" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
Write-Host ""

# Get scheduler container name
$schedulerContainer = docker ps --filter "name=airflow-scheduler" --format "{{.Names}}" | Select-Object -First 1
if (-not $schedulerContainer) {
    Write-Host "[ERROR] Airflow scheduler container not found!" -ForegroundColor Red
    exit 1
}

Write-Host "Using scheduler container: $schedulerContainer" -ForegroundColor Gray
Write-Host ""

# Wait a moment for scheduler to be ready
Write-Host "2. Waiting for scheduler to be ready..." -ForegroundColor Yellow
Start-Sleep -Seconds 5
Write-Host ""

# Check for import errors
Write-Host "3. Checking for DAG import errors..." -ForegroundColor Yellow
$importErrors = docker exec $schedulerContainer airflow dags list-import-errors 2>&1
if ($importErrors -match "No import errors") {
    Write-Host "[OK] No DAG import errors" -ForegroundColor Green
} else {
    Write-Host $importErrors
}
Write-Host ""

# List all DAGs with their status
Write-Host "4. Listing all DAGs and their status..." -ForegroundColor Yellow
docker exec $schedulerContainer airflow dags list
Write-Host ""

# Show DAG runs for each DAG
Write-Host "5. Recent DAG runs..." -ForegroundColor Yellow
Write-Host ""

# Get list of DAGs
$dagList = docker exec $schedulerContainer airflow dags list 2>&1 | Select-String -Pattern "^\s+\w+" | ForEach-Object { $_.Line.Trim() -split '\s+' | Select-Object -First 1 }

foreach ($dag in $dagList) {
    if ($dag -and $dag -ne "dag_id") {
        Write-Host "  DAG: $dag" -ForegroundColor Cyan
        $runs = docker exec $schedulerContainer airflow dags list-runs -d $dag --state running,success,failed,queued 2>&1 | Select-Object -First 5
        if ($runs) {
            Write-Host $runs
        } else {
            Write-Host "    No recent runs" -ForegroundColor Gray
        }
        Write-Host ""
    }
}

# Summary
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "Summary" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Access Airflow UI at: http://localhost:8080" -ForegroundColor Yellow
Write-Host "  Username: admin" -ForegroundColor White
Write-Host "  Password: admin" -ForegroundColor White
Write-Host ""
Write-Host "Useful commands:" -ForegroundColor Yellow
Write-Host "  - List all DAGs: docker exec $schedulerContainer airflow dags list" -ForegroundColor White
Write-Host "  - List runs for a DAG: docker exec $schedulerContainer airflow dags list-runs -d <dag_id>" -ForegroundColor White
Write-Host "  - Show DAG details: docker exec $schedulerContainer airflow dags show <dag_id>" -ForegroundColor White
Write-Host "  - Trigger a DAG: docker exec $schedulerContainer airflow dags trigger <dag_id>" -ForegroundColor White
Write-Host "  - Pause a DAG: docker exec $schedulerContainer airflow dags pause <dag_id>" -ForegroundColor White
Write-Host "  - Unpause a DAG: docker exec $schedulerContainer airflow dags unpause <dag_id>" -ForegroundColor White
Write-Host ""





