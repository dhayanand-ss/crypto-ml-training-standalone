from google.cloud import firestore
from google.oauth2 import service_account
from google.auth import exceptions as google_auth_exceptions
from datetime import datetime, timedelta, timezone
import os

# Initialize GCP Firestore client
def _get_firestore_client():
    """Initialize and return Firestore client using GCP credentials."""
    try:
        # Try to get credentials from environment variable or default path
        cred_path = os.getenv("GCP_CREDENTIALS_PATH") or os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
        if cred_path and os.path.exists(cred_path):
            try:
                cred = service_account.Credentials.from_service_account_file(cred_path)
                # Get project ID from credentials
                project_id = cred.project_id if hasattr(cred, 'project_id') else os.getenv("GCP_PROJECT_ID")
                return firestore.Client(project=project_id, credentials=cred)
            except Exception as e:
                print(f"[WARNING] Failed to initialize GCP Firestore with credentials file: {e}")
                return None
        else:
            # Check if we have project ID - if not, don't even try to initialize
            project_id = os.getenv("GCP_PROJECT_ID")
            if not project_id:
                # No credentials and no project ID - return None without trying
                print("[WARNING] GCP credentials not found. Status logging will be disabled.")
                return None
            
            # Try to initialize with Application Default Credentials (ADC)
            # If this fails, we'll return None
            try:
                return firestore.Client(project=project_id)
            except (Exception, google_auth_exceptions.DefaultCredentialsError) as e:
                # If credentials are missing, return None
                print(f"[WARNING] GCP credentials not found: {e}")
                return None
    except (Exception, google_auth_exceptions.DefaultCredentialsError) as e:
        # Suppress exception details to avoid Airflow import errors
        print(f"[WARNING] Failed to initialize Firestore client")
        return None


