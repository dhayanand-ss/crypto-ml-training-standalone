# What is the Function of Prometheus in This Project?

## Overview

Prometheus is a **monitoring and metrics collection system** that continuously scrapes, stores, and queries metrics from your FastAPI ML inference service. It acts as the **observability layer** for your machine learning application.

---

## Primary Functions

### 1. **Metrics Collection** 📊

Prometheus automatically collects metrics from your FastAPI application every 15 seconds (configurable). Your FastAPI app exposes metrics at the `/metrics` endpoint, and Prometheus scrapes this endpoint to gather data.

**What metrics are collected:**

#### **ML Model Metrics** (Custom metrics from your FastAPI app):
- **`ml_predictions_total`** - Total number of predictions made
  - Labels: `model_name`, `version`, `status` (success/error)
  - Example: Track how many predictions each model has made

- **`ml_predictions_duration_seconds`** - Prediction latency/response time
  - Labels: `model_name`, `version`
  - Example: Monitor how fast your models are making predictions

- **`ml_model_load_errors_total`** - Number of model loading failures
  - Labels: `model_name`, `version`
  - Example: Track when models fail to load from MLflow

- **`ml_active_models`** - Number of models currently loaded in memory
  - Labels: `model_name`, `version`
  - Example: Monitor which models are active and ready for inference

#### **HTTP Metrics** (Automatic from FastAPI Instrumentator):
- Request counts by method, status code, endpoint
- Request duration/latency
- Response sizes
- Active connections

---

### 2. **Time-Series Data Storage** 💾

Prometheus stores all collected metrics as **time-series data**, meaning:
- Each metric is stored with a timestamp
- You can query historical data (e.g., "How many predictions were made in the last hour?")
- Data is retained for 15 days (configurable in `prometheus-values.yaml`)

**Example queries you can run:**
```promql
# Total predictions in last hour
rate(ml_predictions_total[1h])

# Average prediction latency
avg(ml_predictions_duration_seconds)

# Error rate
rate(ml_predictions_total{status="error"}[5m])
```

---

### 3. **Monitoring & Alerting** 🚨

Prometheus enables you to:
- **Monitor** your ML service health in real-time
- **Set up alerts** when things go wrong (via AlertManager)
- **Track performance** trends over time
- **Identify issues** before they become critical

**Example monitoring scenarios:**
- Alert when prediction error rate exceeds 5%
- Alert when model load failures occur
- Alert when prediction latency exceeds 1 second
- Monitor model usage patterns

---

### 4. **Integration with Grafana** 📈

Prometheus serves as the **data source** for Grafana dashboards:
- Grafana queries Prometheus to create visual dashboards
- You can create graphs, charts, and visualizations of your ML metrics
- Real-time monitoring dashboards for your team

**Example dashboards you can create:**
- Prediction throughput over time
- Model latency distribution
- Error rates by model
- Active models status
- API request patterns

---

## How It Works in Your Project

### Architecture Flow

```
┌─────────────────┐         ┌──────────────┐         ┌─────────────┐
│   FastAPI App   │────────▶│  /metrics    │◀────────│ Prometheus   │
│  (Port 8000)    │ Exposes │   Endpoint   │ Scrapes │ (Port 9090)  │
└─────────────────┘         └──────────────┘         └─────────────┘
       │                                                      │
       │                                                      │
       │ Collects metrics:                                   │ Stores &
       │ - Prediction counts                                 │ Queries
       │ - Latencies                                         │ metrics
       │ - Model status                                      │
       │ - HTTP requests                                     │
       │                                                      ▼
       │                                              ┌─────────────┐
       │                                              │   Grafana   │
       │                                              │ (Port 3000) │
       │                                              │  Dashboards │
       └─────────────────────────────────────────────▶└─────────────┘
```

### Step-by-Step Process

1. **FastAPI Application** runs and serves ML models
2. **Metrics are generated** automatically:
   - Every prediction increments `ml_predictions_total`
   - Every prediction records latency in `ml_predictions_duration_seconds`
   - Model loads/errors update respective counters
