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

    # Setup MLflow/WandB if enabled
    if args.use_mlflow:
        try:
            import mlflow
            mlflow.set_tracking_uri("http://localhost:5000")
            mlflow.set_experiment("crypto-ml-pipeline")
            print("MLflow logging enabled")
        except ImportError:
            print("Warning: MLflow not installed. Logging disabled.")
            args.use_mlflow = False
            
    if args.use_wandb:
        try:
            import wandb
            # wandb.init(project="crypto-ml-pipeline", entity="your-entity")
            print("WandB logging enabled (placeholder)")
        except ImportError:
            print("Warning: WandB not installed. Logging disabled.")
            args.use_wandb = False

    try:
        print(f"Starting TST training for {coin}...")
        
        # Start MLflow run if enabled
        active_run = None
        if args.use_mlflow:
            active_run = mlflow.start_run(run_name=f"tst_{coin}_training")

        
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
        
        if args.use_mlflow:
            mlflow.log_params({
                "model_type": "tst",
                "coin": coin,
                "epochs": args.epochs,
                "batch_size": 16,
                "input_dim": input_dim,
                "hidden_dim": 32,
                "num_heads": 2,
                "ff_dim": 64,
                "num_layers": 1,
                "dropout": 0.1
            })

        print("Training model...")
        trainer.train(
            X_train, y_train, 
            X_val, y_val, 
            epochs=args.epochs, 
            batch_size=16 # Using 16 as per example
        )
        
        # Evaluate and log metrics
        print("Evaluating model...")
        predictions, metrics = trainer.evaluate(
            X_test, y_test, 
            use_mlflow=args.use_mlflow, 
            use_wandb=args.use_wandb
        )
        
        if args.use_mlflow:
             # Log model artifact (the latest v3 model)
             model_path = "models/tst/v3/model.pth"
             scaler_path = "models/tst/v3/scaler.pkl"
             if os.path.exists(model_path):
                 mlflow.log_artifact(model_path, artifact_path="model")
             if os.path.exists(scaler_path):
                 mlflow.log_artifact(scaler_path, artifact_path="model")

        
        # Log Success
        if db:
            db.set_state(model_name, coin, "SUCCESS")
            print(f"Set status for {model_name}_{coin} to SUCCESS")

        # Create success marker file for SSH polling
        try:
            Path("_SUCCESS").touch()
            print("Created _SUCCESS marker file")
        except Exception as e:
            print(f"Warning: Failed to create _SUCCESS file: {e}")
            
        if active_run:
            mlflow.end_run()
            
    except Exception as e:
        error_msg = str(e)
        print(f"Training failed: {error_msg}")
        traceback.print_exc()
        
        if db:
            db.set_state(model_name, coin, "FAILED", error_message=error_msg)
            print(f"Set status for {model_name}_{coin} to FAILED")
        # End MLflow run
        if active_run:
            mlflow.end_run()
            
        sys.exit(1)

if __name__ == "__main__":
    main()
