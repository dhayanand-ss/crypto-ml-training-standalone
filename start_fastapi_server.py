#!/usr/bin/env python3
"""
Start FastAPI ML Inference Server
"""
import os
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).resolve().parent
sys.path.insert(0, str(project_root))

if __name__ == "__main__":
    import uvicorn
    
    # Get port from environment or default to 8000
    port = int(os.getenv("PORT", 8000))
    host = os.getenv("HOST", "127.0.0.1")  # Use 127.0.0.1 instead of 0.0.0.0 for localhost
    
    print("=" * 60)
    print("Starting FastAPI ML Inference Server")
    print("=" * 60)
    print(f"Host: {host}")
    print(f"Port: {port}")
    print(f"URL: http://{host}:{port}")
    print(f"Docs: http://{host}:{port}/docs")
    print(f"Health: http://{host}:{port}/health")
    print("=" * 60)
    print("\nPress Ctrl+C to stop the server\n")
    
    try:
        # Enable reload in development (set RELOAD=false to disable)
        reload_enabled = os.getenv("RELOAD", "true").lower() == "true"
        
        uvicorn.run(
            "utils.serve.fastapi_app:app",
            host=host,
            port=port,
            reload=reload_enabled,  # Auto-reload on code changes
            log_level="info"
        )
    except KeyboardInterrupt:
        print("\n\nServer stopped by user")
    except Exception as e:
        print(f"\n\nError starting server: {e}")
        sys.exit(1)




