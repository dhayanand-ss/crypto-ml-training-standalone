#!/bin/bash
# Installation script for Prometheus and Grafana monitoring stack
# This script installs kube-prometheus-stack using Helm

set -e

echo "============================================================"
echo "Installing Prometheus and Grafana Monitoring Stack"
echo "============================================================"
echo ""

# Check if kubectl is available
if ! command -v kubectl &> /dev/null; then
    echo "ERROR: kubectl is not installed or not in PATH"
    exit 1
fi

# Check if helm is available
if ! command -v helm &> /dev/null; then
    echo "ERROR: helm is not installed or not in PATH"
    echo "Install Helm: https://helm.sh/docs/intro/install/"
    exit 1
fi

# Check if we can connect to cluster
if ! kubectl cluster-info &> /dev/null; then
    echo "ERROR: Cannot connect to Kubernetes cluster"
    echo "Please configure kubectl to connect to your cluster"
    exit 1
fi

echo "[OK] Kubernetes cluster connection verified"
echo ""

# Add Helm repository
echo "Adding Prometheus Community Helm repository..."
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update

echo "[OK] Helm repository added"
echo ""

# Create namespace
echo "Creating prometheus namespace..."
kubectl create namespace prometheus --dry-run=client -o yaml | kubectl apply -f -

echo "[OK] Namespace created"
echo ""

# Install kube-prometheus-stack
echo "Installing kube-prometheus-stack..."
helm upgrade --install prometheus prometheus-community/kube-prometheus-stack \
  -n prometheus \
  --create-namespace \
  -f prometheus-values.yaml

echo "[OK] kube-prometheus-stack installed"
echo ""

# Wait for pods to be ready
echo "Waiting for pods to be ready..."
kubectl wait --for=condition=ready pod \
  --all -n prometheus \
  --timeout=300s

echo "[OK] All pods are ready"
echo ""

# Apply Grafana configuration
echo "Applying Grafana configuration..."
kubectl apply -f grafana-config.yaml

# Restart Grafana to apply config
kubectl rollout restart deployment prometheus-grafana -n prometheus

echo "[OK] Grafana configuration applied"
echo ""

# Apply Grafana Ingress (if cert-manager is installed)
echo "Applying Grafana Ingress..."
if kubectl get crd clusterissuers.cert-manager.io &> /dev/null; then
    kubectl apply -f grafanaingress.yaml
    echo "[OK] Grafana Ingress applied"
else
    echo "[WARNING] cert-manager not found. Skipping Ingress setup."
    echo "To enable HTTPS, install cert-manager first."
fi
echo ""

# Get service information
echo "============================================================"
echo "Installation Complete!"
echo "============================================================"
echo ""
echo "Access Prometheus:"
echo "  kubectl port-forward svc/prometheus-kube-prometheus-prometheus -n prometheus 9090:9090"
echo "  Then open: http://localhost:9090"
echo ""
echo "Access Grafana:"
GRAFANA_PASSWORD=$(kubectl get secret prometheus-grafana -n prometheus -o jsonpath="{.data.admin-password}" | base64 -d)
echo "  Username: admin"
echo "  Password: $GRAFANA_PASSWORD"
echo ""
echo "  Port forward: kubectl port-forward svc/prometheus-grafana -n prometheus 3000:80"
echo "  Then open: http://localhost:3000"
echo ""
if kubectl get ingress grafana-ingress -n prometheus &> /dev/null; then
    echo "  Or via Ingress: https://grafana.gokuladethya.uk"
fi
echo ""
echo "Next steps:"
echo "  1. Apply ServiceMonitor for FastAPI: kubectl apply -f fast-api.yaml"
echo "  2. Configure Grafana data source to point to Prometheus"
echo "  3. Import dashboards in Grafana"
echo ""
















