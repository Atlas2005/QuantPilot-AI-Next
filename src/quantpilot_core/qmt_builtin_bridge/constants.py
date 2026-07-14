"""Versioned constants and conservative bounds for the QMT filesystem bridge."""

from __future__ import annotations

from pathlib import Path


SCHEMA_VERSION = 1
BRIDGE_VERSION = "qmt_builtin_readonly_bridge_v1"
PROVIDER_ID = "qmt_builtin_bridge"
ENVIRONMENT_ID = "simulation_signal"

LATEST_SNAPSHOT_RELATIVE_PATH = Path("snapshots") / "latest_snapshot_v1.json"
TEMP_SNAPSHOT_RELATIVE_PATH = Path("snapshots") / "latest_snapshot_v1.json.tmp"

QUERY_SECTIONS = ("account", "positions", "orders", "trades")

MAX_SNAPSHOT_BYTES = 8 * 1024 * 1024
MAX_TEXT_LENGTH = 512
MAX_ERROR_MESSAGE_LENGTH = 512
MAX_METADATA_ENTRIES = 32
MAX_METADATA_KEY_LENGTH = 80
MAX_METADATA_TEXT_LENGTH = 256
MAX_POSITIONS = 5_000
MAX_ORDERS = 5_000
MAX_TRADES = 5_000
MAX_FAILURES = len(QUERY_SECTIONS)
MAX_PROVENANCE_FIELDS = 64
MAX_PROVENANCE_SOURCES = 8
MAX_FUTURE_SKEW_SECONDS = 300.0
