"""Report builder for the isolated RQAlpha prototype runner review."""

from __future__ import annotations

from pathlib import Path

from quantpilot_core.rqalpha_isolated_prototype_runner_review.contracts import (
    RqalphaIsolatedPrototypeReviewResult,
)
from quantpilot_core.rqalpha_isolated_prototype_runner_review.review import (
    review_rqalpha_isolated_prototype_runner,
)


def build_rqalpha_isolated_prototype_runner_review_report(
    project_root: Path | str = ".",
) -> dict[str, object]:
    """Build a plain report for the isolated prototype runner review."""

    result = review_rqalpha_isolated_prototype_runner(project_root)
    return {
        "status": result.status,
        "probe_importable": result.probe_importable,
        "probe_version": result.probe_version,
        "minimal_local_run_attempted": result.minimal_local_run_attempted,
        "minimal_local_run_succeeded": result.minimal_local_run_succeeded,
        "output_metrics_available": result.output_metrics_available,
        "command_spec_summary": _command_spec_summary(result),
        "artifact_review_summary": _artifact_review_summary(result),
        "warnings": result.warnings,
        "next_actions": result.next_actions,
        "production_ready": result.production_ready,
        "blocks_other_frameworks": result.blocks_other_frameworks,
    }


def _command_spec_summary(result: RqalphaIsolatedPrototypeReviewResult) -> dict[str, object]:
    spec = result.command_spec
    return {
        "environment_path": spec.environment_path,
        "output_artifact_path": spec.output_artifact_path,
        "account_type": spec.account_type,
        "initial_cash": spec.initial_cash,
        "frequency": spec.frequency,
        "run_type": spec.run_type,
        "uses_cli": spec.uses_cli,
        "uses_run_func": spec.uses_run_func,
        "statement": (
            "R4C defines CLI and run-function pathways for a future isolated attempt, "
            "but does not execute either path."
        ),
    }


def _artifact_review_summary(
    result: RqalphaIsolatedPrototypeReviewResult,
) -> dict[str, object]:
    if result.artifact_review is None:
        return {
            "reviewed": False,
            "metrics_available": False,
            "normalized_metric_names": (),
        }
    artifact_review = result.artifact_review
    return {
        "reviewed": True,
        "status": artifact_review.status,
        "artifact_path": artifact_review.artifact_path,
        "exists": artifact_review.exists,
        "metrics_available": artifact_review.metrics_available,
        "normalized_metric_names": tuple(
            metric.name for metric in artifact_review.normalized_metrics
        ),
        "warnings": artifact_review.warnings,
        "errors": artifact_review.errors,
    }
