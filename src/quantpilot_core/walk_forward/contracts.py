"""Contracts for rolling walk-forward paper evaluation."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, Literal, Mapping, Protocol, runtime_checkable

import pandas as pd


WalkForwardAdvisoryMode = Literal["disabled", "fallback_only", "evidence_only"]


@dataclass(frozen=True)
class WalkForwardWindow:
    """One train/test slice for point-in-time paper evaluation."""

    train_start: date | datetime | str
    train_end: date | datetime | str
    test_start: date | datetime | str
    test_end: date | datetime | str
    run_label: str


@dataclass(frozen=True)
class WalkForwardInput:
    """Inputs for deterministic walk-forward paper evaluation.

    Pure data — no callbacks, factories, snapshot paths, or data modes.
    """

    historical_price_frame: Any
    historical_signal_frame: Any | None = None
    information_events: Any | None = None
    initial_cash: float = 100_000.0
    current_parameters: Mapping[str, Any] = field(default_factory=dict)
    windows: tuple[WalkForwardWindow, ...] = ()
    advisory_mode: WalkForwardAdvisoryMode = "fallback_only"
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class WalkForwardWindowResult:
    """Per-window output for train-only research and out-of-sample paper trading."""

    window: WalkForwardWindow
    train_summary: Mapping[str, Any]
    order_intent_proposal: Any
    paper_trading_result: Any
    performance_metrics: Mapping[str, Any]
    learning_desk_output: Any | None = None
    deepseek_advisory_summary: Mapping[str, Any] | None = None
    leakage_warnings: tuple[str, ...] = ()
    parameter_update_recommendation: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class WalkForwardResult:
    """Aggregate output across all walk-forward windows."""

    window_results: tuple[WalkForwardWindowResult, ...]
    aggregate_metrics: Mapping[str, Any]
    accepted_parameter_updates: tuple[Mapping[str, Any], ...]
    rejected_parameter_updates: tuple[Mapping[str, Any], ...]
    leakage_checks: tuple[str, ...]
    improvement_summary: Mapping[str, Any]


# ---------------------------------------------------------------------------
# Typed WindowRunner contracts (PR #115)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class WalkForwardWindowContext:
    """Immutable context passed to a WindowRunner for one OOS test window.

    The engine owns window slicing, LeakageGuard, and train evidence.
    The runner receives everything needed to execute the test phase
    without the engine knowing concrete account or execution types.

    ``train_summary``, ``parameters``, and ``metadata`` use
    ``Mapping[str, Any]`` because they are direct pass-through of the
    existing engine contracts (``_train_summary()``,
    ``WalkForwardInput.current_parameters``, ``WalkForwardInput.metadata``).
    """

    window: WalkForwardWindow
    test_prices: pd.DataFrame  # test-window OHLCV bars, sliced by engine
    train_summary: Mapping[str, Any]  # from WalkForwardEngine._train_summary()
    parameters: Mapping[str, Any]  # frozen for baseline; from WalkForwardInput
    metadata: Mapping[str, Any]  # from WalkForwardInput.metadata
    initial_capital: float


@dataclass(frozen=True)
class OOSDailySessionResult:
    """One OOS decision-day result produced by the production pipeline.

    Extracted from the structured reports returned by
    ``run_real_candidate_daily_paper()`` → ``run_daily_paper_loop()``.
    Every field is concrete — no opaque dicts.
    """

    decision_session: date
    execution_session: date
    valuation_session: date
    # --- equity deltas (from production ledger_before / ledger_after) ---
    session_start_equity: float
    session_end_equity: float
    session_net_pnl: float  # = end - start
    gross_pnl: float  # = session_net_pnl + total_cost
    # --- execution metrics (from production outcomes) ---
    intent_count: int
    filled_count: int
    partial_fill_count: int
    rejected_count: int
    requested_quantity: int
    filled_quantity: int
    fill_rate: float  # filled_quantity / requested_quantity
    turnover: float
    # --- fees ---
    commission: float
    transaction_tax: float
    transfer_or_exchange_fee: float
    slippage_cost: float
    total_cost: float
    # --- reconciliation ---
    reconciliation_passed: bool
    settlement_lot_count: int
    # --- provenance ---
    pipeline_request_digest: str
    daily_loop_session_id: str
    report_path: Path | None


@dataclass(frozen=True)
class WalkForwardWindowExecutionResult:
    """Aggregated result from one OOS test window execution.

    Every field is concrete — the engine never unpacks opaque dicts.
    """

    window_label: str
    daily_sessions: tuple[OOSDailySessionResult, ...]

    # --- aggregate metrics (compatible with WalkForwardWindowResult) ---
    net_pnl: float
    gross_pnl: float
    ending_equity: float
    fill_rate: float
    trade_count: int
    rejected_count: int
    turnover: float

    # --- aggregate fee breakdown ---
    commission: float
    transaction_tax: float
    transfer_or_exchange_fee: float
    slippage_cost: float
    total_cost: float

    # --- execution provenance ---
    intent_count: int
    filled_count: int
    partial_fill_count: int
    rejected_count: int
    requested_quantity: int
    filled_quantity: int
    reconciliation_all_passed: bool


@runtime_checkable
class WindowRunner(Protocol):
    """Execute one OOS test window via the production pipeline.

    Implementations call ``run_real_candidate_daily_paper()`` →
    ``run_daily_paper_loop()`` for each decision day in the test window,
    aggregate results, and return the typed execution result.

    The runner owns its concrete state (temp directory, config, state
    path); the engine never sees the account or execution types.
    """

    def run_window(
        self, context: WalkForwardWindowContext
    ) -> WalkForwardWindowExecutionResult: ...


@runtime_checkable
class WindowRunnerFactory(Protocol):
    """Create a WindowRunner for a walk-forward evaluation.

    Separate from *WindowRunner* so the engine does not need to know
    how runners are constructed (temp directories, state paths,
    configuration).  The factory holds its own state path.
    """

    def create_runner(self, *, initial_capital: float) -> WindowRunner: ...
