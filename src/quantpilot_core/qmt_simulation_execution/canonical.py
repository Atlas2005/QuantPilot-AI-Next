"""Canonical JSON primitives shared by protocol writers and readers."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from .errors import MalformedArtifactError


def canonical_json_bytes(value: Mapping[str, Any], *, trailing_newline: bool = False) -> bytes:
    """Return deterministic ASCII JSON and reject non-finite numbers."""

    try:
        text = json.dumps(
            dict(value),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        )
    except (TypeError, ValueError, OverflowError, RecursionError) as exc:
        raise MalformedArtifactError("artifact cannot be represented as canonical JSON") from exc
    if trailing_newline:
        text += "\n"
    return text.encode("ascii")


def canonical_json_text(value: Mapping[str, Any], *, trailing_newline: bool = False) -> str:
    """Text counterpart to :func:`canonical_json_bytes`."""

    return canonical_json_bytes(value, trailing_newline=trailing_newline).decode("ascii")


def decode_json_object(raw: bytes, *, path: object | None = None) -> dict[str, Any]:
    """Decode one strict JSON object, rejecting duplicates and NaN constants."""

    try:
        text = raw.decode("utf-8", "strict")
        payload = json.loads(
            text,
            object_pairs_hook=_object_without_duplicate_keys,
            parse_constant=_reject_json_constant,
        )
    except (UnicodeError, json.JSONDecodeError, ValueError, RecursionError) as exc:
        raise MalformedArtifactError("artifact is not strict UTF-8 JSON", path=path) from exc
    if not isinstance(payload, dict):
        raise MalformedArtifactError("artifact root must be a JSON object", path=path)
    return payload


def _object_without_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON object key")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> None:
    del value
    raise ValueError("non-finite JSON constant")
