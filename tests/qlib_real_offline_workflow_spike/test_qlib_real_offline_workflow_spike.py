from __future__ import annotations

import sys
from pathlib import Path

from quantpilot_core.ai_open_source_provider_small_sample_mixed_etf_replay import (
    OpenSourceProviderExportSpec,
    OpenSourceProviderName,
    ProviderExportSourceType,
    build_p40_ai_provider_replay_report,
)
from quantpilot_core.qlib_real_offline_workflow_spike import (
    QlibDatasetSourceType,
    QlibFieldMapping,
    QlibInstrumentKind,
    QlibRuntimeStatus,
    build_p41_qlib_workflow_report,
    build_qlib_factor_candidates,
    build_qlib_local_dataset_spec,
    build_qlib_workflow_config,
    compare_qlib_evaluation_with_p40,
    detect_qlib_runtime_status,
    evaluate_qlib_style_offline_workflow,
    validate_qlib_dataset_records,
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
        source_uri="fixtures/p41/akshare_export",
        approved_by="qa_reviewer",
        approval_reason="approved deterministic small sample",
        export_timestamp="2026-01-07T00:00:00",
        provider_schema_mapping=provider_mapping(),
        evaluation_start="2026-01-02",
        evaluation_end="2026-01-06",
        initial_cash=100_000.0,
        evidence_refs=("evidence://p41/spec",),
    )


def dataset_spec(input_records: tuple[dict[str, object], ...] | None = None):
    return build_qlib_local_dataset_spec(
        dataset_id="p41-qlib-local-mixed-stock-etf",
        provider_name=OpenSourceProviderName.AKSHARE.value,
        source_type=QlibDatasetSourceType.DETERMINISTIC_FIXTURE.value,
        records=input_records or records(),
        field_mapping=qlib_mapping(),
        evaluation_start="2026-01-02",
        evaluation_end="2026-01-06",
        mixed_mode=True,
    )


def test_deterministic_fixture_dataset_accepted() -> None:
    dataset = dataset_spec()

    assert dataset.source_type == QlibDatasetSourceType.DETERMINISTIC_FIXTURE.value
    assert dataset.stock_count == 1
    assert dataset.etf_count == 1


def test_approved_provider_export_dataset_accepted() -> None:
    dataset = build_qlib_local_dataset_spec(
        dataset_id="p41-approved-provider",
        provider_name=OpenSourceProviderName.AKSHARE.value,
        source_type=QlibDatasetSourceType.APPROVED_PROVIDER_EXPORT.value,
        records=records(),
        field_mapping=qlib_mapping(),
        evaluation_start="2026-01-02",
        evaluation_end="2026-01-06",
        mixed_mode=True,
    )

    assert dataset.provider_name == OpenSourceProviderName.AKSHARE.value
    assert dataset.source_type == QlibDatasetSourceType.APPROVED_PROVIDER_EXPORT.value


def test_mixed_stock_etf_coverage_required_in_mixed_mode() -> None:
    stock_only = tuple(row for row in records() if row["instrument_type"] == "stock")

    blockers = validate_qlib_dataset_records(
        records=stock_only,
        field_mapping=qlib_mapping(),
        evaluation_start="2026-01-02",
        evaluation_end="2026-01-06",
        mixed_mode=True,
        source_type=QlibDatasetSourceType.DETERMINISTIC_FIXTURE.value,
    )

    assert "etf_coverage_missing" in blockers


def test_etf_category_required() -> None:
    rows = [dict(row) for row in records()]
    for row in rows:
        row.pop("etf_category", None)

    blockers = validate_qlib_dataset_records(
        records=tuple(rows),
        field_mapping=qlib_mapping(),
        evaluation_start="2026-01-02",
        evaluation_end="2026-01-06",
        mixed_mode=True,
        source_type=QlibDatasetSourceType.DETERMINISTIC_FIXTURE.value,
    )

    assert "etf_category_missing:510300.SH" in blockers


def test_explicit_instrument_kind_required() -> None:
    rows = [dict(row) for row in records()]
    rows[0].pop("instrument_kind")

    blockers = validate_qlib_dataset_records(
        records=tuple(rows),
        field_mapping=qlib_mapping(),
        evaluation_start="2026-01-02",
        evaluation_end="2026-01-06",
        mixed_mode=True,
        source_type=QlibDatasetSourceType.DETERMINISTIC_FIXTURE.value,
    )

    assert "missing_ohlcv_fields:0:instrument_kind" in blockers


