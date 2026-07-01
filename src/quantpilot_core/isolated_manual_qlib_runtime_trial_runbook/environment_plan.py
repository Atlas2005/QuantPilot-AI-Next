"""Isolated environment plan for manual Qlib trial."""

from __future__ import annotations

from quantpilot_core.isolated_manual_qlib_runtime_trial_runbook.contracts import (
    IsolatedQlibEnvironmentPlan,
    QlibTrialEnvironmentType,
)


def build_isolated_qlib_environment_plan(
    environment_type: str = QlibTrialEnvironmentType.ISOLATED_VENV.value,
) -> IsolatedQlibEnvironmentPlan:
    """Create documentation-only isolated environment instructions."""

    if environment_type == QlibTrialEnvironmentType.CONDA_ENV.value:
        name = "quantpilot-qlib-manual"
        create_command = f"conda create -n {name} python=3.12"
        cleanup_command = f"conda env remove -n {name}"
    elif environment_type == QlibTrialEnvironmentType.CONTAINER_OPTIONAL.value:
        name = "quantpilot-qlib-container"
        create_command = "podman build -t quantpilot-qlib-manual ./manual_runtime"
        cleanup_command = "podman image rm quantpilot-qlib-manual"
    else:
        name = ".manual_qlib_venv"
        create_command = "python3.12 -m venv .manual_qlib_venv"
        cleanup_command = "rm -rf .manual_qlib_venv"

    return IsolatedQlibEnvironmentPlan(
        environment_type=environment_type,
        environment_name=name,
        default_project_env_unchanged=True,
        pyproject_unchanged=True,
        qlib_optional_dependency=True,
        install_commands=(
            create_command,
            "python -m pip install pyqlib",
        ),
        install_commands_documentation_only=True,
        python_version_note="Use an isolated Python version compatible with the optional runtime.",
        cleanup_commands=(cleanup_command,),
        rollback_notes=(
            "Delete the isolated environment only.",
            "Do not change the default project environment.",
            "Do not edit project dependency files.",
        ),
        warnings=(
            "documentation_only_no_install_performed",
            "manual_network_choice_only_for_optional_install",
            "default_tests_do_not_use_this_environment",
        ),
    )
