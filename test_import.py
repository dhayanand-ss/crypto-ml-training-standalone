import sys
import os
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(current_dir)
print(f"CWD: {os.getcwd()}")
print(f"Script Dir: {current_dir}")
print("sys.path:")
for p in sys.path:
    print(f"  {p}")

try:
    print("Attempting to import utils.model_version_manager...")
    import utils.model_version_manager
    print("SUCCESS: import utils.model_version_manager")
except Exception as e:
    print(f"FAILED: {e}")

try:
    print("Attempting to import simplified_integrated_model...")
    from simplified_integrated_model import SimplifiedIntegratedModel
    print("SUCCESS: import SimplifiedIntegratedModel")
except Exception as e:
    import traceback
    traceback.print_exc()
    print(f"FAILED: {e}")
