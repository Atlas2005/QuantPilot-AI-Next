from __future__ import annotations

import sys
from pathlib import Path

from quantpilot_core.ai_open_source_provider_small_sample_mixed_etf_replay import (
    OpenSourceProviderExportSpec,
    OpenSourceProviderName,
    ProviderExportSourceType,
)
from quantpilot_core.controlled_optional_qlib_runtime_spike import (
    build_manual_qlib_execution_plan,
    import_manual_qlib_runtime_results,
)
from quantpilot_core.controlled_optional_qlib_runtime_spike.contracts import (
    QlibRuntimeResultRecord,
)
from quantpilot_core.isolated_manual_qlib_runtime_trial_runbook import (
    QlibTrialArtifactKind,
    QlibTrialEnvironmentType,
    build_isolated_qlib_environment_plan,
    build_isolated_qlib_trial_runbook_report,
    build_qlib_manual_command_plan,
    build_qlib_result_capture_template,
    build_qlib_trial_artifact_checklist,
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
        source_uri="fixtures/p43/akshare_export",
        approved_by="qa_reviewer",
        approval_reason="approved deterministic small sample",
        export_timestamp="2026-01-07T00:00:00",
        provider_schema_mapping=provider_mapping(),
        evaluation_start="2026-01-02",
        evaluation_end="2026-01-06",
        initial_cash=100_000.0,
        evidence_refs=("evidence://p43/spec",),
    )


def p42_manual_plan():
    p41 = build_p41_qlib_workflow_report(
        provider_spec(),
        records(),
        qlib_field_mapping=qlib_mapping(),
    )
    return build_manual_qlib_execution_plan(p41)


def test_isolated_venv_environment_plan_created() -> None:
    plan = build_isolated_qlib_environment_plan()

    assert plan.environment_type == QlibTrialEnvironmentType.ISOLATED_VENV.value
    assert plan.environment_name == ".manual_qlib_venv"


def test_conda_environment_plan_created() -> None:
    plan = build_isolated_qlib_environment_plan(QlibTrialEnvironmentType.CONDA_ENV.value)

    assert plan.environment_type == QlibTrialEnvironmentType.CONDA_ENV.value
    assert plan.environment_name == "quantpilot-qlib-manual"


def test_default_project_env_unchanged() -> None:
    plan = build_isolated_qlib_environment_plan()

    assert plan.default_project_env_unchanged is True


def test_pyproject_unchanged() -> None:
    plan = build_isolated_qlib_environment_plan()

    assert plan.pyproject_unchanged is True


def test_qlib_optional_dependency_marked() -> None:
    plan = build_isolated_qlib_environment_plan()

    assert plan.qlib_optional_dependency is True


def test_install_commands_are_documentation_only() -> None:
    plan = build_isolated_qlib_environment_plan()

    assert plan.install_commands
    assert plan.install_commands_documentation_only is True


def test_cleanup_and_rollback_notes_exist() -> None:
    plan = build_isolated_qlib_environment_plan()

    assert plan.cleanup_commands
    assert plan.rollback_notes


def test_artifact_checklist_includes_all_required_kinds() -> None:
    checklist = build_qlib_trial_artifact_checklist()

    assert tuple(item.kind for item in checklist.items) == tuple(
        kind.value for kind in QlibTrialArtifactKind
    )
    assert checklist.all_required_present is True


def test_missing_required_artifact_is_blocker() -> None:
    checklist = build_qlib_trial_artifact_checklist(
        (QlibTrialArtifactKind.DATASET_SPEC.value,)
    )

    assert checklist.all_required_present is False
    assert "missing_required_artifact:dataset_spec" in checklist.blockers


def test_command_plan_includes_runtime_template_but_not_executed() -> None:
    command_plan = build_qlib_manual_command_plan(build_isolated_qlib_environment_plan())

    assert "qrun " in command_plan.runtime_command_template
    assert command_plan.runtime_not_executed_by_default is True
    assert command_plan.commands_documentation_only is True


