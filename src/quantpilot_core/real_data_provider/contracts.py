"""Provider-independent contracts for real A-share market-data adapters."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Callable, Mapping, Protocol, Sequence
from enum import Enum


class Adjustment(str, Enum):
    NONE = "none"
    QFQ = "qfq"
    HFQ = "hfq"


class ProviderName(str, Enum):
    AKSHARE = "akshare"
    BAOSTOCK = "baostock"
    TUSHARE = "tushare"
    SNAPSHOT = "all_a_share_snapshot"
    TDX_LEVEL1 = "tdx_level1"


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
    previous_close: float | None = None
    pct_change: float | None = None
    turnover: float | None = None
    adjustment_flag: str | None = None
    trade_status: str | None = None
    is_st: bool | None = None
    provider: ProviderName = ProviderName.AKSHARE
    executable_buy_price: float | None = None
    executable_buy_price_available: bool | None = None

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
        self._validate_executable_buy_price()

    def _validate_executable_buy_price(self) -> None:
        available = self.executable_buy_price_available
        price = self.executable_buy_price
        if available is None and price is None:
            return  # unspecified → fallback D close
        if available is True and price is not None and price > 0 and math.isfinite(price):
            return  # explicitly available with valid price
        if available is False and price is None:
            return  # explicitly unavailable
        raise ValueError(
            "executable_buy_price_available/executable_buy_price conflict: "
            f"available={available}, price={price}"
        )


class DailyBarProvider(Protocol):
    provider_name: ProviderName

    def fetch_daily_bars(self, request: DailyBarRequest) -> list[NormalizedDailyBar]:
        """Fetch normalized daily bars for a provider-specific implementation."""


@dataclass(frozen=True)
class NormalizedLevel1Event:
    """One provider-independent Level1 snapshot observation.

    Cumulative volume is expressed in shares and cumulative amount in CNY.
    TDX fields whose units have not yet been confirmed retain source-value
    names and carry their declared interpretation in ``source_units``.
    """

    symbol: str
    timestamp: datetime
    received_at: datetime
    last_price: float
    open: float | None = None
    high: float | None = None
    low: float | None = None
    cumulative_volume_shares: float | None = None
    cumulative_amount_cny: float | None = None
    average_price: float | None = None
    buy1: float | None = None
    sell1: float | None = None
    now_volume_source_value: float | None = None
    inside_volume_source_value: float | None = None
    outside_volume_source_value: float | None = None
    buy_volume_source_values: tuple[float, ...] = ()
    sell_volume_source_values: tuple[float, ...] = ()
    source_units: Mapping[str, str] = field(default_factory=dict)
    timestamp_source: str = "provider"
    provider: ProviderName = ProviderName.TDX_LEVEL1
    raw_payload: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.symbol.strip():
            raise ValueError("symbol must be non-empty")
        if self.timestamp.tzinfo is None or self.timestamp.utcoffset() is None:
            raise ValueError("timestamp must be timezone-aware")
        if self.received_at.tzinfo is None or self.received_at.utcoffset() is None:
            raise ValueError("received_at must be timezone-aware")
        _require_finite_positive(self.last_price, "last_price")
        for field_name in ("open", "high", "low", "average_price", "buy1", "sell1"):
            _require_optional_finite_non_negative(getattr(self, field_name), field_name)
        for field_name in (
            "cumulative_volume_shares",
            "cumulative_amount_cny",
            "now_volume_source_value",
            "inside_volume_source_value",
            "outside_volume_source_value",
        ):
            _require_optional_finite_non_negative(getattr(self, field_name), field_name)
        for field_name in ("buy_volume_source_values", "sell_volume_source_values"):
            for index, value in enumerate(getattr(self, field_name)):
                _require_optional_finite_non_negative(value, f"{field_name}[{index}]")
        if self.high is not None and self.low is not None and self.high < self.low:
            raise ValueError("high must be greater than or equal to low")
        if self.timestamp_source not in {"provider", "collector"}:
            raise ValueError("timestamp_source must be provider or collector")
        if not isinstance(self.raw_payload, Mapping):
            raise TypeError("raw_payload must be a mapping")
        if not isinstance(self.source_units, Mapping):
            raise TypeError("source_units must be a mapping")


@dataclass(frozen=True)
class NormalizedIntradayBar:
    """Intraday bar derived from Level1 events; volume is shares, amount CNY."""

    symbol: str
    start: datetime
    end: datetime
    interval_minutes: int
    open: float
    high: float
    low: float
    close: float
    volume: float
    amount: float
    average_price: float | None
    event_count: int
    missing_minutes_before: int = 0
    partial: bool = False
    provider: ProviderName = ProviderName.TDX_LEVEL1

    def __post_init__(self) -> None:
        if not self.symbol.strip():
            raise ValueError("symbol must be non-empty")
        if self.start.tzinfo is None or self.start.utcoffset() is None:
            raise ValueError("bar start must be timezone-aware")
        if self.end.tzinfo is None or self.end.utcoffset() is None:
            raise ValueError("bar end must be timezone-aware")
        if self.end <= self.start:
            raise ValueError("bar end must be after bar start")
        if self.interval_minutes <= 0:
            raise ValueError("interval_minutes must be positive")
        for field_name in ("open", "high", "low", "close"):
            _require_finite_positive(getattr(self, field_name), field_name)
        if self.high < max(self.open, self.close, self.low):
            raise ValueError("high must cover open, close, and low")
        if self.low > min(self.open, self.close, self.high):
            raise ValueError("low must cover open, close, and high")
        _require_optional_finite_non_negative(self.volume, "volume")
        _require_optional_finite_non_negative(self.amount, "amount")
        _require_optional_finite_non_negative(self.average_price, "average_price")
        if self.event_count <= 0:
            raise ValueError("event_count must be positive")
        if self.missing_minutes_before < 0:
            raise ValueError("missing_minutes_before must be non-negative")


class Level1MarketDataProvider(Protocol):
    """Runtime provider boundary used by the reusable Level1 collector."""

    provider_name: ProviderName

    def initialize(self) -> None: ...

    def get_market_snapshot(self, symbols: Sequence[str]) -> tuple[NormalizedLevel1Event, ...]: ...

    def subscribe_hq(
        self,
        symbols: Sequence[str],
        callback: Callable[[Mapping[str, Any]], None],
    ) -> Any: ...

    def unsubscribe_hq(self, subscription: Any) -> None: ...

    def close(self) -> None: ...


def _require_finite_positive(value: float, field_name: str) -> None:
    numeric = float(value)
    if not math.isfinite(numeric) or numeric <= 0:
        raise ValueError(f"{field_name} must be positive and finite")


def _require_optional_finite_non_negative(value: float | None, field_name: str) -> None:
    if value is None:
        return
    numeric = float(value)
    if not math.isfinite(numeric) or numeric < 0:
        raise ValueError(f"{field_name} must be non-negative and finite")


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


def is_suspended_trade_status(value: Any) -> bool:
    """Interpret provider trade-status values using repository-wide semantics."""

    normalized = str(value).strip().lower()
    return normalized in {"0", "suspended", "停牌", "halted", "false"}
