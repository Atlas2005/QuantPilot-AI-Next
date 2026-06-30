"""Input validation for the R25 small-capital readiness gate."""

from __future__ import annotations

from quantpilot_core.small_capital_readiness_gate.contracts import (
    GateSeverity,
    ReadinessRiskFlag,
    SmallCapitalReadinessThresholds,
)


def validate_readiness_inputs(
    replay_result,
    attribution_result,
    thresholds: SmallCapitalReadinessThresholds,
) -> tuple[ReadinessRiskFlag, ...]:
    """Validate gate inputs and threshold shape."""

    flags: list[ReadinessRiskFlag] = []
    if replay_result is None:
        flags.append(_critical("replay_result_missing", "Replay result is required."))
    if attribution_result is None:
        flags.append(_critical("attribution_result_missing", "Attribution result is required."))
    flags.extend(_validate_thresholds(thresholds))
    return tuple(flags)


def _validate_thresholds(
    thresholds: SmallCapitalReadinessThresholds,
) -> tuple[ReadinessRiskFlag, ...]:
    flags: list[ReadinessRiskFlag] = []
    if thresholds.min_replay_days <= 0:
        flags.append(_critical("min_replay_days_invalid", "min_replay_days must be positive."))
    if not 0 <= thresholds.max_blocked_day_ratio <= 1:
        flags.append(_critical("max_blocked_day_ratio_invalid", "max_blocked_day_ratio must be in [0, 1]."))
    if not 0 <= thresholds.max_blocked_instruction_ratio <= 1:
        flags.append(
            _critical(
                "max_blocked_instruction_ratio_invalid",
                "max_blocked_instruction_ratio must be in [0, 1].",
            )
        )
    if thresholds.max_critical_risk_flags < 0:
        flags.append(_critical("max_critical_risk_flags_invalid", "max_critical_risk_flags must be non-negative."))
    if thresholds.max_total_estimated_cost_ratio < 0:
        flags.append(
            _critical(
                "max_total_estimated_cost_ratio_invalid",
                "max_total_estimated_cost_ratio must be non-negative.",
            )
        )
    if not 0 <= thresholds.max_negative_feedback_ratio <= 1:
        flags.append(
            _critical(
                "max_negative_feedback_ratio_invalid",
                "max_negative_feedback_ratio must be in [0, 1].",
            )
        )
    if thresholds.min_accepted_instruction_count < 0:
        flags.append(
            _critical(
                "min_accepted_instruction_count_invalid",
                "min_accepted_instruction_count must be non-negative.",
            )
        )
    if not 0 <= thresholds.max_cash_drawdown_ratio <= 1:
        flags.append(_critical("max_cash_drawdown_ratio_invalid", "max_cash_drawdown_ratio must be in [0, 1]."))
    if (
        thresholds.max_position_concentration_ratio is not None
        and not 0 <= thresholds.max_position_concentration_ratio <= 1
    ):
        flags.append(
            _critical(
                "max_position_concentration_ratio_invalid",
                "max_position_concentration_ratio must be in [0, 1] when configured.",
            )
        )
    return tuple(flags)


def _critical(code: str, message: str) -> ReadinessRiskFlag:
    return ReadinessRiskFlag(
        code=code,
        severity=GateSeverity.CRITICAL.value,
        message=message,
    )
