"""Contracts for the durable daily paper loop orchestration layer."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Mapping

from quantpilot_core.execution_candidate import ExecutionCandidateReport
from quantpilot_core.paper_trading import PaperFillCostAssumptions
from quantpilot_core.real_data_provider import TradingCalendar
from quantpilot_core.runtime_account import AccountCapabilities, BrokerFeeProfile

DAILY_LOOP_SCHEMA_VERSION = 1
DAILY_LOOP_REPORT_SCHEMA_VERSION = 1
DAILY_LOOP_VERSION = "daily_paper_loop_v1"


class DailyPaperLoopStatus(str, Enum):
    COMPLETED = "completed"
    IDEMPOTENT_REPLAY = "idempotent_replay"


class DailyPaperStateError(ValueError):
    """Raised when persisted daily-loop state is malformed or unsafe."""


class IdempotencyConflictError(DailyPaperStateError):
    """Raised when a completed session is rerun with different stable inputs."""


@dataclass(frozen=True)
class DailyPaperLoopConfig:
    """Runtime settings for exactly one D -> D+1 paper lifecycle."""

    decision_session: str
    initial_capital: float = 100_000.0
    strategy_id: str = "daily-paper-loop-v1"
    state_path: str | Path = ".cache/daily_paper_loop/state.json"
    report_path: str | Path | None = ".cache/daily_paper_loop/latest_report.json"
    max_position_weight: float = 0.10
    target_position_count: int = 10
    reserve_cash_weight: float = 0.02
    min_order_lot: int = 100
    live_market_data: bool = False
    live_symbol_cap: int = 6
    cost_assumptions: PaperFillCostAssumptions = field(default_factory=PaperFillCostAssumptions)
    account_capabilities: AccountCapabilities | None = None
    broker_returned_account_fee_profile: BrokerFeeProfile | None = None
    persisted_user_account_fee_profile: BrokerFeeProfile | None = None
    # Optional PR #123 contract.  It only enriches reports/shadow evidence.
    production_manifest: Any | None = None


@dataclass(frozen=True)
class DailyPaperMarketBundle:
    """Point-in-time market inputs for one execution session."""

    decision_rows_by_symbol: Mapping[str, Mapping[str, Any]]
    execution_rows_by_symbol: Mapping[str, Mapping[str, Any]]
    market_data_provenance: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DailyPaperLoopInput:
    """Injected daily-loop inputs; default runner builds deterministic fixtures."""

    calendar: TradingCalendar
    candidate_report: ExecutionCandidateReport
    market: DailyPaperMarketBundle
    calendar_provenance: Mapping[str, Any] = field(default_factory=dict)
    information_provenance: Mapping[str, Any] = field(default_factory=dict)
    advisory_provenance: Mapping[str, Any] = field(default_factory=dict)
    quant_firm_context: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DailyPaperLoopResult:
    """In-memory result after a daily-loop invocation."""

    status: DailyPaperLoopStatus
    report: Mapping[str, Any]
    state_path: str
    report_path: str | None
