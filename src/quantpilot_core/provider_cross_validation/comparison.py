"""Compare normalized daily bars from two providers."""

from __future__ import annotations

from datetime import date
from math import isclose
from typing import Iterable

from quantpilot_core.provider_cross_validation.contracts import (
    ProviderComparisonTolerance,
    ProviderCrossValidationIssue,
    ProviderCrossValidationReport,
)
from quantpilot_core.real_data_provider.contracts import NormalizedDailyBar


PRIMARY_FIELDS = ("open", "high", "low", "close")
SECONDARY_FIELDS = ("volume", "amount")


def canonicalize_symbol(symbol: str) -> str:
    """Normalize common A-share provider symbol forms to code.exchange."""

    cleaned = symbol.strip().upper()
    if cleaned.startswith("SZ."):
        return cleaned[3:] + ".SZ"
    if cleaned.startswith("SH."):
        return cleaned[3:] + ".SH"
    return cleaned


def compare_provider_daily_bars(
    left_bars: Iterable[NormalizedDailyBar],
    right_bars: Iterable[NormalizedDailyBar],
    *,
    tolerance: ProviderComparisonTolerance | None = None,
) -> ProviderCrossValidationReport:
    """Compare two provider outputs without blocking downstream use."""

    active_tolerance = tolerance or ProviderComparisonTolerance()
    left_tuple = tuple(left_bars)
    right_tuple = tuple(right_bars)
    left_index = _index_bars(left_tuple)
    right_index = _index_bars(right_tuple)
    left_keys = set(left_index)
    right_keys = set(right_index)
    common_keys = sorted(left_keys & right_keys)

    issues: list[ProviderCrossValidationIssue] = []
    for symbol, trade_date in sorted(right_keys - left_keys):
        right = right_index[(symbol, trade_date)]
        issues.append(
            _issue(
                "warning",
                "missing_left_record",
                symbol,
                trade_date,
                "record",
                None,
                None,
                f"left provider missing {symbol} on {trade_date.isoformat()}",
                right,
            )
        )
    for symbol, trade_date in sorted(left_keys - right_keys):
        left = left_index[(symbol, trade_date)]
        issues.append(
            _issue(
                "warning",
                "missing_right_record",
                symbol,
                trade_date,
                "record",
                None,
                None,
                f"right provider missing {symbol} on {trade_date.isoformat()}",
                left,
            )
        )
    for key in common_keys:
        issues.extend(_compare_record_pair(left_index[key], right_index[key], active_tolerance))

    ordered_issues = tuple(
        sorted(issues, key=lambda item: (item.symbol, item.trade_date, item.severity, item.issue_type, item.field_name))
    )
    left_provider = _provider_name(left_tuple)
    right_provider = _provider_name(right_tuple)
    return ProviderCrossValidationReport(
        left_provider=left_provider,
        right_provider=right_provider,
        left_count=len(left_tuple),
        right_count=len(right_tuple),
        common_count=len(common_keys),
        missing_left_count=len(right_keys - left_keys),
        missing_right_count=len(left_keys - right_keys),
        fatal_issue_count=sum(1 for issue in ordered_issues if issue.severity == "fatal"),
        warning_issue_count=sum(1 for issue in ordered_issues if issue.severity == "warning"),
        issues=ordered_issues,
        market_reality_notes=market_reality_notes(),
    )


def market_reality_notes() -> tuple[str, ...]:
    return (
        "Provider agreement on OHLC is prerequisite for later tradability modeling.",
        "Volume/amount discrepancies are secondary because provider unit semantics can differ.",
        "This module does not claim profitability and does not simulate fills.",
    )


def _index_bars(bars: tuple[NormalizedDailyBar, ...]) -> dict[tuple[str, date], NormalizedDailyBar]:
    return {(canonicalize_symbol(bar.symbol), bar.trade_date): bar for bar in bars}


def _compare_record_pair(
    left: NormalizedDailyBar,
    right: NormalizedDailyBar,
    tolerance: ProviderComparisonTolerance,
) -> tuple[ProviderCrossValidationIssue, ...]:
    issues: list[ProviderCrossValidationIssue] = []
    symbol = canonicalize_symbol(left.symbol)
    for field in PRIMARY_FIELDS:
        left_value = float(getattr(left, field))
        right_value = float(getattr(right, field))
        if not isclose(
            left_value,
            right_value,
            rel_tol=tolerance.price_rel_tolerance,
            abs_tol=tolerance.price_abs_tolerance,
        ):
            issues.append(
                ProviderCrossValidationIssue(
                    severity="fatal",
                    issue_type="price_mismatch",
                    symbol=symbol,
                    trade_date=left.trade_date,
                    field_name=field,
                    left_value=left_value,
                    right_value=right_value,
                    message=f"{field} differs beyond price tolerance",
                )
            )
    for field in SECONDARY_FIELDS:
        left_raw = getattr(left, field)
        right_raw = getattr(right, field)
        if left_raw is None and right_raw is None:
            continue
        left_value = None if left_raw is None else float(left_raw)
        right_value = None if right_raw is None else float(right_raw)
        if left_value is None or right_value is None or not isclose(
            left_value,
            right_value,
            rel_tol=tolerance.secondary_rel_tolerance,
            abs_tol=0.0,
        ):
            issues.append(
                ProviderCrossValidationIssue(
                    severity="warning",
                    issue_type="secondary_mismatch",
                    symbol=symbol,
                    trade_date=left.trade_date,
                    field_name=field,
                    left_value=left_value,
                    right_value=right_value,
                    message=f"{field} differs beyond secondary tolerance",
                )
            )
    return tuple(issues)


def _issue(
    severity: str,
    issue_type: str,
    symbol: str,
    trade_date: date,
    field_name: str,
    left_value: float | None,
    right_value: float | None,
    message: str,
    _bar: NormalizedDailyBar,
) -> ProviderCrossValidationIssue:
    return ProviderCrossValidationIssue(
        severity=severity,
        issue_type=issue_type,
        symbol=symbol,
        trade_date=trade_date,
        field_name=field_name,
        left_value=left_value,
        right_value=right_value,
        message=message,
    )


def _provider_name(bars: tuple[NormalizedDailyBar, ...]) -> str:
    if not bars:
        return "unknown"
    provider = bars[0].provider
    return getattr(provider, "value", str(provider))
