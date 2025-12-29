# Kubernetes Setup

This directory contains all the Kubernetes configuration files and scripts needed to deploy the FastAPI ML application and monitoring stack.

## Quick Start

### Prerequisites
- Kubernetes cluster (Docker Desktop, Minikube, Kind, or cloud cluster)
- kubectl configured and connected to your cluster
- Helm installed (v3.x)

### One-Command Deployment

```powershell
cd k8-setup
.\quick-start.ps1
```

This will:
1. ✅ Build the Docker image
2. ✅ Create namespaces
3. ✅ Deploy FastAPI application
4. ✅ Install Prometheus & Grafana
5. ✅ Configure metrics monitoring

### Manual Step-by-Step

See **[KUBERNETES_SETUP_GUIDE.md](./KUBERNETES_SETUP_GUIDE.md)** for detailed instructions.

## Files Overview

### Application Deployment
- `fastapi-deployment.yaml` - FastAPI application deployment
- `fastapi-service.yaml` - FastAPI Kubernetes service
- `fast-api.yaml` - ServiceMonitor for Prometheus metrics scraping

### Monitoring Stack
- `prometheus-values.yaml` - Prometheus/Grafana Helm chart values
- `grafana-config.yaml` - Grafana configuration (anonymous access)
- `grafanaingress.yaml` - Grafana Ingress for HTTPS access
- `install-prometheus-grafana.ps1` - Installation script

### Scripts
- `quick-start.ps1` - Automated deployment script
- `install-helm-windows.ps1` - Helm installation for Windows
- `add-helm-to-path.ps1` - Add Helm to PATH
- `install-prometheus-grafana.ps1` - Monitoring stack installer

### Documentation
- `KUBERNETES_SETUP_GUIDE.md` - Complete setup guide
- `INSTALLATION_COMPLETE.md` - Post-installation information
- `INSTALLATION_STATUS.md` - Installation troubleshooting

## Quick Commands

### Deploy Everything
```powershell
.\quick-start.ps1
```

### Deploy Only FastAPI (Skip Monitoring)
```powershell
.\quick-start.ps1 -SkipMonitoring
```

### Deploy with Custom Image Registry
```powershell
.\quick-start.ps1 -ImageRegistry "your-registry.io" -ImageTag "v1.0.0"
```

### Access Services
```powershell
# FastAPI
kubectl port-forward svc/fastapi-ml -n platform 8000:8000
# Open: http://localhost:8000/docs

# Prometheus
kubectl port-forward svc/prometheus-kube-prometheus-prometheus -n prometheus 9090:9090
# Open: http://localhost:9090

# Grafana
kubectl port-forward svc/prometheus-grafana -n prometheus 3000:80
# Open: http://localhost:3000
# Username: admin
# Password: prom-operator (or get with kubectl command)
```

### Check Status
```powershell
# FastAPI
kubectl get pods -n platform
kubectl logs -f deployment/fastapi-ml -n platform

# Monitoring
kubectl get pods -n prometheus
```

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Kubernetes Cluster                    │
├─────────────────────────────────────────────────────────┤
│                                                          │
│  ┌──────────────┐         ┌──────────────────────┐    │
│  │   FastAPI    │────────▶│   Prometheus         │    │
│  │  (platform)  │ Metrics │   (prometheus)       │    │
│  └──────────────┘         └──────────────────────┘    │
│         │                          │                    │
│         │                          │                    │
│         │                          ▼                    │
│         │                  ┌──────────────────────┐    │
│         │                  │   Grafana            │    │
│         │                  │   (prometheus)       │    │
│         │                  └──────────────────────┘    │
│         │                                               │
│         └─────────── Port Forward ────────────────────┘
│                      (localhost:8000)
└─────────────────────────────────────────────────────────┘
```

## Namespaces

- **platform** - FastAPI application
- **prometheus** - Monitoring stack (Prometheus, Grafana, AlertManager)

## Next Steps

1. **Read the full guide**: [KUBERNETES_SETUP_GUIDE.md](./KUBERNETES_SETUP_GUIDE.md)
2. **Configure Ingress** for external access
3. **Set up SSL/TLS** certificates
4. **Create custom Grafana dashboards**
5. **Configure autoscaling** for production

## Troubleshooting

See the troubleshooting section in [KUBERNETES_SETUP_GUIDE.md](./KUBERNETES_SETUP_GUIDE.md) or check:
- Pod logs: `kubectl logs <pod-name> -n <namespace>`
- Pod events: `kubectl describe pod <pod-name> -n <namespace>`
- Service status: `kubectl get all -n <namespace>`

## Support

For issues or questions:
1. Check pod logs and events
2. Verify ServiceMonitor configuration
3. Check Prometheus targets
4. Review the detailed guide











