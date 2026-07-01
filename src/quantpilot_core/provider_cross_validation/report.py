"""Report helpers for provider cross-validation."""

from __future__ import annotations

from typing import Iterable

from quantpilot_core.provider_cross_validation.comparison import compare_provider_daily_bars
from quantpilot_core.provider_cross_validation.contracts import (
    ProviderComparisonTolerance,
    ProviderCrossValidationReport,
)
from quantpilot_core.real_data_provider.contracts import NormalizedDailyBar


def build_provider_cross_validation_report(
    left_bars: Iterable[NormalizedDailyBar],
    right_bars: Iterable[NormalizedDailyBar],
    *,
    tolerance: ProviderComparisonTolerance | None = None,
) -> ProviderCrossValidationReport:
    """Build a discrepancy report without rejecting provider data by default."""

    return compare_provider_daily_bars(left_bars, right_bars, tolerance=tolerance)
