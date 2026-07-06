"""Contracts for deterministic multi-session real daily evaluation."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping


DAILY_EVALUATION_SCHEMA_VERSION = 1
DAILY_EVALUATION_VERSION = "real_daily_evaluation_v1"


@dataclass(frozen=True)
class RealDailyEvaluationConfig:
    """Configuration for a bounded daily evaluation request."""

    strategy_id: str
    start_decision_session: str
    end_decision_session: str
    symbols: tuple[str, ...]
    capital_values: tuple[float, ...] = (1_000.0, 10_000.0, 100_000.0)
    output_dir: str | Path = ".cache/real_daily_evaluation"
    live_market_data: bool = False
    provider_mode: str = "auto"
    offline_calendar_sessions: tuple[str, ...] = ()
    max_execution_symbols: int = 6
    target_symbol_count: int = 1
    input_bars: tuple[Mapping[str, Any], ...] = ()
    information_signals: tuple[Any, ...] = ()
    information_provenance: Mapping[str, Any] = field(default_factory=dict)
    advisory_provenance: Mapping[str, Any] = field(default_factory=dict)
    quant_firm_context: Mapping[str, Any] = field(default_factory=dict)
    report_filename: str = "evaluation_report.json"


@dataclass(frozen=True)
class RealDailyEvaluationResult:
    """In-memory result for a completed aggregate evaluation."""

    status: str
    report: Mapping[str, Any]
    report_path: str
    evaluation_request_digest: str
