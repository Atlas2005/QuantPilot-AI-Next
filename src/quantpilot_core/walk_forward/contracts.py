"""Contracts for rolling walk-forward paper evaluation."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Literal, Mapping


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
    """Inputs for deterministic walk-forward paper evaluation."""

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

