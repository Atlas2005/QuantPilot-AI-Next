"""Contracts for optional vectorbt-backed replay."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Mapping


class VectorbtReplayStatus(str, Enum):
    COMPLETED = "completed"
    FRAMEWORK_MISSING = "framework_missing"
    INVALID_INPUT = "invalid_input"


@dataclass(frozen=True)
class VectorbtReplayInput:
    prices: Mapping[str, tuple[float, ...]]
    entries: Mapping[str, tuple[bool, ...]]
    exits: Mapping[str, tuple[bool, ...]]
    init_cash: float = 100_000.0
    fees: float = 0.0005
    slippage: float = 0.0005
    freq: str = "1D"


@dataclass(frozen=True)
class VectorbtReplayResult:
    status: str
    reason: str
    equity_curve: tuple[float, ...]
    total_return: float | None
    max_drawdown: float | None
    trade_count: int | None
    turnover_proxy: float | None
    framework: str = "vectorbt"
    warnings: tuple[str, ...] = ()
