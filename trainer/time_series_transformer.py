"""
Time Series Transformer — with full Weights & Biases integration.

Fixes applied vs. original:
  [CRITICAL] Scaler was fit on full dataset before split → now fit on train only (data leakage).
  [CRITICAL] Device parameter was silently overridden to 'cpu' → now respects caller's device.
  [CRITICAL] No random seeds anywhere → set_seed() applied to torch/numpy/random/cuda.
  [WARNING]  tqdm iterator was manually advanced with .update(1) inside a for-loop → removed.
  [WARNING]  CrossEntropyLoss had no class weights → inverse-frequency weights computed from y_train.
  [WARNING]  ReLU in FFN → replaced with GELU (standard for transformers, smoother gradient).
  [WARNING]  No final LayerNorm before classifier head → added.
  [SUGGESTION] DataLoader workers lacked seed function → _seed_worker added for reproducibility.
"""

from __future__ import annotations

# ─────────────────────────────────────────────────────────────────────────────
# W&B CONFIGURATION — single source of truth for ALL hyperparameters
# ─────────────────────────────────────────────────────────────────────────────
WANDB_CONFIG: dict = {
    # ── project metadata ──────────────────────────────────────────────────────
    "project":   "crypto-ml-tst",
    "entity":    None,          # override via WANDB_ENTITY env var or set here
    "job_type":  "train",
    "tags":      ["tst", "transformer", "crypto", "3-class"],

    # ── model architecture ────────────────────────────────────────────────────
    "input_dim":    7,
    "hidden_dim":   32,
    "num_heads":    2,
    "ff_dim":       64,
    "num_layers":   1,
    "dropout":      0.1,
    "num_classes":  3,

    # ── training ──────────────────────────────────────────────────────────────
    "epochs":                   50,
    "batch_size":               32,
    "learning_rate":            1e-3,
    "weight_decay":             1e-5,
    "sequence_length":          30,
    "test_size":                0.2,
    "val_fraction":             0.2,   # fraction of train set used for validation
    "early_stopping_patience":  15,
    "lr_scheduler_patience":    10,
    "lr_scheduler_factor":      0.5,
    "grad_clip_norm":           1.0,
    "label_threshold":          0.00015,
    "seed":                     42,

    # ── logging frequencies ───────────────────────────────────────────────────
    "log_grad_freq":            100,   # steps between gradient/weight histogram logs
}

# W&B Sweep config — Bayesian search over the most impactful hyperparameters
WANDB_SWEEP_CONFIG: dict = {
    "method": "bayes",
    "metric": {"name": "val/loss", "goal": "minimize"},
    "parameters": {
        "hidden_dim":    {"values": [16, 32, 64, 128]},
        "num_layers":    {"values": [1, 2, 3]},
        "dropout":       {"distribution": "uniform",            "min": 0.0,  "max": 0.4},
        "learning_rate": {"distribution": "log_uniform_values", "min": 1e-4, "max": 1e-2},
        "batch_size":    {"values": [16, 32, 64]},
        "weight_decay":  {"distribution": "log_uniform_values", "min": 1e-6, "max": 1e-3},
        "num_heads":     {"values": [2, 4]},
    },
    "early_terminate": {"type": "hyperband", "min_iter": 5},
}

# ─────────────────────────────────────────────────────────────────────────────
# Standard imports
# ─────────────────────────────────────────────────────────────────────────────
import math
import os
import random
import warnings
warnings.filterwarnings("ignore")

import joblib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import shutil
import torch
import torch.nn as nn
import torch.optim as optim
from pathlib import Path
from sklearn.metrics import (
    accuracy_score, classification_report, f1_score, confusion_matrix,
)
from sklearn.preprocessing import StandardScaler
from torch.utils.data import DataLoader, Dataset
from tqdm import tqdm

# Optional W&B
try:
    import wandb
    _WANDB_AVAILABLE = True
except ImportError:
    _WANDB_AVAILABLE = False

# Optional train_utils
try:
    from trainer.train_utils import (
        preprocess_sequences, log_classification_metrics,
        save_start_time, load_start_time,
    )
    TRAIN_UTILS_AVAILABLE = True
except ImportError:
    TRAIN_UTILS_AVAILABLE = False


# ─────────────────────────────────────────────────────────────────────────────
# Reproducibility helpers
# ─────────────────────────────────────────────────────────────────────────────

