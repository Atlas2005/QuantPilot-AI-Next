"""Contracts for the optional RQAlpha A-share backtest adapter."""

from __future__ import annotations

from dataclasses import field, dataclass
from enum import Enum
from typing import Mapping


class RqalphaAshareBacktestStatus(str, Enum):
    FRAMEWORK_MISSING = "framework_missing"
    DATA_BUNDLE_REQUIRED = "data_bundle_required"
    CONFIG_REQUIRED = "config_required"
    NOT_EXECUTED = "not_executed"
    INVALID_INPUT = "invalid_input"
    COMPLETED = "completed"


@dataclass(frozen=True)
class RqalphaAshareBacktestInput:
    strategy_id: str
    symbols: tuple[str, ...]
    start_date: str
    end_date: str
    initial_cash: float
    frequency: str = "1d"
    benchmark: str | None = None
    provider_hint: str | None = None
    metadata: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class RqalphaAshareBacktestMetric:
    name: str
    value: float | str | bool | None
    source: str = "rqalpha"


@dataclass(frozen=True)
class RqalphaAshareBacktestResult:
    status: str
    strategy_id: str
    symbols: tuple[str, ...]
    metrics: tuple[RqalphaAshareBacktestMetric, ...]
    warnings: tuple[str, ...]
    errors: tuple[str, ...]
    runtime_available: bool
    executed: bool
    notes: tuple[str, ...]
    engine: str = "rqalpha"


@dataclass(frozen=True)
class RqalphaAshareBacktestReport:
    engine: str
    status: str
    runtime_available: bool
    executed: bool
    metrics_count: int
    warnings: tuple[str, ...]
    errors: tuple[str, ...]
    notes: tuple[str, ...]
    summary: str
