# FastAPI Results Viewing Guide

## Quick Start

### 1. Start the FastAPI Server

```bash
python start_fastapi_server.py
```

Or set custom host/port:
```bash
# Windows PowerShell
$env:PORT=8000
$env:HOST="127.0.0.1"
python start_fastapi_server.py

# Or Linux/Mac
PORT=8000 HOST=127.0.0.1 python start_fastapi_server.py
```

The server will start at: `http://127.0.0.1:8000`

---

## 🌐 Running on the Web

### Option 1: Local Network Access (Same Network)

To make the server accessible on your local network (e.g., from other devices on your WiFi):

**Windows PowerShell:**
```powershell
$env:PORT=8000
$env:HOST="0.0.0.0"  # Listen on all network interfaces
python start_fastapi_server.py
```

**Linux/Mac:**
```bash
PORT=8000 HOST=0.0.0.0 python start_fastapi_server.py
```

**Find your IP address:**
- **Windows**: `ipconfig` (look for IPv4 Address)
- **Linux/Mac**: `ifconfig` or `ip addr` (look for inet address)

Then access from other devices: `http://YOUR_IP_ADDRESS:8000`

**⚠️ Security Note**: This exposes your server to your local network. For production, use proper authentication and HTTPS.

---

### Option 2: Docker Deployment

Create a `Dockerfile.fastapi` for the FastAPI service:

```dockerfile
FROM python:3.10-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy project files
COPY . .

# Set environment variables
ENV PYTHONPATH=/app
ENV PORT=8000
ENV HOST=0.0.0.0
ENV MLFLOW_TRACKING_URI=http://localhost:5000

# Expose port
EXPOSE 8000

# Run FastAPI server
CMD ["python", "start_fastapi_server.py"]
```

**Build and run:**
```bash
# Build the image
docker build -f Dockerfile.fastapi -t fastapi-ml:latest .

# Run the container
docker run -d \
  --name fastapi-ml \
  -p 8000:8000 \
  -e MLFLOW_TRACKING_URI=http://host.docker.internal:5000 \
  fastapi-ml:latest
```

**Access**: `http://localhost:8000` or `http://YOUR_SERVER_IP:8000`

---

### Option 3: Docker Compose (Recommended for Development)

Add to your `docker-compose.yml` or create `docker-compose.fastapi.yml`:

```yaml
version: '3.8'

services:
  fastapi-ml:
    build:
      context: .
      dockerfile: Dockerfile.fastapi
    ports:
      - "8000:8000"
    environment:
      - PORT=8000
      - HOST=0.0.0.0
      - MLFLOW_TRACKING_URI=http://mlflow:5000
    volumes:
      - ./models:/app/models
      - ./mlruns:/app/mlruns
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3

  mlflow:
    image: python:3.10-slim
    command: mlflow ui --host 0.0.0.0 --port 5000
    ports:
      - "5000:5000"
    volumes:
      - ./mlruns:/mlruns
    environment:
      - MLFLOW_BACKEND_STORE_URI=file:///mlruns
```

**Run:**
```bash
docker-compose -f docker-compose.fastapi.yml up -d
```

---

### Option 4: Cloud Deployment

#### A. Deploy to Kubernetes (Production)

You already have Kubernetes manifests in `k8-setup/`. Deploy with:

```bash
# Apply deployment
kubectl apply -f k8-setup/fastapi-deployment.yaml

# Apply service
kubectl apply -f k8-setup/fastapi-service.yaml

# Check status
kubectl get pods -n platform
kubectl get svc -n platform
```

**Expose with Ingress** (create `fastapi-ingress.yaml`):
```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: fastapi-ml-ingress
  namespace: platform
spec:
  rules:
  - host: your-domain.com
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: fastapi-ml
            port:
              number: 8000
```

#### B. Deploy to Cloud Platforms

**Heroku:**
```bash
# Create Procfile
echo "web: python start_fastapi_server.py" > Procfile

# Deploy
heroku create your-app-name
heroku config:set HOST=0.0.0.0 PORT=$PORT
git push heroku main
```

**AWS EC2 / Google Cloud / Azure VM:**
1. Launch a VM instance
2. Install Python and dependencies
3. Run: `HOST=0.0.0.0 PORT=8000 python start_fastapi_server.py`
4. Configure firewall to allow port 8000
5. Access via: `http://YOUR_VM_IP:8000`

**AWS ECS / Google Cloud Run / Azure Container Instances:**
- Use the Dockerfile from Option 2
- Push to container registry
- Deploy as containerized service

#### C. Use a Reverse Proxy (Nginx/Traefik)

For production, use Nginx as reverse proxy with HTTPS:

