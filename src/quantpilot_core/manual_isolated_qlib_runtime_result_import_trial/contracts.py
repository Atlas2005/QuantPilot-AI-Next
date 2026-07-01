"""Contracts for P44 manual isolated Qlib result import trial."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from quantpilot_core.controlled_optional_qlib_runtime_spike.contracts import (
    QlibRuntimeResultImportResult,
    QlibRuntimeResultRecord,
    QlibRuntimeVsOfflineComparison,
)


class QlibResultArtifactSourceType(str, Enum):
    P43_CAPTURE_TEMPLATE = "p43_capture_template"
    MANUAL_LOCAL_RESULT_RECORD = "manual_local_result_record"
    DETERMINISTIC_FIXTURE = "deterministic_fixture"


class QlibImportTrialStatus(str, Enum):
    NOT_ATTEMPTED = "not_attempted"
    ARTIFACT_LOADED = "artifact_loaded"
    IMPORT_ACCEPTED = "import_accepted"
    IMPORT_REJECTED = "import_rejected"
    COMPARISON_COMPLETED = "comparison_completed"


@dataclass(frozen=True)
class QlibResultArtifactLoadResult:
    ok: bool
    source_type: str
    status: str
    artifact_source: str
    normalized_record: QlibRuntimeResultRecord | None
    blockers: tuple[str, ...]
    warnings: tuple[str, ...]
    raw_artifact: dict[str, Any]


@dataclass(frozen=True)
class QlibImportTrialResult:
    ok: bool
    status: str
    artifact_loaded: bool
    import_accepted: bool
    rejection_reasons: tuple[str, ...]
    dataset_workflow_match: bool
    benchmark_present: bool
    mixed_stock_etf_coverage_preserved: bool
    ic_rankic_available: bool
    cost_aware_metric_available: bool
    profitability_claim_rejected: bool
    warnings_preserved: tuple[str, ...]
    load_result: QlibResultArtifactLoadResult
    p42_import_result: QlibRuntimeResultImportResult


@dataclass(frozen=True)
class QlibImportTrialComparison:
    import_trial_status: str
    offline_vs_runtime_score_delta: float
    cost_aware_agreement: bool
    factor_signal_agreement: bool
    etf_coverage_preserved: bool
    sufficient_for_real_optional_runtime_trial_decision: bool
    promotion_decision: str
    promotion_reasons: tuple[str, ...]
    comparison_notes: tuple[str, ...]
    p42_comparison: QlibRuntimeVsOfflineComparison


@dataclass(frozen=True)
class P44ManualQlibImportTrialReport:
    p43_compatible_result_artifact_loaded: bool
    imported_through_p42_boundary: bool
    import_accepted: bool
    mixed_stock_etf_counts_preserved: bool
    compared_against_p42_p41_p40_direction: bool
    avoided_qrun_and_runtime_import_by_default: bool
    avoided_profitability_claims: bool
    safety_barrier_percent: float
    next_step: str
    load_result: QlibResultArtifactLoadResult
    import_trial: QlibImportTrialResult
    comparison: QlibImportTrialComparison
    evidence_refs: tuple[str, ...]
