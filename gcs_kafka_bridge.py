"""
GCS ↔ Kafka Bidirectional Bridge
=================================

Two classes:

  GCSKafkaSink   — Kafka → GCS archiver (Direction B)
    Consumes every active Kafka topic and writes partitioned JSONL files to GCS.
    GCS path: archive/<topic>/year=YYYY/month=MM/day=DD/<HHmmss>_<N>msgs.jsonl

  GCSKafkaSeeder — GCS → Kafka replayer (Direction A)
    Reads archived JSONL files from GCS and replays them into Kafka topics.
    Supports full replay, date-range filtering, and "latest N files" mode.

CLI usage:
    python gcs_kafka_bridge.py sink
    python gcs_kafka_bridge.py seed --topic BTCUSDT --from 2026-01-01 --to 2026-03-01
    python gcs_kafka_bridge.py seed --topic BTCUSDT --latest-n 10 --target BTCUSDT.replay
    python gcs_kafka_bridge.py list
    python gcs_kafka_bridge.py health
"""

from __future__ import annotations

import json
import logging
import os
import re
import signal
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

# Project root on sys.path so local imports resolve correctly
sys.path.insert(0, str(Path(__file__).parent))

from gcs_credentials import gcs_creds

# ── Optional confluent-kafka import ─────────────────────────────────────────
try:
    from confluent_kafka import Consumer, Producer, KafkaError
    from confluent_kafka.admin import AdminClient
    _CONFLUENT_AVAILABLE = True
except ImportError:
    _CONFLUENT_AVAILABLE = False

# ── Optional QuixStreams import (used by existing producer/consumer) ─────────
try:
    from quixstreams import Application as QuixApplication
    _QUIX_AVAILABLE = True
except ImportError:
    _QUIX_AVAILABLE = False

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s — %(message)s",
)
logger = logging.getLogger("gcs_kafka_bridge")

# ── Helpers ──────────────────────────────────────────────────────────────────

def _bootstrap() -> str:
    host = os.getenv("KAFKA_HOST", "localhost")
    return host if ":" in host else f"{host}:9092"


def _archive_prefix() -> str:
    return os.getenv("GCS_ARCHIVE_PREFIX", "archive")


def _discover_topics(bootstrap: str) -> List[str]:
    """
    Auto-discover topics via Kafka AdminClient.
    Falls back to env var KAFKA_TOPICS (comma-separated) if AdminClient
    is unavailable or times out.
    """
    env_topics = os.getenv("KAFKA_TOPICS", "")
    default_topics = [t.strip() for t in env_topics.split(",") if t.strip()]

    if not _CONFLUENT_AVAILABLE:
        logger.warning(
            "confluent-kafka not installed; using KAFKA_TOPICS env var: %s",
            default_topics or ["BTCUSDT"],
        )
        return default_topics or ["BTCUSDT"]

    try:
        admin = AdminClient({"bootstrap.servers": bootstrap})
        meta = admin.list_topics(timeout=5)
        topics = [t for t in meta.topics if not t.startswith("__")]
        if topics:
            logger.info("Discovered %d Kafka topics: %s", len(topics), topics)
            return topics
    except Exception as exc:
        logger.warning("Topic auto-discovery failed (%s); using fallback.", exc)

    return default_topics or ["BTCUSDT"]


# ═══════════════════════════════════════════════════════════════════════════
# Direction B: Kafka → GCS  (archiver / sink)
# ═══════════════════════════════════════════════════════════════════════════

