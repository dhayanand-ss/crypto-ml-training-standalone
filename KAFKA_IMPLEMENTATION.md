# Kafka Implementation Documentation

## Table of Contents
1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Infrastructure Setup](#infrastructure-setup)
4. [Producer Implementation](#producer-implementation)
5. [Consumer Implementation](#consumer-implementation)
6. [State Management](#state-management)
7. [Job Handler](#job-handler)
8. [Integration with Airflow](#integration-with-airflow)
9. [Data Flow](#data-flow)
10. [Configuration](#configuration)
11. [Troubleshooting](#troubleshooting)

---

## Overview

This project implements a Kafka-based real-time data streaming pipeline for cryptocurrency price data processing and ML model inference. The system uses **QuixStreams** (a Python library built on top of Kafka) to handle data ingestion, processing, and prediction generation.

### Key Components
- **Producer**: Fetches cryptocurrency price data from Binance API and publishes to Kafka topics
- **Consumers**: Subscribe to Kafka topics, process data, generate predictions using ML models, and persist results
- **State Management**: File-based state tracking for producer/consumer lifecycle control
- **Job Handler**: Watches for job files and launches producer/consumer processes

---

## Architecture

```
┌─────────────────┐
│  Binance API    │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│    Producer     │───┐
│  (producer.py)  │   │
└─────────────────┘   │
                      │
                      ▼
              ┌───────────────┐
              │  Kafka Broker │
              │   (Topics)    │
              └───────┬───────┘
                      │
         ┌────────────┼────────────┐
         │            │            │
         ▼            ▼            ▼
  ┌──────────┐ ┌──────────┐ ┌──────────┐
  │Consumer 1│ │Consumer 2│ │Consumer N│
  │(Model v1)│ │(Model v2)│ │(Model v3)│
  └────┬─────┘ └────┬─────┘ └────┬─────┘
       │            │            │
       └────────────┼────────────┘
                    ▼
         ┌──────────────────┐
         │  FastAPI Service  │
         │  (ML Inference)   │
         └──────────┬────────┘
                    │
         ┌──────────┴──────────┐
         │                     │
         ▼                     ▼
  ┌─────────────┐      ┌─────────────┐
  │ PostgreSQL   │      │  CSV Files  │
  │   Database   │      │  (Local)    │
  └─────────────┘      └─────────────┘
```

### Topics Structure
- **Topic Naming**: One topic per cryptocurrency symbol (e.g., `BTCUSDT`)
- **Message Format**: JSON-serialized arrays of OHLCV (Open, High, Low, Close, Volume) data
- **Consumer Groups**: Each consumer uses a unique group ID: `{model}-{version}-consumer`

---

## Infrastructure Setup

### Kubernetes Deployment

#### Kafka Service
The Kafka broker is exposed via a NodePort service:

**File**: `k8-setup/kafka-service.yaml`
```yaml
apiVersion: v1
kind: Service
metadata:
  name: kafka
spec:
  type: NodePort
  selector:
    app: kafka
  ports:
    - port: 9092
      nodePort: 30092
```

#### Producer-Consumer Deployment
**File**: `k8-setup/producer-consumer.yaml`

The producer-consumer deployment runs a job handler that watches for job files and launches processes accordingly.

**Key Configuration**:
- **Image**: `frozenwolf2003/producer_consumer:latest`
- **Environment Variables**:
  - `KAFKA_HOST`: Set from `status.hostIP` (Kubernetes node IP)
  - MLflow tracking credentials from secrets
- **Volume Mounts**: Shared PVC for state files, job files, and data persistence

### Docker Compose (Local Development)

**File**: `k8-setup/kafka.yml`

For local development, a Docker Compose setup includes:
- **Kafka Broker**: Confluent Kafka 7.5.0
- **Schema Registry**: For schema management
- **Control Center**: Kafka management UI (port 9021)
- **REST Proxy**: HTTP interface to Kafka (port 8082)

**Key Ports**:
- `9092`: Kafka broker
- `8081`: Schema Registry
- `8082`: REST Proxy
- `9021`: Control Center

---

## Producer Implementation

### Location
`utils/producer_consumer/producer.py`

### Responsibilities
1. **Data Fetching**: Retrieves OHLCV data from Binance API
2. **Data Persistence**: Writes to PostgreSQL and CSV files
3. **Kafka Publishing**: Sends data batches to Kafka topics
4. **State Management**: Responds to pause/resume/delete commands

### Key Functions

#### `main()`
Main producer loop that:
- Checks state file for control commands (pause/resume/delete)
- Fetches new data from Binance API
- Inserts new records into PostgreSQL
- Publishes data to Kafka topics
- Updates CSV files with new data
- Aligns to 1-minute intervals

#### `download_full_history()`
Downloads historical OHLCV data with resume support:
- Handles rate limiting (0.25s delay between requests)
- Supports incremental fetching from a start timestamp
- Returns pandas DataFrame with standardized columns

#### `send_df_to_quix()`
Publishes DataFrame data to Kafka:
- Batches data (default: 10,000 records per batch)
- Serializes to JSON format (handled automatically by QuixStreams)
- Uses topic-specific keys: `{symbol}_batch_{timestamp}`
- Uses QuixStreams `topic.producer()` API for publishing
- Includes fallback error handling for different QuixStreams versions

### Configuration
```python
KAFKA_BROKER = f"{os.environ['KAFKA_HOST']}:9092"
SYMBOLS = ["BTCUSDT"]  # Supported cryptocurrencies
INTERVAL = "1m"        # Data interval
```

### Producer Configuration
- **Message Max Bytes**: 20 MB per message
- **Serializer**: JSON
- **Topics**: One topic per symbol

### State Management
The producer checks state file at `/opt/airflow/custom_persistent_shared/consumer_states/ALL_producer_main.json`:
- `running`: Normal operation
- `pause`: Pause processing
- `delete`: Shutdown gracefully
- `start`: Resume from paused state

---

## Consumer Implementation

### Location
`utils/producer_consumer/consumer.py`

### Responsibilities
1. **Kafka Consumption**: Subscribes to cryptocurrency topics
2. **Data Processing**: Preprocesses data for ML models
3. **Model Inference**: Calls FastAPI service for predictions
4. **Result Persistence**: Writes predictions to PostgreSQL and CSV
5. **Historical Reconciliation**: Handles missing predictions on startup

### Key Functions

#### `build_pipeline()`
Sets up the QuixStreams processing pipeline:
- Creates topic subscription
- Handles historical inference for missing predictions
- Sets up message processing callback
- Manages state transitions

#### `maybe_process()`
Main message processing function:
- Checks consumer state (wait/pause/start/delete)
- Maintains rolling window of sequence length (30 rows)
- Filters duplicate data based on last processed time
- Calls ML model for predictions
- Persists predictions to database and CSV

#### `get_predictions()`
Calls FastAPI service for batch predictions:
- Batches requests (max 5000 per request)
- Handles retries on failure
- Checks model availability before inference

### Historical Reconciliation
On startup, the consumer:
1. Loads existing predictions from CSV
2. Identifies missing predictions in database
3. Fetches price data for missing time periods
4. Generates predictions for missing dates
5. Upserts predictions into database and CSV

### Configuration
```python
KAFKA_BROKER = f"{os.environ['KAFKA_HOST']}:9092"
seq_len = 30  # Sequence length for time series models
url = "http://fastapi-ml:8000/predict"  # FastAPI endpoint
```

### Consumer Configuration
- **Consumer Group**: `{model}-{version}-consumer`
- **Auto Offset Reset**: `earliest` (processes all messages from start)
- **State Directory**: `/opt/airflow/custom_persistent_shared/quix_state`
- **Max Poll Interval**: 6000 seconds (100 minutes)

### State Management
Each consumer maintains a state file: `{crypto}_{model}_{version}.json`

**States**:
- `wait`: Initial state, waiting to start
- `start`: Command to start processing
- `running`: Actively processing messages
- `pause`: Paused, not processing
- `paused`: Currently in paused state
- `delete`: Command to shutdown
- `deleted`: Successfully shut down

### State Monitor Thread
A background thread (`state_monitor`) continuously checks the state file and gracefully shuts down the consumer if deletion is requested.

---

## State Management

### Location
`utils/producer_consumer/consumer_utils.py`

### State File Structure
State files are stored in `/opt/airflow/custom_persistent_shared/consumer_states/`

**Format**: `{crypto}_{model}_{version}.json`
```json
{
  "crypto": "BTCUSDT",
  "model": "lightgbm",
  "version": "v1",
  "state": "running",
  "error_msg": ""
}
```

### Key Functions

#### `state_write(crypto, model, version, state, error_msg="")`
Writes state to JSON file with proper file permissions (777).

#### `state_checker(crypto, model, version, timeout=120)`
Reads state from file with retry logic:
- Waits up to 120 seconds for file to appear
- Returns "unknown" if file doesn't exist after timeout
- Handles JSON parsing errors gracefully

#### `delete_state(crypto, model, version)`
Removes state file for a specific consumer.

#### `delete_all_states()`
Removes all state files (used for cleanup).

---

## Job Handler

### Location
`utils/producer_consumer/job_handler.py`

### Purpose
Watches a job directory and launches producer/consumer processes based on job files.

### Job File Format
Job files are shell scripts placed in `/opt/airflow/custom_persistent_shared/jobs/`

**Naming**: `{crypto}_{model}_{version}.sh`

**Example**:
```bash
#!/bin/bash
export PYTHONPATH=..:$PYTHONPATH
python -m utils.producer_consumer.consumer --crypto BTCUSDT --model lightgbm --version v1
```

### Operation
1. Continuously watches job directory
2. Detects new `.sh` files
3. Parses filename to extract crypto, model, version
4. Launches appropriate process (producer or consumer)
5. Removes job file after launching

### Process Launching
- Uses `subprocess.Popen` with detached session
- Redirects stdout/stderr to `/dev/null`
- Removes existing state file before launching

---

## Integration with Airflow

### DAG Integration
**File**: `dags/DAG.py`

The Kafka producer/consumer system is integrated into the Airflow DAG through:

#### `consumer_start` Task
```python
BashOperator(
    task_id='consumer_start',
    bash_command='PYTHONPATH=..:$PYTHONPATH python -m utils.producer_consumer.consumer_start',
)
```

This task:
1. Cleans up old state files
2. Downloads initial datasets from S3
3. Creates producer job file
4. Waits for producer to start
5. Creates consumer job files for all available model versions
6. Waits for all consumers to be running

#### `consumer_delete` Task
```python
BashOperator(
    task_id='consumer_delete',
    bash_command='PYTHONPATH=..:$PYTHONPATH python -m utils.producer_consumer.kill_all',
)
```

This task gracefully shuts down all consumers and the producer.

### Consumer Start Script
**File**: `utils/producer_consumer/consumer_start.py`

**Process**:
1. Downloads datasets and predictions from S3
2. Creates producer job file
3. Waits for producer to be running
4. For each crypto/model/version combination:
   - Downloads available predictions from S3
   - Creates consumer job file
   - Sets state to "start" to begin processing

### Kill All Script
**File**: `utils/producer_consumer/kill_all.py`

**Process**:
1. Sets all consumer states to "delete"
2. Sets producer state to "delete"
3. Waits for all processes to shut down
4. Cleans up all state files

---

## Data Flow

### Producer Data Flow
```
Binance API
    │
    ▼
Fetch OHLCV Data
    │
    ▼
Insert into PostgreSQL
    │
    ▼
Append to CSV File
    │
    ▼
Batch Data (10,000 records)
    │
    ▼
Serialize to JSON
    │
    ▼
Publish to Kafka Topic (BTCUSDT)
```

### Consumer Data Flow
```
Kafka Topic (BTCUSDT)
    │
    ▼
Receive Message Batch
    │
    ▼
Filter Duplicates
    │
    ▼
Maintain Rolling Window (30 rows)
    │
    ▼
Preprocess Data
    │
    ▼
Call FastAPI for Predictions
    │
    ▼
Upsert to PostgreSQL
    │
    ▼
Append to CSV File
```

### Historical Reconciliation Flow
```
Consumer Startup
    │
    ▼
Load Existing Predictions (CSV)
    │
    ▼
Query Missing Predictions (Database)
    │
    ▼
Load Price Data (CSV)
    │
    ▼
Filter Missing Time Periods
    │
    ▼
Generate Predictions (FastAPI)
    │
    ▼
Upsert to Database & CSV
    │
    ▼
Start Real-time Processing
```

---

## Configuration

### Environment Variables

#### Required
- `KAFKA_HOST`: Kafka broker hostname/IP (set from Kubernetes `status.hostIP`)

#### Optional (for MLflow)
- `MLFLOW_TRACKING_URI`: MLflow tracking server URL
- `MLFLOW_TRACKING_USERNAME`: MLflow username
- `MLFLOW_TRACKING_PASSWORD`: MLflow password

### Kafka Configuration

#### Producer Settings
- **Broker Address**: `{KAFKA_HOST}:9092`
- **Message Max Bytes**: 20 MB
- **Serializer**: JSON
- **Topics**: One per cryptocurrency symbol

#### Consumer Settings
- **Broker Address**: `{KAFKA_HOST}:9092`
- **Consumer Group**: `{model}-{version}-consumer`
- **Auto Offset Reset**: `earliest`
- **State Directory**: `/opt/airflow/custom_persistent_shared/quix_state`
- **Max Poll Interval**: 6000 seconds

### File Paths

#### State Files
- **Directory**: `/opt/airflow/custom_persistent_shared/consumer_states/`
- **Format**: `{crypto}_{model}_{version}.json`

#### Job Files
- **Directory**: `/opt/airflow/custom_persistent_shared/jobs/`
- **Format**: `{crypto}_{model}_{version}.sh`

#### Data Files
- **Price Data**: `/opt/airflow/custom_persistent_shared/data/prices/{crypto}.csv`
- **Predictions**: `/opt/airflow/custom_persistent_shared/data/predictions/{crypto}/{model}/{version}.csv`

#### Logs
- **Consumer Logs**: `/opt/airflow/custom_persistent_shared/logs/consumer.log`

### Model Configuration
- **Supported Cryptocurrencies**: `["BTCUSDT"]`
- **Supported Models**: `["lightgbm", "tst"]`
- **Supported Versions**: `["v1", "v2", "v3"]`
- **Sequence Length**: 30 (for time series models)
- **Data Interval**: 1 minute

---

## Troubleshooting

### Common Issues

#### Producer Not Starting
1. **Check State File**: Verify `ALL_producer_main.json` exists and state is not "delete"
2. **Check Kafka Connection**: Verify `KAFKA_HOST` environment variable is set correctly
3. **Check Job File**: Ensure job file exists in jobs directory
4. **Check Logs**: Review producer logs for connection errors

#### Consumer Not Processing
1. **Check State**: Verify consumer state is "running" (not "wait" or "pause")
2. **Check Model Availability**: Verify FastAPI service has the model loaded
3. **Check Kafka Connection**: Verify consumer can connect to Kafka broker
4. **Check Historical Data**: Ensure price data CSV exists and has data

#### Missing Predictions
1. **Check Historical Reconciliation**: Consumer should automatically backfill missing predictions on startup
2. **Check Database**: Verify predictions are being written to PostgreSQL
3. **Check CSV Files**: Verify predictions CSV is being updated
4. **Check Model Version**: Ensure correct model version is loaded in FastAPI

#### State File Issues
1. **File Permissions**: Ensure state directory has write permissions (777)
2. **File Locking**: Check for file locking issues if multiple processes access same state file
3. **JSON Format**: Verify state file is valid JSON

#### Kafka Connection Issues
1. **Network**: Verify Kafka broker is accessible from producer/consumer pods
2. **Port**: Ensure port 9092 (or configured port) is open
3. **DNS**: Verify Kafka hostname resolves correctly
4. **Firewall**: Check Kubernetes network policies

### Debugging Commands

#### Check Producer State
```bash
cat /opt/airflow/custom_persistent_shared/consumer_states/ALL_producer_main.json
```

#### Check Consumer State
```bash
cat /opt/airflow/custom_persistent_shared/consumer_states/BTCUSDT_lightgbm_v1.json
```

#### List All States
```bash
ls -la /opt/airflow/custom_persistent_shared/consumer_states/
```

#### Check Job Files
```bash
ls -la /opt/airflow/custom_persistent_shared/jobs/
```

#### View Consumer Logs
```bash
tail -f /opt/airflow/custom_persistent_shared/logs/consumer.log
```

#### Test Kafka Connection
```python
from quixstreams import Application
app = Application(broker_address="<KAFKA_HOST>:9092")
# Try to create a topic or producer
```

### Manual State Control

#### Pause Producer
```python
from utils.producer_consumer.consumer_utils import state_write
state_write("ALL", "producer", "main", "pause")
```

#### Resume Producer
```python
state_write("ALL", "producer", "main", "start")
```

#### Delete Consumer
```python
state_write("BTCUSDT", "lightgbm", "v1", "delete")
```

#### Start Consumer
```python
state_write("BTCUSDT", "lightgbm", "v1", "start")
```

---

## Best Practices

1. **State Management**: Always use state files for process control, never kill processes directly
2. **Error Handling**: Producers and consumers log errors and update state files on failure
3. **Data Consistency**: Both PostgreSQL and CSV files are updated to ensure redundancy
4. **Historical Reconciliation**: Consumers automatically handle missing predictions on startup
5. **Graceful Shutdown**: Always use state files to request shutdown, allowing processes to clean up
6. **Monitoring**: Monitor state files and logs regularly to detect issues early
7. **Resource Management**: Be aware of memory usage when processing large batches
8. **Rate Limiting**: Producer respects Binance API rate limits (0.25s delay)

---

## Related Files

- **Producer**: `utils/producer_consumer/producer.py`
- **Consumer**: `utils/producer_consumer/consumer.py`
- **State Utils**: `utils/producer_consumer/consumer_utils.py`
- **Job Handler**: `utils/producer_consumer/job_handler.py`
- **Consumer Start**: `utils/producer_consumer/consumer_start.py`
- **Kill All**: `utils/producer_consumer/kill_all.py`
- **Logger**: `utils/producer_consumer/logger.py`
- **Kafka Config**: `k8-setup/kafka.yml`
- **Kafka Service**: `k8-setup/kafka-service.yaml`
- **Producer-Consumer Deployment**: `k8-setup/producer-consumer.yaml`
- **Airflow DAG**: `dags/DAG.py`

---

## Additional Resources

- [QuixStreams Documentation](https://quix.io/docs/)
- [Apache Kafka Documentation](https://kafka.apache.org/documentation/)
- [Confluent Kafka Documentation](https://docs.confluent.io/)

