from copy import deepcopy
from dataclasses import dataclass, replace
from enum import Enum

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
from quantpilot_core.small_capital_readiness_gate import (
    MetricStatus,
    ReadinessDecision,
    SmallCapitalReadinessThresholds,
    compute_readiness_metrics,
    run_small_capital_readiness_gate,
    validate_readiness_inputs,
)


class AttributionDecision(str, Enum):
    COMPLETED = "completed"


class AttributionOutcome(str, Enum):
    SIMULATED_GAIN = "simulated_gain"
    SIMULATED_LOSS = "simulated_loss"


@dataclass(frozen=True)
class ProposalAttributionRecord:
    proposal_id: str
    symbol: str
    trading_date: str
    side: str
    quantity: int
    estimated_price: float
    estimated_notional: float
    status: str
    estimated_cash_delta: float
    estimated_position_delta: int
    estimated_cost: float
    outcome: str
    reason: str
    evidence_refs: tuple[str, ...]


@dataclass(frozen=True)
class SymbolAttributionRecord:
    symbol: str
    accepted_count: int
    blocked_count: int
    net_position_delta: int
    net_cash_delta: float
    estimated_total_cost: float
    risk_flags_seen: tuple[str, ...]


@dataclass(frozen=True)
class FeedbackRecord:
    target_type: str
    target_id: str
    outcome: str
    score: float
    reason: str
    evidence_refs: tuple[str, ...]


@dataclass(frozen=True)
class PerformanceAttributionResult:
    ok: bool
    decision: str
    reason: str
    proposal_records: tuple[ProposalAttributionRecord, ...]
    symbol_records: tuple[SymbolAttributionRecord, ...]
    source_records: tuple[object, ...]
    day_records: tuple[object, ...]
    feedback_records: tuple[FeedbackRecord, ...]
    risk_flags: tuple[object, ...]


def instruction_result(**overrides):
    values = {
        "proposal_id": "proposal-001",
        "symbol": "600000",
        "side": "buy",
        "quantity": 100,
        "estimated_price": 10.0,
        "estimated_notional": 1000.0,
        "status": PaperLedgerDryRunInstructionStatus.SIMULATED.value,
        "reason": "simulated_buy",
        "estimated_cash_delta": -1005.0,
        "estimated_position_delta": 100,
        "risk_flags": (),
        "evidence_refs": ("fixture:instruction",),
    }
    values.update(overrides)
    return PaperLedgerDryRunInstructionResult(**values)


def dry_run_result(*instructions, decision=PaperLedgerDryRunDecision.ACCEPTED.value):
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
        risk_flags=(),
    )


def day_result(index, *, blocked=False, cash_start=100_000.0, cash_end=99_000.0):
    status = PaperReplayDayStatus.PARTIAL.value if blocked else PaperReplayDayStatus.SIMULATED.value
    instruction = instruction_result(proposal_id=f"proposal-{index}")
    if blocked:
        blocked_instruction = instruction_result(
            proposal_id=f"blocked-{index}",
            status=PaperLedgerDryRunInstructionStatus.REJECTED.value,
            reason="risk_block",
            estimated_cash_delta=0.0,
            estimated_position_delta=0,
        )
        dry_run = dry_run_result(
            instruction,
            blocked_instruction,
            decision=PaperLedgerDryRunDecision.PARTIAL.value,
        )
        blocked_ids = (blocked_instruction.proposal_id,)
    else:
        dry_run = dry_run_result(instruction)
        blocked_ids = ()
    return PaperReplayDayResult(
        trading_date=f"2026-07-{index:02d}",
        status=status,
        reason="partial_simulation" if blocked else "ok",
        dry_run_result=dry_run,
        cash_start=cash_start,
        cash_end=cash_end,
        positions_start={"600000": index * 100},
        positions_end={"600000": index * 100 + 100},
        blocked_instruction_ids=blocked_ids,
        risk_flags=(),
    )


def replay_result(**overrides):
    days = tuple(
        day_result(index, cash_start=100_000.0 - (index - 1) * 1000, cash_end=99_000.0 - (index - 1) * 1000)
        for index in range(1, 6)
    )
    values = {
        "ok": True,
        "decision": PaperReplayDecision.COMPLETED.value,
        "reason": "ok",
        "day_results": days,
        "final_cash": 95_000.0,
        "final_positions": {"600000": 500},
        "blocked_days": (),
        "risk_flags": (),
    }
    values.update(overrides)
    return PaperReplayResult(**values)


