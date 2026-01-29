
import sys
import os
import torch
import pandas as pd
import numpy as np
from pathlib import Path

# Add project root to path
project_root = Path(__file__).resolve().parent
sys.path.insert(0, str(project_root))

from models.finbert_sentiment import FinBERTSentimentAnalyzer

def test_prediction():
    print("=" * 60)
    print("Testing TRL Model Prediction")
    print("=" * 60)

    # Model paths
    model_path = r"c:\Users\dhaya\crypto-ml-training-standalone\models\finbert\finbert_grpo.pth"
    tokenizer_path = r"c:\Users\dhaya\crypto-ml-training-standalone\models\finbert\tokenizer"

    if not os.path.exists(model_path):
        print(f"Error: Model not found at {model_path}")
        return

    try:
        # Initialize analyzer
        print("Initializing analyzer...")
        analyzer = FinBERTSentimentAnalyzer()
        
        # Load trained weights
        print(f"Loading weights from {model_path}...")
        analyzer.load_model(model_path, tokenizer_path)
        
        # Sample Data
        samples = [
            "Bitcoin surges past $100k as institutional adoption grows.",
            "Crypto markets crash due to unexpected regulatory crackdown.",
            "Market remains sideways as investors await fed decision.",
            "Ethereum upgrade successful, fees drop significantly.",
            "Major exchange hack results in loss of millions."
        ]
        
        print("\nRunning predictions on samples:")
        print("-" * 60)
        
        # Get probabilities
        probs = analyzer.predict_three_class(samples)
        
        for i, text in enumerate(samples):
            p = probs[i]
            # 0=Sell, 1=Hold, 2=Buy
            sentiment_map = {0: "SELL", 1: "HOLD", 2: "BUY"}
            decision = np.argmax(p)
            label = sentiment_map[decision]
            confidence = p[decision]
            
            print(f"Text: {text}")
            print(f"Probs: Sell={p[0]:.4f}, Hold={p[1]:.4f}, Buy={p[2]:.4f}")
            print(f"Prediction: {label} (Conf: {confidence:.2%})")
            print("-" * 60)
            
    except Exception as e:
        print(f"An error occurred: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_prediction()
