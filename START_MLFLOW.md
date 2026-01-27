# How to Start MLflow Server

## Quick Start (Simplest Method)

### Windows PowerShell
```powershell
mlflow ui --port 5000
```

### Windows Command Prompt
```cmd
mlflow ui --port 5000
```

### Linux/Mac
```bash
mlflow ui --port 5000
```

This will start MLflow UI at: **http://localhost:5000**

---

## Installation Check

First, make sure MLflow is installed:
```bash
pip install mlflow
```

Or if using your project requirements:
```bash
pip install -r requirements.txt
```

---

## Starting MLflow Server

### Option 1: Basic UI (File-based Backend)
**Default behavior** - stores data in local `./mlruns` directory

```bash
mlflow ui --port 5000
```

**Access at:** http://localhost:5000

---

### Option 2: With Custom Backend Store (SQLite)
Better for production - uses SQLite database

```bash
mlflow ui --port 5000 --backend-store-uri sqlite:///mlflow.db
```

---

### Option 3: With PostgreSQL Backend (Production)
For production use with PostgreSQL:

```bash
mlflow ui --port 5000 --backend-store-uri postgresql://user:password@localhost:5432/mlflow
```

---

### Option 4: With Custom Artifact Store
If you want to store artifacts in a specific location:

```bash
mlflow ui --port 5000 --default-artifact-root ./mlflow-artifacts
```

---

## Windows-Specific Instructions

### Run in Background (PowerShell)
To keep MLflow running in the background:

```powershell
Start-Process powershell -ArgumentList "-NoExit", "-Command", "mlflow ui --port 5000"
```

### Run in Background (Command Prompt)
```cmd
start cmd /k "mlflow ui --port 5000"
```

### Check if Port 5000 is Available
```powershell
netstat -ano | findstr :5000
```

If port is in use, use a different port:
```powershell
mlflow ui --port 5001
```

Then update your FastAPI environment variable:
```powershell
$env:MLFLOW_TRACKING_URI="http://localhost:5001"
```

---

## Verify MLflow is Running

1. **Open browser:** http://localhost:5000
2. **You should see:** MLflow UI with experiments and models
3. **Check FastAPI connection:**
   ```powershell
   # In another terminal, start FastAPI
   python start_fastapi_server.py
   
   # Then check debug endpoint
   # Open: http://localhost:8000/debug/mlflow
   ```

---

## Common Options

### Full Command with All Options
```bash
mlflow ui \
  --port 5000 \
  --host 0.0.0.0 \
  --backend-store-uri sqlite:///mlflow.db \
  --default-artifact-root ./mlflow-artifacts
```

### Options Explained:
- `--port 5000`: Port to run MLflow UI (default: 5000)
- `--host 0.0.0.0`: Allow access from other machines (default: 127.0.0.1)
- `--backend-store-uri`: Database for storing experiments/models
- `--default-artifact-root`: Where to store model artifacts

---

## Setting Environment Variable

After starting MLflow, ensure FastAPI knows where to find it:

### Windows PowerShell
```powershell
$env:MLFLOW_TRACKING_URI="http://localhost:5000"
python start_fastapi_server.py
```

### Windows Command Prompt
```cmd
set MLFLOW_TRACKING_URI=http://localhost:5000
python start_fastapi_server.py
```

### Linux/Mac
```bash
export MLFLOW_TRACKING_URI=http://localhost:5000
python start_fastapi_server.py
```

---

## Troubleshooting

### Port Already in Use
If port 5000 is busy:
```bash
# Use different port
mlflow ui --port 5001

# Update FastAPI
$env:MLFLOW_TRACKING_URI="http://localhost:5001"
```

### MLflow Not Found
```bash
pip install mlflow
```

### Connection Refused
- Make sure MLflow server is running
- Check firewall settings
- Verify the port matches `MLFLOW_TRACKING_URI`

### No Models Showing
- Models need to be registered first (run training)
- Check that models are in "Production" stage
- Verify models have ONNX artifacts

---

## Running MLflow as a Service (Windows)

### Create a Batch File: `start_mlflow.bat`
```batch
@echo off
echo Starting MLflow Server...
mlflow ui --port 5000 --host 0.0.0.0
pause
```

### Create a PowerShell Script: `start_mlflow.ps1`
```powershell
Write-Host "Starting MLflow Server on port 5000..."
mlflow ui --port 5000 --host 0.0.0.0
```

Run it:
```powershell
.\start_mlflow.ps1
```

---

## Quick Reference

| Command | Description |
|---------|-------------|
| `mlflow ui` | Start MLflow UI (default port 5000) |
| `mlflow ui --port 5001` | Start on custom port |
| `mlflow ui --host 0.0.0.0` | Allow external access |
| `mlflow ui --backend-store-uri sqlite:///mlflow.db` | Use SQLite backend |

---

## Next Steps

1. **Start MLflow:** `mlflow ui --port 5000`
2. **Verify:** Open http://localhost:5000 in browser
3. **Start FastAPI:** `python start_fastapi_server.py`
4. **Check connection:** http://localhost:8000/debug/mlflow
5. **List models:** http://localhost:8000/models












