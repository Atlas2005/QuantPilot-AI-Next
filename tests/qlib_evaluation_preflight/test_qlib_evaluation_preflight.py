from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

from quantpilot_core.qlib_evaluation_preflight import (
    CHECK_NAMES,
    QlibBenchmarkConfig,
    QlibDatasetConfig,
    QlibEvaluationConfig,
    QlibEvaluationDecision,
    QlibEvaluationMode,
    QlibPreflightStatus,
    build_qlib_preflight_checks,
    run_qlib_evaluation_preflight,
    validate_qlib_benchmark_config,
    validate_qlib_dataset_config,
)


def factor_result(
    decision: str = "pass",
    *,
    failed_metrics: tuple[str, ...] = (),
    warning_metrics: tuple[str, ...] = (),
):
    return SimpleNamespace(
        decision=decision,
        failed_metrics=failed_metrics,
        warning_metrics=warning_metrics,
    )


def dataset(**overrides) -> QlibDatasetConfig:
    values = {
        "provider_uri": "local://qlib-cn-a-share-fixture",
        "region": "CN",
        "market": "A_SHARE",
        "instrument_universe": ("000001.SZ", "600000.SH", "300750.SZ"),
        "start_date": "2026-01-02",
        "end_date": "2026-01-31",
        "calendar_name": "a_share_trading_calendar",
        "evidence_refs": ("evidence://dataset",),
    }
    values.update(overrides)
    return QlibDatasetConfig(**values)


def benchmark(**overrides) -> QlibBenchmarkConfig:
    values = {
        "benchmark_symbol": "000300.SH",
        "frequency": "1d",
        "cost_model": "a_share_cash_equity_fixture",
        "slippage_bps": 5.0,
        "commission_rate": 0.0003,
        "stamp_tax_rate": 0.001,
        "evidence_refs": ("evidence://benchmark",),
    }
    values.update(overrides)
    return QlibBenchmarkConfig(**values)


def config(**overrides) -> QlibEvaluationConfig:
    values = {
        "config_id": "qlib-preflight-r29",
        "mode": QlibEvaluationMode.FACTOR_ANALYSIS.value,
        "dataset": dataset(),
        "benchmark": benchmark(),
        "factor_metric_result": factor_result(),
        "pit_required": True,
        "allow_runtime_execution": False,
        "evidence_refs": ("evidence://qlib-config",),
    }
    values.update(overrides)
    return QlibEvaluationConfig(**values)


def codes(result) -> set[str]:
    return {flag.code for flag in result.risk_flags}


def status_by_check(result, name: str) -> str:
    return next(check.status for check in result.checks if check.name == name)


def test_valid_qlib_evaluation_config_returns_ready() -> None:
    result = run_qlib_evaluation_preflight(config())

    assert result.ok is True
    assert result.decision == QlibEvaluationDecision.READY.value
    assert result.failed_checks == ()
    assert result.warning_checks == ()


def test_allow_runtime_execution_true_is_blocked() -> None:
    result = run_qlib_evaluation_preflight(config(allow_runtime_execution=True))

    assert result.decision == QlibEvaluationDecision.BLOCKED.value
    assert "runtime_execution_requested" in codes(result)


def test_pit_required_false_is_blocked() -> None:
    result = run_qlib_evaluation_preflight(config(pit_required=False))

    assert result.decision == QlibEvaluationDecision.BLOCKED.value
    assert "pit_required_false" in codes(result)


def test_missing_factor_metric_result_is_blocked() -> None:
    result = run_qlib_evaluation_preflight(config(factor_metric_result=None))

    assert result.decision == QlibEvaluationDecision.BLOCKED.value
    assert "factor_metric_result_missing" in codes(result)


def test_factor_metric_result_fail_blocks() -> None:
    result = run_qlib_evaluation_preflight(
        config(factor_metric_result=factor_result("fail", failed_metrics=("ic",)))
    )

    assert result.decision == QlibEvaluationDecision.BLOCKED.value
    assert "factor_metric_result_failed" in codes(result)
    assert "factor_metric_failed_metrics_present" in codes(result)


