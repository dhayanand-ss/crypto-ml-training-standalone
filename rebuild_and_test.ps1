# Script to rebuild containers and test DAGs
# This will complete tasks 1 and 2

Write-Host "=== Task 1: Rebuilding Airflow Containers ===" -ForegroundColor Green
Write-Host "This may take 10-30 minutes depending on your system..." -ForegroundColor Yellow

# Check if Docker is running
try {
    docker ps | Out-Null
    Write-Host "Docker is running" -ForegroundColor Green
} catch {
    Write-Host "ERROR: Docker is not running. Please start Docker Desktop first." -ForegroundColor Red
    exit 1
}

# Stop existing containers
Write-Host "`nStopping existing containers..." -ForegroundColor Yellow
docker-compose -f docker-compose.airflow.yml down

# Rebuild containers
Write-Host "`nRebuilding containers (this will take a while)..." -ForegroundColor Yellow
docker-compose -f docker-compose.airflow.yml build

if ($LASTEXITCODE -eq 0) {
    Write-Host "`nBuild completed successfully!" -ForegroundColor Green
    
    # Start containers
    Write-Host "`nStarting containers..." -ForegroundColor Yellow
    docker-compose -f docker-compose.airflow.yml up -d
    
    # Wait for containers to be ready
    Write-Host "`nWaiting for Airflow to initialize (30 seconds)..." -ForegroundColor Yellow
    Start-Sleep -Seconds 30
    
    Write-Host "`n=== Task 2: Testing DAGs ===" -ForegroundColor Green
    
    # Check container status
    Write-Host "`n1. Checking container status..." -ForegroundColor Yellow
    docker ps --filter "name=airflow" --format "table {{.Names}}\t{{.Status}}"
    
    # Test DAG imports
    Write-Host "`n2. Testing DAG imports for errors..." -ForegroundColor Yellow
    $importErrors = docker exec crypto-ml-training-standalone-airflow-scheduler-1 airflow dags list-import-errors 2>&1
    
    if ($importErrors -match "No data found" -or $importErrors -match "filepath") {
        Write-Host "Import errors found:" -ForegroundColor Red
        Write-Host $importErrors
    } else {
        Write-Host "No import errors found!" -ForegroundColor Green
    }
    
    # List all DAGs
    Write-Host "`n3. Listing all DAGs..." -ForegroundColor Yellow
    docker exec crypto-ml-training-standalone-airflow-scheduler-1 airflow dags list
    
    # Show DAG structure
    Write-Host "`n4. Showing training_pipeline DAG structure..." -ForegroundColor Yellow
    docker exec crypto-ml-training-standalone-airflow-scheduler-1 airflow dags show training_pipeline 2>&1 | Select-Object -First 50
    
    # Test a simple task
    Write-Host "`n5. Testing DAG validation..." -ForegroundColor Yellow
    docker exec crypto-ml-training-standalone-airflow-scheduler-1 airflow dags list-import-errors 2>&1 | Select-String -Pattern "training_pipeline|trl_inference|consumer"
    
    Write-Host "`n=== Testing Complete ===" -ForegroundColor Green
    Write-Host "`nTo trigger a DAG run:" -ForegroundColor Cyan
    Write-Host "docker exec crypto-ml-training-standalone-airflow-scheduler-1 airflow dags trigger training_pipeline" -ForegroundColor White
    
} else {
    Write-Host "`nBuild failed! Check the error messages above." -ForegroundColor Red
    exit 1
}

