#!/usr/bin/env python3
"""
Test and fix FastAPI models endpoint
This script will:
1. Check MLflow connection
2. Check if models are registered
3. Register models if needed
4. Ensure models are in Production stage
5. Test FastAPI /models endpoint
"""

import os
import sys
import time
import requests
from pathlib import Path
import logging

# Add project root to path
project_root = Path(__file__).resolve().parent
sys.path.insert(0, str(project_root))

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Configuration
MLFLOW_TRACKING_URI = os.getenv("MLFLOW_TRACKING_URI", "http://localhost:5000")
FASTAPI_URL = os.getenv("FASTAPI_URL", "http://localhost:8000")


def check_mlflow_connection():
    """Check if MLflow is accessible"""
    logger.info("=" * 60)
    logger.info("Step 1: Checking MLflow Connection")
    logger.info("=" * 60)
    
    try:
        import mlflow
        mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
        experiments = mlflow.search_experiments()
        logger.info(f"✅ Connected to MLflow at {MLFLOW_TRACKING_URI}")
        logger.info(f"   Found {len(experiments)} experiment(s)")
        return True, mlflow
    except Exception as e:
        logger.error(f"❌ Failed to connect to MLflow: {e}")
        logger.error(f"   Make sure MLflow is running: mlflow ui --port 5000")
        return False, None


def check_registered_models(mlflow):
    """Check what models are registered in MLflow"""
    logger.info("")
    logger.info("=" * 60)
    logger.info("Step 2: Checking Registered Models")
    logger.info("=" * 60)
    
    try:
        from utils.artifact_control.model_manager import ModelManager
        model_manager = ModelManager(tracking_uri=MLFLOW_TRACKING_URI)
        
        registered_models = model_manager.client.search_registered_models()
        logger.info(f"Found {len(registered_models)} registered model(s)")
        
        if not registered_models:
            logger.warning("⚠️  No models registered in MLflow")
            return False, model_manager, []
        
        production_models = []
        for model in registered_models:
            model_name = model.name
            logger.info(f"\nModel: {model_name}")
            
            # Get all versions
            all_versions = model_manager.client.search_model_versions(f"name='{model_name}'")
            logger.info(f"  Total versions: {len(all_versions)}")
            
            for v in all_versions:
                stage = v.current_stage or "None"
                logger.info(f"  Version {v.version}: Stage = {stage}")
                if stage == "Production":
                    production_models.append((model_name, v.version))
        
        if production_models:
            logger.info(f"\n✅ Found {len(production_models)} Production model(s)")
            for name, version in production_models:
                logger.info(f"   - {name} v{version}")
        else:
            logger.warning("⚠️  No models in Production stage")
        
        return True, model_manager, production_models
        
    except Exception as e:
        logger.error(f"❌ Error checking models: {e}")
        import traceback
        traceback.print_exc()
        return False, None, []


def check_fastapi_running():
    """Check if FastAPI server is running"""
    logger.info("")
    logger.info("=" * 60)
    logger.info("Step 3: Checking FastAPI Server")
    logger.info("=" * 60)
    
    try:
        response = requests.get(f"{FASTAPI_URL}/health", timeout=5)
        if response.status_code == 200:
            health_data = response.json()
            logger.info(f"✅ FastAPI is running at {FASTAPI_URL}")
            logger.info(f"   Models loaded: {health_data.get('models_loaded', 0)}")
            return True
        else:
            logger.error(f"❌ FastAPI returned status {response.status_code}")
            return False
    except requests.exceptions.ConnectionError:
        logger.error(f"❌ FastAPI is not running at {FASTAPI_URL}")
        logger.error("   Start it with: python start_fastapi_server.py")
        return False
    except Exception as e:
        logger.error(f"❌ Error checking FastAPI: {e}")
        return False


