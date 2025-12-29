# Complete script to start Docker, rebuild containers, and test DAGs

Write-Host "=== Starting Docker and Testing Airflow DAGs ===" -ForegroundColor Green

# Step 1: Check if Docker Desktop is running
Write-Host "`n1. Checking Docker Desktop status..." -ForegroundColor Yellow
$dockerRunning = docker ps 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "Docker Desktop is not running!" -ForegroundColor Red
    Write-Host "Please start Docker Desktop and wait for it to fully initialize." -ForegroundColor Yellow
    Write-Host "Then run this script again." -ForegroundColor Yellow
    exit 1
}
Write-Host "Docker Desktop is running." -ForegroundColor Green

# Step 2: Stop existing containers
Write-Host "`n2. Stopping existing containers..." -ForegroundColor Yellow
docker-compose -f docker-compose.airflow.yml down
Start-Sleep -Seconds 2

# Step 3: Rebuild containers
Write-Host "`n3. Rebuilding containers (this may take 10-30 minutes)..." -ForegroundColor Yellow
Write-Host "This is a long process. Please be patient..." -ForegroundColor Cyan
docker-compose -f docker-compose.airflow.yml build

if ($LASTEXITCODE -ne 0) {
    Write-Host "Build failed! Check the error messages above." -ForegroundColor Red
    exit 1
}

Write-Host "Build completed successfully!" -ForegroundColor Green

# Step 4: Start containers
Write-Host "`n4. Starting containers..." -ForegroundColor Yellow
docker-compose -f docker-compose.airflow.yml up -d

if ($LASTEXITCODE -ne 0) {
    Write-Host "Failed to start containers!" -ForegroundColor Red
    exit 1
}

# Step 5: Wait for services to be ready
Write-Host "`n5. Waiting for Airflow services to initialize (30 seconds)..." -ForegroundColor Yellow
Start-Sleep -Seconds 30

# Step 6: Check container status
Write-Host "`n6. Checking container status..." -ForegroundColor Yellow
docker ps --filter "name=airflow" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

# Step 7: Test DAG imports
Write-Host "`n7. Testing DAG imports..." -ForegroundColor Yellow
$importErrors = docker exec crypto-ml-training-standalone-airflow-scheduler-1 airflow dags list-import-errors 2>&1

if ($importErrors -match "ModuleNotFoundError|error|ERROR") {
    Write-Host "Import errors found:" -ForegroundColor Red
    Write-Host $importErrors
} else {
    Write-Host "No import errors found!" -ForegroundColor Green
}

# Step 8: List all DAGs
Write-Host "`n8. Listing all DAGs..." -ForegroundColor Yellow
docker exec crypto-ml-training-standalone-airflow-scheduler-1 airflow dags list

# Step 9: Show DAG structure
Write-Host "`n9. Showing training_pipeline DAG structure..." -ForegroundColor Yellow
docker exec crypto-ml-training-standalone-airflow-scheduler-1 airflow dags show training_pipeline

Write-Host "`n=== Test Complete ===" -ForegroundColor Green
Write-Host "`nUseful commands:" -ForegroundColor Cyan
Write-Host "  Trigger DAG: docker exec crypto-ml-training-standalone-airflow-scheduler-1 airflow dags trigger training_pipeline" -ForegroundColor White
Write-Host "  View logs: docker-compose -f docker-compose.airflow.yml logs -f airflow-scheduler" -ForegroundColor White
Write-Host "  Web UI: http://localhost:8080 (admin/admin)" -ForegroundColor White











