from __future__ import annotations

import json
import sys
from pathlib import Path

from quantpilot_core.ai_open_source_provider_small_sample_mixed_etf_replay import (
    OpenSourceProviderExportSpec,
    OpenSourceProviderName,
    ProviderExportSourceType,
)
from quantpilot_core.controlled_optional_qlib_runtime_spike import (
    build_manual_qlib_execution_plan,
    detect_optional_qlib_runtime,
)
from quantpilot_core.isolated_manual_qlib_runtime_trial_runbook import (
    build_qlib_result_capture_template,
)
from quantpilot_core.manual_isolated_qlib_runtime_result_import_trial import (
    QlibImportTrialStatus,
    QlibResultArtifactSourceType,
    build_manual_isolated_qlib_import_trial_report,
    compare_manual_qlib_import_trial,
    load_qlib_result_artifact,
    run_manual_qlib_result_import_trial,
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
        source_uri="fixtures/p44/akshare_export",
        approved_by="qa_reviewer",
        approval_reason="approved deterministic small sample",
        export_timestamp="2026-01-07T00:00:00",
        provider_schema_mapping=provider_mapping(),
        evaluation_start="2026-01-02",
        evaluation_end="2026-01-06",
        initial_cash=100_000.0,
        evidence_refs=("evidence://p44/spec",),
    )


def p41_report():
    return build_p41_qlib_workflow_report(
        provider_spec(),
        records(),
        qlib_field_mapping=qlib_mapping(),
    )


def manual_plan():
    return build_manual_qlib_execution_plan(p41_report())


def valid_artifact() -> dict[str, object]:
    plan = manual_plan()
    return {
        "result_source": "local/manual_qlib_result.json",
        "dataset_id": plan.dataset_id,
        "workflow_config_id": plan.workflow_config_id,
        "metrics": {
            "ic": 0.04,
            "rank_ic": 0.05,
            "cost_adjusted_score": 0.89,
            "cost_aware_return_proxy": 0.89,
        },
        "missing_metric_reasons": {},
        "profitability_claim": False,
        "benchmark": "000300.SH",
        "stock_count": 1,
        "etf_count": 1,
        "execution_mode": "import_result_only",
        "warnings": ("manual_result_fixture",),
    }


def test_deterministic_fixture_artifact_loads() -> None:
    result = load_qlib_result_artifact(valid_artifact())

    assert result.ok is True
    assert result.source_type == QlibResultArtifactSourceType.DETERMINISTIC_FIXTURE.value
    assert result.normalized_record is not None


def test_p43_capture_template_style_artifact_loads() -> None:
    template = build_qlib_result_capture_template(manual_plan())
    result = load_qlib_result_artifact(
        template,
        source_type=QlibResultArtifactSourceType.P43_CAPTURE_TEMPLATE.value,
    )

    assert result.ok is True
    assert result.normalized_record is not None
    assert result.normalized_record.dataset_id == manual_plan().dataset_id


def test_manual_local_result_record_loads_from_local_json(tmp_path: Path) -> None:
    path = tmp_path / "manual-result.json"
    path.write_text(json.dumps(valid_artifact()), encoding="utf-8")

    result = load_qlib_result_artifact(
        path,
        source_type=QlibResultArtifactSourceType.MANUAL_LOCAL_RESULT_RECORD.value,
    )

    assert result.ok is True
    assert result.artifact_source == str(path)


def test_remote_artifact_source_rejected() -> None:
    result = load_qlib_result_artifact("https://example.invalid/manual-result.json")

    assert result.ok is False
    assert "remote_artifact_source_rejected" in result.blockers


def test_missing_dataset_id_rejected() -> None:
    artifact = valid_artifact()
    artifact.pop("dataset_id")

    result = load_qlib_result_artifact(artifact)

    assert result.ok is False
    assert "dataset_id_missing" in result.blockers


def test_missing_workflow_config_id_rejected() -> None:
    artifact = valid_artifact()
    artifact["workflow_config_id"] = ""

    result = load_qlib_result_artifact(artifact)

    assert result.ok is False
    assert "workflow_config_id_missing" in result.blockers


def test_missing_benchmark_rejected() -> None:
    artifact = valid_artifact()
    artifact["benchmark"] = ""

    result = load_qlib_result_artifact(artifact)

    assert result.ok is False
    assert "benchmark_missing" in result.blockers


def test_negative_stock_or_etf_count_rejected() -> None:
    artifact = valid_artifact()
    artifact["etf_count"] = -1

    result = load_qlib_result_artifact(artifact)

    assert result.ok is False
    assert "etf_count_negative" in result.blockers


def test_missing_ic_rankic_without_reason_rejected() -> None:
    artifact = valid_artifact()
    artifact["metrics"] = {"cost_adjusted_score": 0.89}

    result = load_qlib_result_artifact(artifact)

    assert result.ok is False
    assert "ic_rankic_metric_or_reason_missing" in result.blockers