class GCSKafkaSink:
    """
    Consumes from ALL active Kafka topics and archives messages to GCS as
    partitioned JSONL files.

    GCS path pattern:
        archive/<topic>/year=YYYY/month=MM/day=DD/<HHmmss>_<N>msgs.jsonl

    Messages are buffered in memory and flushed to GCS either when the
    per-topic buffer reaches GCS_SINK_BATCH_SIZE or when
    GCS_SINK_FLUSH_INTERVAL_SECONDS elapses — whichever comes first.

    Environment variables:
        KAFKA_HOST                      Kafka broker (default: localhost:9092)
        KAFKA_TOPICS                    Comma-separated fallback list of topics
        GCS_BUCKET_NAME                 Target GCS bucket
        GCS_ARCHIVE_PREFIX              Top-level prefix in bucket (default: archive)
        GCS_SINK_BATCH_SIZE             Messages per flush per topic (default: 100)
        GCS_SINK_FLUSH_INTERVAL_SECONDS Seconds between forced flushes (default: 60)
    """

    def __init__(self):
        if not _CONFLUENT_AVAILABLE:
            raise RuntimeError(
                "confluent-kafka is required for GCSKafkaSink. "
                "Install with: pip install confluent-kafka"
            )
        self.bootstrap = _bootstrap()
        self.topics = _discover_topics(self.bootstrap)
        self.batch_size = int(os.getenv("GCS_SINK_BATCH_SIZE", "100"))
        self.flush_interval = int(os.getenv("GCS_SINK_FLUSH_INTERVAL_SECONDS", "60"))
        self.bucket = gcs_creds.get_bucket()
        self.buffer: dict[str, list] = defaultdict(list)
        self.last_flush = time.time()
        self._running = True
        signal.signal(signal.SIGTERM, self._handle_signal)
        signal.signal(signal.SIGINT, self._handle_signal)

    def _handle_signal(self, signum, frame):
        logger.info("Signal received — draining buffers and stopping sink.")
        self._running = False

    # ── GCS helpers ─────────────────────────────────────────────────────────

    def _gcs_path(self, topic: str, n_msgs: int) -> str:
        now = datetime.now(timezone.utc)
        return (
            f"{_archive_prefix()}/{topic}/"
            f"year={now.year}/month={now.month:02d}/day={now.day:02d}/"
            f"{now.strftime('%H%M%S')}_{n_msgs}msgs.jsonl"
        )

    def _flush_topic(self, topic: str):
        msgs = self.buffer.get(topic)
        if not msgs:
            return
        content = "\n".join(json.dumps(m, default=str) for m in msgs)
        path = self._gcs_path(topic, len(msgs))
        try:
            blob = self.bucket.blob(path)
            blob.upload_from_string(content, content_type="application/jsonl")
            logger.info(
                "GCS Sink: flushed %d msgs from '%s' → gs://%s/%s",
                len(msgs), topic, self.bucket.name, path,
            )
        except Exception as exc:
            logger.error("GCS Sink: upload failed for topic '%s': %s", topic, exc)
        finally:
            self.buffer[topic].clear()

    def _flush_all(self):
        for topic in list(self.buffer.keys()):
            self._flush_topic(topic)
        self.last_flush = time.time()

    # ── Main loop ───────────────────────────────────────────────────────────

    def run(self):
        """Block and consume.  Flushes to GCS on batch/time trigger."""
        consumer = Consumer(
            {
                "bootstrap.servers": self.bootstrap,
                "group.id": "gcs-sink-archiver",
                "auto.offset.reset": "latest",
                "enable.auto.commit": True,
            }
        )
        consumer.subscribe(self.topics)
        logger.info("GCS Sink started — archiving topics: %s", self.topics)
        try:
            while self._running:
                msg = consumer.poll(timeout=1.0)

                if msg is not None and not msg.error():
                    try:
                        payload = json.loads(msg.value().decode("utf-8"))
                        # Attach Kafka metadata for auditability
                        if isinstance(payload, list):
                            # The existing producer sends batches as JSON arrays;
                            # unwrap into individual records so each line is one candle.
                            for record in payload:
                                record.update(
                                    {
                                        "_kafka_topic": msg.topic(),
                                        "_kafka_offset": msg.offset(),
                                        "_kafka_partition": msg.partition(),
                                        "_archived_at": datetime.now(timezone.utc).isoformat(),
                                    }
                                )
                                self.buffer[msg.topic()].append(record)
                        else:
                            payload.update(
                                {
                                    "_kafka_topic": msg.topic(),
                                    "_kafka_offset": msg.offset(),
                                    "_kafka_partition": msg.partition(),
                                    "_archived_at": datetime.now(timezone.utc).isoformat(),
                                }
                            )
                            self.buffer[msg.topic()].append(payload)
                    except (json.JSONDecodeError, TypeError, AttributeError) as exc:
                        logger.debug("Skipping non-JSON message: %s", exc)
                elif msg is not None and msg.error() and msg.error().code() != KafkaError._PARTITION_EOF:
                    logger.warning("Kafka error: %s", msg.error())

                # ── Flush triggers ────────────────────────────────────────
                for topic, buf in list(self.buffer.items()):
                    if len(buf) >= self.batch_size:
                        self._flush_topic(topic)

                if time.time() - self.last_flush > self.flush_interval:
                    self._flush_all()

        finally:
            logger.info("GCS Sink: flushing remaining buffers before shutdown.")
            self._flush_all()
            consumer.close()
            logger.info("GCS Sink stopped.")


