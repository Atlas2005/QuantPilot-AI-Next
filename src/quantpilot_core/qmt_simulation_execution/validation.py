"""Strict validation, canonical serialization, and intent authentication."""

from __future__ import annotations

import hashlib
import hmac
import math
import re
from collections.abc import Mapping
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, NoReturn

from .account_binding import (
    is_redacted_account_binding,
    validate_account_binding_key,
    verify_account_binding,
)
from .canonical import canonical_json_bytes
from .constants import (
    ACCEPTANCE_LIMITATION,
    ACCOUNT_TYPE,
    ENVIRONMENT,
    INTENT_HMAC_DOMAIN,
    INTENT_OPTIONAL_KEYS,
    INTENT_REQUIRED_KEYS,
    MAX_BROKER_REFERENCE_LENGTH,
    MAX_DEAL_RECORDS,
    MAX_FAILURE_CODE_LENGTH,
    MAX_FAILURE_TYPE_LENGTH,
    MAX_FUTURE_SKEW_SECONDS,
    MAX_INTENT_LIFETIME_SECONDS,
    MAX_LIMIT_PRICE,
    MAX_QUANTITY,
    MAX_RUN_LABEL_LENGTH,
    MAX_STATUS_TEXT_LENGTH,
    ORDER_KIND,
    PROTOCOL_VERSION,
    RESULT_KEYS,
    SAFE_BROKER_STATUS_TEXT,
    SCHEMA_VERSION,
    STATE_KEYS,
    STATUSES,
    STRATEGY_NAME,
)
from .contracts import (
    CodeValue,
    QmtSimulationOrderIntent,
    QmtSimulationOrderResult,
    QmtSimulationOrderState,
)
from .errors import (
    AccountBindingMismatchError,
    ExpiredIntentError,
    FutureIntentError,
    IntentAuthenticationError,
    InvalidIntentError,
    InvalidResultError,
    InvalidStateError,
    UnsupportedProtocolError,
)
from .paths import reject_repository_local_artifact_path, validate_intent_id


_UTC_TIMESTAMP_PATTERN = re.compile(r"\A\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z\Z")
_SYMBOL_PATTERN = re.compile(r"\A[0-9]{6}\.(?:SH|SZ|BJ)\Z")
_LOWER_HEX_64_PATTERN = re.compile(r"\A[0-9a-f]{64}\Z")
_FAILURE_CODE_PATTERN = re.compile(r"\A[a-z][a-z0-9_]{0,79}\Z")
_FAILURE_TYPE_PATTERN = re.compile(r"\A[A-Za-z_][A-Za-z0-9_.]{0,127}\Z")


def format_utc_timestamp(value: datetime) -> str:
    """Format an aware timestamp at the protocol's exact second precision."""

    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware")
    normalized = value.astimezone(timezone.utc).replace(microsecond=0)
    return normalized.strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_utc_timestamp(value: object, field: str, *, error_type: type[Exception]) -> datetime:
    if not isinstance(value, str) or _UTC_TIMESTAMP_PATTERN.fullmatch(value) is None:
        raise error_type(f"{field} must be an exact UTC timestamp")
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise error_type(f"{field} must be an exact UTC timestamp") from exc


def unsigned_intent_mapping(intent: QmtSimulationOrderIntent) -> dict[str, Any]:
    payload = intent_to_mapping(intent)
    del payload["intent_hmac"]
    return payload


def intent_to_mapping(intent: QmtSimulationOrderIntent) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": intent.schema_version,
        "protocol_version": intent.protocol_version,
        "intent_id": intent.intent_id,
        "created_at": format_utc_timestamp(intent.created_at),
        "expires_at": format_utc_timestamp(intent.expires_at),
        "environment": intent.environment,
        "expected_redacted_account_id": intent.expected_redacted_account_id,
        "account_type": intent.account_type,
        "symbol": intent.symbol,
        "side": intent.side,
        "quantity": intent.quantity,
        "order_kind": intent.order_kind,
        "limit_price": intent.limit_price,
        "source_order_digest": intent.source_order_digest,
        "explicit_submit": intent.explicit_submit,
        "intent_hmac": intent.intent_hmac,
    }
    if intent.run_label is not None:
        payload["run_label"] = intent.run_label
    return payload


