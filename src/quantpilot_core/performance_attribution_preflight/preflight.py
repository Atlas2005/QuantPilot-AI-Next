"""Validation helpers for R24 performance attribution preflight."""

from __future__ import annotations

import math

from quantpilot_core.multi_day_paper_replay import PaperReplayDayStatus
from quantpilot_core.paper_ledger_dry_run import PaperLedgerDryRunInstructionStatus
from quantpilot_core.performance_attribution_preflight.contracts import (
    AttributionSeverity,
    PerformanceAttributionRiskFlag,
)


def validate_performance_attribution_input(
    replay_result: object | None,
) -> tuple[PerformanceAttributionRiskFlag, ...]:
    """Validate replay output shape before attribution records are derived."""

    flags: list[PerformanceAttributionRiskFlag] = []
    if replay_result is None:
        return (_critical("replay_result_missing", "Replay result is required."),)
    if not getattr(replay_result, "day_results", ()):
        flags.append(_critical("day_results_missing", "Replay result must include day_results."))
    final_cash = getattr(replay_result, "final_cash", None)
    if not isinstance(final_cash, (int, float)) or not math.isfinite(float(final_cash)):
        flags.append(_critical("final_cash_not_finite", "Replay final_cash must be finite."))

    valid_day_statuses = {status.value for status in PaperReplayDayStatus}
    valid_instruction_statuses = {
        status.value for status in PaperLedgerDryRunInstructionStatus
    }
    for day_index, day in enumerate(getattr(replay_result, "day_results", ())):
        if not getattr(day, "trading_date", "").strip():
            flags.append(_critical(f"day[{day_index}]:trading_date_missing", "Trading date is required."))
        if getattr(day, "status", None) not in valid_day_statuses:
            flags.append(_critical(f"day[{day_index}]:status_invalid", "Day status is not recognized."))
        dry_run = getattr(day, "dry_run_result", None)
        for instruction_index, instruction in enumerate(getattr(dry_run, "instruction_results", ())):
            prefix = f"day[{day_index}].instruction[{instruction_index}]"
            if not getattr(instruction, "proposal_id", "").strip():
                flags.append(_critical(f"{prefix}:proposal_id_missing", "Proposal ID is required."))
            if not getattr(instruction, "symbol", "").strip():
                flags.append(_critical(f"{prefix}:symbol_missing", "Symbol is required."))
            if not getattr(instruction, "side", "").strip():
                flags.append(_critical(f"{prefix}:side_missing", "Side is required."))
            if not isinstance(getattr(instruction, "quantity", None), int):
                flags.append(_critical(f"{prefix}:quantity_invalid", "Quantity must be an integer."))
            if not _finite_positive(getattr(instruction, "estimated_price", None)):
                flags.append(_critical(f"{prefix}:estimated_price_invalid", "Estimated price must be positive."))
            if not _finite_non_negative(getattr(instruction, "estimated_notional", None)):
                flags.append(_critical(f"{prefix}:estimated_notional_invalid", "Estimated notional must be non-negative."))
            if getattr(instruction, "status", None) not in valid_instruction_statuses:
                flags.append(_critical(f"{prefix}:status_invalid", "Instruction status is not recognized."))
            if not _has_evidence(getattr(instruction, "evidence_refs", ())):
                flags.append(_critical(f"{prefix}:evidence_refs_missing", "Instruction evidence is required."))
    return tuple(flags)


def _finite_positive(value: object) -> bool:
    return isinstance(value, (int, float)) and math.isfinite(float(value)) and float(value) > 0


def _finite_non_negative(value: object) -> bool:
    return isinstance(value, (int, float)) and math.isfinite(float(value)) and float(value) >= 0


def _has_evidence(evidence_refs: tuple[str, ...]) -> bool:
    return any(ref.strip() for ref in evidence_refs)


def _critical(code: str, message: str) -> PerformanceAttributionRiskFlag:
    return PerformanceAttributionRiskFlag(
        code=code,
        severity=AttributionSeverity.CRITICAL.value,
        message=message,
    )
