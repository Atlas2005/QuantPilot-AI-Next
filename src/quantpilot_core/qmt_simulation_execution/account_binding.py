"""Strict loading and verification of the shared account-binding key."""

from __future__ import annotations

import hashlib
import hmac
import re
from pathlib import Path

from .constants import (
    ACCOUNT_BINDING_HMAC_DOMAIN,
    ACCOUNT_BINDING_KEY_BYTES,
)
from .errors import AccountBindingKeyError, AccountBindingMismatchError
from .paths import account_binding_key_path


_REDACTED_ACCOUNT_PATTERN = re.compile(r"\Aqmtacct-v1-[0-9a-f]{24}\Z")
_LOWER_HEX_KEY_PATTERN = re.compile(rb"\A[0-9a-f]{64}\Z")


def load_account_binding_key(bridge_root: str | Path) -> bytes:
    """Load the exact pre-existing 32-byte key without creating or printing it."""

    path = account_binding_key_path(bridge_root)
    try:
        with path.open("rb") as handle:
            encoded = handle.read(65)
    except OSError as exc:
        raise AccountBindingKeyError("account binding key is unavailable", path=path) from exc
    if _LOWER_HEX_KEY_PATTERN.fullmatch(encoded) is None:
        raise AccountBindingKeyError("account binding key is malformed", path=path)
    try:
        decoded = bytes.fromhex(encoded.decode("ascii"))
    except (UnicodeError, ValueError) as exc:
        raise AccountBindingKeyError("account binding key is malformed", path=path) from exc
    if len(decoded) != ACCOUNT_BINDING_KEY_BYTES:
        raise AccountBindingKeyError("account binding key is malformed", path=path)
    return decoded


def validate_account_binding_key(binding_key: object) -> bytes:
    try:
        view = memoryview(binding_key)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        raise AccountBindingKeyError("account binding key must be exactly 32 bytes") from None
    try:
        decoded = view.tobytes()
    finally:
        view.release()
    if len(decoded) != ACCOUNT_BINDING_KEY_BYTES:
        raise AccountBindingKeyError("account binding key must be exactly 32 bytes")
    return decoded


def is_redacted_account_binding(value: object) -> bool:
    return isinstance(value, str) and _REDACTED_ACCOUNT_PATTERN.fullmatch(value) is not None


def redact_account_id(raw_account_id: object, *, binding_key: object) -> str:
    """Derive the same bounded account token as the PR #126 read-only bridge."""

    key = validate_account_binding_key(binding_key)
    if not isinstance(raw_account_id, (str, int)) or isinstance(raw_account_id, bool):
        raise AccountBindingMismatchError("broker account identity cannot be bound safely")
    text = str(raw_account_id).strip()
    if not text:
        raise AccountBindingMismatchError("broker account identity cannot be bound safely")
    try:
        encoded = text.encode("utf-8", "strict")
    except UnicodeError:
        raise AccountBindingMismatchError("broker account identity cannot be bound safely") from None
    if len(encoded) > 512:
        raise AccountBindingMismatchError("broker account identity cannot be bound safely")
    digest = hmac.new(
        key,
        ACCOUNT_BINDING_HMAC_DOMAIN + encoded,
        hashlib.sha256,
    ).hexdigest()[:24]
    return "qmtacct-v1-" + digest


def verify_account_binding(
    expected_redacted_account_id: object,
    *,
    actual_redacted_account_id: object | None = None,
    raw_account_id: object | None = None,
    binding_key: object | None = None,
) -> str:
    """Constant-time verification of an intent against the selected QMT account."""

    if not is_redacted_account_binding(expected_redacted_account_id):
        raise AccountBindingMismatchError("expected account binding is malformed")
    if (actual_redacted_account_id is None) == (raw_account_id is None):
        raise AccountBindingMismatchError(
            "provide exactly one actual account identity representation"
        )
    if raw_account_id is not None:
        actual = redact_account_id(raw_account_id, binding_key=binding_key)
    else:
        if not is_redacted_account_binding(actual_redacted_account_id):
            raise AccountBindingMismatchError("actual account binding is malformed")
        actual = str(actual_redacted_account_id)
    expected = str(expected_redacted_account_id)
    if not hmac.compare_digest(expected.encode("ascii"), actual.encode("ascii")):
        raise AccountBindingMismatchError("selected account does not match the intent binding")
    return actual