class CryptoBatchDB:
    """
    Simple GCP Firestore wrapper to track model/coin training runs.
    - Stores state (PENDING, RUNNING, SUCCESS, FAILED)
    - Training scripts call log_event() as they progress
    - External orchestrators can poll with get_status() to check when jobs are done
    """

    def __init__(self, db_url: str = None):
        # db_url is kept for backward compatibility but not used
        self.db = _get_firestore_client()
        self._firestore_available = self.db is not None
        if not self._firestore_available:
            print("[WARNING] Firestore not available. Status logging will be disabled.")
        self._create_tables()

    def _create_tables(self):
        """Collections are created automatically on first write."""
        pass

    # ---------------------------
    # Event logging
    # ---------------------------
    def log_event(self, dag_name: str, task_name: str, model_name: str,
                  run_id: str, event_type: str, status: str = None, message: str = None, metadata: dict = None):
        """Append event and also update snapshot collection."""
        if not self._firestore_available:
            # Silently skip if Firestore is not available
            return
        
        import logging
        logger = logging.getLogger(__name__)
        
        now = datetime.utcnow().replace(tzinfo=timezone.utc)

        try:
            # Insert into event log
            events_ref = self.db.collection('crypto_batch_events')
            event_doc = {
                'dag_name': dag_name,
                'task_name': task_name,
                'model_name': model_name,
                'run_id': run_id,
                'event_type': event_type,
                'status': status,
                'message': message,
                'metadata': metadata,  # Store metadata
                'created_at': now
            }
            events_ref.add(event_doc)
            logger.debug(f"Event logged to crypto_batch_events: {dag_name}/{task_name}")
        except Exception as e:
            error_msg = f"Failed to write to crypto_batch_events: {type(e).__name__}: {str(e)}"
            logger.error(error_msg)
            print(f"[ERROR] {error_msg}")
            # Check if it's a quota error
            if "quota" in str(e).lower() or "429" in str(e) or "ResourceExhausted" in str(type(e).__name__):
                print("[WARNING] Firestore quota exceeded! Check your GCP console.")
                print("         Writes will fail until quota resets or you upgrade your plan.")
            # Don't raise - continue to try status update

        try:
            # Update snapshot
            status_ref = self.db.collection('crypto_batch_status')
            status_id = f"{dag_name}_{task_name}_{model_name}_{run_id}"
            status_doc_ref = status_ref.document(status_id)
            
            # Get existing document to preserve retries
            existing_doc = status_doc_ref.get()
            existing_data = existing_doc.to_dict() if existing_doc.exists else {}
            current_retries = existing_data.get('retries', 0)
            
            if event_type == 'RETRY':
                current_retries += 1
            
            status_doc = {
                'dag_name': dag_name,
                'task_name': task_name,
                'model_name': model_name,
                'run_id': run_id,
                'status': status,
                'retries': current_retries,
                'last_message': message,
                'updated_at': now
            }
            
            # Merge metadata if provided
            if metadata:
                status_doc['metadata'] = metadata
                # Also merge with existing metadata if meaningful logic is needed, 
                # but simple replacement/update is usually fine for snapshots
                if 'metadata' in existing_data and isinstance(existing_data['metadata'], dict):
                     # Update existing metadata with new keys
                     updated_metadata = existing_data['metadata'].copy()
                     updated_metadata.update(metadata)
                     status_doc['metadata'] = updated_metadata
            
        except Exception as e:
            error_msg = f"Failed to update crypto_batch_status: {type(e).__name__}: {str(e)}"
            logger.error(error_msg)
            print(f"[ERROR] {error_msg}")
            # Check if it's a quota error
            if "quota" in str(e).lower() or "429" in str(e) or "ResourceExhausted" in str(type(e).__name__):
                print("[WARNING] Firestore quota exceeded! Check your GCP console.")
                raise  # Re-raise quota errors so callers know writes failed

    # ---------------------------
    # Queries
    # ---------------------------
    def get_status(self, dag_name: str, run_id: str = None):
        """Fetch current snapshot (optionally filter by run_id)."""
        if not self._firestore_available:
            # Return empty list if Firestore is not available
            return []
        
        status_ref = self.db.collection('crypto_batch_status')
        query = status_ref.where('dag_name', '==', dag_name)
        
        if run_id:
            query = query.where('run_id', '==', run_id)
        
        docs = query.order_by('updated_at', direction=firestore.Query.DESCENDING).stream()
        
        results = []
        for doc in docs:
            data = doc.to_dict()
            results.append(data)
        
        return results

    def get_events(self, dag_name: str, run_id: str = None, limit: int = 200):
        """Fetch recent events for timeline/flowmap view."""
        if not self._firestore_available:
            # Return empty list if Firestore is not available
            return []
        
        events_ref = self.db.collection('crypto_batch_events')
        query = events_ref.where('dag_name', '==', dag_name)
        
        if run_id:
            query = query.where('run_id', '==', run_id)
        
        docs = query.order_by('created_at', direction=firestore.Query.DESCENDING).limit(limit).stream()
        
        results = []
        for doc in docs:
            data = doc.to_dict()
            data['id'] = doc.id
            results.append(data)
        
        return results

    # ---------------------------
    # Maintenance
    # ---------------------------
    def cleanup_old_events(self):
        """Delete events older than 365 days."""
        if not self._firestore_available:
            # Silently skip if Firestore is not available
            return
        
        events_ref = self.db.collection('crypto_batch_events')
        cutoff_date = datetime.utcnow().replace(tzinfo=timezone.utc) - timedelta(days=365)
        
        docs_to_delete = events_ref.where('created_at', '<', cutoff_date).stream()
        batch = self.db.batch()
        batch_count = 0
        
        for doc in docs_to_delete:
            batch.delete(doc.reference)
            batch_count += 1
            
            if batch_count >= 500:
                batch.commit()
                batch = self.db.batch()
                batch_count = 0
        
        if batch_count > 0:
            batch.commit()


