"""Contracts for the R26 broker sandbox adapter preflight."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class BrokerSandboxAdapterDecision(str, Enum):
    READY = "ready"
    BLOCKED = "blocked"
    MANUAL_REVIEW = "manual_review"


class BrokerSandboxInstructionStatus(str, Enum):
    ACCEPTED_FOR_SANDBOX = "accepted_for_sandbox"
    REJECTED = "rejected"
    SKIPPED = "skipped"


class BrokerSandboxSeverity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class BrokerSandboxAdapterMode(str, Enum):
    PAPER_ONLY = "paper_only"
    BROKER_SANDBOX = "broker_sandbox"
    READ_ONLY_CHECK = "read_only_check"


@dataclass(frozen=True)
class BrokerSandboxRiskFlag:
    code: str
    severity: str
    message: str


@dataclass(frozen=True)
class BrokerSandboxInstruction:
    instruction_id: str
    proposal_id: str
    symbol: str
    side: str
    quantity: int
    estimated_price: float
    limit_price: float | None
    estimated_notional: float
    mode: str
    evidence_refs: tuple[str, ...]


@dataclass(frozen=True)
class BrokerSandboxInstructionResult:
    instruction_id: str
    proposal_id: str
    symbol: str
    side: str
    quantity: int
    status: str
    reason: str
    risk_flags: tuple[BrokerSandboxRiskFlag, ...]
    evidence_refs: tuple[str, ...]


@dataclass(frozen=True)
class BrokerSandboxAdapterPreflightResult:
    ok: bool
    decision: str
    reason: str
    instruction_results: tuple[BrokerSandboxInstructionResult, ...]
    accepted_instruction_ids: tuple[str, ...]
    blocked_instruction_ids: tuple[str, ...]
    manual_review_instruction_ids: tuple[str, ...]
    risk_flags: tuple[BrokerSandboxRiskFlag, ...]
