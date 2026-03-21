# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## System Overview

This is a **Cryptocurrency Price Prediction ML System** that trains and serves ensemble predictions combining:
- **LightGBM** — gradient boosting with technical indicators + sentiment features
- **Time Series Transformer (TST)** — PyTorch transformer for sequence prediction
- **FinBERT/TRL** — news sentiment via LoRA-fine-tuned FinBERT

Supports BTC, ETH, SOL (BTCUSDT, ETHUSDT, SOLUSDT). Outputs 3-class predictions: SELL (0), HOLD (1), BUY (2).

## Common Commands

```bash
# Local integrated training (all models)
python simplified_integrated_model.py

# Launch distributed training on Vast.ai GPU instances
python run_vast_ai_training.py

# Start full Docker stack (Airflow + Kafka + FastAPI)
./start-all-services.ps1

# Start local stack without Docker (testing)
./start-all-standalone.ps1

# Start FastAPI inference server only
./start_fastapi_web.ps1

# Install dependencies
pip install -r requirements.txt
```

## Architecture

### Training Pipeline

`simplified_integrated_model.py` is the monolithic entry point that trains all three model types sequentially on historical Binance OHLCV data from `data/prices/` and news data from `data/articles.csv`.

For production, `run_vast_ai_training.py` provisions Vast.ai GPU instances via REST API (`utils/trainer/vast_ai_api.py`) and runs remote training scripts from `utils/trainer/`.

### Airflow Orchestration (`dags/`)

- `DAG.py` — main training pipeline: provisions 7 Vast.ai instances (3 cryptos × 2 models + TRL), polls PostgreSQL for completion, registers models, manages consumer lifecycle
- `trl_infer_dag.py` — TRL/sentiment inference pipeline
- `cleanup_DAG.py` — cleanup tasks

Airflow webserver at `http://localhost:8080`.

### Model Versioning

A 3-slot version registry (`models/version_registry.json`, managed by `utils/model_version_manager.py`) handles rolling deployment: new models enter as v3, shifting v3→v2→v1 (v1 is dropped). Each slot has consumers serving live predictions.

Model files live in `models/lightgbm/v{1,2,3}/` and `models/tst/v{1,2,3}/`. ONNX exports for serving go to `models/onnx/`.

### Inference Stack

- **FastAPI** (`utils/serve/fastapi_app.py`) — loads ONNX models, serves `/predict`, `/batch_predict`, `/health`, `/metrics`, `/refresh`. Port 8000.
- **Kafka producers/consumers** (`utils/producer_consumer/`) — producers publish Binance candles; 6 consumers (3 cryptos × 2 model types × v1/v2/v3 slots) write predictions locally.
- `utils/project_output_formatter.py` — formats combined ensemble predictions into JSON responses.

### Data Flow

```
Binance API → Kafka producer → Kafka topics
                                    ↓
                           consumers per model/version
                                    ↓
                           local prediction files
                                    ↓
                           FastAPI /predict endpoint
```

### Database

PostgreSQL (via `utils/database/db.py`, `utils/database/status_db.py`) tracks training status (PENDING → RUNNING → SUCCESS/FAILED). Status changes trigger consumer stop/restart and post-training reconciliation (`utils/utils/post_train_reconcile.py`, `utils/utils/post_train_trl.py`).

### Cloud Storage

- `utils/artifact_control/gcs_manager.py` — Google Cloud Storage
- `utils/artifact_control/s3_manager.py` — AWS S3
- `utils/artifact_control/model_manager.py` — MLflow integration

MLflow experiment tracking at `$MLFLOW_URI`.

## Key Environment Variables

| Variable | Purpose |
|---|---|
| `VASTAI_API_KEY` | Vast.ai GPU provisioning |
| `GCP_PROJECT_ID` / `GCP_CREDENTIALS_PATH` | Google Cloud |
| `MLFLOW_URI` | MLflow tracking server |
| `KAFKA_HOST` | Kafka broker endpoint |
| `FASTAPI_URL` | Inference service URL |
| `DB_HOST` / `DB_USER` / `DB_PASSWORD` | PostgreSQL |

## Docker Compose Files

- `docker-compose.yml` — standard Airflow stack (webserver, scheduler, PostgreSQL)
- `docker-compose.airflow.yml` — enhanced with job-handler service and Kafka networking
- `k8-setup/kafka.yml` — Kafka + Zookeeper + Schema Registry

## Important Notes

- **News data required**: TRL/FinBERT training fails without `data/articles.csv`. Use `create_news_dataset.py` to generate it.
- **ONNX for serving**: Native `.txt`/`.pth` model files are trained locally; ONNX conversion (`convert_to_onnx.py`) is required before FastAPI can serve them.
- **Consumer lifecycle**: Consumers are stopped before training starts and restarted after model registration. Gaps in predictions during training are expected and not backfilled.
- **Vast.ai budget**: Training instances are constrained to ~$0.25/hour. Adjust in `utils/trainer/vast_ai_api.py`.
- **Version shift is destructive**: Registering a new model immediately rotates the version registry — v1 artifacts are dropped.
