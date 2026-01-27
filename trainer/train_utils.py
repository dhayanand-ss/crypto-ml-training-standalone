"""
Training utilities for crypto ML models
Includes preprocessing, metrics logging, ONNX conversion, and time tracking
"""

import pandas as pd
import numpy as np
import time
import os
from typing import Optional, Dict, Any

try:
    import ta
    TA_AVAILABLE = True
except ImportError:
    TA_AVAILABLE = False
    print("Warning: 'ta' library not available. Technical indicators will be skipped.")

# Optional GCSManager import (for download_s3_dataset - aliased as S3Manager for backward compatibility)
try:
    from utils.artifact_control import S3Manager  # This is actually GCSManager
    S3_AVAILABLE = True
except ImportError:
    S3_AVAILABLE = False
    print("Warning: GCSManager not available. GCS download functions will be disabled.")


def preprocess_crypto(df, horizon=1, threshold=0.001, balanced=False):
    """
    Preprocess 1-min crypto OHLCV data for classification.
    
    Parameters:
        df : pd.DataFrame
            Must contain columns: open_time, open, high, low, close, volume,
            and optionally: close_time, quote_asset_volume, trades, taker_base, taker_quote
        horizon : int
            How many minutes ahead to predict
        threshold : float
            Threshold for Buy/Sell classification
        balanced : bool
            Whether to balance classes by undersampling
        
    Returns:
        X : pd.DataFrame
            Feature matrix
        y : pd.Series
            Labels (0=Sell, 1=Hold, 2=Buy)
    """
    
    df = df.copy()
    
    # Drop redundant columns
    if "close_time" in df.columns:
        df = df.drop(columns=["close_time"])
    
    # --- Price features ---
    df["return"] = df["close"].pct_change()
    df["log_return"] = np.log1p(df["return"])
    df["high_low_range"] = (df["high"] - df["low"]) / df["open"]
    df["close_open_range"] = (df["close"] - df["open"]) / df["open"]
    df["rolling_volatility"] = df["log_return"].rolling(30).std()
    
    # Rolling statistics
    df["rolling_mean_5"] = df["close"].rolling(5).mean()
    df["rolling_mean_15"] = df["close"].rolling(15).mean()
    df["rolling_mean_30"] = df["close"].rolling(30).mean()
    df["rolling_std_15"] = df["close"].rolling(15).std()
    
    # --- Technical indicators ---
    if TA_AVAILABLE:
        df["rsi"] = ta.momentum.RSIIndicator(df["close"], window=14).rsi()
        macd = ta.trend.MACD(df["close"])
        df["macd"] = macd.macd()
        df["macd_signal"] = macd.macd_signal()
        df["macd_diff"] = macd.macd_diff()
        bb = ta.volatility.BollingerBands(df["close"])
        df["bb_high"] = bb.bollinger_hband()
        df["bb_low"] = bb.bollinger_lband()
        df["bb_percent"] = bb.bollinger_pband()
    else:
        # Fallback: simple Bollinger Bands calculation
        sma_20 = df["close"].rolling(20).mean()
        std_20 = df["close"].rolling(20).std()
        df["bb_high"] = sma_20 + (std_20 * 2)
        df["bb_low"] = sma_20 - (std_20 * 2)
        df["bb_percent"] = (df["close"] - df["bb_low"]) / (df["bb_high"] - df["bb_low"])
        df["rsi"] = np.nan  # Placeholder
        df["macd"] = np.nan
        df["macd_signal"] = np.nan
        df["macd_diff"] = np.nan
    
    # --- Microstructure features ---
    for col in ["volume", "trades", "taker_base", "taker_quote", "quote_asset_volume"]:
        if col in df.columns:
            df[f"log_{col}"] = np.log1p(df[col])
    
    # --- Lag features ---
    for lag in [1, 3, 5, 15]:
        df[f"lag_return_{lag}"] = df["log_return"].shift(lag)
        if "log_volume" in df.columns:
            df[f"lag_volume_{lag}"] = df["log_volume"].shift(lag)
    
    # --- Label ---
    df["future_return"] = df["close"].shift(-horizon) / df["close"] - 1
    
    def label_func(x):
        if x > threshold:
            return 2  # Buy
        elif x < -threshold:
            return 0  # Sell
        else:
            return 1  # Hold
    
    df["label"] = df["future_return"].apply(label_func)
    
    if balanced:
        min_size = df["label"].value_counts().min()

        # Sample equally from each class
        df_balanced = (
            df.groupby("label", group_keys=False)
              .apply(lambda x: x.sample(min_size, random_state=42))
        )

        # Shuffle
        df_balanced = df_balanced.sample(frac=1, random_state=42).reset_index(drop=True)
        df = df_balanced
    
    # --- Cleanup ---
    
    ohlcv_cols = ["open", "high", "low", "close", "volume"]
    df[ohlcv_cols] = df[ohlcv_cols].ffill().bfill()

    # Fill engineered features with 0 (neutral signal)
    df = df.fillna(0)
    
    df = df.dropna().reset_index(drop=True)
    
    # Features / target
    X = df.drop(columns=["open_time", "label", "future_return"])
    y = df["label"]
    
    return X, y


