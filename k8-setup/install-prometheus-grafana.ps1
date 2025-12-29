# PowerShell script to install Prometheus and Grafana monitoring stack
# This script installs kube-prometheus-stack using Helm

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "Installing Prometheus and Grafana Monitoring Stack" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

# Check if kubectl is available
try {
    kubectl version --client | Out-Null
    Write-Host "[OK] kubectl is available" -ForegroundColor Green
} catch {
    Write-Host "[ERROR] kubectl is not installed or not in PATH" -ForegroundColor Red
    exit 1
}

# Check if helm is available
try {
    helm version | Out-Null
    Write-Host "[OK] helm is available" -ForegroundColor Green
} catch {
    Write-Host "[ERROR] helm is not installed or not in PATH" -ForegroundColor Red
    Write-Host ""
    Write-Host "To install Helm on Windows:" -ForegroundColor Yellow
    Write-Host "  1. Run: .\install-helm-windows.ps1" -ForegroundColor White
    Write-Host "  2. Or install via Chocolatey: choco install kubernetes-helm -y" -ForegroundColor White
    Write-Host "  3. Or see: k8-setup\INSTALL_HELM_WINDOWS.md" -ForegroundColor White
    Write-Host ""
    Write-Host "If Helm is installed but not in PATH:" -ForegroundColor Yellow
    Write-Host "  Run: .\add-helm-to-path.ps1" -ForegroundColor White
    Write-Host ""
    Write-Host "After installing, restart your terminal and try again." -ForegroundColor Yellow
    exit 1
}

# Check if we can connect to cluster
try {
    kubectl cluster-info | Out-Null
    Write-Host "[OK] Kubernetes cluster connection verified" -ForegroundColor Green
} catch {
    Write-Host "[ERROR] Cannot connect to Kubernetes cluster" -ForegroundColor Red
    Write-Host "Please configure kubectl to connect to your cluster" -ForegroundColor Yellow
    exit 1
}

Write-Host ""

# Add Helm repository
Write-Host "Adding Prometheus Community Helm repository..." -ForegroundColor Yellow
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update

Write-Host "[OK] Helm repository added" -ForegroundColor Green
Write-Host ""

# Create namespace
Write-Host "Creating prometheus namespace..." -ForegroundColor Yellow
kubectl create namespace prometheus --dry-run=client -o yaml | kubectl apply -f -

Write-Host "[OK] Namespace created" -ForegroundColor Green
Write-Host ""

# Install kube-prometheus-stack
Write-Host "Installing kube-prometheus-stack..." -ForegroundColor Yellow
helm upgrade --install prometheus prometheus-community/kube-prometheus-stack `
  -n prometheus `
  --create-namespace `
  -f prometheus-values.yaml

Write-Host "[OK] kube-prometheus-stack installed" -ForegroundColor Green
Write-Host ""

# Wait for pods to be ready
Write-Host "Waiting for pods to be ready..." -ForegroundColor Yellow
kubectl wait --for=condition=ready pod `
  --all -n prometheus `
  --timeout=300s

Write-Host "[OK] All pods are ready" -ForegroundColor Green
Write-Host ""

# Apply Grafana configuration
Write-Host "Applying Grafana configuration..." -ForegroundColor Yellow
kubectl apply -f grafana-config.yaml

# Restart Grafana to apply config
kubectl rollout restart deployment prometheus-grafana -n prometheus

Write-Host "[OK] Grafana configuration applied" -ForegroundColor Green
Write-Host ""

# Apply Grafana Ingress (if cert-manager is installed)
Write-Host "Applying Grafana Ingress..." -ForegroundColor Yellow
try {
    kubectl get crd clusterissuers.cert-manager.io | Out-Null
    kubectl apply -f grafanaingress.yaml
    Write-Host "[OK] Grafana Ingress applied" -ForegroundColor Green
} catch {
    Write-Host "[WARNING] cert-manager not found. Skipping Ingress setup." -ForegroundColor Yellow
    Write-Host "To enable HTTPS, install cert-manager first." -ForegroundColor Yellow
}
Write-Host ""

# Get service information
Write-Host "============================================================" -ForegroundColor Green
Write-Host "Installation Complete!" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Green
Write-Host ""
Write-Host "Access Prometheus:" -ForegroundColor Yellow
Write-Host "  kubectl port-forward svc/prometheus-kube-prometheus-prometheus -n prometheus 9090:9090" -ForegroundColor White
Write-Host "  Then open: http://localhost:9090" -ForegroundColor White
Write-Host ""
Write-Host "Access Grafana:" -ForegroundColor Yellow
try {
    $GRAFANA_PASSWORD = kubectl get secret prometheus-grafana -n prometheus -o jsonpath="{.data.admin-password}" | ForEach-Object { [System.Text.Encoding]::UTF8.GetString([System.Convert]::FromBase64String($_)) }
    Write-Host "  Username: admin" -ForegroundColor White
    Write-Host "  Password: $GRAFANA_PASSWORD" -ForegroundColor White
} catch {
    Write-Host "  Username: admin" -ForegroundColor White
    Write-Host "  Password: prom-operator (default)" -ForegroundColor White
}
Write-Host ""
Write-Host "  Port forward: kubectl port-forward svc/prometheus-grafana -n prometheus 3000:80" -ForegroundColor White
Write-Host "  Then open: http://localhost:3000" -ForegroundColor White
Write-Host ""
try {
    kubectl get ingress grafana-ingress -n prometheus | Out-Null
    Write-Host "  Or via Ingress: https://grafana.gokuladethya.uk" -ForegroundColor White
} catch {
    # Ingress not found, skip
}
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Yellow
Write-Host "  1. Apply ServiceMonitor for FastAPI: kubectl apply -f fast-api.yaml" -ForegroundColor White
Write-Host "  2. Configure Grafana data source to point to Prometheus" -ForegroundColor White
Write-Host "  3. Import dashboards in Grafana" -ForegroundColor White
Write-Host ""

