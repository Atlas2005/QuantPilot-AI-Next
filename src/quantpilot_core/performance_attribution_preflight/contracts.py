"""Contracts for the R24 performance attribution flywheel preflight."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class AttributionDecision(str, Enum):
    COMPLETED = "completed"
    PARTIAL = "partial"
    BLOCKED = "blocked"


class FeedbackTargetType(str, Enum):
    PROPOSAL = "proposal"
    SYMBOL = "symbol"
    SOURCE = "source"
    DAY = "day"
    RISK_RULE = "risk_rule"


class AttributionSeverity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AttributionOutcome(str, Enum):
    SIMULATED_GAIN = "simulated_gain"
    SIMULATED_LOSS = "simulated_loss"
    FLAT = "flat"
    BLOCKED = "blocked"
    PARTIAL = "partial"
    SKIPPED = "skipped"


@dataclass(frozen=True)
class PerformanceAttributionRiskFlag:
    code: str
    severity: str
    message: str


@dataclass(frozen=True)
class ProposalAttributionRecord:
    proposal_id: str
    symbol: str
    trading_date: str
    side: str
    quantity: int
    estimated_price: float
    estimated_notional: float
    status: str
    estimated_cash_delta: float
    estimated_position_delta: int
    estimated_cost: float
    outcome: str
    reason: str
    evidence_refs: tuple[str, ...]


@dataclass(frozen=True)
class SymbolAttributionRecord:
    symbol: str
    accepted_count: int
    blocked_count: int
    net_position_delta: int
    net_cash_delta: float
    estimated_total_cost: float
    risk_flags_seen: tuple[str, ...]


@dataclass(frozen=True)
class SourceAttributionRecord:
    source: str
    accepted_count: int
    blocked_count: int
    manual_review_count: int
    estimated_net_cash_delta: float
    estimated_total_cost: float
    risk_flags_seen: tuple[str, ...]


@dataclass(frozen=True)
class DayAttributionRecord:
    trading_date: str
    status: str
    accepted_count: int
    blocked_count: int
    cash_start: float
    cash_end: float
    estimated_net_cash_delta: float
    estimated_total_cost: float
    risk_flags_seen: tuple[str, ...]


@dataclass(frozen=True)
class FeedbackRecord:
    target_type: str
    target_id: str
    outcome: str
    score: float
    reason: str
    evidence_refs: tuple[str, ...]


@dataclass(frozen=True)
class PerformanceAttributionResult:
    ok: bool
    decision: str
    reason: str
    proposal_records: tuple[ProposalAttributionRecord, ...]
    symbol_records: tuple[SymbolAttributionRecord, ...]
    source_records: tuple[SourceAttributionRecord, ...]
    day_records: tuple[DayAttributionRecord, ...]
    feedback_records: tuple[FeedbackRecord, ...]
    risk_flags: tuple[PerformanceAttributionRiskFlag, ...]
