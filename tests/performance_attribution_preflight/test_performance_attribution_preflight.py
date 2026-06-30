from copy import deepcopy
from dataclasses import replace

from quantpilot_core.ai_action_paper_bridge import ActionSide
from quantpilot_core.multi_day_paper_replay import (
    PaperReplayDayResult,
    PaperReplayDayStatus,
    PaperReplayDecision,
    PaperReplayResult,
    PaperReplayRiskFlag,
    RiskSeverity as ReplayRiskSeverity,
)
from quantpilot_core.paper_ledger_dry_run import (
    PaperLedgerDryRunDecision,
    PaperLedgerDryRunInstructionResult,
    PaperLedgerDryRunInstructionStatus,
    PaperLedgerDryRunResult,
)
from quantpilot_core.performance_attribution_preflight import (
    AttributionDecision,
    AttributionOutcome,
    FeedbackTargetType,
    aggregate_day_attribution,
    aggregate_symbol_attribution,
    build_proposal_attribution_records,
    run_performance_attribution_preflight,
    validate_performance_attribution_input,
)


def instruction_result(**overrides):
    values = {
        "proposal_id": "proposal-buy",
        "symbol": "600000",
        "side": ActionSide.BUY.value,
        "quantity": 100,
        "estimated_price": 10.0,
        "estimated_notional": 1000.0,
        "status": PaperLedgerDryRunInstructionStatus.SIMULATED.value,
        "reason": "simulated_buy",
        "estimated_cash_delta": -1010.1,
        "estimated_position_delta": 100,
        "risk_flags": (),
        "evidence_refs": ("proposal:buy", "source:factor_agent"),
    }
    values.update(overrides)
    return PaperLedgerDryRunInstructionResult(**values)


def dry_run_result(*instructions, decision=PaperLedgerDryRunDecision.ACCEPTED.value, risk_flags=()):
    return PaperLedgerDryRunResult(
        ok=decision == PaperLedgerDryRunDecision.ACCEPTED.value,
        decision=decision,
        reason="ok" if decision == PaperLedgerDryRunDecision.ACCEPTED.value else "partial_simulation",
        instruction_results=tuple(instructions),
        simulated_cash_after=0.0,
        simulated_positions_after={},
        blocked_instruction_ids=tuple(
            instruction.proposal_id
            for instruction in instructions
            if instruction.status == PaperLedgerDryRunInstructionStatus.REJECTED.value
        ),
        risk_flags=tuple(risk_flags),
    )


def day_result(**overrides):
    buy = instruction_result()
    values = {
        "trading_date": "2026-07-01",
        "status": PaperReplayDayStatus.SIMULATED.value,
        "reason": "ok",
        "dry_run_result": dry_run_result(buy),
        "cash_start": 50_000.0,
        "cash_end": 48_989.9,
        "positions_start": {"600000": 1000},
        "positions_end": {"600000": 1100},
        "blocked_instruction_ids": (),
        "risk_flags": (),
    }
    values.update(overrides)
    return PaperReplayDayResult(**values)


def replay_result(**overrides):
    sell = instruction_result(
        proposal_id="proposal-sell",
        side=ActionSide.SELL.value,
        quantity=100,
        estimated_cash_delta=988.99,
        estimated_position_delta=-100,
        reason="simulated_sell",
        evidence_refs=("proposal:sell", "source:news_event_agent"),
    )
    blocked = instruction_result(
        proposal_id="proposal-blocked",
        status=PaperLedgerDryRunInstructionStatus.REJECTED.value,
        reason="sellable_quantity_insufficient",
        estimated_cash_delta=0.0,
        estimated_position_delta=0,
        risk_flags=(),
        evidence_refs=("proposal:blocked", "source:risk_agent"),
    )
    day_one = day_result()
    day_two = day_result(
        trading_date="2026-07-02",
        status=PaperReplayDayStatus.PARTIAL.value,
        reason="partial_simulation",
        dry_run_result=dry_run_result(
            sell,
            blocked,
            decision=PaperLedgerDryRunDecision.PARTIAL.value,
        ),
        cash_start=48_989.9,
        cash_end=49_978.89,
        positions_start={"600000": 1100},
        positions_end={"600000": 1000},
        blocked_instruction_ids=("proposal-blocked",),
        risk_flags=(
            PaperReplayRiskFlag(
                code="2026-07-02:sellable_quantity_insufficient",
                severity=ReplayRiskSeverity.CRITICAL.value,
                message="SELL dry-run exceeds sellable quantity.",
            ),
        ),
    )
    values = {
        "ok": False,
        "decision": PaperReplayDecision.PARTIAL.value,
        "reason": "partial_replay",
        "day_results": (day_one, day_two),
        "final_cash": 49_978.89,
        "final_positions": {"600000": 1000},
        "blocked_days": ("2026-07-02",),
        "risk_flags": day_two.risk_flags,
    }
    values.update(overrides)
    return PaperReplayResult(**values)


def feedback_for(result, target_type):
    return tuple(record for record in result.feedback_records if record.target_type == target_type)


def test_valid_replay_result_produces_proposal_symbol_day_and_feedback_records() -> None:
    result = run_performance_attribution_preflight(replay_result())

    assert result.decision == AttributionDecision.PARTIAL.value
    assert len(result.proposal_records) == 3
    assert len(result.symbol_records) == 1
    assert len(result.day_records) == 2
    assert feedback_for(result, FeedbackTargetType.PROPOSAL.value)
    assert feedback_for(result, FeedbackTargetType.SYMBOL.value)
    assert feedback_for(result, FeedbackTargetType.DAY.value)


