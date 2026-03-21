
import lightgbm as lgb
import os

model_path = r"c:\Users\dhaya\crypto-ml-training-standalone\models\lightgbm\v1\lgb_model.txt"
print(f"Testing model at: {model_path}")

print("\n--- Test 1: Load via model_file ---")
try:
    bst = lgb.Booster(model_file=model_path)
    print("SUCCESS: Model loaded via model_file")
except Exception as e:
    print(f"FAILURE: {e}")

print("\n--- Test 2: Load via model_str ---")
try:
    if os.path.exists(model_path):
        with open(model_path, 'r', encoding='utf-8') as f:
            content = f.read()
        bst = lgb.Booster(model_str=content)
        print("SUCCESS: Model loaded via model_str")
    else:
        print("File not found for model_str test")
except Exception as e:
    print(f"FAILURE: {e}")
