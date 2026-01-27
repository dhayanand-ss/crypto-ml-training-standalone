# Kubernetes Setup Guide

This guide will walk you through deploying your FastAPI ML application and monitoring stack to Kubernetes.

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Kubernetes Cluster Setup](#kubernetes-cluster-setup)
3. [Deploy FastAPI Application](#deploy-fastapi-application)
4. [Install Monitoring Stack](#install-monitoring-stack)
5. [Access Services](#access-services)
6. [Troubleshooting](#troubleshooting)

---

## Prerequisites

Before you begin, ensure you have:

- **kubectl** installed and configured
- **Helm** installed (v3.x)
- **Docker** installed (for building images)
- Access to a Kubernetes cluster (local or remote)

### Verify Prerequisites

```powershell
# Check kubectl
kubectl version --client

# Check Helm
helm version

# Check cluster connection
kubectl cluster-info
```

### Install Missing Tools

#### Install Helm (Windows)

```powershell
# Option 1: Using the provided script
cd k8-setup
.\install-helm-windows.ps1

# Option 2: Using Chocolatey
choco install kubernetes-helm -y

# Option 3: Manual installation
# Download from: https://github.com/helm/helm/releases
```

If Helm is installed but not in PATH:
```powershell
.\add-helm-to-path.ps1
```

---

## Kubernetes Cluster Setup

You need a running Kubernetes cluster. Choose one of the following options:

### Option 1: Docker Desktop Kubernetes (Easiest for Local Development)

1. Open **Docker Desktop**
2. Go to **Settings → Kubernetes**
3. Check **"Enable Kubernetes"**
4. Click **"Apply & Restart"**
5. Wait for Kubernetes to start (green indicator)

Verify:
```powershell
kubectl cluster-info
kubectl get nodes
```

### Option 2: Minikube (Local Cluster)

```powershell
# Install Minikube (if not installed)
choco install minikube -y

# Start Minikube
minikube start

# Verify
kubectl cluster-info
```

### Option 3: Kind (Kubernetes in Docker)

```powershell
# Install Kind (if not installed)
choco install kind -y

# Create cluster
kind create cluster --name crypto-ml

# Verify
kubectl cluster-info
```

### Option 4: Remote Cluster (GKE, EKS, AKS)

#### Google Cloud (GKE)
```powershell
gcloud container clusters get-credentials CLUSTER_NAME --zone ZONE --project PROJECT_ID
```

#### AWS (EKS)
```powershell
aws eks update-kubeconfig --name CLUSTER_NAME --region REGION
```

#### Azure (AKS)
```powershell
az aks get-credentials --resource-group RESOURCE_GROUP --name CLUSTER_NAME
```

---

## Deploy FastAPI Application

### Step 1: Build Docker Image

First, build the FastAPI Docker image:

```powershell
# From project root
docker build -f Dockerfile.fastapi -t fastapi-ml:latest .
```

**For Minikube:**
```powershell
# Set Docker environment to Minikube
minikube docker-env | Invoke-Expression

# Build image
docker build -f Dockerfile.fastapi -t fastapi-ml:latest .
```

**For Kind:**
```powershell
# Load image into Kind
kind load docker-image fastapi-ml:latest --name crypto-ml
```

**For Remote Cluster:**
```powershell
# Tag and push to container registry
docker tag fastapi-ml:latest YOUR_REGISTRY/fastapi-ml:latest
docker push YOUR_REGISTRY/fastapi-ml:latest

# Update fastapi-deployment.yaml to use your registry image
```

### Step 2: Create Namespace

```powershell
kubectl create namespace platform
```

### Step 3: Deploy FastAPI

```powershell
cd k8-setup

# Deploy FastAPI application
kubectl apply -f fastapi-deployment.yaml

# Deploy FastAPI service
kubectl apply -f fastapi-service.yaml
```

### Step 4: Verify Deployment

```powershell
# Check deployment status
kubectl get deployments -n platform

# Check pods
kubectl get pods -n platform

# Check service
kubectl get svc -n platform

# View pod logs
kubectl logs -f deployment/fastapi-ml -n platform
```

### Step 5: Test FastAPI (Optional)

```powershell
# Port forward to access FastAPI
kubectl port-forward svc/fastapi-ml -n platform 8000:8000

# In another terminal, test the API
curl http://localhost:8000/health
# Or open in browser: http://localhost:8000/docs
```

---

## Install Monitoring Stack

### Step 1: Install Prometheus and Grafana

```powershell
cd k8-setup

# Run the installation script
.\install-prometheus-grafana.ps1
```

**Or manually:**

```powershell
# Add Helm repository
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update

# Create namespace
kubectl create namespace prometheus

# Install Prometheus/Grafana stack
helm upgrade --install prometheus prometheus-community/kube-prometheus-stack `
  -n prometheus `
  --create-namespace `
  -f prometheus-values.yaml

# Apply Grafana configuration
kubectl apply -f grafana-config.yaml

# Restart Grafana to apply config
kubectl rollout restart deployment prometheus-grafana -n prometheus

# Apply Grafana Ingress (optional, requires cert-manager)
kubectl apply -f grafanaingress.yaml
```

### Step 2: Configure FastAPI Metrics Monitoring

```powershell
# Apply ServiceMonitor for FastAPI
kubectl apply -f fast-api.yaml

# Verify ServiceMonitor
kubectl get servicemonitor -n platform
```

### Step 3: Verify Monitoring Stack

```powershell
# Check all pods in prometheus namespace
kubectl get pods -n prometheus

# All pods should be in "Running" state
# Wait for all pods to be ready (may take 2-3 minutes)
kubectl wait --for=condition=ready pod --all -n prometheus --timeout=300s
```

---

## Access Services

### Access FastAPI

```powershell
# Port forward
kubectl port-forward svc/fastapi-ml -n platform 8000:8000

# Access:
# - API Docs: http://localhost:8000/docs
# - Health: http://localhost:8000/health
# - Metrics: http://localhost:8000/metrics
```

### Access Prometheus

```powershell
# Port forward
kubectl port-forward svc/prometheus-kube-prometheus-prometheus -n prometheus 9090:9090

# Access: http://localhost:9090
```

**Verify FastAPI metrics are being scraped:**
1. Go to **Status → Targets** in Prometheus UI
2. Look for `fastapi-ml` target
3. Should show state: **UP**

### Access Grafana

```powershell
# Port forward
kubectl port-forward svc/prometheus-grafana -n prometheus 3000:80

# Access: http://localhost:3000
```

**Get Grafana password:**
```powershell
kubectl get secret prometheus-grafana -n prometheus -o jsonpath="{.data.admin-password}" | ForEach-Object { [System.Text.Encoding]::UTF8.GetString([System.Convert]::FromBase64String($_)) }
```

**Default credentials:**
- Username: `admin`
- Password: `prom-operator` (or use command above)

**Configure Prometheus Data Source in Grafana:**
1. Go to **Configuration → Data Sources**
2. Click **Add data source**
3. Select **Prometheus**
4. URL: `http://prometheus-kube-prometheus-prometheus.prometheus.svc.cluster.local:9090`
5. Click **Save & Test**

**Via Ingress (if configured):**
- https://grafana.gokuladethya.uk

---

## Quick Start Commands

### Complete Setup (All-in-One)

```powershell
# 1. Ensure cluster is running
kubectl cluster-info

# 2. Build and load Docker image (for local clusters)
docker build -f Dockerfile.fastapi -t fastapi-ml:latest .
# For Minikube: minikube docker-env | Invoke-Expression; docker build -f Dockerfile.fastapi -t fastapi-ml:latest .
# For Kind: kind load docker-image fastapi-ml:latest --name crypto-ml

# 3. Create namespaces
kubectl create namespace platform
kubectl create namespace prometheus

# 4. Deploy FastAPI
cd k8-setup
kubectl apply -f fastapi-deployment.yaml
kubectl apply -f fastapi-service.yaml

# 5. Install monitoring
.\install-prometheus-grafana.ps1

# 6. Configure metrics
kubectl apply -f fast-api.yaml

# 7. Verify everything
kubectl get pods -n platform
kubectl get pods -n prometheus
```

### Useful Commands

```powershell
# View all resources
kubectl get all -n platform
kubectl get all -n prometheus

# View logs
kubectl logs -f deployment/fastapi-ml -n platform
kubectl logs -f deployment/prometheus-grafana -n prometheus

# Restart services
kubectl rollout restart deployment/fastapi-ml -n platform
kubectl rollout restart deployment/prometheus-grafana -n prometheus

# Delete everything (cleanup)
kubectl delete namespace platform
kubectl delete namespace prometheus
helm uninstall prometheus -n prometheus
```

---

## Troubleshooting

### FastAPI Pod Not Starting

```powershell
# Check pod status
kubectl get pods -n platform

# Check pod events
kubectl describe pod <pod-name> -n platform

# Check logs
kubectl logs <pod-name> -n platform

# Common issues:
# - Image pull errors: Ensure image exists and is accessible
# - Resource limits: Check if cluster has enough resources
# - Health check failures: Verify /health endpoint works
```

### Image Pull Errors

**For local clusters (Minikube/Kind):**
- Ensure you built the image in the correct Docker environment
- For Minikube: `minikube docker-env | Invoke-Expression` before building
- For Kind: Use `kind load docker-image` after building

**For remote clusters:**
- Push image to container registry
- Update `imagePullPolicy` and image name in `fastapi-deployment.yaml`

### Prometheus Not Scraping FastAPI

```powershell
# 1. Verify ServiceMonitor exists
kubectl get servicemonitor -n platform

# 2. Check service labels match
kubectl get svc -n platform -l app=fastapi-ml

# 3. Check Prometheus targets
# Access Prometheus UI → Status → Targets
# Look for errors in the fastapi-ml target

# 4. Verify FastAPI exposes metrics
kubectl exec -it <fastapi-pod> -n platform -- curl http://localhost:8000/metrics
```

### Grafana Cannot Connect to Prometheus

```powershell
# 1. Check Prometheus service
kubectl get svc -n prometheus | grep prometheus

# 2. Verify data source URL in Grafana
# Should be: http://prometheus-kube-prometheus-prometheus.prometheus.svc.cluster.local:9090

# 3. Test connectivity from Grafana pod
kubectl exec -it <grafana-pod> -n prometheus -- wget -O- http://prometheus-kube-prometheus-prometheus.prometheus.svc.cluster.local:9090
```

### Pods Stuck in Pending State

```powershell
# Check why pod is pending
kubectl describe pod <pod-name> -n <namespace>

# Common reasons:
# - Insufficient resources: Check cluster capacity
# - Node selector issues: Check node labels
# - PVC issues: Check storage class availability
```

### Check Cluster Resources

```powershell
# Check node resources
kubectl top nodes

# Check pod resources
kubectl top pods -n platform
kubectl top pods -n prometheus

# Check cluster capacity
kubectl describe nodes
```

### Reset Everything

```powershell
# Delete all resources
kubectl delete namespace platform
kubectl delete namespace prometheus

# Uninstall Helm release
helm uninstall prometheus -n prometheus

# Clean up (if needed)
kubectl delete namespace prometheus
```

---

## Next Steps

1. **Configure Ingress** for external access (if needed)
2. **Set up SSL/TLS** with cert-manager
3. **Create custom Grafana dashboards** for ML metrics
4. **Set up alerts** in Prometheus/AlertManager
5. **Configure autoscaling** for FastAPI deployment
6. **Set up CI/CD** for automated deployments

---

## File Reference

- `fastapi-deployment.yaml` - FastAPI application deployment
- `fastapi-service.yaml` - FastAPI service (ClusterIP)
- `fast-api.yaml` - ServiceMonitor for Prometheus metrics
- `prometheus-values.yaml` - Prometheus/Grafana Helm values
- `grafana-config.yaml` - Grafana configuration
- `grafanaingress.yaml` - Grafana Ingress (HTTPS)
- `install-prometheus-grafana.ps1` - Installation script

---

## Support

If you encounter issues:
1. Check pod logs: `kubectl logs <pod-name> -n <namespace>`
2. Check events: `kubectl get events -n <namespace> --sort-by='.lastTimestamp'`
3. Verify ServiceMonitor configuration
4. Check Prometheus targets in UI
5. Verify network connectivity between services