def test_ohlcv_like_fields_required() -> None:
    rows = [dict(row) for row in records()]
    rows[0].pop("open")

    blockers = validate_qlib_dataset_records(
        records=tuple(rows),
        field_mapping=qlib_mapping(),
        evaluation_start="2026-01-02",
        evaluation_end="2026-01-06",
        mixed_mode=True,
        source_type=QlibDatasetSourceType.DETERMINISTIC_FIXTURE.value,
    )

    assert "missing_ohlcv_fields:0:open" in blockers


def test_duplicate_symbol_date_rejected() -> None:
    blockers = validate_qlib_dataset_records(
        records=(*records(), dict(records()[0])),
        field_mapping=qlib_mapping(),
        evaluation_start="2026-01-02",
        evaluation_end="2026-01-06",
        mixed_mode=True,
        source_type=QlibDatasetSourceType.DETERMINISTIC_FIXTURE.value,
    )

    assert "duplicate_symbol_date:000001.SZ:2026-01-02" in blockers


def test_future_rows_rejected() -> None:
    rows = [dict(row) for row in records()]
    rows[-1]["trade_date"] = "2026-01-07"

    blockers = validate_qlib_dataset_records(
        records=tuple(rows),
        field_mapping=qlib_mapping(),
        evaluation_start="2026-01-02",
        evaluation_end="2026-01-06",
        mixed_mode=True,
        source_type=QlibDatasetSourceType.DETERMINISTIC_FIXTURE.value,
    )

    assert "future_dated_row:510300.SH:2026-01-07" in blockers


def test_missing_close_and_volume_rejected() -> None:
    rows = [dict(row) for row in records()]
    rows[0]["close"] = None
    rows[1]["volume"] = 0

    blockers = validate_qlib_dataset_records(
        records=tuple(rows),
        field_mapping=qlib_mapping(),
        evaluation_start="2026-01-02",
        evaluation_end="2026-01-06",
        mixed_mode=True,
        source_type=QlibDatasetSourceType.DETERMINISTIC_FIXTURE.value,
    )

    assert "non_numeric_close:0" in blockers
    assert "missing_volume:1" in blockers


def test_deterministic_date_normalization() -> None:
    dataset = dataset_spec(tuple(reversed(records())))

    assert dataset.trading_calendar == ("2026-01-02", "2026-01-05", "2026-01-06")
    assert "dates_normalized_deterministically" in dataset.quality_flags


def test_dataset_spec_contains_provider_source_counts_and_mapping() -> None:
    dataset = dataset_spec()

    assert dataset.provider_name == OpenSourceProviderName.AKSHARE.value
    assert dataset.stock_count == 1
    assert dataset.etf_count == 1
    assert dataset.field_mapping.as_dict()["close"] == "close"


def test_workflow_config_contains_required_metadata() -> None:
    factors = build_qlib_factor_candidates()
    workflow = build_qlib_workflow_config(dataset_spec(), factors)

    assert workflow.dataset_id == "p41-qlib-local-mixed-stock-etf"
    assert workflow.universe_name == "quantpilot_mixed_stock_etf_small_sample"
    assert workflow.benchmark == "000300.SH"
    assert workflow.label_expression_placeholder
    assert workflow.factor_feature_list == tuple(factor.name for factor in factors)
    assert workflow.train_window_placeholder
    assert workflow.validation_window_placeholder
    assert workflow.test_window_placeholder
    assert workflow.cost_model_assumptions
    assert workflow.execution_assumptions


def test_qrun_disabled_by_default() -> None:
    workflow = build_qlib_workflow_config(dataset_spec(), build_qlib_factor_candidates())

    assert workflow.qrun_disabled_by_default is True


def test_qlib_optional_runtime_status_explicit() -> None:
    status = detect_qlib_runtime_status(qrun_disabled_by_default=False, importer=lambda name: (_ for _ in ()).throw(ImportError()))

    assert status == QlibRuntimeStatus.UNAVAILABLE_OPTIONAL_DEPENDENCY.value


