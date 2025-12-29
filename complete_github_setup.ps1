# Complete GitHub Repository Setup Script
# This script will authenticate, create the repo, and push code

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "Complete GitHub Repository Setup" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

$GITHUB_USERNAME = "dhayanand-ss"
$REPO_NAME = "crypto-ml-training-standalone"
$REPO_URL = "https://github.com/$GITHUB_USERNAME/$REPO_NAME.git"

# Step 1: Check GitHub CLI authentication
Write-Host "1. Checking GitHub CLI authentication..." -ForegroundColor Yellow
$authStatus = gh auth status 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "   [INFO] Not authenticated. Starting authentication process..." -ForegroundColor Yellow
    Write-Host ""
    Write-Host "   You'll be prompted to:" -ForegroundColor White
    Write-Host "   1. Choose GitHub.com" -ForegroundColor Gray
    Write-Host "   2. Choose authentication method (browser recommended)" -ForegroundColor Gray
    Write-Host "   3. Authorize the application" -ForegroundColor Gray
    Write-Host ""
    $continue = Read-Host "   Press Enter to start authentication (or 'skip' to do it manually)"
    
    if ($continue -ne 'skip') {
        gh auth login
        if ($LASTEXITCODE -ne 0) {
            Write-Host "   [ERROR] Authentication failed!" -ForegroundColor Red
            Write-Host "   Please run manually: gh auth login" -ForegroundColor Yellow
            exit 1
        }
        Write-Host "   [OK] Authenticated successfully!" -ForegroundColor Green
    } else {
        Write-Host "   [INFO] Skipping authentication. Please run 'gh auth login' manually." -ForegroundColor Yellow
        Write-Host "   Then run this script again or create the repo manually." -ForegroundColor Yellow
        exit 0
    }
} else {
    Write-Host "   [OK] Already authenticated" -ForegroundColor Green
}

# Step 2: Check if repository already exists
Write-Host "`n2. Checking if repository exists..." -ForegroundColor Yellow
$repoExists = gh repo view $GITHUB_USERNAME/$REPO_NAME 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Host "   [INFO] Repository already exists!" -ForegroundColor Yellow
    $useExisting = Read-Host "   Use existing repository? (y/n)"
    if ($useExisting -ne 'y') {
        Write-Host "   [INFO] Please delete the repository first or choose a different name." -ForegroundColor Yellow
        exit 1
    }
} else {
    Write-Host "   [INFO] Repository doesn't exist. Will create it..." -ForegroundColor Yellow
}

# Step 3: Create repository
Write-Host "`n3. Creating GitHub repository..." -ForegroundColor Yellow
if ($LASTEXITCODE -ne 0) {
    gh repo create $REPO_NAME --public --description "Crypto ML Training Standalone - Vast AI Training Pipeline"
    if ($LASTEXITCODE -ne 0) {
        Write-Host "   [ERROR] Failed to create repository!" -ForegroundColor Red
        Write-Host "   Error details above. Please check and try again." -ForegroundColor Yellow
        exit 1
    }
    Write-Host "   [OK] Repository created successfully!" -ForegroundColor Green
} else {
    Write-Host "   [OK] Using existing repository" -ForegroundColor Green
}

# Step 4: Set up remote and push
Write-Host "`n4. Setting up Git remote..." -ForegroundColor Yellow
$existingRemote = git remote get-url origin 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Host "   Remote 'origin' exists: $existingRemote" -ForegroundColor Gray
    if ($existingRemote -ne $REPO_URL) {
        git remote set-url origin $REPO_URL
        Write-Host "   [OK] Remote updated to: $REPO_URL" -ForegroundColor Green
    } else {
        Write-Host "   [OK] Remote already configured correctly" -ForegroundColor Green
    }
} else {
    git remote add origin $REPO_URL
    Write-Host "   [OK] Remote 'origin' added" -ForegroundColor Green
}

# Step 5: Push code
Write-Host "`n5. Pushing code to GitHub..." -ForegroundColor Yellow
Write-Host "   This may take a few minutes depending on your connection..." -ForegroundColor Gray

# Ensure we're on main branch
git branch -M main 2>&1 | Out-Null

# Push to GitHub
git push -u origin main 2>&1 | Tee-Object -Variable pushOutput

if ($LASTEXITCODE -eq 0) {
    Write-Host "   [OK] Code pushed successfully!" -ForegroundColor Green
} else {
    Write-Host "   [ERROR] Failed to push code!" -ForegroundColor Red
    Write-Host ""
    Write-Host "   Common issues:" -ForegroundColor Yellow
    Write-Host "   1. Authentication failed - try: gh auth login" -ForegroundColor White
    Write-Host "   2. Repository doesn't exist - check if it was created" -ForegroundColor White
    Write-Host "   3. Network issues - check your internet connection" -ForegroundColor White
    Write-Host ""
    Write-Host "   You can try pushing manually:" -ForegroundColor Yellow
    Write-Host "   git push -u origin main" -ForegroundColor Cyan
    exit 1
}

# Step 6: Verify .env file
Write-Host "`n6. Verifying configuration..." -ForegroundColor Yellow
if (Test-Path .env) {
    $envContent = Get-Content .env
    $hasVastaiRepo = $envContent | Select-String -Pattern "^VASTAI_GITHUB_REPO="
    
    if ($hasVastaiRepo) {
        $newContent = $envContent | ForEach-Object {
            if ($_ -match "^VASTAI_GITHUB_REPO=") {
                "VASTAI_GITHUB_REPO=$REPO_URL"
            } else {
                $_
            }
        }
        Set-Content -Path .env -Value $newContent
        Write-Host "   [OK] Updated VASTAI_GITHUB_REPO in .env" -ForegroundColor Green
    } else {
        Add-Content -Path .env -Value "`n# Vast AI GitHub Repository`nVASTAI_GITHUB_REPO=$REPO_URL"
        Write-Host "   [OK] Added VASTAI_GITHUB_REPO to .env" -ForegroundColor Green
    }
} else {
    "VASTAI_GITHUB_REPO=$REPO_URL" | Out-File -FilePath .env -Encoding utf8
    Write-Host "   [OK] Created .env file with VASTAI_GITHUB_REPO" -ForegroundColor Green
}

# Step 7: Summary
Write-Host ""
Write-Host "============================================================" -ForegroundColor Green
Write-Host "Setup Complete!" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Green
Write-Host ""
Write-Host "Repository URL: $REPO_URL" -ForegroundColor Cyan
Write-Host ""
Write-Host "Next step: Restart Airflow to pick up the configuration:" -ForegroundColor Yellow
Write-Host "  docker-compose -f docker-compose.airflow.yml restart" -ForegroundColor Cyan
Write-Host ""
Write-Host "The warning about GitHub repository should disappear on the next DAG run!" -ForegroundColor Green
Write-Host ""

