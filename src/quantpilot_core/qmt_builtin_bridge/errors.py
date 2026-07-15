"""Narrow, machine-readable failures raised by the read-only QMT bridge."""

from __future__ import annotations

from pathlib import Path


class QmtBuiltinBridgeError(RuntimeError):
    """Base error with a stable public code and a non-sensitive message."""

    code = "qmt_builtin_bridge_error"

    def __init__(self, message: str, *, path: str | Path | None = None) -> None:
        super().__init__(message)
        self.path = Path(path) if path is not None else None


class MissingSnapshotError(QmtBuiltinBridgeError):
    code = "missing_snapshot"


class StaleSnapshotError(QmtBuiltinBridgeError):
    code = "stale_heartbeat"


class MalformedSnapshotError(QmtBuiltinBridgeError):
    code = "malformed_json"


class UnsupportedSchemaError(QmtBuiltinBridgeError):
    code = "unsupported_schema"


class IncompleteAtomicWriteError(QmtBuiltinBridgeError):
    code = "incomplete_atomic_write"


class InvalidSnapshotValueError(QmtBuiltinBridgeError):
    code = "invalid_values"


class AccountIdentityMismatchError(QmtBuiltinBridgeError):
    code = "account_identity_mismatch"


class SequenceError(QmtBuiltinBridgeError):
    """Base class for a completed snapshot that is not strictly newer."""


class DuplicateSequenceError(SequenceError):
    code = "duplicate_sequence"


class RegressingSequenceError(SequenceError):
    code = "regressing_sequence"


class ReadOnlyBridgeError(QmtBuiltinBridgeError):
    code = "read_only_bridge"


class OrderSubmissionNotEnabledError(ReadOnlyBridgeError):
    code = "order_submission_not_enabled"
