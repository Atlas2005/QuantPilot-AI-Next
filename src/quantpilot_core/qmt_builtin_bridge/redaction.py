"""Account redaction and bounded primitive metadata helpers.

These helpers never retain the source account identifier.  The redacted value is
a stable keyed pseudonymous binding token, not a credential or display value.
"""

from __future__ import annotations

import hashlib
import hmac
import math
import re
from collections.abc import Mapping
from typing import Any, TypeAlias

from .constants import (
    MAX_METADATA_ENTRIES,
    MAX_METADATA_KEY_LENGTH,
    MAX_METADATA_TEXT_LENGTH,
)


PrimitiveMetadataValue: TypeAlias = str | int | float | bool | None

ACCOUNT_BINDING_KEY_BYTES = 32
MAX_ACCOUNT_ID_UTF8_BYTES = 512

_ACCOUNT_HASH_DOMAIN = b"quantpilot:qmt-account-binding:v1\0"
_REDACTED_ACCOUNT_PATTERN = re.compile(r"\Aqmtacct-v1-[0-9a-f]{24}\Z")

_SENSITIVE_NAME_FRAGMENTS = (
    "accountkey",
    "accountnumber",
    "accountno",
    "accountid",
    "address",
    "auth",
    "acctno",
    "bankaccount",
    "certificate",
    "clientid",
    "clientkey",
    "credential",
    "customerid",
    "custid",
    "email",
    "fundaccount",
    "holderid",
    "idcard",
    "identity",
    "loginid",
    "mobile",
    "password",
    "passwd",
    "phone",
    "privatekey",
    "secret",
    "shareholder",
    "stockholder",
    "token",
)
_SENSITIVE_NAME_EXACT = frozenset(
    {
        "apikey",
        "authkey",
        "pwd",
        "sessiontoken",
        "token",
    }
)


class AccountBindingKeyError(ValueError):
    """The local account-binding key is absent or not exactly 32 bytes."""


class AccountIdentityRedactionError(ValueError):
    """The source account identity cannot be safely bound to a token."""


def validate_account_binding_key(value: object) -> bytes:
    """Return an immutable copy of an exact 32-byte bytes-like binding key.

    Textual key-file decoding belongs to the runtime/exporter boundary.  This
    core primitive accepts decoded bytes only so a malformed secret can never
    be interpreted as account data or silently padded/truncated.
    """

    try:
        view = memoryview(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        raise AccountBindingKeyError(
            "account binding key must be bytes-like and exactly 32 bytes"
        ) from None
    try:
        normalized = view.tobytes()
    except (TypeError, ValueError):
        raise AccountBindingKeyError(
            "account binding key must be bytes-like and exactly 32 bytes"
        ) from None
    finally:
        view.release()
    if len(normalized) != ACCOUNT_BINDING_KEY_BYTES:
        raise AccountBindingKeyError(
            "account binding key must be bytes-like and exactly 32 bytes"
        )
    return normalized


def _account_identity_utf8(value: object) -> bytes:
    if not isinstance(value, (str, int)) or isinstance(value, bool):
        raise AccountIdentityRedactionError(
            "account identity must be a bounded non-empty UTF-8 string or integer"
        )
    text = str(value).strip()
    if not text:
        raise AccountIdentityRedactionError(
            "account identity must be a bounded non-empty UTF-8 string or integer"
        )
    try:
        raw = text.encode("utf-8", "strict")
    except UnicodeEncodeError:
        raise AccountIdentityRedactionError(
            "account identity must be a bounded non-empty UTF-8 string or integer"
        ) from None
    if len(raw) > MAX_ACCOUNT_ID_UTF8_BYTES:
        raise AccountIdentityRedactionError(
            "account identity must be a bounded non-empty UTF-8 string or integer"
        )
    return raw


def redact_account_identity(value: object, *, binding_key: object | None = None) -> str:
    """Return the keyed, domain-separated stable account binding token."""

    key = validate_account_binding_key(binding_key)
    raw = _account_identity_utf8(value)
    digest = hmac.new(key, _ACCOUNT_HASH_DOMAIN + raw, hashlib.sha256).hexdigest()[:24]
    return "qmtacct-v1-" + digest


def is_redacted_account_identity(value: object) -> bool:
    """Return whether *value* is a valid bridge account binding token."""

    return isinstance(value, str) and _REDACTED_ACCOUNT_PATTERN.fullmatch(value) is not None


def is_sensitive_field_name(value: object) -> bool:
    """Identify provider field names that must never enter bridge metadata."""

    if not isinstance(value, str):
        return True
    normalized = "".join(character for character in value.casefold() if character.isalnum())
    if not normalized:
        return True
    if "redactedaccountid" in normalized:
        return False
    return normalized in _SENSITIVE_NAME_EXACT or any(
        fragment in normalized for fragment in _SENSITIVE_NAME_FRAGMENTS
    )


def bounded_provider_metadata(
    values: Mapping[str, Any] | None,
    *,
    max_entries: int = MAX_METADATA_ENTRIES,
    max_string_length: int = MAX_METADATA_TEXT_LENGTH,
) -> dict[str, PrimitiveMetadataValue]:
    """Copy safe unknown primitive fields into a deterministic bounded mapping.

    Sensitive names, nested structures, non-finite numbers, invalid keys, and
    values beyond the entry cap are omitted.  Strings are truncated because this
    helper is intended for normalization at the exporter boundary; the reader
    independently rejects over-bound protocol values.
    """

    if values is None:
        return {}
    if not isinstance(values, Mapping):
        raise TypeError("provider metadata must be a mapping")
    if max_entries < 0 or max_string_length < 0:
        raise ValueError("metadata bounds must be non-negative")

    result: dict[str, PrimitiveMetadataValue] = {}
    for key in sorted(
        (key for key in values if isinstance(key, str)),
        key=lambda item: (item.casefold(), item),
    ):
        if len(result) >= max_entries:
            break
        if not key or len(key) > MAX_METADATA_KEY_LENGTH or is_sensitive_field_name(key):
            continue
        value = values[key]
        if value is None or isinstance(value, bool) or isinstance(value, int):
            result[key] = value
        elif isinstance(value, float):
            if math.isfinite(value):
                result[key] = value
        elif isinstance(value, str):
            result[key] = value[:max_string_length]
    return result
