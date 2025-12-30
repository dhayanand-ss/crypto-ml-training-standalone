# Enhanced Debug Logging for docker_build Error

## Problem

The error "docker_build() error writing dockerfile" keeps occurring, and we need more detailed logs to diagnose the issue.

## Solution: Enhanced Debug Logging

Added comprehensive logging at every step of the file creation and instance creation process.

## New Debug Information

### 1. Startup Command Logging
- Command length (character count)
- Command preview (first 500 characters)
- Full command content available in debug logs

### 2. File Creation Logging
- Temporary file path
- Bytes written
- File size verification
- File permissions (octal and human-readable)
- File existence check
- File readability verification
- File content verification

### 3. Pre-Flight Checks
- Absolute path resolution
- File existence before Vast AI call
- File size before Vast AI call
- File readability check
- File executable check
- File content preview

### 4. Vast AI Command Logging
- Full command being executed
- All parameters
- File details at execution time
- Complete stdout/stderr output
- Return code

### 5. Error Detection
- Detailed error messages
- File state at time of error
- File permissions
- File size
- Content preview

## Log Levels

### INFO Level (Always Visible)
- File creation start/end
- Vast AI command execution
- Command output summary
- Errors

### DEBUG Level (Detailed)
- File paths
- File sizes
- File permissions
- Content previews
- Verification steps

## How to Use

### 1. Enable Debug Logging

In your DAG or environment:
```python
import logging
logging.getLogger('utils.utils.vast_ai_train').setLevel(logging.DEBUG)
```

Or set in Airflow:
```python
AIRFLOW__LOGGING__LOGGING_LEVEL=DEBUG
```

### 2. Check Logs

After running your DAG, check the logs:
```bash
docker-compose -f docker-compose.airflow.yml logs airflow-scheduler | grep -A 50 "vast_ai_train"
```

Or in Airflow UI:
- Go to the task logs
- Look for "vast_ai_train" task
- Check for detailed file creation logs

### 3. What to Look For

**File Creation Issues:**
- "Failed to create temporary file"
- "File is empty after write"
- "File content length mismatch"
- "Failed to verify file readability"

**Permission Issues:**
- File permissions not 0o755
- "File readable: False"
- "File executable: False"

**Vast AI Issues:**
- "docker_build" in output
- "error writing dockerfile"
- Check the full stdout/stderr output

## Example Debug Output

```
INFO - Building startup command...
DEBUG - Startup command length: 1234 characters
DEBUG - Startup command preview (first 500 chars): ...
INFO - Creating temporary startup script file...
DEBUG - Temporary file path: /tmp/vastai_onstart_xxxxx.sh
DEBUG - Writing startup command to file...
DEBUG - Wrote 1234 bytes to file
DEBUG - File size: 1234 bytes
DEBUG - Setting file permissions...
DEBUG - File permissions: -rwxr-xr-x (octal: 0o755)
DEBUG - File verification: readable, 1234 characters
INFO - Successfully created temporary startup script: /tmp/vastai_onstart_xxxxx.sh
DEBUG - Using absolute path: /tmp/vastai_onstart_xxxxx.sh
DEBUG - File exists: True
DEBUG - File size: 1234 bytes
DEBUG - File readable: True
DEBUG - File executable: True
INFO - Executing Vast AI instance creation command...
DEBUG - Full command: vastai create instance 12345 --image python:3.10-slim --onstart /tmp/vastai_onstart_xxxxx.sh --disk 30 --ssh
INFO - Calling Vast AI CLI to create instance...
INFO - ============================================================
INFO - Vast AI Command Output:
INFO - ============================================================
INFO - Return code: 0
INFO - STDOUT (xxx chars): {...}
INFO - STDERR (xxx chars): {...}
INFO - ============================================================
```

## Error Output Example

If docker_build error occurs:
```
ERROR - ============================================================
ERROR - DOCKER_BUILD ERROR DETECTED!
ERROR - ============================================================
ERROR - Error type: docker_build() error writing dockerfile
ERROR - Startup script file: /tmp/vastai_onstart_xxxxx.sh
ERROR - File exists: True
ERROR - File size: 1234 bytes
ERROR - File permissions: -rwxr-xr-x
ERROR - Startup command length: 1234 characters
ERROR - Startup script content (first 1000 chars): ...
ERROR - ============================================================
```

## Next Steps

1. **Run your DAG** with debug logging enabled
2. **Check the logs** for detailed file creation information
3. **Look for** any file creation or permission issues
4. **Share the logs** if the error persists - we'll have much more information to diagnose

## Files Modified

- `utils/utils/vast_ai_train.py`
  - Enhanced logging throughout file creation process
  - Added pre-flight checks
  - Detailed error reporting
  - Complete command output logging

The enhanced logging will help us identify exactly where and why the docker_build error is occurring!





