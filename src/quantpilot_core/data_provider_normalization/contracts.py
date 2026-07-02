"""Contracts for in-memory provider normalization reports."""

from __future__ import annotations

from dataclasses import dataclass


NORMALIZED_OHLCV_COLUMNS = (
    "symbol",
    "date",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "amount",
    "provider",
    "adjustment",
)


@dataclass(frozen=True)
class ProviderKey:
    symbol: str
    date: str


@dataclass(frozen=True)
class ProviderValueDifference:
    symbol: str
    date: str
    field_name: str
    left_value: float | None
    right_value: float | None
    absolute_difference: float | None
    pct_difference: float | None


@dataclass(frozen=True)
class ProviderCrossCheckReport:
    left_provider: str
    right_provider: str
    left_rows: int
    right_rows: int
    left_unique_symbol_dates: int
    right_unique_symbol_dates: int
    common_symbol_dates: int
    coverage_ratio: float
    left_missing_dates: tuple[ProviderKey, ...]
    right_missing_dates: tuple[ProviderKey, ...]
    left_duplicate_symbol_dates: tuple[ProviderKey, ...]
    right_duplicate_symbol_dates: tuple[ProviderKey, ...]
    close_differences: tuple[ProviderValueDifference, ...]
    volume_differences: tuple[ProviderValueDifference, ...]
    max_close_pct_difference: float | None
    advisory_only: bool = True

