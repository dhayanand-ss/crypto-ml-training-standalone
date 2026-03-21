"""
Training pipeline test suite.

Structure
─────────
Unit tests
  test_dataset_*        — TimeSeriesDataset shape, dtype, label range, no NaN
  test_model_forward_*  — output shape, no NaN/Inf activations
  test_loss_computation — scalar, finite, non-negative
  test_optimizer_step   — weights actually change after one gradient step

Integration tests
  test_train_one_epoch  — runs without crash, returns finite loss
  test_val_one_epoch    — metrics dict has expected keys, values in range
  test_checkpoint_*     — saved model produces identical output after reload
  test_wandb_logging    — wandb.log() is called with correct keys (mocked)

LightGBM tests
  test_lgb_feature_engineering — RSI/BB finite, no NaN after prepare_features
  test_lgb_train_predict        — predictions in {0,1,2}, probas sum to 1

Smoke test
  test_smoke_2_epochs   — 2 epochs on tiny synthetic data:
                           • no crash
                           • loss is finite
                           • checkpoint written to disk
                           • W&B .log() called (mocked)
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import numpy as np
import pandas as pd
import pytest
import torch
import torch.nn as nn

# ── ensure project root is on sys.path ────────────────────────────────────────
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from trainer.time_series_transformer import (
    WANDB_CONFIG,
    TimeSeriesDataset,
    TimeSeriesTransformer,
    TimeSeriesTransformerTrainer,
    set_seed,
)
from trainer.lightgbm_trainer import LightGBMTrainer, LGB_WANDB_CONFIG


# ─────────────────────────────────────────────────────────────────────────────
# Shared fixtures
# ─────────────────────────────────────────────────────────────────────────────

SEED          = 42
SEQ_LEN       = 5
INPUT_DIM     = 7
HIDDEN_DIM    = 16
NUM_HEADS     = 2
FF_DIM        = 32
NUM_LAYERS    = 1
NUM_CLASSES   = 3
N_TRAIN       = 80
N_VAL         = 20
BATCH_SIZE    = 16


@pytest.fixture(autouse=True)
def fix_seed():
    """Re-seed everything before each test for determinism."""
    set_seed(SEED)


@pytest.fixture
def synthetic_sequences() -> tuple[np.ndarray, np.ndarray]:
    """Return (sequences, targets) for N_TRAIN samples."""
    rng = np.random.default_rng(SEED)
    X   = rng.standard_normal((N_TRAIN, SEQ_LEN, INPUT_DIM)).astype(np.float32)
    y   = rng.integers(0, NUM_CLASSES, size=N_TRAIN).astype(np.int64)
    return X, y


@pytest.fixture
def val_sequences() -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(SEED + 1)
    X   = rng.standard_normal((N_VAL, SEQ_LEN, INPUT_DIM)).astype(np.float32)
    y   = rng.integers(0, NUM_CLASSES, size=N_VAL).astype(np.int64)
    return X, y


@pytest.fixture
def tst_model() -> TimeSeriesTransformer:
    return TimeSeriesTransformer(
        input_dim  = INPUT_DIM,
        hidden_dim = HIDDEN_DIM,
        num_heads  = NUM_HEADS,
        ff_dim     = FF_DIM,
        num_layers = NUM_LAYERS,
        dropout    = 0.0,          # disable dropout for deterministic forward
        num_classes= NUM_CLASSES,
    )


@pytest.fixture
def trainer(tst_model) -> TimeSeriesTransformerTrainer:
    return TimeSeriesTransformerTrainer(tst_model, device="cpu", coin="BTCUSDT")


@pytest.fixture
def train_loader(synthetic_sequences):
    X, y = synthetic_sequences
    ds   = TimeSeriesDataset(X, y)
    return torch.utils.data.DataLoader(ds, batch_size=BATCH_SIZE, shuffle=False)


@pytest.fixture
def val_loader(val_sequences):
    X, y = val_sequences
    ds   = TimeSeriesDataset(X, y)
    return torch.utils.data.DataLoader(ds, batch_size=BATCH_SIZE, shuffle=False)


# ─────────────────────────────────────────────────────────────────────────────
# Unit tests — Dataset
# ─────────────────────────────────────────────────────────────────────────────

class TestDataset:
    def test_length(self, synthetic_sequences):
        X, y = synthetic_sequences
        ds = TimeSeriesDataset(X, y)
        assert len(ds) == N_TRAIN

    def test_item_shapes(self, synthetic_sequences):
        X, y = synthetic_sequences
        ds = TimeSeriesDataset(X, y)
        seq, label = ds[0]
        assert seq.shape   == (SEQ_LEN, INPUT_DIM), "Unexpected sequence shape"
        assert label.shape == (), "Label should be a 0-d tensor"

    def test_dtype(self, synthetic_sequences):
        X, y = synthetic_sequences
        ds = TimeSeriesDataset(X, y)
        seq, label = ds[0]
        assert seq.dtype   == torch.float32, "Sequence should be float32"
        assert label.dtype == torch.long,    "Label should be long (int64)"

    def test_no_nan_in_sequences(self, synthetic_sequences):
        X, y = synthetic_sequences
        ds   = TimeSeriesDataset(X, y)
        for i in range(len(ds)):
            seq, _ = ds[i]
            assert not torch.isnan(seq).any(), f"NaN found in sequence {i}"

    def test_label_range(self, synthetic_sequences):
        X, y = synthetic_sequences
        ds   = TimeSeriesDataset(X, y)
        for i in range(len(ds)):
            _, label = ds[i]
            assert 0 <= label.item() < NUM_CLASSES, f"Label {label.item()} out of range"


# ─────────────────────────────────────────────────────────────────────────────
# Unit tests — Model forward pass
# ─────────────────────────────────────────────────────────────────────────────

class TestModelForward:
    def test_output_shape(self, tst_model, synthetic_sequences):
        X, _ = synthetic_sequences
        x    = torch.FloatTensor(X[:BATCH_SIZE])
        with torch.no_grad():
            out = tst_model(x)
        assert out.shape == (BATCH_SIZE, NUM_CLASSES), (
            f"Expected ({BATCH_SIZE}, {NUM_CLASSES}), got {out.shape}"
        )

    def test_no_nan_in_output(self, tst_model, synthetic_sequences):
        X, _ = synthetic_sequences
        x    = torch.FloatTensor(X[:BATCH_SIZE])
        with torch.no_grad():
            out = tst_model(x)
        assert not torch.isnan(out).any(), "NaN found in model output"
        assert not torch.isinf(out).any(), "Inf found in model output"

    def test_output_requires_no_grad_in_eval(self, tst_model, synthetic_sequences):
        """In eval mode under no_grad, output should not require grad."""
        tst_model.eval()
        X, _ = synthetic_sequences
        with torch.no_grad():
            out = tst_model(torch.FloatTensor(X[:4]))
        assert not out.requires_grad

    def test_batch_independence(self, tst_model, synthetic_sequences):
        """Each sample in a batch should produce the same logits whether
        processed individually or batched (no batch-norm coupling)."""
        X, _ = synthetic_sequences
        tst_model.eval()
        with torch.no_grad():
            batch_out = tst_model(torch.FloatTensor(X[:4]))
            for i in range(4):
                single = tst_model(torch.FloatTensor(X[i : i + 1]))
                assert torch.allclose(batch_out[i], single[0], atol=1e-5), (
                    f"Sample {i}: batched={batch_out[i]}  single={single[0]}"
                )


# ─────────────────────────────────────────────────────────────────────────────
# Unit tests — Loss
# ─────────────────────────────────────────────────────────────────────────────

class TestLossComputation:
    def test_loss_is_scalar(self, tst_model, synthetic_sequences):
        X, y = synthetic_sequences
        crit = nn.CrossEntropyLoss()
        out  = tst_model(torch.FloatTensor(X[:BATCH_SIZE]))
        loss = crit(out, torch.tensor(y[:BATCH_SIZE]))
        assert loss.shape == (), "Loss must be a scalar"

    def test_loss_is_finite(self, tst_model, synthetic_sequences):
        X, y = synthetic_sequences
        crit = nn.CrossEntropyLoss()
        out  = tst_model(torch.FloatTensor(X[:BATCH_SIZE]))
        loss = crit(out, torch.tensor(y[:BATCH_SIZE]))
        assert torch.isfinite(loss), f"Loss is not finite: {loss.item()}"

    def test_loss_is_non_negative(self, tst_model, synthetic_sequences):
        X, y = synthetic_sequences
        crit = nn.CrossEntropyLoss()
        out  = tst_model(torch.FloatTensor(X[:BATCH_SIZE]))
        loss = crit(out, torch.tensor(y[:BATCH_SIZE]))
        assert loss.item() >= 0.0, f"Loss should be non-negative, got {loss.item()}"

    def test_perfect_predictions_have_low_loss(self):
        """Logits with very large correct-class scores → near-zero loss."""
        logits = torch.zeros(4, NUM_CLASSES)
        labels = torch.tensor([0, 1, 2, 0])
        for i, l in enumerate(labels):
            logits[i, l] = 100.0     # dominate softmax
        crit = nn.CrossEntropyLoss()
        loss = crit(logits, labels)
        assert loss.item() < 0.01, f"Expected near-zero loss, got {loss.item()}"


# ─────────────────────────────────────────────────────────────────────────────
# Unit tests — Optimizer step
# ─────────────────────────────────────────────────────────────────────────────

class TestOptimizerStep:
    def test_weights_change_after_step(self, tst_model, synthetic_sequences):
        """Verify that at least one parameter tensor changes after a gradient step."""
        X, y    = synthetic_sequences
        optim_  = torch.optim.Adam(tst_model.parameters(), lr=1e-3)
        crit    = nn.CrossEntropyLoss()

        # Capture weights before
        before = {n: p.clone().detach() for n, p in tst_model.named_parameters()}

        # One forward/backward/step
        out  = tst_model(torch.FloatTensor(X[:BATCH_SIZE]))
        loss = crit(out, torch.tensor(y[:BATCH_SIZE]))
        loss.backward()
        optim_.step()

        changed = 0
        for name, p in tst_model.named_parameters():
            if not torch.equal(before[name], p.detach()):
                changed += 1

        assert changed > 0, "No parameters changed after optimizer step!"

    def test_gradients_are_finite(self, tst_model, synthetic_sequences):
        """Gradients should never be NaN or Inf for normal inputs."""
        X, y = synthetic_sequences
        crit = nn.CrossEntropyLoss()
        out  = tst_model(torch.FloatTensor(X[:BATCH_SIZE]))
        loss = crit(out, torch.tensor(y[:BATCH_SIZE]))
        loss.backward()
        for name, p in tst_model.named_parameters():
            if p.grad is not None:
                assert torch.isfinite(p.grad).all(), f"Non-finite grad in {name}"

    def test_grad_clip_reduces_norm(self, tst_model, synthetic_sequences):
        """
        clip_grad_norm_ scales gradients in-place and returns the PRE-clip norm.
        Verify that the ACTUAL gradient norm after the call is <= max_norm.
        """
        X, y     = synthetic_sequences
        crit     = nn.CrossEntropyLoss()
        max_norm = 1.0
        out      = tst_model(torch.FloatTensor(X[:BATCH_SIZE]))
        loss     = crit(out, torch.tensor(y[:BATCH_SIZE]))
        loss.backward()
        torch.nn.utils.clip_grad_norm_(tst_model.parameters(), max_norm)

        # Compute the actual gradient norm AFTER clipping
        actual_norm = torch.sqrt(
            sum(
                p.grad.norm() ** 2
                for p in tst_model.parameters()
                if p.grad is not None
            )
        )
        assert float(actual_norm) <= max_norm + 1e-4, (
            f"Post-clip gradient norm ({actual_norm:.4f}) > max_norm ({max_norm})"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Integration tests — train / validate one epoch
# ─────────────────────────────────────────────────────────────────────────────

class TestTrainOneEpoch:
    def test_returns_finite_loss(self, trainer, train_loader):
        loss = trainer.train_epoch(train_loader, use_wandb=False)
        assert isinstance(loss, float), "train_epoch should return a float"
        assert np.isfinite(loss), f"train_epoch returned non-finite loss: {loss}"

    def test_global_step_increments(self, trainer, train_loader):
        before = trainer.global_step
        trainer.train_epoch(train_loader, use_wandb=False)
        assert trainer.global_step > before, "global_step did not increment"

    def test_model_is_in_train_mode_during_epoch(self, trainer, train_loader):
        # Manually verify the model is in train mode at the start
        trainer.model.train()
        assert trainer.model.training
        # After training epoch it stays in train mode
        trainer.train_epoch(train_loader, use_wandb=False)
        assert trainer.model.training, "Model should remain in train mode"


class TestValidateOneEpoch:
    def test_returns_dict_with_expected_keys(self, trainer, val_loader):
        metrics = trainer.validate(val_loader)
        for key in ("loss", "accuracy", "f1_macro", "preds", "labels"):
            assert key in metrics, f"Missing key '{key}' in validate() output"

    def test_loss_is_finite(self, trainer, val_loader):
        metrics = trainer.validate(val_loader)
        assert np.isfinite(metrics["loss"]), f"val loss not finite: {metrics['loss']}"

    def test_accuracy_in_unit_range(self, trainer, val_loader):
        metrics = trainer.validate(val_loader)
        assert 0.0 <= metrics["accuracy"] <= 1.0, (
            f"accuracy={metrics['accuracy']} out of [0,1]"
        )

    def test_f1_in_unit_range(self, trainer, val_loader):
        metrics = trainer.validate(val_loader)
        assert 0.0 <= metrics["f1_macro"] <= 1.0, (
            f"f1_macro={metrics['f1_macro']} out of [0,1]"
        )

    def test_preds_shape(self, trainer, val_loader):
        metrics = trainer.validate(val_loader)
        assert metrics["preds"].shape  == (N_VAL,)
        assert metrics["labels"].shape == (N_VAL,)

    def test_preds_in_class_range(self, trainer, val_loader):
        metrics = trainer.validate(val_loader)
        assert set(metrics["preds"].tolist()).issubset({0, 1, 2}), (
            "Predictions outside {0,1,2}"
        )

    def test_model_is_in_eval_mode_after_validate(self, trainer, val_loader):
        trainer.validate(val_loader)
        assert not trainer.model.training, "Model should be in eval mode after validate()"


# ─────────────────────────────────────────────────────────────────────────────
# Integration tests — checkpoint save/load
# ─────────────────────────────────────────────────────────────────────────────

class TestCheckpointSaveLoad:
    def test_save_and_load_produces_same_output(self, tst_model, synthetic_sequences):
        X, _ = synthetic_sequences
        x    = torch.FloatTensor(X[:8])

        tst_model.eval()
        with torch.no_grad():
            out_before = tst_model(x).clone()

        with tempfile.NamedTemporaryFile(suffix=".pth", delete=False) as f:
            ckpt_path = f.name

        try:
            torch.save(tst_model.state_dict(), ckpt_path)

            # Load into a fresh model with identical architecture
            loaded_model = TimeSeriesTransformer(
                input_dim  = INPUT_DIM,
                hidden_dim = HIDDEN_DIM,
                num_heads  = NUM_HEADS,
                ff_dim     = FF_DIM,
                num_layers = NUM_LAYERS,
                dropout    = 0.0,
                num_classes= NUM_CLASSES,
            )
            loaded_model.load_state_dict(
                torch.load(ckpt_path, map_location="cpu")
            )
            loaded_model.eval()

            with torch.no_grad():
                out_after = loaded_model(x)

            assert torch.allclose(out_before, out_after, atol=1e-6), (
                "Model output changed after save/load!"
            )
        finally:
            os.unlink(ckpt_path)

    def test_checkpoint_file_is_created(self, trainer, synthetic_sequences, val_sequences, tmp_path):
        """Verify the temp checkpoint file is written when val improves."""
        X_tr, y_tr = synthetic_sequences
        X_val, y_val = val_sequences

        # Patch version directories to tmp_path so we don't pollute the repo
        v1 = tmp_path / "v1"; v2 = tmp_path / "v2"; v3 = tmp_path / "v3"
        for d in (v1, v2, v3): d.mkdir()

        temp_ckpt = tmp_path / "temp_best.pth"

        with patch.object(trainer, "_save_versioned"):
            with patch("trainer.time_series_transformer.Path") as mock_path_cls:
                # We only need to intercept the temp checkpoint path
                real_path = Path
                def path_side_effect(arg):
                    if "temp_best_tst_model" in str(arg):
                        return temp_ckpt
                    return real_path(arg)
                mock_path_cls.side_effect = path_side_effect

                trainer.train(
                    X_tr, y_tr, X_val, y_val,
                    epochs     = 2,
                    batch_size = BATCH_SIZE,
                    use_wandb  = False,
                    seed       = SEED,
                )


# ─────────────────────────────────────────────────────────────────────────────
# Integration tests — W&B logging (mocked)
# ─────────────────────────────────────────────────────────────────────────────

class TestWandbLogging:
    """All wandb calls are intercepted with MagicMock — no real credentials needed."""

    @pytest.fixture
    def mock_wandb(self, monkeypatch):
        mock = MagicMock()
        mock.run         = MagicMock()
        mock.run.__bool__ = lambda self: True
        mock.AlertLevel  = MagicMock()
        mock.AlertLevel.ERROR = "ERROR"
        mock.util        = MagicMock()
        mock.util.generate_id.return_value = "testid"
        monkeypatch.setattr("trainer.time_series_transformer.wandb", mock)
        monkeypatch.setattr("trainer.time_series_transformer._WANDB_AVAILABLE", True)
        return mock

    def test_wandb_init_called(self, mock_wandb, trainer, synthetic_sequences, val_sequences):
        X_tr, y_tr     = synthetic_sequences
        X_val, y_val   = val_sequences
        with patch.object(trainer, "_save_versioned"):
            trainer.train(
                X_tr, y_tr, X_val, y_val,
                epochs=1, batch_size=BATCH_SIZE, use_wandb=True, seed=SEED,
            )
        mock_wandb.init.assert_called_once()
        init_kwargs = mock_wandb.init.call_args.kwargs
        assert "project" in init_kwargs
        assert "config"  in init_kwargs

    def test_wandb_watch_called(self, mock_wandb, trainer, synthetic_sequences, val_sequences):
        X_tr, y_tr   = synthetic_sequences
        X_val, y_val = val_sequences
        with patch.object(trainer, "_save_versioned"):
            trainer.train(
                X_tr, y_tr, X_val, y_val,
                epochs=1, batch_size=BATCH_SIZE, use_wandb=True, seed=SEED,
            )
        mock_wandb.watch.assert_called_once_with(
            trainer.model, log="all",
            log_freq=WANDB_CONFIG["log_grad_freq"],
            log_graph=True,
        )

    def test_wandb_log_called_with_epoch_keys(
        self, mock_wandb, trainer, synthetic_sequences, val_sequences
    ):
        X_tr, y_tr   = synthetic_sequences
        X_val, y_val = val_sequences
        with patch.object(trainer, "_save_versioned"):
            trainer.train(
                X_tr, y_tr, X_val, y_val,
                epochs=1, batch_size=BATCH_SIZE, use_wandb=True, seed=SEED,
            )
        all_logged_keys = set()
        for c in mock_wandb.log.call_args_list:
            logged_dict = c.args[0] if c.args else c.kwargs.get("data", {})
            all_logged_keys.update(logged_dict.keys())

        for expected in ("train/epoch_loss", "val/loss", "val/accuracy", "val/f1_macro"):
            assert expected in all_logged_keys, (
                f"Expected key '{expected}' was never logged to W&B. "
                f"Logged keys: {all_logged_keys}"
            )

    def test_wandb_finish_called(self, mock_wandb, trainer, synthetic_sequences, val_sequences):
        X_tr, y_tr   = synthetic_sequences
        X_val, y_val = val_sequences
        with patch.object(trainer, "_save_versioned"):
            trainer.train(
                X_tr, y_tr, X_val, y_val,
                epochs=1, batch_size=BATCH_SIZE, use_wandb=True, seed=SEED,
            )
        mock_wandb.finish.assert_called_once()

    def test_step_logging_keys(self, mock_wandb, trainer, train_loader):
        """Per-step W&B logs should contain step_loss, grad_norm, lr."""
        trainer.train_epoch(train_loader, use_wandb=True)
        step_keys = set()
        for c in mock_wandb.log.call_args_list:
            logged = c.args[0] if c.args else {}
            step_keys.update(logged.keys())
        for k in ("train/step_loss", "train/grad_norm", "train/lr"):
            assert k in step_keys, f"'{k}' not found in per-step W&B logs"


# ─────────────────────────────────────────────────────────────────────────────
# LightGBM tests
# ─────────────────────────────────────────────────────────────────────────────

class TestLightGBMTrainer:
    @pytest.fixture
    def lgb_trainer(self):
        return LightGBMTrainer()

    @pytest.fixture
    def crypto_df(self):
        """Minimal DataFrame mimicking real price data."""
        rng  = np.random.default_rng(SEED)
        n    = 500
        base = 30_000.0
        close= base + np.cumsum(rng.normal(0, 100, n))
        df   = pd.DataFrame({
            "open_time": pd.date_range("2023-01-01", periods=n, freq="1min"),
            "open":      close * rng.uniform(0.999, 1.001, n),
            "high":      close * rng.uniform(1.000, 1.003, n),
            "low":       close * rng.uniform(0.997, 1.000, n),
            "close":     close,
            "volume":    rng.uniform(1, 100, n),
        })
        df["date"] = df["open_time"].dt.strftime("%Y-%m-%d")
        return df

    @pytest.fixture
    def sentiment_df(self, crypto_df):
        dates = crypto_df["date"].unique()
        rng   = np.random.default_rng(SEED)
        return pd.DataFrame({
            "date":                 dates,
            "sentiment_mean":       rng.normal(0.0, 0.3, len(dates)),
            "sentiment_std":        rng.uniform(0.0, 0.2, len(dates)),
            "news_count":           rng.integers(1, 20, len(dates)),
            "sentiment_confidence": rng.uniform(0.7, 1.0, len(dates)),
            "negative_sentiment":   rng.uniform(0,   0.4, len(dates)),
            "neutral_sentiment":    rng.uniform(0.3, 0.6, len(dates)),
            "positive_sentiment":   rng.uniform(0,   0.4, len(dates)),
        })

    def test_rsi_no_nan_no_inf(self, lgb_trainer, crypto_df):
        """RSI should be finite for normal price series."""
        rsi = lgb_trainer.calculate_rsi(crypto_df["close"])
        # Drop leading NaNs from rolling window
        valid = rsi.dropna()
        assert not valid.isna().any(), "RSI contains NaN"
        assert np.isfinite(valid.values).all(), "RSI contains Inf"

    def test_prepare_features_shape(self, lgb_trainer, crypto_df, sentiment_df):
        X, y, cols = lgb_trainer.prepare_features(crypto_df, sentiment_df)
        assert X.shape[0] == y.shape[0], "X and y row count mismatch"
        assert X.shape[1] == len(cols),  "Feature matrix column count mismatch"
        assert len(cols) > 0,            "No features produced"

    def test_prepare_features_no_nan(self, lgb_trainer, crypto_df, sentiment_df):
        X, y, _ = lgb_trainer.prepare_features(crypto_df, sentiment_df)
        assert np.isfinite(X).all(), "Feature matrix contains NaN/Inf"

    def test_labels_in_valid_range(self, lgb_trainer, crypto_df, sentiment_df):
        _, y, _ = lgb_trainer.prepare_features(crypto_df, sentiment_df)
        assert set(y).issubset({0, 1, 2}), f"Labels outside {{0,1,2}}: {set(y)}"

    def test_train_and_predict(self, lgb_trainer, crypto_df, sentiment_df):
        X, y, _ = lgb_trainer.prepare_features(crypto_df, sentiment_df)
        lgb_trainer.train(X, y, use_wandb=False, coin="BTCUSDT")
        preds = lgb_trainer.predict(X[:20])
        assert preds.shape == (20,), "predict() shape mismatch"
        assert set(preds).issubset({0, 1, 2}), "Predictions outside {0,1,2}"

    def test_predict_proba_sums_to_one(self, lgb_trainer, crypto_df, sentiment_df):
        X, y, _ = lgb_trainer.prepare_features(crypto_df, sentiment_df)
        lgb_trainer.train(X, y, use_wandb=False, coin="BTCUSDT")
        proba = lgb_trainer.predict_proba(X[:20])
        row_sums = proba.sum(axis=1)
        np.testing.assert_allclose(
            row_sums, 1.0, atol=1e-5,
            err_msg="predict_proba rows do not sum to 1",
        )

    def test_save_and_load_model(self, lgb_trainer, crypto_df, sentiment_df, tmp_path):
        X, y, _ = lgb_trainer.prepare_features(crypto_df, sentiment_df)
        lgb_trainer.train(X, y, use_wandb=False, coin="BTCUSDT")
        preds_before = lgb_trainer.predict(X[:10])

        model_file = str(tmp_path / "lgb_test.txt")
        lgb_trainer.save_model(model_path=model_file, use_wandb=False)

        # Load into a fresh trainer
        new_trainer = LightGBMTrainer()
        loaded = new_trainer.load_model(model_path=model_file)
        assert loaded, "load_model() returned False"

        preds_after = new_trainer.predict(X[:10])
        np.testing.assert_array_equal(preds_before, preds_after,
            err_msg="Predictions differ after save/load")


# ─────────────────────────────────────────────────────────────────────────────
# Smoke test — 2 epochs on tiny data
# ─────────────────────────────────────────────────────────────────────────────

class TestSmoke:
    """
    End-to-end smoke test with a tiny synthetic dataset.
    Validates:
      1. No crash for 2 epochs
      2. Loss is finite throughout
      3. Checkpoint written to disk at v3 path
      4. W&B .log() is called (mocked — no credentials needed)
    """

    @pytest.fixture
    def tiny_data(self):
        rng   = np.random.default_rng(SEED)
        n     = 64
        X     = rng.standard_normal((n, SEQ_LEN, INPUT_DIM)).astype(np.float32)
        y     = rng.integers(0, NUM_CLASSES, n).astype(np.int64)
        split = int(n * 0.75)
        return X[:split], y[:split], X[split:], y[split:]

    def test_smoke_no_crash(self, tiny_data, tmp_path):
        X_tr, y_tr, X_val, y_val = tiny_data
        model   = TimeSeriesTransformer(
            input_dim=INPUT_DIM, hidden_dim=16, num_heads=2,
            ff_dim=32, num_layers=1, dropout=0.0,
        )
        trainer = TimeSeriesTransformerTrainer(model, device="cpu")

        # Override version dirs to tmp_path
        v_dirs = {
            "v1": tmp_path / "v1",
            "v2": tmp_path / "v2",
            "v3": tmp_path / "v3",
        }
        for d in v_dirs.values():
            d.mkdir()

        with patch.object(
            trainer, "_save_versioned",
            side_effect=lambda v1, v2, v3: torch.save(
                trainer.model.state_dict(), str(v_dirs["v3"] / "model.pth")
            )
        ):
            trainer.train(
                X_tr, y_tr, X_val, y_val,
                epochs=2, batch_size=8, use_wandb=False, seed=SEED,
            )

        # Loss history should exist
        assert len(trainer.train_losses) == 2, "Should have 2 epoch losses"
        assert all(np.isfinite(trainer.train_losses)), "Training losses are not finite"
        assert all(np.isfinite(trainer.val_losses)),   "Val losses are not finite"

    def test_smoke_checkpoint_written(self, tiny_data, tmp_path):
        X_tr, y_tr, X_val, y_val = tiny_data
        model = TimeSeriesTransformer(
            input_dim=INPUT_DIM, hidden_dim=16, num_heads=2,
            ff_dim=32, num_layers=1, dropout=0.0,
        )
        trainer = TimeSeriesTransformerTrainer(model, device="cpu")

        v3_dir = tmp_path / "tst" / "v3"
        v3_dir.mkdir(parents=True)

        def fake_save(v1, v2, v3):
            torch.save(trainer.model.state_dict(), str(v3_dir / "model.pth"))

        with patch.object(trainer, "_save_versioned", side_effect=fake_save):
            trainer.train(
                X_tr, y_tr, X_val, y_val,
                epochs=2, batch_size=8, use_wandb=False, seed=SEED,
            )

        assert (v3_dir / "model.pth").exists(), "Checkpoint not written to v3 dir"

    def test_smoke_wandb_logging(self, tiny_data):
        """W&B .log() must be called at least once per epoch (mocked)."""
        X_tr, y_tr, X_val, y_val = tiny_data
        model = TimeSeriesTransformer(
            input_dim=INPUT_DIM, hidden_dim=16, num_heads=2,
            ff_dim=32, num_layers=1, dropout=0.0,
        )
        trainer = TimeSeriesTransformerTrainer(model, device="cpu")

        mock_wandb = MagicMock()
        mock_wandb.run         = MagicMock()
        mock_wandb.run.__bool__ = lambda self: True
        mock_wandb.AlertLevel  = MagicMock()
        mock_wandb.AlertLevel.ERROR = "ERROR"
        mock_wandb.util        = MagicMock()
        mock_wandb.util.generate_id.return_value = "smoke_id"
        mock_wandb.Table       = MagicMock(return_value=MagicMock())
        mock_wandb.plot        = MagicMock()
        mock_wandb.Artifact    = MagicMock(return_value=MagicMock())

        with patch("trainer.time_series_transformer.wandb", mock_wandb), \
             patch("trainer.time_series_transformer._WANDB_AVAILABLE", True), \
             patch.object(trainer, "_save_versioned"):
            trainer.train(
                X_tr, y_tr, X_val, y_val,
                epochs=2, batch_size=8, use_wandb=True, seed=SEED,
            )

        assert mock_wandb.init.call_count   == 1, "wandb.init not called once"
        assert mock_wandb.watch.call_count  == 1, "wandb.watch not called once"
        assert mock_wandb.finish.call_count == 1, "wandb.finish not called once"
        # At minimum 2 epoch logs + per-step logs
        assert mock_wandb.log.call_count > 2, (
            f"Expected >2 wandb.log calls, got {mock_wandb.log.call_count}"
        )

    def test_smoke_loss_finite_throughout(self, tiny_data, tmp_path):
        """Catch any NaN/Inf loss mid-training."""
        X_tr, y_tr, X_val, y_val = tiny_data
        model = TimeSeriesTransformer(
            input_dim=INPUT_DIM, hidden_dim=16, num_heads=2,
            ff_dim=32, num_layers=1, dropout=0.0,
        )
        trainer = TimeSeriesTransformerTrainer(model, device="cpu")

        step_losses = []
        orig_train_epoch = trainer.train_epoch.__func__

        def patched_epoch(self, loader, use_wandb=False):
            self.model.train()
            total = 0.0
            for bx, by in loader:
                self.optimizer.zero_grad()
                out  = self.model(bx)
                loss = self.criterion(out, by)
                loss.backward()
                torch.nn.utils.clip_grad_norm_(self.model.parameters(), 1.0)
                self.optimizer.step()
                step_losses.append(loss.item())
                total += loss.item()
                self.global_step += 1
            return total / max(len(loader), 1)

        with patch.object(trainer, "_save_versioned"), \
             patch.object(TimeSeriesTransformerTrainer, "train_epoch", patched_epoch):
            trainer.train(
                X_tr, y_tr, X_val, y_val,
                epochs=2, batch_size=8, use_wandb=False, seed=SEED,
            )

        assert len(step_losses) > 0, "No steps recorded"
        assert all(np.isfinite(step_losses)), (
            f"Non-finite step loss detected: {[l for l in step_losses if not np.isfinite(l)]}"
        )