def state_to_mapping(state: QmtSimulationOrderState) -> dict[str, Any]:
    return {
        "schema_version": state.schema_version,
        "protocol_version": state.protocol_version,
        "intent_id": state.intent_id,
        "updated_at": format_utc_timestamp(state.updated_at),
        "status": state.status,
        "expected_redacted_account_id": state.expected_redacted_account_id,
        "passorder_attempted": state.passorder_attempted,
        "failure_code": state.failure_code,
    }


def result_to_mapping(result: QmtSimulationOrderResult) -> dict[str, Any]:
    return {
        "schema_version": result.schema_version,
        "protocol_version": result.protocol_version,
        "intent_id": result.intent_id,
        "generated_at": format_utc_timestamp(result.generated_at),
        "status": result.status,
        "expected_redacted_account_id": result.expected_redacted_account_id,
        "symbol": result.symbol,
        "side": result.side,
        "requested_quantity": result.requested_quantity,
        "limit_price": result.limit_price,
        "strategy_name": result.strategy_name,
        "user_order_id": result.user_order_id,
        "passorder_attempted": result.passorder_attempted,
        "broker_order_reference": result.broker_order_reference,
        "system_order_id": result.system_order_id,
        "order_status": result.order_status,
        "submission_status": result.submission_status,
        "filled_quantity": result.filled_quantity,
        "average_fill_price": result.average_fill_price,
        "deal_count": result.deal_count,
        "failure_code": result.failure_code,
        "failure_type": result.failure_type,
        "latest_snapshot_sequence": result.latest_snapshot_sequence,
        "acceptance_limitation": result.acceptance_limitation,
    }


def calculate_intent_hmac(unsigned_payload: Mapping[str, Any], *, binding_key: object) -> str:
    """Authenticate the exact canonical representation excluding ``intent_hmac``."""

    if "intent_hmac" in unsigned_payload:
        raise InvalidIntentError("unsigned intent payload must omit intent_hmac")
    key = validate_account_binding_key(binding_key)
    canonical = canonical_json_bytes(unsigned_payload)
    return hmac.new(key, INTENT_HMAC_DOMAIN + canonical, hashlib.sha256).hexdigest()


def verify_intent_hmac(intent: QmtSimulationOrderIntent, *, binding_key: object) -> None:
    if _LOWER_HEX_64_PATTERN.fullmatch(intent.intent_hmac) is None:
        raise IntentAuthenticationError("intent authentication is malformed")
    expected = calculate_intent_hmac(unsigned_intent_mapping(intent), binding_key=binding_key)
    if not hmac.compare_digest(expected, intent.intent_hmac):
        raise IntentAuthenticationError("intent authentication failed")


def serialize_intent(intent: QmtSimulationOrderIntent) -> bytes:
    return canonical_json_bytes(intent_to_mapping(intent), trailing_newline=True)


def serialize_state(state: QmtSimulationOrderState) -> bytes:
    return canonical_json_bytes(state_to_mapping(state), trailing_newline=True)


def serialize_result(result: QmtSimulationOrderResult) -> bytes:
    return canonical_json_bytes(result_to_mapping(result), trailing_newline=True)


