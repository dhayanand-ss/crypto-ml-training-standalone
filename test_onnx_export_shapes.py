import onnxmltools
from onnxmltools.convert.common.data_types import FloatTensorType
import lightgbm as lgb
import onnxruntime as ort
import numpy as np

# Create dumpy lgb model
X = np.random.rand(100, 35)
y = np.random.randint(0, 3, 100)
train_data = lgb.Dataset(X, label=y)
model = lgb.train({'objective': 'multiclass', 'num_class': 3}, train_data, 1)

shape = [1, 35]
initial_type = [('float_input', FloatTensorType(shape))]
onnx_model = onnxmltools.convert_lightgbm(model, initial_types=initial_type)
path = f"models/onnx/test_one.onnx"
with open(path, "wb") as f:
    f.write(onnx_model.SerializeToString())

# Test loading
sess = ort.InferenceSession(path)

# Test batch size 2
try:
    test_X = np.random.rand(2, 35).astype(np.float32)
    input_name = sess.get_inputs()[0].name
    res = sess.run(None, {input_name: test_X})
    print("SUCCESS batch 2")
except Exception as e:
    print(f"FAILED batch 2: {e}")

# What if shape is [None, 35] but we use skl2onnx? Wait, skl2onnx doesn't convert LightGBM natively without onnxmltools.
# What if we use string "None" via onnxmltools?
try:
    initial_type = [('float_input', FloatTensorType([None, 35]))]
    onnx_model = onnxmltools.convert_lightgbm(model, initial_types=initial_type, target_opset=14)
    with open("models/onnx/test_none.onnx", "wb") as f:
        f.write(onnx_model.SerializeToString())
    sess = ort.InferenceSession("models/onnx/test_none.onnx")
    res = sess.run(None, {sess.get_inputs()[0].name: test_X})
    print("SUCCESS batch 2 with None")
except Exception as e:
    print(f"FAILED None: {e}")
