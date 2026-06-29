"""Preflight checks for a future optional RQAlpha adapter."""

from __future__ import annotations

import importlib
from typing import Callable

from quantpilot_core.rqalpha_adapter_preflight.contracts import (
    RQAlphaDependencyStatus,
    RQAlphaPreflightRequest,
    RQAlphaPreflightResult,
)


SUPPORTED_FREQUENCIES = frozenset({"1d"})


def detect_rqalpha_dependency(
    importer: Callable[[str], object] | None = None,
) -> RQAlphaDependencyStatus:
    """Detect whether the optional RQAlpha package is importable."""

    package_importer = importer or importlib.import_module
    try:
        package_importer("rq" + "alpha")
    except ImportError:
        return RQAlphaDependencyStatus.MISSING
    return RQAlphaDependencyStatus.AVAILABLE


def run_rqalpha_preflight(
    request: RQAlphaPreflightRequest,
    importer: Callable[[str], object] | None = None,
) -> RQAlphaPreflightResult:
    """Check whether normalized gated bars are ready for future RQAlpha setup."""

    dependency_status = detect_rqalpha_dependency(importer=importer)
    reasons: list[str] = []
    warnings: list[str] = []

    if not request.symbol.strip():
        reasons.append("symbol_missing")
    if request.start_date > request.end_date:
        reasons.append("date_range_invalid")
    if request.bar_count <= 0:
        reasons.append("bar_count_missing")
    if not request.has_required_ohlcv:
        reasons.append("required_ohlcv_missing")
    if not request.gate_passed:
        reasons.append("small_sample_gate_not_passed")
    if request.cash <= 0:
        reasons.append("cash_must_be_positive")
    if request.frequency not in SUPPORTED_FREQUENCIES:
        reasons.append("frequency_not_supported")

    if dependency_status is RQAlphaDependencyStatus.MISSING:
        warnings.append("RQAlpha is optional and is not installed for this preflight.")

    can_prepare = not reasons
    next_action = (
        "Prepare a future dry-run fixture once dependency and data format are ready."
        if can_prepare
        else "Resolve preflight reasons before preparing an RQAlpha run."
    )

    return RQAlphaPreflightResult(
        dependency_status=dependency_status,
        can_prepare_backtest=can_prepare,
        reasons=tuple(reasons),
        warnings=tuple(warnings),
        suggested_next_action=next_action,
    )
