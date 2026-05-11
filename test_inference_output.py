import pandas as pd
import numpy as np
import requests
from trainer.train_utils import preprocess_common
import pprint

# Load 35 rows from BTCUSDT
try:
    df = pd.read_csv("c:/opt/airflow/custom_persistent_shared/data/prices/BTCUSDT.csv")
    print(f"Loaded {len(df)} rows from DB CSV")
except Exception as e:
    df = pd.read_csv("data/prices/BTC.csv") # Try local copy
    print(f"Loaded {len(df)} rows from Local CSV")

df["open_time"] = pd.to_datetime(df["open_time"], utc=True)
df = df.sort_values("open_time").tail(30).copy()

# Call preprocessor
features = preprocess_common("lightgbm", df, seq_len=30, inference=True)
feature_vector = [float(x) for x in np.array(features).flatten()]
print(f"Generated features (length {len(feature_vector)}):\n{feature_vector}")

print("\nCalling FastAPI...")
try:
    url = "http://localhost:8000/predict"
    response = requests.post(
        url,
        json={"features": [feature_vector]},
        params={"model_name": "lightgbm", "version": "v1"},
        timeout=10
    )
    print(f"Status: {response.status_code}")
    if response.status_code == 200:
        print(f"Response: {response.json()}")
    else:
        print(f"Error: {response.text}")
except Exception as e:
    print(f"Request failed: {e}")
