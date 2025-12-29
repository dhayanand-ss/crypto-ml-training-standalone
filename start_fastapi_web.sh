#!/bin/bash
# Bash script to start FastAPI server accessible on the web
# This makes the server accessible on your local network

echo "========================================"
echo "Starting FastAPI Server for Web Access"
echo "========================================"

# Set environment variables for web access
export PORT=8000
export HOST=0.0.0.0  # Listen on all network interfaces
export MLFLOW_TRACKING_URI=http://localhost:5000

# Get local IP address
if [[ "$OSTYPE" == "darwin"* ]]; then
    # macOS
    IP_ADDRESS=$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || echo "localhost")
elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
    # Linux
    IP_ADDRESS=$(hostname -I | awk '{print $1}' 2>/dev/null || echo "localhost")
else
    IP_ADDRESS="localhost"
fi

echo ""
echo "Server will be accessible at:"
echo "  Local:    http://localhost:8000"
echo "  Network:  http://$IP_ADDRESS:8000"
echo ""
echo "API Documentation:"
echo "  http://$IP_ADDRESS:8000/docs"
echo ""
echo "Press Ctrl+C to stop the server"
echo "========================================"
echo ""

# Start the server
python start_fastapi_server.py