**nginx.conf:**
```nginx
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

**With SSL (Let's Encrypt):**
```bash
# Install certbot
sudo apt-get install certbot python3-certbot-nginx

# Get SSL certificate
sudo certbot --nginx -d your-domain.com
```

---

### Option 5: Use ngrok (Quick Public Access)

For quick testing with public URL:

```bash
# Install ngrok: https://ngrok.com/download

# Start your FastAPI server
python start_fastapi_server.py

# In another terminal, expose it
ngrok http 8000
```

This gives you a public URL like: `https://abc123.ngrok.io`

**⚠️ Warning**: ngrok URLs are temporary and public. Don't use for production!

---

## 🔒 Security Considerations for Web Deployment

1. **Authentication**: Add API keys or OAuth2
2. **HTTPS**: Always use HTTPS in production (use reverse proxy)
3. **Rate Limiting**: Add rate limiting to prevent abuse
4. **CORS**: Configure CORS if accessing from web browsers
5. **Firewall**: Only expose necessary ports
6. **Environment Variables**: Don't commit secrets to git

---

## Available Endpoints

### 📚 **Interactive API Documentation (Swagger UI)**
**Best way to explore and test the API!**

- **URL**: `http://127.0.0.1:8000/docs`
- **Description**: Interactive Swagger UI where you can:
  - See all available endpoints
  - Test endpoints directly in the browser
  - View request/response schemas
  - Try out predictions with a user-friendly interface

**Alternative Docs**: `http://127.0.0.1:8000/redoc` (ReDoc format)

---

### 🏥 **Health Check**
Check if the server is running and how many models are loaded.

**GET** `http://127.0.0.1:8000/health`

**Response:**
```json
{
  "status": "healthy",
  "models_loaded": 3,
  "onnxruntime_available": true,
  "prometheus_available": true
}
```

**Browser**: Just open `http://127.0.0.1:8000/health` in your browser

**cURL:**
```bash
curl http://127.0.0.1:8000/health
```

---

### 📋 **List All Loaded Models**
See what models are currently loaded and ready for predictions.

**GET** `http://127.0.0.1:8000/models`

**Response:**
```json
[
  {
    "model_name": "BTCUSDT_lightgbm",
    "version": "1",
    "loaded": true,
    "input_shape": [null, 50],
    "output_shape": [null, 3]
  },
  {
    "model_name": "BTCUSDT_tst",
    "version": "1",
    "loaded": true,
    "input_shape": [null, 50],
    "output_shape": [null, 3]
  }
]
```

**Browser**: Open `http://127.0.0.1:8000/models`

**cURL:**
```bash
curl http://127.0.0.1:8000/models
```

---

### 🔮 **Make Predictions**
Get predictions from your models.

**POST** `http://127.0.0.1:8000/predict?model_name=BTCUSDT_lightgbm&version=0`

**Request Body** (JSON):
```json
[
  [0.1, 0.2, 0.3, ...],  // Feature vector 1
  [0.4, 0.5, 0.6, ...]   // Feature vector 2
]
```

**Response:**
```json
{
  "predictions": [
    [0.1, 0.7, 0.2],  // Prediction probabilities for sample 1
    [0.3, 0.5, 0.2]   // Prediction probabilities for sample 2
  ]
}
```

**Note**: `version` is 0-indexed (0 = v1, 1 = v2, etc.)

**Using Swagger UI** (Recommended):
1. Go to `http://127.0.0.1:8000/docs`
2. Click on `/predict` endpoint
3. Click "Try it out"
4. Enter model_name and version as query parameters
5. Enter features in the request body
6. Click "Execute"

**Using cURL:**
```bash
curl -X POST "http://127.0.0.1:8000/predict?model_name=BTCUSDT_lightgbm&version=0" \
  -H "Content-Type: application/json" \
  -d "[[0.1, 0.2, 0.3, 0.4, 0.5]]"
```

**Using Python:**
```python
import requests

response = requests.post(
    "http://127.0.0.1:8000/predict",
    params={"model_name": "BTCUSDT_lightgbm", "version": 0},
    json=[[0.1, 0.2, 0.3, 0.4, 0.5]]  # Your feature vectors
)
print(response.json())
```

---

### 🔄 **Refresh Models**
Reload models from MLflow (useful after new training).

**POST** `http://127.0.0.1:8000/refresh`

**Request Body** (JSON):
```json
{
  "model_name": null,  // null = refresh all models
  "version": null      // null = load latest production version
}
```

Or refresh a specific model:
```json
{
  "model_name": "BTCUSDT_lightgbm",
  "version": null  // null = latest production version
}
```

**Response:**
```json
{
  "status": "models loaded",
  "models": {
    "BTCUSDT_lightgbm": [[1, 1]],
    "BTCUSDT_tst": [[2, 2]]
  }
}
```

