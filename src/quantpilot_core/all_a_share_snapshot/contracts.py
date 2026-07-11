"""Contracts for the point-in-time all-A-share snapshot (PR #118)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Protocol, Sequence

REQUIRED_DATASETS = ("stock_basic", "calendar", "daily", "adj_factor", "benchmark")
OPTIONAL_DATASETS = ("daily_basic", "suspend", "limits", "namechange")
DEFAULT_START = "20231009"
DEFAULT_END = "20251231"
DEFAULT_BENCHMARK = "000300.SH"


class AllAShareProvider(Protocol):
    """Direct official-provider boundary; market-wide methods are date based."""
    provider_name: str
    def fetch_stock_basic(self, list_statuses: Sequence[str]) -> Sequence[Mapping[str, Any]]: ...
    def fetch_trade_cal(self, start_date: str, end_date: str) -> Sequence[Mapping[str, Any]]: ...
    def fetch_daily_by_trade_date(self, trade_date: str) -> Sequence[Mapping[str, Any]]: ...
    def fetch_adj_factor_by_trade_date(self, trade_date: str) -> Sequence[Mapping[str, Any]]: ...
    def fetch_index_daily(self, symbol: str, start_date: str, end_date: str) -> Sequence[Mapping[str, Any]]: ...
    def fetch_optional(self, dataset: str, trade_date: str | None = None) -> Sequence[Mapping[str, Any]]: ...
    def fetch_namechange_by_ts_code(self, ts_code: str) -> Sequence[Mapping[str, Any]]: ...


@dataclass(frozen=True)
class SnapshotConfig:
    root: str
    start_date: str = DEFAULT_START
    end_date: str = DEFAULT_END
    list_statuses: tuple[str, ...] = ("L", "D", "P")
    include_optional: bool = True
    test_only: bool = False
    max_retries: int = 2
    retry_delay_seconds: float = 0.25
    # Tushare's documented 200 requests/minute quota needs practical headroom.
    min_request_interval_seconds: float = 0.35
    retry_jitter_seconds: float = 0.0
    rate_limit_cooldown_seconds: float = 60.0
    namechange_shard_size: int = 200


@dataclass(frozen=True)
class ValidationResult:
    ok: bool
    errors: tuple[str, ...]
    warnings: tuple[str, ...]
    checked_partitions: int
    manifest: Mapping[str, Any]
