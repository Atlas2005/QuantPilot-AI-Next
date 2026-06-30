"""Bridge AI action proposals into paper-ledger candidate instructions."""

from __future__ import annotations

from typing import Iterable

from quantpilot_core.account_profile_preflight import (
    AccountProfile,
    AccountStatus,
    RiskSeverity as AccountRiskSeverity,
    TradePermission,
    run_account_profile_preflight,
)
from quantpilot_core.ai_action_paper_bridge.contracts import (
    AIActionBridgeRiskFlag,
    AIActionPaperBridgeResult,
    AIActionProposal,
    ActionSide,
    BridgeDecision,
    PaperLedgerCandidateInstruction,
    RiskSeverity,
)
from quantpilot_core.ai_action_paper_bridge.preflight import (
    estimate_trade_cost,
    to_paper_ledger_candidate,
    validate_ai_action_proposal,
)


def run_ai_action_paper_bridge(
    proposals: Iterable[AIActionProposal],
    account_profile: AccountProfile,
    *,
    min_confidence: float = 0.6,
    allow_odd_lot: bool = False,
) -> AIActionPaperBridgeResult:
    """Validate proposals and emit paper-ledger candidate instructions only."""

    proposal_list = tuple(proposals)
    risk_flags: list[AIActionBridgeRiskFlag] = []
    blocked_proposals: list[str] = []
    accepted_instructions: list[PaperLedgerCandidateInstruction] = []
    manual_review = False

    account_preflight = run_account_profile_preflight(account_profile)
    if not account_preflight.ok:
        risk_flags.extend(
            _critical(
                f"account_preflight:{flag.code}",
                f"Account preflight failed: {flag.message}",
            )
            for flag in account_preflight.risk_flags
            if flag.severity == AccountRiskSeverity.CRITICAL.value
        )
        return AIActionPaperBridgeResult(
            ok=False,
            decision=BridgeDecision.BLOCKED.value,
            reason="account_preflight_failed",
            accepted_instructions=(),
            blocked_proposals=_proposal_ids(proposal_list),
            risk_flags=tuple(risk_flags),
        )

    for proposal in proposal_list:
        proposal_flags = list(
            validate_ai_action_proposal(proposal, allow_odd_lot=allow_odd_lot)
        )
        if proposal.confidence < min_confidence and 0 <= proposal.confidence <= 1:
            proposal_flags.append(
                _high(
                    "confidence_below_threshold",
                    f"{proposal.proposal_id} confidence is below minimum threshold.",
                )
            )
            manual_review = True

        if proposal_flags:
            risk_flags.extend(proposal_flags)
            if _has_critical(proposal_flags):
                blocked_proposals.append(proposal.proposal_id)
            continue

        if proposal.side == ActionSide.HOLD.value:
            continue

        account_flags = _validate_against_account(proposal, account_profile, account_preflight)
        if account_flags:
            risk_flags.extend(account_flags)
            if _has_critical(account_flags):
                blocked_proposals.append(proposal.proposal_id)
            else:
                manual_review = True
            continue

        accepted_instructions.append(
            to_paper_ledger_candidate(proposal, reason="accepted_for_paper_candidate")
        )

    if _has_critical(risk_flags):
        return AIActionPaperBridgeResult(
            ok=False,
            decision=BridgeDecision.BLOCKED.value,
            reason="critical_risk_flags",
            accepted_instructions=(),
            blocked_proposals=_unique(blocked_proposals),
            risk_flags=tuple(risk_flags),
        )

    if manual_review:
        return AIActionPaperBridgeResult(
            ok=False,
            decision=BridgeDecision.REQUIRES_MANUAL_REVIEW.value,
            reason="manual_review_required",
            accepted_instructions=(),
            blocked_proposals=(),
            risk_flags=tuple(risk_flags),
        )

    return AIActionPaperBridgeResult(
        ok=True,
        decision=BridgeDecision.ACCEPTED_FOR_PAPER.value,
        reason="ok",
        accepted_instructions=tuple(accepted_instructions),
        blocked_proposals=(),
        risk_flags=tuple(risk_flags),
    )


def _validate_against_account(
    proposal: AIActionProposal,
    account_profile: AccountProfile,
    account_preflight,
) -> tuple[AIActionBridgeRiskFlag, ...]:
    flags: list[AIActionBridgeRiskFlag] = []
    permissions = set(account_profile.broker_capability.permissions)
    if proposal.side == ActionSide.BUY.value and TradePermission.BUY.value not in permissions:
        flags.append(_critical("buy_permission_missing", "BUY proposal requires BUY permission."))
    if proposal.side == ActionSide.SELL.value and TradePermission.SELL.value not in permissions:
        flags.append(_critical("sell_permission_missing", "SELL proposal requires SELL permission."))
    if account_profile.status in {
        AccountStatus.READ_ONLY.value,
        AccountStatus.SUSPENDED.value,
        AccountStatus.KILL_SWITCHED.value,
    }:
        flags.append(
            _critical(
                "account_status_blocks_trade",
                "Non-active account status blocks BUY/SELL proposals.",
            )
        )

    estimated_notional = proposal.quantity * proposal.estimated_price
    estimated_cost = estimate_trade_cost(proposal, account_profile.broker_fee)
    if proposal.side == ActionSide.BUY.value:
        cash_required = estimated_notional + estimated_cost
        if cash_required > account_profile.cash.available_cash:
            flags.append(_critical("buy_cash_insufficient", "BUY notional plus fees exceeds available cash."))
    if proposal.side == ActionSide.SELL.value:
        sellable = account_preflight.normalized_sellable_by_symbol.get(proposal.symbol, 0)
        if proposal.quantity > sellable:
            flags.append(_critical("sellable_quantity_insufficient", "SELL quantity exceeds sellable quantity."))

    max_order_value = account_profile.risk_limits.max_order_value
    if max_order_value is not None and estimated_notional > max_order_value:
        flags.append(_critical("max_order_value_breached", "Proposal notional exceeds max_order_value."))
    return tuple(flags)


def _proposal_ids(proposals: tuple[AIActionProposal, ...]) -> tuple[str, ...]:
    return tuple(proposal.proposal_id for proposal in proposals)


def _has_critical(flags: Iterable[AIActionBridgeRiskFlag]) -> bool:
    return any(flag.severity == RiskSeverity.CRITICAL.value for flag in flags)


def _unique(values: Iterable[str]) -> tuple[str, ...]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return tuple(result)


def _critical(code: str, message: str) -> AIActionBridgeRiskFlag:
    return AIActionBridgeRiskFlag(
        code=code,
        severity=RiskSeverity.CRITICAL.value,
        message=message,
    )


def _high(code: str, message: str) -> AIActionBridgeRiskFlag:
    return AIActionBridgeRiskFlag(
        code=code,
        severity=RiskSeverity.HIGH.value,
        message=message,
    )
