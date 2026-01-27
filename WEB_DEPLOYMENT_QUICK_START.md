# 🌐 Quick Start: Running FastAPI on the Web

## 🚀 Fastest Way: Local Network Access

### Windows (PowerShell)
```powershell
.\start_fastapi_web.ps1
```

Or manually:
```powershell
$env:HOST="0.0.0.0"
python start_fastapi_server.py
```

### Linux/Mac
```bash
./start_fastapi_web.sh
```

Or manually:
```bash
HOST=0.0.0.0 python start_fastapi_server.py
```

**Access from other devices on your network:**
- Find your IP: `ipconfig` (Windows) or `ifconfig` (Linux/Mac)
- Open: `http://YOUR_IP:8000/docs`

---

## 🐳 Docker Deployment (Recommended)

### Option A: Docker Compose (Easiest)

```bash
# Start FastAPI + MLflow together
docker-compose -f docker-compose.fastapi.yml up -d

# View logs
docker-compose -f docker-compose.fastapi.yml logs -f

# Stop
docker-compose -f docker-compose.fastapi.yml down
```

**Access:** `http://localhost:8000` or `http://YOUR_SERVER_IP:8000`

### Option B: Docker Only

```bash
# Build image
docker build -f Dockerfile.fastapi -t fastapi-ml:latest .

# Run container
docker run -d \
  --name fastapi-ml \
  -p 8000:8000 \
  -e MLFLOW_TRACKING_URI=http://host.docker.internal:5000 \
  fastapi-ml:latest

# View logs
docker logs -f fastapi-ml

# Stop
docker stop fastapi-ml
docker rm fastapi-ml
```

---

## ☁️ Cloud Deployment Options

### 1. Kubernetes (You have manifests ready!)

```bash
# Deploy to Kubernetes
kubectl apply -f k8-setup/fastapi-deployment.yaml
kubectl apply -f k8-setup/fastapi-service.yaml

# Check status
kubectl get pods -n platform
kubectl get svc -n platform

# Port forward for local access
kubectl port-forward -n platform svc/fastapi-ml 8000:8000
```

### 2. Heroku

```bash
# Create Procfile
echo "web: python start_fastapi_server.py" > Procfile

# Deploy
heroku create your-app-name
heroku config:set HOST=0.0.0.0 PORT=\$PORT
git push heroku main
```

### 3. AWS / Google Cloud / Azure

1. Launch a VM instance
2. Install dependencies: `pip install -r requirements.txt`
3. Run: `HOST=0.0.0.0 PORT=8000 python start_fastapi_server.py`
4. Open port 8000 in firewall
5. Access: `http://YOUR_VM_IP:8000`

### 4. Quick Public URL (Testing Only)

```bash
# Install ngrok: https://ngrok.com/download
ngrok http 8000
```

**⚠️ Warning**: ngrok URLs are temporary and public. Not for production!

---

## 🔍 Verify It's Working

1. **Health Check**: `http://YOUR_URL/health`
2. **API Docs**: `http://YOUR_URL/docs`
3. **List Models**: `http://YOUR_URL/models`

---

## 🔒 Security Checklist for Production

- [ ] Use HTTPS (reverse proxy with SSL)
- [ ] Add authentication (API keys/OAuth2)
- [ ] Configure CORS if needed
- [ ] Add rate limiting
- [ ] Use environment variables for secrets
- [ ] Configure firewall rules
- [ ] Set up monitoring/logging

---

## 📚 More Details

See `FASTAPI_USAGE_GUIDE.md` for complete documentation.












