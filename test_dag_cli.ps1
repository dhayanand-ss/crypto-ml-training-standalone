# PowerShell script to test DAGs via CLI
# This script tests if the DAGs can be loaded and shows how to run them

Write-Host "=== Testing Airflow DAGs ===" -ForegroundColor Green

# Check if containers are running
Write-Host "`n1. Checking Airflow containers..." -ForegroundColor Yellow
docker ps --filter "name=airflow" --format "table {{.Names}}\t{{.Status}}"

# Wait for scheduler to be ready
Write-Host "`n2. Waiting for Airflow scheduler to be ready..." -ForegroundColor Yellow
Start-Sleep -Seconds 10

# Test DAG imports
Write-Host "`n3. Testing DAG imports..." -ForegroundColor Yellow
docker exec crypto-ml-training-standalone-airflow-scheduler-1 airflow dags list-import-errors

# List all DAGs
Write-Host "`n4. Listing all DAGs..." -ForegroundColor Yellow
docker exec crypto-ml-training-standalone-airflow-scheduler-1 airflow dags list

# Show DAG structure
Write-Host "`n5. Showing training_pipeline DAG structure..." -ForegroundColor Yellow
docker exec crypto-ml-training-standalone-airflow-scheduler-1 airflow dags show training_pipeline

Write-Host "`n=== Test Complete ===" -ForegroundColor Green
Write-Host "`nTo trigger a DAG run manually:" -ForegroundColor Cyan
Write-Host "docker exec crypto-ml-training-standalone-airflow-scheduler-1 airflow dags trigger training_pipeline" -ForegroundColor White
Write-Host "`nTo test a specific task:" -ForegroundColor Cyan
Write-Host "docker exec crypto-ml-training-standalone-airflow-scheduler-1 airflow tasks test training_pipeline pre_train_dataset 2025-01-01" -ForegroundColor White












