"""Stable, non-sensitive failures for QMT simulation execution artifacts."""

from __future__ import annotations

from pathlib import Path


class QmtSimulationExecutionError(RuntimeError):
    """Base error with a stable public code and optional local path."""

    code = "qmt_simulation_execution_error"

    def __init__(self, message: str, *, path: str | Path | None = None) -> None:
        super().__init__(message)
        self.path = Path(path) if path is not None else None


class InvalidBridgeRootError(QmtSimulationExecutionError):
    code = "invalid_bridge_root"


class RepositoryLocalPathError(InvalidBridgeRootError):
    code = "repository_local_path"


class AccountBindingKeyError(QmtSimulationExecutionError):
    code = "invalid_account_binding_key"


class AccountBindingMismatchError(QmtSimulationExecutionError):
    code = "account_binding_mismatch"


class InvalidIntentError(QmtSimulationExecutionError):
    code = "invalid_intent"


class UnsupportedProtocolError(InvalidIntentError):
    code = "unsupported_protocol"


class IntentAuthenticationError(InvalidIntentError):
    code = "invalid_intent_hmac"


class ExpiredIntentError(InvalidIntentError):
    code = "expired_intent"


class FutureIntentError(InvalidIntentError):
    code = "future_intent"


class MissingIntentError(QmtSimulationExecutionError):
    code = "missing_intent"


class IntentConflictError(QmtSimulationExecutionError):
    code = "intent_conflict"


class AtomicWriteError(QmtSimulationExecutionError):
    code = "atomic_write_failed"


class MalformedArtifactError(QmtSimulationExecutionError):
    code = "malformed_artifact"


class InvalidStateError(QmtSimulationExecutionError):
    code = "invalid_state"


class InvalidStateTransitionError(InvalidStateError):
    code = "invalid_state_transition"


class MissingStateError(QmtSimulationExecutionError):
    code = "missing_state"


class MissingResultError(QmtSimulationExecutionError):
    code = "missing_result"


class InvalidResultError(QmtSimulationExecutionError):
    code = "invalid_result"


class BrokerEvidenceError(QmtSimulationExecutionError):
    code = "invalid_broker_evidence"