def test_required_factor_candidates_generated() -> None:
    factors = build_qlib_factor_candidates()

    assert tuple(factor.name for factor in factors) == (
        "momentum_proxy",
        "volatility_proxy",
        "liquidity_proxy",
        "cost_drag_proxy",
        "etf_category_proxy",
        "capital_fit_proxy",
        "ai_shadow_preference_proxy",
    )


def test_factor_candidates_include_leakage_control_notes() -> None:
    factors = build_qlib_factor_candidates()

    assert all(factor.leakage_control_note for factor in factors)


def test_offline_evaluation_computes_scores() -> None:
    factors = build_qlib_factor_candidates()
    workflow = build_qlib_workflow_config(
        dataset_spec(),
        factors,
        runtime_status=QlibRuntimeStatus.UNAVAILABLE_OPTIONAL_DEPENDENCY.value,
    )
    evaluation = evaluate_qlib_style_offline_workflow(dataset_spec(), workflow, factors)

    assert evaluation.candidate_score == 0.92
    assert evaluation.cost_adjusted_score == 0.87
    assert evaluation.tradability_score == 0.8
    assert evaluation.small_capital_fit_score == 0.7


def test_no_real_profitability_claim() -> None:
    report = build_p41_qlib_workflow_report(provider_spec(), records(), qlib_field_mapping=qlib_mapping())

    assert report.evaluation_result.profitability_claim == "none_offline_proxy_only"


def test_comparison_against_p40_baseline_computed() -> None:
    report = build_p41_qlib_workflow_report(provider_spec(), records(), qlib_field_mapping=qlib_mapping())

    assert report.comparison_against_p40_completed is True
    assert "p40_net_delta:3.7347" in report.comparison.comparison_notes


def test_mixed_stock_etf_remains_supported() -> None:
    report = build_p41_qlib_workflow_report(provider_spec(), records(), qlib_field_mapping=qlib_mapping())

    assert report.mixed_stock_etf_covered is True
    assert report.comparison.mixed_stock_etf_supported is True


def test_qlib_promotion_blockers_reported() -> None:
    report = build_p41_qlib_workflow_report(provider_spec(), records(), qlib_field_mapping=qlib_mapping())

    assert "optional_qlib_dependency_unavailable" in report.comparison.promotion_blockers
    assert report.next_improvement_target == "install optional Qlib environment"


def test_available_runtime_can_be_marked_local_workflow_ready() -> None:
    report = build_p41_qlib_workflow_report(
        provider_spec(),
        records(),
        qlib_field_mapping=qlib_mapping(),
        runtime_status=QlibRuntimeStatus.LOCAL_WORKFLOW_READY.value,
    )

    assert report.workflow_config.runtime_status == QlibRuntimeStatus.LOCAL_WORKFLOW_READY.value
    assert report.comparison.workflow_ready_for_optional_runtime_later is True


def test_safety_barrier_remains_at_or_below_140() -> None:
    report = build_p41_qlib_workflow_report(
        provider_spec(),
        records(),
        qlib_field_mapping=qlib_mapping(),
        safety_barrier_percent=185.0,
    )

    assert report.safety_barrier_percent <= 140.0


def test_deterministic_report_ordering() -> None:
    report = build_p41_qlib_workflow_report(provider_spec(), records(), qlib_field_mapping=qlib_mapping())

    assert report.dataset_spec.instrument_symbols == ("000001.SZ", "510300.SH")
    assert tuple(factor.name for factor in report.factor_candidates) == (
        "momentum_proxy",
        "volatility_proxy",
        "liquidity_proxy",
        "cost_drag_proxy",
        "etf_category_proxy",
        "capital_fit_proxy",
        "ai_shadow_preference_proxy",
    )
    assert report.evidence_refs == ("evidence://p41/spec",)


def test_report_answers_p41_questions() -> None:
    report = build_p41_qlib_workflow_report(provider_spec(), records(), qlib_field_mapping=qlib_mapping())

    assert report.moved_beyond_metadata_only_handoff is True
    assert report.dataset_spec_produced is True
    assert report.workflow_config_produced is True
    assert report.factor_candidates_mapped is True
    assert report.offline_evaluation_computed is True
    assert report.qlib_runtime_disabled_by_default is True
    assert report.qlib_optional_dependency_status_explicit is True


def test_no_network_broker_llm_qrun_or_required_qlib_import() -> None:
    package_root = Path("src/quantpilot_core/qlib_real_offline_workflow_spike")
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
    assert "qlib" not in sys.modules
