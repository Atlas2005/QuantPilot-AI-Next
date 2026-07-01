from __future__ import annotations

import sys
from pathlib import Path

from quantpilot_core.ai_open_source_provider_small_sample_mixed_etf_replay import (
    OpenSourceProviderExportSpec,
    OpenSourceProviderName,
    ProviderExportSourceType,
)
from quantpilot_core.controlled_optional_qlib_runtime_spike import (
    OptionalQlibRuntimeState,
    QlibRuntimeExecutionMode,
    QlibRuntimeResultRecord,
    build_controlled_qlib_runtime_report,
    build_manual_qlib_execution_plan,
    compare_runtime_results_with_offline_proxy,
    detect_optional_qlib_runtime,
    import_manual_qlib_runtime_results,
)
from quantpilot_core.qlib_real_offline_workflow_spike import (
    QlibFieldMapping,
    QlibInstrumentKind,
    build_p41_qlib_workflow_report,
)


def qlib_mapping() -> QlibFieldMapping:
    return QlibFieldMapping(
        symbol="symbol",
        trade_date="trade_date",
        open="open",
        high="high",
        low="low",
        close="close",
        volume="volume",
        instrument_kind="instrument_kind",
        etf_category="etf_category",
    )


def provider_mapping() -> dict[str, str]:
    return {
        "symbol": "symbol",
        "trade_date": "trade_date",
        "instrument_type": "instrument_type",
        "open": "open",
        "high": "high",
        "low": "low",
        "close": "close",
        "volume": "volume",
        "etf_category": "etf_category",
    }


def records() -> tuple[dict[str, object], ...]:
    rows: list[dict[str, object]] = []
    for trade_date, stock_close, etf_close in (
        ("2026-01-02", 10.0, 2.0),
        ("2026-01-05", 10.2, 2.02),
        ("2026-01-06", 10.3, 2.04),
    ):
        rows.append(
            {
                "symbol": "000001.SZ",
                "trade_date": trade_date,
                "instrument_type": "stock",
                "instrument_kind": QlibInstrumentKind.A_SHARE_STOCK.value,
                "open": stock_close,
                "high": round(stock_close * 1.02, 4),
                "low": round(stock_close * 0.98, 4),
                "close": stock_close,
                "volume": 1_000_000,
            }
        )
        rows.append(
            {
                "symbol": "510300.SH",
                "trade_date": trade_date,
                "instrument_type": "etf",
                "instrument_kind": QlibInstrumentKind.EXCHANGE_TRADED_ETF.value,
                "etf_category": "equity_etf",
                "open": etf_close,
                "high": round(etf_close * 1.02, 4),
                "low": round(etf_close * 0.98, 4),
                "close": etf_close,
                "volume": 5_000_000,
            }
        )
    return tuple(rows)


def provider_spec() -> OpenSourceProviderExportSpec:
    return OpenSourceProviderExportSpec(
        provider_name=OpenSourceProviderName.AKSHARE.value,
        source_type=ProviderExportSourceType.DETERMINISTIC_FIXTURE.value,
        source_uri="fixtures/p42/akshare_export",
        approved_by="qa_reviewer",
        approval_reason="approved deterministic small sample",
        export_timestamp="2026-01-07T00:00:00",
        provider_schema_mapping=provider_mapping(),
        evaluation_start="2026-01-02",
        evaluation_end="2026-01-06",
        initial_cash=100_000.0,
        evidence_refs=("evidence://p42/spec",),
    )


def p41_report():
    return build_p41_qlib_workflow_report(
        provider_spec(),
        records(),
        qlib_field_mapping=qlib_mapping(),
    )


def manual_plan():
    return build_manual_qlib_execution_plan(p41_report())


def valid_result_record() -> QlibRuntimeResultRecord:
    plan = manual_plan()
    return QlibRuntimeResultRecord(
        result_source="local/manual_result.json",
        dataset_id=plan.dataset_id,
        workflow_config_id=plan.workflow_config_id,
        metrics={
            "ic": 0.04,
            "rank_ic": 0.05,
            "cost_adjusted_score": 0.89,
            "cost_aware_return_proxy": 0.89,
        },
        missing_metric_reasons={},
        profitability_claim=False,
        benchmark="000300.SH",
        stock_count=1,
        etf_count=1,
        execution_mode=QlibRuntimeExecutionMode.IMPORT_RESULT_ONLY.value,
        warnings=("manual_result_fixture",),
    )