def intent_from_mapping(
    payload: object,
    *,
    binding_key: object,
    now: datetime | None = None,
    expected_redacted_account_id: str | None = None,
    actual_redacted_account_id: str | None = None,
    raw_account_id: object | None = None,
    source_path: str | Path | None = None,
    allow_expired: bool = False,
) -> QmtSimulationOrderIntent:
    """Validate every v1 field, HMAC, expiry, and optional account binding."""

    if not isinstance(allow_expired, bool):
        raise TypeError("allow_expired must be a boolean")
    if source_path is not None:
        reject_repository_local_artifact_path(source_path)
    root = _exact_intent_object(payload)
    _protocol(root, error="intent")
    intent_id = validate_intent_id(root["intent_id"])
    created_at = parse_utc_timestamp(root["created_at"], "created_at", error_type=InvalidIntentError)
    expires_at = parse_utc_timestamp(root["expires_at"], "expires_at", error_type=InvalidIntentError)
    clock = _aware_now(now)
    if created_at > clock + timedelta(seconds=MAX_FUTURE_SKEW_SECONDS):
        raise FutureIntentError("intent creation time is too far in the future", path=source_path)
    if expires_at <= clock and not allow_expired:
        raise ExpiredIntentError("intent has expired", path=source_path)
    lifetime = (expires_at - created_at).total_seconds()
    if lifetime <= 0 or lifetime > MAX_INTENT_LIFETIME_SECONDS:
        _invalid_intent("intent validity window is outside protocol bounds", source_path)

    environment = _exact_string(root["environment"], "environment", maximum=32)
    if environment != ENVIRONMENT:
        _invalid_intent("intent environment is unsupported", source_path)
    account_type = _exact_string(root["account_type"], "account_type", maximum=16)
    if account_type != ACCOUNT_TYPE:
        _invalid_intent("intent account type is unsupported", source_path)
    account_binding = _exact_string(
        root["expected_redacted_account_id"],
        "expected_redacted_account_id",
        maximum=64,
    )
    if not is_redacted_account_binding(account_binding):
        _invalid_intent("intent account binding is malformed", source_path)
    if expected_redacted_account_id is not None:
        try:
            verify_account_binding(
                account_binding,
                actual_redacted_account_id=expected_redacted_account_id,
            )
        except AccountBindingMismatchError as exc:
            raise AccountBindingMismatchError(str(exc), path=source_path) from None
    if actual_redacted_account_id is not None and raw_account_id is not None:
        raise AccountBindingMismatchError(
            "provide only one selected account identity representation", path=source_path
        )
    if actual_redacted_account_id is not None or raw_account_id is not None:
        try:
            if raw_account_id is not None:
                verify_account_binding(
                    account_binding,
                    raw_account_id=raw_account_id,
                    binding_key=binding_key,
                )
            else:
                verify_account_binding(
                    account_binding,
                    actual_redacted_account_id=actual_redacted_account_id,
                )
        except AccountBindingMismatchError as exc:
            raise AccountBindingMismatchError(str(exc), path=source_path) from None

    symbol = _symbol(root["symbol"], error_type=InvalidIntentError)
    side = _side(root["side"], error_type=InvalidIntentError)
    quantity = _quantity(root["quantity"], "quantity", error_type=InvalidIntentError, positive=True)
    if side == "buy" and quantity % 100:
        _invalid_intent("buy quantity must be divisible by 100", source_path)
    order_kind = _exact_string(root["order_kind"], "order_kind", maximum=32)
    if order_kind != ORDER_KIND:
        _invalid_intent("intent order kind is unsupported", source_path)
    limit_price = _positive_price(root["limit_price"], "limit_price", InvalidIntentError)
    source_order_digest = _exact_string(
        root["source_order_digest"], "source_order_digest", maximum=64
    )
    if _LOWER_HEX_64_PATTERN.fullmatch(source_order_digest) is None:
        _invalid_intent("source order digest is malformed", source_path)
    if root["explicit_submit"] is not True:
        _invalid_intent("explicit_submit must be exactly true", source_path)
    intent_hmac = _exact_string(root["intent_hmac"], "intent_hmac", maximum=64)
    run_label = None
    if "run_label" in root:
        run_label = _optional_bounded_text(
            root["run_label"],
            "run_label",
            maximum=MAX_RUN_LABEL_LENGTH,
            error_type=InvalidIntentError,
            allow_none=False,
        )

    intent = QmtSimulationOrderIntent(
        schema_version=SCHEMA_VERSION,
        protocol_version=PROTOCOL_VERSION,
        intent_id=intent_id,
        created_at=created_at,
        expires_at=expires_at,
        environment=environment,
        expected_redacted_account_id=account_binding,
        account_type=account_type,
        symbol=symbol,
        side=side,
        quantity=quantity,
        order_kind=order_kind,
        limit_price=limit_price,
        source_order_digest=source_order_digest,
        explicit_submit=True,
        intent_hmac=intent_hmac,
        run_label=run_label,
        source_path=Path(source_path) if source_path is not None else None,
    )
    verify_intent_hmac(intent, binding_key=binding_key)
    return intent


