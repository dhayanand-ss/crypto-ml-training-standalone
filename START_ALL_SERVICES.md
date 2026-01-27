# How to Start All Services Simultaneously

This guide shows you how to start FastAPI, MLflow, Prometheus, and Grafana all at once.

## Option 1: Docker Compose (Recommended) 🐳

This is the easiest way to start everything together.

### Quick Start

```powershell
# Start all services
.\start-all-services.ps1
```

Or manually:

```powershell
# Start all services
docker-compose -f docker-compose.full.yml up -d

# View logs
docker-compose -f docker-compose.full.yml logs -f

# Stop all services
docker-compose -f docker-compose.full.yml down
```

### What Gets Started

| Service | Port | URL | Description |
|---------|------|-----|-------------|
| **FastAPI** | 8000 | http://localhost:8000 | ML inference API |
| **MLflow** | 5000 | http://localhost:5000 | Model registry UI |
| **Prometheus** | 9090 | http://localhost:9090 | Metrics collection |
| **Grafana** | 3000 | http://localhost:3000 | Metrics visualization |

### Verify Services

1. **FastAPI Health Check:**
   ```powershell
   curl http://localhost:8000/health
   ```

2. **Check Prometheus Targets:**
   - Open: http://localhost:9090/targets
   - Look for `fastapi-ml` target
   - Should show state: **UP**

3. **Access Grafana:**
   - Open: http://localhost:3000
   - Login: `admin` / `admin`
   - Prometheus data source is pre-configured

---

## Option 2: Standalone (Without Docker) 💻

If you prefer to run services directly on your machine:

```powershell
# Start all services in separate windows
.\start-all-standalone.ps1
```

This will:
- Start MLflow in one PowerShell window
- Start FastAPI in another PowerShell window
- Start Prometheus in another window (if installed)

**Note:** You need to have Prometheus installed locally for this option.

---

## Option 3: Kubernetes (Production) ☸️

For production deployments in Kubernetes:

```powershell
# 1. Install Prometheus & Grafana stack
cd k8-setup
.\install-prometheus-grafana.ps1

# 2. Deploy FastAPI
kubectl apply -f fastapi-deployment.yaml
kubectl apply -f fastapi-service.yaml

# 3. Configure Prometheus to scrape FastAPI
kubectl apply -f fast-api.yaml

# 4. Port forward to access services
kubectl port-forward svc/fastapi-ml -n platform 8000:8000
kubectl port-forward svc/prometheus-kube-prometheus-prometheus -n prometheus 9090:9090
kubectl port-forward svc/prometheus-grafana -n prometheus 3000:80
```

---

## Service Dependencies

Services start in this order:

1. **MLflow** (no dependencies)
2. **FastAPI** (depends on MLflow)
3. **Prometheus** (depends on FastAPI)
4. **Grafana** (depends on Prometheus)

Docker Compose handles dependencies automatically with `depends_on`.

---

## Troubleshooting

### Services Not Starting

1. **Check Docker is running:**
   ```powershell
   docker ps
   ```

2. **Check service logs:**
   ```powershell
   docker-compose -f docker-compose.full.yml logs fastapi-ml
   docker-compose -f docker-compose.full.yml logs prometheus
   ```

3. **Check port conflicts:**
   ```powershell
   # Check if ports are in use
   netstat -ano | findstr ":8000"
   netstat -ano | findstr ":5000"
   netstat -ano | findstr ":9090"
   netstat -ano | findstr ":3000"
   ```

### Prometheus Not Scraping FastAPI

1. **Verify FastAPI metrics endpoint:**
   ```powershell
   curl http://localhost:8000/metrics
   ```

2. **Check Prometheus targets:**
   - Open: http://localhost:9090/targets
   - Look for errors in the target status

3. **Verify prometheus.yml configuration:**
   - Check that `targets: ['fastapi-ml:8000']` matches your Docker service name

### Grafana Cannot Connect to Prometheus

1. **Verify Prometheus is running:**
   ```powershell
   curl http://localhost:9090/-/healthy
   ```

2. **Check Grafana data source:**
   - Go to: http://localhost:3000 → Configuration → Data Sources
   - URL should be: `http://prometheus:9090` (Docker service name)

---

## Quick Commands Reference

### Docker Compose

```powershell
# Start all
docker-compose -f docker-compose.full.yml up -d

# Stop all
docker-compose -f docker-compose.full.yml down

# Restart all
docker-compose -f docker-compose.full.yml restart

# View logs
docker-compose -f docker-compose.full.yml logs -f

# View specific service logs
docker-compose -f docker-compose.full.yml logs -f fastapi-ml
docker-compose -f docker-compose.full.yml logs -f prometheus

# Check status
docker-compose -f docker-compose.full.yml ps
```

### Individual Service Management

```powershell
# Start only FastAPI and MLflow
docker-compose -f docker-compose.fastapi.yml up -d

# Start only Prometheus (standalone)
docker run -d --name prometheus -p 9090:9090 -v ${PWD}/prometheus.yml:/etc/prometheus/prometheus.yml prom/prometheus:latest
```

---

## Next Steps

After starting all services:

1. ✅ **Verify FastAPI is healthy:** http://localhost:8000/health
2. ✅ **Check Prometheus targets:** http://localhost:9090/targets
3. ✅ **Access Grafana:** http://localhost:3000 (admin/admin)
4. ✅ **Configure Grafana dashboards** for your ML metrics
5. ✅ **Test predictions:** http://localhost:8000/docs

---

## Files Created

- `docker-compose.full.yml` - Complete Docker Compose configuration
- `prometheus.yml` - Prometheus scrape configuration
- `start-all-services.ps1` - Automated startup script (Docker)
- `start-all-standalone.ps1` - Automated startup script (Standalone)
- `grafana/provisioning/datasources/prometheus.yml` - Grafana data source config









