"""Contracts for the R22 paper ledger dry-run integration."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class PaperLedgerDryRunDecision(str, Enum):
    ACCEPTED = "accepted"
    BLOCKED = "blocked"
    PARTIAL = "partial"


class PaperLedgerDryRunInstructionStatus(str, Enum):
    SIMULATED = "simulated"
    REJECTED = "rejected"
    SKIPPED = "skipped"


class RiskSeverity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass(frozen=True)
class PaperLedgerDryRunRiskFlag:
    code: str
    severity: str
    message: str


@dataclass(frozen=True)
class PaperLedgerDryRunInstructionResult:
    proposal_id: str
    symbol: str
    side: str
    quantity: int
    estimated_price: float
    estimated_notional: float
    status: str
    reason: str
    estimated_cash_delta: float
    estimated_position_delta: int
    risk_flags: tuple[PaperLedgerDryRunRiskFlag, ...]
    evidence_refs: tuple[str, ...]


@dataclass(frozen=True)
class PaperLedgerDryRunResult:
    ok: bool
    decision: str
    reason: str
    instruction_results: tuple[PaperLedgerDryRunInstructionResult, ...]
    simulated_cash_after: float
    simulated_positions_after: dict[str, int]
    blocked_instruction_ids: tuple[str, ...]
    risk_flags: tuple[PaperLedgerDryRunRiskFlag, ...]
