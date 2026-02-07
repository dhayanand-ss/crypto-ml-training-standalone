#!/usr/bin/env python3
"""
TST (Time Series Transformer) Training Entry Point
Wrapper script to run TST training and log status to Airflow DB.
"""

import os
import sys
import argparse
import traceback
import torch
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from trainer.time_series_transformer import TimeSeriesTransformer, TimeSeriesTransformerTrainer
import pandas as pd
import numpy as np

def main():
    parser = argparse.ArgumentParser(description="Train TST model")
    parser.add_argument("--coin", type=str, default="BTCUSDT", help="Cryptocurrency pair")
    parser.add_argument("--prices_path", type=str, default=None, help="Path to crypto prices CSV")
    parser.add_argument("--epochs", type=int, default=10, help="Training epochs")
    parser.add_argument("--use_mlflow", action="store_true", help="Enable MLflow logging")
    parser.add_argument("--use_wandb", action="store_true", help="Enable WandB logging")
    
    args = parser.parse_args()
    
    model_name = "tst"
    coin = args.coin
    
    # Setup status logging
    try:
        from utils.database.airflow_db import db
        # Update status to RUNNING
        db.set_state(model_name, coin, "RUNNING")
        print(f"Set status for {model_name}_{coin} to RUNNING")
    except Exception as e:
        print(f"Warning: Failed to connect to status DB: {e}")
        db = None

    try:
        print(f"Starting TST training for {coin}...")
        
        # Load data
        crypto_path = args.prices_path or f"data/{coin.lower()}.csv"
        
        if not os.path.exists(crypto_path):
            raise FileNotFoundError(f"Crypto data not found at {crypto_path}")
            
        print(f"Loading data from {crypto_path}...")
        crypto_df = pd.read_csv(crypto_path)
        
        # Set device
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        print(f"Using device: {device}")
        
        # Initialize Model
        # Using default parameters from the class definition or main() example
        input_dim = 7  # open, high, low, close, volume, taker_base, taker_quote (or fallback)
        
        model = TimeSeriesTransformer(
            input_dim=input_dim,
            hidden_dim=32,
            num_heads=2,
            ff_dim=64,
            num_layers=1,
            dropout=0.1,
            num_classes=3
        )
        
        # Initialize Trainer
        trainer = TimeSeriesTransformerTrainer(model, device)
        
        # Prepare Data
        # Using 15 sequence length as per main() example for efficiency
        X_train, y_train, X_test, y_test = trainer.prepare_data(
            crypto_df, 
            sequence_length=15, 
            test_size=0.2
        )
        
        # Split training data for validation (20% of training)
        val_size = int(len(X_train) * 0.2)
        X_val = X_train[-val_size:]
        y_val = y_train[-val_size:]
        X_train = X_train[:-val_size]
        y_train = y_train[:-val_size]
        
        print("Training model...")
        trainer.train(
            X_train, y_train, 
            X_val, y_val, 
            epochs=args.epochs, 
            batch_size=16 # Using 16 as per example
        )
        
        # Note: Model is saved automatically by trainer.train() using versioning
        
        # Log Success
        if db:
            db.set_state(model_name, coin, "SUCCESS")
            print(f"Set status for {model_name}_{coin} to SUCCESS")
            
    except Exception as e:
        error_msg = str(e)
        print(f"Training failed: {error_msg}")
        traceback.print_exc()
        
        if db:
            db.set_state(model_name, coin, "FAILED", error_message=error_msg)
            print(f"Set status for {model_name}_{coin} to FAILED")
        sys.exit(1)

if __name__ == "__main__":
    main()
