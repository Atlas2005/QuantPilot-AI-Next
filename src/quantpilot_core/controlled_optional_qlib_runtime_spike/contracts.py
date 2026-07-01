"""Contracts for P42 controlled optional Qlib runtime spike."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class OptionalQlibRuntimeState(str, Enum):
    UNAVAILABLE_OPTIONAL_DEPENDENCY = "unavailable_optional_dependency"
    AVAILABLE_MANUAL_EXECUTION_ONLY = "available_manual_execution_only"
    AVAILABLE_BUT_DISABLED_BY_DEFAULT = "available_but_disabled_by_default"
    MANUAL_RUNTIME_RESULT_IMPORTED = "manual_runtime_result_imported"


class QlibRuntimeExecutionMode(str, Enum):
    DISABLED_DEFAULT = "disabled_default"
    MANUAL_LOCAL_ONLY = "manual_local_only"
    IMPORT_RESULT_ONLY = "import_result_only"


@dataclass(frozen=True)
class QlibRuntimeDetectionResult:
    runtime_state: str
    execution_mode: str
    runtime_available: bool
    runtime_imported: bool
    qrun_disabled_by_default: bool
    network_disabled: bool
    broker_disabled: bool
    llm_disabled: bool
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class QlibManualExecutionPlan:
    dataset_id: str
    workflow_config_id: str
    config_summary: tuple[str, ...]
    execution_mode: str
    qrun_disabled_by_default: bool
    manual_local_only: bool
    required_user_confirmation: bool
    no_network_required: bool
    no_broker_required: bool
    no_account_required: bool
    result_import_path_placeholder: str
    warnings: tuple[str, ...]
    default_pytest_statement: str


@dataclass(frozen=True)
class QlibRuntimeResultRecord:
    result_source: str
    dataset_id: str
    workflow_config_id: str
    metrics: dict[str, float]
    missing_metric_reasons: dict[str, str]
    profitability_claim: bool
    benchmark: str
    stock_count: int
    etf_count: int
    execution_mode: str
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class QlibRuntimeResultImportResult:
    ok: bool
    runtime_state: str
    imported_records: tuple[QlibRuntimeResultRecord, ...]
    blockers: tuple[str, ...]
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class QlibRuntimeVsOfflineComparison:
    runtime_result_imported: bool
    qlib_available_status: str
    offline_vs_runtime_score_delta: float
    cost_aware_agreement: bool
    factor_signal_agreement: bool
    etf_coverage_preserved: bool
    promotion_decision: str
    promotion_reasons: tuple[str, ...]
    comparison_notes: tuple[str, ...]


@dataclass(frozen=True)
class P42ControlledQlibRuntimeReport:
    kept_qlib_optional: bool
    qrun_disabled_by_default: bool
    manual_execution_plan_produced: bool
    runtime_result_import_boundary_produced: bool
    imported_runtime_like_result_validated: bool
    comparison_against_p41_p40_completed: bool
    mixed_stock_etf_coverage_visible: bool
    avoided_profitability_claims: bool
    safety_barrier_percent: float
    next_improvement_target: str
    detection: QlibRuntimeDetectionResult
    manual_plan: QlibManualExecutionPlan
    import_result: QlibRuntimeResultImportResult
    comparison: QlibRuntimeVsOfflineComparison
    evidence_refs: tuple[str, ...]
