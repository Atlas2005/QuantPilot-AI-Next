"""Contracts for the R27 multi-agent orchestrator preflight layer."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class OrchestratorDecision(str, Enum):
    READY = "ready"
    BLOCKED = "blocked"
    MANUAL_REVIEW = "manual_review"


class OrchestratorStageStatus(str, Enum):
    PENDING = "pending"
    PASSED = "passed"
    FAILED = "failed"
    MANUAL_REVIEW = "manual_review"
    SKIPPED = "skipped"


class OrchestratorStageName(str, Enum):
    RUNTIME_ROUTER = "runtime_router"
    PIT_FEATURE_STORE = "pit_feature_store"
    NEWS_EVENT_AGENT = "news_event_agent"
    ACCOUNT_PROFILE = "account_profile"
    AI_ACTION_BRIDGE = "ai_action_bridge"
    PAPER_LEDGER_DRY_RUN = "paper_ledger_dry_run"
    MULTI_DAY_REPLAY = "multi_day_replay"
    PERFORMANCE_ATTRIBUTION = "performance_attribution"
    SMALL_CAPITAL_READINESS = "small_capital_readiness"
    BROKER_SANDBOX_PREFLIGHT = "broker_sandbox_preflight"


class OrchestratorSeverity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass(frozen=True)
class OrchestratorRiskFlag:
    code: str
    severity: str
    message: str


@dataclass(frozen=True)
class OrchestratorStageInput:
    stage_name: str
    status: str
    required: bool
    evidence_refs: tuple[str, ...]
    reason: str = ""


@dataclass(frozen=True)
class OrchestratorStageResult:
    stage_name: str
    status: str
    required: bool
    reason: str
    risk_flags: tuple[OrchestratorRiskFlag, ...]
    evidence_refs: tuple[str, ...]


@dataclass(frozen=True)
class OrchestratorPreflightPlan:
    plan_id: str
    stages: tuple[OrchestratorStageInput, ...]
    allow_manual_review: bool = True
    allow_broker_sandbox: bool = False
    evidence_refs: tuple[str, ...] = ()


@dataclass(frozen=True)
class OrchestratorPreflightResult:
    ok: bool
    decision: str
    reason: str
    stage_results: tuple[OrchestratorStageResult, ...]
    blocked_stages: tuple[str, ...]
    manual_review_stages: tuple[str, ...]
    passed_stages: tuple[str, ...]
    risk_flags: tuple[OrchestratorRiskFlag, ...]
