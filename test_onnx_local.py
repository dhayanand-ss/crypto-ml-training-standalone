import pandas as pd
import numpy as np
import onnxruntime as ort
from trainer.train_utils import preprocess_common

# Load 30 rows
try:
    df = pd.read_csv("c:/opt/airflow/custom_persistent_shared/data/prices/BTCUSDT.csv")
except Exception as e:
    df = pd.read_csv("data/prices/BTC.csv")

df["open_time"] = pd.to_datetime(df["open_time"], utc=True)
df = df.sort_values("open_time").tail(30).copy()

# Preprocess
features = preprocess_common("lightgbm", df, seq_len=30, inference=True)
feature_vector = np.array([features], dtype=np.float32)

print(f"Feature vector shape: {feature_vector.shape}")
print(f"Some features: {feature_vector[0][:5]}")

sess = ort.InferenceSession("models/onnx/lightgbm_1.onnx")
input_name = sess.get_inputs()[0].name
label_name = sess.get_outputs()[0].name
prob_name = sess.get_outputs()[1].name if len(sess.get_outputs()) > 1 else None

pred_onx = sess.run([label_name, prob_name] if prob_name else [label_name], {input_name: feature_vector})
print(f"Prediction: {pred_onx}")
