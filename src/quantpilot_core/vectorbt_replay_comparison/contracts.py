"""Contracts for vectorbt comparison replay from QuantPilot signals."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from quantpilot_core.gate_pruning_tradability_fill_loop import TradeSignalCandidate


class VectorbtComparisonStatus(str, Enum):
    COMPLETED = "completed"
    FRAMEWORK_MISSING = "framework_missing"
    INVALID_INPUT = "invalid_input"


@dataclass(frozen=True)
class SignalReplaySample:
    sample_id: str
    symbols: tuple[str, ...]
    dates: tuple[str, ...]
    prices_by_symbol: dict[str, tuple[float, ...]]
    signals_by_date: dict[str, tuple[TradeSignalCandidate, ...]]
    init_cash: float = 100_000.0
    fees: float = 0.0005
    slippage: float = 0.0005


@dataclass(frozen=True)
class VectorbtReplayComparisonResult:
    status: str
    reason: str
    sample_id: str
    vectorbt_status: str
    equity_curve: tuple[float, ...]
    total_return: float | None
    max_drawdown: float | None
    trade_count: int | None
    turnover_proxy: float | None
    warnings: tuple[str, ...]
    old_chain_reference: str | None
