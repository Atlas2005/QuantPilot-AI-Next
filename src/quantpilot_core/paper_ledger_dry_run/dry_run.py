"""In-memory paper ledger dry-run integration for R22."""

from __future__ import annotations

from typing import Iterable

from quantpilot_core.account_profile_preflight import (
    AccountProfile,
    AccountStatus,
    RiskSeverity as AccountRiskSeverity,
    normalize_sellable_quantities,
    run_account_profile_preflight,
)
from quantpilot_core.ai_action_paper_bridge import ActionSide, PaperLedgerCandidateInstruction
from quantpilot_core.paper_ledger_dry_run.contracts import (
    PaperLedgerDryRunDecision,
    PaperLedgerDryRunInstructionResult,
    PaperLedgerDryRunInstructionStatus,
    PaperLedgerDryRunResult,
    PaperLedgerDryRunRiskFlag,
    RiskSeverity,
)
from quantpilot_core.paper_ledger_dry_run.preflight import validate_dry_run_instruction


def simulate_instruction(
    instruction: PaperLedgerCandidateInstruction,
    account_profile: AccountProfile,
    current_cash: float,
    current_positions: dict[str, int],
    *,
    allow_odd_lot: bool = False,
) -> PaperLedgerDryRunInstructionResult:
    """Simulate one candidate instruction without mutating account inputs."""

    flags = list(validate_dry_run_instruction(instruction, allow_odd_lot=allow_odd_lot))
    if account_profile.status in {
        AccountStatus.READ_ONLY.value,
        AccountStatus.SUSPENDED.value,
        AccountStatus.KILL_SWITCHED.value,
    }:
        flags.append(_critical("account_status_blocks_trade", "Account status blocks BUY/SELL dry-run."))

    fee = _estimate_instruction_cost(instruction, account_profile)
    if not flags:
        if instruction.side == ActionSide.BUY.value:
            cash_delta = -round(instruction.estimated_notional + fee, 4)
            if current_cash + cash_delta < 0:
                flags.append(_critical("buy_cash_insufficient", "BUY dry-run would make cash negative."))
        elif instruction.side == ActionSide.SELL.value:
            sellable = min(
                normalize_sellable_quantities(account_profile).get(instruction.symbol, 0),
                current_positions.get(instruction.symbol, 0),
            )
            if instruction.quantity > sellable:
                flags.append(
                    _critical(
                        "sellable_quantity_insufficient",
                        "SELL dry-run exceeds sellable quantity.",
                    )
                )

    if flags:
        return _instruction_result(
            instruction,
            status=PaperLedgerDryRunInstructionStatus.REJECTED.value,
            reason=";".join(flag.code for flag in flags),
            cash_delta=0.0,
            position_delta=0,
            flags=tuple(flags),
        )

    if instruction.side == ActionSide.BUY.value:
        return _instruction_result(
            instruction,
            status=PaperLedgerDryRunInstructionStatus.SIMULATED.value,
            reason="simulated_buy",
            cash_delta=-round(instruction.estimated_notional + fee, 4),
            position_delta=instruction.quantity,
            flags=(),
        )

    return _instruction_result(
        instruction,
        status=PaperLedgerDryRunInstructionStatus.SIMULATED.value,
        reason="simulated_sell",
        cash_delta=round(instruction.estimated_notional - fee, 4),
        position_delta=-instruction.quantity,
        flags=(),
    )


