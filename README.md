# Crypto ML Training (Standalone)

A cryptocurrency price prediction ML system that trains and serves ensemble predictions for **BTC, ETH, and SOL** (BTCUSDT, ETHUSDT, SOLUSDT). The system outputs 3-class predictions: **SELL (0), HOLD (1), BUY (2)**.

## Models

The ensemble combines three model types:

- **LightGBM** — gradient boosting on technical indicators + sentiment features
- **Time Series Transformer (TST)** — PyTorch transformer for sequence prediction
- **FinBERT / TRL** — news sentiment via LoRA-fine-tuned FinBERT

## Architecture

```
                   Binance REST            Yahoo Finance (Playwright)
                        │                              │
                        ▼                              ▼
                  data_fetcher.py            utils/articles_runner/
                        │                              │
                        ▼                              ▼
                  data/prices/                data/articles.csv
                        │                              │
                        └──────────────┬───────────────┘
                                       ▼
                  ┌────────────────────────────────────────┐
                  │  Training (local | Vast.ai GPU)        │
                  │  LightGBM • TST • FinBERT/TRL          │
                  └────────────────────────────────────────┘
                                       │
              ┌────────────────────────┼─────────────────────────┐
              ▼                        ▼                         ▼
     models/{lightgbm,tst}      MLflow + W&B          GCS / S3 artifacts
              │
              ▼
       ONNX conversion ──► models/onnx/
                                       │
   Binance WS ──► Kafka producer ──► Kafka topics ──► consumers (v1/v2/v3)
                                       │                       │
                                       ▼                       ▼
                            gcs_kafka_bridge (archive)   prediction files
                                                                │
                                                                ▼
                                                    FastAPI /predict, /metrics
                                                                │
                                                                ▼
                                                       Prometheus + Grafana
```

### Data Ingestion

- **Historical OHLCV** — `data_fetcher.py` pulls candles from the Binance REST API into `data/prices/` for offline training.
- **Live OHLCV** — Kafka producers (`utils/producer_consumer/producer.py`) stream live Binance candles to per-symbol topics.
- **News scraping** — `utils/articles_runner/scrape.py` and `past_news_scrape.py` scrape Yahoo Finance via Playwright; `create_news_dataset.py` / `download_more_articles.py` assemble `data/articles.csv` for TRL/FinBERT training.

### Training

- **Local integrated run** — `simplified_integrated_model.py` trains all three model types sequentially.
- **Distributed (Vast.ai)** — `run_vast_ai_training.py` and `run_trl_vast_ai.py` provision GPU instances via `utils/trainer/vast_ai_api.py`; remote workers (`vast_client.py`, `vast_trainer.py`) execute trainers from `utils/trainer/` (`lightgbm_train.py`, `tst_train.py`, `trl_train.py`, `vast_ai_trl_train.py`).
- **Job lifecycle** — `utils/utils/training_job_manager.py` and `utils/producer_consumer/job_handler.py` watch job files and manage producer/consumer process lifecycle around training.

### Orchestration (Airflow, `dags/`)

- `DAG.py` — main training pipeline: provisions 7 Vast.ai instances (3 cryptos × 2 models + TRL), polls PostgreSQL, registers models.
- `trl_infer_dag.py` — TRL/sentiment inference pipeline.
- `cleanup_DAG.py` — cleanup tasks.

Airflow webserver: `http://localhost:8080`.

### Streaming & Storage Bridge

- **Kafka producer/consumer** — `utils/producer_consumer/`; 6 consumers (3 cryptos × 2 model types × v1/v2/v3 slots) write predictions to local files.
- **GCS ↔ Kafka bridge** — `gcs_kafka_bridge.py` provides bidirectional archive/replay:
  - `GCSKafkaSink` archives every active Kafka topic to partitioned JSONL on GCS (`archive/<topic>/year=YYYY/month=MM/day=DD/...`).
  - `GCSKafkaSeeder` replays archived data back into Kafka (full, date-ranged, or "latest N").
  - Credentials: `gcs_credentials.py`.

### Inference

- **FastAPI** (`utils/serve/fastapi_app.py`) — loads ONNX models, exposes `/predict`, `/batch_predict`, `/health`, `/metrics`, `/refresh` on port 8000.
- **TRL inference** — `utils/serve/trl_inference.py` runs FinBERT sentiment on scraped articles.
- **ONNX conversion** — `convert_to_onnx.py` and `utils/serve/trl_onnx_maker.py` export trained models to `models/onnx/` for serving.
- **Output formatter** — `utils/project_output_formatter.py` shapes combined ensemble predictions into JSON responses.

### Model Versioning

A 3-slot registry (`models/version_registry.json`, managed by `utils/model_version_manager.py`) handles rolling deployment: new models enter as v3, shifting v3 → v2 → v1 (v1 is dropped). Each slot has consumers serving live predictions.

Model artifacts:
- `models/lightgbm/v{1,2,3}/` — LightGBM
- `models/tst/v{1,2,3}/` — TST
- `models/onnx/` — ONNX exports for serving

### Experiment Tracking & Artifacts

- **MLflow** — experiment tracking at `$MLFLOW_URI`; `utils/artifact_control/model_manager.py` handles registry interactions. Dedicated `Dockerfile.mlflow` for the tracking server.
- **Weights & Biases** — runs logged under `wandb/`.
- **Google Cloud Storage** — `utils/artifact_control/gcs_manager.py` (model + dataset artifacts).
- **AWS S3** — `utils/artifact_control/s3_manager.py`.

### Database

PostgreSQL (`utils/database/db.py`, `utils/database/status_db.py`, `utils/database/airflow_db.py`) tracks training status (PENDING → RUNNING → SUCCESS/FAILED). Status changes trigger consumer stop/restart and post-training reconciliation (`utils/utils/post_train_reconcile.py`, `utils/utils/post_train_trl.py`).

### Monitoring

- **Prometheus** — scrapes FastAPI `/metrics` every 15s (`prometheus.yml`, job `fastapi-ml`).
- **Grafana** — dashboards under `grafana/`.

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
