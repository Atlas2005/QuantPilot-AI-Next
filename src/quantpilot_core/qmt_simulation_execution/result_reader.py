"""Bounded, read-only inspection of intent, state, and acknowledgement files."""

from __future__ import annotations

import hmac
from datetime import datetime
from pathlib import Path
from typing import Any

from ._atomic import read_bounded_file
from .account_binding import load_account_binding_key
from .canonical import decode_json_object
from .constants import MAX_INTENT_BYTES, MAX_RESULT_BYTES, MAX_STATE_BYTES
from .contracts import (
    QmtSimulationOrderIntent,
    QmtSimulationOrderResult,
    QmtSimulationOrderState,
)
from .errors import (
    InvalidIntentError,
    InvalidResultError,
    InvalidStateError,
    MissingIntentError,
    MissingResultError,
    MissingStateError,
)
from .paths import (
    intent_path,
    reject_repository_local_bridge_root,
    result_path,
    state_path,
)
from .validation import (
    format_utc_timestamp,
    intent_from_mapping,
    result_from_mapping,
    serialize_intent,
    serialize_result,
    serialize_state,
    state_from_mapping,
)


def read_intent(
    bridge_root: str | Path,
    intent_id: str,
    *,
    binding_key: object | None = None,
    now: datetime | None = None,
    expected_redacted_account_id: str | None = None,
    actual_redacted_account_id: str | None = None,
    raw_account_id: object | None = None,
    repository_root: str | Path | None = None,
    require_canonical: bool = True,
    allow_expired: bool = False,
) -> QmtSimulationOrderIntent:
    root = reject_repository_local_bridge_root(
        bridge_root,
        repository_root=repository_root,
    )
    path = intent_path(root, intent_id)
    raw = read_bounded_file(
        path,
        maximum=MAX_INTENT_BYTES,
        missing_error=MissingIntentError,
        invalid_error=InvalidIntentError,
    )
    payload = decode_json_object(raw, path=path)
    key = binding_key if binding_key is not None else load_account_binding_key(root)
    intent = intent_from_mapping(
        payload,
        binding_key=key,
        now=now,
        expected_redacted_account_id=expected_redacted_account_id,
        actual_redacted_account_id=actual_redacted_account_id,
        raw_account_id=raw_account_id,
        source_path=path,
        allow_expired=allow_expired,
    )
    if require_canonical and raw != serialize_intent(intent):
        raise InvalidIntentError("intent file is not canonical JSON", path=path)
    return intent


def read_state(
    bridge_root: str | Path,
    intent_id: str,
    *,
    expected_redacted_account_id: str | None = None,
    binding_key: object | None = None,
    repository_root: str | Path | None = None,
    require_canonical: bool = True,
) -> QmtSimulationOrderState:
    root = reject_repository_local_bridge_root(
        bridge_root,
        repository_root=repository_root,
    )
    path = state_path(root, intent_id)
    raw = read_bounded_file(
        path,
        maximum=MAX_STATE_BYTES,
        missing_error=MissingStateError,
        invalid_error=InvalidStateError,
    )
    payload = decode_json_object(raw, path=path)
    state = state_from_mapping(
        payload,
        expected_intent_id=intent_id,
        expected_redacted_account_id=expected_redacted_account_id,
        source_path=path,
    )
    if require_canonical and raw != serialize_state(state):
        raise InvalidStateError("state file is not canonical JSON", path=path)
    intent = read_intent(
        root,
        intent_id,
        binding_key=binding_key,
        now=state.updated_at,
        expected_redacted_account_id=state.expected_redacted_account_id,
        allow_expired=True,
    )
    if state.updated_at < intent.created_at:
        raise InvalidStateError("state predates its authenticated intent", path=path)
    return state


def read_result(
    bridge_root: str | Path,
    intent_id: str,
    *,
    expected_redacted_account_id: str | None = None,
    binding_key: object | None = None,
    repository_root: str | Path | None = None,
    require_canonical: bool = True,
) -> QmtSimulationOrderResult:
    root = reject_repository_local_bridge_root(
        bridge_root,
        repository_root=repository_root,
    )
    path = result_path(root, intent_id)
    raw = read_bounded_file(
        path,
        maximum=MAX_RESULT_BYTES,
        missing_error=MissingResultError,
        invalid_error=InvalidResultError,
    )
    payload = decode_json_object(raw, path=path)
    result = result_from_mapping(
        payload,
        expected_intent_id=intent_id,
        expected_redacted_account_id=expected_redacted_account_id,
        source_path=path,
    )
    if require_canonical and raw != serialize_result(result):
        raise InvalidResultError("result file is not canonical JSON", path=path)
    intent = read_intent(
        root,
        intent_id,
        binding_key=binding_key,
        now=result.generated_at,
        expected_redacted_account_id=result.expected_redacted_account_id,
        allow_expired=True,
    )
    if result.generated_at < intent.created_at:
        raise InvalidResultError("result predates its authenticated intent", path=path)
    if (
        result.symbol != intent.symbol
        or result.side != intent.side
        or result.requested_quantity != intent.quantity
        or result.limit_price != intent.limit_price
        or not hmac.compare_digest(
            result.expected_redacted_account_id,
            intent.expected_redacted_account_id,
        )
    ):
        raise InvalidResultError(
            "result does not match its authenticated intent", path=path
        )
    return result


def inspect_status(
    bridge_root: str | Path,
    intent_id: str,
    *,
    expected_redacted_account_id: str | None = None,
    binding_key: object | None = None,
    now: datetime | None = None,
    repository_root: str | Path | None = None,
) -> dict[str, Any]:
    """Return a bounded display mapping without mutating files or exposing account data."""

    try:
        result = read_result(
            bridge_root,
            intent_id,
            expected_redacted_account_id=expected_redacted_account_id,
            binding_key=binding_key,
            repository_root=repository_root,
        )
    except MissingResultError:
        pass
    else:
        return {
            "source": "acknowledgement",
            "intent_id": result.intent_id,
            "status": result.status,
            "generated_at": format_utc_timestamp(result.generated_at),
            "passorder_attempted": result.passorder_attempted,
            "requested_quantity": result.requested_quantity,
            "filled_quantity": result.filled_quantity,
            "average_fill_price": result.average_fill_price,
            "failure_code": result.failure_code,
        }
    try:
        state = read_state(
            bridge_root,
            intent_id,
            expected_redacted_account_id=expected_redacted_account_id,
            binding_key=binding_key,
            repository_root=repository_root,
        )
    except MissingStateError:
        intent = read_intent(
            bridge_root,
            intent_id,
            binding_key=binding_key,
            now=now,
            expected_redacted_account_id=expected_redacted_account_id,
            repository_root=repository_root,
        )
        return {
            "source": "intent",
            "intent_id": intent.intent_id,
            "status": "received",
            "created_at": format_utc_timestamp(intent.created_at),
            "expires_at": format_utc_timestamp(intent.expires_at),
            "passorder_attempted": False,
            "requested_quantity": intent.quantity,
            "filled_quantity": 0,
            "failure_code": None,
        }
    return {
        "source": "state",
        "intent_id": state.intent_id,
        "status": state.status,
        "updated_at": format_utc_timestamp(state.updated_at),
        "passorder_attempted": state.passorder_attempted,
        "failure_code": state.failure_code,
    }


inspect_order_status = inspect_status
