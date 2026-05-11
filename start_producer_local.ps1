# PowerShell script to start producer locally with correct DATA_PATH

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "Starting Producer (Local Mode)" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

# Set DATA_PATH to point to local data folder
$env:DATA_PATH = "data\prices"

Write-Host "DATA_PATH set to: $env:DATA_PATH" -ForegroundColor Yellow
Write-Host "CSV file location: data\prices\BTCUSDT.csv" -ForegroundColor Yellow
Write-Host ""

Write-Host "[OK] Using Standalone (Mock) configuration - local CSVs only" -ForegroundColor Yellow
Write-Host ""
Write-Host "Starting producer..." -ForegroundColor Yellow
Write-Host "Press Ctrl+C to stop" -ForegroundColor Gray
Write-Host ""

# Start producer
python -m utils.producer_consumer.producer --symbol BTCUSDT



