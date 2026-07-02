"""Deterministic multi-day paper replay built on R22 dry-run."""

from __future__ import annotations

from dataclasses import replace
from typing import Iterable

from quantpilot_core.account_profile_preflight import (
    AccountCashProfile,
    AccountPosition,
    AccountProfile,
    normalize_sellable_quantities,
)
from quantpilot_core.ai_action_paper_bridge import ActionSide
from quantpilot_core.config.legacy_engine import require_legacy_engine
from quantpilot_core.paper_ledger_dry_run import (
    PaperLedgerDryRunDecision,
    PaperLedgerDryRunInstructionStatus,
    run_paper_ledger_dry_run,
)
from quantpilot_core.multi_day_paper_replay.contracts import (
    PaperReplayDayInput,
    PaperReplayDayResult,
    PaperReplayDayStatus,
    PaperReplayDecision,
    PaperReplayResult,
    PaperReplayRiskFlag,
    RiskSeverity,
)
from quantpilot_core.multi_day_paper_replay.preflight import validate_replay_inputs


def run_multi_day_paper_replay(
    days: Iterable[PaperReplayDayInput],
    account_profile: AccountProfile,
    *,
    allow_odd_lot: bool = False,
    fail_fast: bool = False,
    use_legacy_engine: bool | None = None,
) -> PaperReplayResult:
    """Replay candidate paper instructions day by day without persistence."""

    require_legacy_engine(use_legacy_engine)
    day_inputs = tuple(days)
    input_flags = validate_replay_inputs(day_inputs, account_profile)
    initial_cash = account_profile.cash.available_cash
    initial_positions = _initial_positions(account_profile)
    if _has_critical(input_flags):
        return PaperReplayResult(
            ok=False,
            decision=PaperReplayDecision.BLOCKED.value,
            reason="replay_input_preflight_failed",
            day_results=(),
            final_cash=initial_cash,
            final_positions=initial_positions,
            blocked_days=tuple(day.trading_date for day in day_inputs),
            risk_flags=input_flags,
        )

    current_cash = initial_cash
    current_positions = dict(initial_positions)
    sellable_by_symbol = normalize_sellable_quantities(account_profile)
    pending_sellable_next_day: dict[str, int] = {}
    day_results: list[PaperReplayDayResult] = []
    risk_flags: list[PaperReplayRiskFlag] = list(input_flags)
    blocked_days: list[str] = []
    skipping = False

    for day in day_inputs:
        _release_pending_buys(sellable_by_symbol, pending_sellable_next_day)
        cash_start = current_cash
        positions_start = dict(current_positions)

        if skipping:
            day_results.append(
                PaperReplayDayResult(
                    trading_date=day.trading_date,
                    status=PaperReplayDayStatus.SKIPPED.value,
                    reason="skipped_after_fail_fast_block",
                    dry_run_result=None,
                    cash_start=cash_start,
                    cash_end=cash_start,
                    positions_start=positions_start,
                    positions_end=positions_start,
                    blocked_instruction_ids=tuple(
                        instruction.proposal_id for instruction in day.instructions
                    ),
                    risk_flags=(),
                )
            )
            continue

        daily_profile = _build_daily_account_profile(
            account_profile,
            cash=current_cash,
            positions=current_positions,
            sellable_by_symbol=sellable_by_symbol,
        )
        dry_run_result = run_paper_ledger_dry_run(
            day.instructions,
            daily_profile,
            allow_odd_lot=allow_odd_lot,
            fail_fast=fail_fast,
        )
        mapped_flags = _map_dry_run_flags(day.trading_date, dry_run_result.risk_flags)
        risk_flags.extend(mapped_flags)

        if dry_run_result.decision == PaperLedgerDryRunDecision.ACCEPTED.value:
            status = PaperReplayDayStatus.SIMULATED.value
        elif dry_run_result.decision == PaperLedgerDryRunDecision.PARTIAL.value:
            status = PaperReplayDayStatus.PARTIAL.value
            blocked_days.append(day.trading_date)
        else:
            status = PaperReplayDayStatus.BLOCKED.value
            blocked_days.append(day.trading_date)

        if status in {
            PaperReplayDayStatus.SIMULATED.value,
            PaperReplayDayStatus.PARTIAL.value,
        }:
            current_cash, current_positions = _carry_successful_results(
                dry_run_result,
                current_cash,
                current_positions,
                sellable_by_symbol,
                pending_sellable_next_day,
            )

        day_results.append(
            PaperReplayDayResult(
                trading_date=day.trading_date,
                status=status,
                reason=dry_run_result.reason,
                dry_run_result=dry_run_result,
                cash_start=cash_start,
                cash_end=current_cash,
                positions_start=positions_start,
                positions_end=dict(current_positions),
                blocked_instruction_ids=dry_run_result.blocked_instruction_ids,
                risk_flags=mapped_flags,
            )
        )
        if fail_fast and status == PaperReplayDayStatus.BLOCKED.value:
            skipping = True

    simulated_or_partial_days = sum(
        result.status in {
            PaperReplayDayStatus.SIMULATED.value,
            PaperReplayDayStatus.PARTIAL.value,
        }
        for result in day_results
    )

    if not blocked_days:
        decision = PaperReplayDecision.COMPLETED.value
        reason = "ok"
        ok = True
    elif fail_fast or simulated_or_partial_days == 0:
        decision = PaperReplayDecision.BLOCKED.value
        reason = "blocked_days"
        ok = False
    else:
        decision = PaperReplayDecision.PARTIAL.value
        reason = "partial_replay"
        ok = False

    return PaperReplayResult(
        ok=ok,
        decision=decision,
        reason=reason,
        day_results=tuple(day_results),
        final_cash=current_cash,
        final_positions=dict(current_positions),
        blocked_days=tuple(blocked_days),
        risk_flags=tuple(risk_flags),
    )


