"""Contracts for the isolated RQAlpha prototype runner review."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class RqalphaIsolatedPrototypeStatus(str, Enum):
    EVIDENCE_MISSING = "evidence_missing"
    IMPORT_ONLY_PROVEN = "import_only_proven"
    LOCAL_RUN_NOT_ATTEMPTED = "local_run_not_attempted"
    LOCAL_RUN_FAILED = "local_run_failed"
    LOCAL_RUN_SUCCEEDED = "local_run_succeeded"
    OUTPUT_METRICS_MISSING = "output_metrics_missing"
    READY_FOR_ISOLATED_RUNNER_ATTEMPT = "ready_for_isolated_runner_attempt"


@dataclass(frozen=True)
class RqalphaPrototypeCommandSpec:
    environment_path: str
    strategy_file: str | None
    data_bundle_path: str | None
    start_date: str | None
    end_date: str | None
    account_type: str
    initial_cash: float
    frequency: str
    run_type: str
    output_artifact_path: str
    uses_cli: bool
    uses_run_func: bool


@dataclass(frozen=True)
class RqalphaPrototypeArtifactSchema:
    required_fields: tuple[str, ...]
    optional_fields: tuple[str, ...]
    metrics_fields: tuple[str, ...]
    must_not_invent_metrics: bool = True


@dataclass(frozen=True)
class RqalphaPrototypeArtifactReviewResult:
    status: str
    artifact_path: str
    exists: bool
    metrics_available: bool
    normalized_metrics: tuple["RqalphaAshareBacktestMetric", ...]
    warnings: tuple[str, ...]
    errors: tuple[str, ...]


@dataclass(frozen=True)
class RqalphaIsolatedPrototypeReviewResult:
    status: str
    probe_summary_path: str
    probe_importable: bool
    probe_version: str | None
    minimal_local_run_attempted: bool
    minimal_local_run_succeeded: bool
    output_metrics_available: bool
    command_spec: RqalphaPrototypeCommandSpec
    artifact_schema: RqalphaPrototypeArtifactSchema
    artifact_review: RqalphaPrototypeArtifactReviewResult | None
    warnings: tuple[str, ...]
    next_actions: tuple[str, ...]
    production_ready: bool = False
    blocks_other_frameworks: bool = False
