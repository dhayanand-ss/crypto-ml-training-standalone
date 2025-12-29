# Quick fix script to add Helm to PATH and update current session
# This script finds Helm and adds it to PATH immediately

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "Fixing Helm PATH Issue" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

# Common Helm installation paths
$helmPaths = @(
    "C:\Program Files\Helm",
    "C:\Program Files (x86)\Helm",
    "$env:USERPROFILE\AppData\Local\Helm",
    "$env:LOCALAPPDATA\Helm",
    "$env:ProgramFiles\Helm",
    "C:\tools\helm",
    "C:\helm"
)

# Search for Helm
Write-Host "Searching for Helm installation..." -ForegroundColor Yellow
$helmPath = $null

foreach ($path in $helmPaths) {
    if (Test-Path "$path\helm.exe") {
        $helmPath = $path
        Write-Host "[OK] Found Helm at: $helmPath" -ForegroundColor Green
        break
    }
}

# If not found, search more broadly
if (-not $helmPath) {
    Write-Host "[INFO] Searching in Program Files..." -ForegroundColor Yellow
    
    $searchPaths = @("C:\Program Files", "C:\Program Files (x86)")
    foreach ($searchPath in $searchPaths) {
        if (Test-Path $searchPath) {
            $found = Get-ChildItem -Path $searchPath -Filter "helm.exe" -Recurse -ErrorAction SilentlyContinue -Depth 2 | Select-Object -First 1
            if ($found) {
                $helmPath = $found.DirectoryName
                Write-Host "[OK] Found Helm at: $helmPath" -ForegroundColor Green
                break
            }
        }
    }
}

# If still not found
if (-not $helmPath) {
    Write-Host "[ERROR] Helm not found!" -ForegroundColor Red
    Write-Host ""
    Write-Host "Helm needs to be installed first." -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Options:" -ForegroundColor Yellow
    Write-Host "  1. Run: .\install-helm-windows.ps1" -ForegroundColor White
    Write-Host "  2. Install via Chocolatey: choco install kubernetes-helm -y" -ForegroundColor White
    Write-Host "  3. Install via winget: winget install Helm.Helm" -ForegroundColor White
    Write-Host ""
    exit 1
}

# Check if already in PATH
$currentPath = $env:Path
if ($currentPath -like "*$helmPath*") {
    Write-Host "[INFO] Helm path already in current session PATH" -ForegroundColor Yellow
} else {
    # Add to current session PATH immediately
    $env:Path += ";$helmPath"
    Write-Host "[OK] Added to current session PATH" -ForegroundColor Green
}

# Add to permanent PATH
Write-Host ""
Write-Host "Adding to permanent PATH..." -ForegroundColor Yellow

# Check if running as Administrator
$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)

if ($isAdmin) {
    # Add to System PATH
    $systemPath = [Environment]::GetEnvironmentVariable("Path", "Machine")
    if ($systemPath -notlike "*$helmPath*") {
        [Environment]::SetEnvironmentVariable("Path", "$systemPath;$helmPath", "Machine")
        Write-Host "[OK] Added to System PATH (permanent)" -ForegroundColor Green
    } else {
        Write-Host "[OK] Already in System PATH" -ForegroundColor Green
    }
} else {
    # Add to User PATH
    $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
    if ($userPath -notlike "*$helmPath*") {
        [Environment]::SetEnvironmentVariable("Path", "$userPath;$helmPath", "User")
        Write-Host "[OK] Added to User PATH (permanent)" -ForegroundColor Green
    } else {
        Write-Host "[OK] Already in User PATH" -ForegroundColor Green
    }
}

# Verify Helm works NOW (in current session)
Write-Host ""
Write-Host "Testing Helm in current session..." -ForegroundColor Yellow
Start-Sleep -Seconds 1

try {
    $helmVersion = & "$helmPath\helm.exe" version --short 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host ""
        Write-Host "============================================================" -ForegroundColor Green
        Write-Host "[SUCCESS] Helm is now working!" -ForegroundColor Green
        Write-Host "Version: $helmVersion" -ForegroundColor White
        Write-Host "============================================================" -ForegroundColor Green
        Write-Host ""
        Write-Host "You can now use 'helm' command in this terminal." -ForegroundColor Yellow
        Write-Host ""
        Write-Host "Test it:" -ForegroundColor Cyan
        Write-Host "  helm version" -ForegroundColor White
        Write-Host ""
    } else {
        throw "Helm command failed"
    }
} catch {
    Write-Host ""
    Write-Host "[WARNING] Helm found but command failed" -ForegroundColor Yellow
    Write-Host "Trying direct path..." -ForegroundColor Yellow
    Write-Host ""
    Write-Host "You can use Helm with full path:" -ForegroundColor Yellow
    Write-Host "  & '$helmPath\helm.exe' version" -ForegroundColor White
    Write-Host ""
    Write-Host "Or restart your terminal and run: helm version" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "Next steps:" -ForegroundColor Cyan
Write-Host "  1. Test: helm version" -ForegroundColor White
Write-Host "  2. Add repo: helm repo add prometheus-community https://prometheus-community.github.io/helm-charts" -ForegroundColor White
Write-Host "  3. Install Prometheus: .\install-prometheus-grafana.ps1" -ForegroundColor White
Write-Host ""
















