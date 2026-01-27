# PowerShell script to add Helm to PATH
# Run this if Helm is installed but not accessible

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "Adding Helm to PATH" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

# Check if running as Administrator
$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)

if (-not $isAdmin) {
    Write-Host "[WARNING] This script requires Administrator privileges to modify system PATH" -ForegroundColor Yellow
    Write-Host "Please run PowerShell as Administrator and try again." -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Alternative: Add to user PATH (no admin required)..." -ForegroundColor Yellow
}

# Common Helm installation paths
$helmPaths = @(
    "C:\Program Files\Helm",
    "C:\Program Files (x86)\Helm",
    "$env:USERPROFILE\AppData\Local\Helm",
    "$env:LOCALAPPDATA\Helm",
    "$env:ProgramFiles\Helm"
)

# Find Helm installation
$helmPath = $null
foreach ($path in $helmPaths) {
    if (Test-Path "$path\helm.exe") {
        $helmPath = $path
        Write-Host "[OK] Found Helm at: $helmPath" -ForegroundColor Green
        break
    }
}

# If not found, search in common locations
if (-not $helmPath) {
    Write-Host "[INFO] Searching for Helm installation..." -ForegroundColor Yellow
    
    # Search in Program Files
    $programFiles = @("C:\Program Files", "C:\Program Files (x86)")
    foreach ($pf in $programFiles) {
        if (Test-Path $pf) {
            $found = Get-ChildItem -Path $pf -Filter "helm.exe" -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
            if ($found) {
                $helmPath = $found.DirectoryName
                Write-Host "[OK] Found Helm at: $helmPath" -ForegroundColor Green
                break
            }
        }
    }
}

# If still not found, ask user
if (-not $helmPath) {
    Write-Host "[ERROR] Helm installation not found in common locations" -ForegroundColor Red
    Write-Host ""
    Write-Host "Please provide the path to Helm installation:" -ForegroundColor Yellow
    Write-Host "  (e.g., C:\Program Files\Helm or C:\tools\helm)" -ForegroundColor Gray
    $userPath = Read-Host "Enter Helm path"
    
    if (Test-Path "$userPath\helm.exe") {
        $helmPath = $userPath
    } else {
        Write-Host "[ERROR] helm.exe not found at: $userPath" -ForegroundColor Red
        exit 1
    }
}

# Add to PATH
Write-Host ""
Write-Host "Adding to PATH..." -ForegroundColor Yellow

# Get current PATH
if ($isAdmin) {
    $currentPath = [Environment]::GetEnvironmentVariable("Path", "Machine")
    $pathType = "System (Machine)"
} else {
    $currentPath = [Environment]::GetEnvironmentVariable("Path", "User")
    $pathType = "User"
}

# Check if already in PATH
if ($currentPath -like "*$helmPath*") {
    Write-Host "[INFO] Helm path already in $pathType PATH" -ForegroundColor Yellow
} else {
    # Add to PATH
    if ($isAdmin) {
        [Environment]::SetEnvironmentVariable("Path", "$currentPath;$helmPath", "Machine")
        Write-Host "[OK] Added to System PATH (requires restart of terminal)" -ForegroundColor Green
    } else {
        [Environment]::SetEnvironmentVariable("Path", "$currentPath;$helmPath", "User")
        Write-Host "[OK] Added to User PATH (requires restart of terminal)" -ForegroundColor Green
    }
}

# Update current session PATH
$env:Path += ";$helmPath"

# Verify
Write-Host ""
Write-Host "Verifying installation..." -ForegroundColor Yellow
Start-Sleep -Seconds 1

try {
    $helmVersion = helm version --short 2>&1
    Write-Host ""
    Write-Host "============================================================" -ForegroundColor Green
    Write-Host "[SUCCESS] Helm is now accessible!" -ForegroundColor Green
    Write-Host "Version: $helmVersion" -ForegroundColor White
    Write-Host "============================================================" -ForegroundColor Green
    Write-Host ""
    Write-Host "Note: If you opened a new terminal, PATH changes are already active." -ForegroundColor Yellow
    Write-Host "If using current terminal, you may need to restart it for PATH to update." -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Test command: helm version" -ForegroundColor Cyan
} catch {
    Write-Host ""
    Write-Host "[WARNING] Helm added to PATH but not accessible in current session" -ForegroundColor Yellow
    Write-Host "Please restart your terminal and run: helm version" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "PATH has been updated. New terminal windows will have Helm available." -ForegroundColor Green
}
















