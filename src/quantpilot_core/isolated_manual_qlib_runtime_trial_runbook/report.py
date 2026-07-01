"""Report builder for P43 isolated manual Qlib runtime trial runbook."""

from __future__ import annotations

import quantpilot_core.controlled_optional_qlib_runtime_spike.contracts as p42_contracts
from quantpilot_core.isolated_manual_qlib_runtime_trial_runbook.artifact_checklist import (
    build_qlib_trial_artifact_checklist,
)
from quantpilot_core.isolated_manual_qlib_runtime_trial_runbook.command_plan import (
    build_qlib_manual_command_plan,
)
from quantpilot_core.isolated_manual_qlib_runtime_trial_runbook.contracts import (
    P43IsolatedQlibTrialRunbookReport,
    QlibTrialEnvironmentType,
    QlibTrialExecutionStatus,
)
from quantpilot_core.isolated_manual_qlib_runtime_trial_runbook.environment_plan import (
    build_isolated_qlib_environment_plan,
)
from quantpilot_core.isolated_manual_qlib_runtime_trial_runbook.result_capture import (
    build_qlib_result_capture_template,
)


def build_isolated_qlib_trial_runbook_report(
    manual_plan: p42_contracts.QlibManualExecutionPlan,
    *,
    environment_type: str = QlibTrialEnvironmentType.ISOLATED_VENV.value,
    missing_artifact_kinds: tuple[str, ...] = (),
    safety_barrier_percent: float = 140.0,
) -> P43IsolatedQlibTrialRunbookReport:
    """Build the isolated manual runtime trial runbook report."""

    environment = build_isolated_qlib_environment_plan(environment_type)
    checklist = build_qlib_trial_artifact_checklist(missing_artifact_kinds)
    commands = build_qlib_manual_command_plan(environment)
    template = build_qlib_result_capture_template(manual_plan)
    ready = checklist.all_required_present and environment.default_project_env_unchanged
    return P43IsolatedQlibTrialRunbookReport(
        ready_for_isolated_manual_qlib_runtime_trial=ready,
        default_pytest_environment_unchanged=environment.default_project_env_unchanged,
        pyproject_dependency_changes_avoided=environment.pyproject_unchanged,
        artifact_checklist_provided=True,
        manual_command_templates_provided=True,
        p42_compatible_result_capture_template_provided=True,
        runtime_not_executed_by_default=commands.runtime_not_executed_by_default,
        qlib_still_optional=environment.qlib_optional_dependency,
        safety_barrier_percent=min(round(safety_barrier_percent, 4), 140.0),
        next_step=_next_step(ready),
        execution_status=(
            QlibTrialExecutionStatus.READY_FOR_MANUAL_RUN.value
            if ready
            else QlibTrialExecutionStatus.NOT_RUN.value
        ),
        environment_plan=environment,
        artifact_checklist=checklist,
        command_plan=commands,
        result_capture_template=template,
        evidence_refs=("evidence://p43/runbook",),
    )


def _next_step(ready: bool) -> str:
    if ready:
        return "manually run isolated Qlib"
    return "improve provider sample quality"
