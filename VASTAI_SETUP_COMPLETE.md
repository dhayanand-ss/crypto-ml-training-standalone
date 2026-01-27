# Vast AI API Key Configuration - Complete

## ✅ What Has Been Configured

1. **Created `.env` file** with your Vast AI API key:
   ```
   VASTAI_API_KEY=a8a659e0c4935171d71bd6f7dce3a87a28068fe80967eb3235750eae1e286de1
   ```

2. **Updated `docker-compose.airflow.yml`**:
   - Uncommented `VASTAI_API_KEY: ${VASTAI_API_KEY}` in `airflow-webserver` service (line 43)
   - Added `VASTAI_API_KEY: ${VASTAI_API_KEY}` to `airflow-scheduler` service (line 81)
   - Removed obsolete `version: '3.8'` field

## 📋 Next Steps

### 1. Start Docker Desktop
Make sure Docker Desktop is running on your Windows machine.

### 2. Restart Airflow Containers
Once Docker Desktop is running, execute:

```powershell
# Stop existing containers
docker-compose -f docker-compose.airflow.yml down

# Start containers (they will pick up the .env file automatically)
docker-compose -f docker-compose.airflow.yml up -d
```

**Note:** If you encounter build errors due to network issues (like downloading NVIDIA libraries), you can skip the build:
```powershell
docker-compose -f docker-compose.airflow.yml up -d --no-build
```

### 3. Verify the API Key is Loaded
After containers start, verify the environment variable:

```powershell
# Check if the key is in the scheduler container
docker exec crypto-ml-training-standalone-airflow-scheduler-1 printenv | Select-String -Pattern "VASTAI"
```

You should see:
```
VASTAI_API_KEY=a8a659e0c4935171d71bd6f7dce3a87a28068fe80967eb3235750eae1e286de1
```

### 4. Test the DAG
1. Go to Airflow UI: http://localhost:8080
2. Trigger the `training_pipeline` DAG
3. Check the `vast_ai_train` task logs
4. You should **NOT** see the error: "VASTAI_API_KEY environment variable not set"

## 🔍 Troubleshooting

### If the API key still doesn't work:

1. **Check .env file exists:**
   ```powershell
   Get-Content .env
   ```

2. **Verify docker-compose is reading it:**
   ```powershell
   docker-compose -f docker-compose.airflow.yml config | Select-String -Pattern "VASTAI"
   ```

3. **Make sure containers were recreated** (not just restarted):
   ```powershell
   docker-compose -f docker-compose.airflow.yml down
   docker-compose -f docker-compose.airflow.yml up -d
   ```

4. **Check container environment:**
   ```powershell
   docker exec crypto-ml-training-standalone-airflow-scheduler-1 env | Select-String -Pattern "VASTAI"
   ```

## 📝 Files Modified

- ✅ `.env` - Created with API key
- ✅ `docker-compose.airflow.yml` - Added VASTAI_API_KEY to both webserver and scheduler services

## ✨ Summary

The configuration is complete. Once you restart Docker Desktop and bring up the containers, the `vast_ai_train` task should be able to access your Vast AI API key and create instances successfully.


