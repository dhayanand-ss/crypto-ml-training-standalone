import lightgbm as lgb
import os

model_path = r"c:\Users\dhaya\crypto-ml-training-standalone\models_cache\BTCUSDT_lightgbm\6\model.lgb"

print(f"Checking if file exists: {os.path.exists(model_path)}")
print(f"File size: {os.path.getsize(model_path)} bytes")

try:
    print("Attempting to load booster natively...")
    bst = lgb.Booster(model_file=model_path)
    print("Successfully loaded booster!")
    print(f"Number of features: {bst.num_feature()}")
except Exception as e:
    print(f"Native load failed: {e}")
    import traceback
    traceback.print_exc()
