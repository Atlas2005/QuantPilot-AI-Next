"""Validation helpers for R21 AI action proposal bridge."""

from __future__ import annotations

from quantpilot_core.account_profile_preflight import BrokerFeeProfile
from quantpilot_core.ai_action_paper_bridge.contracts import (
    AIActionBridgeRiskFlag,
    AIActionProposal,
    ActionSide,
    PaperLedgerCandidateInstruction,
    ProposalSource,
    RiskSeverity,
)


def validate_ai_action_proposal(
    proposal: AIActionProposal,
    *,
    allow_odd_lot: bool = False,
) -> tuple[AIActionBridgeRiskFlag, ...]:
    """Validate proposal shape before account-aware bridge checks."""

    flags: list[AIActionBridgeRiskFlag] = []
    side = proposal.side
    if not proposal.proposal_id.strip():
        flags.append(_critical("proposal_id_missing", "Proposal ID must be non-empty."))
    if proposal.source not in {source.value for source in ProposalSource}:
        flags.append(_critical("proposal_source_invalid", "Proposal source is unsupported."))
    if side not in {action_side.value for action_side in ActionSide}:
        flags.append(_critical("side_invalid", "Proposal side must be BUY, SELL, or HOLD."))
    if side in {ActionSide.BUY.value, ActionSide.SELL.value} and not proposal.symbol.strip():
        flags.append(_critical("symbol_missing", "BUY/SELL proposal symbol must be non-empty."))
    if side in {ActionSide.BUY.value, ActionSide.SELL.value} and proposal.quantity <= 0:
        flags.append(_critical("quantity_not_positive", "BUY/SELL quantity must be positive."))
    if side == ActionSide.HOLD.value and proposal.quantity != 0:
        flags.append(_critical("hold_quantity_not_zero", "HOLD quantity must be zero."))
    if side in {ActionSide.BUY.value, ActionSide.SELL.value} and proposal.estimated_price <= 0:
        flags.append(_critical("estimated_price_not_positive", "Estimated price must be positive."))
    if proposal.limit_price is not None and proposal.limit_price <= 0:
        flags.append(_critical("limit_price_not_positive", "Limit price must be positive when provided."))
    if not 0 <= proposal.confidence <= 1:
        flags.append(_critical("confidence_out_of_range", "Confidence must be in [0, 1]."))
    if not proposal.rationale.strip():
        flags.append(_critical("rationale_missing", "Proposal rationale must be non-empty."))
    if not _has_evidence(proposal.evidence_refs):
        flags.append(_critical("evidence_refs_missing", "Proposal evidence is required."))
    if (
        side in {ActionSide.BUY.value, ActionSide.SELL.value}
        and proposal.quantity > 0
        and proposal.quantity % 100 != 0
        and not allow_odd_lot
    ):
        flags.append(_critical("a_share_lot_size_invalid", "A-share quantity must be a 100-share lot."))
    return tuple(flags)


def estimate_trade_cost(
    proposal: AIActionProposal,
    broker_fee_profile: BrokerFeeProfile,
) -> float:
    """Estimate conservative trade costs for a candidate paper instruction."""

    if proposal.side not in {ActionSide.BUY.value, ActionSide.SELL.value}:
        return 0.0
    estimated_notional = _estimated_notional(proposal)
    if estimated_notional <= 0:
        return 0.0
    commission = max(
        estimated_notional * broker_fee_profile.commission_rate,
        broker_fee_profile.min_commission,
    )
    stamp_tax = (
        estimated_notional * broker_fee_profile.stamp_tax_rate
        if proposal.side == ActionSide.SELL.value
        else 0.0
    )
    transfer_fee = estimated_notional * broker_fee_profile.transfer_fee_rate
    slippage = estimated_notional * broker_fee_profile.slippage_bps / 10_000
    return round(commission + stamp_tax + transfer_fee + slippage, 4)


def to_paper_ledger_candidate(
    proposal: AIActionProposal,
    *,
    reason: str,
) -> PaperLedgerCandidateInstruction:
    """Convert a valid executable proposal into a candidate instruction only."""

    return PaperLedgerCandidateInstruction(
        proposal_id=proposal.proposal_id,
        symbol=proposal.symbol,
        side=proposal.side,
        quantity=proposal.quantity,
        estimated_price=proposal.estimated_price,
        limit_price=proposal.limit_price,
        estimated_notional=_estimated_notional(proposal),
        reason=reason,
        evidence_refs=proposal.evidence_refs,
    )


def _estimated_notional(proposal: AIActionProposal) -> float:
    return round(proposal.quantity * proposal.estimated_price, 4)


def _has_evidence(evidence_refs: tuple[str, ...]) -> bool:
    return any(ref.strip() for ref in evidence_refs)


def _critical(code: str, message: str) -> AIActionBridgeRiskFlag:
    return AIActionBridgeRiskFlag(
        code=code,
        severity=RiskSeverity.CRITICAL.value,
        message=message,
    )
