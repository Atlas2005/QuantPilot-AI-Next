"""Contracts for provider cross-validation reports."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class ProviderComparisonTolerance:
    price_abs_tolerance: float = 1e-6
    price_rel_tolerance: float = 1e-6
    secondary_rel_tolerance: float = 1e-3


@dataclass(frozen=True)
class ProviderCrossValidationIssue:
    severity: str
    issue_type: str
    symbol: str
    trade_date: date
    field_name: str
    left_value: float | None
    right_value: float | None
    message: str


@dataclass(frozen=True)
class ProviderCrossValidationReport:
    left_provider: str
    right_provider: str
    left_count: int
    right_count: int
    common_count: int
    missing_left_count: int
    missing_right_count: int
    fatal_issue_count: int
    warning_issue_count: int
    issues: tuple[ProviderCrossValidationIssue, ...]
    market_reality_notes: tuple[str, ...]
