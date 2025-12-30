# PENDING Status Issue - Analysis

## Problem Summary

The monitoring task shows all models stuck in **PENDING** state and never transitioning to **RUNNING** or **SUCCESS/FAILED**.

## Root Cause

**Training scripts running on Vast AI instances do NOT update the status in Firestore.**

### Current Flow:

1. ✅ `flush_and_init` task → Sets all statuses to **PENDING** in Firestore
2. ✅ `vast_ai_train` task → Creates Vast AI instances and starts training scripts
3. ❌ **Training scripts run but never call `db.set_state()` to update status**
4. ❌ Monitor task keeps checking → Always sees **PENDING** → Never progresses

### Missing Code in Training Scripts:

The training scripts (`utils/trainer/trl_train.py`, `trainer/lightgbm_trainer.py`, `trainer/time_series_transformer.py`) need to:

1. **At start of training:**
   ```python
   from utils.database.airflow_db import db
   
   # Set status to RUNNING when training starts
   db.set_state(model="trl", coin="ALL", state="RUNNING")
   # or for other models:
   db.set_state(model="lightgbm", coin="BTCUSDT", state="RUNNING")
   ```

2. **On successful completion:**
   ```python
   db.set_state(model="trl", coin="ALL", state="SUCCESS")
   ```

3. **On failure:**
   ```python
   db.set_state(model="trl", coin="ALL", state="FAILED", error_message=str(e))
   ```

## Evidence

### What's Working:
- ✅ Status entries are created (PENDING state)
- ✅ Monitor task can read status from Firestore
- ✅ Vast AI instances are being created (we verified instance 29307606 is running)

### What's NOT Working:
- ❌ Training scripts don't import `airflow_db`
- ❌ Training scripts don't call `set_state()` anywhere
- ❌ Status never changes from PENDING

## Solution

Add status updates to all training scripts:

1. **`utils/trainer/trl_train.py`** - Add status updates for TRL model
2. **`trainer/lightgbm_trainer.py`** - Add status updates for lightgbm model  
3. **`trainer/time_series_transformer.py`** - Add status updates for tst model

### Implementation Pattern:

```python
# At the start of main() function:
from utils.database.airflow_db import db

def main():
    parser = argparse.ArgumentParser(...)
    args = parser.parse_args()
    
    # Determine model and coin from arguments
    model = "trl"  # or "lightgbm" or "tst"
    coin = args.coin if hasattr(args, 'coin') else "ALL"
    
    try:
        # Set status to RUNNING
        db.set_state(model=model, coin=coin, state="RUNNING")
        
        # ... existing training code ...
        
        # Set status to SUCCESS on completion
        db.set_state(model=model, coin=coin, state="SUCCESS")
        
    except Exception as e:
        # Set status to FAILED on error
        db.set_state(model=model, coin=coin, state="FAILED", error_message=str(e))
        raise
```

## Next Steps

1. Add status updates to `utils/trainer/trl_train.py`
2. Add status updates to `trainer/lightgbm_trainer.py`
3. Add status updates to `trainer/time_series_transformer.py`
4. Test by running a training DAG and verify status changes from PENDING → RUNNING → SUCCESS





