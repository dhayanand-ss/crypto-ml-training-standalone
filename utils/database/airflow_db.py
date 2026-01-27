from google.cloud import firestore
from google.oauth2 import service_account
from google.auth import exceptions as google_auth_exceptions
from datetime import datetime, timezone
import os

# Initialize GCP Firestore client
def _get_firestore_client():
    """Initialize and return Firestore client using GCP credentials."""
    try:
        # Try to get credentials from environment variable or default path
        cred_path = os.getenv("GCP_CREDENTIALS_PATH") or os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
        if cred_path and os.path.exists(cred_path):
            cred = service_account.Credentials.from_service_account_file(cred_path)
            # Get project ID from credentials
            project_id = cred.project_id if hasattr(cred, 'project_id') else os.getenv("GCP_PROJECT_ID")
            return firestore.Client(project=project_id, credentials=cred)
        else:
            # Check if we have project ID - if not, don't even try to initialize
            project_id = os.getenv("GCP_PROJECT_ID")
            if not project_id:
                # No credentials and no project ID - return None without trying
                print("[WARNING] GCP credentials not found. Status logging will be disabled.")
                return None
            
            # Use Application Default Credentials (ADC) for GCP environments
            try:
                return firestore.Client(project=project_id)
            except (Exception, google_auth_exceptions.DefaultCredentialsError) as e:
                print(f"[WARNING] GCP credentials not found: {e}")
                return None
    except (Exception, google_auth_exceptions.DefaultCredentialsError) as e:
        # Suppress exception to avoid Airflow import errors
        print(f"[WARNING] Failed to initialize Firestore client")
        return None


class BatchStatusDB:
    """
    Simple GCP Firestore wrapper to track model/coin training runs.
    - Stores state (PENDING, RUNNING, SUCCESS, FAILED)
    - Training scripts call set_state() as they progress
    - External orchestrators can poll with get_status() to check when jobs are done
    - Note: Despite the filename, this does NOT depend on Airflow - it uses GCP Firestore
    """

    def __init__(self, db_url: str = None):
        # db_url is kept for backward compatibility but not used
        self.db = _get_firestore_client()
        self._firestore_available = self.db is not None
        if not self._firestore_available:
            print("[WARNING] Firestore not available. Status logging will be disabled.")
        self._create_table()

    def _create_table(self):
        """Collections are created automatically on first write."""
        pass

    def flush(self):
        """Reset collection at DAG start or before a new cycle."""
        if not self._firestore_available:
            return
        batch_status_ref = self.db.collection('batch_status')
        docs = batch_status_ref.stream()
        batch = self.db.batch()
        batch_count = 0
        
        for doc in docs:
            batch.delete(doc.reference)
            batch_count += 1
            
            if batch_count >= 500:
                batch.commit()
                batch = self.db.batch()
                batch_count = 0
        
        if batch_count > 0:
            batch.commit()

    def init_entries(self):
        """Insert initial documents with PENDING state."""
        if not self._firestore_available:
            return
        batch_status_ref = self.db.collection('batch_status')
        batch = self.db.batch()
        batch_count = 0
        
        for model in ["lightgbm", "tst"]:
            for coin in ["BTCUSDT"]:
                doc_id = f"{model}_{coin}"
                doc_ref = batch_status_ref.document(doc_id)
                batch.set(doc_ref, {
                    'model': model,
                    'coin': coin,
                    'state': 'PENDING',
                    'updated_at': datetime.utcnow().replace(tzinfo=timezone.utc),
                    'error_message': None
                })
                batch_count += 1
        
        # Add TRL entry
        doc_ref = batch_status_ref.document('trl_ALL')
        batch.set(doc_ref, {
            'model': 'trl',
            'coin': 'ALL',
            'state': 'PENDING',
            'updated_at': datetime.utcnow().replace(tzinfo=timezone.utc),
            'error_message': None
        })
        batch_count += 1
        
        if batch_count > 0:
            batch.commit()

    def set_state(self, model, coin, state, error_message=None):
        """
        Update state for a given model/coin.
        state = 'PENDING' | 'RUNNING' | 'SUCCESS' | 'FAILED'
        error_message = optional string with Python exception
        """
        if not self._firestore_available:
            return
        batch_status_ref = self.db.collection('batch_status')
        doc_id = f"{model}_{coin}"
        doc_ref = batch_status_ref.document(doc_id)
        
        doc_ref.set({
            'model': model,
            'coin': coin,
            'state': state,
            'error_message': error_message,
            'updated_at': datetime.utcnow().replace(tzinfo=timezone.utc)
        }, merge=True)

    def get_status(self):
        """Return all job states as a list of dicts."""
        if not self._firestore_available:
            return []
        batch_status_ref = self.db.collection('batch_status')
        docs = batch_status_ref.stream()
        
        results = []
        for doc in docs:
            data = doc.to_dict()
            results.append({
                "model": data.get('model'),
                "coin": data.get('coin'),
                "state": data.get('state'),
                "error_message": data.get('error_message')
            })
        
        return results


