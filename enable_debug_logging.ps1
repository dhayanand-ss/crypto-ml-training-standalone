# Enable Debug Logging for Vast AI Training
# This script helps enable detailed debug logging to diagnose docker_build errors

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "Enabling Debug Logging for Vast AI Training" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

# Check if .env file exists
$envFile = ".env"
if (Test-Path $envFile) {
    $envContent = Get-Content $envFile
    
    # Check if AIRFLOW__LOGGING__LOGGING_LEVEL already exists
    $hasLogLevel = $envContent | Select-String -Pattern "^AIRFLOW__LOGGING__LOGGING_LEVEL="
    
    if ($hasLogLevel) {
        Write-Host "Updating existing logging level..." -ForegroundColor Yellow
        $newContent = $envContent | ForEach-Object {
            if ($_ -match "^AIRFLOW__LOGGING__LOGGING_LEVEL=") {
                "AIRFLOW__LOGGING__LOGGING_LEVEL=DEBUG"
            } else {
                $_
            }
        }
        Set-Content -Path $envFile -Value $newContent
        Write-Host "  [OK] Updated logging level to DEBUG" -ForegroundColor Green
    } else {
        Write-Host "Adding DEBUG logging level..." -ForegroundColor Yellow
        Add-Content -Path $envFile -Value "`n# Debug Logging`nAIRFLOW__LOGGING__LOGGING_LEVEL=DEBUG"
        Write-Host "  [OK] Added DEBUG logging level" -ForegroundColor Green
    }
} else {
    Write-Host "Creating .env file with DEBUG logging..." -ForegroundColor Yellow
    @"
# Debug Logging
AIRFLOW__LOGGING__LOGGING_LEVEL=DEBUG
"@ | Out-File -FilePath $envFile -Encoding utf8
    Write-Host "  [OK] Created .env file with DEBUG logging" -ForegroundColor Green
}

Write-Host ""
Write-Host "============================================================" -ForegroundColor Green
Write-Host "Debug Logging Enabled!" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Green
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Yellow
Write-Host "1. Restart Airflow to apply the logging level:" -ForegroundColor White
Write-Host "   docker-compose -f docker-compose.airflow.yml restart" -ForegroundColor Cyan
Write-Host ""
Write-Host "2. Run your training DAG" -ForegroundColor White
Write-Host ""
Write-Host "3. Check detailed logs:" -ForegroundColor White
Write-Host "   docker-compose -f docker-compose.airflow.yml logs -f airflow-scheduler | Select-String -Pattern 'vast_ai|docker_build|startup script'" -ForegroundColor Cyan
Write-Host ""
Write-Host "The logs will now show:" -ForegroundColor Yellow
Write-Host "  - File creation details" -ForegroundColor Gray
Write-Host "  - File permissions and size" -ForegroundColor Gray
Write-Host "  - Complete Vast AI command output" -ForegroundColor Gray
Write-Host "  - Detailed error information" -ForegroundColor Gray
Write-Host ""





