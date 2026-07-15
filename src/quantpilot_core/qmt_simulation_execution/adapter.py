"""Narrow adapter from the existing advisory ``OrderIntent`` shape."""

from __future__ import annotations

import hashlib
import re
import uuid
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import Any

from quantpilot_core.order_intent import OrderIntent, OrderIntentSide

from .contracts import QmtSimulationOrderIntent
from .errors import InvalidIntentError
from .intent_writer import build_signed_intent
from .paths import validate_intent_id


_LOWER_HEX_64_PATTERN = re.compile(r"\A[0-9a-f]{64}\Z")
_SOURCE_DIGEST_DOMAIN = b"quantpilot:order-intent-source:v1\0"


def build_signed_intent_from_order_intent(
    order_intent: OrderIntent,
    *,
    limit_price: float,
    expected_redacted_account_id: str,
    binding_key: object | None = None,
    bridge_root: str | Path | None = None,
    intent_id: str | None = None,
    created_at: datetime | None = None,
    expires_at: datetime | None = None,
    ttl_seconds: float = 300.0,
    validation_now: datetime | None = None,
) -> QmtSimulationOrderIntent:
    """Translate exactly one share-sized intent without changing its contract."""

    if not isinstance(order_intent, OrderIntent):
        raise TypeError("order_intent must be the canonical OrderIntent contract")
    side_value = order_intent.side.value if isinstance(order_intent.side, OrderIntentSide) else order_intent.side
    if not isinstance(side_value, str) or side_value not in {"buy", "sell"}:
        raise InvalidIntentError("OrderIntent side is not broker executable")
    canonical_symbol = _canonical_symbol(order_intent.symbol)
    shares = order_intent.target_shares
    if isinstance(shares, bool) or not isinstance(shares, int) or shares <= 0:
        raise InvalidIntentError("OrderIntent requires explicit positive target_shares")
    metadata = order_intent.metadata
    if not isinstance(metadata, Mapping):
        raise InvalidIntentError("OrderIntent metadata must be a mapping")

    source_identity = _metadata_identity(metadata)
    selected_intent_id = intent_id or _valid_protocol_identity(source_identity)
    if selected_intent_id is None:
        selected_intent_id = "qpi_" + uuid.uuid4().hex
    validate_intent_id(selected_intent_id)
    source_digest = _metadata_digest(metadata)
    if source_digest is None:
        source_digest = _source_digest(
            source_identity
            or "|".join(
                (
                    canonical_symbol,
                    side_value,
                    str(shares),
                    str(order_intent.run_label or ""),
                )
            )
        )

    return build_signed_intent(
        intent_id=selected_intent_id,
        expected_redacted_account_id=expected_redacted_account_id,
        symbol=canonical_symbol,
        side=str(side_value),
        quantity=shares,
        limit_price=limit_price,
        source_order_digest=source_digest,
        run_label=order_intent.run_label,
        binding_key=binding_key,
        bridge_root=bridge_root,
        created_at=created_at,
        expires_at=expires_at,
        ttl_seconds=ttl_seconds,
        validation_now=validation_now,
    )


def adapt_order_intent(*args: Any, **kwargs: Any) -> QmtSimulationOrderIntent:
    """Short public alias for the canonical adapter."""

    return build_signed_intent_from_order_intent(*args, **kwargs)


def _metadata_identity(metadata: Mapping[str, Any]) -> str | None:
    for key in ("intent_id", "order_id", "client_order_id", "source_order_id"):
        value = metadata.get(key)
        if isinstance(value, str) and value and len(value) <= 256 and "\x00" not in value:
            return value
    return None


def _metadata_digest(metadata: Mapping[str, Any]) -> str | None:
    for key in ("source_order_digest", "order_digest"):
        value = metadata.get(key)
        if isinstance(value, str) and _LOWER_HEX_64_PATTERN.fullmatch(value) is not None:
            return value
    return None


def _valid_protocol_identity(value: str | None) -> str | None:
    if value is None:
        return None
    try:
        return validate_intent_id(value)
    except InvalidIntentError:
        return None


def _source_digest(value: str) -> str:
    try:
        encoded = value.encode("utf-8", "strict")
    except UnicodeError:
        raise InvalidIntentError("OrderIntent identity is not valid UTF-8") from None
    if len(encoded) > 512:
        raise InvalidIntentError("OrderIntent identity exceeds transport bounds")
    return hashlib.sha256(_SOURCE_DIGEST_DOMAIN + encoded).hexdigest()


def _canonical_symbol(value: object) -> str:
    if not isinstance(value, str):
        raise InvalidIntentError("OrderIntent symbol must be text")
    cleaned = value.strip().upper()
    if cleaned.startswith(("SH.", "SZ.", "BJ.")):
        exchange, code = cleaned.split(".", 1)
        cleaned = code + "." + exchange
    if len(cleaned) == 6 and cleaned.isdigit():
        if cleaned.startswith(("110", "111", "113", "118", "5", "6", "900")):
            cleaned += ".SH"
        elif cleaned.startswith(("4", "8", "920")):
            cleaned += ".BJ"
        elif cleaned.startswith(("0", "1", "2", "3")):
            cleaned += ".SZ"
    return cleaned
