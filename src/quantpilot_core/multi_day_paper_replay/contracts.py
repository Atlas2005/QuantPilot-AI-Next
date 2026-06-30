"""Contracts for the R23 multi-day paper replay."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from quantpilot_core.ai_action_paper_bridge import PaperLedgerCandidateInstruction


class PaperReplayDecision(str, Enum):
    COMPLETED = "completed"
    PARTIAL = "partial"
    BLOCKED = "blocked"


class PaperReplayDayStatus(str, Enum):
    SIMULATED = "simulated"
    PARTIAL = "partial"
    BLOCKED = "blocked"
    SKIPPED = "skipped"


class RiskSeverity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass(frozen=True)
class PaperReplayRiskFlag:
    code: str
    severity: str
    message: str


@dataclass(frozen=True)
class PaperReplayDayInput:
    trading_date: str
    instructions: tuple[PaperLedgerCandidateInstruction, ...]


@dataclass(frozen=True)
class PaperReplayDayResult:
    trading_date: str
    status: str
    reason: str
    dry_run_result: Any
    cash_start: float
    cash_end: float
    positions_start: dict[str, int]
    positions_end: dict[str, int]
    blocked_instruction_ids: tuple[str, ...]
    risk_flags: tuple[PaperReplayRiskFlag, ...]


@dataclass(frozen=True)
class PaperReplayResult:
    ok: bool
    decision: str
    reason: str
    day_results: tuple[PaperReplayDayResult, ...]
    final_cash: float
    final_positions: dict[str, int]
    blocked_days: tuple[str, ...]
    risk_flags: tuple[PaperReplayRiskFlag, ...]
