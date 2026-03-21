
import joblib
import torch
import os

def inspect_lightgbm_features():
    path = r"c:\Users\dhaya\crypto-ml-training-standalone\models\lightgbm\v1\lgb_model_features.pkl"
    print(f"Inspecting LightGBM features at {path}...")
    if not os.path.exists(path):
        print("File not found.")
        return

    try:
        data = joblib.load(path)
        print("Keys found:", data.keys())
        if 'params' in data:
            print("Params:", data['params'])
        if 'best_score' in data:
            print("Best Score:", data['best_score'])
        if 'evals_result' in data:
            print("Evals Result keys:", data['evals_result'].keys() if data['evals_result'] else "None")
    except Exception as e:
        print(f"Failed to load: {e}")

def inspect_tst_model():
    path = r"c:\Users\dhaya\crypto-ml-training-standalone\models\tst\v1\tst_model.pth"
    print(f"\nInspecting TST model at {path}...")
    if not os.path.exists(path):
        print("File not found.")
        return

    try:
        data = torch.load(path, map_location='cpu')
        print("Type:", type(data))
        if isinstance(data, dict):
            print("Keys:", data.keys())
            # Check if it's just a state dict or has more info
            if 'model_state_dict' in data:
                print("Found model_state_dict, checking for other keys...")
                for k in data.keys():
                    if k != 'model_state_dict':
                        print(f"  {k}: {type(data[k])}")
            else:
                 print("Looks like a plain state_dict (layer names).")
    except Exception as e:
        print(f"Failed to load: {e}")

if __name__ == "__main__":
    with open("inspection_result.txt", "w", encoding="utf-8") as f:
        # Redirect stdout to file
        import sys
        original_stdout = sys.stdout
        sys.stdout = f
        
        inspect_lightgbm_features()
        inspect_tst_model()
        
        sys.stdout = original_stdout
