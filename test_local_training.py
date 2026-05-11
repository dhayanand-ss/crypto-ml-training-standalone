import os
import shutil
import pandas as pd
import numpy as np
import sys

# Ensure root is in path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from simplified_integrated_model import SimplifiedIntegratedModel

def test_local_training():
    print("Testing local training without MLflow...")
    
    # Create dummy data
    # Create dummy data
    dates = pd.date_range(start="2023-01-01", periods=1000, freq="H")
    df = pd.DataFrame({
        "open_time": dates, # Changed from timestamp to open_time to match expected col
        "open": np.random.rand(1000) * 100,
        "high": np.random.rand(1000) * 100,
        "low": np.random.rand(1000) * 100,
        "close": np.random.rand(1000) * 100,
        "volume": np.random.rand(1000) * 1000,
        "quote_asset_volume": np.random.rand(1000) * 1000, # Added missing expected col
        "number_of_trades": np.random.rand(1000) * 10,     # Added missing expected col
        "taker_buy_base_asset_volume": np.random.rand(1000) * 100, # Added missing expected col
        "taker_buy_quote_asset_volume": np.random.rand(1000) * 100, # Added missing expected col
    })
    
    # Create dummy sentiment data
    sentiment_df = pd.DataFrame({
        "date": dates.strftime('%Y-%m-%d'),
        "sentiment_mean": np.random.rand(1000),
        "sentiment_std": np.random.rand(1000),
        "news_count": np.random.randint(0, 10, 1000),
        "sentiment_confidence": np.random.rand(1000),
        "negative_sentiment": np.random.rand(1000),
        "neutral_sentiment": np.random.rand(1000),
        "positive_sentiment": np.random.rand(1000)
    })
    
    model = SimplifiedIntegratedModel()
    
    # Train LightGBM
    print("\nTraining LightGBM...")
    try:
        # Mocking prepare_features to accept sentiment_df is tricky if call signature is fixed
        # But wait, we can pass sentiment_df to train_lightgbm if we modify train_lightgbm signature?
        # No, train_lightgbm has default None. We need to pass it.
        # But SimplifiedIntegratedModel.train_lightgbm signature: def train_lightgbm(self, crypto_df, sentiment_df=None, force_retrain=False):
        # So we can pass it!
        
        model.train_lightgbm(df, sentiment_df=sentiment_df, force_retrain=True)
        print("LightGBM training call completed.")
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"FAILED: LightGBM training failed: {e}")
        return

    # Verify file existence
    if os.path.exists("models/lightgbm/v3/model.txt"):
        print("SUCCESS: models/lightgbm/v3/model.txt exists.")
        
        # Verify loading
        print("Verifying loadability...")
        try:
            import lightgbm as lgb
            bst = lgb.Booster(model_file="models/lightgbm/v3/model.txt")
            print("SUCCESS: Model loaded successfully.")
        except Exception as e:
            print(f"FAILED: Could not load model: {e}")
            import traceback
            traceback.print_exc()

    else:
        print("FAILED: models/lightgbm/v3/model.txt not found.")

    # Verify registry
    if os.path.exists("models/version_registry.json"):
        print("SUCCESS: models/version_registry.json exists.")
    else:
        print("FAILED: models/version_registry.json not found.")

    print("\nTest completed.")

if __name__ == "__main__":
    test_local_training()