**Using Swagger UI**: Go to `/docs`, find `/refresh`, click "Try it out"

**Using cURL:**
```bash
curl -X POST "http://127.0.0.1:8000/refresh" \
  -H "Content-Type: application/json" \
  -d '{"model_name": null, "version": null}'
```

---

### ✅ **Check Model Availability**
Check if a specific model version is available.

**POST** `http://127.0.0.1:8000/is_model_available`

**Request Body** (JSON):
```json
{
  "model_name": "BTCUSDT_lightgbm",
  "version": 0  // 0-indexed: 0 = v1, 1 = v2, etc.
}
```

**Response:**
```json
{
  "available": true
}
```

---

### 📊 **Prometheus Metrics**
View metrics for monitoring (prediction counts, latencies, etc.).

**GET** `http://127.0.0.1:8000/metrics`

**Browser**: Open `http://127.0.0.1:8000/metrics`

**cURL:**
```bash
curl http://127.0.0.1:8000/metrics
```

---

### 🔍 **Debug MLflow Connection**
**Diagnose why no models are loaded** - Check MLflow connection, registered models, and production models.

**GET** `http://127.0.0.1:8000/debug/mlflow`

**Response includes:**
- MLflow tracking URI
- Connection status
- All registered models
- Production models with ONNX availability
- Any errors encountered

**Browser**: Open `http://127.0.0.1:8000/debug/mlflow`

**cURL:**
```bash
curl http://127.0.0.1:8000/debug/mlflow
```

**Example response:**
```json
{
  "mlflow_tracking_uri": "http://localhost:5000",
  "mlflow_available": true,
  "connection_status": "connected",
  "registered_models": [
    {"name": "BTCUSDT_lightgbm", "latest_versions": 3}
  ],
  "production_models": [
    {
      "name": "BTCUSDT_lightgbm",
      "version": "1",
      "stage": "Production",
      "source": "runs:/abc123/BTCUSDT_lightgbm",
      "onnx_available": true
    }
  ],
  "errors": []
}
```

---

## Quick Testing Workflow

1. **Start the server**: `python start_fastapi_server.py`

2. **Check health**: Open `http://127.0.0.1:8000/health` in browser
   - Verify `models_loaded > 0`

3. **List models**: Open `http://127.0.0.1:8000/models` in browser
   - See what models are available

4. **Test predictions**: Go to `http://127.0.0.1:8000/docs`
   - Use the interactive Swagger UI to test `/predict` endpoint
   - Enter your feature vectors and get predictions

5. **Refresh if needed**: Use `/refresh` endpoint if you've trained new models

---

## Troubleshooting

### No models loaded?
**First, use the debug endpoint to diagnose:**
1. Open `http://127.0.0.1:8000/debug/mlflow` in your browser
2. Check the response for:
   - `connection_status`: Should be "connected"
   - `registered_models`: Lists all models in MLflow
   - `production_models`: Lists models in Production stage
   - `errors`: Any issues found

**Common issues and fixes:**

1. **MLflow not running or not accessible**
   - Check if MLflow server is running: `mlflow ui --port 5000`
   - Verify `MLFLOW_TRACKING_URI` environment variable is correct
   - Default: `http://localhost:5000`

2. **No models registered in MLflow**
   - Models need to be trained and registered first
   - Run your training DAGs to register models
   - Or manually register models using `ModelManager.save_model()`

3. **Models not in "Production" stage**
   - FastAPI only loads models in "Production" stage
   - Use `ModelManager.set_production()` to set models to Production
   - Or manually transition in MLflow UI

4. **Models don't have ONNX versions**
   - FastAPI requires ONNX models for inference
   - Ensure training saves ONNX models: `save_model(..., onnx_model=onnx_model)`
   - Check `onnx_available` in debug endpoint response

5. **Wrong MLflow tracking URI**
   - Set environment variable: `export MLFLOW_TRACKING_URI=http://your-mlflow-server:5000`
   - Or set in code before starting FastAPI

**After fixing issues:**
- Use `/refresh` endpoint to reload models
- Check `/models` endpoint to verify models are loaded

### Can't connect to server?
- Check if server is running: `python start_fastapi_server.py`
- Verify port 8000 is not in use
- Check firewall settings

### Model not found?
- Check `/models` endpoint to see what's loaded
- Verify model name and version are correct
- Use `/is_model_available` to check if model exists
- Try `/refresh` to reload from MLflow

---

## Environment Variables

- `PORT`: Server port (default: 8000)
- `HOST`: Server host (default: 127.0.0.1)
- `MLFLOW_TRACKING_URI`: MLflow server URI (default: http://localhost:5000)

