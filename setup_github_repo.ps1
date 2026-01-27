# Script to set up GitHub repository for Vast AI training
# This will help you create and push your code to GitHub

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "GitHub Repository Setup for Vast AI Training" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

$GITHUB_USERNAME = "dhayanand-ss"
$REPO_NAME = "crypto-ml-training-standalone-clean"
$REPO_URL = "https://github.com/$GITHUB_USERNAME/$REPO_NAME.git"

Write-Host "Configuration:" -ForegroundColor Yellow
Write-Host "  Username: $GITHUB_USERNAME" -ForegroundColor White
Write-Host "  Repository: $REPO_NAME" -ForegroundColor White
Write-Host "  URL: $REPO_URL" -ForegroundColor White
Write-Host ""

# Check if git is installed
Write-Host "1. Checking Git installation..." -ForegroundColor Yellow
try {
    $gitVersion = git --version 2>&1
    Write-Host "   [OK] Git is installed: $gitVersion" -ForegroundColor Green
}
catch {
    Write-Host "   [ERROR] Git is not installed!" -ForegroundColor Red
    Write-Host "   Please install Git from: https://git-scm.com/downloads" -ForegroundColor Yellow
    exit 1
}

# Check if already a git repository
Write-Host "`n2. Checking Git repository status..." -ForegroundColor Yellow
if (Test-Path .git) {
    Write-Host "   [OK] Already a Git repository" -ForegroundColor Green
    $isGitRepo = $true
}
else {
    Write-Host "   [INFO] Not a Git repository yet. Will initialize..." -ForegroundColor Yellow
    $isGitRepo = $false
}

# Check if user is logged into GitHub CLI (optional but helpful)
Write-Host "`n3. Checking GitHub CLI (optional)..." -ForegroundColor Yellow
try {
    $ghVersion = gh --version 2>&1 | Select-Object -First 1
    Write-Host "   [OK] GitHub CLI is installed" -ForegroundColor Green
    $hasGhCli = $true
}
catch {
    Write-Host "   [INFO] GitHub CLI not installed (optional)" -ForegroundColor Gray
    Write-Host "   You can install it from: https://cli.github.com/" -ForegroundColor Gray
    $hasGhCli = $false
}

# Step 1: Initialize Git repository if needed
if (-not $isGitRepo) {
    Write-Host "`n4. Initializing Git repository..." -ForegroundColor Yellow
    git init
    if ($LASTEXITCODE -ne 0) {
        Write-Host "   [ERROR] Failed to initialize Git repository!" -ForegroundColor Red
        exit 1
    }
    Write-Host "   [OK] Git repository initialized" -ForegroundColor Green
}

