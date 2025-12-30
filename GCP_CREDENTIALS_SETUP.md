# GCP Credentials Setup for Airflow

This guide ensures that GCP credentials are properly configured for Airflow to download data from Google Cloud Storage.

## Current Configuration

The `docker-compose.airflow.yml` file is already configured with GCP environment variables:

```yaml
GCP_CREDENTIALS_PATH: ${GCP_CREDENTIALS_PATH:-/opt/airflow/gcp-credentials.json}
GOOGLE_APPLICATION_CREDENTIALS: ${GOOGLE_APPLICATION_CREDENTIALS:-/opt/airflow/gcp-credentials.json}
GCP_PROJECT_ID: ${GCP_PROJECT_ID:-dhaya123-335710}
```

## Setup Methods

### Method 1: Using Environment Variables (Recommended)

Set these environment variables before starting Airflow:

**Windows PowerShell:**
```powershell
$env:GCP_CREDENTIALS_PATH = "C:\Users\dhaya\crypto-ml-training-standalone\dhaya123-335710-039eabaad669.json"
$env:GOOGLE_APPLICATION_CREDENTIALS = "C:\Users\dhaya\crypto-ml-training-standalone\dhaya123-335710-039eabaad669.json"
$env:GCP_PROJECT_ID = "dhaya123-335710"
```

**Windows CMD:**
```cmd
set GCP_CREDENTIALS_PATH=C:\Users\dhaya\crypto-ml-training-standalone\dhaya123-335710-039eabaad669.json
set GOOGLE_APPLICATION_CREDENTIALS=C:\Users\dhaya\crypto-ml-training-standalone\dhaya123-335710-039eabaad669.json
set GCP_PROJECT_ID=dhaya123-335710
```

**Linux/Mac:**
```bash
export GCP_CREDENTIALS_PATH=/path/to/dhaya123-335710-039eabaad669.json
export GOOGLE_APPLICATION_CREDENTIALS=/path/to/dhaya123-335710-039eabaad669.json
export GCP_PROJECT_ID=dhaya123-335710
```

### Method 2: Using .env File

Create a `.env` file in the project root:

```env
GCP_CREDENTIALS_PATH=./dhaya123-335710-039eabaad669.json
GOOGLE_APPLICATION_CREDENTIALS=./dhaya123-335710-039eabaad669.json
GCP_PROJECT_ID=dhaya123-335710
```

Then start Airflow:
```bash
docker-compose -f docker-compose.airflow.yml up -d
```

### Method 3: Default Configuration (Already Set)

The docker-compose file already mounts the credentials file:
- **Local path:** `./dhaya123-335710-039eabaad669.json`
- **Container path:** `/opt/airflow/gcp-credentials.json`

If the credentials file exists in the project root, it will be automatically mounted and used.

## Verification

### Check if credentials file exists:
```powershell
Test-Path "dhaya123-335710-039eabaad669.json"
```

### Verify environment variables in Airflow container:
```bash
docker exec -it <airflow-container> env | grep GCP
```

### Test GCS connection:
```python
from utils.artifact_control import S3Manager
gcs = S3Manager(bucket='mlops-new')
# Should not raise an error if credentials are correct
```

## Services Configured

The following Airflow services have GCP credentials configured:
- ✅ `airflow-webserver`
- ✅ `airflow-scheduler`
- ✅ `job-handler`

## GCS Connection Details

- **Bucket:** `mlops-new`
- **Price Data Path:** `gs://mlops-new/prices/BTCUSDT.parquet`
- **Articles Path:** `gs://mlops-new/articles/articles.parquet`

## Troubleshooting

### Issue: "Credentials not found"
**Solution:** Ensure the credentials file exists at the path specified in `GCP_CREDENTIALS_PATH`

### Issue: "Permission denied"
**Solution:** Check file permissions on the credentials JSON file

### Issue: "Invalid credentials"
**Solution:** Verify the JSON file is valid and contains the correct service account key

### Issue: "Project ID mismatch"
**Solution:** Ensure `GCP_PROJECT_ID` matches your GCP project ID

## Next Steps

After setting up credentials:
1. Restart Airflow services: `docker-compose -f docker-compose.airflow.yml restart`
2. Verify credentials are loaded in logs
3. Test data download from GCS in the `pre_train_dataset` task