def preprocess_sequences(df, seq_len=30, horizon=1, threshold=0.001, return_first=False, inference=False):
    """
    Convert raw OHLCV + sentiment features into sequences suitable for LSTM/Transformer.
    Returns X_seq (tensor or numpy array) and y_seq (tensor or numpy array).
    
    Parameters:
        df : pd.DataFrame
            DataFrame with OHLCV data
        seq_len : int
            Sequence length (default: 30)
        horizon : int
            How many steps ahead to predict
        threshold : float
            Threshold for Buy/Sell classification
        return_first : bool
            Whether to return sequences starting from the first timestep (padded)
        inference : bool
            If True, returns numpy arrays instead of torch tensors
    
    Returns:
        X_seq : torch.Tensor or np.ndarray
            Sequence data
        y_seq : torch.Tensor or np.ndarray
            Labels (0=Sell, 1=Hold, 2=Buy)
    """
    # Raw features per timestep
    features = ["open", "high", "low", "close", "volume"]
    
    # Add optional features if available
    optional_features = ["taker_base", "taker_quote"]
    for feat in optional_features:
        if feat in df.columns:
            features.append(feat)
    
    # Ensure we have at least the required features
    available_features = [f for f in features if f in df.columns]
    if len(available_features) < 5:
        raise ValueError(f"Required features not found. Available: {df.columns.tolist()}")
    
    X_raw = df[available_features].values.astype(float)
    
    # Label for classification: Buy(2), Hold(1), Sell(0)
    df = df.copy()
    df["future_return"] = df["close"].shift(-horizon) / df["close"] - 1
    
    def label_func(x):
        if x > threshold:
            return 2  # Buy
        elif x < -threshold:
            return 0  # Sell
        else:
            return 1  # Hold
    
    y_raw = df["future_return"].apply(label_func).values.astype(int)
    
    # Build sequences
    X_seq, y_seq = [], []
    if return_first:
        for i in range(seq_len):
            temp = [X_raw[0].tolist()]*(seq_len-i)+X_raw[:i].tolist()
            X_seq.append(temp)
            y_seq.append(y_raw[i])
            
    for i in range(len(X_raw) - seq_len):
        X_seq.append(X_raw[i:i+seq_len])
        y_seq.append(y_raw[i+seq_len])
    
    if not inference:
        import torch
        X_seq = torch.tensor(X_seq, dtype=torch.float32)
        y_seq = torch.tensor(y_seq, dtype=torch.long)
    else:
        X_seq = np.array(X_seq)
        y_seq = np.array(y_seq)
    
    return X_seq, y_seq


