♦# DAG Process Flowcharts Documentation

## Overview

This document provides detailed step-by-step flowcharts for all DAG processes associated with each model type (LightGBM, TST, and TRL) in the crypto-mlops pipeline.

---

## Table of Contents

1. [LightGBM & TST Models Flowchart](#1-lightgbm--tst-models-per-crypto-btcusdt)
2. [TRL Model Flowchart](#2-trl-model-global)
3. [Consumer Start DAG Flowchart](#3-consumer-start-dag-schedule-once---runs-once)
4. [Summary of DAGs](#summary-of-dags-and-models)
5. [Key Processes Explained](#key-processes-explained)

---

## 1. LightGBM & TST Models (Per Crypto: BTCUSDT)

### DAG: `training_pipeline`
**Schedule:** Every 5 days  
**Location:** `dags/DAG.py`

### Process Flow

```
┌─────────────────────────────────────────────────────────────────┐
│ STEP 1: pre_train_dataset                                        │
│ - Prepare training datasets                                      │
│ - Update train/test splits                                       │
└────────────────────┬────────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────────┐
│ STEP 2: flush_and_init                                          │
│ - Flush airflow_db status table                                 │
│ - Initialize status entries for all models                       │
│   (Sets all to 'PENDING')                                       │
└────────────────────┬────────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────────┐
│ STEP 3: vast_ai_train                                           │
│ - Create VastAI instances                                       │
│ - Submit Kubernetes jobs for:                                    │
│   • BTCUSDT_lightgbm → lgb_train.py                            │
│   • BTCUSDT_tst → tst_train.py                                  │
│   • trl → trl_train.py                                          │
│                                                                  │
│   Each training job:                                             │
│   ├─ Downloads dataset from S3                                  │
│   ├─ Trains model                                               │
│   ├─ Generates predictions for entire dataset                    │
│   ├─ Saves predictions to S3 (v{N}.parquet)                     │
│   ├─ Converts model to ONNX                                     │
│   ├─ Saves model to MLflow                                      │
│   └─ Sets status in airflow_db:                                  │
│      • 'RUNNING' → during training                               │
│      • 'SUCCESS' → on completion                                 │
│      • 'FAILED' → on error                                       │
└────────────────────┬────────────────────────────────────────────┘
                     │
                     ├─────────────────┐
                     │                 │
                     ▼                 ▼
        ┌──────────────────────┐  ┌──────────────────────┐
        │ monitor_BTCUSDT_     │  │ monitor_BTCUSDT_tst  │
        │   lightgbm            │  │                      │
        │                       │  │                      │
        │ Polls airflow_db      │  │ Polls airflow_db     │
        │ every 10 seconds      │  │ every 10 seconds     │
        │                       │  │                      │
        │ Checks status:        │  │ Checks status:       │
        │ • PENDING/RUNNING →   │  │ • PENDING/RUNNING →  │
        │   Continue polling    │  │   Continue polling   │
        │ • SUCCESS → Branch to  │  │ • SUCCESS → Branch   │
        │   post_train          │  │   to post_train      │
        │ • FAILED → Branch to   │  │ • FAILED → Branch    │
        │   skip_model          │  │   to skip_model      │
        └──────────┬───────────┘  └──────────┬──────────┘
                   │                         │
        ┌──────────┴───────────┐  ┌──────────┴──────────┐
        │                      │  │                      │
        ▼                      ▼  ▼                      ▼
┌──────────────────┐  ┌──────────────┐  ┌──────────────────┐  ┌──────────────┐
│ post_train_      │  │ skip_model   │  │ post_train_      │  │ skip_model   │
│ BTCUSDT_         │  │              │  │ BTCUSDT_tst      │  │              │
│ lightgbm          │  │              │  │                  │  │              │
│                  │  │              │  │                  │  │              │
│ Runs:            │  │              │  │ Runs:            │  │              │
│ post_train_      │  │              │  │ post_train_      │  │              │
│ reconcile.py     │  │              │  │ reconcile.py     │  │              │
│ --crypto BTCUSDT │  │              │  │ --crypto BTCUSDT │  │              │
│ --model lightgbm │  │              │  │ --model tst      │  │              │
└────────┬─────────┘  └──────────────┘  └────────┬─────────┘  └──────────────┘
         │                                        │
         │                                        │
         └──────────────┬─────────────────────────┘
                        │
                        ▼
        ┌───────────────────────────────────────────────┐
        │ post_train_reconcile.py (for each model)     │
        │                                                 │
        │ IF versions <= 3:                              │
        │   ├─ Download predictions from S3 (v{N})       │
        │   ├─ Push predictions to PostgreSQL            │
        │   │   (bulk_update_predictions)                │
        │   ├─ Trigger FastAPI /refresh                  │
        │   └─ Create & start consumer for v{N}          │
        │                                                 │
        │ IF versions > 3:                                │
        │   ├─ Reassign S3 predictions (v3→v2, v4→v3)    │
        │   ├─ Delete v2 & v3 consumers                 │
        │   ├─ Trigger FastAPI /refresh                  │
        │   ├─ Shift DB columns (v3→v2)                 │
        │   ├─ Rename local CSV (v3→v2)                 │
        │   ├─ Create & start v2 consumer               │
        │   ├─ Download new v3 predictions from S3      │
        │   ├─ Push v3 predictions to PostgreSQL        │
        │   └─ Create & start v3 consumer                │
        └────────────────────┬──────────────────────────┘
                             │
                             ▼
        ┌───────────────────────────────────────────────┐
        │ monitor_all_to_kill                            │
        │ (Runs in parallel with monitoring)             │
        │                                                │
        │ Polls all model statuses                       │
        │ Waits until ALL models reach:                  │
        │ • SUCCESS or FAILED                            │
        └────────────────────┬──────────────────────────┘
                             │
                             ▼
        ┌───────────────────────────────────────────────┐
        │ final_kill_kill_vast_ai_instances              │
        │ - Kills all VastAI instances                  │
        │ - Cleanup resources                            │
        └───────────────────────────────────────────────┘
```

### Detailed Steps for LightGBM/TST

#### Step 1: Pre-Training Dataset Preparation
- **Task:** `pre_train_dataset`
- **Script:** `utils.utils.pre_train_dataset`
- **Actions:**
  - Prepares training datasets
  - Updates train/test data splits
  - Prepares data for model training

#### Step 2: Database Initialization
- **Task:** `flush_and_init`
- **Actions:**
  - Flushes the airflow_db status table
  - Initializes status entries for all models (LightGBM, TST, TRL)
  - Sets all model statuses to 'PENDING'

#### Step 3: Model Training
- **Task:** `vast_ai_train`
- **Script:** `utils.utils.vast_ai_train.create_instance`
- **Actions:**
  - Creates VastAI cloud instances
  - Submits Kubernetes training jobs for each model:
    - `BTCUSDT_lightgbm` → runs `lgb_train.py`
    - `BTCUSDT_tst` → runs `tst_train.py`
    - `trl` → runs `trl_train.py`

#### Step 4: Training Job Execution (Parallel)
Each training job performs:
1. Downloads dataset from S3
2. Trains the model
3. Generates predictions for entire training dataset
4. Saves predictions to S3 as `predictions/{crypto}/{model}/v{N}.parquet`
5. Converts model to ONNX format
6. Saves model to MLflow Model Registry
7. Updates status in airflow_db:
   - Sets to 'RUNNING' at start
   - Sets to 'SUCCESS' on completion
   - Sets to 'FAILED' on error

#### Step 5: Model State Monitoring
- **Tasks:** `monitor_BTCUSDT_lightgbm`, `monitor_BTCUSDT_tst`
- **Type:** BranchPythonOperator
- **Actions:**
  - Polls airflow_db every 10 seconds
  - Checks model status:
    - If 'PENDING' or 'RUNNING': Continue polling
    - If 'SUCCESS': Branch to `post_train_{model}`
    - If 'FAILED': Branch to `skip_model`
  - Timeout: 1.5 hours (5400 seconds)

#### Step 6: Post-Training Reconciliation
- **Tasks:** `post_train_BTCUSDT_lightgbm`, `post_train_BTCUSDT_tst`
- **Script:** `utils.utils.post_train_reconcile`
- **Parameters:** `--crypto BTCUSDT --model {lightgbm|tst}`

**Scenario A: First 3 Versions (versions <= 3)**
1. Download predictions from S3 (latest version)
2. Push predictions to PostgreSQL using `bulk_update_predictions`
3. Trigger FastAPI `/refresh` endpoint to load new models
4. Create consumer job file for the new version
5. Start consumer and wait for it to be "running"

**Scenario B: Version Rotation (versions > 3)**
1. Reassign S3 predictions:
   - Delete v2 from S3
   - Copy v3 → v2 in S3
   - Copy v4 → v3 in S3
   - Delete v4 from S3
2. Delete existing v2 and v3 consumers (set state to "delete")
3. Trigger FastAPI `/refresh` endpoint
4. Shift database columns:
   - Set `{model}_3` column to NULL
   - Copy `{model}_3` → `{model}_2` in PostgreSQL
5. Rename local CSV files: v3.csv → v2.csv
6. Create and start v2 consumer
7. Download new v3 predictions from S3
8. Push v3 predictions to PostgreSQL
9. Create and start v3 consumer

#### Step 7: Final Cleanup
- **Task:** `final_kill_kill_vast_ai_instances`
- **Trigger:** After all post-training tasks complete
- **Actions:**
  - Kills all VastAI cloud instances
  - Cleans up resources

---

## 2. TRL Model (Global)

### DAG: `training_pipeline`
**Schedule:** Every 5 days  
**Location:** `dags/DAG.py`

### Process Flow

```
┌─────────────────────────────────────────────────────────────────┐
│ STEP 1-3: Same as LightGBM/TST                                  │
│ (pre_train_dataset → flush_and_init → vast_ai_train)           │
└────────────────────┬────────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────────┐
│ STEP 4: monitor_trl                                             │
│ - Polls airflow_db for TRL model status                          │
│ - Checks: PENDING/RUNNING/SUCCESS/FAILED                         │
└────────────────────┬────────────────────────────────────────────┘
                     │
        ┌────────────┴────────────┐
        │                         │
        ▼                         ▼
┌──────────────────┐    ┌──────────────────┐
│ post_train_trl   │    │ skip_model       │
│                  │    │                  │
│ Runs:            │    │                  │
│ post_train_trl.py│    │                  │
└────────┬─────────┘    └──────────────────┘
         │
         ▼
┌───────────────────────────────────────────────┐
│ post_train_trl.py                              │
│                                                │
│ ├─ Get production TRL versions from MLflow    │
│ ├─ Reassign S3 predictions (if versions > 3) │
│ ├─ Shift DB columns (trl_3 → trl_2)            │
│ ├─ Download new v{N} predictions from S3      │
│ ├─ Push predictions to PostgreSQL (trl table)  │
│ └─ Reset TRL version in DB                     │
└───────────────────────────────────────────────┘
```

### Detailed Steps for TRL

#### Steps 1-3: Same as LightGBM/TST
- Pre-training dataset preparation
- Database initialization
- Model training (runs `trl_train.py`)

#### Step 4: TRL State Monitoring
- **Task:** `monitor_trl`
- **Type:** BranchPythonOperator
- **Actions:**
  - Polls airflow_db for TRL model status
  - Branches based on status (same logic as LightGBM/TST)

#### Step 5: Post-Training TRL Reconciliation
- **Task:** `post_train_trl`
- **Script:** `utils.utils.post_train_trl`
- **Actions:**
  1. Get production TRL versions from MLflow (latest 2)
  2. If versions > 3: Reassign S3 predictions (v3→v2, v4→v3)
  3. Shift database columns: `trl_3` → `trl_2` in PostgreSQL
  4. Rename local CSV: v3.csv → v2.csv
  5. Download new v{N} predictions from S3
  6. Push predictions to PostgreSQL `trl` table
  7. Reset TRL version in database

---

### DAG: `trl_inference_pipeline`
**Schedule:** Every 30 minutes  
**Location:** `dags/trl_infer_dag.py`

### Process Flow

```
┌─────────────────────────────────────────────────────────────────┐
│ STEP 1: past_news_scrape                                        │
│ - Scrapes past news articles                                    │
│ - Updates articles dataset                                      │
└────────────────────┬────────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────────┐
│ STEP 2: trl_onnx_maker                                          │
│ - Converts TRL model to ONNX format                             │
│ - Prepares ONNX model for inference                             │
└────────────────────┬────────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────────┐
│ STEP 3: trl_inference                                           │
│ - Runs inference on new articles                                │
│ - Generates TRL predictions                                    │
│ - Saves predictions to PostgreSQL (trl table)                  │
└─────────────────────────────────────────────────────────────────┘
```

### Detailed Steps for TRL Inference

#### Step 1: News Article Scraping
- **Task:** `past_news_scrape`
- **Script:** `utils.articles_runner.past_news_scrape`
- **Actions:**
  - Scrapes past news articles from sources
  - Updates articles dataset
  - Saves to CSV/database

#### Step 2: ONNX Model Preparation
- **Task:** `trl_onnx_maker`
- **Script:** `utils.serve.trl_onnx_maker`
- **Actions:**
  - Converts TRL model to ONNX format
  - Prepares ONNX model for fast inference
  - Saves ONNX model files

#### Step 3: TRL Inference
- **Task:** `trl_inference`
- **Script:** `utils.serve.trl_inference`
- **Actions:**
  - Loads ONNX model
  - Runs inference on new articles
  - Generates TRL predictions (3-class classification)
  - Saves predictions to PostgreSQL `trl` table

---

## 3. Consumer Start DAG (Schedule: @once - Runs Once)

### DAG: `consumer_start`
**Schedule:** @once (runs exactly once)  
**Location:** `dags/DAG.py`

### Process Flow

```
┌─────────────────────────────────────────────────────────────────┐
│ consumer_start DAG                                               │
│                                                                  │
│ Runs: consumer_start.py                                         │
└────────────────────┬────────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────────┐
│ STEP 1: Cleanup & Initialization                                │
│ ├─ Delete old state files                                        │
│ └─ Download initial datasets from S3                            │
└────────────────────┬────────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────────┐
│ STEP 2: Start Producer                                          │
│ ├─ Create producer job file                                     │
│ ├─ Wait for producer to be "running"                           │
│ └─ Producer publishes price data to Kafka                       │
└────────────────────┬────────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────────┐
│ STEP 3: For Each Crypto × Model Combination                     │
│ (BTCUSDT × lightgbm, BTCUSDT × tst)                            │
│                                                                  │
│ ├─ Download available predictions from S3                       │
│ │  (v1, v2, v3 if they exist)                                   │
│ │                                                                │
│ ├─ For each available version:                                  │
│ │  ├─ Create consumer job file                                 │
│ │  ├─ Wait for consumer state to be "wait"                     │
│ │  ├─ Set consumer state to "start"                            │
│ │  └─ Wait for consumer to be "running"                        │
│ │                                                                │
│ └─ Consumers now:                                               │
│    ├─ Listen to Kafka for new price data                        │
│    ├─ Generate predictions via FastAPI                          │
│    ├─ Write to local CSV                                        │
│    └─ Write to PostgreSQL                                       │
└─────────────────────────────────────────────────────────────────┘
```

### Detailed Steps for Consumer Start

#### Step 1: System Initialization
- **Script:** `utils.producer_consumer.consumer_start`
- **Actions:**
  - Deletes all old state files
  - Downloads initial datasets from S3:
    - Price data for BTCUSDT
    - Articles data for TRL

#### Step 2: Producer Startup
- **Actions:**
  - Creates producer job file at `/opt/airflow/custom_persistent_shared/jobs/`
  - Job handler process launches the producer
  - Producer starts publishing price data to Kafka topics
  - Waits until producer state is "running"

#### Step 3: Consumer Initialization
For each combination of:
- **Cryptos:** BTCUSDT
- **Models:** lightgbm, tst
- **Versions:** v1, v2, v3 (based on available S3 versions)

**Actions:**
1. Download available predictions from S3 for each model
2. For each version that exists:
   - Create consumer job file
   - Wait for consumer state to be "wait"
   - Set consumer state to "start"
   - Wait for consumer to be "running"

#### Step 4: Consumer Operations (Continuous)
Once consumers are running, they:
1. **Listen to Kafka:** Receive new price data from producer
2. **Check for Missing Predictions:**
   - Compare Kafka data with local CSV
   - Compare with PostgreSQL database
   - Identify missing prediction timestamps
3. **Generate Predictions:**
   - Preprocess data for model input
   - Call FastAPI `/predict` endpoint
   - Receive predictions from ONNX models
4. **Write Predictions:**
   - Append to local CSV file
   - Upsert to PostgreSQL database
   - Maintain version-specific CSV files

---

## Summary of DAGs and Models

| DAG Name | Schedule | Models | Purpose |
|----------|----------|--------|---------|
| **training_pipeline** | Every 5 days | LightGBM, TST, TRL | Train models, generate predictions, reconcile versions |
| **trl_inference_pipeline** | Every 30 mins | TRL only | Run inference on new articles |
| **consumer_start** | @once | LightGBM, TST | Initialize real-time prediction consumers |

---

## Key Processes Explained

### 1. Training Pipeline
- **Orchestrates** training for all models in parallel
- **Monitors** each model's training status independently
- **Reconciles** versions after each model completes training
- **Manages** version rotation (v3→v2, new→v3) when needed
- **Cleans up** VastAI instances after all training completes

### 2. Post-Training Reconciliation
- **Manages version rotation** when new models are trained
- **Updates database** with new predictions
- **Refreshes FastAPI** to load new ONNX models
- **Restarts consumers** for updated versions
- **Maintains** up to 3 versions (v1, v2, v3) per model

### 3. Consumer System
- **Runs continuously** after initialization
- **Handles real-time predictions** for incoming data streams
- **Fills gaps** in historical predictions
- **Maintains synchronization** between S3, local CSV, and PostgreSQL
- **Supports multiple versions** running concurrently

### 4. TRL Inference Pipeline
- **Runs more frequently** (every 30 minutes) than training
- **Processes new articles** as they become available
- **Generates predictions** for news sentiment analysis
- **Updates database** with latest TRL predictions

---

## File Locations

### DAG Files
- **Main Training DAG:** `dags/DAG.py`
- **TRL Inference DAG:** `dags/trl_infer_dag.py`

### Training Scripts
- **LightGBM:** `utils/trainer/lgb_train.py`
- **TST:** `utils/trainer/tst_train.py`
- **TRL:** `utils/trainer/trl_train.py`

### Post-Training Scripts
- **LightGBM/TST:** `utils/utils/post_train_reconcile.py`
- **TRL:** `utils/utils/post_train_trl.py`

### Consumer Scripts
- **Consumer Start:** `utils/producer_consumer/consumer_start.py`
- **Consumer:** `utils/producer_consumer/consumer.py`
- **Producer:** `utils/producer_consumer/producer.py`

### Inference Scripts
- **FastAPI:** `utils/serve/fastapi_app.py`
- **TRL Inference:** `utils/serve/trl_inference.py`
- **TRL ONNX Maker:** `utils/serve/trl_onnx_maker.py`

---

## Database Schema

### Crypto Tables (e.g., `btcusdt`)
```sql
CREATE TABLE "btcusdt" (
    open_time TIMESTAMP NOT NULL PRIMARY KEY,
    open FLOAT,
    high FLOAT,
    low FLOAT,
    close FLOAT,
    volume FLOAT,
    tst_1 FLOAT[] DEFAULT NULL,
    tst_2 FLOAT[] DEFAULT NULL,
    tst_3 FLOAT[] DEFAULT NULL,
    lightgbm_1 FLOAT[] DEFAULT NULL,
    lightgbm_2 FLOAT[] DEFAULT NULL,
    lightgbm_3 FLOAT[] DEFAULT NULL
);
```

### TRL Table
```sql
CREATE TABLE "trl" (
    title TEXT,
    link TEXT NOT NULL PRIMARY KEY,
    date TIMESTAMP NOT NULL,
    "trl_1" FLOAT[] DEFAULT NULL,
    "trl_2" FLOAT[] DEFAULT NULL,
    "trl_3" FLOAT[] DEFAULT NULL,
    price_change FLOAT DEFAULT NULL,
    label INT DEFAULT NULL
);
```

---

## S3 Storage Structure

```
s3://mlops/
├── prices/
│   ├── BTCUSDT.parquet
│   └── BTCUSDT_test.parquet
├── predictions/
│   ├── BTCUSDT/
│   │   ├── lightgbm/
│   │   │   ├── v1.parquet
│   │   │   ├── v2.parquet
│   │   │   └── v3.parquet
│   │   └── tst/
│   │       ├── v1.parquet
│   │       ├── v2.parquet
│   │       └── v3.parquet
│   └── preds/
│       └── trl/
│           ├── v1.parquet
│           ├── v2.parquet
│           └── v3.parquet
└── articles/
    └── articles.parquet
```

---

## Version Management

### Model Versions
- **MLflow:** Maintains up to 5 versions, keeps 2 in production
- **S3 Predictions:** Maintains up to 3 versions (v1, v2, v3)
- **Database:** Stores 3 versions per model (`{model}_1`, `{model}_2`, `{model}_3`)

### Version Rotation
When a new model is trained:
1. Old v3 → becomes v2
2. Old v2 → becomes v1 (or deleted)
3. New model → becomes v3

This ensures:
- **v1:** Most stable, production-ready
- **v2:** Previous version, for comparison
- **v3:** Latest version, being validated

---

## Error Handling

### Training Failures
- If training fails, status is set to 'FAILED' in airflow_db
- Post-training reconciliation is skipped (`skip_model` task)
- VastAI instances are still cleaned up
- Failed models can be retrained in next DAG run

### Consumer Failures
- Consumers monitor their state files
- If state is set to "delete", consumer gracefully shuts down
- State files track consumer status: `unknown`, `wait`, `start`, `running`, `pause`, `deleted`
- Consumers can be restarted via post-training reconciliation

### Timeout Handling
- Model monitoring timeout: 1.5 hours
- All models monitoring timeout: 2 hours
- On timeout, models are marked as 'FAILED'
- VastAI instances are killed on timeout or completion

---

## Monitoring and Logging

### Status Tracking
- **airflow_db:** Tracks training status (PENDING, RUNNING, SUCCESS, FAILED)
- **State files:** Track consumer status (JSON files in STATE_DIR)
- **Status DB:** Logs all DAG task events (START, COMPLETE, FAILED)

### Logging
- Each consumer has its own logger
- Training scripts log to stdout/stderr
- FastAPI logs prediction requests
- All logs are captured by Airflow

---

## Dependencies

### External Services
- **VastAI:** Cloud GPU instances for training
- **Kubernetes:** Container orchestration for training jobs
- **Kafka:** Message queue for real-time data streaming
- **PostgreSQL:** Database for storing predictions and raw data
- **S3:** Object storage for datasets and predictions
- **MLflow:** Model registry and experiment tracking
- **FastAPI:** Inference service for ONNX models

### Internal Components
- **Producer:** Publishes price data to Kafka
- **Consumers:** Subscribe to Kafka, generate predictions
- **Job Handler:** Launches producer/consumer processes
- **Model Manager:** Manages MLflow model versions
- **S3 Manager:** Handles S3 uploads/downloads
- **Database Manager:** Handles PostgreSQL operations

---

## Notes

1. **Parallel Execution:** All models train in parallel, but post-training reconciliation happens independently as each completes.

2. **Version Management:** The system maintains 3 versions to allow for A/B testing and gradual rollouts.

3. **Real-Time Processing:** Consumers run continuously and handle new data as it arrives via Kafka.

4. **Fault Tolerance:** The system handles failures gracefully, with proper cleanup and state management.

5. **Scalability:** The architecture supports multiple cryptos and models, with each running independently.

---

**Document Version:** 1.0  
**Last Updated:** 2025  
**Author:** Crypto-MLOps Pipeline Documentation

