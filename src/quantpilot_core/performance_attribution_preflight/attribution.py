"""Deterministic performance attribution over R23 replay outputs."""

from __future__ import annotations

from collections import defaultdict
from typing import Iterable

from quantpilot_core.multi_day_paper_replay import PaperReplayDecision
from quantpilot_core.paper_ledger_dry_run import PaperLedgerDryRunInstructionStatus
from quantpilot_core.performance_attribution_preflight.contracts import (
    AttributionDecision,
    AttributionOutcome,
    AttributionSeverity,
    DayAttributionRecord,
    FeedbackRecord,
    FeedbackTargetType,
    PerformanceAttributionResult,
    PerformanceAttributionRiskFlag,
    ProposalAttributionRecord,
    SourceAttributionRecord,
    SymbolAttributionRecord,
)
from quantpilot_core.performance_attribution_preflight.preflight import (
    validate_performance_attribution_input,
)


def build_proposal_attribution_records(
    replay_result,
) -> tuple[ProposalAttributionRecord, ...]:
    """Flatten replay instruction results into proposal attribution records."""

    records: list[ProposalAttributionRecord] = []
    for day in replay_result.day_results:
        dry_run = day.dry_run_result
        for instruction in getattr(dry_run, "instruction_results", ()):
            records.append(
                ProposalAttributionRecord(
                    proposal_id=instruction.proposal_id,
                    symbol=instruction.symbol,
                    trading_date=day.trading_date,
                    side=instruction.side,
                    quantity=instruction.quantity,
                    estimated_price=instruction.estimated_price,
                    estimated_notional=instruction.estimated_notional,
                    status=instruction.status,
                    estimated_cash_delta=instruction.estimated_cash_delta,
                    estimated_position_delta=instruction.estimated_position_delta,
                    estimated_cost=_estimate_cost(instruction),
                    outcome=_outcome_for_instruction(instruction),
                    reason=instruction.reason,
                    evidence_refs=instruction.evidence_refs,
                )
            )
    return tuple(records)


def aggregate_symbol_attribution(
    proposal_records: Iterable[ProposalAttributionRecord],
) -> tuple[SymbolAttributionRecord, ...]:
    grouped: dict[str, list[ProposalAttributionRecord]] = defaultdict(list)
    for record in proposal_records:
        grouped[record.symbol].append(record)
    return tuple(
        SymbolAttributionRecord(
            symbol=symbol,
            accepted_count=_accepted_count(records),
            blocked_count=_blocked_count(records),
            net_position_delta=sum(record.estimated_position_delta for record in records),
            net_cash_delta=round(sum(record.estimated_cash_delta for record in records), 4),
            estimated_total_cost=round(sum(record.estimated_cost for record in records), 4),
            risk_flags_seen=_risk_codes_from_records(records),
        )
        for symbol, records in sorted(grouped.items())
    )


def aggregate_source_attribution(
    proposal_records: Iterable[ProposalAttributionRecord],
    source_by_proposal_id: dict[str, str] | None = None,
) -> tuple[SourceAttributionRecord, ...]:
    source_map = source_by_proposal_id or {}
    grouped: dict[str, list[ProposalAttributionRecord]] = defaultdict(list)
    for record in proposal_records:
        grouped[source_map.get(record.proposal_id, _source_from_evidence(record.evidence_refs))].append(record)
    return tuple(
        SourceAttributionRecord(
            source=source,
            accepted_count=_accepted_count(records),
            blocked_count=_blocked_count(records),
            manual_review_count=sum(1 for record in records if record.outcome == AttributionOutcome.PARTIAL.value),
            estimated_net_cash_delta=round(sum(record.estimated_cash_delta for record in records), 4),
            estimated_total_cost=round(sum(record.estimated_cost for record in records), 4),
            risk_flags_seen=_risk_codes_from_records(records),
        )
        for source, records in sorted(grouped.items())
    )


