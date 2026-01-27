# PowerShell script to install Helm on Windows
# This script provides multiple installation methods

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "Installing Helm on Windows" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

# Check if Helm is already installed
try {
    $helmVersion = helm version --short
    Write-Host "[OK] Helm is already installed: $helmVersion" -ForegroundColor Green
    Write-Host ""
    Write-Host "You can now proceed with Prometheus/Grafana installation." -ForegroundColor Yellow
    exit 0
} catch {
    Write-Host "[INFO] Helm is not installed. Proceeding with installation..." -ForegroundColor Yellow
    Write-Host ""
}

# Method 1: Using Chocolatey (Recommended for Windows)
Write-Host "Method 1: Installing via Chocolatey (Recommended)" -ForegroundColor Yellow
Write-Host ""

# Check if Chocolatey is installed
try {
    choco --version | Out-Null
    Write-Host "[OK] Chocolatey is installed" -ForegroundColor Green
    Write-Host ""
    Write-Host "Installing Helm..." -ForegroundColor Yellow
    
    # Install Helm using Chocolatey
    choco install kubernetes-helm -y
    
    if ($LASTEXITCODE -eq 0) {
        Write-Host ""
        Write-Host "[OK] Helm installed successfully via Chocolatey!" -ForegroundColor Green
        
        # Refresh environment variables
        $env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")
        
        Write-Host ""
        Write-Host "Verifying installation..." -ForegroundColor Yellow
        Start-Sleep -Seconds 2
        
        try {
            $helmVersion = helm version --short
            Write-Host "[OK] Helm is working: $helmVersion" -ForegroundColor Green
            Write-Host ""
            Write-Host "You can now run: .\install-prometheus-grafana.ps1" -ForegroundColor Green
            exit 0
        } catch {
            Write-Host "[WARNING] Helm installed but not in PATH. Please restart your terminal." -ForegroundColor Yellow
            Write-Host "After restarting, run: helm version" -ForegroundColor Yellow
            exit 0
        }
    } else {
        Write-Host "[ERROR] Chocolatey installation failed. Trying alternative method..." -ForegroundColor Red
    }
} catch {
    Write-Host "[INFO] Chocolatey is not installed. Trying alternative method..." -ForegroundColor Yellow
    Write-Host ""
}

# Method 2: Manual Installation
Write-Host "Method 2: Manual Installation" -ForegroundColor Yellow
Write-Host ""

$helmVersion = "3.13.3"  # Latest stable version (update as needed)
$helmUrl = "https://get.helm.sh/helm-v${helmVersion}-windows-amd64.zip"
$tempDir = "$env:TEMP\helm-install"
$installDir = "$env:ProgramFiles\Helm"

Write-Host "Downloading Helm v${helmVersion}..." -ForegroundColor Yellow
Write-Host "URL: $helmUrl" -ForegroundColor Gray

# Create temp directory
if (Test-Path $tempDir) {
    Remove-Item $tempDir -Recurse -Force
}
New-Item -ItemType Directory -Path $tempDir -Force | Out-Null

# Download Helm
$zipPath = "$tempDir\helm.zip"
try {
    Invoke-WebRequest -Uri $helmUrl -OutFile $zipPath -UseBasicParsing
    Write-Host "[OK] Download complete" -ForegroundColor Green
} catch {
    Write-Host "[ERROR] Failed to download Helm: $_" -ForegroundColor Red
    Write-Host ""
    Write-Host "Please install Helm manually:" -ForegroundColor Yellow
    Write-Host "  1. Download from: https://github.com/helm/helm/releases" -ForegroundColor White
    Write-Host "  2. Extract to: C:\Program Files\Helm" -ForegroundColor White
    Write-Host "  3. Add to PATH: C:\Program Files\Helm" -ForegroundColor White
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

# Create installation directory
if (-not (Test-Path $installDir)) {
    New-Item -ItemType Directory -Path $installDir -Force | Out-Null
}

# Copy helm.exe
$helmExe = Get-ChildItem -Path $tempDir -Filter "helm.exe" -Recurse | Select-Object -First 1
if ($helmExe) {
    Copy-Item $helmExe.FullName -Destination "$installDir\helm.exe" -Force
    Write-Host "[OK] Helm copied to $installDir" -ForegroundColor Green
} else {
    Write-Host "[ERROR] helm.exe not found in extracted files" -ForegroundColor Red
    exit 1
}

# Add to PATH
Write-Host "Adding Helm to PATH..." -ForegroundColor Yellow

# Check if running as Administrator
$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)

if ($isAdmin) {
    # Add to System PATH (requires admin)
    $currentPath = [Environment]::GetEnvironmentVariable("Path", "Machine")
    if ($currentPath -notlike "*$installDir*") {
        [Environment]::SetEnvironmentVariable("Path", "$currentPath;$installDir", "Machine")
        Write-Host "[OK] Added to System PATH" -ForegroundColor Green
        Write-Host "[INFO] You may need to restart your terminal for PATH changes to take effect" -ForegroundColor Yellow
    } else {
        Write-Host "[OK] Already in System PATH" -ForegroundColor Green
    }
} else {
    # Add to User PATH (no admin required)
    $currentPath = [Environment]::GetEnvironmentVariable("Path", "User")
    if ($currentPath -notlike "*$installDir*") {
        [Environment]::SetEnvironmentVariable("Path", "$currentPath;$installDir", "User")
        Write-Host "[OK] Added to User PATH" -ForegroundColor Green
        Write-Host "[INFO] You may need to restart your terminal for PATH changes to take effect" -ForegroundColor Yellow
    } else {
        Write-Host "[OK] Already in User PATH" -ForegroundColor Green
    }
}

# Cleanup
Remove-Item $tempDir -Recurse -Force

# Refresh PATH in current session
$env:Path += ";$installDir"

# Verify installation
Write-Host ""
Write-Host "Verifying installation..." -ForegroundColor Yellow
Start-Sleep -Seconds 1

try {
    $helmVersion = helm version --short
    Write-Host ""
    Write-Host "============================================================" -ForegroundColor Green
    Write-Host "[SUCCESS] Helm installed successfully!" -ForegroundColor Green
    Write-Host "Version: $helmVersion" -ForegroundColor White
    Write-Host "============================================================" -ForegroundColor Green
    Write-Host ""
    Write-Host "You can now run: .\install-prometheus-grafana.ps1" -ForegroundColor Yellow
} catch {
    Write-Host ""
    Write-Host "[WARNING] Helm installed but not accessible in current session" -ForegroundColor Yellow
    Write-Host "Please restart your terminal and run: helm version" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "If it still doesn't work, manually add to PATH:" -ForegroundColor Yellow
    Write-Host "  $installDir" -ForegroundColor White
}

