"""
GCS / S3 Manager — artifact upload/download via Google Cloud Storage.

Uses the centralised GCSCredentialManager from gcs_credentials.py so that
all credential logic lives in one place.  Falls back gracefully to local-file
mode when GCS is not configured or unreachable, preserving standalone
(non-cloud) operation.

Credential priority (handled by GCSCredentialManager):
  1. GCS_CREDENTIALS_B64   — base64-encoded service account JSON in env var
  2. GOOGLE_APPLICATION_CREDENTIALS / GCP_CREDENTIALS_PATH — JSON key file path
  3. Application Default Credentials (gcloud auth application-default login)
"""

import io
import os
import logging
from pathlib import Path
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)

# ── Lazy import of gcs_creds so the module is usable without google-cloud ───
try:
    import sys
    # Resolve project root regardless of where this file is imported from
    _project_root = Path(__file__).resolve().parent.parent.parent
    if str(_project_root) not in sys.path:
        sys.path.insert(0, str(_project_root))

    from gcs_credentials import gcs_creds, _GCS_AVAILABLE
except ImportError:
    gcs_creds = None
    _GCS_AVAILABLE = False


def _gcs_ready() -> bool:
    """Return True only when GCS credentials and bucket name are configured."""
    if not _GCS_AVAILABLE or gcs_creds is None:
        return False
    if not os.getenv("GCS_BUCKET_NAME", "").strip():
        return False
    return True


class GCSManager:
    """
    Manages artifact storage in Google Cloud Storage with a local-file fallback.

    When GCS is not configured (no bucket name / no credentials) the class
    operates in standalone mode — uploads are skipped and downloads check the
    local filesystem only.
    """

    def __init__(
        self,
        bucket: Optional[str] = None,
        project_id: Optional[str] = None,
        credentials_path: Optional[str] = None,
    ):
        self.bucket_name = bucket or os.getenv("GCS_BUCKET_NAME", "").strip()
        # credentials_path kept for API compatibility; gcs_creds handles loading
        self._standalone = not _gcs_ready()

        if self._standalone:
            logger.info(
                "GCSManager running in standalone (local) mode — "
                "set GCS_BUCKET_NAME + credentials to enable cloud storage."
            )
        else:
            logger.info("GCSManager initialised with bucket: %s", self.bucket_name)

    # ── Internal helpers ─────────────────────────────────────────────────────

    def _get_bucket(self):
        return gcs_creds.get_bucket(self.bucket_name)

    # ── Public API ───────────────────────────────────────────────────────────

    def download_df(self, local_path: str, key: str) -> bool:
        """
        Download a parquet/CSV DataFrame from GCS to *local_path*.

        In standalone mode (no GCS), returns True if the local file already
        exists, False otherwise.
        """
        if self._standalone:
            if os.path.exists(local_path):
                logger.info("Standalone: local file found at %s — skipping GCS download.", local_path)
                return True
            logger.warning("Standalone: file not found at %s and GCS is not configured.", local_path)
            return False

        try:
            bucket = self._get_bucket()
            blob = bucket.blob(key)
            data = blob.download_as_bytes()
            # Detect format from key extension
            local_path_obj = Path(local_path)
            local_path_obj.parent.mkdir(parents=True, exist_ok=True)
            if key.endswith(".parquet"):
                df = pd.read_parquet(io.BytesIO(data))
                df.to_parquet(local_path, index=False)
            else:
                local_path_obj.write_bytes(data)
            logger.info("GCS download: gs://%s/%s → %s", self.bucket_name, key, local_path)
            return True
        except Exception as exc:
            logger.error("GCS download failed for key '%s': %s", key, exc)
            # Fallback to local file if it exists
            if os.path.exists(local_path):
                logger.warning("Using existing local file at %s as fallback.", local_path)
                return True
            return False

    def upload_df(self, df: pd.DataFrame, key: str) -> bool:
        """
        Upload a DataFrame to GCS under *key*.

        In standalone mode the upload is silently skipped.
        """
        if self._standalone:
            logger.info("Standalone: GCSManager.upload_df skipped for key '%s'.", key)
            return True

        try:
            bucket = self._get_bucket()
            blob = bucket.blob(key)
            if key.endswith(".parquet"):
                buf = io.BytesIO()
                df.to_parquet(buf, index=False)
                buf.seek(0)
                blob.upload_from_file(buf, content_type="application/octet-stream")
            else:
                csv_str = df.to_csv(index=False)
                blob.upload_from_string(csv_str, content_type="text/csv")
            logger.info(
                "GCS upload: DataFrame (%d rows) → gs://%s/%s",
                len(df), self.bucket_name, key,
            )
            return True
        except Exception as exc:
            logger.error("GCS upload failed for key '%s': %s", key, exc)
            return False

    def download_price_data(self, symbol: str, local_path: str) -> bool:
        """
        Download price CSV for *symbol* from GCS.

        In standalone mode, checks if the file already exists locally.
        GCS key convention: prices/<symbol>.csv
        """
        key = f"prices/{symbol}.csv"
        if self._standalone:
            if os.path.exists(local_path):
                logger.info("Standalone: local price data found at %s.", local_path)
                return True
            logger.warning(
                "Standalone: price data for %s not found at %s.", symbol, local_path
            )
            return False

        return self.download_df(local_path, key)

    def upload_price_data(self, symbol: str, local_path: str) -> bool:
        """Upload a local price CSV to GCS.  GCS key: prices/<symbol>.csv"""
        if self._standalone:
            logger.info("Standalone: upload_price_data skipped for %s.", symbol)
            return True

        key = f"prices/{symbol}.csv"
        try:
            bucket = self._get_bucket()
            blob = bucket.blob(key)
            blob.upload_from_filename(local_path, content_type="text/csv")
            logger.info(
                "GCS upload: %s → gs://%s/%s", local_path, self.bucket_name, key
            )
            return True
        except Exception as exc:
            logger.error("GCS upload_price_data failed for %s: %s", symbol, exc)
            return False

    def upload_model(self, local_path: str, key: str) -> bool:
        """Upload a model artefact (ONNX, pkl, txt, pth) to GCS."""
        if self._standalone:
            logger.info("Standalone: upload_model skipped for key '%s'.", key)
            return True

        try:
            bucket = self._get_bucket()
            blob = bucket.blob(key)
            blob.upload_from_filename(local_path)
            logger.info(
                "GCS upload: model %s → gs://%s/%s", local_path, self.bucket_name, key
            )
            return True
        except Exception as exc:
            logger.error("GCS upload_model failed for key '%s': %s", key, exc)
            return False

    def download_model(self, key: str, local_path: str) -> bool:
        """Download a model artefact from GCS to *local_path*."""
        return self.download_df(local_path, key)


# Alias — backward-compatible (existing code imports S3Manager from here)
S3Manager = GCSManager
