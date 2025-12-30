#!/bin/bash
# Script to check Vast AI instance status after SSH connection

echo "=========================================="
echo "Checking Instance Status"
echo "=========================================="

echo ""
echo "1. Checking if pip installation is still running..."
ps aux | grep -E "(pip|python.*install)" | grep -v grep

echo ""
echo "2. Checking current directory and workspace..."
pwd
ls -la /workspace 2>/dev/null || echo "No /workspace directory found"
ls -la /workspace/crypto-ml-training-standalone 2>/dev/null || echo "Repository not found in /workspace"

echo ""
echo "3. Checking if training has started..."
ps aux | grep -E "(train_paralelly|time_series_transformer|lightgbm|trl_train)" | grep -v grep

echo ""
echo "4. Checking recent log files..."
find /workspace -name "*.log" -type f -mmin -30 2>/dev/null | head -5

echo ""
echo "5. Checking if Python processes are running..."
ps aux | grep python | grep -v grep

echo ""
echo "6. Checking startup script output (if available)..."
tail -100 /tmp/onstart.log 2>/dev/null || echo "No onstart.log found"

echo ""
echo "7. Checking if requirements.txt installation completed..."
if [ -f /workspace/crypto-ml-training-standalone/requirements.txt ]; then
    echo "requirements.txt exists"
    echo "Checking pip list for key packages..."
    pip list | grep -E "(torch|transformers|lightgbm|pandas)" || echo "Packages not installed yet"
else
    echo "requirements.txt not found - repository may not be cloned yet"
fi

echo ""
echo "8. Checking disk space..."
df -h

echo ""
echo "=========================================="
echo "Status Check Complete"
echo "=========================================="





