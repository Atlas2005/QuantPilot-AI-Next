"""Contracts for bridging executable candidates to paper ledger dry-run."""

from __future__ import annotations

from dataclasses import dataclass

from quantpilot_core.account_profile_preflight import AccountProfile
from quantpilot_core.ai_action_paper_bridge import PaperLedgerCandidateInstruction
from quantpilot_core.executable_candidate import (
    ExecutableCandidateDecision,
    ExecutableCandidateInput,
)
from quantpilot_core.paper_ledger_dry_run import PaperLedgerDryRunResult


@dataclass(frozen=True)
class CandidatePaperBridgeIssue:
    severity: str
    code: str
    message: str


@dataclass(frozen=True)
class CandidatePaperBridgeInput:
    candidate_input: ExecutableCandidateInput
    candidate_decision: ExecutableCandidateDecision
    account_profile: AccountProfile
    evidence_refs: tuple[str, ...]
    proposal_id: str
    trade_date: str
    dry_run_only: bool = True


@dataclass(frozen=True)
class CandidatePaperBridgeResult:
    accepted: bool
    dry_run_executed: bool
    instruction: PaperLedgerCandidateInstruction | None
    dry_run_result: PaperLedgerDryRunResult | None
    issues: tuple[CandidatePaperBridgeIssue, ...]
    warnings: tuple[CandidatePaperBridgeIssue, ...]
    decision_notes: tuple[str, ...]
    live_execution_claim: bool = False
    broker_execution_reference: str | None = None