def test_qlib_unavailable_status_reported_without_import() -> None:
    result = detect_optional_qlib_runtime(find_spec_func=lambda name: None)

    assert result.runtime_state == OptionalQlibRuntimeState.UNAVAILABLE_OPTIONAL_DEPENDENCY.value
    assert result.runtime_imported is False
    assert "qlib" not in sys.modules


def test_qlib_available_simulated_status_still_disabled_by_default() -> None:
    result = detect_optional_qlib_runtime(find_spec_func=lambda name: object())

    assert result.runtime_state == OptionalQlibRuntimeState.AVAILABLE_BUT_DISABLED_BY_DEFAULT.value
    assert result.qrun_disabled_by_default is True


def test_default_execution_mode_disabled() -> None:
    result = detect_optional_qlib_runtime(find_spec_func=lambda name: object())

    assert result.execution_mode == QlibRuntimeExecutionMode.DISABLED_DEFAULT.value


def test_manual_execution_plan_requires_user_confirmation() -> None:
    plan = manual_plan()

    assert plan.required_user_confirmation is True


def test_manual_execution_plan_is_local_only() -> None:
    plan = manual_plan()

    assert plan.manual_local_only is True
    assert plan.no_network_required is True
    assert plan.no_broker_required is True
    assert plan.no_account_required is True


def test_manual_execution_plan_does_not_execute_qrun() -> None:
    plan = manual_plan()

    assert plan.qrun_disabled_by_default is True
    assert plan.default_pytest_statement == "Default pytest does not execute Qlib or qrun."


def test_result_import_accepts_deterministic_local_runtime_like_records() -> None:
    result = import_manual_qlib_runtime_results(manual_plan(), (valid_result_record(),))

    assert result.ok is True
    assert result.runtime_state == OptionalQlibRuntimeState.MANUAL_RUNTIME_RESULT_IMPORTED.value


def test_remote_result_source_rejected() -> None:
    record = valid_result_record().__dict__ | {"result_source": "https://example.invalid/result.json"}
    result = import_manual_qlib_runtime_results(manual_plan(), (QlibRuntimeResultRecord(**record),))

    assert result.ok is False
    assert "remote_result_source:0" in result.blockers


def test_dataset_mismatch_rejected() -> None:
    record = valid_result_record().__dict__ | {"dataset_id": "wrong-dataset"}
    result = import_manual_qlib_runtime_results(manual_plan(), (QlibRuntimeResultRecord(**record),))

    assert result.ok is False
    assert "dataset_id_mismatch:0" in result.blockers


def test_workflow_mismatch_rejected() -> None:
    record = valid_result_record().__dict__ | {"workflow_config_id": "wrong-workflow"}
    result = import_manual_qlib_runtime_results(manual_plan(), (QlibRuntimeResultRecord(**record),))

    assert result.ok is False
    assert "workflow_config_id_mismatch:0" in result.blockers


def test_missing_ic_rankic_or_equivalent_reason_handled() -> None:
    record = valid_result_record().__dict__ | {
        "metrics": {"cost_adjusted_score": 0.89},
        "missing_metric_reasons": {"ic_rank_ic": "manual result omitted factor metrics"},
    }
    result = import_manual_qlib_runtime_results(manual_plan(), (QlibRuntimeResultRecord(**record),))

    assert result.ok is True


def test_cost_aware_metric_or_missing_reason_required() -> None:
    record = valid_result_record().__dict__ | {"metrics": {"ic": 0.04}, "missing_metric_reasons": {}}
    result = import_manual_qlib_runtime_results(manual_plan(), (QlibRuntimeResultRecord(**record),))

    assert result.ok is False
    assert "cost_aware_metric_missing:0" in result.blockers


def test_profitability_claim_rejected() -> None:
    record = valid_result_record().__dict__ | {"profitability_claim": True}
    result = import_manual_qlib_runtime_results(manual_plan(), (QlibRuntimeResultRecord(**record),))

    assert result.ok is False
    assert "profitability_claim_rejected:0" in result.blockers


def test_benchmark_required() -> None:
    record = valid_result_record().__dict__ | {"benchmark": ""}
    result = import_manual_qlib_runtime_results(manual_plan(), (QlibRuntimeResultRecord(**record),))

    assert result.ok is False
    assert "benchmark_missing:0" in result.blockers


def test_stock_etf_coverage_preserved() -> None:
    result = import_manual_qlib_runtime_results(manual_plan(), (valid_result_record(),))

    assert result.imported_records[0].stock_count == 1
    assert result.imported_records[0].etf_count == 1


