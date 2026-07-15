"""Signed intent construction and immutable atomic publication."""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ._atomic import write_immutable_atomic
from .account_binding import load_account_binding_key
from .constants import (
    ACCOUNT_TYPE,
    ENVIRONMENT,
    MAX_INTENT_BYTES,
    MAX_INTENT_LIFETIME_SECONDS,
    MAX_LIMIT_PRICE,
    ORDER_KIND,
    PROTOCOL_VERSION,
    SCHEMA_VERSION,
)
from .contracts import QmtSimulationOrderIntent
from .errors import AccountBindingKeyError, InvalidIntentError
from .paths import intent_path, reject_repository_local_bridge_root
from .validation import (
    calculate_intent_hmac,
    format_utc_timestamp,
    intent_from_mapping,
    serialize_intent,
)


def build_signed_intent(
    *,
    intent_id: str,
    expected_redacted_account_id: str,
    symbol: str,
    side: str,
    quantity: int,
    limit_price: float,
    source_order_digest: str,
    binding_key: object | None = None,
    bridge_root: str | Path | None = None,
    created_at: datetime | None = None,
    expires_at: datetime | None = None,
    ttl_seconds: float = 300.0,
    run_label: str | None = None,
    validation_now: datetime | None = None,
) -> QmtSimulationOrderIntent:
    """Build and validate one authenticated, executable share-limit intent."""

    key = _binding_key(binding_key=binding_key, bridge_root=bridge_root)
    created = _normalized_time(created_at or datetime.now(timezone.utc))
    if expires_at is None:
        if isinstance(ttl_seconds, bool) or not isinstance(ttl_seconds, (int, float)):
            raise InvalidIntentError("ttl_seconds must be a positive bounded number")
        ttl = float(ttl_seconds)
        if not math.isfinite(ttl) or ttl <= 0 or ttl > MAX_INTENT_LIFETIME_SECONDS:
            raise InvalidIntentError("ttl_seconds must be a positive bounded number")
        expires = created + timedelta(seconds=ttl)
    else:
        expires = _normalized_time(expires_at)

    if isinstance(limit_price, bool) or not isinstance(limit_price, (int, float)):
        raise InvalidIntentError("limit_price must be finite and positive")
    normalized_price = float(limit_price)
    if (
        not math.isfinite(normalized_price)
        or normalized_price <= 0
        or normalized_price > MAX_LIMIT_PRICE
    ):
        raise InvalidIntentError("limit_price must be finite and positive")

    unsigned: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "protocol_version": PROTOCOL_VERSION,
        "intent_id": intent_id,
        "created_at": format_utc_timestamp(created),
        "expires_at": format_utc_timestamp(expires),
        "environment": ENVIRONMENT,
        "expected_redacted_account_id": expected_redacted_account_id,
        "account_type": ACCOUNT_TYPE,
        "symbol": symbol,
        "side": side,
        "quantity": quantity,
        "order_kind": ORDER_KIND,
        "limit_price": normalized_price,
        "source_order_digest": source_order_digest,
        "explicit_submit": True,
    }
    if run_label is not None:
        unsigned["run_label"] = run_label
    payload = dict(unsigned)
    payload["intent_hmac"] = calculate_intent_hmac(unsigned, binding_key=key)
    clock = _normalized_time(validation_now or datetime.now(timezone.utc))
    return intent_from_mapping(payload, binding_key=key, now=clock)


def write_intent_atomic(
    bridge_root: str | Path,
    intent: QmtSimulationOrderIntent,
    *,
    binding_key: object | None = None,
    now: datetime | None = None,
    repository_root: str | Path | None = None,
) -> Path:
    """Publish one immutable intent; identical retries are byte-idempotent."""

    root = reject_repository_local_bridge_root(
        bridge_root,
        repository_root=repository_root,
    )
    key = binding_key if binding_key is not None else load_account_binding_key(root)
    validated = intent_from_mapping(
        dict_from_intent(intent),
        binding_key=key,
        now=now,
        expected_redacted_account_id=intent.expected_redacted_account_id,
    )
    encoded = serialize_intent(validated)
    return write_immutable_atomic(
        intent_path(root, validated.intent_id),
        encoded,
        maximum=MAX_INTENT_BYTES,
    )


def create_and_write_intent(
    bridge_root: str | Path,
    *,
    intent_id: str,
    expected_redacted_account_id: str,
    symbol: str,
    side: str,
    quantity: int,
    limit_price: float,
    source_order_digest: str,
    created_at: datetime | None = None,
    expires_at: datetime | None = None,
    ttl_seconds: float = 300.0,
    run_label: str | None = None,
    validation_now: datetime | None = None,
    repository_root: str | Path | None = None,
) -> tuple[QmtSimulationOrderIntent, Path]:
    """CLI-facing convenience that loads the existing key, signs, and writes."""

    root = reject_repository_local_bridge_root(
        bridge_root,
        repository_root=repository_root,
    )
    key = load_account_binding_key(root)
    intent = build_signed_intent(
        intent_id=intent_id,
        expected_redacted_account_id=expected_redacted_account_id,
        symbol=symbol,
        side=side,
        quantity=quantity,
        limit_price=limit_price,
        source_order_digest=source_order_digest,
        binding_key=key,
        created_at=created_at,
        expires_at=expires_at,
        ttl_seconds=ttl_seconds,
        run_label=run_label,
        validation_now=validation_now,
    )
    path = write_intent_atomic(
        root,
        intent,
        binding_key=key,
        now=validation_now,
        repository_root=repository_root,
    )
    return intent, path


def dict_from_intent(intent: QmtSimulationOrderIntent) -> dict[str, object]:
    """Compatibility helper kept local to avoid accepting arbitrary objects."""

    if not isinstance(intent, QmtSimulationOrderIntent):
        raise TypeError("intent must be QmtSimulationOrderIntent")
    from .validation import intent_to_mapping

    return intent_to_mapping(intent)


def _binding_key(*, binding_key: object | None, bridge_root: str | Path | None) -> bytes:
    if binding_key is not None:
        from .account_binding import validate_account_binding_key

        return validate_account_binding_key(binding_key)
    if bridge_root is None:
        raise AccountBindingKeyError("binding_key or bridge_root is required")
    return load_account_binding_key(bridge_root)


def _normalized_time(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise InvalidIntentError("intent timestamps must be timezone-aware")
    return value.astimezone(timezone.utc).replace(microsecond=0)
