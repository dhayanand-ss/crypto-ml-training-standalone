# Prometheus & Grafana Installation Complete

## Installation Status

The Prometheus and Grafana monitoring stack has been installed using Helm.

## What Was Installed

1. **kube-prometheus-stack** - Complete monitoring stack including:
   - Prometheus (metrics collection)
   - Grafana (visualization)
   - AlertManager (alerting)
   - Node Exporter (node metrics)
   - Kube State Metrics (Kubernetes metrics)

2. **Grafana Configuration** - Anonymous access enabled
3. **Grafana Ingress** - HTTPS access via `grafana.gokuladethya.uk`
4. **FastAPI ServiceMonitor** - Configured to scrape FastAPI metrics

## Access Information

### Prometheus

**Port Forward:**
```powershell
kubectl port-forward svc/prometheus-kube-prometheus-prometheus -n prometheus 9090:9090
```

**Access:** http://localhost:9090

### Grafana

**Port Forward:**
```powershell
kubectl port-forward svc/prometheus-grafana -n prometheus 3000:80
```

**Access:** http://localhost:3000

**Credentials:**
- Username: `admin`
- Password: Get with:
  ```powershell
  kubectl get secret prometheus-grafana -n prometheus -o jsonpath="{.data.admin-password}" | ForEach-Object { [System.Text.Encoding]::UTF8.GetString([System.Convert]::FromBase64String($_)) }
  ```
- Default: `prom-operator`

**Via Ingress:** https://grafana.gokuladethya.uk (if cert-manager is configured)

## Configuration Details

### Prometheus

- **Namespace:** `prometheus`
- **ServiceMonitor Discovery:** Enabled across all namespaces
- **Retention:** 15 days
- **Storage:** 50Gi PVC

### Grafana

- **Namespace:** `prometheus`
- **Anonymous Access:** Enabled (Viewer role)
- **Domain:** `grafana.gokuladethya.uk`
- **Storage:** 10Gi PVC

### FastAPI ServiceMonitor

- **Namespace:** `platform`
- **Service Label:** `app: fastapi-ml`
- **Port:** `fastapi-custom-port`
- **Scrape Interval:** 15 seconds
- **Metrics Path:** `/metrics`

## Next Steps

### 1. Verify Installation

Check if pods are running:
```powershell
kubectl get pods -n prometheus
```

All pods should be in `Running` state.

### 2. Configure Grafana Data Source

1. Access Grafana UI
2. Go to **Configuration → Data Sources**
3. Click **Add data source**
4. Select **Prometheus**
5. URL: `http://prometheus-kube-prometheus-prometheus.prometheus.svc.cluster.local:9090`
6. Click **Save & Test**

### 3. Verify FastAPI Metrics

Check if Prometheus is scraping FastAPI:
1. Access Prometheus UI
2. Go to **Status → Targets**
3. Look for `fastapi-ml` target
4. Should show state: **UP**

### 4. Import Dashboards

In Grafana:
1. Go to **Dashboards → Import**
2. Import these dashboards:
   - **NGINX Ingress Controller** (ID: 9614)
   - **Kubernetes Cluster Monitoring** (ID: 7249)
   - Create custom FastAPI dashboard

### 5. Create Custom Dashboards

Create dashboards for:
- FastAPI request rates
- ML model prediction latency
- Model prediction counts
- Error rates

## Troubleshooting

### Pods Not Starting

```powershell
# Check pod status
kubectl get pods -n prometheus

# Check pod logs
kubectl logs <pod-name> -n prometheus

# Check events
kubectl get events -n prometheus --sort-by='.lastTimestamp'
```

### Prometheus Not Scraping FastAPI

1. **Verify ServiceMonitor exists:**
   ```powershell
   kubectl get servicemonitor -n platform
   ```

2. **Check service labels:**
   ```powershell
   kubectl get svc -n platform -l app=fastapi-ml
   ```

3. **Check Prometheus targets:**
   - Access Prometheus UI → Status → Targets
   - Look for errors

### Grafana Cannot Connect to Prometheus

1. **Check Prometheus service:**
   ```powershell
   kubectl get svc -n prometheus | grep prometheus
   ```

2. **Verify data source URL:**
   - Should be: `http://prometheus-kube-prometheus-prometheus.prometheus.svc.cluster.local:9090`

### Metrics Not Appearing

1. **Check if FastAPI exposes metrics:**
   ```powershell
   kubectl exec -it <fastapi-pod> -n platform -- curl http://localhost:8000/metrics
   ```

2. **Query metrics in Prometheus:**
   - Prometheus UI → Graph
   - Query: `up{job="fastapi-ml"}`

## Useful Commands

### Check Installation Status

```powershell
# List Helm releases
helm list -n prometheus

# Check all resources
kubectl get all -n prometheus

# Check ServiceMonitors
kubectl get servicemonitor -A
```

### Get Grafana Password

```powershell
kubectl get secret prometheus-grafana -n prometheus -o jsonpath="{.data.admin-password}" | ForEach-Object { [System.Text.Encoding]::UTF8.GetString([System.Convert]::FromBase64String($_)) }
```

### Restart Services

```powershell
# Restart Grafana
kubectl rollout restart deployment prometheus-grafana -n prometheus

# Restart Prometheus
kubectl rollout restart statefulset prometheus-prometheus-kube-prometheus-prometheus -n prometheus
```

### View Logs

```powershell
# Grafana logs
kubectl logs -f deployment/prometheus-grafana -n prometheus

# Prometheus logs
kubectl logs -f statefulset/prometheus-prometheus-kube-prometheus-prometheus -n prometheus
```

## Files Created

- `prometheus-values.yaml` - Helm values configuration
- `grafana-config.yaml` - Grafana ConfigMap
- `grafanaingress.yaml` - NGINX Ingress for Grafana
- `fast-api.yaml` - ServiceMonitor for FastAPI

## References

- [Prometheus Documentation](https://prometheus.io/docs/)
- [Grafana Documentation](https://grafana.com/docs/)
- [kube-prometheus-stack](https://github.com/prometheus-community/helm-charts/tree/main/charts/kube-prometheus-stack)

## Support

If you encounter issues:
1. Check pod logs
2. Verify ServiceMonitor configuration
3. Check Prometheus targets
4. Verify network connectivity between services
