def test_execution_mode_manual_or_import_only_required() -> None:
    record = valid_result_record().__dict__ | {
        "execution_mode": QlibRuntimeExecutionMode.DISABLED_DEFAULT.value
    }
    result = import_manual_qlib_runtime_results(manual_plan(), (QlibRuntimeResultRecord(**record),))

    assert result.ok is False
    assert "execution_mode_not_manual_or_import_only:0" in result.blockers


def test_comparison_against_p41_offline_proxy_computed() -> None:
    detection = detect_optional_qlib_runtime(
        execution_mode=QlibRuntimeExecutionMode.MANUAL_LOCAL_ONLY.value,
        find_spec_func=lambda name: object(),
    )
    import_result = import_manual_qlib_runtime_results(manual_plan(), (valid_result_record(),))
    comparison = compare_runtime_results_with_offline_proxy(p41_report(), detection, import_result)

    assert comparison.offline_vs_runtime_score_delta == 0.02
    assert "offline_score:0.87" in comparison.comparison_notes


def test_comparison_against_p40_baseline_metadata_computed_when_available() -> None:
    detection = detect_optional_qlib_runtime(find_spec_func=lambda name: object())
    import_result = import_manual_qlib_runtime_results(manual_plan(), (valid_result_record(),))
    comparison = compare_runtime_results_with_offline_proxy(p41_report(), detection, import_result)

    assert "p40_next_target:install optional Qlib environment" in comparison.comparison_notes


def test_promotion_decision_computed() -> None:
    report = build_controlled_qlib_runtime_report(
        p41_report(),
        (valid_result_record(),),
        execution_mode=QlibRuntimeExecutionMode.MANUAL_LOCAL_ONLY.value,
        find_spec_func=lambda name: object(),
    )

    assert report.comparison.promotion_decision == "promote_to_real_qlib_runtime_trial"


def test_qrun_disabled_by_default() -> None:
    report = build_controlled_qlib_runtime_report(p41_report())

    assert report.qrun_disabled_by_default is True


def test_no_required_qlib_import_in_default_tests() -> None:
    build_controlled_qlib_runtime_report(p41_report(), find_spec_func=lambda name: None)

    assert "qlib" not in sys.modules


def test_no_real_profitability_claim() -> None:
    report = build_controlled_qlib_runtime_report(p41_report(), (valid_result_record(),))

    assert report.avoided_profitability_claims is True


def test_safety_barrier_remains_at_or_below_140() -> None:
    report = build_controlled_qlib_runtime_report(
        p41_report(),
        (valid_result_record(),),
        safety_barrier_percent=185.0,
    )

    assert report.safety_barrier_percent <= 140.0


def test_deterministic_report_ordering() -> None:
    report = build_controlled_qlib_runtime_report(p41_report(), (valid_result_record(),))

    assert report.manual_plan.config_summary == (
        "dataset:p41-qlib-local-mixed-stock-etf",
        "universe:quantpilot_mixed_stock_etf_small_sample",
        "benchmark:000300.SH",
        "factors:momentum_proxy,volatility_proxy,liquidity_proxy,cost_drag_proxy,etf_category_proxy,capital_fit_proxy,ai_shadow_preference_proxy",
    )
    assert report.evidence_refs == ("evidence://p42/spec",)


def test_report_answers_p42_questions() -> None:
    report = build_controlled_qlib_runtime_report(
        p41_report(),
        (valid_result_record(),),
        execution_mode=QlibRuntimeExecutionMode.MANUAL_LOCAL_ONLY.value,
        find_spec_func=lambda name: object(),
    )

    assert report.kept_qlib_optional is True
    assert report.manual_execution_plan_produced is True
    assert report.runtime_result_import_boundary_produced is True
    assert report.imported_runtime_like_result_validated is True
    assert report.comparison_against_p41_p40_completed is True
    assert report.mixed_stock_etf_coverage_visible is True
    assert report.next_improvement_target == "real Qlib installation"


def test_no_network_broker_llm_or_runtime_execution_patterns() -> None:
    package_root = Path("src/quantpilot_core/controlled_optional_qlib_runtime_spike")
    source_text = "\n".join(path.read_text() for path in sorted(package_root.glob("*.py")))

    forbidden_fragments = (
        "requests.",
        "connect_broker(",
        "place_order(",
        "send_order(",
        "submit_order(",
        "execute_order(",
        "api_key",
        "access_token",
        "qrun(",
        "import qlib",
        "from qlib",
    )
    assert not any(fragment in source_text for fragment in forbidden_fragments)
