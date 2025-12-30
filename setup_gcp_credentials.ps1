# PowerShell script to set up GCP credentials for Airflow

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "GCP Credentials Setup for Airflow" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

# Check if credentials file exists
$credFile = "dhaya123-335710-039eabaad669.json"
if (Test-Path $credFile) {
    Write-Host "[OK] Credentials file found: $credFile" -ForegroundColor Green
    $credPath = (Resolve-Path $credFile).Path
} else {
    Write-Host "[ERROR] Credentials file not found: $credFile" -ForegroundColor Red
    Write-Host "Please ensure the GCP service account JSON file exists in the project root." -ForegroundColor Yellow
    exit 1
}

# Set environment variables
$env:GCP_CREDENTIALS_PATH = $credPath
$env:GOOGLE_APPLICATION_CREDENTIALS = $credPath
$env:GCP_PROJECT_ID = "dhaya123-335710"

Write-Host ""
Write-Host "Environment variables set:" -ForegroundColor Green
Write-Host "  GCP_CREDENTIALS_PATH = $env:GCP_CREDENTIALS_PATH" -ForegroundColor Gray
Write-Host "  GOOGLE_APPLICATION_CREDENTIALS = $env:GOOGLE_APPLICATION_CREDENTIALS" -ForegroundColor Gray
Write-Host "  GCP_PROJECT_ID = $env:GCP_PROJECT_ID" -ForegroundColor Gray

# Add to .env file if it exists
if (Test-Path ".env") {
    Write-Host ""
    Write-Host "Updating .env file..." -ForegroundColor Yellow
    
    $envContent = Get-Content .env -Raw
    
    # Remove existing GCP variables if they exist
    $envContent = $envContent -replace "(?m)^GCP_CREDENTIALS_PATH=.*$", ""
    $envContent = $envContent -replace "(?m)^GOOGLE_APPLICATION_CREDENTIALS=.*$", ""
    $envContent = $envContent -replace "(?m)^GCP_PROJECT_ID=.*$", ""
    $envContent = $envContent.Trim()
    
    # Add new GCP variables
    $gcpVars = @"

# GCP Credentials Configuration
GCP_CREDENTIALS_PATH=./dhaya123-335710-039eabaad669.json
GOOGLE_APPLICATION_CREDENTIALS=./dhaya123-335710-039eabaad669.json
GCP_PROJECT_ID=dhaya123-335710
"@
    
    $envContent += $gcpVars
    Set-Content -Path .env -Value $envContent
    Write-Host "[OK] .env file updated" -ForegroundColor Green
} else {
    Write-Host ""
    Write-Host "[INFO] .env file not found. Creating new .env file..." -ForegroundColor Yellow
    $gcpVars = @"
# GCP Credentials Configuration
GCP_CREDENTIALS_PATH=./dhaya123-335710-039eabaad669.json
GOOGLE_APPLICATION_CREDENTIALS=./dhaya123-335710-039eabaad669.json
GCP_PROJECT_ID=dhaya123-335710
"@
    Set-Content -Path .env -Value $gcpVars
    Write-Host "[OK] .env file created" -ForegroundColor Green
}

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "Setup Complete!" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Yellow
Write-Host "  1. Restart Airflow services:" -ForegroundColor Gray
Write-Host "     docker-compose -f docker-compose.airflow.yml restart" -ForegroundColor White
Write-Host ""
Write-Host "  2. Verify credentials in Airflow container:" -ForegroundColor Gray
Write-Host "     docker exec -it <airflow-container> env | grep GCP" -ForegroundColor White
Write-Host ""
Write-Host "  3. Test GCS connection in Airflow:" -ForegroundColor Gray
Write-Host "     Check logs of pre_train_dataset task" -ForegroundColor White
Write-Host ""