def state_from_mapping(
    payload: object,
    *,
    expected_intent_id: str | None = None,
    expected_redacted_account_id: str | None = None,
    source_path: str | Path | None = None,
) -> QmtSimulationOrderState:
    root = _exact_object(payload, STATE_KEYS, InvalidStateError, "state")
    _protocol(root, error="state")
    try:
        intent_id = validate_intent_id(root["intent_id"])
    except InvalidIntentError as exc:
        raise InvalidStateError("state intent_id is malformed", path=source_path) from exc
    if expected_intent_id is not None and intent_id != validate_intent_id(expected_intent_id):
        raise InvalidStateError("state identity does not match requested intent", path=source_path)
    updated_at = parse_utc_timestamp(root["updated_at"], "updated_at", error_type=InvalidStateError)
    status = _status(root["status"], InvalidStateError)
    binding = _account_binding(root["expected_redacted_account_id"], InvalidStateError)
    if expected_redacted_account_id is not None:
        _compare_binding(binding, expected_redacted_account_id, InvalidStateError, source_path)
    attempted = _strict_bool(root["passorder_attempted"], "passorder_attempted", InvalidStateError)
    if status in {"received", "claimed", "expired"} and attempted:
        raise InvalidStateError("pre-submission state cannot contain attempt evidence", path=source_path)
    if status == "submission_attempted" and not attempted:
        raise InvalidStateError("state status requires submission attempt evidence", path=source_path)
    failure_code = _failure_code(root["failure_code"], InvalidStateError)
    return QmtSimulationOrderState(
        schema_version=SCHEMA_VERSION,
        protocol_version=PROTOCOL_VERSION,
        intent_id=intent_id,
        updated_at=updated_at,
        status=status,
        expected_redacted_account_id=binding,
        passorder_attempted=attempted,
        failure_code=failure_code,
        source_path=Path(source_path) if source_path is not None else None,
    )


def result_from_mapping(
    payload: object,
    *,
    expected_intent_id: str | None = None,
    expected_redacted_account_id: str | None = None,
    source_path: str | Path | None = None,
) -> QmtSimulationOrderResult:
    root = _exact_object(payload, RESULT_KEYS, InvalidResultError, "result")
    _protocol(root, error="result")
    try:
        intent_id = validate_intent_id(root["intent_id"])
    except InvalidIntentError as exc:
        raise InvalidResultError("result intent_id is malformed", path=source_path) from exc
    if expected_intent_id is not None and intent_id != validate_intent_id(expected_intent_id):
        raise InvalidResultError("result identity does not match requested intent", path=source_path)
    generated_at = parse_utc_timestamp(
        root["generated_at"], "generated_at", error_type=InvalidResultError
    )
    status = _status(root["status"], InvalidResultError)
    binding = _account_binding(root["expected_redacted_account_id"], InvalidResultError)
    if expected_redacted_account_id is not None:
        _compare_binding(binding, expected_redacted_account_id, InvalidResultError, source_path)
    symbol = _symbol(root["symbol"], error_type=InvalidResultError)
    side = _side(root["side"], error_type=InvalidResultError)
    requested = _quantity(
        root["requested_quantity"],
        "requested_quantity",
        error_type=InvalidResultError,
        positive=True,
    )
    if side == "buy" and requested % 100:
        raise InvalidResultError("result buy quantity must be divisible by 100", path=source_path)
    limit_price = _positive_price(root["limit_price"], "limit_price", InvalidResultError)
    strategy = _exact_string(
        root["strategy_name"],
        "strategy_name",
        maximum=64,
        error_type=InvalidResultError,
    )
    if strategy != STRATEGY_NAME:
        raise InvalidResultError("result strategy is unsupported", path=source_path)
    user_order_id = _exact_string(
        root["user_order_id"],
        "user_order_id",
        maximum=64,
        error_type=InvalidResultError,
    )
    if user_order_id != intent_id:
        raise InvalidResultError("result user order identity is inconsistent", path=source_path)
    attempted = _strict_bool(root["passorder_attempted"], "passorder_attempted", InvalidResultError)
    broker_ref = _bounded_optional_string(
        root["broker_order_reference"],
        "broker_order_reference",
        MAX_BROKER_REFERENCE_LENGTH,
        InvalidResultError,
    )
    system_order_id = _bounded_optional_string(
        root["system_order_id"],
        "system_order_id",
        MAX_BROKER_REFERENCE_LENGTH,
        InvalidResultError,
    )
    order_status = _code(root["order_status"], "order_status", InvalidResultError)
    submission_status = _code(
        root["submission_status"], "submission_status", InvalidResultError
    )
    filled = _quantity(
        root["filled_quantity"],
        "filled_quantity",
        error_type=InvalidResultError,
        positive=False,
    )
    if filled > requested:
        raise InvalidResultError("result fill quantity exceeds request", path=source_path)
    average = _optional_positive_price(
        root["average_fill_price"], "average_fill_price", InvalidResultError
    )
    deal_count = _quantity(
        root["deal_count"], "deal_count", error_type=InvalidResultError, positive=False
    )
    if deal_count > MAX_DEAL_RECORDS:
        raise InvalidResultError("result deal_count exceeds protocol bounds", path=source_path)
    failure_code = _failure_code(root["failure_code"], InvalidResultError)
    failure_type = _failure_type(root["failure_type"], InvalidResultError)
    sequence = _optional_positive_int(
        root["latest_snapshot_sequence"],
        "latest_snapshot_sequence",
        InvalidResultError,
    )
    limitation = _exact_string(
        root["acceptance_limitation"],
        "acceptance_limitation",
        maximum=128,
        error_type=InvalidResultError,
    )
    if limitation != ACCEPTANCE_LIMITATION:
        raise InvalidResultError("result acceptance limitation is unsupported", path=source_path)

    if status == "submission_attempted" and not attempted:
        raise InvalidResultError("result status requires submission attempt evidence", path=source_path)
    if status in {"received", "claimed", "expired"} and attempted:
        raise InvalidResultError("pre-submission result cannot contain attempt evidence", path=source_path)
    order_observed = any(
        value is not None
        for value in (broker_ref, system_order_id, order_status, submission_status)
    )
    if status == "broker_acknowledged" and not order_observed:
        raise InvalidResultError("broker acknowledgement requires an order record", path=source_path)
    if status == "rejected" and (
        not order_observed or failure_code != "broker_order_rejected"
    ):
        raise InvalidResultError("rejected result requires explicit broker rejection evidence", path=source_path)
    if status == "partially_filled" and not (0 < filled < requested and deal_count > 0):
        raise InvalidResultError("partial fill requires bounded deal evidence", path=source_path)
    if status == "filled" and not (filled == requested and deal_count > 0):
        raise InvalidResultError("filled result requires complete deal evidence", path=source_path)
    if filled > 0 and (deal_count <= 0 or average is None):
        raise InvalidResultError("positive fill requires priced deal evidence", path=source_path)
    if filled == 0 and average is not None:
        raise InvalidResultError("zero fill cannot have an average fill price", path=source_path)

    return QmtSimulationOrderResult(
        schema_version=SCHEMA_VERSION,
        protocol_version=PROTOCOL_VERSION,
        intent_id=intent_id,
        generated_at=generated_at,
        status=status,
        expected_redacted_account_id=binding,
        symbol=symbol,
        side=side,
        requested_quantity=requested,
        limit_price=limit_price,
        strategy_name=strategy,
        user_order_id=user_order_id,
        passorder_attempted=attempted,
        broker_order_reference=broker_ref,
        system_order_id=system_order_id,
        order_status=order_status,
        submission_status=submission_status,
        filled_quantity=filled,
        average_fill_price=average,
        deal_count=deal_count,
        failure_code=failure_code,
        failure_type=failure_type,
        latest_snapshot_sequence=sequence,
        acceptance_limitation=limitation,
        source_path=Path(source_path) if source_path is not None else None,
    )


