#!/bin/bash
# Comprehensive diagnostic script for Vast.ai instance
# Run this via SSH to diagnose issues

echo "=========================================="
echo "Vast.ai Instance Diagnostic Script"
echo "=========================================="
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 1. Check system info
echo "1. System Information"
echo "-------------------"
echo "Hostname: $(hostname)"
echo "Uptime: $(uptime)"
echo "Date: $(date)"
echo ""

# 2. Check disk space
echo "2. Disk Space"
echo "-------------------"
df -h | grep -E "(Filesystem|/workspace|/root|/tmp)"
echo ""

# 3. Check memory
echo "3. Memory Usage"
echo "-------------------"
free -h
echo ""

# 4. Check running processes
echo "4. Running Processes"
echo "-------------------"
echo "Python processes:"
ps aux | grep python | grep -v grep | head -10
echo ""
echo "All processes (top 10 by CPU):"
ps aux --sort=-%cpu | head -11
echo ""

# 5. Check network/listening ports
echo "5. Network - Listening Ports"
echo "-------------------"
echo "Ports listening on all interfaces:"
netstat -tlnp 2>/dev/null | grep LISTEN || ss -tlnp 2>/dev/null | grep LISTEN || echo "Cannot check ports (netstat/ss not available)"
echo ""
echo "Port 8080 specifically:"
netstat -tlnp 2>/dev/null | grep :8080 || ss -tlnp 2>/dev/null | grep :8080 || echo "Port 8080 is NOT listening"
echo ""

# 6. Check workspace directory
echo "6. Workspace Directory"
echo "-------------------"
if [ -d /workspace ]; then
    echo -e "${GREEN}✓ /workspace exists${NC}"
    echo "Contents:"
    ls -la /workspace/ | head -20
    echo ""
    
    # Check for project directory
    if [ -d /workspace/crypto-ml-training-standalone ]; then
        echo -e "${GREEN}✓ Project directory found${NC}"
        echo "Project contents:"
        ls -la /workspace/crypto-ml-training-standalone/ | head -20
    else
        echo -e "${YELLOW}⚠ Project directory not found${NC}"
        echo "Looking for other directories:"
        find /workspace -maxdepth 1 -type d 2>/dev/null
    fi
else
    echo -e "${RED}✗ /workspace does not exist${NC}"
fi
echo ""

# 7. Check startup script logs
echo "7. Startup Script Logs"
echo "-------------------"
if [ -f /tmp/onstart.log ]; then
    echo -e "${GREEN}✓ Startup log found${NC}"
    echo "Last 50 lines:"
    tail -50 /tmp/onstart.log
else
    echo -e "${YELLOW}⚠ No startup log found at /tmp/onstart.log${NC}"
fi
echo ""

# 8. Check for training processes
echo "8. Training Status"
echo "-------------------"
TRAINING_PROCESSES=$(ps aux | grep -E "(train_paralelly|time_series_transformer|lightgbm|trl_train|train)" | grep -v grep)
if [ -n "$TRAINING_PROCESSES" ]; then
    echo -e "${GREEN}✓ Training processes found:${NC}"
    echo "$TRAINING_PROCESSES"
else
    echo -e "${YELLOW}⚠ No training processes running${NC}"
fi
echo ""

# 9. Check Python environment
echo "9. Python Environment"
echo "-------------------"
echo "Python version:"
python3 --version 2>/dev/null || python --version 2>/dev/null || echo "Python not found"
echo ""
echo "Pip version:"
pip3 --version 2>/dev/null || pip --version 2>/dev/null || echo "Pip not found"
echo ""
echo "Key packages installed:"
pip list 2>/dev/null | grep -E "(torch|transformers|lightgbm|pandas|numpy|trl)" | head -10 || echo "Cannot check packages"
echo ""

