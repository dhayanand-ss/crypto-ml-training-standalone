# Crypto ML Training (Standalone)

A cryptocurrency price prediction ML system that trains and serves ensemble predictions for **BTC, ETH, and SOL** (BTCUSDT, ETHUSDT, SOLUSDT). The system outputs 3-class predictions: **SELL (0), HOLD (1), BUY (2)**.

## Models

The ensemble combines three model types:

- **LightGBM** — gradient boosting on technical indicators + sentiment features
- **Time Series Transformer (TST)** — PyTorch transformer for sequence prediction
- **FinBERT / TRL** — news sentiment via LoRA-fine-tuned FinBERT

## Architecture

```
Binance API ──► Kafka producer ──► Kafka topics
                                       │
                                       ▼
                             consumers per model/version
                                       │
                                       ▼
                              local prediction files
                                       │
                                       ▼
                             FastAPI /predict endpoint
```

### Components

- **Training pipeline** — `simplified_integrated_model.py` trains all three model types on historical Binance OHLCV (`data/prices/`) and news data (`data/articles.csv`).
- **Distributed training** — `run_vast_ai_training.py` provisions Vast.ai GPU instances via REST API (`utils/trainer/vast_ai_api.py`).
- **Airflow orchestration** (`dags/`):
  - `DAG.py` — main training pipeline: provisions 7 Vast.ai instances (3 cryptos × 2 models + TRL), polls PostgreSQL, registers models.
  - `trl_infer_dag.py` — TRL/sentiment inference pipeline.
  - `cleanup_DAG.py` — cleanup tasks.
- **Inference** — FastAPI server (`utils/serve/fastapi_app.py`) loads ONNX models and exposes `/predict`, `/batch_predict`, `/health`, `/metrics`, `/refresh` on port 8000.
- **Streaming** — Kafka producers publish Binance candles; 6 consumers (3 cryptos × 2 model types × v1/v2/v3 slots) write predictions locally.

### Model Versioning

A 3-slot version registry (`models/version_registry.json`, managed by `utils/model_version_manager.py`) handles rolling deployment: new models enter as v3, shifting v3 → v2 → v1 (v1 is dropped). Each slot has consumers serving live predictions.

Model artifacts:
- `models/lightgbm/v{1,2,3}/` — LightGBM models
- `models/tst/v{1,2,3}/` — TST models
- `models/onnx/` — ONNX exports for serving

### Storage & Tracking

- **PostgreSQL** (`utils/database/`) — tracks training status (PENDING → RUNNING → SUCCESS/FAILED).
- **MLflow** — experiment tracking at `$MLFLOW_URI`.
- **Google Cloud Storage** — `utils/artifact_control/gcs_manager.py`.
- **AWS S3** — `utils/artifact_control/s3_manager.py`.

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

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
```

Airflow webserver: `http://localhost:8080`
FastAPI inference: `http://localhost:8000`

## Environment Variables

| Variable | Purpose |
|---|---|
| `VASTAI_API_KEY` | Vast.ai GPU provisioning |
| `GCP_PROJECT_ID` / `GCP_CREDENTIALS_PATH` | Google Cloud |
| `MLFLOW_URI` | MLflow tracking server |
| `KAFKA_HOST` | Kafka broker endpoint |
| `FASTAPI_URL` | Inference service URL |
| `DB_HOST` / `DB_USER` / `DB_PASSWORD` | PostgreSQL |

See `.env.example` for the full list.

## Docker Compose

- `docker-compose.yml` — standard Airflow stack (webserver, scheduler, PostgreSQL)
- `docker-compose.airflow.yml` — enhanced with job-handler service and Kafka networking
- `k8-setup/kafka.yml` — Kafka + Zookeeper + Schema Registry

## Notes

- **News data required**: TRL/FinBERT training fails without `data/articles.csv`. Use `create_news_dataset.py` to generate it.
- **ONNX for serving**: Native `.txt`/`.pth` model files are trained locally; ONNX conversion (`convert_to_onnx.py`) is required before FastAPI can serve them.
- **Consumer lifecycle**: Consumers are stopped before training starts and restarted after model registration. Gaps in predictions during training are expected and not backfilled.
- **Vast.ai budget**: Training instances are constrained to ~$0.25/hour. Adjust in `utils/trainer/vast_ai_api.py`.
- **Version shift is destructive**: Registering a new model immediately rotates the version registry — v1 artifacts are dropped.
