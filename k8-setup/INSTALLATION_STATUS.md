# Prometheus & Grafana Installation Status

## Current Status

The installation script has been executed, but **kubectl is configured to connect to `localhost:8080`** which is not accessible. This means:

1. ✅ Helm is installed and working
2. ✅ Prometheus Helm repository is added
3. ⚠️ Kubernetes cluster connection is not available
4. ⚠️ Installation cannot complete without a running cluster

## What You Need

### Option 1: Connect to Your Remote Kubernetes Cluster

If you have a remote Kubernetes cluster (GKE, EKS, AKS, etc.):

1. **Configure kubectl** to point to your cluster:
   ```powershell
   # For GKE
   gcloud container clusters get-credentials CLUSTER_NAME --zone ZONE
   
   # For EKS
   aws eks update-kubeconfig --name CLUSTER_NAME --region REGION
   
   # For AKS
   az aks get-credentials --resource-group RESOURCE_GROUP --name CLUSTER_NAME
   ```

2. **Verify connection:**
   ```powershell
   kubectl cluster-info
   ```

3. **Run installation again:**
   ```powershell
   cd k8-setup
   .\install-prometheus-grafana.ps1
   ```

### Option 2: Use Local Kubernetes (Minikube/Kind)

If you want to test locally:

#### Using Minikube

```powershell
# Install minikube (if not installed)
# choco install minikube

# Start minikube
minikube start

# Verify
kubectl cluster-info
```

#### Using Kind

```powershell
# Install kind (if not installed)
# choco install kind

# Create cluster
kind create cluster --name prometheus-test

# Verify
kubectl cluster-info
```

Then run the installation script.

### Option 3: Use Docker Desktop Kubernetes

If you have Docker Desktop:

1. **Enable Kubernetes:**
   - Open Docker Desktop
   - Go to Settings → Kubernetes
   - Check "Enable Kubernetes"
   - Click "Apply & Restart"

2. **Verify:**
   ```powershell
   kubectl cluster-info
   ```

3. **Run installation:**
   ```powershell
   cd k8-setup
   .\install-prometheus-grafana.ps1
   ```

## Installation Commands (Once Cluster is Ready)

Once you have a working Kubernetes cluster:

```powershell
cd k8-setup

# 1. Update Helm repos
helm repo update

# 2. Create namespace
kubectl create namespace prometheus

# 3. Install Prometheus/Grafana
helm upgrade --install prometheus prometheus-community/kube-prometheus-stack `
  -n prometheus `
  --create-namespace `
  -f prometheus-values.yaml

# 4. Apply Grafana config
kubectl apply -f grafana-config.yaml

# 5. Apply Grafana Ingress (optional)
kubectl apply -f grafanaingress.yaml

# 6. Apply FastAPI ServiceMonitor
kubectl apply -f fast-api.yaml
```

## Verify Installation

Once installed, check status:

```powershell
# Check pods
kubectl get pods -n prometheus

# Check services
kubectl get svc -n prometheus

# Check Helm release
helm list -n prometheus
```

## Access Services

### Prometheus

```powershell
kubectl port-forward svc/prometheus-kube-prometheus-prometheus -n prometheus 9090:9090
```

Access: http://localhost:9090

### Grafana

```powershell
kubectl port-forward svc/prometheus-grafana -n prometheus 3000:80
```

Access: http://localhost:3000

**Credentials:**
- Username: `admin`
- Password: Get with:
  ```powershell
  kubectl get secret prometheus-grafana -n prometheus -o jsonpath="{.data.admin-password}" | ForEach-Object { [System.Text.Encoding]::UTF8.GetString([System.Convert]::FromBase64String($_)) }
  ```

## Troubleshooting kubectl Connection

### Check Current Configuration

```powershell
# View current context
kubectl config current-context

# View all contexts
kubectl config get-contexts

# View kubeconfig location
kubectl config view
```

### Fix kubectl Configuration

If kubectl is pointing to wrong server:

```powershell
# List contexts
kubectl config get-contexts

# Switch context
kubectl config use-context CONTEXT_NAME

# Or set server directly
kubectl config set-cluster CLUSTER_NAME --server=https://YOUR_CLUSTER_URL
```

## Next Steps

1. **Set up your Kubernetes cluster** (choose one of the options above)
2. **Verify kubectl connection** with `kubectl cluster-info`
3. **Run the installation script** again
4. **Verify installation** with `kubectl get pods -n prometheus`
5. **Access Grafana and Prometheus** using port-forward commands

## Files Ready

All configuration files are ready in `k8-setup/`:
- ✅ `prometheus-values.yaml` - Helm values
- ✅ `grafana-config.yaml` - Grafana config
- ✅ `grafanaingress.yaml` - Ingress config
- ✅ `fast-api.yaml` - ServiceMonitor

Once your Kubernetes cluster is accessible, the installation will complete successfully.
















