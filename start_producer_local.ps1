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

# REQUIRED: Set GCP credentials for cloud updates
# Set the path to your GCP service account key file:
if (-not $env:GCP_CREDENTIALS_PATH -and -not $env:GOOGLE_APPLICATION_CREDENTIALS) {
    # Try to find the credential file in the current directory
    $credFile = Get-ChildItem -Path . -Filter "*.json" -File | Where-Object { 
        $_.Name -match ".*-.*-.*\.json" -or $_.Name -like "*service-account*.json"
    } | Select-Object -First 1
    
    if ($credFile) {
        $env:GCP_CREDENTIALS_PATH = $credFile.FullName
        Write-Host "[OK] Found GCP credentials: $($credFile.Name)" -ForegroundColor Green
    } else {
        Write-Host "[ERROR] GCP credentials are REQUIRED!" -ForegroundColor Red
        Write-Host "Please set one of:" -ForegroundColor Yellow
        Write-Host "  - GCP_CREDENTIALS_PATH = 'path\to\service-account-key.json'" -ForegroundColor Gray
        Write-Host "  - GOOGLE_APPLICATION_CREDENTIALS = 'path\to\service-account-key.json'" -ForegroundColor Gray
        Write-Host "  - GCP_PROJECT_ID = 'your-project-id'" -ForegroundColor Gray
        Write-Host ""
        Write-Host "Example:" -ForegroundColor Yellow
        Write-Host "  `$env:GCP_CREDENTIALS_PATH = 'dhaya123-335710-039eabaad669.json'" -ForegroundColor Gray
        Write-Host "  `$env:GCP_PROJECT_ID = 'dhaya123-335710'" -ForegroundColor Gray
        exit 1
    }
}

if ($env:GCP_CREDENTIALS_PATH -or $env:GOOGLE_APPLICATION_CREDENTIALS) {
    Write-Host "[OK] GCP credentials configured - will update BOTH CSV and Firestore" -ForegroundColor Green
} else {
    Write-Host "[ERROR] GCP credentials are REQUIRED!" -ForegroundColor Red
    exit 1
}
Write-Host ""

# Check if file exists
if (Test-Path "data\prices\BTCUSDT.csv") {
    Write-Host "[OK] CSV file found" -ForegroundColor Green
} else {
    Write-Host "[ERROR] CSV file not found at data\prices\BTCUSDT.csv" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "Starting producer..." -ForegroundColor Yellow
Write-Host "Press Ctrl+C to stop" -ForegroundColor Gray
Write-Host ""

# Start producer
python -m utils.producer_consumer.producer --symbol BTCUSDT



