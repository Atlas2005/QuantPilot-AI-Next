"""Broker sandbox adapter preflight without broker connectivity."""

from __future__ import annotations

from typing import Iterable

from quantpilot_core.account_profile_preflight import (
    AccountProfile,
    AccountStatus,
    BrokerCapability,
    RiskSeverity as AccountRiskSeverity,
    TradePermission,
    normalize_sellable_quantities,
    run_account_profile_preflight,
)
from quantpilot_core.ai_action_paper_bridge import (
    ActionSide,
    PaperLedgerCandidateInstruction,
)
from quantpilot_core.broker_sandbox_adapter_preflight.contracts import (
    BrokerSandboxAdapterDecision,
    BrokerSandboxAdapterMode,
    BrokerSandboxAdapterPreflightResult,
    BrokerSandboxInstruction,
    BrokerSandboxInstructionResult,
    BrokerSandboxInstructionStatus,
    BrokerSandboxRiskFlag,
    BrokerSandboxSeverity,
)
from quantpilot_core.broker_sandbox_adapter_preflight.preflight import (
    validate_broker_sandbox_instruction,
)
from quantpilot_core.small_capital_readiness_gate import (
    ReadinessDecision,
    SmallCapitalReadinessGateResult,
)


def to_broker_sandbox_instruction(
    candidate_instruction: PaperLedgerCandidateInstruction,
    *,
    instruction_id: str,
    mode: str = BrokerSandboxAdapterMode.BROKER_SANDBOX.value,
) -> BrokerSandboxInstruction:
    """Convert an R21/R22 candidate instruction into a broker sandbox handoff record."""

    return BrokerSandboxInstruction(
        instruction_id=instruction_id,
        proposal_id=candidate_instruction.proposal_id,
        symbol=candidate_instruction.symbol,
        side=candidate_instruction.side,
        quantity=candidate_instruction.quantity,
        estimated_price=candidate_instruction.estimated_price,
        limit_price=candidate_instruction.limit_price,
        estimated_notional=candidate_instruction.estimated_notional,
        mode=mode,
        evidence_refs=candidate_instruction.evidence_refs,
    )


