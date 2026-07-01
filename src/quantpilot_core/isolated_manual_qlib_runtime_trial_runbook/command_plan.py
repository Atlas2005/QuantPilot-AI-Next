"""Manual command templates for isolated Qlib runtime trial."""

from __future__ import annotations

from quantpilot_core.isolated_manual_qlib_runtime_trial_runbook.contracts import (
    IsolatedQlibEnvironmentPlan,
    QlibManualCommandPlan,
)


def build_qlib_manual_command_plan(
    environment_plan: IsolatedQlibEnvironmentPlan,
    *,
    dataset_path: str = "local_artifacts/p41_dataset",
    workflow_config_path: str = "local_artifacts/p41_workflow_config.yaml",
    result_path: str = "local_artifacts/p42_manual_result.json",
) -> QlibManualCommandPlan:
    """Create documentation-only command templates."""

    return QlibManualCommandPlan(
        isolated_environment_creation_command=environment_plan.install_commands[0],
        optional_qlib_installation_command=environment_plan.install_commands[1],
        dataset_preparation_command_placeholder=(
            f"python scripts/manual_prepare_dataset.py --input {dataset_path}"
        ),
        runtime_command_template=(
            f"qrun {workflow_config_path} --experiment-name quantpilot_manual_qlib_trial"
        ),
        result_export_command_placeholder=(
            f"python scripts/manual_export_result.py --output {result_path}"
        ),
        result_import_command_placeholder=(
            f"python -m quantpilot_core.controlled_optional_qlib_runtime_spike --import {result_path}"
        ),
        commands_documentation_only=True,
        runtime_not_executed_by_default=True,
        network_disabled_by_default=True,
        no_broker_account_credential_commands=True,
        local_filesystem_paths_only=all(
            not value.startswith(("http://", "https://"))
            for value in (dataset_path, workflow_config_path, result_path)
        ),
        warnings=(
            "commands_are_templates_only",
            "manual_user_confirmation_required",
            "no_broker_account_or_credential_command_allowed",
        ),
    )
