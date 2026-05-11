"""
LightGBM Trainer — with full Weights & Biases integration.

Fixes applied vs. original:
  [CRITICAL] No random seeds → seed set via params['seed'] (was 'random_state', an invalid LGB key).
  [WARNING]  RSI calculation: division by zero when all gains or losses are 0 → epsilon guard added.
  [WARNING]  bb_position: division by zero when bb_upper == bb_lower → epsilon guard added.
  [WARNING]  TimeSeriesSplit should replace KFold for cross-validation on temporal data.
  [WARNING]  Duplicate argparse.ArgumentParser() and duplicate add_argument() in main() → fixed.
  [SUGGESTION] W&B logging was a bool flag passed through but never initialised → fully integrated.
"""

from __future__ import annotations

# ─────────────────────────────────────────────────────────────────────────────
# W&B CONFIGURATION — single source of truth for ALL hyperparameters
# ─────────────────────────────────────────────────────────────────────────────
LGB_WANDB_CONFIG: dict = {
    # ── project metadata ──────────────────────────────────────────────────────
    "project":   "crypto-ml-lgbm",
    "entity":    None,            # override via WANDB_ENTITY env var or here
    "job_type":  "train",
    "tags":      ["lightgbm", "gbdt", "crypto", "3-class"],

    # ── LightGBM params ───────────────────────────────────────────────────────
    "objective":        "multiclass",
    "metric":           "multi_logloss",
    "num_class":        3,
    "boosting_type":    "gbdt",
    "num_leaves":       31,
    "learning_rate":    0.05,
    "feature_fraction": 0.9,
    "bagging_fraction": 0.8,
    "bagging_freq":     5,
    "seed":             42,      # NOTE: 'seed' is the correct LightGBM key (not 'random_state')
    "verbose":          -1,

    # ── training schedule ─────────────────────────────────────────────────────
    "num_boost_round":        1000,
    "early_stopping_rounds":  100,
    "log_evaluation_freq":    100,

    # ── data splits ───────────────────────────────────────────────────────────
    "test_size":       0.2,
    "cv_folds":        5,
    "label_threshold": 0.00015,
}

# W&B Sweep config for LightGBM hyperparameter search
LGB_SWEEP_CONFIG: dict = {
    "method": "bayes",
    "metric": {"name": "lgbm/valid/multi_logloss", "goal": "minimize"},
    "parameters": {
        "num_leaves":       {"distribution": "int_uniform", "min": 15,   "max": 127},
        "learning_rate":    {"distribution": "log_uniform_values", "min": 0.005, "max": 0.2},
        "feature_fraction": {"distribution": "uniform", "min": 0.5, "max": 1.0},
        "bagging_fraction": {"distribution": "uniform", "min": 0.5, "max": 1.0},
        "min_child_samples":{"distribution": "int_uniform", "min": 5,    "max": 100},
    },
}

# ─────────────────────────────────────────────────────────────────────────────
# Standard imports
# ─────────────────────────────────────────────────────────────────────────────
import os
import warnings
warnings.filterwarnings("ignore")

import joblib
import lightgbm as lgb
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from pathlib import Path
from sklearn.metrics import (
    accuracy_score, classification_report, f1_score, confusion_matrix,
)
from sklearn.model_selection import TimeSeriesSplit

# Optional W&B
try:
    import wandb
    _WANDB_AVAILABLE = True
except ImportError:
    _WANDB_AVAILABLE = False

# Optional train_utils
try:
    from trainer.train_utils import (
        preprocess_crypto, log_classification_metrics,
        save_start_time, load_start_time,
    )
    TRAIN_UTILS_AVAILABLE = True
except ImportError:
    TRAIN_UTILS_AVAILABLE = False


# ─────────────────────────────────────────────────────────────────────────────
# W&B LightGBM callback
# ─────────────────────────────────────────────────────────────────────────────