def aggregate_day_attribution(
    replay_result,
    proposal_records: Iterable[ProposalAttributionRecord],
) -> tuple[DayAttributionRecord, ...]:
    records_by_day: dict[str, list[ProposalAttributionRecord]] = defaultdict(list)
    for record in proposal_records:
        records_by_day[record.trading_date].append(record)
    return tuple(
        DayAttributionRecord(
            trading_date=day.trading_date,
            status=day.status,
            accepted_count=_accepted_count(records_by_day.get(day.trading_date, ())),
            blocked_count=_blocked_count(records_by_day.get(day.trading_date, ())),
            cash_start=day.cash_start,
            cash_end=day.cash_end,
            estimated_net_cash_delta=round(
                sum(record.estimated_cash_delta for record in records_by_day.get(day.trading_date, ())),
                4,
            ),
            estimated_total_cost=round(
                sum(record.estimated_cost for record in records_by_day.get(day.trading_date, ())),
                4,
            ),
            risk_flags_seen=tuple(flag.code for flag in day.risk_flags),
        )
        for day in replay_result.day_results
    )


def build_feedback_records(
    proposal_records: tuple[ProposalAttributionRecord, ...],
    symbol_records: tuple[SymbolAttributionRecord, ...],
    day_records: tuple[DayAttributionRecord, ...],
    risk_flags: tuple[PerformanceAttributionRiskFlag, ...],
) -> tuple[FeedbackRecord, ...]:
    feedback: list[FeedbackRecord] = []
    for record in proposal_records:
        feedback.append(
            FeedbackRecord(
                target_type=FeedbackTargetType.PROPOSAL.value,
                target_id=record.proposal_id,
                outcome=record.outcome,
                score=_score_for_outcome(record.outcome, record.estimated_cash_delta, record.estimated_notional),
                reason=record.reason,
                evidence_refs=record.evidence_refs,
            )
        )
    for record in symbol_records:
        feedback.append(
            FeedbackRecord(
                target_type=FeedbackTargetType.SYMBOL.value,
                target_id=record.symbol,
                outcome=_cash_outcome(record.net_cash_delta),
                score=_score_from_cash_delta(record.net_cash_delta),
                reason="symbol_attribution",
                evidence_refs=(f"symbol:{record.symbol}",),
            )
        )
    for record in day_records:
        feedback.append(
            FeedbackRecord(
                target_type=FeedbackTargetType.DAY.value,
                target_id=record.trading_date,
                outcome=AttributionOutcome.PARTIAL.value if record.blocked_count else _cash_outcome(record.estimated_net_cash_delta),
                score=-0.5 if record.blocked_count else _score_from_cash_delta(record.estimated_net_cash_delta),
                reason="day_attribution",
                evidence_refs=(f"day:{record.trading_date}",),
            )
        )
    for flag in risk_flags:
        feedback.append(
            FeedbackRecord(
                target_type=FeedbackTargetType.RISK_RULE.value,
                target_id=flag.code,
                outcome=AttributionOutcome.BLOCKED.value,
                score=_score_for_severity(flag.severity),
                reason=flag.message,
                evidence_refs=(f"risk:{flag.code}",),
            )
        )
    return tuple(feedback)


def run_performance_attribution_preflight(
    replay_result,
    *,
    source_by_proposal_id: dict[str, str] | None = None,
) -> PerformanceAttributionResult:
    """Run deterministic attribution over a replay result without model updates."""

    validation_flags = validate_performance_attribution_input(replay_result)
    if validation_flags:
        feedback = build_feedback_records((), (), (), validation_flags)
        return PerformanceAttributionResult(
            ok=False,
            decision=AttributionDecision.BLOCKED.value,
            reason="attribution_input_invalid",
            proposal_records=(),
            symbol_records=(),
            source_records=(),
            day_records=(),
            feedback_records=feedback,
            risk_flags=validation_flags,
        )

    proposal_records = build_proposal_attribution_records(replay_result)
    symbol_records = aggregate_symbol_attribution(proposal_records)
    source_records = aggregate_source_attribution(
        proposal_records,
        source_by_proposal_id=source_by_proposal_id,
    )
    day_records = aggregate_day_attribution(replay_result, proposal_records)
    replay_flags = _map_replay_flags(getattr(replay_result, "risk_flags", ()))
    feedback_records = build_feedback_records(
        proposal_records,
        symbol_records,
        day_records,
        replay_flags,
    )
    decision = _decision_from_replay(replay_result)
    return PerformanceAttributionResult(
        ok=decision == AttributionDecision.COMPLETED.value,
        decision=decision,
        reason="ok" if decision == AttributionDecision.COMPLETED.value else "replay_not_completed",
        proposal_records=proposal_records,
        symbol_records=symbol_records,
        source_records=source_records,
        day_records=day_records,
        feedback_records=feedback_records,
        risk_flags=replay_flags,
    )


