# Cleanup Vast AI Instances Script
# This script helps clean up any stale or problematic Vast AI instances

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "Vast AI Instance Cleanup" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

# Check if vastai CLI is installed
Write-Host "1. Checking Vast AI CLI..." -ForegroundColor Yellow
try {
    $vastaiVersion = vastai --version 2>&1
    Write-Host "   [OK] Vast AI CLI is installed" -ForegroundColor Green
} catch {
    Write-Host "   [ERROR] Vast AI CLI not found!" -ForegroundColor Red
    Write-Host "   Install with: pip install vastai" -ForegroundColor Yellow
    exit 1
}

# Check API key
Write-Host "`n2. Checking Vast AI API key..." -ForegroundColor Yellow
if (Test-Path .env) {
    $envContent = Get-Content .env
    $apiKey = ($envContent | Select-String -Pattern "^VASTAI_API_KEY=(.+)$").Matches.Groups[1].Value
    if ($apiKey) {
        $env:VASTAI_API_KEY = $apiKey
        Write-Host "   [OK] API key loaded from .env" -ForegroundColor Green
    } else {
        Write-Host "   [WARNING] VASTAI_API_KEY not found in .env" -ForegroundColor Yellow
        Write-Host "   Set it with: .\set_vastai_key.ps1" -ForegroundColor Cyan
    }
} else {
    Write-Host "   [WARNING] .env file not found" -ForegroundColor Yellow
}

# Set API key if available
if ($env:VASTAI_API_KEY) {
    vastai set api-key $env:VASTAI_API_KEY 2>&1 | Out-Null
    Write-Host "   [OK] API key configured" -ForegroundColor Green
} else {
    Write-Host "   [ERROR] VASTAI_API_KEY not set!" -ForegroundColor Red
    Write-Host "   Set it with: .\set_vastai_key.ps1" -ForegroundColor Yellow
    exit 1
}

# List all instances
Write-Host "`n3. Listing all Vast AI instances..." -ForegroundColor Yellow
try {
    $instances = vastai show instances --raw 2>&1 | ConvertFrom-Json
    if ($instances) {
        if (-not ($instances -is [Array])) {
            $instances = @($instances)
        }
        Write-Host "   Found $($instances.Count) instance(s)" -ForegroundColor White
        
        if ($instances.Count -gt 0) {
            Write-Host ""
            Write-Host "   Instance Details:" -ForegroundColor Cyan
            foreach ($inst in $instances) {
                $id = $inst.id
                $status = $inst.actual_status
                $cost = $inst.dph_total
                Write-Host "     ID: $id | Status: $status | Cost: `$$cost/hr" -ForegroundColor Gray
            }
        }
    } else {
        Write-Host "   [OK] No instances found" -ForegroundColor Green
        $instances = @()
    }
} catch {
    Write-Host "   [ERROR] Failed to list instances: $_" -ForegroundColor Red
    $instances = @()
}

# Ask if user wants to kill all instances
if ($instances.Count -gt 0) {
    Write-Host ""
    Write-Host "4. Cleanup options:" -ForegroundColor Yellow
    Write-Host "   [1] Kill all instances" -ForegroundColor White
    Write-Host "   [2] Kill specific instance" -ForegroundColor White
    Write-Host "   [3] Skip cleanup" -ForegroundColor White
    Write-Host ""
    $choice = Read-Host "   Enter choice (1-3)"
    
    if ($choice -eq "1") {
        Write-Host "`n   Killing all instances..." -ForegroundColor Yellow
        foreach ($inst in $instances) {
            $id = $inst.id
            Write-Host "     Killing instance $id..." -ForegroundColor Gray
            vastai destroy instance $id 2>&1 | Out-Null
            if ($LASTEXITCODE -eq 0) {
                Write-Host "       [OK] Instance $id terminated" -ForegroundColor Green
            } else {
                Write-Host "       [WARNING] Failed to terminate instance $id (may already be gone)" -ForegroundColor Yellow
            }
        }
        Write-Host "   [OK] Cleanup complete" -ForegroundColor Green
    } elseif ($choice -eq "2") {
        Write-Host ""
        $instanceId = Read-Host "   Enter instance ID to kill"
        Write-Host "   Killing instance $instanceId..." -ForegroundColor Yellow
        vastai destroy instance $instanceId 2>&1 | Out-Null
        if ($LASTEXITCODE -eq 0) {
            Write-Host "   [OK] Instance $instanceId terminated" -ForegroundColor Green
        } else {
            Write-Host "   [WARNING] Failed to terminate instance $instanceId" -ForegroundColor Yellow
        }
    } else {
        Write-Host "   [INFO] Skipping cleanup" -ForegroundColor Gray
    }
} else {
    Write-Host "`n4. No instances to clean up" -ForegroundColor Green
}

Write-Host ""
Write-Host "============================================================" -ForegroundColor Green
Write-Host "Cleanup Complete!" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Green
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Yellow
Write-Host "1. Restart Airflow if needed:" -ForegroundColor White
Write-Host "   docker-compose -f docker-compose.airflow.yml restart" -ForegroundColor Cyan
Write-Host ""
Write-Host "2. Run your DAG again - it should work now!" -ForegroundColor White
Write-Host ""