# Step 2: Create .gitignore if it doesn't exist
Write-Host "`n5. Setting up .gitignore..." -ForegroundColor Yellow
if (-not (Test-Path .gitignore)) {
    $gitignoreContent = @"
# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
env/
venv/
ENV/
.venv

# IDEs
.vscode/
.idea/
*.swp
*.swo
*~

# OS
.DS_Store
Thumbs.db

# Project specific
*.log
logs/
mlruns/
mlartifacts/
models/*.pkl
models/*.pth
models/*.onnx
!models/version_registry.json
!models/finbert/
!models/tst/
!models/lightgbm/
!models/onnx/

# Data (keep structure but ignore large files)
data/prices/*.csv
!data/prices/.gitkeep
data/articles.csv

# Environment
.env
*.env
!requirements.txt

# Docker
.dockerignore

# Airflow
airflow.db
airflow.cfg

# Credentials (IMPORTANT: Never commit!)
*.json
!package*.json
!tsconfig*.json
dhaya123-*.json
*-credentials.json
*-key.json

# Temporary files
*.tmp
*.temp
*.bak
*.swp

# Results
results/*.json
results/*.png
results/*.csv

# Custom persistent shared
custom_persistent_shared/
"@
    Set-Content -Path .gitignore -Value $gitignoreContent
    Write-Host "   [OK] Created .gitignore file" -ForegroundColor Green
}
else {
    Write-Host "   [OK] .gitignore already exists" -ForegroundColor Green
}

# Step 3: Add files to Git
Write-Host "`n6. Adding files to Git..." -ForegroundColor Yellow
git add .
if ($LASTEXITCODE -ne 0) {
    Write-Host "   [WARNING] Some files may have been skipped (check .gitignore)" -ForegroundColor Yellow
}
else {
    Write-Host "   [OK] Files added to Git" -ForegroundColor Green
}

# Step 4: Check if there are changes to commit
$gitStatus = git status --porcelain
if ($gitStatus) {
    Write-Host "`n7. Committing changes..." -ForegroundColor Yellow
    git commit -m "Initial commit: Crypto ML Training Standalone"
    if ($LASTEXITCODE -ne 0) {
        Write-Host "   [ERROR] Failed to commit!" -ForegroundColor Red
        exit 1
    }
    Write-Host "   [OK] Changes committed" -ForegroundColor Green
}
else {
    Write-Host "`n7. No changes to commit" -ForegroundColor Yellow
}

# Step 5: Create GitHub repository
Write-Host "`n8. Creating GitHub repository..." -ForegroundColor Yellow
Write-Host "   You need to create the repository on GitHub first." -ForegroundColor White
Write-Host ""
Write-Host "   Option A: Using GitHub CLI (if installed):" -ForegroundColor Cyan
Write-Host "     gh repo create $REPO_NAME --public --source=. --remote=origin --push" -ForegroundColor White
Write-Host ""
Write-Host "   Option B: Manual creation:" -ForegroundColor Cyan
Write-Host "     1. Go to: https://github.com/new" -ForegroundColor White
Write-Host "     2. Repository name: $REPO_NAME" -ForegroundColor White
Write-Host "     3. Set to Public (or Private if you prefer)" -ForegroundColor White
Write-Host "     4. DO NOT initialize with README, .gitignore, or license" -ForegroundColor White
Write-Host "     5. Click 'Create repository'" -ForegroundColor White
Write-Host ""

if ($hasGhCli) {
    $useGhCli = Read-Host "   Do you want to create the repo using GitHub CLI? (y/n)"
    if ($useGhCli -eq 'y') {
        Write-Host "   Creating repository with GitHub CLI..." -ForegroundColor Yellow
        gh repo create $REPO_NAME --public --source=. --remote=origin --push
        if ($LASTEXITCODE -eq 0) {
            Write-Host "   [OK] Repository created and code pushed!" -ForegroundColor Green
            $repoCreated = $true
        }
        else {
            Write-Host "   [ERROR] Failed to create repository with GitHub CLI" -ForegroundColor Red
            Write-Host "   Please create it manually and run the next steps" -ForegroundColor Yellow
            $repoCreated = $false
        }
    }
    else {
        $repoCreated = $false
    }
}
else {
    $repoCreated = $false
}

if (-not $repoCreated) {
    Write-Host ""
    Write-Host "   After creating the repository on GitHub, press Enter to continue..." -ForegroundColor Yellow
    Read-Host
}

# Step 6: Add remote and push
Write-Host "`n9. Setting up remote and pushing code..." -ForegroundColor Yellow

# Check if remote already exists
$existingRemote = git remote get-url origin 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Host "   Remote 'origin' already exists: $existingRemote" -ForegroundColor Yellow
    $updateRemote = Read-Host "   Update it to $REPO_URL? (y/n)"
    if ($updateRemote -eq 'y') {
        git remote set-url origin $REPO_URL
        Write-Host "   [OK] Remote updated" -ForegroundColor Green
    }
}
else {
    git remote add origin $REPO_URL
    Write-Host "   [OK] Remote 'origin' added" -ForegroundColor Green
}

# Push to GitHub
Write-Host "   Pushing code to GitHub..." -ForegroundColor Yellow
git branch -M main
git push -u origin main

if ($LASTEXITCODE -eq 0) {
    Write-Host "   [OK] Code pushed successfully!" -ForegroundColor Green
}
else {
    Write-Host "   [ERROR] Failed to push code!" -ForegroundColor Red
    Write-Host "   You may need to:" -ForegroundColor Yellow
    Write-Host "     1. Check your GitHub credentials" -ForegroundColor White
    Write-Host "     2. Use a personal access token if 2FA is enabled" -ForegroundColor White
    Write-Host "     3. Run: git push -u origin main" -ForegroundColor White
    exit 1
}

# Step 7: Update .env file
Write-Host "`n10. Updating .env file..." -ForegroundColor Yellow
if (Test-Path .env) {
    $envContent = Get-Content .env
    $hasVastaiRepo = $envContent | Select-String -Pattern "^VASTAI_GITHUB_REPO="
    
    if ($hasVastaiRepo) {
        $newContent = $envContent | ForEach-Object {
            if ($_ -match "^VASTAI_GITHUB_REPO=") {
                "VASTAI_GITHUB_REPO=$REPO_URL"
            }
            else {
                $_
            }
        }
        Set-Content -Path .env -Value $newContent
    }
    else {
        Add-Content -Path .env -Value "`n# Vast AI GitHub Repository`nVASTAI_GITHUB_REPO=$REPO_URL"
    }
    Write-Host "   [OK] Updated .env file with VASTAI_GITHUB_REPO" -ForegroundColor Green
}
else {
    "VASTAI_GITHUB_REPO=$REPO_URL" | Out-File -FilePath .env -Encoding utf8
    Write-Host "   [OK] Created .env file with VASTAI_GITHUB_REPO" -ForegroundColor Green
}

# Summary
Write-Host ""
Write-Host "============================================================" -ForegroundColor Green
Write-Host "Setup Complete!" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Green
Write-Host ""
Write-Host "Repository URL: $REPO_URL" -ForegroundColor Cyan
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Yellow
Write-Host "  1. Restart Airflow to pick up the new configuration:" -ForegroundColor White
Write-Host "     docker-compose -f docker-compose.airflow.yml restart" -ForegroundColor Cyan
Write-Host ""
Write-Host "  2. The warning should disappear on the next DAG run" -ForegroundColor White
Write-Host ""
Write-Host "  3. Your Vast AI instances will now clone code from GitHub" -ForegroundColor White
Write-Host ""

