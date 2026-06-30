"""Contracts for the R21 AI action proposal to paper-ledger bridge."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ActionSide(str, Enum):
    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"


class ProposalSource(str, Enum):
    AI_SUPERVISOR = "ai_supervisor"
    NEWS_EVENT_AGENT = "news_event_agent"
    FACTOR_AGENT = "factor_agent"
    RISK_AGENT = "risk_agent"
    MANUAL_REVIEW = "manual_review"


class BridgeDecision(str, Enum):
    ACCEPTED_FOR_PAPER = "accepted_for_paper"
    BLOCKED = "blocked"
    REQUIRES_MANUAL_REVIEW = "requires_manual_review"


class RiskSeverity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass(frozen=True)
class AIActionProposal:
    proposal_id: str
    source: str
    symbol: str
    side: str
    quantity: int
    limit_price: float | None
    estimated_price: float
    confidence: float
    rationale: str
    evidence_refs: tuple[str, ...]


@dataclass(frozen=True)
class PaperLedgerCandidateInstruction:
    proposal_id: str
    symbol: str
    side: str
    quantity: int
    estimated_price: float
    limit_price: float | None
    estimated_notional: float
    reason: str
    evidence_refs: tuple[str, ...]


@dataclass(frozen=True)
class AIActionBridgeRiskFlag:
    code: str
    severity: str
    message: str


@dataclass(frozen=True)
class AIActionPaperBridgeResult:
    ok: bool
    decision: str
    reason: str
    accepted_instructions: tuple[PaperLedgerCandidateInstruction, ...]
    blocked_proposals: tuple[str, ...]
    risk_flags: tuple[AIActionBridgeRiskFlag, ...]
