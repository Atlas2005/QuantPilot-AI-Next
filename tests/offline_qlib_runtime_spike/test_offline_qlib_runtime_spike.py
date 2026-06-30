from __future__ import annotations

from dataclasses import replace

from quantpilot_core.offline_qlib_runtime_spike import (
    CHECK_NAMES,
    DEFAULT_REQUIRED_FACTOR_METRICS,
    FactorMetricHandoff,
    OfflineQlibRuntimeDecision,
    OfflineQlibRuntimeMode,
    OfflineQlibRuntimePlan,
    QlibBenchmarkBoundary,
    QlibCalendarBoundary,
    QlibDatasetBoundary,
    build_offline_runtime_checks,
    build_offline_runtime_readiness_report,
    run_optional_offline_qlib_runtime_spike,
    validate_dataset_boundary,
    validate_factor_metric_handoff,
)


def dataset(**overrides) -> QlibDatasetBoundary:
    values = {
        "dataset_uri": "fixtures/qlib/a_share_daily",
        "provider_name": "fixture",
        "market": "A_SHARE",
        "symbols": ("000001.SZ", "600000.SH"),
        "start_date": "2026-01-02",
        "end_date": "2026-01-05",
        "local_only": True,
        "evidence_refs": ("evidence://dataset",),
    }
    values.update(overrides)
    return QlibDatasetBoundary(**values)


def calendar(**overrides) -> QlibCalendarBoundary:
    values = {
        "calendar_name": "a_share_fixture_calendar",
        "trading_dates": ("2026-01-02", "2026-01-05"),
        "fixture_backed": True,
        "evidence_refs": ("evidence://calendar",),
    }
    values.update(overrides)
    return QlibCalendarBoundary(**values)


def benchmark(**overrides) -> QlibBenchmarkBoundary:
    values = {
        "benchmark_symbol": "000300.SH",
        "frequency": "1d",
        "cost_model": "a_share_cost_fixture",
        "evidence_refs": ("evidence://benchmark",),
    }
    values.update(overrides)
    return QlibBenchmarkBoundary(**values)


def handoff(**overrides) -> FactorMetricHandoff:
    values = {
        "factor_id": "factor-001",
        "decision": "pass",
        "metric_names": DEFAULT_REQUIRED_FACTOR_METRICS,
        "required_metric_names": DEFAULT_REQUIRED_FACTOR_METRICS,
        "evidence_refs": ("evidence://factor-metrics",),
    }
    values.update(overrides)
    return FactorMetricHandoff(**values)


def plan(**overrides) -> OfflineQlibRuntimePlan:
    values = {
        "plan_id": "p32-offline-runtime-plan",
        "mode": OfflineQlibRuntimeMode.PLAN_ONLY.value,
        "dataset": dataset(),
        "calendar": calendar(),
        "benchmark": benchmark(),
        "factor_metric_handoff": handoff(),
        "allow_network": False,
        "allow_runtime_execution": False,
        "manual_runtime_required": True,
        "integration_boundary_evidence": ("evidence://p32/integration-boundary",),
        "forbidden_scope_evidence": ("evidence://p32/no-live-runtime-scope",),
        "evidence_refs": ("evidence://p32/plan",),
    }
    values.update(overrides)
    return OfflineQlibRuntimePlan(**values)


def codes(report) -> set[str]:
    return {flag.code for flag in report.risk_flags}


def test_valid_plan_generates_ready_report() -> None:
    report = build_offline_runtime_readiness_report(plan())

    assert report.ready is True
    assert report.decision == OfflineQlibRuntimeDecision.READY.value
    assert report.blockers == ()
    assert report.warnings == ()
    assert "keep_runtime_disabled_until_manual_spike" in report.required_manual_steps


def test_missing_dataset_is_rejected() -> None:
    report = build_offline_runtime_readiness_report(plan(dataset=dataset(dataset_uri="")))

    assert report.decision == OfflineQlibRuntimeDecision.NOT_READY.value
    assert "dataset_boundary" in report.blockers
    assert "dataset_uri_missing" in codes(report)


