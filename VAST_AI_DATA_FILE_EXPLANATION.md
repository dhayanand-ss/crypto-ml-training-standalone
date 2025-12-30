# Vast AI Data File Path Issue - Explanation

## The Problem

You're seeing this sequence:
1. ✅ `pre_train_dataset` task completes successfully in Airflow
2. ✅ Files are validated and exist in Airflow environment (`/opt/airflow/...`)
3. ❌ Vast AI training fails with "Prices file not found: data/btcusdt.csv"

## Why This Happens

### Two Separate Environments

1. **Airflow Environment** (`/opt/airflow/...`)
   - Runs `pre_train_dataset` task
   - Prepares and validates datasets locally
   - Files exist here: `/opt/airflow/data/btcusdt.csv`

2. **Vast AI Instance** (Remote machine at `/workspace/crypto-ml-training-standalone/`)
   - Completely separate remote machine
   - Clones repo from GitHub
   - **Does NOT have access to Airflow's files**
   - Must download/copy data files itself

### The Flow

```
Airflow DAG:
├── pre_train_dataset (runs in Airflow)
│   └── Prepares files in /opt/airflow/data/
│
└── vast_ai_train (creates remote instance)
    └── Vast AI Instance (separate machine)
        ├── Clones repo from GitHub
        ├── Needs to download data from GCS/S3
        └── Needs to copy data/prices/BTCUSDT.csv → data/btcusdt.csv
```

## The Solution

The Vast AI startup script must:
1. **Download** data files from cloud storage (GCS/S3)
2. **Copy** files to expected locations
3. **Then** start training

### What Was Fixed

**Before:**
- TRL startup script didn't download or copy data files
- Training started immediately, expecting files to exist
- ❌ Files not found error

**After:**
- TRL startup script now:
  1. Downloads `data/prices/BTCUSDT.csv` from GCS/S3
  2. Copies to `data/btcusdt.csv` (with fallbacks)
  3. Then starts training
- ✅ Files available when training starts

## Files Updated

1. `utils/trainer/vast_ai_trl_train.py`
   - Added data download step
   - Added file copy steps with fallbacks

2. `utils/trainer/vast_ai_api.py`
   - Same fixes for API-based instance creation

## Verification

The startup script now includes:
```bash
# Download data files
python -c "from trainer.train_utils import download_s3_dataset; download_s3_dataset('BTCUSDT', trl_model=True)"

# Copy/create btcusdt.csv from various locations
[ -f data/prices/BTCUSDT.csv ] && cp data/prices/BTCUSDT.csv data/btcusdt.csv
[ -f data/prices/btcusdt.csv ] && cp data/prices/btcusdt.csv data/btcusdt.csv
[ -f data/BTCUSDT.csv ] && cp data/BTCUSDT.csv data/btcusdt.csv
```

## Key Takeaway

**`pre_train_dataset` in Airflow is for validation/preparation in the Airflow environment.**

**Vast AI instances are separate and must download/copy data themselves via the startup script.**

The fix ensures Vast AI instances have the required data files before training starts.


