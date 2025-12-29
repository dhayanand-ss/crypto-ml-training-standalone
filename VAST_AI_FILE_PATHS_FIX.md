# Vast AI File Paths Fix

## Problem Summary

The Vast AI startup script was failing with:
- `ssh: command not found` errors
- `WARNING: btcusdt.csv missing`
- `WARNING: BTCUSDT.csv missing`

## Root Causes

1. **SSH Command Not Found**: Vast AI's internal `.launch` script requires `openssh-client` which wasn't installed
2. **File Path Issues**: Relative paths were used without ensuring the correct working directory
3. **Data Download Timing**: File copy operations might run before downloads complete

## File Paths Used in the System

### Expected File Locations

#### On Vast AI Instance (after setup):
```
/workspace/{repo_name}/
├── data/
│   ├── btcusdt.csv              # Required for training (lowercase)
│   ├── articles.csv              # For TRL training
│   ├── prices/
│   │   ├── BTCUSDT.csv          # Downloaded from GCS (uppercase)
│   │   └── BTCUSDT_test.csv     # Test data
│   └── articles/
│       └── articles.csv         # Alternative location for articles
```

#### Local Development:
```
crypto-ml-training-standalone/
├── data/
│   ├── btcusdt.csv              # Price data (lowercase)
│   ├── articles.csv             # News articles
│   ├── prices/
│   │   └── BTCUSDT.csv          # Price data (uppercase)
│   └── articles/
│       └── articles.csv         # Alternative articles location
```

### File Path Resolution

1. **Download Location** (from GCS):
   - `data/prices/BTCUSDT.csv` - Main price data
   - `data/prices/BTCUSDT_test.csv` - Test price data
   - `data/articles/articles.csv` - News articles (if trl_model=True)

2. **Training Script Expectations**:
   - `trainer/lightgbm_trainer.py`: Expects `data/btcusdt.csv`
   - `trainer/time_series_transformer.py`: Expects `data/btcusdt.csv`
   - `utils/trainer/trl_train.py`: Expects `data/{coin}.csv` (defaults to `data/btcusdt.csv`)

3. **Copy Operations** (in startup script):
   - Copy from `data/prices/BTCUSDT.csv` → `data/btcusdt.csv`
   - Copy from `data/prices/btcusdt.csv` → `data/btcusdt.csv` (if lowercase exists)
   - Copy from `data/BTCUSDT.csv` → `data/btcusdt.csv` (if in root)

## Fixes Applied

### 1. SSH Command Fix
- Added `openssh-client` installation to all startup commands
- Fixes: `utils/utils/vast_ai_train.py`, `utils/trainer/vast_ai_trl_train.py`, `utils/trainer/vast_ai_api.py`

### 2. File Path Fixes
- **Absolute Paths**: Now using `/workspace/{repo_name}/data/...` instead of relative `data/...`
- **Working Directory**: Explicitly `cd` to project root before all file operations
- **Path Verification**: Added `pwd` and file listing commands to verify paths

### 3. Enhanced Data Download
- Better error handling with detailed logging
- File existence checks after download
- Multiple fallback paths for file copying

### 4. Improved Debugging
- Added `pwd` to show current directory
- Added `find data -name '*.csv'` to list all CSV files
- Better error messages with file paths

## Startup Command Flow

1. **Setup**:
   ```bash
   mkdir -p /workspace
   cd /workspace
   git clone <repo>  # or use custom image
   cd {repo_name}
   ```

2. **Install Dependencies**:
   ```bash
   apt-get update && apt-get install -y libgomp1 curl openssh-client
   pip install wandb
   ```

3. **Download Data**:
   ```bash
   cd /workspace/{repo_name}
   python -c "from trainer.train_utils import download_s3_dataset; download_s3_dataset('BTCUSDT')"
   ```
   Downloads to: `data/prices/BTCUSDT.csv`

4. **Copy Files**:
   ```bash
   cd /workspace/{repo_name}
   cp data/prices/BTCUSDT.csv data/btcusdt.csv  # If needed
   ```

5. **Verify Files**:
   ```bash
   cd /workspace/{repo_name}
   ls -la data/btcusdt.csv
   ls -la data/prices/BTCUSDT.csv
   ```

6. **Start Training**:
   ```bash
   cd /workspace/{repo_name}
   python -m utils.trainer.train_paralelly
   ```

## Key Changes in Code

### Before:
```bash
"mkdir -p data/prices",
"[ -f data/prices/BTCUSDT.csv ] && cp data/prices/BTCUSDT.csv data/btcusdt.csv"
```

### After:
```bash
"cd /workspace/{repo_name} && mkdir -p data/prices data/articles",
"cd /workspace/{repo_name} && [ -f data/prices/BTCUSDT.csv ] && cp data/prices/BTCUSDT.csv data/btcusdt.csv"
```

## Testing

To verify the fix works:

1. Check SSH error is gone (should see no `ssh: command not found` messages)
2. Check data files are found:
   ```
   ✓ btcusdt.csv found
   ✓ BTCUSDT.csv found
   ```
3. Check working directory is correct:
   ```
   Working directory: /workspace/crypto-ml-training-standalone
   ```

## Environment Variables

- `VASTAI_GITHUB_REPO`: GitHub repository URL (determines repo_name)
- `VASTAI_DOCKER_IMAGE`: Custom Docker image (if using, repo_name = "crypto-ml-training")
- `GOOGLE_APPLICATION_CREDENTIALS`: Path to GCP credentials file
- `GCP_CREDENTIALS_PATH`: Alternative GCP credentials path
- `DATA_PATH`: Override for data directory (defaults to "data")

## Status

✅ **Fixed**: SSH command not found error
✅ **Fixed**: File path resolution issues
✅ **Fixed**: Working directory consistency
✅ **Enhanced**: Better error messages and debugging

The startup script now ensures:
- All file operations use absolute paths or explicit `cd` commands
- Working directory is always the project root
- Files are verified after download and copy operations
- Better error messages show actual file paths

