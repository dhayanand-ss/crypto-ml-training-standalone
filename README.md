<div align="center">

# 📈 Crypto ML Training

### Production-grade ensemble price prediction for **BTC · ETH · SOL**

*LightGBM + Time Series Transformer + FinBERT sentiment — orchestrated with Airflow, served via FastAPI, trained on Vast.ai GPUs.*

[![Python](https://img.shields.io/badge/python-3.10+-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![PyTorch](https://img.shields.io/badge/PyTorch-EE4C2C?logo=pytorch&logoColor=white)](https://pytorch.org/)
[![LightGBM](https://img.shields.io/badge/LightGBM-43A047?logo=lightgbm&logoColor=white)](https://lightgbm.readthedocs.io/)
[![Airflow](https://img.shields.io/badge/Airflow-017CEE?logo=apache-airflow&logoColor=white)](https://airflow.apache.org/)
[![Kafka](https://img.shields.io/badge/Kafka-231F20?logo=apachekafka&logoColor=white)](https://kafka.apache.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![MLflow](https://img.shields.io/badge/MLflow-0194E2?logo=mlflow&logoColor=white)](https://mlflow.org/)
[![ONNX](https://img.shields.io/badge/ONNX-005CED?logo=onnx&logoColor=white)](https://onnx.ai/)
[![Docker](https://img.shields.io/badge/Docker-2496ED?logo=docker&logoColor=white)](https://www.docker.com/)

</div>

---

## ✨ Highlights

- 🧠 **Three-model ensemble** — LightGBM (technicals + sentiment), Time Series Transformer (sequence dynamics), and FinBERT/TRL (news sentiment).
- ⚡ **Live inference** — ONNX-served FastAPI endpoint backed by Kafka stream of Binance candles.
- 🔁 **Zero-downtime rollouts** — 3-slot rolling version registry (v3 → v2 → v1) with hot-swappable consumers.
- ☁️ **Distributed training** — auto-provisions Vast.ai GPU instances under a $0.25/hour budget cap.
- 🪣 **Bidirectional Kafka ↔ GCS bridge** — archive every topic to partitioned JSONL, replay any date range.
- 📊 **Full observability** — Prometheus + Grafana on FastAPI; MLflow + W&B for experiments.

> **Output classes:** `SELL (0)` · `HOLD (1)` · `BUY (2)`

---

## 📑 Table of Contents

1. [Quick Start](#-quick-start)
2. [Architecture](#-architecture)
3. [Pipeline Details](#-pipeline-details)
4. [Model Versioning](#-model-versioning)
5. [Configuration](#-configuration)
6. [Docker Compose](#-docker-compose)
7. [Operational Notes](#-operational-notes)

---

## 🚀 Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Train all three models locally
python simplified_integrated_model.py

# 3. Or launch distributed training on Vast.ai GPUs
python run_vast_ai_training.py

# 4. Bring up the full stack (Airflow + Kafka + FastAPI)
./start-all-services.ps1
```

| Service | URL |
|---|---|
| 🌬️ Airflow webserver | http://localhost:8080 |
| ⚡ FastAPI inference | http://localhost:8000 |
| 📈 Prometheus | http://localhost:9090 |

> 💡 **No Docker?** Use `./start-all-standalone.ps1` for a local-only test stack.

---

## 🏗️ Architecture

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
                  │  Training  (local | Vast.ai GPU)       │
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

---

## 🔧 Pipeline Details

### 📥 Data Ingestion

| Source | Module | Output |
|---|---|---|
| Binance REST (historical OHLCV) | `data_fetcher.py` | `data/prices/` |
| Binance WS (live candles) | `utils/producer_consumer/producer.py` | Kafka topics |
| Yahoo Finance (news, Playwright) | `utils/articles_runner/scrape.py`, `past_news_scrape.py` | `data/articles.csv` |
| News dataset assembly | `create_news_dataset.py`, `download_more_articles.py` | `data/articles.csv` |

### 🏋️ Training

- **Local integrated run** — `simplified_integrated_model.py` trains all three model types sequentially.
- **Distributed (Vast.ai)** — `run_vast_ai_training.py` and `run_trl_vast_ai.py` provision GPU instances via `utils/trainer/vast_ai_api.py`; remote workers (`vast_client.py`, `vast_trainer.py`) execute trainers from `utils/trainer/` (`lightgbm_train.py`, `tst_train.py`, `trl_train.py`, `vast_ai_trl_train.py`).
- **Job lifecycle** — `utils/utils/training_job_manager.py` and `utils/producer_consumer/job_handler.py` watch job files and manage producer/consumer process lifecycle around training.

### 🌬️ Orchestration (Airflow, `dags/`)

| DAG | Purpose |
|---|---|
| `DAG.py` | Main training pipeline — provisions 7 Vast.ai instances (3 cryptos × 2 models + TRL), polls PostgreSQL, registers models |
| `trl_infer_dag.py` | TRL / sentiment inference pipeline |
| `cleanup_DAG.py` | Cleanup tasks |

### 🔄 Streaming & Storage Bridge

- **Kafka producer/consumer** — `utils/producer_consumer/`; **6 consumers** (3 cryptos × 2 model types × v1/v2/v3) write predictions locally.
- **GCS ↔ Kafka bridge** (`gcs_kafka_bridge.py`):
  - `GCSKafkaSink` → archives every active Kafka topic as partitioned JSONL (`archive/<topic>/year=YYYY/month=MM/day=DD/...`).
  - `GCSKafkaSeeder` → replays archived data back into Kafka (full, date-ranged, or "latest N").
  - Credentials via `gcs_credentials.py`.

### ⚡ Inference

- **FastAPI** (`utils/serve/fastapi_app.py`) — loads ONNX models, exposes `/predict`, `/batch_predict`, `/health`, `/metrics`, `/refresh` on port 8000.
- **TRL inference** — `utils/serve/trl_inference.py` runs FinBERT sentiment on scraped articles.
- **ONNX conversion** — `convert_to_onnx.py` and `utils/serve/trl_onnx_maker.py` export trained models to `models/onnx/` for serving.
- **Output formatter** — `utils/project_output_formatter.py` shapes combined ensemble predictions into JSON.

### 📊 Experiment Tracking & Artifacts

| Layer | Tool | Module |
|---|---|---|
| Experiment tracking | MLflow | `utils/artifact_control/model_manager.py` · `Dockerfile.mlflow` |
| Run logging | Weights & Biases | `wandb/` |
| Cloud storage | Google Cloud Storage | `utils/artifact_control/gcs_manager.py` |
| Cloud storage | AWS S3 | `utils/artifact_control/s3_manager.py` |

### 🗄️ Database

PostgreSQL (`utils/database/db.py`, `status_db.py`, `airflow_db.py`) tracks training status:

```
PENDING → RUNNING → SUCCESS / FAILED
```

Status changes trigger consumer stop/restart and post-training reconciliation (`utils/utils/post_train_reconcile.py`, `post_train_trl.py`).

### 📈 Monitoring

- **Prometheus** — scrapes FastAPI `/metrics` every 15s (`prometheus.yml`, job `fastapi-ml`).
- **Grafana** — dashboards under `grafana/`.

---

## 🔁 Model Versioning

A **3-slot rolling registry** (`models/version_registry.json`, managed by `utils/model_version_manager.py`) handles zero-downtime deployment:

```
       new model
          │
          ▼
        ┌────┐    ┌────┐    ┌────┐
        │ v3 │ →  │ v2 │ →  │ v1 │ ─► dropped
        └────┘    └────┘    └────┘
```

Each slot has dedicated live-serving consumers.

**Artifact layout:**
```
models/
├── lightgbm/{v1,v2,v3}/    # LightGBM models
├── tst/{v1,v2,v3}/         # Time Series Transformer
└── onnx/                   # ONNX exports for serving
```

---

## ⚙️ Configuration

Key environment variables (see `.env.example` for the full list):

| Variable | Purpose |
|---|---|
| `VASTAI_API_KEY` | Vast.ai GPU provisioning |
| `GCP_PROJECT_ID` / `GCP_CREDENTIALS_PATH` | Google Cloud |
| `MLFLOW_URI` | MLflow tracking server |
| `KAFKA_HOST` | Kafka broker endpoint |
| `FASTAPI_URL` | Inference service URL |
| `DB_HOST` / `DB_USER` / `DB_PASSWORD` | PostgreSQL |

---

## 🐳 Docker Compose

| File | Stack |
|---|---|
| `docker-compose.yml` | Airflow webserver + scheduler + PostgreSQL |
| `docker-compose.airflow.yml` | Enhanced — adds job-handler service and Kafka networking |
| `docker-compose.fastapi.yml` | Standalone FastAPI inference service |
| `k8-setup/kafka.yml` | Kafka + Zookeeper + Schema Registry |

---

## ⚠️ Operational Notes

> 📰 **News data is required** — TRL/FinBERT training fails without `data/articles.csv`. Run `create_news_dataset.py` first.

> 🔄 **ONNX conversion is mandatory before serving** — native `.txt` / `.pth` files are trained locally; run `convert_to_onnx.py` before FastAPI can load them.

> 🔌 **Consumer lifecycle** — consumers stop before training and restart after model registration. **Prediction gaps during training are expected and not backfilled.**

> 💰 **Vast.ai budget cap** — training instances are limited to **~$0.25/hour**. Adjust in `utils/trainer/vast_ai_api.py`.

> 💥 **Version shift is destructive** — registering a new model immediately rotates the registry. **v1 artifacts are dropped.**