def test_url_dataset_is_rejected() -> None:
    flags = validate_dataset_boundary(dataset(dataset_uri="https://example.invalid/qlib"))

    assert any(flag.code == "dataset_uri_is_url" for flag in flags)


def test_missing_calendar_is_rejected() -> None:
    report = build_offline_runtime_readiness_report(
        plan(calendar=calendar(calendar_name="", trading_dates=(), fixture_backed=False))
    )

    assert report.decision == OfflineQlibRuntimeDecision.NOT_READY.value
    assert "calendar_boundary" in report.blockers


def test_missing_benchmark_is_rejected() -> None:
    report = build_offline_runtime_readiness_report(plan(benchmark=benchmark(benchmark_symbol="")))

    assert report.decision == OfflineQlibRuntimeDecision.NOT_READY.value
    assert "benchmark_boundary" in report.blockers


def test_missing_factor_metric_fields_are_rejected() -> None:
    flags = validate_factor_metric_handoff(
        handoff(metric_names=("ic", "rank_ic"), required_metric_names=DEFAULT_REQUIRED_FACTOR_METRICS)
    )

    assert any(flag.code == "factor_metric_fields_missing" for flag in flags)


def test_factor_metric_manual_review_creates_warning_report() -> None:
    report = build_offline_runtime_readiness_report(
        plan(factor_metric_handoff=handoff(decision="manual_review"))
    )

    assert report.decision == OfflineQlibRuntimeDecision.MANUAL_REVIEW.value
    assert report.warnings == ("factor_metric_handoff",)


def test_missing_dependency_does_not_fail_default_tests() -> None:
    runtime_plan = plan(
        mode=OfflineQlibRuntimeMode.MANUAL_RUNTIME.value,
        allow_runtime_execution=True,
        manual_runtime_required=True,
    )

    def importer(name: str) -> object:
        raise ImportError(name)

    report = run_optional_offline_qlib_runtime_spike(
        runtime_plan,
        enable_manual_runtime=True,
        importer=importer,
    )

    assert report.decision == OfflineQlibRuntimeDecision.MANUAL_REVIEW.value
    assert report.reason == "runtime_dependency_missing"


def test_forbidden_live_mode_is_blocked_with_reason() -> None:
    report = build_offline_runtime_readiness_report(
        plan(mode=OfflineQlibRuntimeMode.LIVE_RUNTIME.value)
    )

    assert report.decision == OfflineQlibRuntimeDecision.NOT_READY.value
    assert "live_runtime_mode_blocked" in codes(report)
    assert "runtime_guard" in report.blockers


def test_network_mode_is_blocked() -> None:
    report = build_offline_runtime_readiness_report(plan(allow_network=True))

    assert report.decision == OfflineQlibRuntimeDecision.NOT_READY.value
    assert "network_mode_blocked" in codes(report)


def test_manual_runner_guard_does_not_import_when_disabled() -> None:
    calls: list[str] = []

    def importer(name: str) -> object:
        calls.append(name)
        raise AssertionError("importer should not be called")

    report = run_optional_offline_qlib_runtime_spike(
        plan(),
        enable_manual_runtime=False,
        importer=importer,
    )

    assert calls == []
    assert report.decision == OfflineQlibRuntimeDecision.MANUAL_REVIEW.value
    assert report.reason == "manual_runtime_not_enabled"


def test_report_generation_has_deterministic_check_names() -> None:
    checks = build_offline_runtime_checks(plan())

    assert tuple(check.name for check in checks) == CHECK_NAMES
    assert tuple(check.reason for check in checks) == tuple("passed" for _ in CHECK_NAMES)


def test_forbidden_scope_evidence_blocks_report() -> None:
    report = build_offline_runtime_readiness_report(
        plan(forbidden_scope_evidence=("operator requested place_order after spike",))
    )

    assert report.decision == OfflineQlibRuntimeDecision.NOT_READY.value
    assert "forbidden_scope" in report.blockers


def test_no_mutation_of_input_plan() -> None:
    runtime_plan = plan()
    before = replace(runtime_plan)

    build_offline_runtime_readiness_report(runtime_plan)
    run_optional_offline_qlib_runtime_spike(runtime_plan)

    assert runtime_plan == before