3. **FastAPI exposes metrics** at `http://localhost:8000/metrics`
4. **Prometheus scrapes** the `/metrics` endpoint every 15 seconds
5. **Prometheus stores** the metrics in its time-series database
6. **You can query** metrics via Prometheus UI or Grafana dashboards

---

## Real-World Use Cases

### 1. **Performance Monitoring**
- Track which models are being used most
- Monitor prediction latency to ensure fast responses
- Identify slow models that need optimization

### 2. **Reliability Monitoring**
- Detect when models fail to load
- Track error rates per model
- Monitor service availability

### 3. **Capacity Planning**
- Understand prediction volume trends
- Plan for scaling based on usage patterns
- Identify peak usage times

### 4. **Debugging & Troubleshooting**
- Investigate why predictions are slow
- Identify which models are causing errors
- Track model refresh operations

### 5. **Business Intelligence**
- Track model usage statistics
- Monitor API usage patterns
- Generate reports on model performance

---

## Example Metrics You Can Track

### Prediction Metrics
```promql
# Total predictions per model
sum(ml_predictions_total) by (model_name)

# Success rate
sum(rate(ml_predictions_total{status="success"}[5m])) / 
sum(rate(ml_predictions_total[5m]))

# Average latency per model
avg(ml_predictions_duration_seconds) by (model_name)

# 95th percentile latency
histogram_quantile(0.95, ml_predictions_duration_seconds)
```

### Model Health Metrics
```promql
# Active models count
sum(ml_active_models)

# Model load errors
sum(rate(ml_model_load_errors_total[5m])) by (model_name)
```

### API Metrics
```promql
# Request rate
rate(http_requests_total[5m])

# Error rate
rate(http_requests_total{status=~"5.."}[5m])
```

---

## Why Prometheus is Important for ML Services

1. **Visibility**: You can't improve what you can't measure
2. **Reliability**: Catch issues before they impact users
3. **Performance**: Identify bottlenecks and optimize
4. **Debugging**: Understand what happened when things go wrong
5. **Compliance**: Track model usage and performance for auditing

---

## Configuration in Your Project

### FastAPI Side (Already Configured)
- ✅ Metrics exposed at `/metrics` endpoint
- ✅ Custom ML metrics defined (predictions, latency, errors)
- ✅ Automatic HTTP metrics via `prometheus-fastapi-instrumentator`

### Prometheus Side
- ✅ Configured to scrape FastAPI every 15 seconds
- ✅ ServiceMonitor configured in Kubernetes (`k8-setup/fast-api.yaml`)
- ✅ 15-day data retention
- ✅ Integrated with Grafana for visualization

---

## Summary

**Prometheus in your project:**
- ✅ **Collects** metrics from your FastAPI ML service
- ✅ **Stores** time-series data for historical analysis
- ✅ **Enables** monitoring and alerting
- ✅ **Powers** Grafana dashboards for visualization
- ✅ **Tracks** ML-specific metrics (predictions, latency, errors, model status)
- ✅ **Monitors** API health and performance

**Without Prometheus**, you would have:
- ❌ No visibility into model performance
- ❌ No way to track prediction patterns
- ❌ No alerts when things go wrong
- ❌ No historical data for analysis
- ❌ No dashboards for monitoring

**With Prometheus**, you have:
- ✅ Complete observability of your ML service
- ✅ Real-time and historical metrics
- ✅ Ability to create alerts and dashboards
- ✅ Data-driven insights for optimization

---

## Next Steps

1. **Run Prometheus** (see `PROMETHEUS_RUN_GUIDE.md`)
2. **Access Prometheus UI** at http://localhost:9090
3. **Query metrics** to explore your data
4. **Set up Grafana** for visual dashboards
5. **Create alerts** for critical metrics

For more details, see:
- `PROMETHEUS_RUN_GUIDE.md` - How to run Prometheus
- `k8-setup/KUBERNETES_SETUP_GUIDE.md` - Full setup guide
- `FASTAPI_USAGE_GUIDE.md` - FastAPI endpoints
















