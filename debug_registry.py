import sys
import os
import json
import logging
import lightgbm as lgb

# Configure logging to stdout
logging.basicConfig(level=logging.INFO)

# Add current dir to sys.path
sys.path.append(os.getcwd())

from utils.artifact_control.model_manager import ModelManager

def debug_load():
    print(f"CWD: {os.getcwd()}")
    mm = ModelManager()
    
    path = mm.get_local_model_path("lightgbm", "3")
    print(f"Path: {path}")
    
    if path and os.path.exists(path):
        print("Attempting to load using model_file...")
        try:
            bst = lgb.Booster(model_file=path)
            print("Success with model_file!")
        except Exception as e:
            print(f"Failed with model_file: {e}")
            
        print("Attempting to load using model_str...")
        try:
            with open(path, 'r') as f:
                content = f.read()
            bst = lgb.Booster(model_str=content)
            print("Success with model_str!")
        except Exception as e:
            print(f"Failed with model_str: {e}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    debug_load()
