# Script to set VASTAI_API_KEY environment variable
# This will create/update a .env file for docker-compose

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "Setting Vast AI API Key" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

# Check if .env file exists
if (Test-Path .env) {
    Write-Host "Found existing .env file" -ForegroundColor Yellow
    
    # Check if VASTAI_API_KEY already exists
    $existing = Get-Content .env | Select-String -Pattern "^VASTAI_API_KEY="
    if ($existing) {
        Write-Host "VASTAI_API_KEY already exists in .env file" -ForegroundColor Yellow
        $response = Read-Host "Do you want to update it? (y/n)"
        if ($response -ne 'y') {
            Write-Host "Keeping existing key." -ForegroundColor Green
            exit 0
        }
        # Remove old line
        (Get-Content .env) | Where-Object { $_ -notmatch "^VASTAI_API_KEY=" } | Set-Content .env
    }
} else {
    Write-Host "Creating new .env file" -ForegroundColor Green
}

# Get API key from user
$apiKey = Read-Host "Enter your Vast AI API Key"

if ([string]::IsNullOrWhiteSpace($apiKey)) {
    Write-Host "ERROR: API key cannot be empty!" -ForegroundColor Red
    exit 1
}

# Add or update the key in .env file
Add-Content -Path .env -Value "VASTAI_API_KEY=$apiKey" -Force

Write-Host ""
Write-Host "============================================================" -ForegroundColor Green
Write-Host "VASTAI_API_KEY has been set in .env file" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Green
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Yellow
Write-Host "1. Restart your Airflow containers to apply the change:" -ForegroundColor White
Write-Host "   docker-compose -f docker-compose.airflow.yml down" -ForegroundColor Cyan
Write-Host "   docker-compose -f docker-compose.airflow.yml up -d" -ForegroundColor Cyan
Write-Host ""
Write-Host "2. Or set it as a system environment variable (alternative):" -ForegroundColor White
Write-Host "   `$env:VASTAI_API_KEY='$apiKey'" -ForegroundColor Cyan
Write-Host ""