def _initial_positions(account_profile: AccountProfile) -> dict[str, int]:
    return {position.symbol: position.quantity for position in account_profile.positions}


def _has_critical(flags: tuple[PaperReplayRiskFlag, ...]) -> bool:
    return any(flag.severity == RiskSeverity.CRITICAL.value for flag in flags)


def _build_daily_account_profile(
    account_profile: AccountProfile,
    *,
    cash: float,
    positions: dict[str, int],
    sellable_by_symbol: dict[str, int],
) -> AccountProfile:
    existing_by_symbol = {position.symbol: position for position in account_profile.positions}
    daily_positions: list[AccountPosition] = []
    for symbol in sorted(positions):
        existing = existing_by_symbol.get(symbol)
        if existing is None:
            daily_positions.append(
                AccountPosition(
                    symbol=symbol,
                    quantity=positions[symbol],
                    sellable_quantity=sellable_by_symbol.get(symbol, 0),
                    avg_cost=0.0,
                    market_value=0.0,
                    industry=None,
                )
            )
        else:
            daily_positions.append(
                replace(
                    existing,
                    quantity=positions[symbol],
                    sellable_quantity=sellable_by_symbol.get(symbol, 0),
                )
            )
    return replace(
        account_profile,
        cash=AccountCashProfile(
            currency=account_profile.cash.currency,
            available_cash=cash,
            frozen_cash=account_profile.cash.frozen_cash,
            total_equity=max(account_profile.cash.total_equity, cash),
        ),
        positions=tuple(daily_positions),
    )


def _carry_successful_results(
    dry_run_result,
    current_cash: float,
    current_positions: dict[str, int],
    sellable_by_symbol: dict[str, int],
    pending_sellable_next_day: dict[str, int],
) -> tuple[float, dict[str, int]]:
    updated_cash = current_cash
    updated_positions = dict(current_positions)
    for instruction_result in dry_run_result.instruction_results:
        if instruction_result.status != PaperLedgerDryRunInstructionStatus.SIMULATED.value:
            continue
        updated_cash = round(updated_cash + instruction_result.estimated_cash_delta, 4)
        updated_positions[instruction_result.symbol] = (
            updated_positions.get(instruction_result.symbol, 0)
            + instruction_result.estimated_position_delta
        )
        if instruction_result.side == ActionSide.BUY.value:
            pending_sellable_next_day[instruction_result.symbol] = (
                pending_sellable_next_day.get(instruction_result.symbol, 0)
                + instruction_result.quantity
            )
        elif instruction_result.side == ActionSide.SELL.value:
            sellable_by_symbol[instruction_result.symbol] = max(
                0,
                sellable_by_symbol.get(instruction_result.symbol, 0)
                - instruction_result.quantity,
            )
    return updated_cash, updated_positions


def _release_pending_buys(
    sellable_by_symbol: dict[str, int],
    pending_sellable_next_day: dict[str, int],
) -> None:
    for symbol, quantity in pending_sellable_next_day.items():
        sellable_by_symbol[symbol] = sellable_by_symbol.get(symbol, 0) + quantity
    pending_sellable_next_day.clear()


def _map_dry_run_flags(
    trading_date: str,
    dry_run_flags,
) -> tuple[PaperReplayRiskFlag, ...]:
    return tuple(
        PaperReplayRiskFlag(
            code=f"{trading_date}:{flag.code}",
            severity=flag.severity,
            message=flag.message,
        )
        for flag in dry_run_flags
    )