def annotate_news(df_prices, df_news, window_hours=12, threshold=0.005):
    """
    Annotate news articles with price change labels based on price movements.
    
    This function implements text-based labeling where:
    - Scraped articles are analyzed for average price change over specified hours
    - Labels (Buy, Hold, Sell) correspond to market reaction
    
    Process:
    1. For each article, find price BEFORE publication
    2. Calculate AVERAGE price over the next window_hours
    3. Calculate price change percentage: (avg_price_after - price_before) / price_before
    4. Assign label based on threshold:
       - Buy (2):  price_change > threshold (price increased significantly)
       - Sell (0): price_change < -threshold (price decreased significantly)
       - Hold (1): -threshold <= price_change <= threshold (neutral)
    
    Features:
    - Automatic date range validation
    - Filters news articles to only include those within price data range
    - Comprehensive logging and statistics
    - Warning system for date mismatches
    
    Parameters:
        df_prices : pd.DataFrame
            Price data with 'open_time' and 'close' columns
        df_news : pd.DataFrame
            News data with 'date', 'title', and 'text' columns
        window_hours : int
            Hours after news to measure price change (default: 12)
        threshold : float
            Threshold for Buy/Sell classification (default: 0.005 = 0.5%)
    
    Returns:
        pd.DataFrame: News dataframe with 'annotation', 'price_change', and 'label' columns
        - price_change: Percentage change in price over window
        - label: 0=Sell, 1=Hold, 2=Buy (based on market reaction)
        - annotation: Text label ('Negative', 'Neutral', 'Positive')
        
    Raises:
        ValueError: If no news articles are found within price data date range
    """
    import warnings
    
    df_prices = df_prices.copy()
    df_news = df_news.copy()
    
    # Ensure datetime columns
    if df_prices['open_time'].dtype == 'object':
        df_prices['open_time'] = pd.to_datetime(df_prices['open_time'], utc=True, format='mixed', errors='coerce')
    else:
        df_prices['open_time'] = pd.to_datetime(df_prices['open_time'], utc=True, errors='coerce')
    
    if df_news['date'].dtype == 'object':
        df_news['date'] = pd.to_datetime(df_news['date'], utc=True, format='mixed', errors='coerce')
    else:
        df_news['date'] = pd.to_datetime(df_news['date'], utc=True, errors='coerce')
    
    # Sort by time
    df_prices = df_prices.sort_values('open_time').reset_index(drop=True)
    df_news = df_news.sort_values('date').reset_index(drop=True)
    
    # Calculate date ranges
    price_min = df_prices['open_time'].min()
    price_max = df_prices['open_time'].max()
    news_min = df_news['date'].min()
    news_max = df_news['date'].max()
    
    # Log date ranges
    print(f"\nPrice data: {len(df_prices)} records from {price_min} to {price_max}")
    print(f"News data: {len(df_news)} articles from {news_min} to {news_max}")
    
    # Filter news to only include dates where price data exists (with window buffer)
    # Need to ensure we have price data for at least window_hours after news date
    effective_price_max = price_max - pd.Timedelta(hours=window_hours)
    
    initial_news_count = len(df_news)
    
    # Filter news to only dates within valid price data range
    df_news_filtered = df_news[
        (df_news['date'] >= price_min) & 
        (df_news['date'] <= effective_price_max) &
        (df_news['date'].notna())  # Exclude invalid dates
    ].copy()
    
    if len(df_news_filtered) < initial_news_count:
        filtered_count = initial_news_count - len(df_news_filtered)
        print(f"WARNING: Filtered {filtered_count} news articles outside price data range")
        print(f"  Valid range: {price_min} to {effective_price_max} (with {window_hours}h window)")
        
        if len(df_news_filtered) == 0:
            raise ValueError(
                f"No news articles found within price data range. "
                f"Price range: {price_min} to {price_max} (effective: {price_min} to {effective_price_max} with {window_hours}h window). "
                f"News range: {news_min} to {news_max}. "
                f"Please ensure news dates overlap with price data dates."
            )
    
    # Check if dates overlap (before filtering)
    if news_min > effective_price_max or news_max < price_min:
        warnings.warn(
            f"DATE MISMATCH DETECTED!\n"
            f"Price data range: {price_min} to {price_max}\n"
            f"News data range: {news_min} to {news_max}\n"
            f"Effective price max (with {window_hours}h window): {effective_price_max}\n"
            f"Filtering news to match price data range...",
            UserWarning
        )
    
    # Use filtered news for annotation
    df_news = df_news_filtered.reset_index(drop=True)
    
    if len(df_news) == 0:
        raise ValueError(
            "No news articles found within price data date range. "
            "Please ensure news dates overlap with price data dates."
        )
    
    print(f"Processing {len(df_news)} articles within valid date range")
    
    # Annotation loop
    annotations, price_change_l = [], []
    matched_count = 0
    unmatched_count = 0
    
    for idx, row in df_news.iterrows():
        news_time = row['date']
        
        # Skip if date is invalid (shouldn't happen after filtering, but safety check)
        if pd.isna(news_time):
            annotations.append('Neutral')
            price_change_l.append(0.0)
            unmatched_count += 1
            continue
        
        window_end = news_time + pd.Timedelta(hours=window_hours)
        
        # Find price at news time (before news)
        price_at_news = df_prices[df_prices['open_time'] <= news_time]
        if len(price_at_news) == 0:
            # Fallback: use first available price if no price before news
            annotations.append('Neutral')
            price_change_l.append(0.0)
            unmatched_count += 1
            continue
        
        price_before = price_at_news.iloc[-1]['close']
        
        # Find prices AFTER the news (within a time window)
        # Use average price over the window
        price_after = df_prices[
            (df_prices['open_time'] > news_time) & 
            (df_prices['open_time'] <= window_end)
        ]
        
        if len(price_after) == 0:
            # Fallback: use last available price if no price after window
            # This can happen if news is near the end of price data
            close_price = df_prices['close'].iloc[-1]
        else:
            # Get average price over the window
            close_price = price_after['close'].mean()
        
        # Calculate price change percentage
        price_change = (close_price - price_before) / price_before
        
        # Assign label based on threshold
        # Label mapping: Sell=0 (price decreased), Hold=1 (neutral), Buy=2 (price increased)
        if price_change > threshold:
            annotation = 'Positive'
            label = 2  # Buy (price increased > threshold)
        elif price_change < -threshold:
            annotation = 'Negative'
            label = 0  # Sell (price decreased > threshold)
        else:
            annotation = 'Neutral'
            label = 1  # Hold (price change within threshold range)
        
        annotations.append(annotation)
        price_change_l.append(price_change)
        matched_count += 1
    
    # Ensure news text formatting
    if 'text' in df_news.columns:
        df_news['text'] = df_news['text'].apply(lambda x: x if isinstance(x, (str, list)) else "")
        df_news['text'] = df_news['text'].apply(lambda x: '\n'.join(x) if isinstance(x, list) else x)
    
    # Add columns to news dataframe
    df_news['annotation'] = annotations
    df_news['price_change'] = price_change_l
    df_news['label'] = [{'Positive': 2, 'Negative': 0, 'Neutral': 1}[a] for a in annotations]
    
    # Report annotation statistics
    label_counts = pd.Series(df_news['label']).value_counts()
    buy_count = label_counts.get(2, 0)   # Buy = 2 (price increased)
    sell_count = label_counts.get(0, 0)  # Sell = 0 (price decreased)
    hold_count = label_counts.get(1, 0)  # Hold = 1 (neutral)
    
    print(f"\nAnnotation Results:")
    print(f"  Matched articles: {matched_count}/{len(df_news)}")
    print(f"  Unmatched articles: {unmatched_count}/{len(df_news)}")
    print(f"\nLabel Distribution (based on {window_hours}-hour price change):")
    print(f"  Buy (2):  {buy_count} ({100*buy_count/len(annotations):.1f}%) - Price increased > {threshold*100:.2f}%")
    print(f"  Sell (0): {sell_count} ({100*sell_count/len(annotations):.1f}%) - Price decreased > {threshold*100:.2f}%")
    print(f"  Hold (1): {hold_count} ({100*hold_count/len(annotations):.1f}%) - Price change within ±{threshold*100:.2f}%")
    
    # Price change statistics
    if len(price_change_l) > 0:
        price_changes = pd.Series(price_change_l)
        print(f"\nPrice Change Statistics:")
        print(f"  Mean: {price_changes.mean():.4f} ({price_changes.mean()*100:.2f}%)")
        print(f"  Std: {price_changes.std():.4f}")
        print(f"  Min: {price_changes.min():.4f} ({price_changes.min()*100:.2f}%)")
        print(f"  Max: {price_changes.max():.4f} ({price_changes.max()*100:.2f}%)")
    
    # Warning if all labels are hold
    if hold_count == len(annotations) and len(annotations) > 0:
        warnings.warn(
            "ALL LABELS ARE HOLD! This may indicate a date mismatch issue or "
            "price changes are all within the threshold range. "
            "Check that news dates overlap with price data dates and consider adjusting the threshold.",
            UserWarning
        )
    
    return df_news


