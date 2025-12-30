# PowerShell script to set GCP credentials as embedded JSON in environment variable
# This avoids file path issues by embedding credentials directly

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "Setting GCP Credentials as Embedded JSON" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

# Check if credentials file exists
$credFile = "dhaya123-335710-039eabaad669.json"
if (-not (Test-Path $credFile)) {
    Write-Host "[ERROR] Credentials file not found: $credFile" -ForegroundColor Red
    Write-Host "Please ensure the GCP service account JSON file exists in the project root." -ForegroundColor Yellow
    exit 1
}

Write-Host "[OK] Credentials file found: $credFile" -ForegroundColor Green
Write-Host ""

# Read the JSON file content
try {
    $jsonContent = Get-Content $credFile -Raw
    # Validate it's valid JSON
    $jsonObject = $jsonContent | ConvertFrom-Json
    Write-Host "[OK] JSON file is valid" -ForegroundColor Green
} catch {
    Write-Host "[ERROR] Invalid JSON file: $_" -ForegroundColor Red
    exit 1
}

# Set environment variable with JSON content
# Escape quotes for PowerShell
$escapedJson = $jsonContent -replace '"', '\"'
$env:GCP_CREDENTIALS_JSON = $jsonContent

Write-Host ""
Write-Host "Environment variable set:" -ForegroundColor Green
Write-Host "  GCP_CREDENTIALS_JSON = [JSON content embedded]" -ForegroundColor Gray
Write-Host "  GCP_PROJECT_ID = dhaya123-335710" -ForegroundColor Gray
Write-Host ""

# Also set project ID
$env:GCP_PROJECT_ID = "dhaya123-335710"

Write-Host "[SUCCESS] GCP credentials are now embedded in environment variable" -ForegroundColor Green
Write-Host ""
Write-Host "Note: This environment variable will be used instead of file paths." -ForegroundColor Yellow
Write-Host "The GCSManager will automatically use embedded credentials when GCP_CREDENTIALS_JSON is set." -ForegroundColor Yellow
Write-Host ""
Write-Host "To use in Docker/Airflow, add to docker-compose.airflow.yml:" -ForegroundColor Cyan
Write-Host "  GCP_CREDENTIALS_JSON: '{\"type\":\"service_account\",...}'" -ForegroundColor Gray
Write-Host ""

