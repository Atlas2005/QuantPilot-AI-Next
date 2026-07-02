"""Project metadata configuration."""

from quantpilot_core.config.project import (
    PRODUCT_NAME,
    PROJECT_NAME,
    PROJECT_STAGE,
    TRADING_READINESS,
)
from quantpilot_core.config.legacy_engine import (
    LEGACY_ENGINE_DISABLED_REASON,
    USE_LEGACY_ENGINE_ENV,
    legacy_engine_enabled,
    require_legacy_engine,
    use_legacy_engine_default,
)

__all__ = [
    "LEGACY_ENGINE_DISABLED_REASON",
    "PRODUCT_NAME",
    "PROJECT_NAME",
    "PROJECT_STAGE",
    "TRADING_READINESS",
    "USE_LEGACY_ENGINE_ENV",
    "legacy_engine_enabled",
    "require_legacy_engine",
    "use_legacy_engine_default",
]