def validate_news_dataset(df):
    """
    Validate news dataset structure.
    
    Args:
        df: News DataFrame
        
    Returns:
        Dictionary with validation results
    """
    issues = []
    
    # Check required columns
    required_cols = ['title', 'text', 'date']
    for col in required_cols:
        if col not in df.columns:
            issues.append(f"Missing required column: {col}")
    
    # Check if empty
    if len(df) == 0:
        issues.append("Dataset is empty")
    
    # Check for date column
    if 'date' in df.columns:
        valid_dates = pd.to_datetime(df['date'], errors='coerce').notna().sum()
        if valid_dates < len(df) * 0.8:
            issues.append(f"Only {valid_dates}/{len(df)} articles have valid dates")
    
    # Check for label column (if annotation done)
    if 'label' in df.columns:
        label_counts = df['label'].value_counts()
        if len(label_counts) < 2:
            issues.append("Labels are not balanced (needs at least 2 classes)")
    
    return {
        'valid': len(issues) == 0,
        'issues': issues
    }


def preprocess_common(model, df, seq_len=30, horizon=1, threshold=0.00015, return_first=True, inference=True):
    """
    Common preprocessing for single prediction (inference).
    
    Parameters:
        model : str
            Model type: "tst" or "lightgbm"
        df : pd.DataFrame
            Input data
        seq_len : int
            Sequence length for TST (default: 30)
        horizon : int
            Prediction horizon
        threshold : float
            Classification threshold
        return_first : bool
            Whether to return first sequence (for TST)
        inference : bool
            Whether this is for inference
    
    Returns:
        X : list or array
            Preprocessed features for single prediction
    """
    if model == "tst":
        X, _ = preprocess_sequences(df, seq_len=seq_len, horizon=horizon, threshold=threshold, 
                                    return_first=return_first, inference=inference)
        if isinstance(X, np.ndarray):
            X = X[-1].tolist()
        else:
            X = X[-1].tolist()
        
    elif model == "lightgbm":
        X, _ = preprocess_crypto(df, horizon=horizon, threshold=threshold, balanced=False)
        print(f"Preprocessed {len(X)} rows for LightGBM")
        X = X[-1:].values.tolist()[0]
    else:
        raise ValueError(f"Unknown model type: {model}")
    
    return X