def test_factor_metric_result_manual_review_propagates_manual_review() -> None:
    result = run_qlib_evaluation_preflight(
        config(factor_metric_result=factor_result("manual_review", warning_metrics=("turnover",)))
    )

    assert result.decision == QlibEvaluationDecision.MANUAL_REVIEW.value
    assert "factor_metric_handoff" in result.warning_checks


def test_missing_config_evidence_refs_is_rejected() -> None:
    result = run_qlib_evaluation_preflight(config(evidence_refs=()))

    assert result.decision == QlibEvaluationDecision.BLOCKED.value
    assert "config_evidence_missing" in codes(result)


def test_invalid_dataset_date_shape_rejected() -> None:
    flags = validate_qlib_dataset_config(dataset(start_date="20260102"))

    assert any(flag.code == "dataset_start_date_invalid" for flag in flags)


def test_start_date_after_end_date_rejected() -> None:
    result = run_qlib_evaluation_preflight(
        config(dataset=dataset(start_date="2026-02-01", end_date="2026-01-01"))
    )

    assert result.decision == QlibEvaluationDecision.BLOCKED.value
    assert "dataset_date_range_invalid" in codes(result)


def test_empty_instrument_universe_rejected() -> None:
    result = run_qlib_evaluation_preflight(config(dataset=dataset(instrument_universe=())))

    assert result.decision == QlibEvaluationDecision.BLOCKED.value
    assert "dataset_instrument_universe_empty" in codes(result)


def test_duplicate_instruments_rejected() -> None:
    result = run_qlib_evaluation_preflight(
        config(dataset=dataset(instrument_universe=("000001.SZ", "000001.SZ")))
    )

    assert result.decision == QlibEvaluationDecision.BLOCKED.value
    assert "dataset_duplicate_instruments" in codes(result)


def test_suspicious_provider_uri_rejected() -> None:
    result = run_qlib_evaluation_preflight(config(dataset=dataset(provider_uri="TODO")))

    assert result.decision == QlibEvaluationDecision.BLOCKED.value
    assert "dataset_provider_uri_invalid" in codes(result)


def test_invalid_benchmark_frequency_rejected() -> None:
    flags = validate_qlib_benchmark_config(benchmark(frequency="minute"), market="A_SHARE")

    assert any(flag.code == "benchmark_frequency_invalid" for flag in flags)


def test_invalid_slippage_bps_rejected() -> None:
    result = run_qlib_evaluation_preflight(config(benchmark=benchmark(slippage_bps=101.0)))

    assert result.decision == QlibEvaluationDecision.BLOCKED.value
    assert "benchmark_slippage_bps_invalid" in codes(result)


def test_invalid_commission_rate_rejected() -> None:
    result = run_qlib_evaluation_preflight(config(benchmark=benchmark(commission_rate=0.02)))

    assert result.decision == QlibEvaluationDecision.BLOCKED.value
    assert "benchmark_commission_rate_invalid" in codes(result)


def test_invalid_stamp_tax_rate_rejected() -> None:
    result = run_qlib_evaluation_preflight(config(benchmark=benchmark(stamp_tax_rate=0.02)))

    assert result.decision == QlibEvaluationDecision.BLOCKED.value
    assert "benchmark_stamp_tax_rate_invalid" in codes(result)


def test_benchmark_market_compatibility_warning_creates_manual_review() -> None:
    result = run_qlib_evaluation_preflight(
        config(benchmark=benchmark(benchmark_symbol="SPY"))
    )

    assert result.decision == QlibEvaluationDecision.MANUAL_REVIEW.value
    assert "benchmark_config" in result.warning_checks
    assert status_by_check(result, "benchmark_config") == QlibPreflightStatus.WARNING.value


def test_deterministic_check_names_and_statuses() -> None:
    checks = build_qlib_preflight_checks(config())

    assert tuple(check.name for check in checks) == CHECK_NAMES
    assert tuple(check.status for check in checks) == tuple(
        QlibPreflightStatus.PASS.value for _ in CHECK_NAMES
    )


def test_no_mutation_of_config() -> None:
    original = config()
    before = replace(original)

    run_qlib_evaluation_preflight(original)
    build_qlib_preflight_checks(original)

    assert original == before