def run_broker_sandbox_adapter_preflight(
    instructions: Iterable[BrokerSandboxInstruction],
    account_profile: AccountProfile,
    readiness_result: SmallCapitalReadinessGateResult | None,
    *,
    allow_odd_lot: bool = False,
) -> BrokerSandboxAdapterPreflightResult:
    """Validate sandbox handoff records without touching any broker system."""

    instruction_list = tuple(instructions)
    global_flags = list(_validate_global_inputs(account_profile, readiness_result))
    readiness_decision = getattr(readiness_result, "decision", None)
    account_preflight = run_account_profile_preflight(account_profile)
    if not account_preflight.ok:
        global_flags.extend(
            _critical(
                f"account_preflight:{flag.code}",
                f"Account preflight failed: {flag.message}",
            )
            for flag in account_preflight.risk_flags
            if flag.severity == AccountRiskSeverity.CRITICAL.value
        )

    instruction_results: list[BrokerSandboxInstructionResult] = []
    for instruction in instruction_list:
        flags = list(validate_broker_sandbox_instruction(instruction, allow_odd_lot=allow_odd_lot))
        flags.extend(_mode_and_readiness_flags(instruction, readiness_decision))
        flags.extend(_account_instruction_flags(instruction, account_profile))

        if flags:
            status = (
                BrokerSandboxInstructionStatus.SKIPPED.value
                if instruction.side == ActionSide.HOLD.value
                and all(flag.code == "hold_instruction_skipped" for flag in flags)
                else BrokerSandboxInstructionStatus.REJECTED.value
            )
            reason = ";".join(flag.code for flag in flags)
        elif instruction.mode == BrokerSandboxAdapterMode.BROKER_SANDBOX.value:
            status = BrokerSandboxInstructionStatus.ACCEPTED_FOR_SANDBOX.value
            reason = "accepted_for_broker_sandbox_preflight"
        else:
            status = BrokerSandboxInstructionStatus.SKIPPED.value
            reason = "non_executable_mode_skipped"

        instruction_results.append(
            BrokerSandboxInstructionResult(
                instruction_id=instruction.instruction_id,
                proposal_id=instruction.proposal_id,
                symbol=instruction.symbol,
                side=instruction.side,
                quantity=instruction.quantity,
                status=status,
                reason=reason,
                risk_flags=tuple(flags),
                evidence_refs=instruction.evidence_refs,
            )
        )

    all_flags = tuple(global_flags) + tuple(
        flag for result in instruction_results for flag in result.risk_flags
    )
    accepted_ids = tuple(
        result.instruction_id
        for result in instruction_results
        if result.status == BrokerSandboxInstructionStatus.ACCEPTED_FOR_SANDBOX.value
    )
    blocked_ids = tuple(
        result.instruction_id
        for result in instruction_results
        if result.status == BrokerSandboxInstructionStatus.REJECTED.value
    )
    manual_ids = tuple(
        result.instruction_id
        for result in instruction_results
        if any(flag.severity in {BrokerSandboxSeverity.HIGH.value, BrokerSandboxSeverity.MEDIUM.value} for flag in result.risk_flags)
    )

    if any(flag.severity == BrokerSandboxSeverity.CRITICAL.value for flag in all_flags):
        decision = BrokerSandboxAdapterDecision.BLOCKED.value
        reason = "critical_risk_flags"
    elif manual_ids or readiness_decision == ReadinessDecision.MANUAL_REVIEW.value:
        decision = BrokerSandboxAdapterDecision.MANUAL_REVIEW.value
        reason = "manual_review_required"
    elif accepted_ids:
        decision = BrokerSandboxAdapterDecision.READY.value
        reason = "ready"
    else:
        decision = BrokerSandboxAdapterDecision.MANUAL_REVIEW.value
        reason = "no_executable_broker_sandbox_instructions"

    return BrokerSandboxAdapterPreflightResult(
        ok=decision == BrokerSandboxAdapterDecision.READY.value,
        decision=decision,
        reason=reason,
        instruction_results=tuple(instruction_results),
        accepted_instruction_ids=accepted_ids,
        blocked_instruction_ids=blocked_ids,
        manual_review_instruction_ids=manual_ids,
        risk_flags=all_flags,
    )


def _validate_global_inputs(
    account_profile: AccountProfile,
    readiness_result: SmallCapitalReadinessGateResult | None,
) -> tuple[BrokerSandboxRiskFlag, ...]:
    flags: list[BrokerSandboxRiskFlag] = []
    if readiness_result is None:
        flags.append(_critical("readiness_result_missing", "Readiness gate result is required."))
    elif readiness_result.decision == ReadinessDecision.FAIL.value:
        flags.append(_critical("readiness_failed", "Readiness FAIL blocks broker sandbox handoff."))
    if account_profile.status in {
        AccountStatus.READ_ONLY.value,
        AccountStatus.SUSPENDED.value,
        AccountStatus.KILL_SWITCHED.value,
    }:
        flags.append(_critical("account_status_blocks_trade", "Account status blocks BUY/SELL sandbox acceptance."))
    if _is_a_share_market(account_profile.broker_capability.market) and (
        BrokerCapability.A_SHARE_CASH_EQUITY.value not in set(account_profile.broker_capability.capabilities)
    ):
        flags.append(
            _critical(
                "a_share_cash_equity_capability_missing",
                "A-share sandbox handoff requires A_SHARE_CASH_EQUITY capability.",
            )
        )
    return tuple(flags)