def preprocess_common_batch(model, df, seq_len=30, horizon=1, threshold=0.00015, return_first=True, inference=True):
    """
    Common preprocessing for batch predictions (inference).
    
    Parameters:
        model : str
            Model type: "tst" or "lightgbm"
        df : pd.DataFrame
            Input data
        seq_len : int
            Sequence length for TST (default: 30)
        horizon : int
            Prediction horizon
        threshold : float
            Classification threshold
        return_first : bool
            Whether to return first sequence (for TST)
        inference : bool
            Whether this is for inference
    
    Returns:
        X : list or array
            Preprocessed features for batch predictions
    """
    if model == "tst":
        X, _ = preprocess_sequences(df, seq_len=seq_len, horizon=horizon, threshold=threshold, 
                                    return_first=return_first, inference=inference)
        if isinstance(X, np.ndarray):
            X = X.tolist()
        else:
            X = X.tolist()
        
    elif model == "lightgbm":
        X, _ = preprocess_crypto(df, horizon=horizon, threshold=threshold, balanced=False)
        print(f"Preprocessed {len(X)} rows for LightGBM")
        X = X.values.tolist()
    else:
        raise ValueError(f"Unknown model type: {model}")
    
    return X


def log_classification_metrics(y_pred, y_true, name="val", step=None, class_labels=None, use_mlflow=True, use_wandb=True):
    """
    Log classification metrics to MLflow and/or WandB.
    
    Parameters:
        y_pred : array-like
            Predicted labels
        y_true : array-like
            True labels
        name : str
            Metric name prefix (default: "val")
        step : int, optional
            Step number for logging
        class_labels : list, optional
            Custom class labels
        use_mlflow : bool
            Whether to log to MLflow (default: True)
        use_wandb : bool
            Whether to log to WandB (default: True)
    
    Returns:
        dict : Classification report dictionary
    """
    from sklearn.metrics import classification_report
    
    report = classification_report(y_true, y_pred, output_dict=True)

    if class_labels is None:
        class_labels = [k for k in report.keys() if k not in ["accuracy", "macro avg", "weighted avg"]]

    metrics_dict = {}
    for cls in class_labels:
        metrics_dict[f"{name}_f1_class_{cls}"] = report[cls]["f1-score"]
    
    metrics_dict[f"{name}_f1_macro"] = report["macro avg"]["f1-score"]
    metrics_dict[f"{name}_accuracy"] = report["accuracy"]
    
    # Log to MLflow if available
    if use_mlflow:
        try:
            import mlflow
            for cls in class_labels:
                mlflow.log_metric(f"{name}_f1_class_{cls}", report[cls]["f1-score"], step=step)
            mlflow.log_metric(f"{name}_f1_macro", report["macro avg"]["f1-score"], step=step)
            mlflow.log_metric(f"{name}_accuracy", report["accuracy"], step=step)
        except ImportError:
            print("Warning: MLflow not available. Skipping MLflow logging.")
        except Exception as e:
            print(f"Warning: Failed to log to MLflow: {e}")
    
    # Log to WandB if available
    if use_wandb:
        try:
            import wandb
            wandb.log(metrics_dict)
        except ImportError:
            print("Warning: WandB not available. Skipping WandB logging.")
        except Exception as e:
            print(f"Warning: Failed to log to WandB: {e}")
    
    return report


