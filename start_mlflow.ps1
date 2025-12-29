#!/usr/bin/env pwsh
"""
Start MLflow Server
Simple script to start MLflow UI server for model tracking and registry.
"""

Write-Host "=" * 60
Write-Host "Starting MLflow Server"
Write-Host "=" * 60

# Get port from environment or default to 5000
$port = if ($env:MLFLOW_PORT) { $env:MLFLOW_PORT } else { "5000" }
$host_address = if ($env:MLFLOW_HOST) { $env:MLFLOW_HOST } else { "127.0.0.1" }

Write-Host "Port: $port"
Write-Host "Host: $host_address"
Write-Host "URL: http://$host_address`:$port"
Write-Host "=" * 60
Write-Host ""

# Check if MLflow is installed
try {
    $mlflowVersion = mlflow --version 2>&1
    Write-Host "MLflow version: $mlflowVersion"
} catch {
    Write-Host "ERROR: MLflow not found. Install with: pip install mlflow" -ForegroundColor Red
    Write-Host "Or install all requirements: pip install -r requirements.txt" -ForegroundColor Yellow
    exit 1
}

Write-Host ""
Write-Host "Starting MLflow UI server..." -ForegroundColor Green
Write-Host "Press Ctrl+C to stop the server" -ForegroundColor Yellow
Write-Host ""

# Check if mlartifacts directory exists
$artifactRoot = "./mlartifacts"
if (-not (Test-Path $artifactRoot)) {
    Write-Host "Warning: Artifact root directory '$artifactRoot' does not exist" -ForegroundColor Yellow
    Write-Host "Creating directory..." -ForegroundColor Yellow
    New-Item -ItemType Directory -Path $artifactRoot -Force | Out-Null
}

Write-Host "Artifact root: $artifactRoot" -ForegroundColor Cyan
Write-Host ""

# Start MLflow UI with artifact root configured
try {
    mlflow ui --port $port --host $host_address --default-artifact-root $artifactRoot
} catch {
    Write-Host ""
    Write-Host "ERROR: Failed to start MLflow server" -ForegroundColor Red
    Write-Host "Error: $_" -ForegroundColor Red
    Write-Host ""
    Write-Host "Troubleshooting:" -ForegroundColor Yellow
    Write-Host "1. Check if port $port is already in use: netstat -ano | findstr :$port"
    Write-Host "2. Try a different port: `$env:MLFLOW_PORT=5001; .\start_mlflow.ps1"
    Write-Host "3. Make sure MLflow is installed: pip install mlflow"
    exit 1
}

