"""Daily full-A production-input bridge."""

from quantpilot_core.daily_production_input.builder import (
    AUTHORITATIVE_PRODUCTION_PRESELECTOR,
    DAILY_PRODUCTION_INPUT_VERSION,
    DailyProductionInputConfig,
    DailyProductionInputError,
    DailyProductionInputResult,
    build_daily_production_input_v1,
)

__all__ = [
    "AUTHORITATIVE_PRODUCTION_PRESELECTOR",
    "DAILY_PRODUCTION_INPUT_VERSION",
    "DailyProductionInputConfig",
    "DailyProductionInputError",
    "DailyProductionInputResult",
    "build_daily_production_input_v1",
]