def convert_to_onnx(model, type="lightgbm", tokenizer=None, sample_input=None):
    """
    Convert a model to an ONNX object in memory.
    Returns an ONNX model object suitable for mlflow.onnx.log_model.
    
    Parameters:
        model : model object
            The model to convert (LightGBM Booster, PyTorch model, or Transformers model)
        type : str
            Model type: "lightgbm", "pytorch", or "transformers"
        tokenizer : optional
            Tokenizer for transformers models
        sample_input : optional
            Sample input for PyTorch/LightGBM models
    
    Returns:
        onnx_model : ONNX model object
    """
    if type == "transformers":
        try:
            from transformers.onnx import FeaturesManager, export as onnx_export
            from pathlib import Path
            import onnx

            feature = "sequence-classification"
            model_kind, onnx_config_class = FeaturesManager.check_supported_model_or_raise(
                model, feature=feature
            )
            onnx_config = onnx_config_class(model.config)

            # Export to a temporary path (required by export)
            output_path = Path("temp_transformers.onnx")
            onnx_inputs, onnx_outputs = onnx_export(
                preprocessor=tokenizer,
                model=model,
                config=onnx_config,
                opset=17,
                output=output_path,
            )
            # Load the ONNX model object in memory
            onnx_model = onnx.load(str(output_path))
            # Clean up temp file
            if output_path.exists():
                output_path.unlink()
            return onnx_model
        except ImportError:
            raise ImportError("transformers library required for transformers model conversion")
        except Exception as e:
            raise RuntimeError(f"Failed to convert transformers model to ONNX: {e}")

    elif type == "pytorch":
        try:
            import torch
            import io
            import onnx

            f = io.BytesIO()
            torch.onnx.export(
                model,
                sample_input,
                f,
                input_names=["input"],
                output_names=["output"],
                opset_version=14,
                dynamic_axes={"input": {0: "batch_size"}, "output": {0: "batch_size"}},
            )
            f.seek(0)
            onnx_model = onnx.load_model(f)
            return onnx_model
        except ImportError:
            raise ImportError("torch and onnx libraries required for PyTorch model conversion")
        except Exception as e:
            raise RuntimeError(f"Failed to convert PyTorch model to ONNX: {e}")

    elif type == "lightgbm":
        try:
            import onnxmltools
            from onnxmltools.convert.common.data_types import FloatTensorType
            
            if sample_input is None:
                raise ValueError("sample_input is required for LightGBM ONNX conversion")
            
            onnx_model = onnxmltools.convert_lightgbm(
                model, 
                name="lgbm_model", 
                initial_types=[("float_input", FloatTensorType([None, sample_input.shape[1]]))]
            )
            return onnx_model
        except ImportError:
            raise ImportError("onnxmltools library required for LightGBM model conversion")
        except Exception as e:
            raise RuntimeError(f"Failed to convert LightGBM model to ONNX: {e}")
    else:
        raise ValueError(f"Unknown model type: {type}")