# ═══════════════════════════════════════════════════════════════════════════
# Direction A: GCS → Kafka  (seeder / replayer)
# ═══════════════════════════════════════════════════════════════════════════

class GCSKafkaSeeder:
    """
    Reads JSONL archive files from GCS and produces their messages back
    into Kafka topics — enabling backfill, replay, or fresh-cluster seeding.

    Environment variables:
        KAFKA_HOST          Kafka broker
        GCS_BUCKET_NAME     Source GCS bucket
        GCS_ARCHIVE_PREFIX  Archive prefix (default: archive)
    """

    def __init__(self):
        self.bootstrap = _bootstrap()
        self.bucket = gcs_creds.get_bucket()
        self.prefix = _archive_prefix()

    # ── GCS listing ─────────────────────────────────────────────────────────

    def list_archived_topics(self) -> List[str]:
        """Return the list of topics that have archived data in GCS."""
        blobs = self.bucket.list_blobs(prefix=self.prefix + "/", delimiter="/")
        # Force iteration to populate blobs.prefixes
        _ = list(blobs)
        return sorted(
            p.replace(self.prefix + "/", "").rstrip("/")
            for p in (blobs.prefixes or [])
        )

    def list_archived_files(
        self,
        topic: str,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        latest_n: Optional[int] = None,
    ) -> list:
        """
        Return sorted list of GCS Blob objects for a topic,
        optionally filtered by date range and/or capped to latest N files.
        """
        prefix = f"{self.prefix}/{topic}/"
        blobs = sorted(
            self.bucket.list_blobs(prefix=prefix),
            key=lambda b: b.name,
        )

        if date_from or date_to:
            blobs = [b for b in blobs if self._blob_in_range(b.name, date_from, date_to)]

        if latest_n:
            blobs = blobs[-latest_n:]

        return blobs

    @staticmethod
    def _blob_in_range(
        blob_name: str,
        date_from: Optional[str],
        date_to: Optional[str],
    ) -> bool:
        """True if the blob's encoded date falls within [date_from, date_to]."""
        match = re.search(r"year=(\d+)/month=(\d+)/day=(\d+)", blob_name)
        if not match:
            return True
        blob_date = (
            f"{match.group(1)}-"
            f"{match.group(2).zfill(2)}-"
            f"{match.group(3).zfill(2)}"
        )
        if date_from and blob_date < date_from:
            return False
        if date_to and blob_date > date_to:
            return False
        return True

    # ── Replay ──────────────────────────────────────────────────────────────

    def replay_topic(
        self,
        topic: str,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        latest_n: Optional[int] = None,
        target_topic: Optional[str] = None,
    ) -> int:
        """
        Replay archived messages for *topic* back into Kafka.

        Args:
            topic:        Source archive topic name.
            date_from:    ISO date string "YYYY-MM-DD" — skip blobs before this date.
            date_to:      ISO date string "YYYY-MM-DD" — skip blobs after this date.
            latest_n:     Only replay the N most recent archive files.
            target_topic: Destination Kafka topic (defaults to source topic name).

        Returns:
            Total number of messages produced.
        """
        if not _CONFLUENT_AVAILABLE:
            raise RuntimeError(
                "confluent-kafka is required for GCSKafkaSeeder. "
                "Install with: pip install confluent-kafka"
            )

        dest = target_topic or topic
        blobs = self.list_archived_files(topic, date_from, date_to, latest_n)

        if not blobs:
            logger.warning("No archived files found for topic '%s' with given filters.", topic)
            return 0

        producer = Producer({"bootstrap.servers": self.bootstrap})
        _STRIP_KEYS = {
            "_kafka_topic", "_kafka_offset", "_kafka_partition", "_archived_at"
        }
        total = 0

        for blob in blobs:
            try:
                content = blob.download_as_text()
            except Exception as exc:
                logger.error("Failed to download %s: %s", blob.name, exc)
                continue

            for line in content.strip().splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                    for k in _STRIP_KEYS:
                        record.pop(k, None)
                    producer.produce(
                        dest,
                        value=json.dumps(record, default=str).encode("utf-8"),
                    )
                    total += 1
                except json.JSONDecodeError as exc:
                    logger.debug("Skipping malformed line in %s: %s", blob.name, exc)

            producer.flush()
            logger.info("GCS Seeder: replayed %s → '%s'", blob.name, dest)

        logger.info(
            "GCS Seeder: finished — %d messages produced to topic '%s'.", total, dest
        )
        return total


