import sys
print("Checking dependencies...")
deps = [
    'pandas', 'numpy', 'torch', 'joblib', 'sklearn', 'matplotlib', 'lightgbm', 'transformers'
]
for dep in deps:
    try:
        __import__(dep)
        print(f"[OK] {dep}")
    except ImportError as e:
        print(f"[MISSING] {dep}: {e}")

try:
    import utils.model_version_manager
    print("[OK] utils.model_version_manager")
except ImportError as e:
    print(f"[MISSING] utils.model_version_manager: {e}")
