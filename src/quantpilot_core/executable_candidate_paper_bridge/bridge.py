"""Bridge executable candidate decisions to paper ledger dry-run."""

from __future__ import annotations

from quantpilot_core.ai_action_paper_bridge import ActionSide, PaperLedgerCandidateInstruction
from quantpilot_core.executable_candidate import CandidateSide
from quantpilot_core.executable_candidate_paper_bridge.contracts import (
    CandidatePaperBridgeInput,
    CandidatePaperBridgeIssue,
    CandidatePaperBridgeResult,
)
from quantpilot_core.paper_ledger_dry_run import run_paper_ledger_dry_run


DRY_RUN_NOTES = (
    "no_live_execution",
    "paper_ledger_dry_run_only",
    "executable_candidate_bridge",
)


def build_paper_ledger_instruction_from_candidate(
    bridge_input: CandidatePaperBridgeInput,
) -> PaperLedgerCandidateInstruction:
    """Translate an accepted executable candidate into a paper instruction."""

    candidate = bridge_input.candidate_input
    decision = bridge_input.candidate_decision
    return PaperLedgerCandidateInstruction(
        proposal_id=bridge_input.proposal_id,
        symbol=candidate.symbol,
        side=_map_side(candidate.side),
        quantity=decision.executable_quantity,
        estimated_price=candidate.reference_price,
        limit_price=candidate.reference_price,
        estimated_notional=decision.estimated_notional,
        reason=";".join(DRY_RUN_NOTES + (f"trade_date:{bridge_input.trade_date}",)),
        evidence_refs=bridge_input.evidence_refs,
    )


def run_candidate_paper_dry_run(
    bridge_input: CandidatePaperBridgeInput,
    *,
    use_legacy_engine: bool | None = None,
) -> CandidatePaperBridgeResult:
    """Run the existing paper ledger dry-run for an executable candidate."""

    issues = _bridge_issues(bridge_input)
    warnings = tuple(
        CandidatePaperBridgeIssue(
            severity="warning",
            code=warning.code,
            message=warning.message,
        )
        for warning in bridge_input.candidate_decision.warnings
    )
    if issues:
        return CandidatePaperBridgeResult(
            accepted=False,
            dry_run_executed=False,
            instruction=None,
            dry_run_result=None,
            issues=tuple(issues),
            warnings=warnings,
            decision_notes=DRY_RUN_NOTES,
            live_execution_claim=False,
            broker_execution_reference=None,
        )

    instruction = build_paper_ledger_instruction_from_candidate(bridge_input)
    dry_run_result = run_paper_ledger_dry_run(
        (instruction,),
        bridge_input.account_profile,
        use_legacy_engine=use_legacy_engine,
    )
    return CandidatePaperBridgeResult(
        accepted=dry_run_result.ok,
        dry_run_executed=True,
        instruction=instruction,
        dry_run_result=dry_run_result,
        issues=tuple(
            CandidatePaperBridgeIssue(
                severity="fatal",
                code=flag.code,
                message=flag.message,
            )
            for flag in dry_run_result.risk_flags
        ),
        warnings=warnings,
        decision_notes=DRY_RUN_NOTES + (f"paper_ledger_decision:{dry_run_result.decision}",),
        live_execution_claim=False,
        broker_execution_reference=None,
    )


def _bridge_issues(bridge_input: CandidatePaperBridgeInput) -> list[CandidatePaperBridgeIssue]:
    decision = bridge_input.candidate_decision
    issues: list[CandidatePaperBridgeIssue] = []
    if not bridge_input.dry_run_only:
        issues.append(_fatal("dry_run_only_required", "bridge only supports paper ledger dry-run"))
    if not decision.accepted:
        issues.append(_fatal("candidate_decision_rejected", "candidate decision was not accepted"))
    if decision.executable_quantity <= 0:
        issues.append(_fatal("executable_quantity_missing", "executable quantity must be positive"))
    if decision.live_execution_claim:
        issues.append(_fatal("live_execution_claim_rejected", "live execution claim is forbidden"))
    if decision.broker_execution_reference is not None:
        issues.append(_fatal("broker_reference_rejected", "broker execution reference is forbidden"))
    if not bridge_input.evidence_refs:
        issues.append(_fatal("evidence_refs_missing", "evidence refs are required for dry-run"))
    return issues


def _map_side(side: CandidateSide) -> str:
    if side == CandidateSide.BUY:
        return ActionSide.BUY.value
    return ActionSide.SELL.value


def _fatal(code: str, message: str) -> CandidatePaperBridgeIssue:
    return CandidatePaperBridgeIssue(severity="fatal", code=code, message=message)