def run_paper_ledger_dry_run(
    instructions: Iterable[PaperLedgerCandidateInstruction],
    account_profile: AccountProfile,
    *,
    allow_odd_lot: bool = False,
    fail_fast: bool = False,
) -> PaperLedgerDryRunResult:
    """Run deterministic in-memory paper ledger simulation for candidate instructions."""

    instruction_list = tuple(instructions)
    current_cash = account_profile.cash.available_cash
    current_positions = {
        position.symbol: position.quantity for position in account_profile.positions
    }
    account_preflight = run_account_profile_preflight(account_profile)
    if not account_preflight.ok:
        flags = tuple(
            _critical(
                f"account_preflight:{flag.code}",
                f"Account preflight failed: {flag.message}",
            )
            for flag in account_preflight.risk_flags
            if flag.severity == AccountRiskSeverity.CRITICAL.value
        )
        return PaperLedgerDryRunResult(
            ok=False,
            decision=PaperLedgerDryRunDecision.BLOCKED.value,
            reason="account_preflight_failed",
            instruction_results=(),
            simulated_cash_after=current_cash,
            simulated_positions_after=current_positions,
            blocked_instruction_ids=tuple(instruction.proposal_id for instruction in instruction_list),
            risk_flags=flags,
        )

    results: list[PaperLedgerDryRunInstructionResult] = []
    risk_flags: list[PaperLedgerDryRunRiskFlag] = []
    blocked_ids: list[str] = []
    seen_ids: set[str] = set()
    skipping = False

    for instruction in instruction_list:
        if skipping:
            results.append(_skipped_result(instruction))
            continue

        duplicate_flags: tuple[PaperLedgerDryRunRiskFlag, ...] = ()
        if instruction.proposal_id in seen_ids:
            duplicate_flags = (
                _critical("duplicate_proposal_id", "Duplicate proposal ID is not allowed."),
            )
        else:
            seen_ids.add(instruction.proposal_id)

        if duplicate_flags:
            result = _instruction_result(
                instruction,
                status=PaperLedgerDryRunInstructionStatus.REJECTED.value,
                reason="duplicate_proposal_id",
                cash_delta=0.0,
                position_delta=0,
                flags=duplicate_flags,
            )
        else:
            result = simulate_instruction(
                instruction,
                account_profile,
                current_cash,
                current_positions,
                allow_odd_lot=allow_odd_lot,
            )

        results.append(result)
        risk_flags.extend(result.risk_flags)
        if result.status == PaperLedgerDryRunInstructionStatus.REJECTED.value:
            blocked_ids.append(instruction.proposal_id)
            if fail_fast and _has_critical(result.risk_flags):
                skipping = True
            continue

        current_cash = round(current_cash + result.estimated_cash_delta, 4)
        current_positions[instruction.symbol] = (
            current_positions.get(instruction.symbol, 0)
            + result.estimated_position_delta
        )

    simulated_count = sum(
        result.status == PaperLedgerDryRunInstructionStatus.SIMULATED.value
        for result in results
    )
    rejected_count = sum(
        result.status == PaperLedgerDryRunInstructionStatus.REJECTED.value
        for result in results
    )

    if rejected_count == 0:
        decision = PaperLedgerDryRunDecision.ACCEPTED.value
        reason = "ok"
        ok = True
    elif fail_fast or simulated_count == 0:
        decision = PaperLedgerDryRunDecision.BLOCKED.value
        reason = "critical_risk_flags"
        ok = False
    else:
        decision = PaperLedgerDryRunDecision.PARTIAL.value
        reason = "partial_simulation"
        ok = False

    return PaperLedgerDryRunResult(
        ok=ok,
        decision=decision,
        reason=reason,
        instruction_results=tuple(results),
        simulated_cash_after=current_cash,
        simulated_positions_after=current_positions,
        blocked_instruction_ids=_unique(blocked_ids),
        risk_flags=tuple(risk_flags),
    )


def _estimate_instruction_cost(
    instruction: PaperLedgerCandidateInstruction,
    account_profile: AccountProfile,
) -> float:
    if instruction.side not in {ActionSide.BUY.value, ActionSide.SELL.value}:
        return 0.0
    fee = account_profile.broker_fee
    notional = instruction.estimated_notional
    if notional <= 0:
        return 0.0
    commission = max(notional * fee.commission_rate, fee.min_commission)
    stamp_tax = notional * fee.stamp_tax_rate if instruction.side == ActionSide.SELL.value else 0.0
    transfer_fee = notional * fee.transfer_fee_rate
    slippage = notional * fee.slippage_bps / 10_000
    return round(commission + stamp_tax + transfer_fee + slippage, 4)


def _instruction_result(
    instruction: PaperLedgerCandidateInstruction,
    *,
    status: str,
    reason: str,
    cash_delta: float,
    position_delta: int,
    flags: tuple[PaperLedgerDryRunRiskFlag, ...],
) -> PaperLedgerDryRunInstructionResult:
    return PaperLedgerDryRunInstructionResult(
        proposal_id=instruction.proposal_id,
        symbol=instruction.symbol,
        side=instruction.side,
        quantity=instruction.quantity,
        estimated_price=instruction.estimated_price,
        estimated_notional=instruction.estimated_notional,
        status=status,
        reason=reason,
        estimated_cash_delta=round(cash_delta, 4),
        estimated_position_delta=position_delta,
        risk_flags=flags,
        evidence_refs=instruction.evidence_refs,
    )


def _skipped_result(
    instruction: PaperLedgerCandidateInstruction,
) -> PaperLedgerDryRunInstructionResult:
    return _instruction_result(
        instruction,
        status=PaperLedgerDryRunInstructionStatus.SKIPPED.value,
        reason="skipped_after_fail_fast_block",
        cash_delta=0.0,
        position_delta=0,
        flags=(),
    )


def _has_critical(flags: tuple[PaperLedgerDryRunRiskFlag, ...]) -> bool:
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


def _critical(code: str, message: str) -> PaperLedgerDryRunRiskFlag:
    return PaperLedgerDryRunRiskFlag(
        code=code,
        severity=RiskSeverity.CRITICAL.value,
        message=message,
    )