def _estimate_cost(instruction) -> float:
    if instruction.status != PaperLedgerDryRunInstructionStatus.SIMULATED.value:
        return 0.0
    notional = instruction.estimated_notional
    cash_delta = instruction.estimated_cash_delta
    if cash_delta < 0:
        cost = abs(cash_delta) - notional
    elif cash_delta > 0:
        cost = notional - cash_delta
    else:
        cost = 0.0
    if cost < 0 and abs(cost) <= 0.0001:
        return 0.0
    return round(max(0.0, cost), 4)


def _outcome_for_instruction(instruction) -> str:
    if instruction.status == PaperLedgerDryRunInstructionStatus.REJECTED.value:
        return AttributionOutcome.BLOCKED.value
    if instruction.status == PaperLedgerDryRunInstructionStatus.SKIPPED.value:
        return AttributionOutcome.SKIPPED.value
    if instruction.status == PaperLedgerDryRunInstructionStatus.SIMULATED.value:
        return _cash_outcome(instruction.estimated_cash_delta)
    return AttributionOutcome.FLAT.value


def _cash_outcome(cash_delta: float) -> str:
    if cash_delta > 0:
        return AttributionOutcome.SIMULATED_GAIN.value
    if cash_delta < 0:
        return AttributionOutcome.SIMULATED_LOSS.value
    return AttributionOutcome.FLAT.value


def _accepted_count(records: Iterable[ProposalAttributionRecord]) -> int:
    return sum(record.status == PaperLedgerDryRunInstructionStatus.SIMULATED.value for record in records)


def _blocked_count(records: Iterable[ProposalAttributionRecord]) -> int:
    return sum(record.outcome in {AttributionOutcome.BLOCKED.value, AttributionOutcome.SKIPPED.value} for record in records)


def _risk_codes_from_records(records: Iterable[ProposalAttributionRecord]) -> tuple[str, ...]:
    return tuple(record.reason for record in records if record.outcome == AttributionOutcome.BLOCKED.value)


def _source_from_evidence(evidence_refs: tuple[str, ...]) -> str:
    for ref in evidence_refs:
        if ref.startswith("source:"):
            return ref.split(":", 1)[1] or "unknown"
    return "unknown"


def _score_for_outcome(outcome: str, cash_delta: float, notional: float) -> float:
    if outcome == AttributionOutcome.BLOCKED.value:
        return -0.75
    if outcome == AttributionOutcome.SKIPPED.value:
        return -0.25
    if outcome == AttributionOutcome.PARTIAL.value:
        return -0.5
    if outcome == AttributionOutcome.FLAT.value:
        return 0.0
    denominator = max(abs(notional), 1.0)
    return _clamp_score(cash_delta / denominator)


def _score_from_cash_delta(cash_delta: float) -> float:
    return _clamp_score(cash_delta / max(abs(cash_delta), 1.0)) if cash_delta else 0.0


def _score_for_severity(severity: str) -> float:
    if severity == AttributionSeverity.CRITICAL.value:
        return -1.0
    if severity == AttributionSeverity.HIGH.value:
        return -0.75
    if severity == AttributionSeverity.MEDIUM.value:
        return -0.5
    return -0.25


def _clamp_score(value: float) -> float:
    return round(max(-1.0, min(1.0, value)), 4)


def _map_replay_flags(flags) -> tuple[PerformanceAttributionRiskFlag, ...]:
    return tuple(
        PerformanceAttributionRiskFlag(
            code=flag.code,
            severity=flag.severity,
            message=flag.message,
        )
        for flag in flags
    )


def _decision_from_replay(replay_result) -> str:
    if replay_result.decision == PaperReplayDecision.COMPLETED.value:
        return AttributionDecision.COMPLETED.value
    if replay_result.decision == PaperReplayDecision.PARTIAL.value:
        return AttributionDecision.PARTIAL.value
    return AttributionDecision.BLOCKED.value
