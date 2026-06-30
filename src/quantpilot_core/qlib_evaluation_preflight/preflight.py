"""R29 Qlib evaluation preflight without Qlib runtime execution."""

from __future__ import annotations

from quantpilot_core.qlib_evaluation_preflight.config_validation import (
    validate_qlib_benchmark_config,
    validate_qlib_dataset_config,
    validate_qlib_evaluation_config,
)
from quantpilot_core.qlib_evaluation_preflight.contracts import (
    QlibEvaluationConfig,
    QlibEvaluationDecision,
    QlibEvaluationPreflightResult,
    QlibEvaluationRiskFlag,
    QlibPreflightCheckRecord,
    QlibPreflightStatus,
    QlibRiskSeverity,
)


CHECK_NAMES: tuple[str, ...] = (
    "config_shape",
    "runtime_disabled",
    "pit_required",
    "dataset_config",
    "benchmark_config",
    "factor_metric_handoff",
    "sandbox_safety",
)


def build_qlib_preflight_checks(
    config: QlibEvaluationConfig,
) -> tuple[QlibPreflightCheckRecord, ...]:
    """Build deterministic check records for a future Qlib evaluation setup."""

    all_flags = validate_qlib_evaluation_config(config)
    dataset_flags = validate_qlib_dataset_config(config.dataset)
    benchmark_flags = validate_qlib_benchmark_config(config.benchmark, market=config.dataset.market)
    return (
        _check(
            "config_shape",
            _flags_with_codes(
                all_flags,
                {
                    "config_id_missing",
                    "config_mode_invalid",
                    "config_evidence_missing",
                },
            ),
            config.evidence_refs,
        ),
        _check(
            "runtime_disabled",
            _flags_with_codes(all_flags, {"runtime_execution_requested"}),
            config.evidence_refs,
        ),
        _check(
            "pit_required",
            _flags_with_codes(
                all_flags,
                {
                    "pit_required_false",
                    "factor_metric_pit_evidence_failed",
                },
            ),
            config.evidence_refs,
        ),
        _check("dataset_config", dataset_flags, config.dataset.evidence_refs),
        _check("benchmark_config", benchmark_flags, config.benchmark.evidence_refs),
        _check(
            "factor_metric_handoff",
            _flags_with_prefix(all_flags, "factor_metric"),
            config.evidence_refs,
        ),
        _check(
            "sandbox_safety",
            _flags_with_codes(
                all_flags,
                {
                    "runtime_execution_requested",
                    "pit_required_false",
                },
            ),
            config.evidence_refs,
        ),
    )


def run_qlib_evaluation_preflight(
    config: QlibEvaluationConfig,
) -> QlibEvaluationPreflightResult:
    """Evaluate Qlib readiness without imports or runtime execution."""

    checks = build_qlib_preflight_checks(config)
    risk_flags = validate_qlib_evaluation_config(config)
    passed_checks = tuple(check.name for check in checks if check.status == QlibPreflightStatus.PASS.value)
    warning_checks = tuple(check.name for check in checks if check.status == QlibPreflightStatus.WARNING.value)
    failed_checks = tuple(check.name for check in checks if check.status == QlibPreflightStatus.FAIL.value)

    if any(flag.severity == QlibRiskSeverity.CRITICAL.value for flag in risk_flags) or failed_checks:
        decision = QlibEvaluationDecision.BLOCKED.value
        reason = "critical_risk_flags"
    elif warning_checks:
        decision = QlibEvaluationDecision.MANUAL_REVIEW.value
        reason = "warning_checks"
    else:
        decision = QlibEvaluationDecision.READY.value
        reason = "ready"

    return QlibEvaluationPreflightResult(
        ok=decision == QlibEvaluationDecision.READY.value,
        decision=decision,
        reason=reason,
        config_id=config.config_id,
        checks=checks,
        risk_flags=risk_flags,
        passed_checks=passed_checks,
        warning_checks=warning_checks,
        failed_checks=failed_checks,
    )


def _check(
    name: str,
    flags: tuple[QlibEvaluationRiskFlag, ...],
    evidence_refs: tuple[str, ...],
) -> QlibPreflightCheckRecord:
    if any(flag.severity == QlibRiskSeverity.CRITICAL.value for flag in flags):
        status = QlibPreflightStatus.FAIL.value
    elif flags:
        status = QlibPreflightStatus.WARNING.value
    else:
        status = QlibPreflightStatus.PASS.value
    return QlibPreflightCheckRecord(
        name=name,
        status=status,
        reason=";".join(flag.code for flag in flags) if flags else "passed",
        evidence_refs=evidence_refs,
    )


def _flags_with_codes(
    flags: tuple[QlibEvaluationRiskFlag, ...],
    codes: set[str],
) -> tuple[QlibEvaluationRiskFlag, ...]:
    return tuple(flag for flag in flags if flag.code in codes)


def _flags_with_prefix(
    flags: tuple[QlibEvaluationRiskFlag, ...],
    prefix: str,
) -> tuple[QlibEvaluationRiskFlag, ...]:
    return tuple(flag for flag in flags if flag.code.startswith(prefix))
