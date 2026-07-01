"""Provider-independent contracts for real A-share daily bar adapters."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Mapping, Protocol
from enum import Enum


class Adjustment(str, Enum):
    NONE = "none"
    QFQ = "qfq"
    HFQ = "hfq"


class ProviderName(str, Enum):
    AKSHARE = "akshare"
    BAOSTOCK = "baostock"
    TUSHARE = "tushare"


class ProviderError(Exception):
    """Base exception for real data provider adapter failures."""


class ProviderDependencyError(ProviderError):
    """Raised when an optional provider dependency is not available."""


class ProviderDataError(ProviderError):
    """Raised when provider output cannot be normalized safely."""


@dataclass(frozen=True)
class DailyBarRequest:
    symbol: str
    start_date: date
    end_date: date
    adjustment: Adjustment = Adjustment.NONE

    def __post_init__(self) -> None:
        if not self.symbol.strip():
            raise ValueError("symbol must be non-empty")
        if self.start_date > self.end_date:
            raise ValueError("start_date must be before or equal to end_date")


@dataclass(frozen=True)
class NormalizedDailyBar:
    symbol: str
    trade_date: date
    open: float
    close: float
    high: float
    low: float
    volume: float
    amount: float | None = None
    pct_change: float | None = None
    turnover: float | None = None
    provider: ProviderName = ProviderName.AKSHARE

    def __post_init__(self) -> None:
        if not self.symbol.strip():
            raise ValueError("symbol must be non-empty")
        if self.open <= 0 or self.close <= 0 or self.high <= 0 or self.low <= 0:
            raise ValueError("OHLC values must be positive")
        if self.volume < 0:
            raise ValueError("volume must be non-negative")
        if self.high < self.low:
            raise ValueError("high must be greater than or equal to low")
        if self.high < self.open or self.high < self.close:
            raise ValueError("high must be greater than or equal to open and close")
        if self.low > self.open or self.low > self.close:
            raise ValueError("low must be less than or equal to open and close")


class DailyBarProvider(Protocol):
    provider_name: ProviderName

    def fetch_daily_bars(self, request: DailyBarRequest) -> list[NormalizedDailyBar]:
        """Fetch normalized daily bars for a provider-specific implementation."""


def parse_yyyymmdd(value: str) -> date:
    if len(value) != 8 or not value.isdigit():
        raise ValueError("date must use YYYYMMDD format")
    return date(int(value[:4]), int(value[4:6]), int(value[6:8]))


def to_yyyymmdd(value: date) -> str:
    return value.strftime("%Y%m%d")


def require_columns(row: Mapping[str, Any], required_columns: set[str]) -> None:
    missing = {column for column in required_columns if column not in row}
    if missing:
        raise ProviderDataError(f"missing required columns: {sorted(missing)}")


def to_float(value: Any, field_name: str) -> float:
    if value is None or isinstance(value, bool):
        raise ProviderDataError(f"{field_name} must be a number")
    if isinstance(value, str) and not value.strip():
        raise ProviderDataError(f"{field_name} must be a number")
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ProviderDataError(f"{field_name} must be a number") from exc