def check_fastapi_debug():
    """Check FastAPI debug endpoint"""
    logger.info("")
    logger.info("=" * 60)
    logger.info("Step 4: Checking FastAPI Debug Endpoint")
    logger.info("=" * 60)
    
    try:
        response = requests.get(f"{FASTAPI_URL}/debug/mlflow", timeout=10)
        if response.status_code == 200:
            debug_data = response.json()
            logger.info(f"MLflow Tracking URI: {debug_data.get('mlflow_tracking_uri')}")
            logger.info(f"MLflow Available: {debug_data.get('mlflow_available')}")
            logger.info(f"Connection Status: {debug_data.get('connection_status')}")
            logger.info(f"Loaded Models Count: {debug_data.get('loaded_models_count', 0)}")
            
            registered = debug_data.get('registered_models', [])
            logger.info(f"Registered Models: {len(registered)}")
            for model in registered:
                logger.info(f"  - {model.get('name')}")
            
            production = debug_data.get('production_models', [])
            logger.info(f"Production Models: {len(production)}")
            for model in production:
                logger.info(f"  - {model.get('name')} v{model.get('version')} (ONNX: {model.get('onnx_available')})")
            
            errors = debug_data.get('errors', [])
            if errors:
                logger.warning("Errors found:")
                for error in errors:
                    logger.warning(f"  - {error}")
            
            return debug_data
        else:
            logger.error(f"❌ Debug endpoint returned status {response.status_code}")
            return None
    except Exception as e:
        logger.error(f"❌ Error checking debug endpoint: {e}")
        return None


def register_models_if_needed(model_manager, debug_data):
    """Register models if they don't exist"""
    logger.info("")
    logger.info("=" * 60)
    logger.info("Step 5: Registering Models (if needed)")
    logger.info("=" * 60)
    
    registered_models = debug_data.get('registered_models', []) if debug_data else []
    
    if registered_models:
        logger.info("✅ Models are already registered")
        return True
    
    logger.info("⚠️  No models registered. Running registration script...")
    
    try:
        # Import and run registration
        import subprocess
        result = subprocess.run(
            [sys.executable, "register_models_to_mlflow.py"],
            cwd=project_root,
            capture_output=True,
            text=True,
            timeout=300
        )
        
        if result.returncode == 0:
            logger.info("✅ Model registration completed")
            logger.info(result.stdout)
            return True
        else:
            logger.error("❌ Model registration failed")
            logger.error(result.stderr)
            return False
    except Exception as e:
        logger.error(f"❌ Error running registration script: {e}")
        return False


def transition_to_production(model_manager):
    """Ensure models are in Production stage"""
    logger.info("")
    logger.info("=" * 60)
    logger.info("Step 6: Ensuring Models are in Production Stage")
    logger.info("=" * 60)
    
    try:
        registered_models = model_manager.client.search_registered_models()
        
        if not registered_models:
            logger.warning("⚠️  No models to transition")
            return False
        
        transitioned = False
        for model in registered_models:
            model_name = model.name
            
            # Get all versions
            all_versions = model_manager.client.search_model_versions(f"name='{model_name}'")
            
            for v in all_versions:
                stage = v.current_stage or "None"
                if stage != "Production":
                    # Check if this is v1 or v3 (based on registration script logic)
                    # For now, transition the latest version
                    if v.version == all_versions[0].version:  # Latest version
                        try:
                            model_manager.client.transition_model_version_stage(
                                name=model_name,
                                version=v.version,
                                stage="Production"
                            )
                            logger.info(f"✅ Transitioned {model_name} v{v.version} to Production")
                            transitioned = True
                        except Exception as e:
                            logger.warning(f"⚠️  Could not transition {model_name} v{v.version}: {e}")
        
        if not transitioned:
            logger.info("✅ All models are already in Production stage")
        
        return True
    except Exception as e:
        logger.error(f"❌ Error transitioning models: {e}")
        return False


