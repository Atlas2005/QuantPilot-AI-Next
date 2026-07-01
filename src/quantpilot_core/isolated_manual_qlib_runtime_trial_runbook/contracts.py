"""Contracts for P43 isolated manual Qlib runtime trial runbook."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class QlibTrialEnvironmentType(str, Enum):
    ISOLATED_VENV = "isolated_venv"
    CONDA_ENV = "conda_env"
    CONTAINER_OPTIONAL = "container_optional"


class QlibTrialExecutionStatus(str, Enum):
    NOT_RUN = "not_run"
    READY_FOR_MANUAL_RUN = "ready_for_manual_run"
    MANUAL_RUN_COMPLETED_EXTERNALLY = "manual_run_completed_externally"
    RESULT_CAPTURE_READY = "result_capture_ready"


class QlibTrialArtifactKind(str, Enum):
    DATASET_SPEC = "dataset_spec"
    WORKFLOW_CONFIG = "workflow_config"
    FACTOR_MAPPING = "factor_mapping"
    COST_MODEL_ASSUMPTIONS = "cost_model_assumptions"
    EXECUTION_ASSUMPTIONS = "execution_assumptions"
    RESULT_RECORD_TEMPLATE = "result_record_template"


@dataclass(frozen=True)
class IsolatedQlibEnvironmentPlan:
    environment_type: str
    environment_name: str
    default_project_env_unchanged: bool
    pyproject_unchanged: bool
    qlib_optional_dependency: bool
    install_commands: tuple[str, ...]
    install_commands_documentation_only: bool
    python_version_note: str
    cleanup_commands: tuple[str, ...]
    rollback_notes: tuple[str, ...]
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class QlibTrialArtifactChecklistItem:
    kind: str
    required: bool
    present: bool
    source_module: str
    validation_note: str
    blocker_if_missing: str


@dataclass(frozen=True)
class QlibTrialArtifactChecklist:
    items: tuple[QlibTrialArtifactChecklistItem, ...]
    blockers: tuple[str, ...]
    all_required_present: bool


@dataclass(frozen=True)
class QlibManualCommandPlan:
    isolated_environment_creation_command: str
    optional_qlib_installation_command: str
    dataset_preparation_command_placeholder: str
    runtime_command_template: str
    result_export_command_placeholder: str
    result_import_command_placeholder: str
    commands_documentation_only: bool
    runtime_not_executed_by_default: bool
    network_disabled_by_default: bool
    no_broker_account_credential_commands: bool
    local_filesystem_paths_only: bool
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class QlibResultCaptureTemplate:
    result_source: str
    dataset_id: str
    workflow_config_id: str
    benchmark: str
    stock_count: int
    etf_count: int
    metrics: dict[str, float]
    missing_metric_reasons: dict[str, str]
    execution_mode: str
    profitability_claim: bool
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class P43IsolatedQlibTrialRunbookReport:
    ready_for_isolated_manual_qlib_runtime_trial: bool
    default_pytest_environment_unchanged: bool
    pyproject_dependency_changes_avoided: bool
    artifact_checklist_provided: bool
    manual_command_templates_provided: bool
    p42_compatible_result_capture_template_provided: bool
    runtime_not_executed_by_default: bool
    qlib_still_optional: bool
    safety_barrier_percent: float
    next_step: str
    execution_status: str
    environment_plan: IsolatedQlibEnvironmentPlan
    artifact_checklist: QlibTrialArtifactChecklist
    command_plan: QlibManualCommandPlan
    result_capture_template: QlibResultCaptureTemplate
    evidence_refs: tuple[str, ...]