def test_command_plan_has_no_broker_account_credential_commands() -> None:
    command_plan = build_qlib_manual_command_plan(build_isolated_qlib_environment_plan())

    assert command_plan.no_broker_account_credential_commands is True
    text = " ".join(
        (
            command_plan.isolated_environment_creation_command,
            command_plan.optional_qlib_installation_command,
            command_plan.dataset_preparation_command_placeholder,
            command_plan.runtime_command_template,
            command_plan.result_export_command_placeholder,
            command_plan.result_import_command_placeholder,
        )
    )
    assert "broker" not in text
    assert "account" not in text
    assert "credential" not in text


def test_command_plan_uses_local_paths_only() -> None:
    command_plan = build_qlib_manual_command_plan(build_isolated_qlib_environment_plan())

    assert command_plan.local_filesystem_paths_only is True


def test_result_capture_template_matches_p42_import_expectations() -> None:
    template = build_qlib_result_capture_template(p42_manual_plan())
    record = QlibRuntimeResultRecord(
        result_source=template.result_source,
        dataset_id=template.dataset_id,
        workflow_config_id=template.workflow_config_id,
        metrics=template.metrics,
        missing_metric_reasons=template.missing_metric_reasons,
        profitability_claim=template.profitability_claim,
        benchmark=template.benchmark,
        stock_count=template.stock_count,
        etf_count=template.etf_count,
        execution_mode=template.execution_mode,
        warnings=template.warnings,
    )

    result = import_manual_qlib_runtime_results(p42_manual_plan(), (record,))

    assert result.ok is True


def test_result_capture_template_sets_profitability_claim_false() -> None:
    template = build_qlib_result_capture_template(p42_manual_plan())

    assert template.profitability_claim is False


def test_report_ready_for_manual_run_when_required_artifacts_present() -> None:
    report = build_isolated_qlib_trial_runbook_report(p42_manual_plan())

    assert report.ready_for_isolated_manual_qlib_runtime_trial is True
    assert report.execution_status == "ready_for_manual_run"


def test_report_blocks_manual_run_when_required_artifacts_missing() -> None:
    report = build_isolated_qlib_trial_runbook_report(
        p42_manual_plan(),
        missing_artifact_kinds=(QlibTrialArtifactKind.WORKFLOW_CONFIG.value,),
    )

    assert report.ready_for_isolated_manual_qlib_runtime_trial is False
    assert "missing_required_artifact:workflow_config" in report.artifact_checklist.blockers


def test_qrun_not_executed_by_default() -> None:
    report = build_isolated_qlib_trial_runbook_report(p42_manual_plan())

    assert report.runtime_not_executed_by_default is True


def test_no_network_broker_llm_or_qlib_required_import() -> None:
    package_root = Path("src/quantpilot_core/isolated_manual_qlib_runtime_trial_runbook")
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
        "import qlib",
        "from qlib",
    )
    assert not any(fragment in source_text for fragment in forbidden_fragments)
    assert "qlib" not in sys.modules


def test_no_dependency_installation_or_pyproject_modification() -> None:
    report = build_isolated_qlib_trial_runbook_report(p42_manual_plan())

    assert report.environment_plan.install_commands_documentation_only is True
    assert report.pyproject_dependency_changes_avoided is True


def test_no_real_profitability_claim() -> None:
    report = build_isolated_qlib_trial_runbook_report(p42_manual_plan())

    assert report.result_capture_template.profitability_claim is False


def test_safety_barrier_remains_at_or_below_140() -> None:
    report = build_isolated_qlib_trial_runbook_report(
        p42_manual_plan(),
        safety_barrier_percent=185.0,
    )

    assert report.safety_barrier_percent <= 140.0


def test_deterministic_report_ordering() -> None:
    report = build_isolated_qlib_trial_runbook_report(p42_manual_plan())

    assert tuple(item.kind for item in report.artifact_checklist.items) == tuple(
        kind.value for kind in QlibTrialArtifactKind
    )
    assert report.evidence_refs == ("evidence://p43/runbook",)


def test_report_answers_p43_questions() -> None:
    report = build_isolated_qlib_trial_runbook_report(p42_manual_plan())

    assert report.default_pytest_environment_unchanged is True
    assert report.pyproject_dependency_changes_avoided is True
    assert report.artifact_checklist_provided is True
    assert report.manual_command_templates_provided is True
    assert report.p42_compatible_result_capture_template_provided is True
    assert report.qlib_still_optional is True
    assert report.next_step == "manually run isolated Qlib"