def refresh_fastapi_models():
    """Refresh models in FastAPI"""
    logger.info("")
    logger.info("=" * 60)
    logger.info("Step 7: Refreshing FastAPI Models")
    logger.info("=" * 60)
    
    try:
        response = requests.post(
            f"{FASTAPI_URL}/refresh",
            json={"model_name": None, "version": None},
            timeout=30
        )
        
        if response.status_code == 200:
            result = response.json()
            logger.info(f"✅ Models refreshed successfully")
            logger.info(f"   Status: {result.get('status')}")
            models = result.get('models', {})
            if models:
                for model_name, versions in models.items():
                    logger.info(f"   {model_name}: {versions}")
            return True
        else:
            logger.error(f"❌ Refresh failed: {response.status_code}")
            logger.error(response.text)
            return False
    except Exception as e:
        logger.error(f"❌ Error refreshing models: {e}")
        return False


def test_models_endpoint():
    """Test the /models endpoint"""
    logger.info("")
    logger.info("=" * 60)
    logger.info("Step 8: Testing /models Endpoint")
    logger.info("=" * 60)
    
    try:
        response = requests.get(f"{FASTAPI_URL}/models", timeout=10)
        
        if response.status_code == 200:
            models = response.json()
            logger.info(f"✅ /models endpoint returned {len(models)} model(s)")
            
            if models:
                logger.info("\n📋 Loaded Models:")
                for model in models:
                    logger.info(f"   - {model.get('model_name')} v{model.get('version')}")
                    logger.info(f"     Input shape: {model.get('input_shape')}")
                    logger.info(f"     Output shape: {model.get('output_shape')}")
                return True
            else:
                logger.warning("⚠️  /models endpoint returned empty list")
                return False
        else:
            logger.error(f"❌ /models endpoint returned status {response.status_code}")
            logger.error(response.text)
            return False
    except Exception as e:
        logger.error(f"❌ Error testing /models endpoint: {e}")
        return False


def main():
    """Main test and fix workflow"""
    logger.info("")
    logger.info("=" * 60)
    logger.info("FastAPI Models Test and Fix Script")
    logger.info("=" * 60)
    logger.info("")
    
    # Step 1: Check MLflow
    mlflow_ok, mlflow = check_mlflow_connection()
    if not mlflow_ok:
        logger.error("\n❌ Cannot proceed without MLflow. Please start MLflow first.")
        logger.error("   Run: mlflow ui --port 5000")
        return False
    
    # Step 2: Check registered models
    models_ok, model_manager, production_models = check_registered_models(mlflow)
    if not models_ok:
        logger.error("\n❌ Cannot proceed without ModelManager")
        return False
    
    # Step 3: Check FastAPI
    fastapi_ok = check_fastapi_running()
    if not fastapi_ok:
        logger.error("\n❌ Cannot proceed without FastAPI. Please start FastAPI first.")
        logger.error("   Run: python start_fastapi_server.py")
        return False
    
    # Step 4: Check debug endpoint
    debug_data = check_fastapi_debug()
    
    # Step 5: Register models if needed
    if not debug_data or not debug_data.get('registered_models'):
        register_models_if_needed(model_manager, debug_data)
        # Wait a bit for registration to complete
        time.sleep(2)
        # Re-check debug
        debug_data = check_fastapi_debug()
    
    # Step 6: Transition to Production
    transition_to_production(model_manager)
    
    # Step 7: Refresh FastAPI models
    refresh_fastapi_models()
    
    # Wait a bit for models to load
    time.sleep(2)
    
    # Step 8: Test /models endpoint
    success = test_models_endpoint()
    
    logger.info("")
    logger.info("=" * 60)
    if success:
        logger.info("✅ SUCCESS: Models are now visible in FastAPI!")
        logger.info(f"   View at: {FASTAPI_URL}/models")
        logger.info(f"   Or in Swagger UI: {FASTAPI_URL}/docs")
    else:
        logger.error("❌ FAILED: Models are still not visible")
        logger.error("   Check the errors above and try:")
        logger.error("   1. Ensure MLflow is running: mlflow ui --port 5000")
        logger.error("   2. Register models: python register_models_to_mlflow.py")
        logger.error("   3. Check debug endpoint: http://localhost:8000/debug/mlflow")
    logger.info("=" * 60)
    
    return success


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)


