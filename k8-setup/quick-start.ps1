# Quick Start Script for Kubernetes Deployment
# This script automates the Kubernetes deployment process

param(
    [switch]$SkipBuild,
    [switch]$SkipMonitoring,
    [string]$ImageRegistry = "",
    [string]$ImageTag = "latest"
)

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "Kubernetes Quick Start Deployment" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

# Check prerequisites
Write-Host "Checking prerequisites..." -ForegroundColor Yellow

# Check kubectl
try {
    kubectl version --client | Out-Null
    Write-Host "[OK] kubectl is available" -ForegroundColor Green
} catch {
    Write-Host "[ERROR] kubectl is not installed or not in PATH" -ForegroundColor Red
    exit 1
}

# Check Helm
try {
    helm version | Out-Null
    Write-Host "[OK] helm is available" -ForegroundColor Green
} catch {
    Write-Host "[ERROR] helm is not installed. Run: .\install-helm-windows.ps1" -ForegroundColor Red
    exit 1
}

# Check cluster connection
try {
    kubectl cluster-info | Out-Null
    Write-Host "[OK] Kubernetes cluster connection verified" -ForegroundColor Green
} catch {
    Write-Host "[ERROR] Cannot connect to Kubernetes cluster" -ForegroundColor Red
    Write-Host "Please configure kubectl to connect to your cluster" -ForegroundColor Yellow
    Write-Host "See KUBERNETES_SETUP_GUIDE.md for cluster setup options" -ForegroundColor Yellow
    exit 1
}

Write-Host ""

# Step 1: Build Docker image (unless skipped)
if (-not $SkipBuild) {
    Write-Host "Step 1: Building Docker image..." -ForegroundColor Yellow
    
    # Detect cluster type
    $clusterContext = kubectl config current-context
    $isMinikube = $clusterContext -like "*minikube*"
    $isKind = $clusterContext -like "*kind*"
    
    if ($isMinikube) {
        Write-Host "Detected Minikube cluster. Setting Docker environment..." -ForegroundColor Cyan
        minikube docker-env | Invoke-Expression
    }
    
    # Build image
    $imageName = if ($ImageRegistry) { "$ImageRegistry/fastapi-ml:$ImageTag" } else { "fastapi-ml:$ImageTag" }
    
    Write-Host "Building image: $imageName" -ForegroundColor Cyan
    docker build -f Dockerfile.fastapi -t $imageName .
    
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[ERROR] Docker build failed" -ForegroundColor Red
        exit 1
    }
    
    if ($isKind) {
        Write-Host "Loading image into Kind cluster..." -ForegroundColor Cyan
        $kindCluster = kubectl config current-context -replace "kind-", ""
        kind load docker-image $imageName --name $kindCluster
    }
    
    if ($ImageRegistry) {
        Write-Host "Pushing image to registry: $ImageRegistry" -ForegroundColor Cyan
        docker push $imageName
    }
    
    Write-Host "[OK] Docker image built" -ForegroundColor Green
    Write-Host ""
} else {
    Write-Host "Step 1: Skipping Docker build (--SkipBuild specified)" -ForegroundColor Yellow
    $imageName = if ($ImageRegistry) { "$ImageRegistry/fastapi-ml:$ImageTag" } else { "fastapi-ml:$ImageTag" }
    Write-Host ""
}

# Step 2: Create namespaces
Write-Host "Step 2: Creating namespaces..." -ForegroundColor Yellow
kubectl create namespace platform --dry-run=client -o yaml | kubectl apply -f -
kubectl create namespace prometheus --dry-run=client -o yaml | kubectl apply -f -
Write-Host "[OK] Namespaces created" -ForegroundColor Green
Write-Host ""

# Step 3: Update deployment with correct image
Write-Host "Step 3: Updating deployment configuration..." -ForegroundColor Yellow
$deploymentFile = "fastapi-deployment.yaml"
if (Test-Path $deploymentFile) {
    $content = Get-Content $deploymentFile -Raw
    if ($ImageRegistry) {
        # Update image in deployment file
        $content = $content -replace "image: fastapi-ml:latest", "image: $imageName"
        $content = $content -replace "imagePullPolicy: IfNotPresent", "imagePullPolicy: Always"
        Set-Content $deploymentFile -Value $content -NoNewline
        Write-Host "Updated deployment to use image: $imageName" -ForegroundColor Cyan
    }
    Write-Host "[OK] Deployment configuration ready" -ForegroundColor Green
} else {
    Write-Host "[WARNING] fastapi-deployment.yaml not found" -ForegroundColor Yellow
}
Write-Host ""

