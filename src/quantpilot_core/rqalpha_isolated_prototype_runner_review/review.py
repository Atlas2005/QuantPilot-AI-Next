"""Review the isolated RQAlpha prototype runner contract."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from quantpilot_core.rqalpha_isolated_prototype_runner_review.artifact_import import (
    DEFAULT_ARTIFACT_PATH,
    review_rqalpha_prototype_artifact,
)
from quantpilot_core.rqalpha_isolated_prototype_runner_review.contracts import (
    RqalphaIsolatedPrototypeReviewResult,
    RqalphaIsolatedPrototypeStatus,
    RqalphaPrototypeArtifactSchema,
    RqalphaPrototypeCommandSpec,
)


PROBE_SUMMARY_PATH = (
    "local_artifacts/backtest_prototypes/rqalpha/rqalpha_probe_summary.json"
)


def review_rqalpha_isolated_prototype_runner(
    project_root: Path | str = ".",
) -> RqalphaIsolatedPrototypeReviewResult:
    """Build a review-only contract for a future isolated local prototype attempt."""

    root = Path(project_root)
    probe_summary = _load_probe_summary(root / PROBE_SUMMARY_PATH)
    probe_exists = bool(probe_summary)
    probe_importable = probe_summary.get("rqalpha_importable") is True
    probe_version = _optional_string(probe_summary.get("rqalpha_version"))
    artifact_review = review_rqalpha_prototype_artifact(root)
    minimal_local_run_attempted = _first_bool(
        artifact_review.minimal_local_run_attempted,
        probe_summary.get("minimal_local_run_attempted"),
    )
    minimal_local_run_succeeded = _first_bool(
        artifact_review.minimal_local_run_succeeded,
        probe_summary.get("minimal_local_run_succeeded"),
    )
    output_metrics_available = (
        probe_summary.get("output_metrics_available") is True
        or artifact_review.metrics_available
    )
    status = _determine_status(
        probe_exists=probe_exists,
        probe_importable=probe_importable,
        artifact_exists=artifact_review.exists,
        artifact_status=artifact_review.status,
        minimal_local_run_attempted=minimal_local_run_attempted,
        minimal_local_run_succeeded=minimal_local_run_succeeded,
        output_metrics_available=output_metrics_available,
        artifact_metrics_available=artifact_review.metrics_available,
    )

    return RqalphaIsolatedPrototypeReviewResult(
        status=status,
        probe_summary_path=PROBE_SUMMARY_PATH,
        probe_importable=probe_importable,
        probe_version=probe_version,
        minimal_local_run_attempted=minimal_local_run_attempted,
        minimal_local_run_succeeded=minimal_local_run_succeeded,
        output_metrics_available=output_metrics_available,
        command_spec=_build_command_spec(),
        artifact_schema=_build_artifact_schema(),
        artifact_review=artifact_review,
        warnings=_build_warnings(status, probe_summary),
        next_actions=_build_next_actions(status),
        production_ready=False,
        blocks_other_frameworks=False,
    )


def _load_probe_summary(path: Path) -> dict[str, Any]:
    if not path.exists() or not path.is_file():
        return {}
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(loaded, dict):
        return {}
    safe_keys = {
        "rqalpha_importable",
        "rqalpha_version",
        "minimal_local_run_attempted",
        "minimal_local_run_succeeded",
        "fake_fixture_direct_support_observed",
        "output_metrics_available",
        "data_bundle_required_or_observed",
        "conclusion",
        "warnings",
        "errors",
    }
    return {key: loaded[key] for key in safe_keys if key in loaded}


def _build_command_spec() -> RqalphaPrototypeCommandSpec:
    return RqalphaPrototypeCommandSpec(
        environment_path=".venv-prototypes/rqalpha/",
        strategy_file=None,
        data_bundle_path=None,
        start_date=None,
        end_date=None,
        account_type="stock",
        initial_cash=100_000.0,
        frequency="1d",
        run_type="b",
        output_artifact_path=DEFAULT_ARTIFACT_PATH,
        uses_cli=True,
        uses_run_func=True,
    )


def _build_artifact_schema() -> RqalphaPrototypeArtifactSchema:
    return RqalphaPrototypeArtifactSchema(
        required_fields=(
            "status",
            "executed",
            "metrics",
        ),
        optional_fields=(
            "engine",
            "rqalpha_version",
            "environment_path",
            "warnings",
            "errors",
            "notes",
        ),
        metrics_fields=(
            "total_return",
            "annualized_return",
            "max_drawdown",
            "sharpe",
            "trade_count",
            "turnover",
        ),
        must_not_invent_metrics=True,
    )


def _determine_status(
    *,
    probe_exists: bool,
    probe_importable: bool,
    artifact_exists: bool,
    artifact_status: str,
    minimal_local_run_attempted: bool,
    minimal_local_run_succeeded: bool,
    output_metrics_available: bool,
    artifact_metrics_available: bool,
) -> str:
    if artifact_exists and artifact_status in {
        RqalphaIsolatedPrototypeStatus.LOCAL_RUN_FAILED.value,
        RqalphaIsolatedPrototypeStatus.OUTPUT_METRICS_MISSING.value,
        RqalphaIsolatedPrototypeStatus.LOCAL_RUN_SUCCEEDED.value,
    }:
        return artifact_status
    if not probe_exists:
        return RqalphaIsolatedPrototypeStatus.EVIDENCE_MISSING.value
    if probe_importable and not minimal_local_run_attempted:
        return RqalphaIsolatedPrototypeStatus.LOCAL_RUN_NOT_ATTEMPTED.value
    if minimal_local_run_attempted and not minimal_local_run_succeeded:
        return RqalphaIsolatedPrototypeStatus.LOCAL_RUN_FAILED.value
    if minimal_local_run_succeeded and not (
        output_metrics_available or artifact_metrics_available
    ):
        return RqalphaIsolatedPrototypeStatus.OUTPUT_METRICS_MISSING.value
    if minimal_local_run_succeeded and (
        output_metrics_available or artifact_metrics_available
    ):
        return RqalphaIsolatedPrototypeStatus.LOCAL_RUN_SUCCEEDED.value
    if probe_importable:
        return RqalphaIsolatedPrototypeStatus.IMPORT_ONLY_PROVEN.value
    return RqalphaIsolatedPrototypeStatus.READY_FOR_ISOLATED_RUNNER_ATTEMPT.value


def _build_warnings(
    status: str,
    probe_summary: dict[str, Any],
) -> tuple[str, ...]:
    warnings = [
        "R4C does not run RQAlpha and does not prove production readiness.",
        "RQAlpha remains optional and must stay outside the main project environment.",
        "vectorbt, Qlib, and DeepSeek workflows must not be blocked by RQAlpha gaps.",
    ]
    if status == RqalphaIsolatedPrototypeStatus.EVIDENCE_MISSING.value:
        warnings.append("No existing isolated probe summary was found.")
    for item in probe_summary.get("warnings", ()):
        if isinstance(item, str):
            warnings.append(item)
    return tuple(warnings)


def _build_next_actions(status: str) -> tuple[str, ...]:
    common = (
        "Keep any real RQAlpha attempt under .venv-prototypes/rqalpha/.",
        f"Write any future real output to {DEFAULT_ARTIFACT_PATH}.",
        "Import only explicit output metrics from a real artifact.",
    )
    if status == RqalphaIsolatedPrototypeStatus.EVIDENCE_MISSING.value:
        return (
            "Restore the isolated probe summary before planning a local runner attempt.",
            *common,
        )
    if status == RqalphaIsolatedPrototypeStatus.LOCAL_RUN_NOT_ATTEMPTED.value:
        return (
            "Resolve data bundle and config requirements before attempting an isolated local run.",
            *common,
        )
    if status == RqalphaIsolatedPrototypeStatus.OUTPUT_METRICS_MISSING.value:
        return (
            "Capture real RQAlpha output metrics in the expected artifact schema.",
            *common,
        )
    return (
        "Review the imported artifact before making any adapter or engine-selection decision.",
        *common,
    )


def _optional_string(value: object) -> str | None:
    if value is None:
        return None
    return str(value)


def _first_bool(*values: object) -> bool:
    for value in values:
        if isinstance(value, bool):
            return value
    return False
