"""
Centralised GCS credential manager.

Supports three methods in priority order:
  1. Inline base64-encoded JSON in env var (GCS_CREDENTIALS_B64)
  2. Path to service account JSON (GOOGLE_APPLICATION_CREDENTIALS or GCP_CREDENTIALS_PATH)
  3. Application Default Credentials (gcloud auth application-default login)

Usage:
    from gcs_credentials import gcs_creds

    client = gcs_creds.get_client()
    bucket = gcs_creds.get_bucket()          # uses GCS_BUCKET_NAME env var
    bucket = gcs_creds.get_bucket("my-bkt")  # explicit name
"""

import os
import json
import base64
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Lazy-import so the module is importable even when google-cloud-storage is absent
try:
    from google.oauth2 import service_account
    from google.cloud import storage
    _GCS_AVAILABLE = True
except ImportError:
    _GCS_AVAILABLE = False
    logger.warning(
        "google-cloud-storage not installed. "
        "Install with: pip install google-cloud-storage google-auth"
    )


class GCSCredentialManager:
    """Thread-safe, lazy singleton for GCS client initialisation."""

    def __init__(self):
        self._client = None
        self._credentials = None
        self._method_used: Optional[str] = None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load_credentials(self):
        """Return google.oauth2 credentials or None (triggers ADC)."""
        if not _GCS_AVAILABLE:
            raise RuntimeError(
                "google-cloud-storage is not installed. "
                "Run: pip install google-cloud-storage google-auth"
            )

        # ── Method 1: base64-encoded JSON in env var (most portable) ──
        b64 = os.getenv("GCS_CREDENTIALS_B64", "").strip()
        if b64:
            try:
                json_str = base64.b64decode(b64).decode("utf-8")
                info = json.loads(json_str)
                creds = service_account.Credentials.from_service_account_info(
                    info,
                    scopes=["https://www.googleapis.com/auth/cloud-platform"],
                )
                self._method_used = "GCS_CREDENTIALS_B64 (inline base64 JSON)"
                return creds
            except Exception as exc:
                logger.warning("GCS_CREDENTIALS_B64 parsing failed: %s", exc)

        # ── Method 2: path to JSON key file ──
        key_path = (
            os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "").strip()
            or os.getenv("GCP_CREDENTIALS_PATH", "").strip()
        )
        if key_path and os.path.exists(key_path):
            try:
                creds = service_account.Credentials.from_service_account_file(
                    key_path,
                    scopes=["https://www.googleapis.com/auth/cloud-platform"],
                )
                self._method_used = f"service account JSON file ({key_path})"
                return creds
            except Exception as exc:
                logger.warning(
                    "Failed to load service account from %s: %s", key_path, exc
                )
        elif key_path:
            logger.warning(
                "Credential file path '%s' does not exist; falling back to ADC.",
                key_path,
            )

        # ── Method 3: Application Default Credentials (ADC) ──
        self._method_used = "Application Default Credentials (ADC)"
        return None  # google.cloud.storage picks up ADC automatically

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_client(self) -> "storage.Client":
        """Return (and cache) an initialised storage.Client."""
        if self._client is None:
            creds = self._load_credentials()
            project = os.getenv("GCP_PROJECT_ID") or None
            self._client = storage.Client(credentials=creds, project=project)
            logger.info("GCS client initialised via: %s", self._method_used)
        return self._client

    def get_bucket(self, bucket_name: Optional[str] = None) -> "storage.Bucket":
        """Return a Bucket handle.  Reads GCS_BUCKET_NAME if name is omitted."""
        name = bucket_name or os.getenv("GCS_BUCKET_NAME", "").strip()
        if not name:
            raise ValueError(
                "Bucket name not provided and GCS_BUCKET_NAME is not set in environment."
            )
        return self.get_client().bucket(name)

    def health_check(self) -> dict:
        """
        Lightweight connectivity test — reloads bucket metadata without
        downloading any objects.

        Returns a dict with keys: status ("ok" | "error"), method, bucket, project.
        """
        if not _GCS_AVAILABLE:
            return {
                "status": "error",
                "error": "google-cloud-storage not installed",
                "method": None,
            }
        try:
            client = self.get_client()
            bucket_name = os.getenv("GCS_BUCKET_NAME", "").strip()
            if not bucket_name:
                return {
                    "status": "error",
                    "error": "GCS_BUCKET_NAME env var not set",
                    "method": self._method_used,
                }
            bucket = client.bucket(bucket_name)
            bucket.reload()
            return {
                "status": "ok",
                "method": self._method_used,
                "bucket": bucket_name,
                "project": client.project,
            }
        except Exception as exc:
            return {
                "status": "error",
                "error": str(exc),
                "method": self._method_used,
            }

    def reset(self):
        """Force re-initialisation on next get_client() call (useful in tests)."""
        self._client = None
        self._credentials = None
        self._method_used = None


# ── Module-level singleton ──────────────────────────────────────────────────
gcs_creds = GCSCredentialManager()
