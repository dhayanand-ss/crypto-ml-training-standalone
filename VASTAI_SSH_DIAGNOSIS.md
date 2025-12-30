# Vast.ai Instance SSH Diagnosis Guide

## Quick Diagnosis

You've connected to a Vast.ai instance via SSH tunnel on port 8080. However, **the training instance does NOT run a web service on port 8080**. Port 8080 is typically used for Airflow locally, not on Vast.ai training instances.

## Step 1: Connect via SSH

```bash
ssh -p 16388 root@ssh8.vast.ai -L 8080:localhost:8080
```

## Step 2: Run Diagnostic Script

Once connected, upload and run the diagnostic script:

### Option A: Copy script content and run directly

```bash
# On the remote server, create the script
cat > /tmp/diagnose.sh << 'EOF'
#!/bin/bash
# [Paste the content of diagnose_vastai_instance.sh here]
EOF

chmod +x /tmp/diagnose.sh
/tmp/diagnose.sh
```

### Option B: Upload the script file

From your local machine (in a new terminal, while SSH is connected):

```bash
# From your local machine
scp -P 16388 diagnose_vastai_instance.sh root@ssh8.vast.ai:/tmp/
```

Then on the remote server:
```bash
chmod +x /tmp/diagnose_vastai_instance.sh
/tmp/diagnose_vastai_instance.sh
```

## Step 3: Quick Manual Checks

If you can't run the full script, try these quick checks:

### Check if training is running:
```bash
ps aux | grep -E "(train_paralelly|python.*train)" | grep -v grep
```

### Check workspace:
```bash
ls -la /workspace/
ls -la /workspace/crypto-ml-training-standalone/ 2>/dev/null || echo "Project not found"
```

### Check startup logs:
```bash
tail -100 /tmp/onstart.log
```

### Check what's on port 8080:
```bash
netstat -tlnp | grep 8080
# or
ss -tlnp | grep 8080
```

### Check for errors:
```bash
find /workspace -name "*.log" -type f -mmin -60 -exec tail -20 {} \;
```

## Common Issues and Solutions

### Issue 1: Port 8080 Not Listening
**Symptom:** Nothing listening on port 8080

**Explanation:** This is **NORMAL**. The Vast.ai training instance runs training scripts, not web services. Port 8080 is only used for Airflow locally on your machine.

**Solution:** No action needed. The training should be running as a Python process, not a web service.

### Issue 2: Training Not Running
**Symptom:** No training processes found

**Possible causes:**
1. Startup script failed
2. Training completed
3. Training crashed

**Check:**
```bash
# Check startup log
tail -100 /tmp/onstart.log

# Check for Python errors
find /workspace -name "*.log" -exec grep -l "Error\|Exception\|Traceback" {} \;

# Check if training completed
ls -la /workspace/crypto-ml-training-standalone/results/ 2>/dev/null
```

### Issue 3: Project Directory Missing
**Symptom:** `/workspace/crypto-ml-training-standalone` doesn't exist

**Possible causes:**
1. GitHub clone failed
2. Startup script didn't run
3. Wrong directory name

**Check:**
```bash
# Check what's in workspace
ls -la /workspace/

# Check startup log for clone errors
grep -i "clone\|git" /tmp/onstart.log

# Check if repo exists with different name
find /workspace -name "*crypto*" -type d
```

### Issue 4: Data Files Missing
**Symptom:** No `data/btcusdt.csv` or `data/articles.csv`

**Check:**
```bash
cd /workspace/crypto-ml-training-standalone
ls -la data/
ls -la data/prices/
```

**Solution:** Data should be downloaded automatically. If missing, check GCP credentials and S3 access.

### Issue 5: Out of Disk Space
**Symptom:** Training fails with disk space errors

**Check:**
```bash
df -h
```

**Solution:** Clean up old files or use instance with more disk space.

## What Should Be Running

On a healthy Vast.ai training instance, you should see:

1. **Python training process:**
   ```bash
   ps aux | grep train_paralelly
   ```

2. **Project directory:**
   ```bash
   ls -la /workspace/crypto-ml-training-standalone/
   ```

3. **Data files:**
   ```bash
   ls -la /workspace/crypto-ml-training-standalone/data/
   ```

4. **Startup log:**
   ```bash
   ls -la /tmp/onstart.log
   ```

## Understanding the SSH Tunnel

The SSH command you used:
```bash
ssh -p 16388 root@ssh8.vast.ai -L 8080:localhost:8080
```

This creates a **local port forward**:
- **Local port 8080** → **Remote localhost:8080**

This is useful if there WAS a web service running on port 8080 on the remote server. However, the training instance doesn't run web services - it runs training scripts.

If you want to access a web service (like MLflow or FastAPI), you would need to:
1. Start the service on the remote instance
2. Use the appropriate port (e.g., 5000 for MLflow, 8000 for FastAPI)

## Next Steps

1. Run the diagnostic script to get a full report
2. Check the startup log for errors
3. Verify training is running
4. Check for any error logs in the project directory
5. If training failed, check the error messages and fix the underlying issue

## Getting Help

If you find specific errors, check:
- `/tmp/onstart.log` - Startup script output
- `/workspace/crypto-ml-training-standalone/logs/` - Training logs (if exists)
- Python tracebacks in any log files
- Disk space and memory usage