def test_missing_cost_aware_metric_without_reason_rejected() -> None:
    artifact = valid_artifact()
    artifact["metrics"] = {"ic": 0.04}

    result = load_qlib_result_artifact(artifact)

    assert result.ok is False
    assert "cost_aware_metric_or_reason_missing" in result.blockers


def test_profitability_claim_rejected() -> None:
    artifact = valid_artifact()
    artifact["profitability_claim"] = True

    result = load_qlib_result_artifact(artifact)

    assert result.ok is False
    assert "profitability_claim_rejected" in result.blockers


def test_warnings_preserved() -> None:
    result = run_manual_qlib_result_import_trial(manual_plan(), valid_artifact())

    assert result.warnings_preserved == ("manual_result_fixture",)


def test_import_accepted_through_p42_compatible_boundary() -> None:
    result = run_manual_qlib_result_import_trial(manual_plan(), valid_artifact())

    assert result.ok is True
    assert result.status == QlibImportTrialStatus.IMPORT_ACCEPTED.value
    assert result.import_accepted is True


def test_import_rejected_with_reasons() -> None:
    artifact = valid_artifact() | {"dataset_id": "wrong-dataset"}

    result = run_manual_qlib_result_import_trial(manual_plan(), artifact)

    assert result.ok is False
    assert "dataset_id_mismatch:0" in result.rejection_reasons


def test_dataset_workflow_match_reported() -> None:
    result = run_manual_qlib_result_import_trial(manual_plan(), valid_artifact())

    assert result.dataset_workflow_match is True


def test_mixed_stock_etf_coverage_preserved() -> None:
    result = run_manual_qlib_result_import_trial(manual_plan(), valid_artifact())

    assert result.mixed_stock_etf_coverage_preserved is True


def test_comparison_against_p42_p41_p40_direction_computed() -> None:
    report = build_manual_isolated_qlib_import_trial_report(
        p41_report(),
        valid_artifact(),
        runtime_available=True,
    )

    assert report.compared_against_p42_p41_p40_direction is True
    assert report.comparison.offline_vs_runtime_score_delta == 0.02
    assert "p40_next_target:install optional Qlib environment" in report.comparison.comparison_notes


def test_promotion_decision_computed() -> None:
    report = build_manual_isolated_qlib_import_trial_report(
        p41_report(),
        valid_artifact(),
        runtime_available=True,
    )

    assert report.comparison.promotion_decision == "require_real_qrun_result"
    assert report.next_step == "run real isolated Qlib"


def test_no_qrun_execution_or_required_runtime_package() -> None:
    report = build_manual_isolated_qlib_import_trial_report(p41_report(), valid_artifact())

    assert report.avoided_qrun_and_runtime_import_by_default is True
    assert "qlib" not in sys.modules


def test_no_network_broker_llm_or_dependency_installation_patterns() -> None:
    package_root = Path("src/quantpilot_core/manual_isolated_qlib_runtime_result_import_trial")
    source_text = "\n".join(path.read_text() for path in sorted(package_root.glob("*.py")))

    forbidden_fragments = (
        "requests.",
        "connect_broker(",
        "place_order(",
        "send_order(",
        "submit_order(",
        "execute_order(",
        "openai",
        "deepseek",
        "pip install",
        "pyproject.toml",
        "qrun(",
        "import qlib",
        "from qlib",
    )
    assert not any(fragment in source_text.lower() for fragment in forbidden_fragments)


def test_no_real_profitability_claim() -> None:
    report = build_manual_isolated_qlib_import_trial_report(p41_report(), valid_artifact())

    assert report.avoided_profitability_claims is True


def test_safety_barrier_remains_at_or_below_140() -> None:
    report = build_manual_isolated_qlib_import_trial_report(
        p41_report(),
        valid_artifact(),
        safety_barrier_percent=185.0,
    )

    assert report.safety_barrier_percent <= 140.0


def test_deterministic_report_ordering() -> None:
    report = build_manual_isolated_qlib_import_trial_report(
        p41_report(),
        valid_artifact(),
        runtime_available=True,
    )

    assert report.evidence_refs == ("evidence://p44/manual-isolated-result-import",)
    assert report.comparison.comparison_notes == tuple(sorted(report.comparison.comparison_notes))


def test_report_answers_p44_questions() -> None:
    report = build_manual_isolated_qlib_import_trial_report(
        p41_report(),
        valid_artifact(),
        runtime_available=True,
    )

    assert report.p43_compatible_result_artifact_loaded is True
    assert report.imported_through_p42_boundary is True
    assert report.import_accepted is True
    assert report.mixed_stock_etf_counts_preserved is True
    assert report.avoided_qrun_and_runtime_import_by_default is True
    assert report.avoided_profitability_claims is True


def test_comparison_helper_can_be_called_directly() -> None:
    import_trial = run_manual_qlib_result_import_trial(manual_plan(), valid_artifact())
    detection = detect_optional_qlib_runtime(find_spec_func=lambda name: object())
    comparison = compare_manual_qlib_import_trial(
        p41_report(),
        detection,
        import_trial,
    )

    assert comparison.import_trial_status == QlibImportTrialStatus.COMPARISON_COMPLETED.value