import os
# Initialize status_db - handle missing GCP credentials gracefully
db_url = os.getenv("STATUS_DB")


import json
from pathlib import Path

class FileBasedStatusDB:
    """File-based implementation for tracking events when Firestore is unavailable."""
    def __init__(self, storage_dir=None):
        if storage_dir:
            self.storage_dir = Path(storage_dir)
        else:
            self.storage_dir = Path(os.getenv(
                "VASTAI_BLACKLIST_DIR", 
                "/opt/airflow/custom_persistent_shared"
            ))
        
        try:
            self.storage_dir.mkdir(parents=True, exist_ok=True)
            # Try to set permissions to allow writes from multiple users/containers
            try: os.chmod(self.storage_dir, 0o777)
            except: pass
        except Exception:
            self.storage_dir = Path("/tmp/batch_status")
            self.storage_dir.mkdir(parents=True, exist_ok=True)

        self.events_file = self.storage_dir / "event_log.json"
        self.status_file = self.storage_dir / "batch_status_v2.json"
        print(f"[INFO] FileBasedStatusDB using storage: {self.storage_dir}")

    def _load_json(self, file_path):
        if not file_path.exists(): return [] if "event" in file_path.name else {}
        try:
            with open(file_path, 'r') as f: return json.load(f)
        except: return [] if "event" in file_path.name else {}

    def _save_json(self, file_path, data):
        try:
            temp_file = file_path.with_suffix('.tmp')
            with open(temp_file, 'w') as f:
                json.dump(data, f, indent=2, default=str)
            temp_file.replace(file_path)
            try: os.chmod(file_path, 0o777)
            except: pass
        except Exception as e:
            print(f"[ERROR] Failed to save status: {e}")

    def log_event(self, dag_name, task_name, model_name, run_id, event_type, status=None, message=None, metadata=None):
        events = self._load_json(self.events_file)
        event = {
            'dag_name': dag_name,
            'task_name': task_name,
            'model_name': model_name,
            'run_id': run_id,
            'event_type': event_type,
            'status': status,
            'message': message,
            'metadata': metadata,
            'created_at': datetime.utcnow().replace(tzinfo=timezone.utc).isoformat()
        }
        events.append(event)
        # Keep only last 500 events to avoid file bloating
        if len(events) > 500: events = events[-500:]
        self._save_json(self.events_file, events)
        
        # Also update a snapshot status for convenience
        all_status = self._load_json(self.status_file)
        status_id = f"{dag_name}_{task_name}_{model_name}_{run_id}"
        all_status[status_id] = event
        self._save_json(self.status_file, all_status)
        print(f"[INFO] Event logged locally: {event_type} for {model_name}")

    def get_status(self, dag_name, run_id=None):
        all_status = self._load_json(self.status_file)
        results = []
        for sid, data in all_status.items():
            if data.get('dag_name') == dag_name:
                if run_id is None or data.get('run_id') == run_id:
                    results.append(data)
        return results

    def get_events(self, dag_name, run_id=None, limit=200):
        events = self._load_json(self.events_file)
        results = []
        for event in reversed(events): # Newest first
            if event.get('dag_name') == dag_name:
                if run_id is None or event.get('run_id') == run_id:
                    results.append(event)
            if len(results) >= limit: break
        return results

    def cleanup_old_events(self):
        pass

# Initialize status_db - handle missing GCP credentials or Firestore failure
db_url = os.getenv("STATUS_DB")

# Try to initialize Firestore, but fall back to FileBased if it fails
try:
    status_db = CryptoBatchDB(db_url)
    if not hasattr(status_db, '_firestore_available') or not status_db._firestore_available:
        print("[WARNING] Firestore not available. Falling back to FileBasedStatusDB.")
        status_db = FileBasedStatusDB()
except Exception as e:
    print(f"[WARNING] StatusDB initialization failed ({e}). Falling back to FileBasedStatusDB.")
    status_db = FileBasedStatusDB()
