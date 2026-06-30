"""Validation helpers for R22 paper ledger dry-run instructions."""

from __future__ import annotations

from quantpilot_core.ai_action_paper_bridge import ActionSide, PaperLedgerCandidateInstruction
from quantpilot_core.paper_ledger_dry_run.contracts import (
    PaperLedgerDryRunRiskFlag,
    RiskSeverity,
)


NOTIONAL_TOLERANCE = 0.0001


def validate_dry_run_instruction(
    instruction: PaperLedgerCandidateInstruction,
    *,
    allow_odd_lot: bool = False,
) -> tuple[PaperLedgerDryRunRiskFlag, ...]:
    """Validate a candidate instruction before in-memory dry-run simulation."""

    flags: list[PaperLedgerDryRunRiskFlag] = []
    if not instruction.proposal_id.strip():
        flags.append(_critical("proposal_id_missing", "Proposal ID must be non-empty."))
    if not instruction.symbol.strip():
        flags.append(_critical("symbol_missing", "Instruction symbol must be non-empty."))
    if instruction.side not in {ActionSide.BUY.value, ActionSide.SELL.value}:
        if instruction.side == ActionSide.HOLD.value:
            flags.append(_critical("hold_instruction_not_allowed", "HOLD must not reach dry-run."))
        else:
            flags.append(_critical("unsupported_side", "Dry-run side must be BUY or SELL."))
    if instruction.quantity <= 0:
        flags.append(_critical("quantity_not_positive", "Instruction quantity must be positive."))
    if instruction.estimated_price <= 0:
        flags.append(_critical("estimated_price_not_positive", "Estimated price must be positive."))
    expected_notional = round(instruction.quantity * instruction.estimated_price, 4)
    if abs(instruction.estimated_notional - expected_notional) > NOTIONAL_TOLERANCE:
        flags.append(
            _critical(
                "estimated_notional_mismatch",
                "Estimated notional must equal quantity times estimated price.",
            )
        )
    if not _has_evidence(instruction.evidence_refs):
        flags.append(_critical("evidence_refs_missing", "Instruction evidence is required."))
    if (
        instruction.side in {ActionSide.BUY.value, ActionSide.SELL.value}
        and instruction.quantity > 0
        and instruction.quantity % 100 != 0
        and not allow_odd_lot
    ):
        flags.append(_critical("a_share_lot_size_invalid", "A-share quantity must be a 100-share lot."))
    return tuple(flags)


def _has_evidence(evidence_refs: tuple[str, ...]) -> bool:
    return any(ref.strip() for ref in evidence_refs)


def _critical(code: str, message: str) -> PaperLedgerDryRunRiskFlag:
    return PaperLedgerDryRunRiskFlag(
        code=code,
        severity=RiskSeverity.CRITICAL.value,
        message=message,
    )
