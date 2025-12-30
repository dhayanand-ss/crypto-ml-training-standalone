# Vast AI "C.29306163" Container Error - Fixed

## Problem
```
Error response from daemon: No such container: C.29306163
```

This error occurs when Vast AI CLI returns an error in the format `C.<instance_id>` (e.g., `C.29306163`). This is Vast AI's internal container ID format, which appears when:
1. An instance was destroyed/terminated
2. An instance never existed
3. There's a timing issue where the instance disappears before status can be checked

## Root Cause

The error handling code was only checking for generic patterns like "no such container" but wasn't catching the specific `C.<instance_id>` format that Vast AI uses internally.

## Solution Applied

### 1. Enhanced Error Pattern Detection
Updated error handling in three key functions to detect the `C.<instance_id>` format:

- **`wait_for_pod()`** in `utils/utils/vast_ai_train.py`
- **`verify_instance_exists()`** in `utils/utils/vast_ai_train.py`  
- **`kill_instance()`** in `utils/utils/kill_vast_ai_instances.py`

### 2. Improved Error Message Parsing
Now checks both `stderr` and `stdout` for error messages, as Vast AI CLI may output errors in either stream.

### 3. Pattern Matching
Added detection for multiple error formats:
- `"no such container"`
- `"not found"`
- `"does not exist"`
- `"c.<instance_id>"` (Vast AI internal format like "C.29306163")
- `"container.*<instance_id>"`

## Files Modified

1. **`utils/utils/vast_ai_train.py`**
   - Enhanced `wait_for_pod()` error handling
   - Enhanced `verify_instance_exists()` error handling

2. **`utils/utils/kill_vast_ai_instances.py`**
   - Enhanced `kill_instance()` error handling

## How It Works Now

When the code encounters a "No such container: C.29306163" error:

1. **`wait_for_pod()`**: Detects the error, logs it clearly, and returns `False` immediately (no more retry loops)
2. **`verify_instance_exists()`**: Detects the error and returns `None` gracefully
3. **`kill_instance()`**: Treats it as success (instance already gone)

## Testing

After applying the fix:

1. **Restart Airflow** (already done):
   ```powershell
   docker-compose -f docker-compose.airflow.yml restart
   ```

2. **Run your DAG** - the error should be handled gracefully:
   - No more error spam in logs
   - Code will detect missing instances and move on
   - Will try next available pod if instance creation fails

3. **Monitor logs**:
   ```powershell
   docker-compose -f docker-compose.airflow.yml logs -f airflow-scheduler | Select-String -Pattern "instance|vastai|container"
   ```

## Expected Behavior

### Before Fix:
```
Error response from daemon: No such container: C.29306163
[Repeats many times, causing log spam]
```

### After Fix:
```
Instance 29306163 does not exist. It may have been destroyed or never created.
[Code moves on to next available pod or retry]
```

## Additional Notes

- The `C.` prefix is Vast AI's internal container identifier format
- Instances can be destroyed quickly if they fail to start
- The improved error handling prevents infinite retry loops
- All error detection is case-insensitive for robustness

## If Error Persists

If you still see the error:

1. **Check instance status manually**:
   ```powershell
   vastai show instance 29306163
   ```

2. **List all instances**:
   ```powershell
   vastai show instances
   ```

3. **Clean up any stale instances**:
   ```powershell
   # From Airflow container
   docker exec crypto-ml-training-standalone-airflow-scheduler-1 python -m utils.utils.kill_vast_ai_instances
   ```

4. **Check full error context in logs**:
   ```powershell
   docker-compose -f docker-compose.airflow.yml logs airflow-scheduler --tail 200
   ```

The error should now be caught and handled gracefully without causing log spam or blocking the training pipeline.





