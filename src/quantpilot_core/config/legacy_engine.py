"""Legacy paper-engine routing controls."""

from __future__ import annotations

import os


USE_LEGACY_ENGINE_ENV = "USE_LEGACY_ENGINE"
LEGACY_ENGINE_DISABLED_REASON = (
    "legacy paper engine disabled; use vectorbt_integration/provider_vectorbt_replay "
    "or explicitly set USE_LEGACY_ENGINE=true for reference compatibility"
)

_TRUE_VALUES = {"1", "true", "yes", "on"}


def use_legacy_engine_default() -> bool:
    """Return whether legacy paper engines are explicitly enabled."""

    return os.getenv(USE_LEGACY_ENGINE_ENV, "").strip().lower() in _TRUE_VALUES


def legacy_engine_enabled(explicit: bool | None = None) -> bool:
    """Resolve an explicit override or the process-level legacy engine flag."""

    if explicit is not None:
        return explicit
    return use_legacy_engine_default()


def require_legacy_engine(explicit: bool | None = None) -> None:
    """Block legacy paper engines unless the caller opted in."""

    if not legacy_engine_enabled(explicit):
        raise RuntimeError(LEGACY_ENGINE_DISABLED_REASON)