import os
# Note: Despite the variable name, this is not Airflow-specific
# It's a Firestore-based status database that can be used by any orchestrator
STATUS_DB_URL = os.getenv("STATUS_DB") or os.getenv("AIRFLOW_DB")  # Backward compatibility

# File-based implementation when Firestore is not available
import json
from pathlib import Path

class FileBasedBatchStatusDB:
    """File-based status tracking using JSON files (works without Firestore)."""
    
    def __init__(self, storage_dir=None):
        # Use persistent directory that's shared across Airflow containers
        if storage_dir:
            self.storage_dir = Path(storage_dir)
        else:
            # Try to use Airflow's persistent shared directory
            self.storage_dir = Path(os.getenv(
                "VASTAI_BLACKLIST_DIR",
                "/opt/airflow/custom_persistent_shared"
            ))
        
        # Try to create/use the directory and test write permissions
        storage_ok = False
        if self.storage_dir.exists() or self.storage_dir.parent.exists():
            try:
                self.storage_dir.mkdir(parents=True, exist_ok=True)
                # Test write permissions
                test_file = self.storage_dir / ".write_test"
                try:
                    test_file.write_text("test")
                    test_file.unlink()
                    storage_ok = True
                except (PermissionError, OSError):
                    pass
            except (PermissionError, OSError):
                pass
        
        # Fallback to local directory if persistent dir doesn't exist or isn't writable
        if not storage_ok:
            fallback_dirs = [
                Path("/tmp/batch_status") if os.path.exists("/tmp") else None,
                Path("./batch_status"),
                Path.home() / "batch_status" if hasattr(Path, 'home') else None
            ]
            for fallback_dir in fallback_dirs:
                if fallback_dir is None:
                    continue
                try:
                    fallback_dir.mkdir(parents=True, exist_ok=True)
                    # Test write permissions
                    test_file = fallback_dir / ".write_test"
                    test_file.write_text("test")
                    test_file.unlink()
                    self.storage_dir = fallback_dir
                    storage_ok = True
                    print(f"[WARNING] Using fallback storage directory: {self.storage_dir}")
                    break
                except (PermissionError, OSError):
                    continue
        
        if not storage_ok:
            raise RuntimeError("Could not find a writable directory for batch status storage")
        
        # Set directory permissions to allow writes from all processes
        try:
            os.chmod(self.storage_dir, 0o777)
        except Exception:
            pass  # Ignore permission errors on Windows or if already set
        
        self.status_file = self.storage_dir / "batch_status.json"
        print(f"[INFO] FileBasedBatchStatusDB using storage: {self.storage_dir}")
    
    def _load_status(self):
        """Load status from JSON file."""
        if not self.status_file.exists():
            return {}
        try:
            with open(self.status_file, 'r') as f:
                return json.load(f)
        except Exception as e:
            print(f"[WARNING] Failed to load status file: {e}")
            return {}
    
    def _save_status(self, status_dict):
        """Save status to JSON file."""
        try:
            # Ensure directory exists and has write permissions
            self.storage_dir.mkdir(parents=True, exist_ok=True)
            try:
                os.chmod(self.storage_dir, 0o777)
            except Exception:
                pass  # Ignore permission errors on Windows or if already set
            
            # Write to temporary file first, then rename (atomic operation)
            temp_file = self.status_file.with_suffix('.json.tmp')
            with open(temp_file, 'w') as f:
                json.dump(status_dict, f, indent=2, default=str)
            
            # Set file permissions before renaming
            try:
                os.chmod(temp_file, 0o777)
            except Exception:
                pass  # Ignore permission errors on Windows
            
            # Atomic rename
            temp_file.replace(self.status_file)
            
            # Ensure final file has correct permissions
            try:
                os.chmod(self.status_file, 0o777)
            except Exception:
                pass  # Ignore permission errors on Windows
        except Exception as e:
            print(f"[ERROR] Failed to save status file: {e}")
            # Try fallback: write directly (non-atomic)
            try:
                with open(self.status_file, 'w') as f:
                    json.dump(status_dict, f, indent=2, default=str)
                try:
                    os.chmod(self.status_file, 0o777)
                except Exception:
                    pass
            except Exception as e2:
                print(f"[ERROR] Fallback save also failed: {e2}")
    
    def flush(self):
        """Reset all status entries."""
        self._save_status({})
        print("[INFO] Flushed all status entries")
    
    def init_entries(self):
        """Insert initial documents with PENDING state."""
        status = self._load_status()
        
        for model in ["lightgbm", "tst"]:
            for coin in ["BTCUSDT"]:
                doc_id = f"{model}_{coin}"
                status[doc_id] = {
                    'model': model,
                    'coin': coin,
                    'state': 'PENDING',
                    'updated_at': datetime.utcnow().replace(tzinfo=timezone.utc).isoformat(),
                    'error_message': None
                }
        
        # Add TRL entry
        status['trl_ALL'] = {
            'model': 'trl',
            'coin': 'ALL',
            'state': 'PENDING',
            'updated_at': datetime.utcnow().replace(tzinfo=timezone.utc).isoformat(),
            'error_message': None
        }
        
        self._save_status(status)
        print(f"[INFO] Initialized {len(status)} status entries")
    
    def set_state(self, model, coin, state, error_message=None):
        """Update state for a given model/coin."""
        status = self._load_status()
        doc_id = f"{model}_{coin}"
        
        status[doc_id] = {
            'model': model,
            'coin': coin,
            'state': state,
            'error_message': error_message,
            'updated_at': datetime.utcnow().replace(tzinfo=timezone.utc).isoformat()
        }
        
        self._save_status(status)
        print(f"[INFO] Updated {doc_id} to {state}")
    
    def get_status(self):
        """Return all job states as a list of dicts."""
        status = self._load_status()
        results = []
        for doc_id, data in status.items():
            results.append({
                "model": data.get('model'),
                "coin": data.get('coin'),
                "state": data.get('state'),
                "error_message": data.get('error_message')
            })
        return results


