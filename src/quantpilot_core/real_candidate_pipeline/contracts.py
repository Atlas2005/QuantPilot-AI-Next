"""Contracts for real PIT factor candidate production."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from quantpilot_core.daily_paper_loop import DailyPaperLoopInput, DailyPaperLoopResult
from quantpilot_core.execution_candidate import ExecutionCandidateReport
from quantpilot_core.runtime_account import AccountCapabilities


class PipelineIdempotencyConflictError(ValueError):
    """Raised when a completed pipeline session is rerun with different stable inputs."""


@dataclass(frozen=True)
class RealCandidatePipelineConfig:
    """Configuration for one D -> D+1 real-candidate paper lifecycle."""

    decision_session: str
    symbols: tuple[str, ...] = ()
    initial_capital: float = 100_000.0
    state_path: str | Path = ".cache/real_candidate_daily_paper/state.json"
    report_path: str | Path | None = ".cache/real_candidate_daily_paper/latest_report.json"
    strategy_id: str = "real-candidate-defensive-composite-v1"
    max_execution_symbols: int = 6
    target_symbol_count: int = 1
    live_market_data: bool = False
    input_bars: tuple[Mapping[str, Any], ...] = ()
    # Optional authoritative sessions for an offline immutable-data replay.
    # This keeps exchange holidays and D+1 boundaries aligned with the source
    # snapshot without constructing or calling a provider.
    input_calendar_sessions: tuple[str, ...] = ()
    input_calendar_provider: str = ""
    information_signals: tuple[Any, ...] = ()
    information_provenance: Mapping[str, Any] = field(default_factory=dict)
    advisory_provenance: Mapping[str, Any] = field(default_factory=dict)
    quant_firm_context: Mapping[str, Any] = field(default_factory=dict)
    account_capabilities: AccountCapabilities | None = None


@dataclass(frozen=True)
class RealCandidatePipelineResult:
    """Combined candidate-pipeline and daily-paper-loop result."""

    candidate_report: ExecutionCandidateReport
    loop_input: DailyPaperLoopInput
    candidate_pipeline_report: Mapping[str, Any]
    daily_paper_loop_result: DailyPaperLoopResult | None = None
    combined_report: Mapping[str, Any] | None = None
