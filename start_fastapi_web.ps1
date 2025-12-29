# PowerShell script to start FastAPI server accessible on the web
# This makes the server accessible on your local network

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Starting FastAPI Server for Web Access" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

# Set environment variables for web access
$env:PORT = "8000"
$env:HOST = "0.0.0.0"  # Listen on all network interfaces
$env:MLFLOW_TRACKING_URI = "http://localhost:5000"

# Get local IP address
$ipAddress = (Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.InterfaceAlias -notlike "*Loopback*" -and $_.IPAddress -notlike "169.254.*" } | Select-Object -First 1).IPAddress

Write-Host ""
Write-Host "Server will be accessible at:" -ForegroundColor Green
Write-Host "  Local:    http://localhost:8000" -ForegroundColor Yellow
Write-Host "  Network:  http://$ipAddress:8000" -ForegroundColor Yellow
Write-Host ""
Write-Host "API Documentation:" -ForegroundColor Green
Write-Host "  http://$ipAddress:8000/docs" -ForegroundColor Yellow
Write-Host ""
Write-Host "Press Ctrl+C to stop the server" -ForegroundColor Gray
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Start the server
python start_fastapi_server.py












