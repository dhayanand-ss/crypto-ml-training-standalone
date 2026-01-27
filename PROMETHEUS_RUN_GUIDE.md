# How to Run Prometheus

This guide covers different ways to run Prometheus for monitoring your FastAPI application.

## Option 1: Kubernetes (Recommended for Production)

### Quick Start

```powershell
# Navigate to k8-setup directory
cd k8-setup

# Run the installation script
.\install-prometheus-grafana.ps1
```

### Manual Installation

```powershell
# 1. Add Helm repository
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update

# 2. Create namespace
kubectl create namespace prometheus

# 3. Install Prometheus/Grafana stack
helm upgrade --install prometheus prometheus-community/kube-prometheus-stack `
  -n prometheus `
  --create-namespace `
  -f prometheus-values.yaml

# 4. Apply Grafana configuration
kubectl apply -f grafana-config.yaml
kubectl rollout restart deployment prometheus-grafana -n prometheus

# 5. Configure FastAPI metrics scraping
kubectl apply -f fast-api.yaml
```

### Access Prometheus

```powershell
# Port forward to access Prometheus UI
kubectl port-forward svc/prometheus-kube-prometheus-prometheus -n prometheus 9090:9090
```

Then open: **http://localhost:9090**

### Verify FastAPI Metrics

1. In Prometheus UI, go to **Status → Targets**
2. Look for `fastapi-ml` target
3. Should show state: **UP**

---

## Option 2: Docker Compose (For Local Development)

Add Prometheus to your `docker-compose.fastapi.yml`:

```yaml
version: '3.8'

services:
  fastapi-ml:
    build:
      context: .
      dockerfile: Dockerfile.fastapi
    container_name: fastapi-ml
    ports:
      - "8000:8000"
    environment:
      - PORT=8000
      - HOST=0.0.0.0
      - MLFLOW_TRACKING_URI=http://mlflow:5000
    volumes:
      - ./models:/app/models
      - ./mlruns:/app/mlruns
    networks:
      - fastapi-network

  mlflow:
    image: python:3.10-slim
    container_name: mlflow-server
    command: >
      sh -c "pip install mlflow && 
             mlflow ui --host 0.0.0.0 --port 5000 --backend-store-uri file:///mlruns"
    ports:
      - "5000:5000"
    volumes:
      - ./mlruns:/mlruns
    networks:
      - fastapi-network

  prometheus:
    image: prom/prometheus:latest
    container_name: prometheus
    ports:
      - "9090:9090"
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml
      - prometheus-data:/prometheus
    command:
      - '--config.file=/etc/prometheus/prometheus.yml'
      - '--storage.tsdb.path=/prometheus'
    networks:
      - fastapi-network
    restart: unless-stopped

networks:
  fastapi-network:
    driver: bridge

volumes:
  prometheus-data:
```

### Create Prometheus Configuration

Create `prometheus.yml` in your project root:

```yaml
global:
  scrape_interval: 15s
  evaluation_interval: 15s

scrape_configs:
  - job_name: 'fastapi'
    static_configs:
      - targets: ['fastapi-ml:8000']
    metrics_path: '/metrics'
    scrape_interval: 15s
```

### Run with Docker Compose

```powershell
# Start all services including Prometheus
docker-compose -f docker-compose.fastapi.yml up -d

# View logs
docker-compose -f docker-compose.fastapi.yml logs -f prometheus

# Access Prometheus
# Open: http://localhost:9090
```

---

## Option 3: Standalone Docker (Quick Test)

### Run Prometheus Container

```powershell
# Create prometheus.yml (see above)

# Run Prometheus
docker run -d `
  --name prometheus `
  -p 9090:9090 `
  -v ${PWD}/prometheus.yml:/etc/prometheus/prometheus.yml `
  prom/prometheus:latest
```

### Access Prometheus

Open: **http://localhost:9090**

### Stop Prometheus

```powershell
docker stop prometheus
docker rm prometheus
```

---

## Option 4: Direct Binary (Advanced)

### Download Prometheus

1. Download from: https://prometheus.io/download/
2. Extract the archive
3. Create `prometheus.yml` (see configuration above)

### Run Prometheus

```powershell
# Windows
.\prometheus.exe --config.file=prometheus.yml

# Linux/Mac
./prometheus --config.file=prometheus.yml
```

---

## Prometheus Configuration for FastAPI

Your FastAPI app already exposes metrics at `/metrics` endpoint. Here's a basic `prometheus.yml` configuration:

```yaml
global:
  scrape_interval: 15s      # How often to scrape targets
  evaluation_interval: 15s  # How often to evaluate rules

