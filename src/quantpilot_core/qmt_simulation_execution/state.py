"""Atomic state/result publication and monotonic state transitions."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from ._atomic import write_replace_atomic
from .constants import (
    MAX_RESULT_BYTES,
    MAX_STATE_BYTES,
    PROTOCOL_VERSION,
    SCHEMA_VERSION,
)
from .contracts import QmtSimulationOrderResult, QmtSimulationOrderState
from .errors import InvalidStateTransitionError, MissingResultError, MissingStateError
from .paths import reject_repository_local_bridge_root, result_path, state_path
from .result_reader import read_intent, read_state
from .validation import (
    result_from_mapping,
    result_to_mapping,
    serialize_result,
    serialize_state,
    state_from_mapping,
    state_to_mapping,
)


_TRANSITIONS = {
    "received": frozenset({"received", "claimed", "expired", "rejected"}),
    "claimed": frozenset(
        {"claimed", "submission_attempted", "broker_acknowledged", "partially_filled", "filled", "rejected", "expired", "uncertain"}
    ),
    "submission_attempted": frozenset(
        {"submission_attempted", "uncertain", "broker_acknowledged", "partially_filled", "filled", "rejected"}
    ),
    "uncertain": frozenset(
        {"uncertain", "broker_acknowledged", "partially_filled", "filled", "rejected"}
    ),
    "broker_acknowledged": frozenset(
        {"broker_acknowledged", "partially_filled", "filled", "rejected"}
    ),
    "partially_filled": frozenset({"partially_filled", "filled"}),
    "filled": frozenset({"filled"}),
    "rejected": frozenset({"rejected"}),
    "expired": frozenset({"expired"}),
}

_RESULT_TRANSITIONS = {
    **_TRANSITIONS,
    "received": frozenset(
        {
            "received",
            "claimed",
            "submission_attempted",
            "uncertain",
            "broker_acknowledged",
            "partially_filled",
            "filled",
            "rejected",
            "expired",
        }
    ),
    "claimed": frozenset(
        {
            "claimed",
            "submission_attempted",
            "uncertain",
            "broker_acknowledged",
            "partially_filled",
            "filled",
            "rejected",
            "expired",
        }
    ),
}


def build_state(
    *,
    intent_id: str,
    expected_redacted_account_id: str,
    status: str,
    passorder_attempted: bool = False,
    failure_code: str | None = None,
    updated_at: datetime | None = None,
) -> QmtSimulationOrderState:
    payload = {
        "schema_version": SCHEMA_VERSION,
        "protocol_version": PROTOCOL_VERSION,
        "intent_id": intent_id,
        "updated_at": _timestamp(updated_at),
        "status": status,
        "expected_redacted_account_id": expected_redacted_account_id,
        "passorder_attempted": passorder_attempted,
        "failure_code": failure_code,
    }
    return state_from_mapping(payload)


def write_state_atomic(
    bridge_root: str | Path,
    state: QmtSimulationOrderState,
    *,
    repository_root: str | Path | None = None,
    binding_key: object | None = None,
) -> Path:
    root = reject_repository_local_bridge_root(
        bridge_root,
        repository_root=repository_root,
    )
    validated = state_from_mapping(state_to_mapping(state))
    intent = read_intent(
        root,
        validated.intent_id,
        binding_key=binding_key,
        now=validated.updated_at,
        expected_redacted_account_id=validated.expected_redacted_account_id,
        allow_expired=True,
    )
    if validated.updated_at < intent.created_at:
        raise InvalidStateTransitionError("state predates its authenticated intent")
    try:
        previous = read_state(
            root,
            validated.intent_id,
            expected_redacted_account_id=validated.expected_redacted_account_id,
            binding_key=binding_key,
        )
    except MissingStateError:
        previous = None
    if previous is not None:
        allowed = _TRANSITIONS[previous.status]
        if validated.status not in allowed:
            raise InvalidStateTransitionError("state transition would regress")
        if previous.passorder_attempted and not validated.passorder_attempted:
            raise InvalidStateTransitionError("submission attempt evidence cannot be cleared")
        if validated.updated_at < previous.updated_at:
            raise InvalidStateTransitionError("state timestamp would regress")
    return write_replace_atomic(
        state_path(root, validated.intent_id),
        serialize_state(validated),
        maximum=MAX_STATE_BYTES,
    )


def write_result_atomic(
    bridge_root: str | Path,
    result: QmtSimulationOrderResult,
    *,
    repository_root: str | Path | None = None,
    binding_key: object | None = None,
) -> Path:
    root = reject_repository_local_bridge_root(
        bridge_root,
        repository_root=repository_root,
    )
    validated = result_from_mapping(result_to_mapping(result))
    intent = read_intent(
        root,
        validated.intent_id,
        binding_key=binding_key,
        now=validated.generated_at,
        expected_redacted_account_id=validated.expected_redacted_account_id,
        allow_expired=True,
    )
    if (
        validated.generated_at < intent.created_at
        or validated.symbol != intent.symbol
        or validated.side != intent.side
        or validated.requested_quantity != intent.quantity
        or validated.limit_price != intent.limit_price
    ):
        from .errors import InvalidResultError

        raise InvalidResultError("result does not match its authenticated intent")
    from .result_reader import read_result

    try:
        previous = read_result(
            root,
            validated.intent_id,
            expected_redacted_account_id=validated.expected_redacted_account_id,
            binding_key=binding_key,
        )
    except MissingResultError:
        previous = None
    if previous is not None:
        allowed = _RESULT_TRANSITIONS[previous.status]
        if validated.status not in allowed:
            raise InvalidStateTransitionError("result transition would regress")
        if previous.passorder_attempted and not validated.passorder_attempted:
            raise InvalidStateTransitionError("result attempt evidence cannot be cleared")
        if validated.generated_at < previous.generated_at:
            raise InvalidStateTransitionError("result timestamp would regress")
        if validated.filled_quantity < previous.filled_quantity:
            raise InvalidStateTransitionError("result filled quantity would regress")
        if validated.deal_count < previous.deal_count:
            raise InvalidStateTransitionError("result deal evidence would regress")
        if (
            previous.broker_order_reference is not None
            and previous.broker_order_reference != validated.broker_order_reference
        ):
            raise InvalidStateTransitionError("result broker order identity changed or cleared")
        if (
            previous.system_order_id is not None
            and previous.system_order_id != validated.system_order_id
        ):
            raise InvalidStateTransitionError("result system order identity changed or cleared")
    return write_replace_atomic(
        result_path(root, validated.intent_id),
        serialize_result(validated),
        maximum=MAX_RESULT_BYTES,
    )


def _timestamp(value: datetime | None) -> str:
    from .validation import format_utc_timestamp

    return format_utc_timestamp(value or datetime.now(timezone.utc))