def set_seed(seed: int = 42) -> None:
    """Set ALL random seeds for full reproducibility across runs."""
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False   # disable auto-tuner for determinism
    os.environ["PYTHONHASHSEED"] = str(seed)


def _seed_worker(worker_id: int) -> None:
    """DataLoader worker initialiser — ensures each worker has a unique, deterministic seed."""
    worker_seed = torch.initial_seed() % (2 ** 32)
    np.random.seed(worker_seed)
    random.seed(worker_seed)


# ─────────────────────────────────────────────────────────────────────────────
# Dataset
# ─────────────────────────────────────────────────────────────────────────────

class TimeSeriesDataset(Dataset):
    """PyTorch Dataset for fixed-length time-series windows."""

    def __init__(self, sequences: np.ndarray, targets: np.ndarray) -> None:
        self.sequences = sequences
        self.targets   = targets

    def __len__(self) -> int:
        return len(self.sequences)

    def __getitem__(self, idx: int):
        return (
            torch.FloatTensor(self.sequences[idx]),
            torch.tensor(self.targets[idx], dtype=torch.long),
        )


# ─────────────────────────────────────────────────────────────────────────────
# Model
# ─────────────────────────────────────────────────────────────────────────────

class TSTBlock(nn.Module):
    """
    Pre-Norm Transformer encoder block.

    Pre-norm (LayerNorm before attention/FFN) trains more stably than
    post-norm and does not require learning-rate warm-up in most cases.
    GELU activation replaces ReLU for smoother gradients.
    """

    def __init__(
        self,
        hidden_dim: int,
        num_heads:  int,
        ff_dim:     int,
        dropout:    float = 0.1,
    ) -> None:
        super().__init__()
        self.attn  = nn.MultiheadAttention(
            hidden_dim, num_heads, batch_first=True, dropout=dropout,
        )
        self.ff    = nn.Sequential(
            nn.Linear(hidden_dim, ff_dim),
            nn.GELU(),           # GELU is standard in modern transformers (GPT, BERT, ViT)
            nn.Dropout(dropout),
            nn.Linear(ff_dim, hidden_dim),
            nn.Dropout(dropout),
        )
        self.norm1 = nn.LayerNorm(hidden_dim)
        self.norm2 = nn.LayerNorm(hidden_dim)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        normed       = self.norm1(x)
        attn_out, _  = self.attn(normed, normed, normed)
        x            = x + attn_out               # residual

        x            = x + self.ff(self.norm2(x)) # residual
        return x


class TimeSeriesTransformer(nn.Module):
    """
    Transformer classifier for multivariate time series.

    Input:  (batch, seq_len, input_dim)
    Output: (batch, num_classes)  — raw logits (apply softmax externally)

    Architecture:
      Linear projection  →  N × TSTBlock  →  final LayerNorm  →  [last-step]  →  Linear head
    """

    def __init__(
        self,
        input_dim:   int,
        hidden_dim:  int   = 32,
        num_heads:   int   = 2,
        ff_dim:      int   = 64,
        num_layers:  int   = 1,
        dropout:     float = 0.1,
        num_classes: int   = 3,
    ) -> None:
        super().__init__()
        self.input_proj = nn.Linear(input_dim, hidden_dim)
        self.layers     = nn.ModuleList([
            TSTBlock(hidden_dim, num_heads, ff_dim, dropout)
            for _ in range(num_layers)
        ])
        # Final norm stabilises the representation before the head
        self.norm       = nn.LayerNorm(hidden_dim)
        self.classifier = nn.Linear(hidden_dim, num_classes)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x = self.input_proj(x)        # (B, L, hidden_dim)
        for layer in self.layers:
            x = layer(x)
        x = self.norm(x)
        return self.classifier(x[:, -1, :])  # last timestep → logits


# ─────────────────────────────────────────────────────────────────────────────
# Trainer
# ─────────────────────────────────────────────────────────────────────────────