def proposal_record(index, **overrides):
    values = {
        "proposal_id": f"proposal-{index}",
        "symbol": "600000",
        "trading_date": f"2026-07-{index:02d}",
        "side": "buy",
        "quantity": 100,
        "estimated_price": 10.0,
        "estimated_notional": 1000.0,
        "status": PaperLedgerDryRunInstructionStatus.SIMULATED.value,
        "estimated_cash_delta": -1005.0,
        "estimated_position_delta": 100,
        "estimated_cost": 5.0,
        "outcome": AttributionOutcome.SIMULATED_LOSS.value,
        "reason": "simulated_buy",
        "evidence_refs": ("fixture:proposal",),
    }
    values.update(overrides)
    return ProposalAttributionRecord(**values)


def feedback(index, score=0.1, **overrides):
    values = {
        "target_type": "proposal",
        "target_id": f"proposal-{index}",
        "outcome": AttributionOutcome.SIMULATED_GAIN.value,
        "score": score,
        "reason": "fixture_feedback",
        "evidence_refs": ("fixture:feedback",),
    }
    values.update(overrides)
    return FeedbackRecord(**values)


def attribution_result(**overrides):
    proposals = tuple(proposal_record(index) for index in range(1, 6))
    values = {
        "ok": True,
        "decision": AttributionDecision.COMPLETED.value,
        "reason": "ok",
        "proposal_records": proposals,
        "symbol_records": (
            SymbolAttributionRecord(
                symbol="600000",
                accepted_count=5,
                blocked_count=0,
                net_position_delta=500,
                net_cash_delta=-5025.0,
                estimated_total_cost=25.0,
                risk_flags_seen=(),
            ),
        ),
        "source_records": (),
        "day_records": (),
        "feedback_records": tuple(feedback(index) for index in range(1, 6)),
        "risk_flags": (),
    }
    values.update(overrides)
    return PerformanceAttributionResult(**values)


def metric_by_name(result, name):
    return {metric.name: metric for metric in result.metrics}[name]


def test_valid_replay_and_attribution_pass_all_thresholds() -> None:
    result = run_small_capital_readiness_gate(replay_result(), attribution_result())

    assert result.ok is True
    assert result.decision == ReadinessDecision.PASS.value
    assert result.failed_checks == ()
    assert result.manual_review_checks == ()


def test_fewer_than_min_replay_days_returns_manual_review_metric() -> None:
    replay = replay_result(day_results=replay_result().day_results[:4])
    result = run_small_capital_readiness_gate(replay, attribution_result())

    assert result.decision == ReadinessDecision.MANUAL_REVIEW.value
    assert "replay_days" in result.manual_review_checks
    assert result.failed_checks == ()


def test_high_blocked_day_ratio_returns_manual_review_metric() -> None:
    days = (
        day_result(1, blocked=True),
        day_result(2, blocked=True),
        *replay_result().day_results[2:],
    )
    replay = replay_result(ok=False, decision=PaperReplayDecision.PARTIAL.value, day_results=days, blocked_days=("2026-07-01", "2026-07-02"))
    result = run_small_capital_readiness_gate(replay, attribution_result())

    assert "blocked_day_ratio" in result.manual_review_checks
    assert result.failed_checks == ()


def test_high_blocked_instruction_ratio_returns_manual_review_metric() -> None:
    days = (day_result(1, blocked=True), *replay_result().day_results[1:])
    replay = replay_result(ok=False, decision=PaperReplayDecision.PARTIAL.value, day_results=days, blocked_days=("2026-07-01",))
    result = run_small_capital_readiness_gate(
        replay,
        attribution_result(),
        SmallCapitalReadinessThresholds(max_blocked_instruction_ratio=0.10),
    )

    assert "blocked_instruction_ratio" in result.manual_review_checks
    assert result.failed_checks == ()


def test_critical_risk_flag_returns_fail() -> None:
    replay = replay_result(
        risk_flags=(
            PaperReplayRiskFlag(
                code="critical_rule",
                severity=ReplayRiskSeverity.CRITICAL.value,
                message="Critical replay risk.",
            ),
        )
    )
    result = run_small_capital_readiness_gate(replay, attribution_result())

    assert "critical_risk_flag_count" in result.failed_checks