# Time tracking utilities
START_FILE = "train_start_time.txt"


def save_start_time(path=START_FILE):
    """Save the current time to a file."""
    with open(path, "w") as f:
        f.write(str(time.time()))


def load_start_time(path=START_FILE):
    """Load start time from file, or create it if missing."""
    if not os.path.exists(path):
        save_start_time(path)
    with open(path, "r") as f:
        return float(f.read().strip())


def download_s3_dataset(coin, trl_model=False):
    """
    Download dataset from GCS (requires GCSManager/S3Manager).
    
    Parameters:
        coin : str
            Coin symbol
        trl_model : bool
            Whether to download articles for TRL model
    
    Note: This function requires GCSManager to be available.
    """
    if not S3_AVAILABLE:
        raise ImportError("GCSManager not available. Cannot download from GCS.")
    
    # S3Manager is aliased to GCSManager in __init__.py
    gcs_manager = S3Manager(bucket='mlops-new')
    
    # Use environment variable or default to local data directory
    data_base_path = os.getenv("DATA_PATH", "data")
    
    coins = ["BTCUSDT"] if trl_model else [coin]
    if trl_model:
        article_path = os.path.join(data_base_path, "articles", "articles.csv")
        os.makedirs(os.path.dirname(article_path), exist_ok=True)
        gcs_manager.download_df(article_path, key=f'articles/articles.parquet')
        
    for coin in coins:
        price_test_path = os.path.join(data_base_path, "prices", f"{coin}_test.csv")
        os.makedirs(os.path.dirname(price_test_path), exist_ok=True)
        gcs_manager.download_df(price_test_path, key=f'prices/{coin}_test.parquet')
    
        prices_path = os.path.join(data_base_path, "prices", f"{coin}.csv")
        os.makedirs(os.path.dirname(prices_path), exist_ok=True)
        gcs_manager.download_df(prices_path, key=f'prices/{coin}.parquet')
