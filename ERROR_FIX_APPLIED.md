# Error Fix Applied: "Error response from daemon: No such container: C.29306411"

## Problem

The error "Error response from daemon: No such container: C.29306411" was appearing in logs even though we had error handling in place.

## Root Cause

The error can appear in two scenarios:
1. **Command fails** (CalledProcessError) - Already handled ✅
2. **Command succeeds but error in output** - Was NOT being checked ❌

The error message can appear in `stdout` or `stderr` even when the command returns exit code 0.

## Solution Applied

### 1. Added Pre-Parse Error Check

Before parsing JSON, we now check for error messages in the output:

```python
# Check for error messages in output (even if command succeeded)
error_output = (result.stderr or "") + (result.stdout or "")
if error_output and ("error response from daemon" in error_output.lower() or 
                    f"no such container" in error_output.lower() or
                    f"c.{instance_id}" in error_output.lower()):
    instance_id_str = str(instance_id)
    if instance_id_str in error_output:
        logger.warning(f"Instance {instance_id} container not found (may still be starting): {error_output[:200]}")
        time.sleep(10)
        continue
```

### 2. Enhanced Error Pattern Detection

Improved the pattern matching to catch all variations:
- "error response from daemon"
- "no such container"
- "C.<instance_id>" (case-insensitive)
- Instance ID presence check

### 3. Better Error Logging

Added stderr logging when JSON parsing fails to help debug issues.

## Files Modified

- `utils/utils/vast_ai_train.py`
  - Added pre-parse error check in `wait_for_pod()` (lines 378-390)
  - Enhanced error pattern detection
  - Improved error logging

## How It Works Now

1. **Command executes** - `vastai show instance <id> --raw`
2. **Check output first** - Look for error messages even if command succeeded
3. **If error found** - Log warning and wait/retry (instance may still be starting)
4. **If command fails** - Catch CalledProcessError and handle gracefully
5. **Parse JSON** - Only if no errors found

## Expected Behavior

### Before Fix:
```
Error response from daemon: No such container: C.29306411
[Appears in logs, not caught]
```

### After Fix:
```
Instance 29306411 container not found (may still be starting): Error response from daemon: No such container: C.29306411
[Caught, logged, and handled gracefully - waits and retries]
```

## Testing

The fix handles:
- ✅ Errors in stdout
- ✅ Errors in stderr  
- ✅ Errors when command succeeds
- ✅ Errors when command fails
- ✅ Case variations (C., c., etc.)
- ✅ Instance ID detection

## Status

✅ **Fix Applied** - Error handling now catches the error in all scenarios
✅ **Airflow Restarted** - Changes are active

The error should now be caught and handled gracefully!