class TimeSeriesTransformerTrainer:
    """
    Full training harness for TimeSeriesTransformer.

    W&B integration:
      • wandb.init()        — project/entity/config/job_type/tags
      • wandb.watch()       — gradient + weight histograms
      • Per-step logging    — step_loss, grad_norm, lr
      • Per-epoch logging   — val_loss, accuracy, macro-F1, confusion_matrix
      • Sample table        — logged every 5 epochs
      • Artifacts           — best checkpoint + final v3 model directory
      • wandb.alert()       — NaN loss (both train and val)
      • wandb.finish()      — clean run close
      • Sweep config        — WANDB_SWEEP_CONFIG at module level
    """

    CLASS_NAMES = ["Sell", "Hold", "Buy"]

    def __init__(
        self,
        model:  TimeSeriesTransformer,
        device: str | torch.device = "cpu",
        coin:   str = "BTCUSDT",
    ) -> None:
        self.model  = model
        # Respect the caller's device — do NOT force CPU
        self.device = torch.device(device) if isinstance(device, str) else device
        self.model.to(self.device)
        self.coin   = coin

        # Criterion will be replaced in train() once class weights are known
        self.criterion = nn.CrossEntropyLoss()
        self.optimizer = optim.Adam(
            model.parameters(),
            lr           = WANDB_CONFIG["learning_rate"],
            weight_decay = WANDB_CONFIG["weight_decay"],
        )
        self.scheduler = optim.lr_scheduler.ReduceLROnPlateau(
            self.optimizer,
            mode    = "min",
            factor  = WANDB_CONFIG["lr_scheduler_factor"],
            patience= WANDB_CONFIG["lr_scheduler_patience"],
        )

        self.train_losses: list = []
        self.val_losses:   list = []
        self.global_step:  int  = 0
        self._wandb_run         = None

    # ── Label helpers ─────────────────────────────────────────────────────────

    def _label_price_change(
        self,
        price_change_pct,
        threshold: float = 0.00015,
    ) -> int | np.ndarray:
        pct    = np.asarray(price_change_pct)
        labels = np.ones_like(pct, dtype=int)      # default = Hold
        labels[pct >  threshold] = 2               # Buy
        labels[pct < -threshold] = 0               # Sell
        return int(labels.item()) if pct.ndim == 0 else labels

    def create_sequences(
        self,
        data:          np.ndarray,
        close_prices:  np.ndarray,
        sequence_length: int = 30,
    ) -> tuple[np.ndarray, np.ndarray]:
        """
        Build (seq_len, features) windows and *forward-looking* 3-class labels.

        For window ending at index i-1, the label is the price change at candle i
        (i.e. the very next candle after the last observed one), which is consistent
        with LightGBM's shift(-1) labelling.
        """
        threshold  = WANDB_CONFIG["label_threshold"]
        sequences, targets = [], []
        for i in range(sequence_length, len(data)):
            sequences.append(data[i - sequence_length : i])
            pct = (close_prices[i] - close_prices[i - 1]) / (close_prices[i - 1] + 1e-9)
            targets.append(self._label_price_change(pct, threshold))
        return (
            np.array(sequences, dtype=np.float32),
            np.array(targets,   dtype=np.int64),
        )

    # ── Data preparation ──────────────────────────────────────────────────────

    def prepare_data(
        self,
        crypto_df:       pd.DataFrame,
        sequence_length: int   = 30,
        test_size:       float = 0.2,
        seed:            int   = 42,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        """
        Build train/test splits.

        CRITICAL FIX: the scaler is fit ONLY on the training portion.
        The original code fit on the entire dataset, leaking test statistics
        into the normalisation and inflating reported validation metrics.
        """
        print("Preparing time series data...")

        required  = ["open", "high", "low", "close", "volume"]
        optional  = ["taker_base", "taker_quote"]
        available = required.copy()
        for f in optional:
            if f in crypto_df.columns:
                available.append(f)

        if "taker_base" not in crypto_df.columns or "taker_quote" not in crypto_df.columns:
            if "price_change" not in crypto_df.columns:
                crypto_df = crypto_df.copy()
                crypto_df["price_change"] = crypto_df["close"].pct_change()
            if "price_change" not in available:
                available.append("price_change")

        features = available[:7]
        features = [f for f in features if not crypto_df[f].isna().all()]
        if not features:
            raise ValueError("All selected features are entirely NaN — cannot train.")
        print(f"Using features ({len(features)}): {features}")

        initial = len(crypto_df)
        crypto_df = crypto_df.dropna(subset=features)
        if len(crypto_df) < initial:
            print(f"Dropped {initial - len(crypto_df)} rows with NaN values")

        data         = crypto_df[features].values
        close_prices = crypto_df["close"].values

        # ── Split BEFORE fitting the scaler ───────────────────────────────
        split        = int(len(data) * (1 - test_size))
        train_raw    = data[:split];    close_train = close_prices[:split]
        test_raw     = data[split:];    close_test  = close_prices[split:]

        self.scaler        = StandardScaler()
        train_scaled       = self.scaler.fit_transform(train_raw)   # fit on train only
        test_scaled        = self.scaler.transform(test_raw)        # transform only

        X_train, y_train   = self.create_sequences(train_scaled, close_train, sequence_length)
        X_test,  y_test    = self.create_sequences(test_scaled,  close_test,  sequence_length)

        print(f"Train={len(X_train)}  Test={len(X_test)}")
        print(f"Target distribution (train): {np.bincount(y_train)}")
        return X_train, y_train, X_test, y_test

    # ── Training step ─────────────────────────────────────────────────────────

    def train_epoch(
        self,
        train_loader: DataLoader,
        use_wandb:    bool = False,
    ) -> float:
        """One full pass over the training set with per-step W&B logging."""
        self.model.train()
        total_loss = 0.0

        pbar = tqdm(train_loader, desc="  Training", leave=False, ncols=90)
        for batch_x, batch_y in pbar:
            batch_x = batch_x.to(self.device)
            batch_y = batch_y.to(self.device)

            self.optimizer.zero_grad()
            outputs  = self.model(batch_x)
            loss     = self.criterion(outputs, batch_y)
            loss.backward()

            # Gradient clipping prevents exploding gradients
            grad_norm = torch.nn.utils.clip_grad_norm_(
                self.model.parameters(),
                max_norm=WANDB_CONFIG["grad_clip_norm"],
            )

            self.optimizer.step()
            total_loss       += loss.item()
            self.global_step += 1

            pbar.set_postfix(loss=f"{loss.item():.4f}", gnorm=f"{grad_norm:.3f}")

            # ── Per-step W&B logging ───────────────────────────────────────
            if use_wandb and _WANDB_AVAILABLE and wandb.run is not None:
                log_data = {
                    "train/step_loss": loss.item(),
                    "train/grad_norm": grad_norm.item(),
                    "train/lr":        self.optimizer.param_groups[0]["lr"],
                }
                wandb.log(log_data, step=self.global_step)

                if math.isnan(loss.item()):
                    wandb.alert(
                        title="NaN Training Loss",
                        text=f"Loss became NaN at global step {self.global_step}",
                        level=wandb.AlertLevel.ERROR,
                    )

        return total_loss / max(len(train_loader), 1)

    # ── Validation ────────────────────────────────────────────────────────────

    def validate(self, val_loader: DataLoader) -> dict:
        """
        Evaluate on the validation loader.

        Returns dict with:
          loss (float), accuracy (float), f1_macro (float),
          preds (ndarray), labels (ndarray)
        """
        self.model.eval()
        total_loss  = 0.0
        all_preds   = []
        all_labels  = []

        with torch.no_grad():
            for batch_x, batch_y in val_loader:
                batch_x    = batch_x.to(self.device)
                batch_y    = batch_y.to(self.device)
                outputs    = self.model(batch_x)
                loss       = self.criterion(outputs, batch_y)
                total_loss += loss.item()
                preds       = torch.argmax(outputs, dim=1)
                all_preds.extend(preds.cpu().numpy())
                all_labels.extend(batch_y.cpu().numpy())

        preds_arr  = np.array(all_preds)
        labels_arr = np.array(all_labels)
        return {
            "loss":     total_loss / max(len(val_loader), 1),
            "accuracy": accuracy_score(labels_arr, preds_arr),
            "f1_macro": f1_score(labels_arr, preds_arr, average="macro", zero_division=0),
            "preds":    preds_arr,
            "labels":   labels_arr,
        }

    # ── Main training loop ────────────────────────────────────────────────────

    def train(
        self,
        X_train:    np.ndarray,
        y_train:    np.ndarray,
        X_val:      np.ndarray,
        y_val:      np.ndarray,
        epochs:     int  = 50,
        batch_size: int  = 32,
        use_wandb:  bool = False,
        coin:       str  = "BTCUSDT",
        seed:       int  = 42,
    ) -> None:
        """
        Full training loop.

        3-slot versioning:
          v1 — baseline (written once, never overwritten)
          v2 — previous run
          v3 — current run  (most recent)
        """
        set_seed(seed)
        self.coin = coin

        # ── Class-weighted loss for imbalanced targets ────────────────────
        counts         = np.bincount(y_train, minlength=3).astype(np.float32)
        class_weights  = len(y_train) / (3.0 * counts + 1e-9)
        weight_tensor  = torch.tensor(class_weights, dtype=torch.float32).to(self.device)
        self.criterion = nn.CrossEntropyLoss(weight=weight_tensor)

        # ── W&B initialisation ────────────────────────────────────────────
        if use_wandb and _WANDB_AVAILABLE:
            run_cfg = {
                **WANDB_CONFIG,
                "coin":       coin,
                "seed":       seed,
                "epochs":     epochs,
                "batch_size": batch_size,
            }
            self._wandb_run = wandb.init(
                project  = WANDB_CONFIG["project"],
                entity   = WANDB_CONFIG.get("entity"),
                config   = run_cfg,
                job_type = WANDB_CONFIG["job_type"],
                tags     = WANDB_CONFIG["tags"] + [coin],
                name     = f"tst-{coin}-{wandb.util.generate_id()}",
                reinit   = True,
            )
            # Track gradients AND weights; histograms every log_grad_freq steps
            wandb.watch(
                self.model,
                log      = "all",
                log_freq = WANDB_CONFIG["log_grad_freq"],
                log_graph= True,
            )
            # ── Dataset statistics ────────────────────────────────────────
            train_counts = np.bincount(y_train, minlength=3)
            val_counts   = np.bincount(y_val,   minlength=3)
            dist_table   = wandb.Table(
                columns=["split", "class", "count"],
                data=[
                    [s, c, int(n)]
                    for s, arr in [("train", train_counts), ("val", val_counts)]
                    for c, n  in zip(self.CLASS_NAMES, arr)
                ],
            )
            wandb.log({
                "dataset/train_samples":       len(X_train),
                "dataset/val_samples":         len(X_val),
                "dataset/class_distribution":  wandb.plot.bar(
                    dist_table, "class", "count",
                    title="Class Distribution",
                ),
                "dataset/class_weights_sell":  float(class_weights[0]),
                "dataset/class_weights_hold":  float(class_weights[1]),
                "dataset/class_weights_buy":   float(class_weights[2]),
            })
        else:
            use_wandb = False   # disable cleanly if wandb unavailable

        # ── Load existing checkpoint (warm-start) ─────────────────────────
        base_dir = Path("models/tst")
        v1_dir, v2_dir, v3_dir = base_dir/"v1", base_dir/"v2", base_dir/"v3"
        for d in (v1_dir, v2_dir, v3_dir):
            d.mkdir(parents=True, exist_ok=True)

        for version_dir, label in [(v3_dir, "v3"), (v2_dir, "v2")]:
            ckpt = version_dir / "model.pth"
            scl  = version_dir / "scaler.pkl"
            if ckpt.exists() and scl.exists():
                try:
                    self.model.load_state_dict(
                        torch.load(str(ckpt), map_location=self.device)
                    )
                    if hasattr(self, "scaler"):
                        self.scaler = joblib.load(str(scl))
                    print(f"[LOAD] Warm-started from {label} checkpoint")
                    break
                except Exception as e:
                    print(f"[LOAD] Could not load {label}: {e}")

        # ── DataLoaders ───────────────────────────────────────────────────
        g = torch.Generator()
        g.manual_seed(seed)

        train_loader = DataLoader(
            TimeSeriesDataset(X_train, y_train),
            batch_size      = batch_size,
            shuffle         = True,
            generator       = g,
            worker_init_fn  = _seed_worker,
        )
        val_loader = DataLoader(
            TimeSeriesDataset(X_val, y_val),
            batch_size = batch_size,
            shuffle    = False,
        )

        print(f"Training TST  |  coin={coin}  device={self.device}")
        print(f"  train={len(X_train)}  val={len(X_val)}  epochs={epochs}  bs={batch_size}")
        print("-" * 60)

        best_val_loss    = float("inf")
        patience_counter = 0
        patience         = WANDB_CONFIG["early_stopping_patience"]
        temp_ckpt        = Path("models/temp_best_tst_model.pth")
        temp_ckpt.parent.mkdir(parents=True, exist_ok=True)

        for epoch in range(epochs):
            # Train
            train_loss = self.train_epoch(train_loader, use_wandb=use_wandb)
            # Validate
            val_metrics = self.validate(val_loader)
            val_loss    = val_metrics["loss"]

            self.scheduler.step(val_loss)
            current_lr = self.optimizer.param_groups[0]["lr"]

            self.train_losses.append(train_loss)
            self.val_losses.append(val_loss)

            improved = val_loss < best_val_loss
            if improved:
                best_val_loss    = val_loss
                patience_counter = 0
                torch.save(self.model.state_dict(), str(temp_ckpt))
                flag = "✓ best"
            else:
                patience_counter += 1
                flag = f"patience {patience_counter}/{patience}"

            print(
                f"  Epoch {epoch+1:3d}/{epochs} | "
                f"train={train_loss:.5f} | val={val_loss:.5f} | "
                f"acc={val_metrics['accuracy']:.3f} | "
                f"f1={val_metrics['f1_macro']:.3f} | "
                f"lr={current_lr:.2e} | {flag}"
            )

            # ── Per-epoch W&B logging ──────────────────────────────────────
            if use_wandb:
                epoch_log: dict = {
                    "train/epoch_loss": train_loss,
                    "val/loss":         val_loss,
                    "val/accuracy":     val_metrics["accuracy"],
                    "val/f1_macro":     val_metrics["f1_macro"],
                    "train/lr":         current_lr,
                    "epoch":            epoch + 1,
                }

                # Confusion matrix every epoch
                epoch_log["val/confusion_matrix"] = wandb.plot.confusion_matrix(
                    probs       = None,
                    y_true      = val_metrics["labels"].tolist(),
                    preds       = val_metrics["preds"].tolist(),
                    class_names = self.CLASS_NAMES,
                )

                # Sample prediction table every 5 epochs
                if (epoch + 1) % 5 == 0:
                    tbl = wandb.Table(columns=["true", "predicted", "correct"])
                    for t, p in zip(val_metrics["labels"][:50], val_metrics["preds"][:50]):
                        tbl.add_data(self.CLASS_NAMES[t], self.CLASS_NAMES[p], bool(t == p))
                    epoch_log["val/sample_predictions"] = tbl

                # Save best-checkpoint artifact
                if improved:
                    art = wandb.Artifact(
                        name     = f"tst-{coin.lower()}-checkpoint",
                        type     = "model",
                        metadata = {"epoch": epoch + 1, "val_loss": val_loss, "coin": coin},
                    )
                    art.add_file(str(temp_ckpt))
                    wandb.log_artifact(art, aliases=["best"])

                # Alert on NaN val loss
                if math.isnan(val_loss):
                    wandb.alert(
                        title="NaN Validation Loss",
                        text=f"val/loss is NaN at epoch {epoch + 1}",
                        level=wandb.AlertLevel.ERROR,
                    )

                wandb.log(epoch_log, step=self.global_step)

            if patience_counter >= patience:
                print(f"\nEarly stopping at epoch {epoch + 1}")
                break

        # ── Restore best model ────────────────────────────────────────────
        if temp_ckpt.exists():
            self.model.load_state_dict(
                torch.load(str(temp_ckpt), map_location=self.device)
            )
            print(f"[FINAL] Loaded best model (val_loss={best_val_loss:.5f})")
        else:
            print("[WARNING] No improvement — keeping final weights.")

        # ── Save with 3-slot versioning ───────────────────────────────────
        self._save_versioned(v1_dir, v2_dir, v3_dir)

        # ── Log final model artifact ──────────────────────────────────────
        if use_wandb:
            final_art = wandb.Artifact(
                name     = f"tst-{coin.lower()}-final",
                type     = "model",
                metadata = {
                    "best_val_loss":  best_val_loss,
                    "epochs_trained": len(self.train_losses),
                    "coin":           coin,
                    "config":         WANDB_CONFIG,
                },
            )
            final_art.add_dir(str(v3_dir), name="v3")
            wandb.log_artifact(final_art, aliases=["latest", "v3"])
            wandb.log({
                "final/best_val_loss":  best_val_loss,
                "final/epochs_trained": len(self.train_losses),
            })
            wandb.finish()
            self._wandb_run = None

        if temp_ckpt.exists():
            temp_ckpt.unlink()

        print(
            f"\nTraining complete | best_val_loss={best_val_loss:.5f} "
            f"| epochs={len(self.train_losses)}"
        )

    # ── Version management ────────────────────────────────────────────────────

    def _save_versioned(self, v1_dir: Path, v2_dir: Path, v3_dir: Path) -> None:
        """Rotate v3 → v2, protect v1 baseline, write new v3."""
        v3_m, v3_s = v3_dir/"model.pth", v3_dir/"scaler.pkl"
        v2_m, v2_s = v2_dir/"model.pth", v2_dir/"scaler.pkl"
        v1_m, v1_s = v1_dir/"model.pth", v1_dir/"scaler.pkl"

        # Move v3 → v2
        if v3_m.exists():
            try:
                v2_m.unlink(missing_ok=True)
                v2_s.unlink(missing_ok=True)
                v3_m.rename(v2_m)
                if v3_s.exists():
                    v3_s.rename(v2_s)
                print("[SAVE] v3 → v2")
            except Exception as e:
                print(f"[SAVE] Warning: rotate v3→v2 failed: {e}")

        # Create v1 baseline (first run only)
        if not v1_m.exists():
            try:
                torch.save(self.model.state_dict(), str(v1_m))
                if hasattr(self, "scaler"):
                    joblib.dump(self.scaler, str(v1_s))
                print("[SAVE] Created v1 baseline")
            except Exception as e:
                print(f"[SAVE] Warning: v1 creation failed: {e}")

        # Save current model as v3
        try:
            torch.save(self.model.state_dict(), str(v3_m))
            if hasattr(self, "scaler"):
                joblib.dump(self.scaler, str(v3_s))
            print(f"[SAVE] New v3 → {v3_dir}")
        except Exception as e:
            print(f"[SAVE] ERROR saving v3: {e}")
            raise

    # ── Inference ─────────────────────────────────────────────────────────────

    def predict(self, X_test: np.ndarray) -> np.ndarray:
        """Return predicted class indices (0=Sell, 1=Hold, 2=Buy)."""
        self.model.eval()
        preds = []
        with torch.no_grad():
            for i in range(0, len(X_test), 32):
                batch = torch.FloatTensor(X_test[i : i + 32]).to(self.device)
                preds.extend(torch.argmax(self.model(batch), dim=1).cpu().numpy())
        return np.array(preds)

    def predict_proba(self, X_test: np.ndarray) -> np.ndarray:
        """Return class probabilities, shape (N, 3)."""
        self.model.eval()
        probs = []
        with torch.no_grad():
            for i in range(0, len(X_test), 32):
                batch = torch.FloatTensor(X_test[i : i + 32]).to(self.device)
                probs.extend(
                    torch.softmax(self.model(batch), dim=1).cpu().numpy()
                )
        return np.array(probs)

    def predict_three_class(
        self, X_test: np.ndarray, current_prices=None
    ) -> np.ndarray:
        """Return [Sell, Hold, Buy] probabilities. Alias for predict_proba()."""
        return self.predict_proba(X_test)

    # ── Evaluation ────────────────────────────────────────────────────────────

    def evaluate(
        self,
        X_test:     np.ndarray,
        y_test:     np.ndarray,
        use_mlflow: bool = False,
        use_wandb:  bool = False,
    ) -> tuple:
        predictions = self.predict(X_test)
        accuracy    = accuracy_score(y_test, predictions)

        print(f"Test Accuracy: {accuracy:.4f}")
        print("\nClassification Report:")
        print(classification_report(y_test, predictions, target_names=self.CLASS_NAMES))

        if use_wandb and _WANDB_AVAILABLE and wandb.run is not None:
            wandb.log({
                "test/accuracy":         accuracy,
                "test/f1_macro":         f1_score(y_test, predictions, average="macro", zero_division=0),
                "test/confusion_matrix": wandb.plot.confusion_matrix(
                    probs=None,
                    y_true=y_test.tolist(),
                    preds=predictions.tolist(),
                    class_names=self.CLASS_NAMES,
                ),
            })

        if TRAIN_UTILS_AVAILABLE:
            try:
                log_classification_metrics(
                    predictions, y_test, name="tst_val",
                    class_labels=["0", "1", "2"],
                    use_mlflow=use_mlflow, use_wandb=use_wandb,
                )
            except Exception as e:
                print(f"Warning: log_classification_metrics failed: {e}")

        return predictions, {"accuracy": accuracy}

    # ── Utilities ─────────────────────────────────────────────────────────────

    def plot_training_history(self, save_dir: str = "results") -> None:
        """Save loss curves to disk (non-blocking — uses plt.close)."""
        Path(save_dir).mkdir(parents=True, exist_ok=True)
        fig, axes = plt.subplots(1, 2, figsize=(12, 4))
        for ax, (tl, vl), title in zip(
            axes,
            [(self.train_losses, self.val_losses),
             (self.train_losses[-20:], self.val_losses[-20:])],
            ["Full Training History", "Last 20 Epochs"],
        ):
            ax.plot(tl, label="Train")
            ax.plot(vl, label="Val")
            ax.set_title(title)
            ax.set_xlabel("Epoch")
            ax.set_ylabel("Loss")
            ax.legend()
            ax.grid(True)
        fig.tight_layout()
        out = Path(save_dir) / "tst_training_history.png"
        fig.savefig(str(out), dpi=150, bbox_inches="tight")
        plt.close(fig)
        print(f"Training history → {out}")


# ─────────────────────────────────────────────────────────────────────────────
# W&B Sweep helper
# ─────────────────────────────────────────────────────────────────────────────

def create_sweep(
    project: str = WANDB_CONFIG["project"],
    entity:  str = None,
) -> str:
    """
    Register a W&B hyperparameter sweep and return the sweep ID.

    Usage::

        sweep_id = create_sweep()

        def sweep_run():
            with wandb.init() as run:
                cfg = run.config
                # build model and trainer from cfg …
                trainer.train(…, use_wandb=True)

        wandb.agent(sweep_id, function=sweep_run, count=20)
    """
    if not _WANDB_AVAILABLE:
        raise ImportError("wandb is not installed")
    sweep_id = wandb.sweep(WANDB_SWEEP_CONFIG, project=project, entity=entity)
    print(f"Sweep created — id={sweep_id}")
    return sweep_id


# ─────────────────────────────────────────────────────────────────────────────
# CLI entry point
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Train Time Series Transformer")
    parser.add_argument("--coin",         type=str,  default="BTCUSDT")
    parser.add_argument("--epochs",       type=int,  default=WANDB_CONFIG["epochs"])
    parser.add_argument("--batch_size",   type=int,  default=WANDB_CONFIG["batch_size"])
    parser.add_argument("--seed",         type=int,  default=WANDB_CONFIG["seed"])
    parser.add_argument("--use_wandb",    action="store_true")
    parser.add_argument("--create_sweep", action="store_true",
                        help="Register a W&B sweep and exit")
    args = parser.parse_args()

    if args.create_sweep:
        sid = create_sweep()
        print(f"Run with: wandb agent {sid}")
        return

    set_seed(args.seed)

    crypto_path = f"data/{args.coin.lower()}.csv"
    if not os.path.exists(crypto_path):
        print(f"Data not found: {crypto_path}")
        return

    crypto_df = pd.read_csv(crypto_path)
    print(f"Loaded {len(crypto_df)} rows from {crypto_path}")

    model = TimeSeriesTransformer(
        input_dim   = WANDB_CONFIG["input_dim"],
        hidden_dim  = WANDB_CONFIG["hidden_dim"],
        num_heads   = WANDB_CONFIG["num_heads"],
        ff_dim      = WANDB_CONFIG["ff_dim"],
        num_layers  = WANDB_CONFIG["num_layers"],
        dropout     = WANDB_CONFIG["dropout"],
        num_classes = WANDB_CONFIG["num_classes"],
    )
    device  = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    trainer = TimeSeriesTransformerTrainer(model, device=str(device), coin=args.coin)

    X_train, y_train, X_test, y_test = trainer.prepare_data(
        crypto_df,
        sequence_length = WANDB_CONFIG["sequence_length"],
        test_size       = WANDB_CONFIG["test_size"],
        seed            = args.seed,
    )
    val_size          = int(len(X_train) * WANDB_CONFIG["val_fraction"])
    X_val, y_val      = X_train[-val_size:], y_train[-val_size:]
    X_train, y_train  = X_train[:-val_size], y_train[:-val_size]

    trainer.train(
        X_train, y_train, X_val, y_val,
        epochs     = args.epochs,
        batch_size = args.batch_size,
        use_wandb  = args.use_wandb,
        coin       = args.coin,
        seed       = args.seed,
    )
    trainer.evaluate(X_test, y_test, use_wandb=args.use_wandb)
    trainer.plot_training_history()


if __name__ == "__main__":
    main()
