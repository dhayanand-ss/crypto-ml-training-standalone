
import lightgbm as lgb
import numpy as np
import os

def test_fresh_model():
    print("Testing fresh model creation...")
    X = np.random.rand(100, 10)
    y = np.random.randint(0, 2, 100)
    train_data = lgb.Dataset(X, label=y)
    params = {'objective': 'binary', 'verbose': -1}
    bst = lgb.train(params, train_data, num_boost_round=10)
    
    save_path = "test_model.txt"
    bst.save_model(save_path)
    print(f"Saved fresh model to {save_path}")
    
    try:
        bst_loaded = lgb.Booster(model_file=save_path)
        print("Fresh model loaded successfully!")
        return True
    except Exception as e:
        print(f"Fresh model loading failed: {e}")
        return False

def test_existing_model_content():
    model_path = r"c:\Users\dhaya\crypto-ml-training-standalone\models\lightgbm\v1\lgb_model.txt"
    print(f"\nTesting existing model at {model_path}...")
    if not os.path.exists(model_path):
        print("Model file not found.")
        return

    try:
        with open(model_path, 'r', encoding='utf-8') as f:
            content = f.read()
        print(f"File read successfully. Length: {len(content)}")
        print(f"First 50 chars: {content[:50]}")
        
        bst = lgb.Booster(model_str=content)
        print("Existing model loaded successfully via string!")
    except Exception as e:
        print(f"Existing model loading failed: {e}")

if __name__ == "__main__":
    if test_fresh_model():
        test_existing_model_content()
