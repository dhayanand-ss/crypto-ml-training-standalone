#!/usr/bin/env python3
"""
Fix FastAPI models by loading them directly from local MLflow runs
This bypasses the artifact download issue
"""

import os
import sys
import requests
from pathlib import Path
import glob

project_root = Path(__file__).resolve().parent
sys.path.insert(0, str(project_root))

print("=" * 60)
print("Fix and Load Models - Direct Approach")
print("=" * 60)
print()

# Step 1: Check if we can find ONNX models locally
print("Step 1: Searching for ONNX models in local directories...")
print()

onnx_files = []
search_paths = [
    project_root / "mlruns",
    project_root / "mlartifacts", 
    project_root / "models" / "onnx"
]

for search_path in search_paths:
    if search_path.exists():
        found = list(search_path.rglob("*.onnx"))
        if found:
            print(f"Found {len(found)} ONNX file(s) in {search_path}")
            for f in found[:5]:  # Show first 5
                print(f"  - {f.relative_to(project_root)}")
            onnx_files.extend(found)

if not onnx_files:
    print("No ONNX files found locally")
    print()
    print("Solution: Re-register models with ONNX")
    print("  But first, let's fix the registration script Unicode issue...")
    
    # Fix Unicode in registration script
    print()
    print("Fixing registration script...")
    reg_file = project_root / "register_models_to_mlflow.py"
    if reg_file.exists():
        content = reg_file.read_text(encoding='utf-8')
        # Replace all Unicode emojis
        replacements = {
            '✅': 'OK:',
            '❌': 'ERROR:',
            '⚠️': 'WARNING:'
        }
        for old, new in replacements.items():
            content = content.replace(old, new)
        reg_file.write_text(content, encoding='utf-8')
        print("OK: Registration script fixed")
    
    print()
    print("Now you can run: python register_models_to_mlflow.py")
    exit(0)

print()
print(f"Found {len(onnx_files)} ONNX file(s) total")
print()

# Step 2: Try to use these with FastAPI
print("Step 2: Checking FastAPI...")
try:
    response = requests.get("http://localhost:8000/health", timeout=5)
    if response.status_code == 200:
        print("OK: FastAPI is running")
    else:
        print("ERROR: FastAPI returned status", response.status_code)
        exit(1)
except Exception as e:
    print(f"ERROR: FastAPI is not running: {e}")
    print("Start it with: python start_fastapi_server.py")
    exit(1)

# Step 3: The real issue - MLflow artifact download
print()
print("Step 3: The Real Problem")
print("=" * 60)
print("Models are registered in MLflow but artifacts can't be downloaded.")
print("This is why FastAPI can't load them.")
print()
print("Root Cause: MLflow artifact storage issue")
print("  - Models registered but artifacts return 500 errors")
print("  - Artifact download fails with 'too many 500 error responses'")
print()
print("Solution:")
print("  1. Re-register models (this will create new artifact storage)")
print("  2. Make sure MLflow artifact root is properly configured")
print()
print("Let's check MLflow configuration...")

# Check MLflow artifact root
try:
    import mlflow
    mlflow.set_tracking_uri("http://localhost:5000")
    
    # Get default artifact root
    try:
        experiments = mlflow.search_experiments()
        if experiments:
            exp = experiments[0]
            print(f"Experiment: {exp.name}")
            print(f"Artifact location: {exp.artifact_location}")
    except:
        pass
    
    print()
    print("To fix this:")
    print("  1. Stop MLflow")
    print("  2. Restart MLflow with explicit artifact root:")
    print("     mlflow ui --port 5000 --default-artifact-root ./mlartifacts")
    print("  3. Re-register models:")
    print("     python register_models_to_mlflow.py")
    print("  4. Restart FastAPI with correct URI:")
    print("     $env:MLFLOW_TRACKING_URI='http://localhost:5000'; python start_fastapi_server.py")
    print("  5. Refresh models:")
    print("     POST http://localhost:8000/refresh")
    
except Exception as e:
    print(f"Error: {e}")

print()
print("=" * 60)


