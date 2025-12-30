#!/bin/bash
# Quick one-liner diagnostic for Vast.ai instance
# Run this directly on the remote server via SSH

echo "=== QUICK STATUS CHECK ===" && \
echo "Training processes:" && ps aux | grep -E "(train_paralelly|python.*train)" | grep -v grep || echo "  None running" && \
echo "" && \
echo "Port 8080:" && (netstat -tlnp 2>/dev/null | grep :8080 || ss -tlnp 2>/dev/null | grep :8080 || echo "  Not listening (NORMAL - no web service)") && \
echo "" && \
echo "Workspace:" && ls -la /workspace/ 2>/dev/null | head -5 || echo "  /workspace missing" && \
echo "" && \
echo "Project:" && ls -la /workspace/crypto-ml-training-standalone/ 2>/dev/null | head -3 || echo "  Project directory missing" && \
echo "" && \
echo "Startup log (last 10 lines):" && tail -10 /tmp/onstart.log 2>/dev/null || echo "  No startup log" && \
echo "" && \
echo "Disk space:" && df -h | grep -E "(Filesystem|/workspace|/root)" && \
echo "" && \
echo "=== CHECK COMPLETE ==="


