"""Contracts for R30 final readiness / release hardening."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class FinalReadinessDecision(str, Enum):
    READY = "ready"
    BLOCKED = "blocked"
    MANUAL_REVIEW = "manual_review"


class ReleaseCheckStatus(str, Enum):
    PASS = "pass"
    WARNING = "warning"
    FAIL = "fail"


class ReleaseSeverity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ReleaseArea(str, Enum):
    DATA = "data"
    PIT = "pit"
    AI_AGENT = "ai_agent"
    ACCOUNT = "account"
    PAPER_LEDGER = "paper_ledger"
    REPLAY = "replay"
    ATTRIBUTION = "attribution"
    READINESS = "readiness"
    BROKER_SANDBOX = "broker_sandbox"
    ORCHESTRATOR = "orchestrator"
    FACTOR_STATS = "factor_stats"
    QLIB_PREFLIGHT = "qlib_preflight"
    SAFETY = "safety"
    DOCS = "docs"


@dataclass(frozen=True)
class FinalReadinessRiskFlag:
    code: str
    severity: str
    message: str


@dataclass(frozen=True)
class ReleaseCheckRecord:
    name: str
    area: str
    status: str
    reason: str
    evidence_refs: tuple[str, ...]


@dataclass(frozen=True)
class RequiredModuleRecord:
    module_name: str
    area: str
    required: bool
    import_path: str
    evidence_refs: tuple[str, ...]


@dataclass(frozen=True)
class RequiredDocumentRecord:
    document_path: str
    area: str
    required: bool
    evidence_refs: tuple[str, ...]


@dataclass(frozen=True)
class ForbiddenScopeCheck:
    name: str
    forbidden_terms: tuple[str, ...]
    allowed_exceptions: tuple[str, ...]
    evidence_refs: tuple[str, ...]


@dataclass(frozen=True)
class FinalReadinessInput:
    release_id: str
    modules: tuple[RequiredModuleRecord, ...]
    documents: tuple[RequiredDocumentRecord, ...]
    forbidden_scope_checks: tuple[ForbiddenScopeCheck, ...]
    evidence_refs: tuple[str, ...]


@dataclass(frozen=True)
class FinalReadinessReport:
    ok: bool
    decision: str
    reason: str
    release_id: str
    checks: tuple[ReleaseCheckRecord, ...]
    risk_flags: tuple[FinalReadinessRiskFlag, ...]
    passed_checks: tuple[str, ...]
    warning_checks: tuple[str, ...]
    failed_checks: tuple[str, ...]
