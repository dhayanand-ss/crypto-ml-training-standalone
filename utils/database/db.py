import os
import pandas as pd
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

class CryptoDB:
    """
    Mock CryptoDB for standalone execution.
    Uses local CSV files instead of GCP Firestore.
    """
    def __init__(self, engine=None, engine_trl=None, coins=None, data_path=None, wanted_columns=None):
        self.coins = coins or []
        self.data_path = data_path or os.getenv("DATA_PATH", "data/prices")
        self.wanted_columns = wanted_columns or ["open_time", "open", "high", "low", "close", "volume"]
        logger.info(f"Mock CryptoDB initialized (data_path: {self.data_path})")

    def _create_table_if_not_exists(self, coin):
        pass

    def create_TRL_tables(self):
        pass

    def update_from_csv(self, coin, max_rows_to_sync=None):
        logger.info(f"Mock sync from CSV for {coin} (skipped for standalone)")
        pass

    def bulk_insert_df(self, table_name, df):
        logger.info(f"Mock bulk_insert_df for {table_name}: {len(df)} rows (skipped Firestore)")
        return True

    def get_last_date(self, table_name):
        """Read last date from local CSV instead of DB."""
        csv_path = Path(self.data_path) / f"{table_name.upper()}.csv"
        if csv_path.exists():
            try:
                df = pd.read_csv(csv_path)
                if not df.empty and "open_time" in df.columns:
                    return pd.to_datetime(df["open_time"], utc=True).max()
            except Exception as e:
                logger.warning(f"Error reading {csv_path} for last date: {e}")
        return None

    def insert_row(self, table_name, **kwargs):
        logger.info(f"Mock insert_row into {table_name} (skipped Firestore)")

    def insert_df_rows(self, table_name, df, bulk=False, chunk_size=1000):
        logger.info(f"Mock insert_df_rows into {table_name}: {len(df)} rows (skipped Firestore)")

    def upsert_predictions(self, table_name, model, version, open_times, predictions, original_df, threshold=100):
        logger.info(f"Mock upsert_predictions into {table_name} (skipped Firestore)")

    def get_missing_prediction_times(self, coin, model, version):
        """Mock missing prediction times - return empty for now to skip backfill."""
        logger.info(f"Mock get_missing_prediction_times for {coin} {model} {version} (returning empty)")
        return []
