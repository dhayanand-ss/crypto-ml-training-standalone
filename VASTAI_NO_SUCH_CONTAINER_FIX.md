# Vast AI "No such container" Error - Fixed

## Problem
```
Error response from daemon: No such container: C.29306111
```

This error occurs when the code tries to check the status of a Vast AI instance that doesn't exist. This can happen when:
1. An instance was destroyed/terminated but the code still has a reference to it
2. Instance creation failed but the code parsed an incorrect instance ID
3. There's a timing issue where the instance disappears before status can be checked

## Solution Applied

### 1. Improved Error Handling in `wait_for_pod()`
- Now detects "No such container" errors and handles them gracefully
- Returns `False` immediately if instance doesn't exist (instead of retrying indefinitely)

### 2. Improved Error Handling in `kill_instance()`
- Treats "No such container" as success (instance already terminated)
- Prevents unnecessary error messages when cleaning up non-existent instances

### 3. Improved Error Handling in `verify_instance_exists()`
- Better handling of non-existent instances
- More informative logging

## Files Modified
- `utils/utils/vast_ai_train.py` - Added error detection for "No such container"
- `utils/utils/kill_vast_ai_instances.py` - Improved cleanup error handling

## How to Use

### Option 1: Clean Up Stale Instances (Recommended)
Run the cleanup script from within the Airflow container:

```powershell
# Enter the Airflow scheduler container
docker exec -it crypto-ml-training-standalone-airflow-scheduler-1 bash

# Run the cleanup
python -c "from utils.utils.kill_vast_ai_instances import kill_all_vastai_instances; kill_all_vastai_instances()"
```

Or use the Python script directly:
```powershell
docker exec crypto-ml-training-standalone-airflow-scheduler-1 python -m utils.utils.kill_vast_ai_instances
```

### Option 2: Manual Cleanup via Vast AI Dashboard
1. Go to https://console.vast.ai/instances
2. Find and terminate any stale instances
3. Run your DAG again

### Option 3: Let It Auto-Cleanup
The code automatically cleans up instances before creating new ones. Just run your DAG again - the error should be handled gracefully now.

## Testing

After applying the fix, when you run your training DAG:

1. **If instance doesn't exist**: The code will detect it and move on (no more error spam)
2. **If instance creation fails**: The code will clean up and try the next available pod
3. **If instance is stale**: The cleanup function will handle it gracefully

## Next Steps

1. **Restart Airflow** to load the updated code:
   ```powershell
   docker-compose -f docker-compose.airflow.yml restart
   ```

2. **Run your training DAG** - it should handle the error gracefully now

3. **Monitor the logs** to see if instances are being created successfully:
   ```powershell
   docker-compose -f docker-compose.airflow.yml logs -f airflow-scheduler | Select-String -Pattern "instance|vastai"
   ```

## Additional Notes

- The error handling now distinguishes between:
  - **Network errors** (retry)
  - **Instance doesn't exist** (fail fast, don't retry)
  - **Other errors** (log and retry)

- The cleanup process is more robust and won't fail if an instance is already gone

- Instance verification is more reliable and handles edge cases better

## If Error Persists

If you still see the error:

1. Check if there are any instances in your Vast AI dashboard
2. Verify your API key is correct: `.\set_vastai_key.ps1`
3. Check the full error logs:
   ```powershell
   docker-compose -f docker-compose.airflow.yml logs airflow-scheduler --tail 100
   ```
4. Make sure your GitHub repository is accessible and public (or you have proper authentication)