def test_high_estimated_cost_ratio_returns_manual_review_metric() -> None:
    attribution = attribution_result(
        proposal_records=tuple(
            proposal_record(index, estimated_cost=20.0)
            for index in range(1, 6)
        )
    )
    result = run_small_capital_readiness_gate(replay_result(), attribution)

    assert "total_estimated_cost_ratio" in result.manual_review_checks
    assert result.failed_checks == ()


def test_high_negative_feedback_ratio_returns_manual_review_metric() -> None:
    attribution = attribution_result(
        feedback_records=tuple(feedback(index, score=-0.5) for index in range(1, 6))
    )
    result = run_small_capital_readiness_gate(replay_result(), attribution)

    assert "negative_feedback_ratio" in result.manual_review_checks
    assert result.failed_checks == ()


def test_too_few_accepted_instructions_returns_manual_review_metric() -> None:
    attribution = attribution_result(proposal_records=(proposal_record(1), proposal_record(2)))
    result = run_small_capital_readiness_gate(replay_result(), attribution)

    assert "accepted_instruction_count" in result.manual_review_checks
    assert result.failed_checks == ()


def test_high_cash_drawdown_returns_manual_review_metric() -> None:
    days = replay_result().day_results
    replay = replay_result(
        day_results=(
            replace(days[0], cash_start=100_000.0, cash_end=90_000.0),
            *days[1:],
        )
    )
    result = run_small_capital_readiness_gate(replay, attribution_result())

    assert "cash_drawdown_ratio" in result.manual_review_checks
    assert result.failed_checks == ()


def test_insufficient_optional_concentration_data_returns_manual_review() -> None:
    replay = replay_result(final_positions={})
    result = run_small_capital_readiness_gate(
        replay,
        attribution_result(),
        SmallCapitalReadinessThresholds(max_position_concentration_ratio=0.5),
    )

    assert result.decision == ReadinessDecision.MANUAL_REVIEW.value
    assert "position_concentration_ratio" in result.manual_review_checks


def test_warnings_without_hard_failure_return_manual_review() -> None:
    replay = replay_result(final_positions={})
    result = run_small_capital_readiness_gate(
        replay,
        attribution_result(),
        SmallCapitalReadinessThresholds(
            max_position_concentration_ratio=1.0,
        ),
    )

    assert result.failed_checks == ()
    assert result.decision == ReadinessDecision.MANUAL_REVIEW.value


def test_invalid_missing_replay_result_is_rejected() -> None:
    result = run_small_capital_readiness_gate(None, attribution_result())

    assert result.decision == ReadinessDecision.FAIL.value
    assert "replay_result_missing" in result.failed_checks


def test_invalid_missing_attribution_result_is_rejected() -> None:
    result = run_small_capital_readiness_gate(replay_result(), None)

    assert result.decision == ReadinessDecision.FAIL.value
    assert "attribution_result_missing" in result.failed_checks


def test_invalid_threshold_values_are_rejected() -> None:
    flags = validate_readiness_inputs(
        replay_result(),
        attribution_result(),
        SmallCapitalReadinessThresholds(min_replay_days=0),
    )

    assert "min_replay_days_invalid" in tuple(flag.code for flag in flags)


def test_deterministic_metric_names_and_statuses() -> None:
    metrics = compute_readiness_metrics(
        replay_result(),
        attribution_result(),
        SmallCapitalReadinessThresholds(),
    )

    assert tuple(metric.name for metric in metrics) == (
        "replay_days",
        "blocked_day_ratio",
        "blocked_instruction_ratio",
        "critical_risk_flag_count",
        "total_estimated_cost_ratio",
        "negative_feedback_ratio",
        "accepted_instruction_count",
        "cash_drawdown_ratio",
    )
    assert all(metric.status == MetricStatus.PASS.value for metric in metrics)


def test_no_mutation_of_replay_or_attribution_result() -> None:
    replay = replay_result()
    attribution = attribution_result()
    replay_snapshot = deepcopy(replay)
    attribution_snapshot = deepcopy(attribution)

    run_small_capital_readiness_gate(replay, attribution)

    assert replay == replay_snapshot
    assert attribution == attribution_snapshot
