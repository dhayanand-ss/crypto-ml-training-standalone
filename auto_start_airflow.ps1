# Auto-start script for Docker and Airflow
# This script checks if Docker is running and starts Airflow containers

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "Auto-Starting Docker and Airflow" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

# Function to check if Docker is running
function Test-DockerRunning {
    try {
        docker ps | Out-Null
        return $true
    } catch {
        return $false
    }
}

# Check if Docker is running
Write-Host "1. Checking Docker Desktop..." -ForegroundColor Yellow
if (Test-DockerRunning) {
    Write-Host "   [OK] Docker is already running" -ForegroundColor Green
} else {
    Write-Host "   [INFO] Docker Desktop is not running" -ForegroundColor Yellow
    Write-Host "   Starting Docker Desktop..." -ForegroundColor Yellow
    
    # Try to start Docker Desktop
    $dockerPath = "C:\Program Files\Docker\Docker\Docker Desktop.exe"
    if (Test-Path $dockerPath) {
        Start-Process $dockerPath
        Write-Host "   [OK] Docker Desktop starting..." -ForegroundColor Green
        Write-Host "   Waiting for Docker to be ready (this may take 30-60 seconds)..." -ForegroundColor Yellow
        
        # Wait for Docker to be ready
        $maxWait = 120  # 2 minutes max
        $waitInterval = 5
        $elapsed = 0
        $dockerReady = $false
        
        while ($elapsed -lt $maxWait -and -not $dockerReady) {
            Start-Sleep -Seconds $waitInterval
            $elapsed += $waitInterval
            if (Test-DockerRunning) {
                $dockerReady = $true
                Write-Host "   [OK] Docker is ready!" -ForegroundColor Green
            } else {
                Write-Host "   Still waiting... ($elapsed seconds)" -ForegroundColor Gray
            }
        }
        
        if (-not $dockerReady) {
            Write-Host "   [WARNING] Docker did not start within timeout" -ForegroundColor Yellow
            Write-Host "   Please start Docker Desktop manually and run this script again" -ForegroundColor Yellow
            exit 1
        }
    } else {
        Write-Host "   [ERROR] Docker Desktop not found at: $dockerPath" -ForegroundColor Red
        Write-Host "   Please install Docker Desktop or update the path in this script" -ForegroundColor Yellow
        exit 1
    }
}

# Change to project directory
$projectDir = "C:\Users\dhaya\crypto-ml-training-standalone"
if (-not (Test-Path $projectDir)) {
    Write-Host "   [ERROR] Project directory not found: $projectDir" -ForegroundColor Red
    exit 1
}

Set-Location $projectDir

# Check if containers are already running
Write-Host "`n2. Checking Airflow containers..." -ForegroundColor Yellow
$containers = docker-compose -f docker-compose.airflow.yml ps -q 2>&1
if ($containers -and $containers.Count -gt 0) {
    $running = docker-compose -f docker-compose.airflow.yml ps --services --filter "status=running" 2>&1
    if ($running -and $running.Count -gt 0) {
        Write-Host "   [OK] Airflow containers are already running" -ForegroundColor Green
        Write-Host "   Running containers:" -ForegroundColor Gray
        docker-compose -f docker-compose.airflow.yml ps --format "table {{.Service}}\t{{.Status}}" | Select-Object -Skip 1
        exit 0
    }
}

# Start containers
Write-Host "   Starting Airflow containers..." -ForegroundColor Yellow
$startOutput = docker-compose -f docker-compose.airflow.yml up -d 2>&1

if ($LASTEXITCODE -eq 0) {
    Write-Host "   [OK] Airflow containers started successfully" -ForegroundColor Green
    Write-Host ""
    Write-Host "   Waiting 10 seconds for services to initialize..." -ForegroundColor Yellow
    Start-Sleep -Seconds 10
    
    Write-Host ""
    Write-Host "   Container Status:" -ForegroundColor Cyan
    docker-compose -f docker-compose.airflow.yml ps --format "table {{.Service}}\t{{.Status}}\t{{.Ports}}"
    
    Write-Host ""
    Write-Host "============================================================" -ForegroundColor Green
    Write-Host "Airflow is ready!" -ForegroundColor Green
    Write-Host "============================================================" -ForegroundColor Green
    Write-Host ""
    Write-Host "Access Airflow UI at: http://localhost:8080" -ForegroundColor Cyan
    Write-Host "Username: admin" -ForegroundColor White
    Write-Host "Password: admin" -ForegroundColor White
    Write-Host ""
} else {
    Write-Host "   [ERROR] Failed to start containers" -ForegroundColor Red
    Write-Host $startOutput -ForegroundColor Red
    exit 1
}

