# PowerShell script to set GCP credentials in docker-compose.airflow.yml
# This embeds the credentials directly in the docker-compose file

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "Setting GCP Credentials in docker-compose.airflow.yml" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

# Check if credentials file exists
$credFile = "dhaya123-335710-039eabaad669.json"
if (-not (Test-Path $credFile)) {
    Write-Host "[ERROR] Credentials file not found: $credFile" -ForegroundColor Red
    exit 1
}

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

# Escape the JSON for YAML (single quotes around JSON, escape single quotes inside)
# In YAML, we can use single quotes and escape any single quotes inside
$escapedJson = $jsonContent -replace "'", "''"  # Escape single quotes for YAML

# Read docker-compose file
$composeFile = "docker-compose.airflow.yml"
if (-not (Test-Path $composeFile)) {
    Write-Host "[ERROR] docker-compose.airflow.yml not found" -ForegroundColor Red
    exit 1
}

Write-Host "Reading $composeFile..." -ForegroundColor Yellow
$content = Get-Content $composeFile -Raw

# Check if GCP_CREDENTIALS_JSON is already set
if ($content -match "GCP_CREDENTIALS_JSON:\s*\$\{GCP_CREDENTIALS_JSON:-([^}]+)\}") {
    Write-Host "[INFO] GCP_CREDENTIALS_JSON already has a default value" -ForegroundColor Yellow
    Write-Host "Updating with embedded credentials..." -ForegroundColor Yellow
    
    # Replace the default value with our JSON
    $content = $content -replace "GCP_CREDENTIALS_JSON:\s*\$\{GCP_CREDENTIALS_JSON:-[^}]+\}", "GCP_CREDENTIALS_JSON: '${escapedJson}'"
} elseif ($content -match "GCP_CREDENTIALS_JSON:\s*\$\{GCP_CREDENTIALS_JSON:-\}") {
    Write-Host "[INFO] GCP_CREDENTIALS_JSON is empty, setting it..." -ForegroundColor Yellow
    
    # Replace empty default with our JSON
    $content = $content -replace "GCP_CREDENTIALS_JSON:\s*\$\{GCP_CREDENTIALS_JSON:-\}", "GCP_CREDENTIALS_JSON: '${escapedJson}'"
} else {
    Write-Host "[WARNING] Could not find GCP_CREDENTIALS_JSON in docker-compose file" -ForegroundColor Yellow
    Write-Host "You may need to add it manually." -ForegroundColor Yellow
}

# Write back to file
try {
    Set-Content -Path $composeFile -Value $content -NoNewline
    Write-Host "[SUCCESS] Updated $composeFile with embedded credentials" -ForegroundColor Green
    Write-Host ""
    Write-Host "Next steps:" -ForegroundColor Cyan
    Write-Host "1. Restart Airflow services:" -ForegroundColor White
    Write-Host "   docker-compose -f docker-compose.airflow.yml restart" -ForegroundColor Gray
    Write-Host ""
    Write-Host "2. Or recreate containers:" -ForegroundColor White
    Write-Host "   docker-compose -f docker-compose.airflow.yml up -d --force-recreate" -ForegroundColor Gray
} catch {
    Write-Host "[ERROR] Failed to write to $composeFile : $_" -ForegroundColor Red
    exit 1
}

