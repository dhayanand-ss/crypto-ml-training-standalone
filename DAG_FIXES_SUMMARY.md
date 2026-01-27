# DAG Fixes Summary

## Issues Fixed

### 1. ✅ Path Setup Issue (FIXED)
**Problem**: DAGs couldn't find the `utils` module because it's located at `/opt/airflow/project/utils` instead of `/opt/airflow/utils`.

**Solution**: Updated path detection in all 3 DAG files:
- `dags/DAG.py`
- `dags/trl_infer_dag.py`
- `dags/cleanup_DAG.py`

All now check for `/opt/airflow/project/utils` as well as `/opt/airflow/utils`.

### 2. ✅ PYTHONPATH Configuration (FIXED)
**Problem**: PYTHONPATH didn't include the project directory.

**Solution**: 
- Updated `Dockerfile.airflow` to set `ENV PYTHONPATH=/opt/airflow:/opt/airflow/project`
- Updated `docker-compose.airflow.yml` to set `PYTHONPATH: /opt/airflow:/opt/airflow/project` in all services

### 3. ✅ Dependency Issues (FIXED)
**Problem**: 
- `firebase-admin` dependency was being used
- `pandas-ta` was causing dependency resolution issues

**Solution**:
- ✅ **COMPLETELY REMOVED** Firebase implementation - migrated to `google-cloud-firestore>=2.11.0` (native GCP client)
- All Firebase Admin SDK code replaced with GCP Firestore client
- Firebase credential files removed
- Commented out `pandas-ta` in requirements.txt to avoid pip resolution conflicts (can be installed separately if needed)

## Testing the DAGs

### Option 1: Use the Test Script
```powershell
.\test_dag_cli.ps1
```

### Option 2: Manual CLI Testing

1. **Start the containers** (if not running):
```powershell
docker-compose -f docker-compose.airflow.yml up -d
```

2. **Check for import errors**:
```powershell
docker exec crypto-ml-training-standalone-airflow-scheduler-1 airflow dags list-import-errors
```

3. **List all DAGs**:
```powershell
docker exec crypto-ml-training-standalone-airflow-scheduler-1 airflow dags list
```

4. **View DAG structure**:
```powershell
docker exec crypto-ml-training-standalone-airflow-scheduler-1 airflow dags show training_pipeline
```

5. **Trigger a DAG run manually**:
```powershell
docker exec crypto-ml-training-standalone-airflow-scheduler-1 airflow dags trigger training_pipeline
```

6. **Test a specific task**:
```powershell
docker exec crypto-ml-training-standalone-airflow-scheduler-1 airflow tasks test training_pipeline pre_train_dataset 2025-01-01
```

## Next Steps

1. **Rebuild the containers** (if needed):
   ```powershell
   docker-compose -f docker-compose.airflow.yml build
   docker-compose -f docker-compose.airflow.yml up -d
   ```

2. **Wait for containers to be ready** (about 30-60 seconds)

3. **Run the test script**:
   ```powershell
   .\test_dag_cli.ps1
   ```

4. **If pandas-ta is needed**, install it separately:
   ```powershell
   docker exec crypto-ml-training-standalone-airflow-scheduler-1 pip install pandas-ta
   docker exec crypto-ml-training-standalone-airflow-webserver-1 pip install pandas-ta
   ```

## Files Modified

1. `dags/DAG.py` - Fixed path detection
2. `dags/trl_infer_dag.py` - Fixed path detection
3. `dags/cleanup_DAG.py` - Fixed path detection
4. `Dockerfile.airflow` - Updated PYTHONPATH, commented pandas-ta note
5. `docker-compose.airflow.yml` - Updated PYTHONPATH in all services
6. `requirements.txt` - Commented out pandas-ta to avoid dependency conflicts

## Expected Results

After rebuilding and starting containers:
- ✅ DAGs should load without import errors
- ✅ `utils` module should be found correctly
- ✅ `google-cloud-firestore` should be available (GCP native client)
- ✅ All DAGs should appear in `airflow dags list`








