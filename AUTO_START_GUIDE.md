# Auto-Start Guide for Airflow DAGs

## The Short Answer

**Yes, Docker Desktop needs to be running**, but you can configure it to start automatically. Once Docker is running, your containers will automatically restart and your DAGs will run on schedule.

## Current Setup ✅

Your containers already have `restart: always` configured, which means:
- ✅ Containers will automatically restart if Docker is running
- ✅ Containers will restart after system reboot (if Docker auto-starts)
- ✅ Containers will restart if they crash

## Option 1: Enable Docker Desktop Auto-Start (Recommended) 🚀

### Windows Settings:

1. **Open Docker Desktop**
2. **Go to Settings** (gear icon)
3. **General tab** → Check **"Start Docker Desktop when you log in"**
4. **Apply & Restart**

Now Docker will start automatically when you log into Windows, and your Airflow containers will start automatically.

## Option 2: Use a Startup Script 📝

Create a shortcut or scheduled task to run this on startup:

```powershell
# Check if Docker is running, if not start it
if (-not (Get-Process "Docker Desktop" -ErrorAction SilentlyContinue)) {
    Start-Process "C:\Program Files\Docker\Docker\Docker Desktop.exe"
    Write-Host "Waiting for Docker Desktop to start..."
    Start-Sleep -Seconds 30
}

# Start Airflow containers
cd C:\Users\dhaya\crypto-ml-training-standalone
docker-compose -f docker-compose.airflow.yml up -d
```

## Option 3: Windows Task Scheduler (Fully Automatic) ⏰

1. **Open Task Scheduler** (search "Task Scheduler" in Windows)
2. **Create Basic Task**
3. **Name:** "Start Docker and Airflow"
4. **Trigger:** "When I log on"
5. **Action:** "Start a program"
   - Program: `powershell.exe`
   - Arguments: `-File "C:\Users\dhaya\crypto-ml-training-standalone\auto_start_airflow.ps1"`
6. **Finish**

## Quick Commands

### Check if Docker is running:
```powershell
docker ps
```

### Start Docker Desktop manually:
```powershell
Start-Process "C:\Program Files\Docker\Docker\Docker Desktop.exe"
```

### Start Airflow containers:
```powershell
cd C:\Users\dhaya\crypto-ml-training-standalone
docker-compose -f docker-compose.airflow.yml up -d
```

### Check container status:
```powershell
docker-compose -f docker-compose.airflow.yml ps
```

## What Happens When Docker Starts?

1. ✅ Docker Desktop starts
2. ✅ Containers with `restart: always` automatically start
3. ✅ Airflow scheduler begins running
4. ✅ DAGs execute on their schedule
5. ✅ You can access Airflow UI at http://localhost:8080

## Summary

- **Docker Desktop must be running** for DAGs to execute
- **Enable auto-start in Docker Desktop settings** (easiest)
- **Containers will auto-restart** once Docker is running (already configured)
- **DAGs will run on schedule** once everything is up

The only manual step needed is ensuring Docker Desktop is running. Enable auto-start and you're all set! 🎉

