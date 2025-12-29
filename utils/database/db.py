from google.cloud import firestore
from google.oauth2 import service_account
import pandas as pd
from datetime import timedelta, datetime, timezone
from tqdm import tqdm
import os
import json
import numpy as np
import ast
import time

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
            # Use Application Default Credentials (ADC) for GCP environments
            project_id = os.getenv("GCP_PROJECT_ID")
            return firestore.Client(project=project_id) if project_id else firestore.Client()
    except Exception as e:
        print(f"[WARNING] Failed to initialize Firestore client: {e}")
        raise

def normalize_pred(x):
    if isinstance(x, np.ndarray):
        return x.tolist()
    if isinstance(x, (tuple, list)):
        return list(x)
    if isinstance(x, str):
        s = x.strip()
        if s.startswith("[") and s.endswith("]"):
            try:
                # try JSON first
                return json.loads(s.replace(" ", ","))
            except Exception:
                # fallback: NumPy parse space-separated
                return np.fromstring(s.strip("[]"), sep=" ").tolist()
        return [float(s)]
    return [float(x)]

required_cols = ["open_time", "open", "high", "low", "close", "volume"]

class CryptoDB:
    def __init__(self, engine=None, engine_trl=None, coins=None, data_path=None, wanted_columns=None):
        # For backward compatibility, engine params are ignored
        self.db = _get_firestore_client()
        self.coins = coins or []
        # Use environment variable or default to local data directory
        self.data_path = data_path or os.getenv("DATA_PATH", "data/prices")
        self.wanted_columns = wanted_columns or ["open_time", "open", "high", "low", "close", "volume"]

        # Initialize collections and update with CSV
        # Limit initial sync to 100,000 rows to avoid long initialization times
        max_initial_sync = int(os.getenv("MAX_INITIAL_SYNC_ROWS", "100000"))
        for coin in self.coins:
            self._create_table_if_not_exists(coin)
            self.update_from_csv(coin, max_rows_to_sync=max_initial_sync)
        
        self.create_TRL_tables()

    def _create_table_if_not_exists(self, coin):
        # Firestore collections are created automatically on first write
        # This method is kept for API compatibility
        pass
            
    def create_TRL_tables(self):
        # Firestore collections are created automatically on first write
        # This method is kept for API compatibility
        pass

    def reset_trl_version(self, version: int):
        """
        Sets the entire trl_{version} field to None in the 'trl' collection.
        """
        trl_column = f"trl_{version}"
        trl_ref = self.db.collection('trl')
        
        # Get all documents and update them
        docs = trl_ref.stream()
        batch = self.db.batch()
        batch_count = 0
        
        for doc in docs:
            doc_ref = trl_ref.document(doc.id)
            batch.update(doc_ref, {trl_column: None})
            batch_count += 1
            
            if batch_count >= 500:  # Firestore batch limit
                batch.commit()
                batch = self.db.batch()
                batch_count = 0
        
        if batch_count > 0:
            batch.commit()

        print(f"All values in field '{trl_column}' have been set to None.")

    def upsert_trl_full(self, df, version=1):
        """
        Full upsert into 'trl' collection:
        - Updates existing documents for the given trl_version field
        - Inserts missing documents
        - Stores 'pred' as list in the specified trl field
        - Uses batch operations for efficiency
        - 'label' and 'price_change' can be None
        - Uses 'link' as the document ID
        """
        trl_column = f"trl_{version}"
        trl_ref = self.db.collection('trl')

        def parse_pred(val):
            if isinstance(val, str):
                try:
                    parsed = ast.literal_eval(val)
                    if isinstance(parsed, list):
                        return [float(x) for x in parsed]
                    else:
                        return [float(parsed)]
                except Exception:
                    cleaned = val.strip('[]').replace(',', ' ')
                    return [float(x) for x in cleaned.split() if x]
            elif isinstance(val, (list, tuple)):
                return [float(x) for x in val]
            elif isinstance(val, (int, float)):
                return [float(val)]
            return None

        df['pred_list'] = df['pred'].apply(parse_pred)
        
        if "label" not in df.columns:
            df["label"] = None
        if "price_change" not in df.columns:
            df["price_change"] = None

        print(f"Upserting {len(df)} rows into trl collection...")
        
        batch = self.db.batch()
        batch_count = 0
        
        for _, row in df.iterrows():
            doc_data = {
                'title': row['title'],
                'link': row['link'],
                'date': pd.to_datetime(row['date']).replace(tzinfo=timezone.utc) if pd.notna(row['date']) else None,
                trl_column: row['pred_list'],
                'price_change': float(row['price_change']) if pd.notna(row['price_change']) else None,
                'label': int(row['label']) if pd.notna(row['label']) else None
            }
            
            # Use link as document ID for upsert
            doc_ref = trl_ref.document(row['link'])
            batch.set(doc_ref, doc_data, merge=True)
            batch_count += 1
            
            if batch_count >= 500:
                batch.commit()
                batch = self.db.batch()
                batch_count = 0
        
        if batch_count > 0:
            batch.commit()
        
        print(f"Upserted {len(df)} rows into trl collection.")

    def insert_if_not_exists(self, df, table_name="trl"):
        """
        Insert documents into `table_name` collection only if the 'link' does not already exist.
        """
        if df['pred'].dtype == object and isinstance(df['pred'].iloc[0], str):
            df['pred_list'] = df['pred'].apply(lambda x: [float(i) for i in x.strip('[]').split()])
        else:
            df['pred_list'] = df['pred']

        collection_ref = self.db.collection(table_name)
        rows_inserted = 0
        batch = self.db.batch()
        batch_count = 0
        
        for _, row in df.iterrows():
            doc_ref = collection_ref.document(row['link'])
            # Check if document exists
            if doc_ref.get().exists:
                continue
            
            doc_data = {
                'title': row['title'],
                'link': row['link'],
                'date': pd.to_datetime(row['date']).replace(tzinfo=timezone.utc) if pd.notna(row['date']) else None,
                'pred': row['pred_list'],
                'price_change': float(row['price_change']) if pd.notna(row['price_change']) else None,
                'label': int(row['label']) if pd.notna(row['label']) else None
            }
            
            batch.set(doc_ref, doc_data)
            batch_count += 1
            rows_inserted += 1
            
            if batch_count >= 500:
                batch.commit()
                batch = self.db.batch()
                batch_count = 0
        
        if batch_count > 0:
            batch.commit()

        print(f"Inserted {rows_inserted} new rows into {table_name}, skipped existing links.")

    def get_last_crypto_date(self):
        """
        Returns the latest date from the 'trl' collection.
        If no documents exist, returns None.
        """
        trl_ref = self.db.collection('trl')
        docs = trl_ref.order_by('date', direction=firestore.Query.DESCENDING).limit(1).stream()
        
        for doc in docs:
            data = doc.to_dict()
            if 'date' in data and data['date']:
                return pd.to_datetime(data['date'], utc=True)
        return None

    def update_from_csv(self, coin, max_rows_to_sync=None):
        """
        Update Firestore from CSV file.
        
        Args:
            coin: Coin symbol (e.g., 'BTCUSDT')
            max_rows_to_sync: Maximum number of rows to sync in one go (default: None = no limit)
                            If set and CSV has more rows, only the most recent rows will be synced.
        """
        print(f"Processing {coin}...")
        
        print(f"Reading CSV from {self.data_path}/{coin}.csv")
        df = pd.read_csv(f'{self.data_path}/{coin}.csv')[self.wanted_columns]
        df['open_time'] = pd.to_datetime(df['open_time'], utc=True, format='mixed')
        
        last_date = self.get_last_date(coin.lower())
        last_date = pd.to_datetime(last_date, utc=True, format='mixed') if last_date else None
        print(f"Last date in DB for {coin}: {last_date}")
        print(f"Last date in CSV for {coin}: {df['open_time'].max()}")
        
        df_new = df[df['open_time'] > last_date] if last_date is not None else df
        print(f"New rows to insert for {coin}: {len(df_new):,}")
        
        # If no data in DB and CSV is very large, limit initial sync
        if last_date is None and max_rows_to_sync and len(df_new) > max_rows_to_sync:
            print(f"[WARNING] CSV has {len(df_new):,} rows but DB is empty.")
            print(f"Limiting initial sync to most recent {max_rows_to_sync:,} rows to avoid timeouts.")
            print(f"Remaining rows will be synced incrementally as new data arrives.")
            df_new = df_new.tail(max_rows_to_sync)
            print(f"Syncing rows from {df_new['open_time'].min()} to {df_new['open_time'].max()}")
        
        if not df_new.empty:
            self.bulk_insert_df(coin, df_new)
        else:
            print("No new rows to insert.")

    def bulk_insert_df(self, table_name, df):
        table_name = table_name.lower()
        collection_ref = self.db.collection(table_name)
        
        total_rows = len(df)
        if total_rows == 0:
            print(f"No rows to insert into {table_name}.")
            return
        
        print(f"Starting bulk insert of {total_rows:,} rows into {table_name}...")
        print(f"This may take a while for large datasets. Progress will be shown every 10,000 rows.")
        
        batch = self.db.batch()
        batch_count = 0
        total_committed = 0
        
        try:
            for idx, (_, row) in enumerate(df.iterrows(), 1):
                # Use open_time as document ID (convert to string)
                doc_id = pd.to_datetime(row['open_time']).isoformat()
                doc_ref = collection_ref.document(doc_id)
                
                doc_data = {
                    'open_time': pd.to_datetime(row['open_time']).replace(tzinfo=timezone.utc),
                    'open': float(row['open']) if pd.notna(row['open']) else None,
                    'high': float(row['high']) if pd.notna(row['high']) else None,
                    'low': float(row['low']) if pd.notna(row['low']) else None,
                    'close': float(row['close']) if pd.notna(row['close']) else None,
                    'volume': float(row['volume']) if pd.notna(row['volume']) else None,
                }
                
                batch.set(doc_ref, doc_data, merge=True)
                batch_count += 1
                
                # Commit every 500 documents (Firestore batch limit)
                if batch_count >= 500:
                    try:
                        batch.commit()
                        total_committed += batch_count
                        batch = self.db.batch()
                        batch_count = 0
                        
                        # Show progress every 10,000 rows
                        if total_committed % 10000 == 0:
                            progress_pct = (total_committed / total_rows) * 100
                            print(f"Progress: {total_committed:,}/{total_rows:,} rows ({progress_pct:.1f}%)")
                    except Exception as e:
                        print(f"[ERROR] Failed to commit batch at row {idx}: {e}")
                        # Check for rate limiting
                        if "quota" in str(e).lower() or "429" in str(e) or "ResourceExhausted" in str(type(e).__name__):
                            print("[WARNING] Firestore quota/rate limit hit. Waiting 60 seconds before retry...")
                            time.sleep(60)
                            # Retry the commit
                            try:
                                batch.commit()
                                total_committed += batch_count
                                batch = self.db.batch()
                                batch_count = 0
                            except Exception as e2:
                                print(f"[ERROR] Retry also failed: {e2}")
                                raise
                        else:
                            raise
                
                # Add small delay to avoid overwhelming Firestore
                if idx % 1000 == 0:
                    time.sleep(0.1)
            
            # Commit remaining documents
            if batch_count > 0:
                try:
                    batch.commit()
                    total_committed += batch_count
                except Exception as e:
                    print(f"[ERROR] Failed to commit final batch: {e}")
                    raise
            
            print(f"Successfully inserted {total_committed:,} rows into {table_name}.")
            self._keep_last_365_days(table_name)
            
        except Exception as e:
            print(f"[ERROR] Bulk insert failed after {total_committed:,} rows: {e}")
            print(f"Only {total_committed:,} out of {total_rows:,} rows were inserted.")
            raise

    def insert_row(self, table_name, **kwargs):
        table_name = table_name.lower()
        collection_ref = self.db.collection(table_name)
        
        # Use open_time as document ID if available
        if 'open_time' in kwargs:
            doc_id = pd.to_datetime(kwargs['open_time']).isoformat()
            doc_ref = collection_ref.document(doc_id)
        else:
            doc_ref = collection_ref.document()
        
        # Convert datetime to Firestore timestamp
        doc_data = {}
        for key, value in kwargs.items():
            if isinstance(value, pd.Timestamp) or isinstance(value, datetime):
                doc_data[key] = pd.to_datetime(value).replace(tzinfo=timezone.utc)
            elif isinstance(value, (list, np.ndarray)):
                doc_data[key] = [float(x) for x in value] if len(value) > 0 else None
            elif pd.isna(value):
                doc_data[key] = None
            else:
                doc_data[key] = value
        
        doc_ref.set(doc_data, merge=True)
        self._keep_last_365_days(table_name)
        print(f"Inserted row into {table_name} and trimmed old rows.")

    def insert_df_rows(self, table_name, df, bulk=False, chunk_size=1000):
        table_name = table_name.lower()

        if df.empty:
            print("No rows to insert.")
            return

        if bulk or len(df) > 100:
            print(f"Bulk inserting {len(df)} rows into {table_name}...")
            collection_ref = self.db.collection(table_name)
            
            batch = self.db.batch()
            batch_count = 0
            
            for _, row in df.iterrows():
                # Filter only required columns
                row_filtered = {col: row[col] for col in required_cols if col in row}
                
                if not row_filtered:
                    continue
                
                # Use open_time as document ID
                doc_id = pd.to_datetime(row['open_time']).isoformat()
                doc_ref = collection_ref.document(doc_id)
                
                doc_data = {}
                for col in required_cols:
                    if col in row:
                        if col == 'open_time':
                            doc_data[col] = pd.to_datetime(row[col]).replace(tzinfo=timezone.utc)
                        else:
                            doc_data[col] = float(row[col]) if pd.notna(row[col]) else None
                
                batch.set(doc_ref, doc_data, merge=True)
                batch_count += 1
                
                if batch_count >= 500:
                    batch.commit()
                    batch = self.db.batch()
                    batch_count = 0
            
            if batch_count > 0:
                batch.commit()
            
            print(f"Bulk inserted {len(df)} rows into {table_name}.")
            self._keep_last_365_days(table_name)
        else:
            df_filtered = df[[c for c in required_cols if c in df.columns]]
            
            if df_filtered.empty:
                print("No rows to insert.")
                return
            
            collection_ref = self.db.collection(table_name)
            batch = self.db.batch()
            batch_count = 0
            
            for start in tqdm(range(0, len(df_filtered), chunk_size)):
                end = start + chunk_size
                chunk = df_filtered.iloc[start:end]
                
                for _, row in chunk.iterrows():
                    doc_id = pd.to_datetime(row['open_time']).isoformat()
                    doc_ref = collection_ref.document(doc_id)
                    
                    doc_data = {}
                    for col in df_filtered.columns:
                        if col == 'open_time':
                            doc_data[col] = pd.to_datetime(row[col]).replace(tzinfo=timezone.utc)
                        else:
                            doc_data[col] = float(row[col]) if pd.notna(row[col]) else None
                    
                    batch.set(doc_ref, doc_data, merge=True)
                    batch_count += 1
                    
                    if batch_count >= 500:
                        batch.commit()
                        batch = self.db.batch()
                        batch_count = 0
                
                if batch_count > 0:
                    batch.commit()
                    batch = self.db.batch()
                    batch_count = 0
            
            self._keep_last_365_days(table_name)
            print(f"Inserted {len(df_filtered)} rows into {table_name} in chunks of {chunk_size}.")

    def shift_predictions(self, table_name, model, from_version, to_version):
        table_name = table_name.lower()
        collection_ref = self.db.collection(table_name)
        
        from_field = f"{model}_{from_version}"
        to_field = f"{model}_{to_version}"
        
        docs = collection_ref.where(from_field, '!=', None).stream()
        batch = self.db.batch()
        batch_count = 0
        
        for doc in docs:
            data = doc.to_dict()
            if from_field in data and data[from_field] is not None:
                doc_ref = collection_ref.document(doc.id)
                batch.update(doc_ref, {
                    to_field: data[from_field],
                    from_field: None
                })
                batch_count += 1
                
                if batch_count >= 500:
                    batch.commit()
                    batch = self.db.batch()
                    batch_count = 0
        
        if batch_count > 0:
            batch.commit()

    def shift_predictions_trl(self, table_name, model, from_version, to_version):
        table_name = table_name.lower()
        collection_ref = self.db.collection(table_name)
        
        from_field = f"{model}_{from_version}"
        to_field = f"{model}_{to_version}"
        
        docs = collection_ref.where(from_field, '!=', None).stream()
        batch = self.db.batch()
        batch_count = 0
        
        for doc in docs:
            data = doc.to_dict()
            if from_field in data and data[from_field] is not None:
                doc_ref = collection_ref.document(doc.id)
                batch.update(doc_ref, {
                    to_field: data[from_field],
                    from_field: None
                })
                batch_count += 1
                
                if batch_count >= 500:
                    batch.commit()
                    batch = self.db.batch()
                    batch_count = 0
        
        if batch_count > 0:
            batch.commit()

    def bulk_update_predictions(self, table_name, model, version, pred_df):
        """
        Bulk update predictions for a given model/version into an existing collection.
        """
        if not {"open_time", "pred"}.issubset(pred_df.columns):
            raise ValueError("pred_df must contain 'open_time' and 'pred' columns")
        
        pred_df = pred_df[["open_time", "pred"]].copy()
        table_name = table_name.lower()
        model = model.lower()
        col_name = f"{model}_{version}"
        collection_ref = self.db.collection(table_name)

        pred_df["open_time"] = pd.to_datetime(pred_df["open_time"], utc=True, format='mixed')

        # Get earliest timestamp in DB
        first_doc = collection_ref.order_by('open_time', direction=firestore.Query.ASCENDING).limit(1).stream()
        first_time_in_db = None
        for doc in first_doc:
            data = doc.to_dict()
            if 'open_time' in data:
                first_time_in_db = pd.to_datetime(data['open_time'], utc=True)
                break

        print(f"Earliest timestamp in {table_name}: {first_time_in_db}, last in DB: {self.get_last_date(table_name)}")
        print(f"Earliest timestamp in input DF: {pred_df['open_time'].min()}, last in input DF: {pred_df['open_time'].max()}")
        
        if first_time_in_db is None:
            print(f"No rows exist in {table_name}, skipping update.")
            return

        pred_df = pred_df[pred_df["open_time"] >= first_time_in_db].copy()
        if pred_df.empty:
            print("No new rows to update after slicing by earliest DB timestamp.")
            return

        print(f"Updating {len(pred_df)} rows in {table_name}.{col_name}")

        # Normalize predictions
        pred_df["pred"] = pred_df["pred"].apply(normalize_pred)

        # Create a map of open_time to pred
        pred_map = {pd.to_datetime(ot).isoformat(): pred for ot, pred in zip(pred_df["open_time"], pred_df["pred"])}

        # Get all documents that need updating
        batch = self.db.batch()
        batch_count = 0
        updated_count = 0

        for time_str, pred in pred_map.items():
            doc_ref = collection_ref.document(time_str)
            doc = doc_ref.get()
            
            if doc.exists:
                batch.update(doc_ref, {col_name: pred})
                batch_count += 1
                updated_count += 1
                
                if batch_count >= 500:
                    batch.commit()
                    batch = self.db.batch()
                    batch_count = 0

        if batch_count > 0:
            batch.commit()

        print(f"Successfully updated {updated_count} rows in {table_name}.{col_name}")

    def get_total_pred_count(self, table_name, model, version):
        table_name = table_name.lower()
        model = model.lower()
        col_name = model if version is None else f"{model}_{version}"
        collection_ref = self.db.collection(table_name)
        
        docs = collection_ref.where(col_name, '!=', None).stream()
        count = sum(1 for _ in docs)
        return count

    def get_first_missing_date(self, table_name, model, version):
        table_name = table_name.lower()
        model = model.lower()
        col_name = model if version is None else f"{model}_{version}"
        collection_ref = self.db.collection(table_name)
        
        # Get documents where col_name is None, ordered by open_time
        docs = collection_ref.where(col_name, '==', None).order_by('open_time', direction=firestore.Query.ASCENDING).limit(1).stream()
        
        for doc in docs:
            data = doc.to_dict()
            if 'open_time' in data:
                return pd.to_datetime(data['open_time'], utc=True)
        return None

    def get_last_date(self, table_name):
        table_name = table_name.lower()
        collection_ref = self.db.collection(table_name)
        
        docs = collection_ref.order_by('open_time', direction=firestore.Query.DESCENDING).limit(1).stream()
        
        for doc in docs:
            data = doc.to_dict()
            if 'open_time' in data:
                return pd.to_datetime(data['open_time'], utc=True)
        return None

    def get_missing_prediction_times(self, table_name, model, version):
        table_name = table_name.lower()
        model = model.lower()
        col_name = model if version is None else f"{model}_{version}"
        collection_ref = self.db.collection(table_name)
        
        docs = collection_ref.where(col_name, '==', None).order_by('open_time', direction=firestore.Query.ASCENDING).stream()
        
        times = []
        for doc in docs:
            data = doc.to_dict()
            if 'open_time' in data:
                times.append(pd.to_datetime(data['open_time'], utc=True))
        return times
    
    def get_missing_prediction_date_range(self, table_name, model, version):
        table_name = table_name.lower()
        model = model.lower()
        col_name = model if version is None else f"{model}_{version}"
        collection_ref = self.db.collection(table_name)
        
        # Get min
        min_docs = collection_ref.where(col_name, '==', None).order_by('open_time', direction=firestore.Query.ASCENDING).limit(1).stream()
        first_missing = None
        for doc in min_docs:
            data = doc.to_dict()
            if 'open_time' in data:
                first_missing = pd.to_datetime(data['open_time'], utc=True)
                break
        
        # Get max
        max_docs = collection_ref.where(col_name, '==', None).order_by('open_time', direction=firestore.Query.DESCENDING).limit(1).stream()
        last_missing = None
        for doc in max_docs:
            data = doc.to_dict()
            if 'open_time' in data:
                last_missing = pd.to_datetime(data['open_time'], utc=True)
                break
        
        return first_missing, last_missing

    def upsert_predictions(self, table_name, model, version, open_times, predictions, original_df, threshold=100):
        """
        Upsert predictions into the given collection.
        """
        original_df = original_df[[c for c in required_cols if c in original_df.columns]].copy()
        self._keep_last_365_days(table_name)
        
        if len(predictions) == 0:
            print("No predictions to upsert.")
            return
        
        if len(open_times) != len(predictions):
            raise ValueError("Number of predictions must match number of open_times")

        table_name = table_name.lower()
        model = model.lower()
        col_name = f"{model}_{version}"
        collection_ref = self.db.collection(table_name)

        # Normalize open_times to datetime
        if isinstance(open_times, pd.Series):
            open_times = pd.to_datetime(open_times, utc=True)
        else:
            open_times = pd.to_datetime(open_times, utc=True)

        # If large batch → use bulk update
        if len(open_times) > threshold:
            pred_df = pd.DataFrame({
                "open_time": open_times,
                "pred": predictions
            })

            before = len(pred_df)
            pred_df = pred_df.dropna(subset=["pred"])
            after = len(pred_df)
            print(f"Bulk update skipped {before - after} null predictions, proceeding with {after} updates.")

            if not pred_df.empty:
                self.bulk_update_predictions(table_name, model, version, pred_df)

            # Handle inserts for missing open_times
            print("Checking for missing open_times to insert...")
            
            # Get existing times
            existing_times = set()
            for ot in open_times:
                doc_id = pd.to_datetime(ot).isoformat()
                doc = collection_ref.document(doc_id).get()
                if doc.exists:
                    existing_times.add(pd.to_datetime(ot, utc=True))

            missing_times = [ot for ot in open_times if ot not in existing_times]
            print(f"Missing times in DB: {len(missing_times)} out of {len(open_times)}")

            if missing_times:
                print(f"Inserting {len(missing_times)} missing rows...")
                insert_df = original_df[original_df["open_time"].isin(missing_times)].copy()
                pred_map = dict(zip(open_times, predictions))
                insert_df = insert_df[required_cols]
                insert_df[col_name] = insert_df["open_time"].map(pred_map)
                print("Columns in insert_df:", insert_df.columns.tolist())
                self.bulk_insert_df(table_name, insert_df)

            print(f"Upserted {len(open_times)} predictions into {table_name}.{col_name} (bulk + insert).")
            return

        # Small batch path
        batch = self.db.batch()
        batch_count = 0
        
        for ot, preds in zip(open_times, predictions):
            doc_id = pd.to_datetime(ot).isoformat()
            doc_ref = collection_ref.document(doc_id)
            batch.update(doc_ref, {col_name: normalize_pred(preds)})
            batch_count += 1
            
            if batch_count >= 500:
                batch.commit()
                batch = self.db.batch()
                batch_count = 0
        
        if batch_count > 0:
            batch.commit()

        # Check for missing times and insert
        existing_times = set()
        for ot in open_times:
            doc_id = pd.to_datetime(ot).isoformat()
            doc = collection_ref.document(doc_id).get()
            if doc.exists:
                existing_times.add(pd.to_datetime(ot, utc=True))

        missing_times = [ot for ot in open_times if ot not in existing_times]
        print(f"Missing times in DB: {len(missing_times)} out of {len(open_times)}")
        
        if missing_times:
            insert_df = original_df[original_df["open_time"].isin(missing_times)].copy()
            pred_map = dict(zip(open_times, predictions))
            insert_df[col_name] = insert_df["open_time"].map(pred_map)
            print("Columns in insert_df:", insert_df.columns.tolist())
            self.bulk_insert_df(table_name, insert_df)

        print(f"Upserted {len(open_times)} predictions into {table_name}.{col_name} (row-wise).")

    def _keep_last_365_days(self, table_name, time='open_time'):
        table_name = table_name.lower()
        collection_ref = self.db.collection(table_name)
        
        # Get latest timestamp
        latest_docs = collection_ref.order_by(time, direction=firestore.Query.DESCENDING).limit(1).stream()
        latest_ts = None
        for doc in latest_docs:
            data = doc.to_dict()
            if time in data:
                latest_ts = pd.to_datetime(data[time], utc=True)
                break
        
        if latest_ts is None:
            return
        
        cutoff_date = latest_ts - timedelta(days=180)
        cutoff_timestamp = cutoff_date.replace(tzinfo=timezone.utc)
        
        # Delete documents older than cutoff
        docs_to_delete = collection_ref.where(time, '<', cutoff_timestamp).stream()
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


# Usage example - maintain backward compatibility
# Only initialize if credentials are available (lazy initialization)
coins = ["BTCUSDT"]
crypto_db = None

def _init_crypto_db():
    """Lazy initialization of crypto_db - only if credentials are available."""
    global crypto_db
    if crypto_db is None:
        try:
            print("Connecting to GCP Firestore...")
            crypto_db = CryptoDB(coins=coins)
            print("----------------Connected to GCP Firestore...")
        except Exception as e:
            print(f"Warning: Could not initialize GCP Firestore (credentials not found): {e}")
            print("Database operations will be unavailable. Set GCP_CREDENTIALS_PATH or GOOGLE_APPLICATION_CREDENTIALS or configure Application Default Credentials.")
            crypto_db = None
    return crypto_db

# Try to initialize, but don't fail if credentials aren't available
try:
    _init_crypto_db()
except Exception:
    pass  # Silently fail - will be initialized when needed