def _make_wandb_callback(use_wandb: bool = True):
    """
    Return a LightGBM callback that streams per-iteration metrics to W&B.

    LightGBM passes an `env` object whose `evaluation_result_list` contains
    tuples of (dataset_name, metric_name, value, is_higher_better).
    """
    def callback(env):
        if not use_wandb or not _WANDB_AVAILABLE or wandb.run is None:
            return
        metrics: dict = {"lgbm/iteration": env.iteration}
        for dataset_name, metric_name, value, _ in env.evaluation_result_list:
            metrics[f"lgbm/{dataset_name}/{metric_name}"] = value

        # Alert on NaN metric
        if any(
            isinstance(v, float) and (v != v)   # NaN check without math import
            for v in metrics.values()
        ):
            wandb.alert(
                title="NaN LightGBM Metric",
                text=f"A metric became NaN at iteration {env.iteration}",
                level=wandb.AlertLevel.ERROR,
            )
        wandb.log(metrics)

    callback.order = 10   # run after built-in callbacks
    return callback


# ─────────────────────────────────────────────────────────────────────────────
# Trainer
# ─────────────────────────────────────────────────────────────────────────────

class LightGBMTrainer:
    """
    LightGBM trainer for 3-class cryptocurrency price prediction.

    W&B integration:
      • wandb.init()          — project/entity/config
      • Per-iteration logging — loss curves via custom callback
      • Feature importance    — wandb.plot.bar chart
      • Confusion matrix      — wandb.plot.confusion_matrix
      • Class distribution    — wandb.Table
      • Artifacts             — model .txt + features .pkl
      • wandb.alert()         — NaN metric detection
      • wandb.finish()        — clean run close
    """

    def __init__(self, params: dict = None) -> None:
        # Build params from LGB_WANDB_CONFIG so all hyperparms live in one place
        cfg = LGB_WANDB_CONFIG
        self.params: dict = params or {
            "objective":        cfg["objective"],
            "metric":           cfg["metric"],
            "num_class":        cfg["num_class"],
            "boosting_type":    cfg["boosting_type"],
            "num_leaves":       cfg["num_leaves"],
            "learning_rate":    cfg["learning_rate"],
            "feature_fraction": cfg["feature_fraction"],
            "bagging_fraction": cfg["bagging_fraction"],
            "bagging_freq":     cfg["bagging_freq"],
            "seed":             cfg["seed"],     # correct LightGBM key
            "verbose":          cfg["verbose"],
        }
        self.model             = None
        self.feature_names:  list  = None
        self.feature_importance    = None
        self.evals_result_         = None
        self.best_iteration_: int  = None
        self.best_score_           = None

    # ── Feature engineering ───────────────────────────────────────────────────

    def prepare_features(
        self,
        crypto_df:    pd.DataFrame,
        sentiment_df: pd.DataFrame = None,
    ) -> tuple[np.ndarray, np.ndarray, list]:
        """
        Compute technical indicators, merge sentiment, and build (X, y).

        All division operations include an epsilon guard to prevent NaN/Inf
        in edge cases (e.g. flat price candles, zero volume).
        """
        print("Preparing features for LightGBM…")
        df = crypto_df.copy()

        # Ensure date column
        if "date" not in df.columns and "open_time" in df.columns:
            df["date"] = pd.to_datetime(df["open_time"])

        # ── Price features ────────────────────────────────────────────────
        df["price_change"]    = df["close"].pct_change()
        df["high_low_ratio"]  = df["high"]  / (df["low"]   + 1e-9)
        df["open_close_ratio"]= df["open"]  / (df["close"] + 1e-9)

        # ── Moving averages ───────────────────────────────────────────────
        for w in [5, 10, 20, 50]:
            df[f"sma_{w}"] = df["close"].rolling(w).mean()
        df["sma_5_ratio"]  = df["close"] / (df["sma_5"]  + 1e-9)
        df["sma_20_ratio"] = df["close"] / (df["sma_20"] + 1e-9)

        # ── Volatility ────────────────────────────────────────────────────
        for w in [5, 10, 20]:
            df[f"volatility_{w}"] = df["price_change"].rolling(w).std()

        # ── Volume ────────────────────────────────────────────────────────
        df["volume_sma_5"] = df["volume"].rolling(5).mean()
        df["volume_ratio"] = df["volume"] / (df["volume_sma_5"] + 1e-9)

        # ── RSI (epsilon guard against division by zero) ──────────────────
        df["rsi"] = self.calculate_rsi(df["close"])

        # ── Bollinger Bands ───────────────────────────────────────────────
        std20          = df["close"].rolling(20).std()
        df["bb_upper"] = df["sma_20"] + 2 * std20
        df["bb_lower"] = df["sma_20"] - 2 * std20
        band_width     = (df["bb_upper"] - df["bb_lower"]).replace(0, np.nan)
        df["bb_position"] = (df["close"] - df["bb_lower"]) / band_width
        df["bb_position"] = df["bb_position"].fillna(0.5)   # flat band → neutral

        # ── Sentiment ─────────────────────────────────────────────────────
        if sentiment_df is None:
            raise ValueError(
                "sentiment_df is required for LightGBM training. "
                "Pass a DataFrame with daily sentiment features."
            )

        # Normalise dates to plain YYYY-MM-DD strings (avoids tz issues)
        df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.strftime("%Y-%m-%d")
        sentiment_df = sentiment_df.copy()
        sentiment_df["date"] = (
            pd.to_datetime(sentiment_df["date"], errors="coerce", utc=True)
            .dt.strftime("%Y-%m-%d")
        )

        df = df.merge(sentiment_df, on="date", how="left")

        sentiment_cols = [
            "sentiment_mean", "sentiment_std", "news_count",
            "sentiment_confidence", "negative_sentiment",
            "neutral_sentiment", "positive_sentiment",
        ]
        for col in sentiment_cols:
            if col in df.columns:
                fill = df[col].mean()
                df[col] = df[col].fillna(0 if pd.isna(fill) else fill)

        # ── Target variable: forward-looking 3-class label ────────────────
        threshold = LGB_WANDB_CONFIG["label_threshold"]
        pct_change = (df["close"].shift(-1) - df["close"]) / (df["close"] + 1e-9)
        df["target"] = self._label_price_change(pct_change, threshold)

        # ── Feature selection ─────────────────────────────────────────────
        feature_cols = [
            c for c in df.columns
            if c not in ("date", "target") and not c.startswith("open_time")
        ]

        print(f"DEBUG before dropna: shape={df.shape}")
        print(f"NaN counts:\n{df[feature_cols + ['target']].isna().sum().to_string()}")

        # Drop entirely-empty columns
        valid_cols = [c for c in feature_cols if not df[c].isna().all()]
        if not valid_cols:
            raise ValueError("All feature columns are entirely NaN — cannot train.")
        feature_cols = valid_cols

        df = df.dropna(subset=feature_cols + ["target"])
        if len(df) == 0:
            raise ValueError(
                "0 samples remain after dropna. Check raw data for excessive NaNs."
            )

        X = df[feature_cols].values
        y = df["target"].values.astype(int)
        self.feature_names = feature_cols

        print(f"Features: {len(feature_cols)}  Samples: {len(X)}")
        print(f"Target distribution: {np.bincount(y)}")
        return X, y, feature_cols

    def calculate_rsi(self, prices: pd.Series, window: int = 14) -> pd.Series:
        """
        Wilder's RSI with an epsilon guard.

        When all candles in the window are gains (loss=0) or all are losses
        (gain=0) the standard formula produces +Inf / NaN. We add 1e-9 to
        the denominator to keep values finite.
        """
        delta = prices.diff()
        gain  = delta.where(delta > 0, 0.0).rolling(window).mean()
        loss  = (-delta.where(delta < 0, 0.0)).rolling(window).mean()
        rs    = gain / (loss + 1e-9)
        return 100.0 - (100.0 / (1.0 + rs))

    def _label_price_change(
        self,
        price_change_pct,
        threshold: float = 0.00015,
    ) -> int | np.ndarray:
        pct    = np.asarray(price_change_pct, dtype=float)
        labels = np.ones_like(pct, dtype=int)      # default = Hold
        labels[pct >  threshold] = 2               # Buy
        labels[pct < -threshold] = 0               # Sell
        return int(labels.item()) if pct.ndim == 0 else labels

    # ── Training ─────────────────────────────────────────────────────────────

    def train(
        self,
        X:          np.ndarray,
        y:          np.ndarray,
        test_size:  float = 0.2,
        cv_folds:   int   = 5,
        use_wandb:  bool  = False,
        coin:       str   = "BTCUSDT",
    ) -> tuple:
        """
        Train the LightGBM model with optional W&B logging.

        Returns (X_test, y_test, y_pred, y_pred_proba, accuracy).
        """
        print("Training LightGBM model…")

        # ── W&B initialisation ────────────────────────────────────────────
        if use_wandb and _WANDB_AVAILABLE:
            wandb.init(
                project  = LGB_WANDB_CONFIG["project"],
                entity   = LGB_WANDB_CONFIG.get("entity"),
                config   = {**LGB_WANDB_CONFIG, "coin": coin},
                job_type = LGB_WANDB_CONFIG["job_type"],
                tags     = LGB_WANDB_CONFIG["tags"] + [coin],
                name     = f"lgbm-{coin}-{wandb.util.generate_id()}",
                reinit   = True,
            )
            # Log class distribution
            counts = np.bincount(y, minlength=3)
            dist_tbl = wandb.Table(
                columns=["class", "count"],
                data=[[c, int(n)] for c, n in zip(["Sell", "Hold", "Buy"], counts)],
            )
            wandb.log({
                "dataset/total_samples":      len(X),
                "dataset/class_distribution": wandb.plot.bar(
                    dist_tbl, "class", "count", title="Class Distribution"
                ),
            })
        else:
            use_wandb = False

        # ── Temporal train/test split (no shuffle for time series) ────────
        split_idx    = int(len(X) * (1 - test_size))
        X_train, X_test = X[:split_idx],  X[split_idx:]
        y_train, y_test = y[:split_idx],  y[split_idx:]

        train_data = lgb.Dataset(X_train, label=y_train,
                                 feature_name=self.feature_names)
        test_data  = lgb.Dataset(X_test,  label=y_test,
                                 reference=train_data,
                                 feature_name=self.feature_names)

        # ── Build callbacks ───────────────────────────────────────────────
        callbacks = [
            lgb.early_stopping(LGB_WANDB_CONFIG["early_stopping_rounds"]),
            lgb.log_evaluation(LGB_WANDB_CONFIG["log_evaluation_freq"]),
        ]
        if use_wandb:
            callbacks.append(_make_wandb_callback(use_wandb=True))

        # ── Train ─────────────────────────────────────────────────────────
        self.model = lgb.train(
            self.params,
            train_data,
            valid_sets  = [train_data, test_data],
            valid_names = ["train", "valid"],
            num_boost_round = LGB_WANDB_CONFIG["num_boost_round"],
            callbacks   = callbacks,
        )

        # Preserve metadata (evals_result lost after model reload)
        self.evals_result_  = getattr(self.model, "evals_result", None)
        self.best_iteration_= getattr(self.model, "best_iteration", None)
        self.best_score_    = getattr(self.model, "best_score",    None)

        # ── Predictions & metrics ─────────────────────────────────────────
        y_pred_proba = self.model.predict(
            X_test, num_iteration=self.model.best_iteration
        )
        y_pred    = np.argmax(y_pred_proba, axis=1)
        accuracy  = accuracy_score(y_test, y_pred)
        f1_mac    = f1_score(y_test, y_pred, average="macro", zero_division=0)
        CLASS_NAMES = ["Sell", "Hold", "Buy"]

        print(f"LightGBM Accuracy: {accuracy:.4f}  F1-macro: {f1_mac:.4f}")
        print("\nClassification Report:")
        print(classification_report(y_test, y_pred, target_names=CLASS_NAMES))

        # ── Feature importance ────────────────────────────────────────────
        self.feature_importance = pd.DataFrame({
            "feature":    self.feature_names,
            "importance": self.model.feature_importance(importance_type="gain"),
        }).sort_values("importance", ascending=False)
        print("\nTop 10 Features:")
        print(self.feature_importance.head(10).to_string(index=False))

        # ── Temporal cross-validation ─────────────────────────────────────
        # TimeSeriesSplit respects temporal ordering (no future leakage)
        tscv      = TimeSeriesSplit(n_splits=cv_folds)
        cv_scores = []
        for fold_train_idx, fold_val_idx in tscv.split(X):
            lgb_fold = lgb.LGBMClassifier(**self.params)
            lgb_fold.fit(X[fold_train_idx], y[fold_train_idx])
            fold_pred = lgb_fold.predict(X[fold_val_idx])
            cv_scores.append(accuracy_score(y[fold_val_idx], fold_pred))
        cv_scores = np.array(cv_scores)
        print(f"\nTimeSeriesSplit CV: {cv_scores}  mean={cv_scores.mean():.3f} ±{cv_scores.std()*2:.3f}")

        # ── Log to train_utils if available ──────────────────────────────
        if TRAIN_UTILS_AVAILABLE:
            try:
                log_classification_metrics(
                    y_pred, y_test, name="lightgbm_val",
                    class_labels=["0", "1", "2"],
                    use_mlflow=False, use_wandb=use_wandb,
                )
            except Exception as e:
                print(f"Warning: log_classification_metrics: {e}")

        # ── W&B post-training logging ─────────────────────────────────────
        if use_wandb:
            # Confusion matrix
            wandb.log({
                "val/accuracy":         accuracy,
                "val/f1_macro":         f1_mac,
                "val/best_iteration":   self.best_iteration_,
                "val/confusion_matrix": wandb.plot.confusion_matrix(
                    probs=None,
                    y_true=y_test.tolist(),
                    preds=y_pred.tolist(),
                    class_names=CLASS_NAMES,
                ),
                "cv/mean_accuracy":  float(cv_scores.mean()),
                "cv/std_accuracy":   float(cv_scores.std()),
            })

            # Feature importance bar chart
            top20 = self.feature_importance.head(20)
            fi_tbl = wandb.Table(
                columns=["feature", "importance"],
                data=top20.values.tolist(),
            )
            wandb.log({
                "features/importance_chart": wandb.plot.bar(
                    fi_tbl, "feature", "importance",
                    title="Top-20 Feature Importance (gain)"
                )
            })

        return X_test, y_test, y_pred, y_pred_proba, accuracy

    # ── Inference ─────────────────────────────────────────────────────────────

    def predict(self, X: np.ndarray) -> np.ndarray:
        if self.model is None:
            raise ValueError("Model not trained. Call train() first.")
        best = self.best_iteration_ if self.best_iteration_ is not None \
               else self.model.best_iteration
        return np.argmax(self.model.predict(X, num_iteration=best), axis=1)

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        if self.model is None:
            raise ValueError("Model not trained. Call train() first.")
        best = self.best_iteration_ if self.best_iteration_ is not None \
               else self.model.best_iteration
        return self.model.predict(X, num_iteration=best)

    def get_training_metadata(self) -> dict:
        return {
            "evals_result":  self.evals_result_,
            "best_iteration":self.best_iteration_,
            "best_score":    self.best_score_,
            "params":        self.params,
        }

    # ── Persistence ───────────────────────────────────────────────────────────

    def save_model(
        self,
        model_path: str = None,
        use_wandb:  bool = False,
        coin:       str  = "BTCUSDT",
    ) -> None:
        """Save with 3-slot versioning and optional W&B artifact."""
        if self.model is None:
            raise ValueError("No model to save. Train first.")

        base = Path("models/lightgbm")
        v1_dir, v2_dir, v3_dir = base/"v1", base/"v2", base/"v3"
        for d in (v1_dir, v2_dir, v3_dir):
            d.mkdir(parents=True, exist_ok=True)

        v1_m, v1_f = v1_dir/"model.txt", v1_dir/"model_features.pkl"
        v2_m, v2_f = v2_dir/"model.txt", v2_dir/"model_features.pkl"
        v3_m, v3_f = v3_dir/"model.txt", v3_dir/"model_features.pkl"

        feature_info = {
            "feature_names":     self.feature_names,
            "feature_importance":self.feature_importance.to_dict()
                                  if self.feature_importance is not None else None,
            "evals_result":      self.evals_result_,
            "best_iteration":    self.best_iteration_,
            "best_score":        self.best_score_,
            "params":            self.params,
        }

        # Rotate v3 → v2
        if v3_m.exists():
            try:
                v2_m.unlink(missing_ok=True)
                v2_f.unlink(missing_ok=True)
                v3_m.rename(v2_m)
                v3_f.rename(v2_f)
                print("[SAVE] v3 → v2")
            except Exception as e:
                print(f"[SAVE] Warning: rotate v3→v2 failed: {e}")

        # Create v1 baseline (first run only)
        if not v1_m.exists():
            try:
                self.model.save_model(str(v1_m))
                joblib.dump(feature_info, str(v1_f))
                print("[SAVE] Created v1 baseline")
            except Exception as e:
                print(f"[SAVE] Warning: v1 creation failed: {e}")

        # Save new model as v3
        try:
            self.model.save_model(str(v3_m))
            joblib.dump(feature_info, str(v3_f))
            print(f"[SAVE] New v3 → {v3_dir}")
        except Exception as e:
            print(f"[SAVE] ERROR saving v3: {e}")
            raise

        # Legacy path support
        if model_path:
            os.makedirs(os.path.dirname(os.path.abspath(model_path)), exist_ok=True)
            self.model.save_model(model_path)
            joblib.dump(feature_info, model_path.replace(".txt", "_features.pkl"))

        # ── W&B artifact ──────────────────────────────────────────────────
        if use_wandb and _WANDB_AVAILABLE and wandb.run is not None:
            art = wandb.Artifact(
                name     = f"lgbm-{coin.lower()}-final",
                type     = "model",
                metadata = {
                    "best_iteration": self.best_iteration_,
                    "coin":           coin,
                    "params":         self.params,
                },
            )
            art.add_dir(str(v3_dir), name="v3")
            wandb.log_artifact(art, aliases=["latest", "v3"])
            wandb.finish()

    def load_model(self, model_path: str = None) -> bool:
        """Load with v3 → v2 → v1 priority fallback."""
        base = Path("models/lightgbm")
        candidates = [
            (base/"v3"/"model.txt", base/"v3"/"model_features.pkl", "v3"),
            (base/"v2"/"model.txt", base/"v2"/"model_features.pkl", "v2"),
            (base/"v1"/"model.txt", base/"v1"/"model_features.pkl", "v1"),
        ]
        if model_path:
            candidates.append((
                Path(model_path),
                Path(model_path.replace(".txt", "_features.pkl")),
                "legacy",
            ))

        for m_path, f_path, label in candidates:
            if not m_path.exists():
                continue
            try:
                self.model = lgb.Booster(model_file=str(m_path))
                if f_path.exists():
                    info = joblib.load(str(f_path))
                    self.feature_names   = info.get("feature_names")
                    self.evals_result_   = info.get("evals_result")
                    self.best_iteration_ = info.get("best_iteration", self.model.best_iteration)
                    self.best_score_     = info.get("best_score")
                    if "params" in info:
                        self.params = info["params"]
                    if info.get("feature_importance"):
                        self.feature_importance = pd.DataFrame(info["feature_importance"])
                else:
                    self.best_iteration_ = getattr(self.model, "best_iteration", None)
                print(f"[LOAD] Loaded {label}  best_iter={self.best_iteration_}")
                return True
            except Exception as e:
                print(f"[LOAD] Failed to load {label}: {e}")

        print("[LOAD] No model found — need to train.")
        return False

    # ── Visualisation ─────────────────────────────────────────────────────────

    def plot_feature_importance(self, top_n: int = 20, save_path: str = None) -> None:
        if self.feature_importance is None:
            print("Train the model first.")
            return
        fig, ax = plt.subplots(figsize=(10, 8))
        top = self.feature_importance.head(top_n)
        sns.barplot(data=top, x="importance", y="feature", ax=ax)
        ax.set_title(f"LightGBM Feature Importance (Top {top_n})")
        ax.set_xlabel("Importance (gain)")
        fig.tight_layout()
        if save_path:
            fig.savefig(save_path, dpi=150, bbox_inches="tight")
            print(f"Saved → {save_path}")
        plt.close(fig)   # non-blocking