def _mode_and_readiness_flags(
    instruction: BrokerSandboxInstruction,
    readiness_decision: str | None,
) -> tuple[BrokerSandboxRiskFlag, ...]:
    flags: list[BrokerSandboxRiskFlag] = []
    if instruction.side == ActionSide.HOLD.value:
        flags.append(_low("hold_instruction_skipped", "HOLD is skipped and never executable."))
    if instruction.mode == BrokerSandboxAdapterMode.PAPER_ONLY.value:
        flags.append(_medium("paper_only_not_broker_ready", "PAPER_ONLY cannot claim broker sandbox readiness."))
    if instruction.mode == BrokerSandboxAdapterMode.READ_ONLY_CHECK.value:
        flags.append(_medium("read_only_check_not_executable", "READ_ONLY_CHECK is non-executable."))
    if instruction.mode == BrokerSandboxAdapterMode.BROKER_SANDBOX.value:
        if readiness_decision == ReadinessDecision.MANUAL_REVIEW.value:
            flags.append(_high("readiness_manual_review", "Readiness MANUAL_REVIEW requires human review."))
        elif readiness_decision != ReadinessDecision.PASS.value:
            flags.append(_critical("readiness_not_pass", "BROKER_SANDBOX requires readiness PASS."))
    return tuple(flags)


def _account_instruction_flags(
    instruction: BrokerSandboxInstruction,
    account_profile: AccountProfile,
) -> tuple[BrokerSandboxRiskFlag, ...]:
    flags: list[BrokerSandboxRiskFlag] = []
    permissions = set(account_profile.broker_capability.permissions)
    if TradePermission.QUERY_ONLY.value in permissions and instruction.mode != BrokerSandboxAdapterMode.READ_ONLY_CHECK.value:
        flags.append(_critical("query_only_requires_read_only_check", "QUERY_ONLY only allows READ_ONLY_CHECK mode."))
    if instruction.mode != BrokerSandboxAdapterMode.BROKER_SANDBOX.value:
        return tuple(flags)
    if instruction.side == ActionSide.BUY.value and TradePermission.BUY.value not in permissions:
        flags.append(_critical("buy_permission_missing", "BUY requires BUY permission."))
    if instruction.side == ActionSide.SELL.value and TradePermission.SELL.value not in permissions:
        flags.append(_critical("sell_permission_missing", "SELL requires SELL permission."))
    if instruction.side == ActionSide.BUY.value:
        if instruction.estimated_notional + _estimate_cost(instruction, account_profile) > account_profile.cash.available_cash:
            flags.append(_critical("buy_cash_insufficient", "BUY notional plus fees exceeds available cash."))
    if instruction.side == ActionSide.SELL.value:
        sellable = normalize_sellable_quantities(account_profile).get(instruction.symbol, 0)
        if instruction.quantity > sellable:
            flags.append(_critical("sellable_quantity_insufficient", "SELL quantity exceeds sellable quantity."))
    return tuple(flags)


def _estimate_cost(
    instruction: BrokerSandboxInstruction,
    account_profile: AccountProfile,
) -> float:
    if instruction.side not in {ActionSide.BUY.value, ActionSide.SELL.value}:
        return 0.0
    fee = account_profile.broker_fee
    notional = instruction.estimated_notional
    commission = max(notional * fee.commission_rate, fee.min_commission)
    stamp_tax = notional * fee.stamp_tax_rate if instruction.side == ActionSide.SELL.value else 0.0
    transfer_fee = notional * fee.transfer_fee_rate
    slippage = notional * fee.slippage_bps / 10_000
    return round(commission + stamp_tax + transfer_fee + slippage, 4)


def _is_a_share_market(market: str) -> bool:
    normalized = market.strip().lower().replace("-", "_")
    return normalized in {"a_share", "ashare", "cn_a_share", "china_a_share"}


def _critical(code: str, message: str) -> BrokerSandboxRiskFlag:
    return BrokerSandboxRiskFlag(code=code, severity=BrokerSandboxSeverity.CRITICAL.value, message=message)


def _high(code: str, message: str) -> BrokerSandboxRiskFlag:
    return BrokerSandboxRiskFlag(code=code, severity=BrokerSandboxSeverity.HIGH.value, message=message)


def _medium(code: str, message: str) -> BrokerSandboxRiskFlag:
    return BrokerSandboxRiskFlag(code=code, severity=BrokerSandboxSeverity.MEDIUM.value, message=message)


def _low(code: str, message: str) -> BrokerSandboxRiskFlag:
    return BrokerSandboxRiskFlag(code=code, severity=BrokerSandboxSeverity.LOW.value, message=message)
