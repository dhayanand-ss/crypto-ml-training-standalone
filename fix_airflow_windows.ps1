# Fix Airflow Windows Path Issue
# This script sets AIRFLOW_HOME to avoid the %dhaya% path issue

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "Fixing Airflow Windows Path Issue" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

# Set AIRFLOW_HOME to a path without special characters
$airflowHome = "C:\airflow"

# Create directory if it doesn't exist
if (-not (Test-Path $airflowHome)) {
    New-Item -ItemType Directory -Path $airflowHome -Force | Out-Null
    Write-Host "[OK] Created directory: $airflowHome" -ForegroundColor Green
} else {
    Write-Host "[OK] Directory exists: $airflowHome" -ForegroundColor Green
}

# Set environment variable for current session
$env:AIRFLOW_HOME = $airflowHome
Write-Host "[OK] Set AIRFLOW_HOME = $airflowHome" -ForegroundColor Green

# Create symlink or copy dags folder
$dagsSource = Join-Path $PSScriptRoot "dags"
$dagsTarget = Join-Path $airflowHome "dags"

if (-not (Test-Path $dagsTarget)) {
    # Create symlink to your dags folder
    try {
        New-Item -ItemType SymbolicLink -Path $dagsTarget -Target $dagsSource -Force | Out-Null
        Write-Host "[OK] Created symlink: $dagsTarget -> $dagsSource" -ForegroundColor Green
    } catch {
        # If symlink fails, just copy
        Copy-Item -Path $dagsSource -Destination $dagsTarget -Recurse -Force
        Write-Host "[OK] Copied dags folder to: $dagsTarget" -ForegroundColor Green
    }
} else {
    Write-Host "[INFO] Dags folder already exists at: $dagsTarget" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "Setup Complete!" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Now you can run:" -ForegroundColor Yellow
Write-Host "  airflow webserver --port 8080" -ForegroundColor White
Write-Host ""
Write-Host "Or start Airflow with:" -ForegroundColor Yellow
Write-Host "  airflow db init" -ForegroundColor White
Write-Host "  airflow webserver --port 8080" -ForegroundColor White
Write-Host ""
