def _exact_intent_object(payload: object) -> Mapping[str, Any]:
    if not isinstance(payload, dict):
        raise InvalidIntentError("intent root must be a JSON object")
    keys = frozenset(payload)
    if not INTENT_REQUIRED_KEYS.issubset(keys) or not keys.issubset(
        INTENT_REQUIRED_KEYS | INTENT_OPTIONAL_KEYS
    ):
        raise InvalidIntentError("intent does not match the v1 protocol fields")
    return payload


def _exact_object(
    payload: object,
    keys: frozenset[str],
    error_type: type[Exception],
    label: str,
) -> Mapping[str, Any]:
    if not isinstance(payload, dict) or frozenset(payload) != keys:
        raise error_type(f"{label} does not match the v1 protocol fields")
    return payload


def _protocol(root: Mapping[str, Any], *, error: str) -> None:
    version = root.get("schema_version")
    protocol = root.get("protocol_version")
    if isinstance(version, bool) or not isinstance(version, int):
        raise UnsupportedProtocolError(f"{error} schema version is unsupported")
    if version != SCHEMA_VERSION or protocol != PROTOCOL_VERSION:
        raise UnsupportedProtocolError(f"{error} protocol version is unsupported")


def _aware_now(value: datetime | None) -> datetime:
    now = value or datetime.now(timezone.utc)
    if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    return now.astimezone(timezone.utc)


def _exact_string(
    value: object,
    field: str,
    *,
    maximum: int,
    error_type: type[Exception] = InvalidIntentError,
) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > maximum
        or "\x00" in value
        or "\r" in value
        or "\n" in value
    ):
        raise error_type(f"{field} must be a bounded non-empty string")
    return value