def test_simulated_buy_creates_negative_cash_delta_and_cost_attribution() -> None:
    records = build_proposal_attribution_records(replay_result())
    buy = records[0]

    assert buy.outcome == AttributionOutcome.SIMULATED_LOSS.value
    assert buy.estimated_cash_delta == -1010.1
    assert buy.estimated_cost == 10.1


def test_simulated_sell_creates_positive_cash_delta_and_cost_attribution() -> None:
    records = build_proposal_attribution_records(replay_result())
    sell = records[1]

    assert sell.outcome == AttributionOutcome.SIMULATED_GAIN.value
    assert sell.estimated_cash_delta == 988.99
    assert sell.estimated_cost == 11.01


def test_blocked_instruction_creates_blocked_outcome_and_negative_feedback() -> None:
    result = run_performance_attribution_preflight(replay_result())
    blocked = [record for record in result.proposal_records if record.proposal_id == "proposal-blocked"][0]
    feedback = [record for record in result.feedback_records if record.target_id == "proposal-blocked"][0]

    assert blocked.outcome == AttributionOutcome.BLOCKED.value
    assert feedback.score < 0


def test_skipped_instruction_creates_skipped_outcome() -> None:
    skipped = instruction_result(
        proposal_id="proposal-skipped",
        status=PaperLedgerDryRunInstructionStatus.SKIPPED.value,
        reason="skipped_after_fail_fast_block",
        estimated_cash_delta=0.0,
        estimated_position_delta=0,
    )
    replay = replay_result(
        decision=PaperReplayDecision.BLOCKED.value,
        day_results=(day_result(dry_run_result=dry_run_result(skipped)),),
        risk_flags=(),
    )

    record = build_proposal_attribution_records(replay)[0]

    assert record.outcome == AttributionOutcome.SKIPPED.value


def test_partial_day_is_represented_in_day_attribution() -> None:
    records = build_proposal_attribution_records(replay_result())
    days = aggregate_day_attribution(replay_result(), records)

    assert days[1].status == PaperReplayDayStatus.PARTIAL.value
    assert days[1].blocked_count == 1


def test_symbol_aggregation_is_deterministic() -> None:
    records = build_proposal_attribution_records(replay_result())
    symbols = aggregate_symbol_attribution(records)

    assert symbols[0].symbol == "600000"
    assert symbols[0].accepted_count == 2
    assert symbols[0].blocked_count == 1
    assert symbols[0].net_position_delta == 0
    assert symbols[0].net_cash_delta == -21.11
    assert symbols[0].estimated_total_cost == 21.11


def test_day_aggregation_is_deterministic() -> None:
    records = build_proposal_attribution_records(replay_result())
    days = aggregate_day_attribution(replay_result(), records)

    assert days[0].trading_date == "2026-07-01"
    assert days[0].accepted_count == 1
    assert days[0].estimated_net_cash_delta == -1010.1
    assert days[1].risk_flags_seen == ("2026-07-02:sellable_quantity_insufficient",)


def test_source_aggregation_works_when_mapping_is_provided() -> None:
    result = run_performance_attribution_preflight(
        replay_result(),
        source_by_proposal_id={
            "proposal-buy": "factor_agent",
            "proposal-sell": "news_event_agent",
            "proposal-blocked": "risk_agent",
        },
    )

    assert tuple(record.source for record in result.source_records) == (
        "factor_agent",
        "news_event_agent",
        "risk_agent",
    )


def test_missing_replay_result_or_empty_day_results_is_rejected() -> None:
    assert validate_performance_attribution_input(None)[0].code == "replay_result_missing"
    result = run_performance_attribution_preflight(replay_result(day_results=()))

    assert result.decision == AttributionDecision.BLOCKED.value
    assert "day_results_missing" in tuple(flag.code for flag in result.risk_flags)


def test_missing_evidence_refs_on_instruction_result_is_rejected() -> None:
    bad_instruction = instruction_result(evidence_refs=())
    replay = replay_result(day_results=(day_result(dry_run_result=dry_run_result(bad_instruction)),))

    flags = validate_performance_attribution_input(replay)

    assert "day[0].instruction[0]:evidence_refs_missing" in tuple(flag.code for flag in flags)


def test_invalid_non_finite_final_cash_is_rejected() -> None:
    flags = validate_performance_attribution_input(replay_result(final_cash=float("inf")))

    assert "final_cash_not_finite" in tuple(flag.code for flag in flags)


def test_estimated_cost_is_never_negative_due_to_float_noise() -> None:
    noisy = instruction_result(estimated_cash_delta=999.99999)
    replay = replay_result(day_results=(day_result(dry_run_result=dry_run_result(noisy)),))
    record = build_proposal_attribution_records(replay)[0]

    assert record.estimated_cost == 0.0


def test_critical_risk_flags_create_negative_feedback() -> None:
    result = run_performance_attribution_preflight(replay_result())
    risk_feedback = feedback_for(result, FeedbackTargetType.RISK_RULE.value)

    assert risk_feedback
    assert risk_feedback[0].score == -1.0


def test_no_mutation_of_replay_result() -> None:
    original = replay_result()
    snapshot = deepcopy(original)

    run_performance_attribution_preflight(original)

    assert original == snapshot