# 10. Check for data files
echo "10. Data Files"
echo "-------------------"
if [ -d /workspace/crypto-ml-training-standalone ]; then
    cd /workspace/crypto-ml-training-standalone
    echo "Checking for data files:"
    [ -f data/btcusdt.csv ] && echo -e "${GREEN}✓ data/btcusdt.csv exists${NC}" || echo -e "${YELLOW}⚠ data/btcusdt.csv missing${NC}"
    [ -f data/articles.csv ] && echo -e "${GREEN}✓ data/articles.csv exists${NC}" || echo -e "${YELLOW}⚠ data/articles.csv missing${NC}"
    [ -f data/prices/BTCUSDT.csv ] && echo -e "${GREEN}✓ data/prices/BTCUSDT.csv exists${NC}" || echo -e "${YELLOW}⚠ data/prices/BTCUSDT.csv missing${NC}"
    [ -f requirements.txt ] && echo -e "${GREEN}✓ requirements.txt exists${NC}" || echo -e "${YELLOW}⚠ requirements.txt missing${NC}"
else
    echo "Cannot check data files - project directory not found"
fi
echo ""

# 11. Check for errors in common log locations
echo "11. Recent Error Logs"
echo "-------------------"
echo "Checking for error patterns in logs:"
find /workspace -name "*.log" -type f -mmin -60 2>/dev/null | head -5 | while read logfile; do
    echo "Checking $logfile:"
    grep -i "error\|exception\|failed\|traceback" "$logfile" 2>/dev/null | tail -5 || echo "  No errors found"
done
echo ""

# 12. Check Docker (if applicable)
echo "12. Docker Status"
echo "-------------------"
if command -v docker &> /dev/null; then
    echo "Docker version:"
    docker --version
    echo ""
    echo "Running containers:"
    docker ps 2>/dev/null || echo "Cannot list containers (may need sudo)"
else
    echo "Docker not installed or not in PATH"
fi
echo ""

# 13. Check environment variables
echo "13. Environment Variables"
echo "-------------------"
echo "Key environment variables:"
env | grep -E "(VASTAI|GCP|MLFLOW|WANDB|CUDA|PATH)" | sort
echo ""

# 14. Check GPU (if available)
echo "14. GPU Status"
echo "-------------------"
if command -v nvidia-smi &> /dev/null; then
    nvidia-smi --query-gpu=name,memory.total,memory.used,memory.free,temperature.gpu,utilization.gpu --format=csv,noheader,nounits 2>/dev/null || nvidia-smi
else
    echo "nvidia-smi not available (no GPU or drivers not installed)"
fi
echo ""

# 15. Summary and recommendations
echo "=========================================="
echo "Summary and Recommendations"
echo "=========================================="
echo ""

ISSUES=0

# Check if training is running
if ! ps aux | grep -E "(train_paralelly|time_series_transformer|lightgbm|trl_train)" | grep -v grep > /dev/null; then
    echo -e "${YELLOW}⚠ Training is not running${NC}"
    ISSUES=$((ISSUES + 1))
fi

# Check if workspace exists
if [ ! -d /workspace ]; then
    echo -e "${RED}✗ /workspace directory missing${NC}"
    ISSUES=$((ISSUES + 1))
fi

# Check if project directory exists
if [ ! -d /workspace/crypto-ml-training-standalone ]; then
    echo -e "${YELLOW}⚠ Project directory missing${NC}"
    ISSUES=$((ISSUES + 1))
fi

# Check port 8080
if ! (netstat -tlnp 2>/dev/null | grep :8080 > /dev/null || ss -tlnp 2>/dev/null | grep :8080 > /dev/null); then
    echo -e "${YELLOW}⚠ Port 8080 is not listening${NC}"
    echo "  Note: The training script does not start a web service on port 8080."
    echo "  Port 8080 is typically used for Airflow locally, not on Vast.ai instances."
    ISSUES=$((ISSUES + 1))
fi

if [ $ISSUES -eq 0 ]; then
    echo -e "${GREEN}✓ No obvious issues detected${NC}"
else
    echo ""
    echo "Recommendations:"
    echo "1. Check /tmp/onstart.log for startup errors"
    echo "2. Verify the startup script completed successfully"
    echo "3. Check if training process crashed (look for Python tracebacks)"
    echo "4. Verify data files are present"
    echo "5. Check disk space (training may have failed due to full disk)"
fi

echo ""
echo "=========================================="
echo "Diagnostic Complete"
echo "=========================================="