def _optional_bounded_text(
    value: object,
    field: str,
    *,
    maximum: int,
    error_type: type[Exception],
    allow_none: bool,
) -> str | None:
    if value is None and allow_none:
        return None
    if (
        not isinstance(value, str)
        or not value
        or len(value) > maximum
        or any(character in value for character in ("\x00", "\r", "\n"))
    ):
        raise error_type(f"{field} must be bounded text")
    return value


def _bounded_optional_string(
    value: object,
    field: str,
    maximum: int,
    error_type: type[Exception],
) -> str | None:
    if value is None:
        return None
    return _optional_bounded_text(
        value,
        field,
        maximum=maximum,
        error_type=error_type,
        allow_none=False,
    )


def _symbol(value: object, *, error_type: type[Exception]) -> str:
    if not isinstance(value, str) or _SYMBOL_PATTERN.fullmatch(value) is None:
        raise error_type("symbol must be canonical six-digit exchange-qualified text")
    return value


def _side(value: object, *, error_type: type[Exception]) -> str:
    if value not in {"buy", "sell"} or not isinstance(value, str):
        raise error_type("side must be buy or sell")
    return value


def _quantity(
    value: object,
    field: str,
    *,
    error_type: type[Exception],
    positive: bool,
) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise error_type(f"{field} must be an integer")
    minimum = 1 if positive else 0
    if value < minimum or value > MAX_QUANTITY:
        raise error_type(f"{field} is outside protocol bounds")
    return value


def _positive_price(value: object, field: str, error_type: type[Exception]) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise error_type(f"{field} must be numeric")
    try:
        converted = float(value)
    except (OverflowError, ValueError):
        raise error_type(f"{field} must be finite and positive") from None
    if not math.isfinite(converted) or converted <= 0 or converted > MAX_LIMIT_PRICE:
        raise error_type(f"{field} must be finite and positive")
    return converted


def _optional_positive_price(
    value: object, field: str, error_type: type[Exception]
) -> float | None:
    if value is None:
        return None
    return _positive_price(value, field, error_type)


def _strict_bool(value: object, field: str, error_type: type[Exception]) -> bool:
    if not isinstance(value, bool):
        raise error_type(f"{field} must be a boolean")
    return value


def _status(value: object, error_type: type[Exception]) -> str:
    if not isinstance(value, str) or value not in STATUSES:
        raise error_type("status is unsupported")
    return value


def _account_binding(value: object, error_type: type[Exception]) -> str:
    if not is_redacted_account_binding(value):
        raise error_type("account binding is malformed")
    return str(value)


def _compare_binding(
    actual: str,
    expected: str,
    error_type: type[Exception],
    source_path: str | Path | None,
) -> None:
    if not is_redacted_account_binding(expected) or not hmac.compare_digest(actual, expected):
        raise error_type("account binding does not match expectation", path=source_path)


def _failure_code(value: object, error_type: type[Exception]) -> str | None:
    if value is None:
        return None
    if (
        not isinstance(value, str)
        or len(value) > MAX_FAILURE_CODE_LENGTH
        or _FAILURE_CODE_PATTERN.fullmatch(value) is None
    ):
        raise error_type("failure_code is malformed")
    return value


def _failure_type(value: object, error_type: type[Exception]) -> str | None:
    if value is None:
        return None
    if (
        not isinstance(value, str)
        or len(value) > MAX_FAILURE_TYPE_LENGTH
        or _FAILURE_TYPE_PATTERN.fullmatch(value) is None
    ):
        raise error_type("failure_type is malformed")
    return value


def _code(value: object, field: str, error_type: type[Exception]) -> CodeValue:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise error_type(f"{field} must be null, text, or an integer")
    if isinstance(value, int) and not (-2_147_483_648 <= value <= 2_147_483_647):
        raise error_type(f"{field} integer is outside protocol bounds")
    if isinstance(value, str) and (
        not value
        or len(value) > MAX_STATUS_TEXT_LENGTH
        or any(character in value for character in ("\x00", "\r", "\n"))
    ):
        raise error_type(f"{field} text is outside protocol bounds")
    if isinstance(value, str) and value not in SAFE_BROKER_STATUS_TEXT:
        raise error_type(f"{field} text is not a fixed protocol status")
    return value


def _optional_positive_int(
    value: object, field: str, error_type: type[Exception]
) -> int | None:
    if value is None:
        return None
    parsed = _quantity(value, field, error_type=error_type, positive=True)
    return parsed


def _invalid_intent(message: str, source_path: str | Path | None) -> NoReturn:
    raise InvalidIntentError(message, path=source_path)