# No-op implementation when Firestore is not available (kept for backward compatibility)
class NoOpBatchStatusDB:
    """No-op implementation when GCP Firestore is not available."""
    def flush(self, *args, **kwargs):
        pass
    def init_entries(self, *args, **kwargs):
        pass
    def set_state(self, *args, **kwargs):
        pass
    def get_status(self, *args, **kwargs):
        return []

# Try to initialize Firestore, but fall back to FileBased if it fails
try:
    db = BatchStatusDB(STATUS_DB_URL)
    # Verify it actually initialized (check if firestore is available)
    if not hasattr(db, '_firestore_available') or not db._firestore_available:
        print("[WARNING] Firestore not available. Check GCP credentials configuration.")
        print("[WARNING] Falling back to file-based status tracking.")
        print("[WARNING] To use Firestore, set GCP_CREDENTIALS_PATH and GCP_PROJECT_ID environment variables.")
        db = FileBasedBatchStatusDB()
    else:
        print("[INFO] Firestore initialized successfully. Using GCP Firestore for status tracking.")
except (Exception, google_auth_exceptions.DefaultCredentialsError) as e:
    # If GCP credentials are missing, use file-based implementation
    print(f"[WARNING] Firestore initialization failed: {e}")
    print("[WARNING] Falling back to file-based status tracking.")
    print("[WARNING] To use Firestore, ensure GCP_CREDENTIALS_PATH and GCP_PROJECT_ID are set correctly.")
    db = FileBasedBatchStatusDB()
# -------------------------------------------------------------------
# Usage Examples
# -------------------------------------------------------------------
#
# db_url = "........."
# db = BatchStatusDB(db_url)
#
# --- In Airflow DAG start (reset + init jobs) ---
# db.flush()
# db.init_entries(models=["tst", "lightgbm", "trl"], coins=["BTCUSDT"])
#
# --- In training script ---
# db.set_state("tst", "BTCUSDT", "RUNNING")
# ... training code ...
# db.set_state("tst", "BTCUSDT", "SUCCESS")
#
# --- In Airflow sensor ---
# states = db.get_status()
# if all(s["state"] in ("SUCCESS", "FAILED") for s in states):
#     # All jobs finished, continue DAG
