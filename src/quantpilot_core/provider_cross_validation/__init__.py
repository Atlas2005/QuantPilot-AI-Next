"""Provider cross-validation for normalized daily bars."""

from quantpilot_core.provider_cross_validation.comparison import (
    canonicalize_symbol,
    compare_provider_daily_bars,
    market_reality_notes,
)
from quantpilot_core.provider_cross_validation.contracts import (
    ProviderComparisonTolerance,
    ProviderCrossValidationIssue,
    ProviderCrossValidationReport,
)
from quantpilot_core.provider_cross_validation.report import (
    build_provider_cross_validation_report,
)

__all__ = [
    "ProviderComparisonTolerance",
    "ProviderCrossValidationIssue",
    "ProviderCrossValidationReport",
    "build_provider_cross_validation_report",
    "canonicalize_symbol",
    "compare_provider_daily_bars",
    "market_reality_notes",
]
