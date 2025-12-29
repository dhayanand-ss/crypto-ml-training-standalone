# Install Helm to user directory (no admin required)
# This installs Helm to a user-accessible location

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "Installing Helm to User Directory" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

$helmVersion = "3.13.3"
$helmUrl = "https://get.helm.sh/helm-v${helmVersion}-windows-amd64.zip"
$installDir = "$env:USERPROFILE\Tools\Helm"
$tempDir = "$env:TEMP\helm-install-$(Get-Random)"

Write-Host "Installing Helm v${helmVersion} to: $installDir" -ForegroundColor Yellow
Write-Host "(No administrator privileges required)" -ForegroundColor Gray
Write-Host ""

# Create installation directory
if (-not (Test-Path $installDir)) {
    New-Item -ItemType Directory -Path $installDir -Force | Out-Null
    Write-Host "[OK] Created directory: $installDir" -ForegroundColor Green
}

# Create temp directory
if (Test-Path $tempDir) {
    Remove-Item $tempDir -Recurse -Force
}
New-Item -ItemType Directory -Path $tempDir -Force | Out-Null

# Download Helm
Write-Host "Downloading Helm..." -ForegroundColor Yellow
$zipPath = "$tempDir\helm.zip"
try {
    Invoke-WebRequest -Uri $helmUrl -OutFile $zipPath -UseBasicParsing
    Write-Host "[OK] Download complete" -ForegroundColor Green
} catch {
    Write-Host "[ERROR] Failed to download Helm: $_" -ForegroundColor Red
    exit 1
}

# Extract Helm
Write-Host "Extracting Helm..." -ForegroundColor Yellow
try {
    Expand-Archive -Path $zipPath -DestinationPath $tempDir -Force
    Write-Host "[OK] Extraction complete" -ForegroundColor Green
} catch {
    Write-Host "[ERROR] Failed to extract Helm: $_" -ForegroundColor Red
    exit 1
}

# Find helm.exe
$helmExe = Get-ChildItem -Path $tempDir -Filter "helm.exe" -Recurse | Select-Object -First 1
if (-not $helmExe) {
    Write-Host "[ERROR] helm.exe not found in extracted files" -ForegroundColor Red
    exit 1
}

# Copy helm.exe
Copy-Item $helmExe.FullName -Destination "$installDir\helm.exe" -Force
Write-Host "[OK] Helm installed to: $installDir" -ForegroundColor Green

# Cleanup
Remove-Item $tempDir -Recurse -Force

# Add to User PATH
Write-Host ""
Write-Host "Adding to User PATH..." -ForegroundColor Yellow
$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
if ($userPath -notlike "*$installDir*") {
    [Environment]::SetEnvironmentVariable("Path", "$userPath;$installDir", "User")
    Write-Host "[OK] Added to User PATH" -ForegroundColor Green
} else {
    Write-Host "[OK] Already in User PATH" -ForegroundColor Green
}

# Add to current session PATH
$env:Path += ";$installDir"

# Verify installation
Write-Host ""
Write-Host "Verifying installation..." -ForegroundColor Yellow
Start-Sleep -Seconds 1

try {
    $helmVersionOutput = & "$installDir\helm.exe" version --short 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host ""
        Write-Host "============================================================" -ForegroundColor Green
        Write-Host "[SUCCESS] Helm installed successfully!" -ForegroundColor Green
        Write-Host "Version: $helmVersionOutput" -ForegroundColor White
        Write-Host "Location: $installDir" -ForegroundColor White
        Write-Host "============================================================" -ForegroundColor Green
        Write-Host ""
        Write-Host "Helm is now available in this terminal session!" -ForegroundColor Yellow
        Write-Host ""
        Write-Host "Test it:" -ForegroundColor Cyan
        Write-Host "  helm version" -ForegroundColor White
        Write-Host ""
        Write-Host "Next steps:" -ForegroundColor Cyan
        Write-Host "  1. Add Prometheus repo: helm repo add prometheus-community https://prometheus-community.github.io/helm-charts" -ForegroundColor White
        Write-Host "  2. Install Prometheus: .\install-prometheus-grafana.ps1" -ForegroundColor White
        Write-Host ""
    } else {
        throw "Helm command failed"
    }
} catch {
    Write-Host ""
    Write-Host "[WARNING] Helm installed but verification failed" -ForegroundColor Yellow
    Write-Host "Try running: & '$installDir\helm.exe' version" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Or restart your terminal and run: helm version" -ForegroundColor Yellow
}
















