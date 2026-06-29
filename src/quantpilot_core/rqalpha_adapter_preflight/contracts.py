"""Contracts for the R10 RQAlpha adapter preflight spike."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum


class RQAlphaDependencyStatus(str, Enum):
    AVAILABLE = "available"
    MISSING = "missing"


@dataclass(frozen=True)
class RQAlphaPreflightRequest:
    symbol: str
    start_date: date
    end_date: date
    bar_count: int
    has_required_ohlcv: bool
    gate_passed: bool
    cash: float = 1000.0
    frequency: str = "1d"


@dataclass(frozen=True)
class RQAlphaPreflightResult:
    dependency_status: RQAlphaDependencyStatus
    can_prepare_backtest: bool
    reasons: tuple[str, ...]
    warnings: tuple[str, ...]
    suggested_next_action: str