# Step 4: Deploy FastAPI
Write-Host "Step 4: Deploying FastAPI application..." -ForegroundColor Yellow
kubectl apply -f fastapi-deployment.yaml
kubectl apply -f fastapi-service.yaml
Write-Host "[OK] FastAPI deployed" -ForegroundColor Green
Write-Host ""

# Wait for FastAPI to be ready
Write-Host "Waiting for FastAPI pods to be ready..." -ForegroundColor Yellow
try {
    kubectl wait --for=condition=available deployment/fastapi-ml -n platform --timeout=120s
    Write-Host "[OK] FastAPI is ready" -ForegroundColor Green
} catch {
    Write-Host "[WARNING] FastAPI pods may still be starting. Check with: kubectl get pods -n platform" -ForegroundColor Yellow
}
Write-Host ""

# Step 5: Install monitoring (unless skipped)
if (-not $SkipMonitoring) {
    Write-Host "Step 5: Installing monitoring stack..." -ForegroundColor Yellow
    if (Test-Path "install-prometheus-grafana.ps1") {
        & .\install-prometheus-grafana.ps1
    } else {
        Write-Host "[WARNING] install-prometheus-grafana.ps1 not found. Skipping monitoring." -ForegroundColor Yellow
    }
    Write-Host ""
    
    # Apply ServiceMonitor
    Write-Host "Applying ServiceMonitor for FastAPI metrics..." -ForegroundColor Yellow
    kubectl apply -f fast-api.yaml
    Write-Host "[OK] ServiceMonitor applied" -ForegroundColor Green
    Write-Host ""
} else {
    Write-Host "Step 5: Skipping monitoring stack (--SkipMonitoring specified)" -ForegroundColor Yellow
    Write-Host ""
}

# Summary
Write-Host "============================================================" -ForegroundColor Green
Write-Host "Deployment Complete!" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Green
Write-Host ""

# Show status
Write-Host "Current Status:" -ForegroundColor Yellow
Write-Host ""
Write-Host "FastAPI Pods:" -ForegroundColor Cyan
kubectl get pods -n platform
Write-Host ""

if (-not $SkipMonitoring) {
    Write-Host "Monitoring Pods:" -ForegroundColor Cyan
    kubectl get pods -n prometheus
    Write-Host ""
}

# Access information
Write-Host "Access Services:" -ForegroundColor Yellow
Write-Host ""
Write-Host "FastAPI:" -ForegroundColor Cyan
Write-Host "  kubectl port-forward svc/fastapi-ml -n platform 8000:8000" -ForegroundColor White
Write-Host "  Then open: http://localhost:8000/docs" -ForegroundColor White
Write-Host ""

if (-not $SkipMonitoring) {
    Write-Host "Prometheus:" -ForegroundColor Cyan
    Write-Host "  kubectl port-forward svc/prometheus-kube-prometheus-prometheus -n prometheus 9090:9090" -ForegroundColor White
    Write-Host "  Then open: http://localhost:9090" -ForegroundColor White
    Write-Host ""
    
    Write-Host "Grafana:" -ForegroundColor Cyan
    Write-Host "  kubectl port-forward svc/prometheus-grafana -n prometheus 3000:80" -ForegroundColor White
    Write-Host "  Then open: http://localhost:3000" -ForegroundColor White
    Write-Host "  Username: admin" -ForegroundColor White
    try {
        $GRAFANA_PASSWORD = kubectl get secret prometheus-grafana -n prometheus -o jsonpath="{.data.admin-password}" 2>$null | ForEach-Object { [System.Text.Encoding]::UTF8.GetString([System.Convert]::FromBase64String($_)) }
        if ($GRAFANA_PASSWORD) {
            Write-Host "  Password: $GRAFANA_PASSWORD" -ForegroundColor White
        } else {
            Write-Host "  Password: prom-operator (default)" -ForegroundColor White
        }
    } catch {
        Write-Host "  Password: prom-operator (default)" -ForegroundColor White
    }
    Write-Host ""
}

Write-Host "Useful Commands:" -ForegroundColor Yellow
Write-Host "  View logs: kubectl logs -f deployment/fastapi-ml -n platform" -ForegroundColor White
Write-Host "  Check status: kubectl get all -n platform" -ForegroundColor White
Write-Host "  Restart: kubectl rollout restart deployment/fastapi-ml -n platform" -ForegroundColor White
Write-Host ""

Write-Host "For more information, see: KUBERNETES_SETUP_GUIDE.md" -ForegroundColor Cyan
Write-Host ""