scrape_configs:
  # FastAPI metrics
  - job_name: 'fastapi'
    static_configs:
      - targets: ['localhost:8000']  # Change to your FastAPI host:port
    metrics_path: '/metrics'
    scrape_interval: 15s
```

### For Docker Compose

```yaml
scrape_configs:
  - job_name: 'fastapi'
    static_configs:
      - targets: ['fastapi-ml:8000']  # Use service name
    metrics_path: '/metrics'
```

### For Kubernetes

Use ServiceMonitor (already configured in `k8-setup/fast-api.yaml`). No manual configuration needed!

---

## Verify Metrics are Working

### 1. Check FastAPI Metrics Endpoint

```powershell
# If FastAPI is running locally
curl http://localhost:8000/metrics

# If FastAPI is in Docker
docker exec fastapi-ml curl http://localhost:8000/metrics

# If FastAPI is in Kubernetes
kubectl exec -it <fastapi-pod> -n platform -- curl http://localhost:8000/metrics
```

You should see Prometheus-formatted metrics like:
```
# HELP http_requests_total Total number of HTTP requests
# TYPE http_requests_total counter
http_requests_total{method="GET",status="200"} 42
```

### 2. Check Prometheus Targets

1. Open Prometheus UI: http://localhost:9090
2. Go to **Status → Targets**
3. Your FastAPI target should show **UP**

### 3. Query Metrics

In Prometheus UI, go to **Graph** and try queries like:
- `http_requests_total` - Total HTTP requests
- `rate(http_requests_total[5m])` - Request rate
- `http_request_duration_seconds` - Request duration

---

## Quick Commands Reference

### Kubernetes

```powershell
# Install
cd k8-setup
.\install-prometheus-grafana.ps1

# Access
kubectl port-forward svc/prometheus-kube-prometheus-prometheus -n prometheus 9090:9090

# Check status
kubectl get pods -n prometheus
kubectl get svc -n prometheus

# View logs
kubectl logs -f deployment/prometheus-kube-prometheus-prometheus -n prometheus
```

### Docker Compose

```powershell
# Start
docker-compose -f docker-compose.fastapi.yml up -d prometheus

# Stop
docker-compose -f docker-compose.fastapi.yml stop prometheus

# Logs
docker-compose -f docker-compose.fastapi.yml logs -f prometheus

# Restart
docker-compose -f docker-compose.fastapi.yml restart prometheus
```

### Standalone Docker

```powershell
# Start
docker run -d --name prometheus -p 9090:9090 -v ${PWD}/prometheus.yml:/etc/prometheus/prometheus.yml prom/prometheus:latest

# Stop
docker stop prometheus && docker rm prometheus

# Logs
docker logs -f prometheus
```

---

## Troubleshooting

### Prometheus Can't Scrape FastAPI

1. **Check FastAPI is running:**
   ```powershell
   curl http://localhost:8000/health
   ```

2. **Check metrics endpoint:**
   ```powershell
   curl http://localhost:8000/metrics
   ```

3. **Verify network connectivity:**
   - For Docker Compose: Ensure services are on the same network
   - For Kubernetes: Check ServiceMonitor configuration
   - For standalone: Ensure Prometheus can reach FastAPI host:port

4. **Check Prometheus targets:**
   - Go to Prometheus UI → Status → Targets
   - Look for error messages

### Prometheus Not Starting

1. **Check configuration file:**
   ```powershell
   # Validate prometheus.yml syntax
   docker run --rm -v ${PWD}/prometheus.yml:/etc/prometheus/prometheus.yml prom/prometheus:latest promtool check config /etc/prometheus/prometheus.yml
   ```

2. **Check logs:**
   ```powershell
   # Docker
   docker logs prometheus
   
   # Kubernetes
   kubectl logs -f deployment/prometheus-kube-prometheus-prometheus -n prometheus
   ```

3. **Check port availability:**
   ```powershell
   # Windows
   netstat -ano | findstr :9090
   
   # Linux/Mac
   lsof -i :9090
   ```

---

## Next Steps

1. **Set up Grafana** for visualization (already included in Kubernetes setup)
2. **Create dashboards** for your ML metrics
3. **Set up alerts** in AlertManager
4. **Configure retention policies** based on your storage needs

For more details, see:
- `k8-setup/KUBERNETES_SETUP_GUIDE.md` - Full Kubernetes setup
- `FASTAPI_USAGE_GUIDE.md` - FastAPI endpoints including `/metrics`