# ═══════════════════════════════════════════════════════════════════════════
# CLI entry point
# ═══════════════════════════════════════════════════════════════════════════

def _build_parser():
    import argparse

    parser = argparse.ArgumentParser(
        description="GCS ↔ Kafka Bridge — bidirectional archive/replay tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Archive all Kafka topics to GCS (runs forever):
  python gcs_kafka_bridge.py sink

  # Replay a full topic from GCS into Kafka:
  python gcs_kafka_bridge.py seed --topic BTCUSDT

  # Replay only a date range:
  python gcs_kafka_bridge.py seed --topic BTCUSDT --from 2026-01-01 --to 2026-02-28

  # Replay the 5 most recent archive files into an alternate topic:
  python gcs_kafka_bridge.py seed --topic BTCUSDT --latest-n 5 --target BTCUSDT.replay

  # List topics that have archived data:
  python gcs_kafka_bridge.py list

  # Verify GCS credentials and bucket connectivity:
  python gcs_kafka_bridge.py health
""",
    )
    sub = parser.add_subparsers(dest="command", metavar="COMMAND")

    # ── sink ────────────────────────────────────────────────────────────────
    sub.add_parser("sink", help="Start Kafka → GCS archiver (runs until interrupted)")

    # ── seed ────────────────────────────────────────────────────────────────
    seed_p = sub.add_parser("seed", help="Replay archived GCS data → Kafka")
    seed_p.add_argument("--topic", required=True, help="Source archive topic name")
    seed_p.add_argument(
        "--from", dest="date_from", default=None, metavar="YYYY-MM-DD",
        help="Replay from this date (inclusive)"
    )
    seed_p.add_argument(
        "--to", dest="date_to", default=None, metavar="YYYY-MM-DD",
        help="Replay up to this date (inclusive)"
    )
    seed_p.add_argument(
        "--latest-n", dest="latest_n", type=int, default=None,
        help="Only replay the N most recent archive files"
    )
    seed_p.add_argument(
        "--target", dest="target", default=None,
        help="Destination Kafka topic (defaults to source topic)"
    )

    # ── list ────────────────────────────────────────────────────────────────
    sub.add_parser("list", help="List archived topics in GCS")

    # ── health ──────────────────────────────────────────────────────────────
    sub.add_parser("health", help="Verify GCS credentials and bucket connectivity")

    return parser


def main():
    parser = _build_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    if args.command == "sink":
        sink = GCSKafkaSink()
        sink.run()

    elif args.command == "seed":
        seeder = GCSKafkaSeeder()
        count = seeder.replay_topic(
            topic=args.topic,
            date_from=args.date_from,
            date_to=args.date_to,
            latest_n=args.latest_n,
            target_topic=args.target,
        )
        print(f"Replayed {count} messages from GCS → Kafka topic '{args.target or args.topic}'")

    elif args.command == "list":
        seeder = GCSKafkaSeeder()
        topics = seeder.list_archived_topics()
        if topics:
            print("Archived topics in GCS:")
            for t in topics:
                print(f"  - {t}")
        else:
            print("No archived topics found in GCS bucket.")

    elif args.command == "health":
        result = gcs_creds.health_check()
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