# ─────────────────────────────────────────────────────────────────────────────
# W&B Sweep helper
# ─────────────────────────────────────────────────────────────────────────────

def create_lgb_sweep(
    project: str = LGB_WANDB_CONFIG["project"],
    entity:  str = None,
) -> str:
    if not _WANDB_AVAILABLE:
        raise ImportError("wandb is not installed")
    sweep_id = wandb.sweep(LGB_SWEEP_CONFIG, project=project, entity=entity)
    print(f"LightGBM sweep created — id={sweep_id}")
    return sweep_id


# ─────────────────────────────────────────────────────────────────────────────
# CLI entry point
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Train LightGBM model")
    parser.add_argument("--coin",         type=str,  default="BTCUSDT")
    parser.add_argument("--use_wandb",    action="store_true")
    parser.add_argument("--create_sweep", action="store_true",
                        help="Register a W&B sweep and exit")
    args = parser.parse_args()

    if args.create_sweep:
        sid = create_lgb_sweep()
        print(f"Run with: wandb agent {sid}")
        return

    print("=" * 60)
    print("LightGBM Training")
    print("=" * 60)

    crypto_path = f"data/{args.coin.lower()}.csv"
    if not os.path.exists(crypto_path):
        print(f"Data not found: {crypto_path}")
        return

    crypto_df = pd.read_csv(crypto_path)

    # Sentiment data
    sentiment_df = None
    if os.path.exists("results/daily_sentiment_features.csv"):
        sentiment_df = pd.read_csv("results/daily_sentiment_features.csv")
    elif os.path.exists("data/articles.csv"):
        # Mock sentiment for local demo runs
        if "date" not in crypto_df.columns and "open_time" in crypto_df.columns:
            crypto_df["date"] = pd.to_datetime(crypto_df["open_time"])
        dates = pd.to_datetime(crypto_df["date"]).dt.strftime("%Y-%m-%d").unique()
        rng   = np.random.default_rng(LGB_WANDB_CONFIG["seed"])
        sentiment_df = pd.DataFrame({
            "date":                   dates,
            "sentiment_mean":         rng.normal(0.1,  0.5,  len(dates)),
            "sentiment_std":          rng.uniform(0.1, 0.3,  len(dates)),
            "news_count":             rng.integers(5,  50,   len(dates)),
            "sentiment_confidence":   rng.uniform(0.8, 0.99, len(dates)),
            "negative_sentiment":     rng.uniform(0,   0.3,  len(dates)),
            "neutral_sentiment":      rng.uniform(0.3, 0.7,  len(dates)),
            "positive_sentiment":     rng.uniform(0,   0.3,  len(dates)),
        })

    trainer = LightGBMTrainer()
    X, y, _ = trainer.prepare_features(crypto_df, sentiment_df)
    trainer.train(X, y, use_wandb=args.use_wandb, coin=args.coin)
    trainer.save_model(use_wandb=args.use_wandb, coin=args.coin)
    print("\nLightGBM training complete.")


if __name__ == "__main__":
    main()
