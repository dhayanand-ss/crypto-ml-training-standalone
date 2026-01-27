
import lightgbm as lgb
import os
import traceback

paths = [
    r'c:\Users\dhaya\crypto-ml-training-standalone\models\lightgbm\v3\lgb_model.txt',
    r'c:\Users\dhaya\crypto-ml-training-standalone\models\lightgbm\v3\model.txt'
]

for p in paths:
    if os.path.exists(p):
        print(f"\nAttempting to load {p}...")
        try:
            model = lgb.Booster(model_file=p)
            print(f"Successfully loaded {p}")
            print(f"Num class: {model.num_class()}")
            print(f"Num feature: {model.num_feature()}")
        except Exception:
            print(f"Failed to load {p}")
            traceback.print_exc()
    else:
        print(f"Path does not exist: {p}")
